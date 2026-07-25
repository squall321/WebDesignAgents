# 회의 진행 상태 머신 — 다음 발언자 결정·턴 검증·라운드 전이·폐회 (결정론, LLM 무호출)
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/meetings/engine.py
# (copy-adapt: import 경로만 wdcore로 — 로직·검증 규칙은 원본 그대로)
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from wdcore.models.common import utcnow
from wdcore.models.meeting import (
    ArtifactType,
    MeetingMeta,
    MeetingStatus,
    MeetingTurn,
    MeetingType,
    RoundSpec,
    SpeakerRole,
)

from .minutes import render_minutes
from .store import MeetingStore
from .templates import MEETING_TEMPLATES


class MeetingEngine:
    """라운드 템플릿 기반 결정론적 회의 진행 엔진.

    발언 순서는 LLM 재량이 아니라 템플릿과 발언 이력으로 서버가 강제한다.
    registry(선택)를 주면 참가자 실존 검증과 회의록 표시 이름 조회에 사용한다.
    """

    def __init__(self, store: MeetingStore, registry=None) -> None:
        self.store = store
        self.registry = registry

    # --- 생성 ---
    def create(self, type: MeetingType | str, topic: str, participants: list[str]) -> MeetingMeta:
        """회의를 생성하고 meta.json을 저장한다. 참가 확정 순서가 곧 발언 순서다."""
        if len(set(participants)) != len(participants):
            raise ValueError("참가자 목록에 중복이 있다")
        if self.registry is not None:
            for pid in participants:
                self.registry.get(pid)  # 미존재 시 PersonaNotFoundError
        meta = MeetingMeta(
            id=str(uuid4()), type=MeetingType(type), topic=topic, participants=participants,
        )
        self.store.save_meta(meta)
        return meta

    # --- 다음 발언자 결정 (결정론 규칙) ---
    def next_speaker(
        self, meta: MeetingMeta, turns: list[MeetingTurn]
    ) -> tuple[SpeakerRole, str | None, RoundSpec, str]:
        """(역할, 페르소나 id | None, 라운드 스펙, 지시문)을 반환한다.

        - fixed: 항상 모더레이터.
        - round_robin: 이번 라운드 발언 수 % 참가자 수 위치의 참가자.
        - moderator_pick: 사이클마다 모더레이터가 먼저, 이후 참가 확정 순서 (결정론 구현).
        회의가 폐회됐거나 전 라운드가 끝났으면 ValueError.
        """
        if meta.status is MeetingStatus.closed:
            raise ValueError("이미 폐회된 회의다")
        specs = MEETING_TEMPLATES[meta.type]
        if meta.round_index >= len(specs):
            raise ValueError("모든 라운드가 종료됐다. close()로 회의록을 생성하라")
        spec = specs[meta.round_index]
        n = len(self._round_turns(meta, turns))
        if spec.speaker_order == "fixed":
            return SpeakerRole.moderator, None, spec, spec.instruction
        if spec.speaker_order == "round_robin":
            return (
                SpeakerRole.expert,
                meta.participants[n % len(meta.participants)],
                spec,
                spec.instruction,
            )
        # moderator_pick
        pos = n % (1 + len(meta.participants))
        if pos == 0:
            return SpeakerRole.moderator, None, spec, spec.instruction
        return SpeakerRole.expert, meta.participants[pos - 1], spec, spec.instruction

    # --- 턴 제출 (검증 경로) ---
    def submit_turn(
        self, meta: MeetingMeta, turn: MeetingTurn, known_refs: set[str]
    ) -> MeetingTurn:
        """턴을 검증·채번·영속화하고 라운드 전이와 상태를 갱신한다.

        거부(ValueError) 조건: 폐회됨 / round_no 불일치 / 발언 차례 불일치 /
        인용 필수 라운드에서 citations 비어 있음 / citations.ref가 known_refs 밖(환각 인용 차단).
        user·system 턴은 순서·인용 검증 없이 기록되고 라운드 진행에 영향을 주지 않는다.
        """
        if meta.status is MeetingStatus.closed:
            raise ValueError("폐회된 회의에는 턴을 제출할 수 없다")
        specs = MEETING_TEMPLATES[meta.type]
        if meta.round_index >= len(specs):
            raise ValueError("모든 라운드가 종료됐다. close()로 회의록을 생성하라")
        spec = specs[meta.round_index]
        if turn.round_no != meta.round_index:
            raise ValueError(
                f"현재 라운드는 {meta.round_index}({spec.name})인데 round_no={turn.round_no}가 제출됐다"
            )
        _, all_turns = self.store.load(meta.id)
        if turn.role in (SpeakerRole.expert, SpeakerRole.moderator):
            exp_role, exp_expert, _, _ = self.next_speaker(meta, all_turns)
            if turn.role is not exp_role or (
                exp_role is SpeakerRole.expert and turn.expert_id != exp_expert
            ):
                expected = exp_expert if exp_role is SpeakerRole.expert else "모더레이터"
                raise ValueError(f"지금은 {expected}의 차례다")
            if spec.citation_required and not turn.citations:
                raise ValueError(f"'{spec.name}' 라운드는 근거 인용이 필수다. citations를 채워라")
            for c in turn.citations:
                if c.ref not in known_refs:
                    raise ValueError(
                        f"존재하지 않는 인용 ref: {c.ref!r}. 브리핑에 제공된 ID/라벨만 사용하라"
                    )
        turn = turn.model_copy(update={"turn_no": len(all_turns) + 1})
        self.store.append_turn(meta, turn)
        if meta.status is MeetingStatus.created:
            meta.status = MeetingStatus.in_progress
        self._maybe_transition(meta, all_turns + [turn], spec)
        self.store.save_meta(meta)
        return turn

    # --- 폐회 ---
    def close(self, meta: MeetingMeta, turns: list[MeetingTurn]) -> Path:
        """회의를 닫고 minutes.md를 생성해 경로를 반환한다."""
        if meta.status is MeetingStatus.closed:
            raise ValueError("이미 폐회된 회의다")
        experts: dict[str, str] = {}
        if self.registry is not None:
            for pid in meta.participants:
                experts[pid] = self.registry.get(pid).name_ko
        meta.status = MeetingStatus.closed
        meta.closed_at = utcnow()
        path = self.store.save_minutes(meta, render_minutes(meta, turns, experts))
        self.store.save_meta(meta)
        return path

    # --- 내부 ---
    @staticmethod
    def _round_turns(meta: MeetingMeta, turns: list[MeetingTurn]) -> list[MeetingTurn]:
        """현재 라운드의 진행 카운트 대상 턴 (user/system 제외)."""
        return [
            t
            for t in turns
            if t.round_no == meta.round_index
            and t.role in (SpeakerRole.expert, SpeakerRole.moderator)
        ]

    @staticmethod
    def _expected_turns(spec: RoundSpec, participants: list[str]) -> int:
        if spec.speaker_order == "fixed":
            return spec.cycles
        if spec.speaker_order == "round_robin":
            return spec.cycles * len(participants)
        return spec.cycles * (1 + len(participants))  # moderator_pick

    def _maybe_transition(
        self, meta: MeetingMeta, turns: list[MeetingTurn], spec: RoundSpec
    ) -> bool:
        """라운드 전이 조건 평가: 정량(예정 발언 수 완료) 또는 조기 종료(decision 산출물)."""
        round_turns = self._round_turns(meta, turns)
        done = len(round_turns) >= self._expected_turns(spec, meta.participants)
        if not done and spec.allow_early_close and round_turns:
            done = any(a.type is ArtifactType.decision for a in round_turns[-1].artifacts)
        if done:
            meta.round_index += 1
        return done
