# wdcore MeetingEngine 결정론 검증 — 발언 순서 강제·차례 위반 거부·인용 규칙·조기 종료
from __future__ import annotations

import pytest

from wdcore.meetings import MeetingEngine, MeetingStore
from wdcore.models import Artifact, ArtifactType, Citation, MeetingStatus, MeetingTurn, SpeakerRole

P1 = "vis-typographer"
P2 = "vis-color-brand"
P3 = "impl-technical-director"


@pytest.fixture()
def engine(tmp_path):
    return MeetingEngine(MeetingStore(root=tmp_path / "meetings"))


def _turn(round_no, role, expert_id=None, content="발언 내용", stance=None, citations=None, artifacts=None):
    return MeetingTurn(
        round_no=round_no,
        role=role,
        expert_id=expert_id,
        stance=stance,
        content_md=content,
        citations=citations or [],
        artifacts=artifacts or [],
    )


def test_next_speaker_order_is_deterministic(engine):
    """brainstorm R1(round_robin cycles=2)은 참가 확정 순서를 정확히 2바퀴 강제한다."""
    meta = engine.create("brainstorm", "컨셉 도출", [P1, P2, P3])
    expected_sequence = [P1, P2, P3, P1, P2, P3]
    for expected in expected_sequence:
        _, turns = engine.store.load(meta.id)
        role, pid, spec, _ = engine.next_speaker(meta, turns)
        assert role is SpeakerRole.expert
        assert pid == expected
        assert spec.name == "diverge"
        engine.submit_turn(meta, _turn(0, SpeakerRole.expert, pid), known_refs=set())
    # 2사이클 완료 → R2(build_on)로 전이
    assert meta.round_index == 1
    _, turns = engine.store.load(meta.id)
    role, pid, spec, _ = engine.next_speaker(meta, turns)
    assert (role, pid, spec.name) == (SpeakerRole.expert, P1, "build_on")


def test_out_of_turn_submission_rejected(engine):
    """차례가 아닌 참가자·역할의 제출은 거부되고 상태가 변하지 않는다."""
    meta = engine.create("brainstorm", "컨셉 도출", [P1, P2])
    # P1 차례에 P2가 제출
    with pytest.raises(ValueError, match="차례"):
        engine.submit_turn(meta, _turn(0, SpeakerRole.expert, P2), known_refs=set())
    # expert 차례에 모더레이터가 제출
    with pytest.raises(ValueError, match="차례"):
        engine.submit_turn(meta, _turn(0, SpeakerRole.moderator), known_refs=set())
    _, turns = engine.store.load(meta.id)
    assert turns == []
    assert meta.round_index == 0


def test_wrong_round_no_rejected(engine):
    meta = engine.create("brainstorm", "컨셉 도출", [P1, P2])
    with pytest.raises(ValueError, match="round_no"):
        engine.submit_turn(meta, _turn(1, SpeakerRole.expert, P1), known_refs=set())


def test_citation_required_round_rejects_missing_and_unknown_refs(engine):
    """scenario_build R2(cross_rebuttal)는 인용 없는 제출과 known_refs 밖 ref를 거부한다."""
    meta = engine.create("scenario_build", "시나리오 빌드", [P3, P1])
    # R1 structure_diverge(fixed) — 모더레이터 1턴으로 종료
    engine.submit_turn(meta, _turn(0, SpeakerRole.moderator, content="구조 초안 대독"), known_refs=set())
    assert meta.round_index == 1

    known = {"TD-R-001"}
    # 인용 없음 → 거부
    with pytest.raises(ValueError, match="인용이 필수"):
        engine.submit_turn(meta, _turn(1, SpeakerRole.expert, P3), known_refs=known)
    # known_refs 밖 ref → 거부 (환각 인용 차단)
    bad = _turn(1, SpeakerRole.expert, P3, citations=[Citation(ref="TD-R-999")])
    with pytest.raises(ValueError, match="존재하지 않는 인용"):
        engine.submit_turn(meta, bad, known_refs=known)
    # 화이트리스트 안 ref → 수리
    ok = _turn(1, SpeakerRole.expert, P3, stance="rebut", citations=[Citation(ref="TD-R-001")])
    accepted = engine.submit_turn(meta, ok, known_refs=known)
    assert accepted.turn_no == 2


def test_early_close_on_decision_artifact(engine):
    """allow_early_close 라운드는 decision 산출물 제출 시 예정 발언 수 전에 전이한다."""
    meta = engine.create("brainstorm", "컨셉 도출", [P1, P2])
    # R1 diverge: round_robin cycles=2 → 예정 4턴이지만 2턴째 decision으로 조기 종료
    engine.submit_turn(meta, _turn(0, SpeakerRole.expert, P1), known_refs=set())
    assert meta.round_index == 0
    decision = _turn(
        0, SpeakerRole.expert, P2,
        artifacts=[Artifact(type=ArtifactType.decision, content="톤은 신뢰-기술 축으로 확정")],
    )
    engine.submit_turn(meta, decision, known_refs=set())
    assert meta.round_index == 1


def test_user_turn_recorded_without_order_check(engine):
    """user 턴은 순서 검증 없이 기록되고 라운드 진행에 영향을 주지 않는다."""
    meta = engine.create("brainstorm", "컨셉 도출", [P1, P2])
    engine.submit_turn(meta, _turn(0, SpeakerRole.user, content="러닝타임은 90초로"), known_refs=set())
    assert meta.round_index == 0
    _, turns = engine.store.load(meta.id)
    assert len(turns) == 1
    # 다음 발언자는 여전히 P1
    role, pid, _, _ = engine.next_speaker(meta, turns)
    assert (role, pid) == (SpeakerRole.expert, P1)


def test_close_and_reject_after_close(engine):
    meta = engine.create("brainstorm", "컨셉 도출", [P1, P2])
    engine.submit_turn(meta, _turn(0, SpeakerRole.expert, P1), known_refs=set())
    _, turns = engine.store.load(meta.id)
    path = engine.close(meta, turns)
    assert path.name == "minutes.md" and path.is_file()
    assert meta.status is MeetingStatus.closed
    with pytest.raises(ValueError, match="폐회"):
        engine.submit_turn(meta, _turn(0, SpeakerRole.expert, P2), known_refs=set())
    with pytest.raises(ValueError, match="폐회"):
        engine.close(meta, turns)
