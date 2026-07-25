# wdcore MeetingStore 영속화 검증 — 파일 재조립(resume)·목록·미존재 조회
from __future__ import annotations

import pytest

from wdcore.meetings import MeetingEngine, MeetingStore
from wdcore.models import Citation, MeetingStatus, MeetingTurn, SpeakerRole

P1 = "impl-technical-director"
P2 = "ux-accessibility"


def _turn(round_no, role, expert_id=None, content="발언", citations=None):
    return MeetingTurn(
        round_no=round_no, role=role, expert_id=expert_id,
        content_md=content, citations=citations or [],
    )


def test_resume_from_files_only(tmp_path):
    """meta.json + turns.jsonl만으로 새 엔진이 회의를 재조립해 이어간다 (파일이 진실)."""
    root = tmp_path / "meetings"
    engine1 = MeetingEngine(MeetingStore(root=root))
    meta1 = engine1.create("scenario_build", "소개영상 시나리오", [P1, P2])
    engine1.submit_turn(meta1, _turn(0, SpeakerRole.moderator, content="구조 초안 대독"), known_refs=set())

    # 완전히 새로운 store/engine 인스턴스로 재조립
    engine2 = MeetingEngine(MeetingStore(root=root))
    meta2, turns2 = engine2.store.load(meta1.id)
    assert meta2.id == meta1.id
    assert meta2.status is MeetingStatus.in_progress
    assert meta2.round_index == 1  # R1 fixed 1턴 완료 상태가 복원됨
    assert len(turns2) == 1
    assert turns2[0].content_md == "구조 초안 대독"

    # 재조립된 meta로 다음 라운드(cross_rebuttal, citation_required)를 이어서 진행
    role, pid, spec, _ = engine2.next_speaker(meta2, turns2)
    assert (role, pid, spec.name) == (SpeakerRole.expert, P1, "cross_rebuttal")
    engine2.submit_turn(
        meta2,
        _turn(1, SpeakerRole.expert, P1, citations=[Citation(ref="TD-R-001")]),
        known_refs={"TD-R-001"},
    )
    # 세 번째 재조립으로 두 턴이 모두 남았는지 확인
    meta3, turns3 = MeetingStore(root=root).load(meta1.id)
    assert [t.turn_no for t in turns3] == [1, 2]
    assert meta3.round_index == 1  # R2는 2인 round_robin — 1턴 남음


def test_close_after_resume_writes_minutes(tmp_path):
    root = tmp_path / "meetings"
    engine1 = MeetingEngine(MeetingStore(root=root))
    meta1 = engine1.create("brainstorm", "Concept Sprint", [P1, P2])
    engine1.submit_turn(meta1, _turn(0, SpeakerRole.expert, P1), known_refs=set())

    engine2 = MeetingEngine(MeetingStore(root=root))
    meta2, turns2 = engine2.store.load(meta1.id)
    path = engine2.close(meta2, turns2)
    assert path.is_file()
    assert "[회의록]" in path.read_text(encoding="utf-8")
    # 폐회 상태도 파일로 영속화 → 재조립 시 closed
    meta3, _ = engine2.store.load(meta1.id)
    assert meta3.status is MeetingStatus.closed
    assert meta3.closed_at is not None


def test_dir_naming_and_listing(tmp_path):
    root = tmp_path / "meetings"
    store = MeetingStore(root=root)
    engine = MeetingEngine(store)
    meta = engine.create("brainstorm", "HWAX Intro Video!", [P1])
    d = store.find_dir(meta.id)
    # {stamp}_{type}_{slug}_{id4} 규칙
    assert d.name.endswith(f"_{meta.id[:4]}")
    assert "_brainstorm_hwax-intro-video_" in d.name
    metas = store.list_meetings()
    assert [m.id for m in metas] == [meta.id]


def test_find_unknown_meeting_raises(tmp_path):
    store = MeetingStore(root=tmp_path / "meetings")
    with pytest.raises(FileNotFoundError):
        store.load("00000000-0000-0000-0000-000000000000")
