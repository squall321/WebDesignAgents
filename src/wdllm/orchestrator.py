# 무인 심의 오케스트레이터 — next_speaker→격리 브리핑→LLM→submit_turn 턴 루프 (경로 B, PLAN §3)
"""wdcore.MeetingEngine 위에서 vLLM(또는 FakeLLM)으로 회의를 무인 완주한다.

턴 루프: engine.next_speaker → 브리핑 조립 → LLM 호출(MeetingTurn 부분 스키마
JSON 강제) → engine.submit_turn 검증 → 거부 시 hint 로 repair 1회 → 재실패 시
skip 기록 후 중단(같은 발언자가 다시 지목되므로 계속하면 무한루프).

페르소나 격리 — 매 턴 messages 를 [system(해당 페르소나 system_prompt),
user(브리핑)] 로 독립 구성한다. 전체 대화 이력은 공유하지 않고 최근 턴 gist 만
브리핑에 요약해 넣는다. 발언자 신원(round_no/role/expert_id)은 LLM 출력이 아니라
엔진의 next_speaker 결정을 그대로 쓴다 — LLM 은 stance/content_md/citations/
artifacts 부분 스키마만 채운다 (타인 명의 발화 구조적 차단).

보고서 조각 브리핑 — run(run_id=... | fragments_path=...) 로
data/pipeline/{run_id}/fragments.json 을 로드하면 조각(frag_id/text)이 매 턴
[F#] 근거 목록에 카드와 함께 편입되고, frag_id 전체가 초기 known_refs
인용 화이트리스트가 된다 (PLAN §4 P1 계약 — 경로 A meeting_start(run_id)와
동일 의미론).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import get_args

import structlog

from wdcore.config import get_settings
from wdcore.meetings.engine import MeetingEngine
from wdcore.models.meeting import (
    Artifact,
    ArtifactType,
    Citation,
    MeetingMeta,
    MeetingTurn,
    RoundSpec,
    SpeakerRole,
    Stance,
)

from wdmcp.session import split_fact_structure

from .client import LLMError, SupportsChat, chat_json

log = structlog.get_logger("wdllm.orchestrator")

MODERATOR_SYSTEM_PROMPT = (
    "너는 이 회의의 모더레이터(크리에이티브 디렉터)다. 진행·쟁점 조직화·판정 집계만 하고 "
    "새로운 기술적 주장은 만들지 않는다. 참가자 발언을 요약·군집화하고 라운드 지시를 수행하라."
)

_STANCE_VALUES = set(get_args(Stance))
_ARTIFACT_VALUES = {a.value for a in ArtifactType}


@dataclass
class RunResult:
    """회의 1건 무인 실행 결과."""

    meeting_id: str
    status: str  # "closed" | "stalled"
    turns_submitted: int = 0
    repairs: int = 0
    skips: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {
        "calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
    })
    minutes_path: Path | None = None


class AutoOrchestrator:
    """MeetingEngine + LLM 클라이언트(.chat)로 회의를 무인 진행한다."""

    def __init__(
        self,
        engine: MeetingEngine,
        llm: SupportsChat,
        registry=None,
        *,
        max_facts: int = 6,
        recent_n: int = 4,
        parse_retries: int = 2,
    ) -> None:
        self.engine = engine
        self.llm = llm
        self.registry = registry if registry is not None else engine.registry
        self.max_facts = max_facts
        self.recent_n = recent_n
        self.parse_retries = parse_retries
        # (frag_id, 라벨, 본문) — run()에서 설정. 라벨은 구조 요약("표 4열×7행: …")이거나
        # 구조가 없으면 "조각:{type}" 이다.
        self._fragments: list[tuple[str, str, str]] = []

    # --- 실행 ---
    def run(
        self,
        meta: MeetingMeta,
        *,
        max_turns: int | None = None,
        run_id: str | None = None,
        fragments_path: Path | None = None,
    ) -> RunResult:
        """전 라운드 무인 완주. 완주 시 폐회(minutes.md)까지 수행한다.

        max_turns 를 주면 그만큼 제출 후 폐회 없이 멈춘다(status="paused") —
        실 vLLM 1턴 스모크 등 부분 실행용.

        run_id 를 주면 data/pipeline/{run_id}/fragments.json 을 로드해 조각을
        매 턴 [F#] 근거로 브리핑하고, frag_id 목록을 초기 known_refs 인용
        화이트리스트로 쓴다. fragments_path 로 파일 경로를 직접 줄 수도 있다
        (지정 시 run_id 보다 우선). 파일이 없으면 FileNotFoundError.
        """
        self._fragments = self._load_fragments(run_id, fragments_path)
        result = RunResult(meeting_id=meta.id, status="stalled")
        # PLAN §4 P1 — frag_id 목록이 회의의 초기 known_refs 화이트리스트가 된다
        known_refs: set[str] = {fid for fid, _, _ in self._fragments}
        while True:
            if max_turns is not None and result.turns_submitted >= max_turns:
                result.status = "paused"
                break
            _, turns = self.engine.store.load(meta.id)
            try:
                role, speaker_id, spec, instruction = self.engine.next_speaker(meta, turns)
            except ValueError:
                # 전 라운드 종료 → 폐회
                result.minutes_path = self.engine.close(meta, turns)
                result.status = "closed"
                break
            ok = self._one_turn(
                meta, turns, role, speaker_id, spec, instruction, known_refs, result
            )
            if not ok:
                result.status = "stalled"
                break
        self._write_usage(meta, result)
        log.info(
            "meeting_run_done", meeting_id=meta.id, status=result.status,
            turns=result.turns_submitted, repairs=result.repairs,
            skips=len(result.skips), tokens=result.usage["total_tokens"],
        )
        return result

    # --- 턴 1건 (호출→검증→repair→skip) ---
    def _one_turn(
        self,
        meta: MeetingMeta,
        turns: list[MeetingTurn],
        role: SpeakerRole,
        speaker_id: str | None,
        spec: RoundSpec,
        instruction: str,
        known_refs: set[str],
        result: RunResult,
    ) -> bool:
        messages = self._build_messages(meta, turns, role, speaker_id, spec, instruction, known_refs)
        try:
            data, calls = chat_json(self.llm, messages, parse_retries=self.parse_retries)
        except LLMError as exc:
            self._record_skip(meta, role, speaker_id, spec, str(exc), result)
            return False
        self._add_usage(result, calls)

        error = self._try_submit(meta, role, speaker_id, data, known_refs)
        if error is None:
            result.turns_submitted += 1
            return True

        # repair 1회 — 같은 발언자 격리 messages 에 거부 사유(hint)만 덧붙인다
        repair_messages = messages + [
            {"role": "assistant", "content": json.dumps(data, ensure_ascii=False)},
            {
                "role": "user",
                "content": (
                    f"[수정요청] 직전 제출이 거부되었다: {error}\n"
                    "같은 발언자·라운드 그대로, 규칙을 지켜 JSON 객체 하나만 다시 출력하라. "
                    "citations 의 ref 는 [근거]에 제시된 값만 쓸 수 있다."
                ),
            },
        ]
        try:
            data2, calls2 = chat_json(self.llm, repair_messages, parse_retries=self.parse_retries)
        except LLMError as exc:
            self._record_skip(meta, role, speaker_id, spec, str(exc), result)
            return False
        self._add_usage(result, calls2)

        error2 = self._try_submit(meta, role, speaker_id, data2, known_refs)
        if error2 is None:
            result.repairs += 1
            result.turns_submitted += 1
            log.info("turn_repaired", meeting_id=meta.id, speaker=speaker_id or "moderator")
            return True
        self._record_skip(meta, role, speaker_id, spec, error2, result)
        return False

    def _try_submit(
        self,
        meta: MeetingMeta,
        role: SpeakerRole,
        speaker_id: str | None,
        data: dict,
        known_refs: set[str],
    ) -> str | None:
        """부분 스키마 → MeetingTurn → 엔진 제출. 성공 None, 실패 시 hint 문자열."""
        try:
            turn = self._build_turn(meta, role, speaker_id, data)
            self.engine.submit_turn(meta, turn, known_refs)
        except (ValueError, LLMError) as exc:
            return str(exc)
        return None

    @staticmethod
    def _build_turn(
        meta: MeetingMeta, role: SpeakerRole, speaker_id: str | None, data: dict
    ) -> MeetingTurn:
        """LLM 부분 스키마(dict) → MeetingTurn. 신원 필드는 엔진 결정을 강제한다.

        stance/artifacts 는 관대하게 보정(모르는 값은 버림)하되 content_md 부재와
        citations 형식 오류는 ValueError 로 올려 repair 경로를 태운다.
        """
        content = str(data.get("content_md") or "").strip()
        if not content:
            raise ValueError("content_md 가 비어 있다. 발언 본문을 채워라")
        stance = data.get("stance")
        if stance not in _STANCE_VALUES:
            stance = None
        citations = []
        for c in data.get("citations") or []:
            if isinstance(c, dict) and c.get("ref"):
                citations.append(Citation(ref=str(c["ref"]), quote=str(c.get("quote") or "")))
        artifacts = []
        for a in data.get("artifacts") or []:
            if isinstance(a, dict) and a.get("type") in _ARTIFACT_VALUES and a.get("content"):
                artifacts.append(Artifact(type=ArtifactType(a["type"]), content=str(a["content"])))
        return MeetingTurn(
            round_no=meta.round_index,
            role=role,
            expert_id=speaker_id if role is SpeakerRole.expert else None,
            stance=stance,
            content_md=content,
            citations=citations,
            artifacts=artifacts,
        )

    # --- 브리핑 조립 (페르소나 격리) ---
    def _build_messages(
        self,
        meta: MeetingMeta,
        turns: list[MeetingTurn],
        role: SpeakerRole,
        speaker_id: str | None,
        spec: RoundSpec,
        instruction: str,
        known_refs: set[str],
    ) -> list[dict]:
        if role is SpeakerRole.moderator:
            system = MODERATOR_SYSTEM_PROMPT
        else:
            persona = self.registry.get(speaker_id) if self.registry is not None else None
            system = persona.persona.system_prompt if persona else f"너는 페르소나 {speaker_id} 다."

        # 조각은 라운드 지시·gist 와 같은 층위 — 역할 무관 매 턴 브리핑에 포함 (모더레이터 대독 포함)
        facts: list[tuple[str, str, str]] = [
            (fid, label, text[:200]) for fid, label, text in self._fragments
        ]
        if role is SpeakerRole.expert:
            facts += self._facts_for(speaker_id)
        known_refs.update(ref for ref, _, _ in facts)

        lines = [
            f"[회의] type={meta.type.value} topic={meta.topic}",
            f"[라운드] no={meta.round_index} name={spec.name} "
            f"citation_required={'true' if spec.citation_required else 'false'}",
            f"[발언자] role={role.value} id={speaker_id or '-'}",
            f"[지시] {instruction}",
            "[최근턴]",
        ]
        recent = [
            t for t in turns
            if t.role in (SpeakerRole.expert, SpeakerRole.moderator)
        ][-self.recent_n:]
        if not recent:
            lines.append("- (아직 발언 없음)")
        for t in recent:
            gist = (t.content_md.strip().splitlines() or [""])[0][:150]
            lines.append(
                f"- turn={t.turn_no} speaker={t.expert_id or t.role.value} "
                f"stance={t.stance or '-'} gist={gist}"
            )
        lines.append("[근거] 인용(citations)의 ref 에는 아래 목록의 ref 값만 쓸 수 있다.")
        if facts:
            for i, (ref, title, gist) in enumerate(facts, start=1):
                lines.append(f"[F{i}] ref={ref} | {title} | {gist}")
        elif spec.citation_required and known_refs:
            # 모더레이터 등 자기 근거가 없는 발언자용 — 회의에 이미 전달된 ref 재사용
            lines.append("(기전달 근거) " + ", ".join(f"ref={r}" for r in sorted(known_refs)))
        else:
            lines.append("(이번 턴 제공 근거 없음)")
        lines += [
            "[출력형식] 설명 없이 JSON 객체 하나만 출력하라. 키: stance, content_md, citations, artifacts.",
            f"- stance: {sorted(_STANCE_VALUES)} 중 하나",
            "- content_md: 200~1500자 1인칭 발언 (마크다운)",
            '- citations: [{"ref": "...", "quote": "..."}] — [근거]의 ref 만 허용'
            + (" (이번 라운드 인용 필수)" if spec.citation_required else ""),
            '- artifacts: [{"type": "...", "content": "..."}], '
            f"type 은 {sorted(_ARTIFACT_VALUES)} 중 하나",
        ]
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": "\n".join(lines)},
        ]

    @staticmethod
    def _load_fragments(
        run_id: str | None, fragments_path: Path | None
    ) -> list[tuple[str, str, str]]:
        """fragments.json → (frag_id, 라벨, 본문) 목록. run_id·경로 둘 다 없으면 빈 목록.

        구조 위젯 조각은 라벨이 구조 요약 한 줄이 되어 [F#] 줄이
        `[F7] ref=RA-x-012 | 표 4열×7행: 단계/담당/기한/상태 | 배포 절차 표` 로 찍힌다.
        구조가 없는 조각은 종전대로 `조각:{type}` 라벨을 쓴다.
        """
        if fragments_path is None:
            if run_id is None:
                return []
            fragments_path = get_settings().pipeline_dir / run_id / "fragments.json"
        if not fragments_path.is_file():
            raise FileNotFoundError(f"fragments.json 없음: {fragments_path}")
        raw = json.loads(fragments_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError(f"fragments.json 형식 오류(리스트 아님): {fragments_path}")
        out: list[tuple[str, str, str]] = []
        for f in raw:
            if not isinstance(f, dict) or not f.get("frag_id"):
                continue
            summary, body = split_fact_structure(f)
            label = summary or f"조각:{f.get('type', '')}"
            out.append((str(f["frag_id"]), label, body))
        return out

    def _facts_for(self, speaker_id: str | None) -> list[tuple[str, str, str]]:
        """발언자 브리핑용 (ref, title, gist) 목록 — 자기 카드 우선, 부족분은 전역 카드로 보충."""
        if self.registry is None or speaker_id is None:
            return []
        own = self.registry.cards_for(speaker_id)
        pool = own + [c for c in self.registry.all_cards() if c.owner_id != speaker_id]
        facts = []
        for card in pool[: self.max_facts]:
            gist = (card.body_md.strip().splitlines() or [""])[0][:120]
            facts.append((card.id, card.title, gist))
        return facts

    # --- 기록 ---
    def _record_skip(
        self,
        meta: MeetingMeta,
        role: SpeakerRole,
        speaker_id: str | None,
        spec: RoundSpec,
        reason: str,
        result: RunResult,
    ) -> None:
        speaker = speaker_id or "moderator"
        result.skips.append({
            "round_no": meta.round_index, "round_name": spec.name,
            "speaker": speaker, "reason": reason,
        })
        log.warning(
            "turn_skipped", meeting_id=meta.id, round=spec.name,
            speaker=speaker, reason=reason[:200],
        )
        # 감사 흔적 — system 턴은 순서 검증 없이 기록되고 진행에 영향 없음
        skip_turn = MeetingTurn(
            round_no=meta.round_index,
            role=SpeakerRole.system,
            content_md=f"[skip] round={spec.name} speaker={speaker} 사유: {reason[:300]}",
        )
        self.engine.submit_turn(meta, skip_turn, set())

    @staticmethod
    def _add_usage(result: RunResult, calls: list) -> None:
        for r in calls:
            u = r.usage or {}
            result.usage["calls"] += 1
            for k in ("prompt_tokens", "completion_tokens", "total_tokens"):
                result.usage[k] += int(u.get(k) or 0)

    def _write_usage(self, meta: MeetingMeta, result: RunResult) -> None:
        """회의당 토큰 사용량을 회의 디렉터리에 usage.json 으로 기록한다."""
        d = self.engine.store.dir_for(meta)
        d.mkdir(parents=True, exist_ok=True)
        payload = {
            "meeting_id": meta.id,
            "status": result.status,
            "turns_submitted": result.turns_submitted,
            "repairs": result.repairs,
            "skips": result.skips,
            **result.usage,
        }
        (d / "usage.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
