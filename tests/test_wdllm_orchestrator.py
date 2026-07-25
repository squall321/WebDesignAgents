# wdllm 무인 오케스트레이터 검증 — FakeLLM scenario_build 완주·페르소나 격리·repair·skip 경로
from __future__ import annotations

import json

import pytest

from wdcore.config import get_settings
from wdcore.meetings import MeetingEngine, MeetingStore
from wdcore.models import ArtifactType, MeetingStatus, SpeakerRole
from wdcore.registry.registry import load_registry
from wdllm.fake import HALLUCINATED_REF, FakeLLM
from wdllm.orchestrator import AutoOrchestrator

# 5인 참가 (ST/TD/AX/MO/QA — QA 는 자기 카드 0장 → 전역 카드 보충 경로 검증)
PARTICIPANTS = [
    "narr-story-architect",
    "impl-technical-director",
    "ux-accessibility",
    "mot-motion-director",
    "qa-consistency",
]
# scenario_build 예정 턴 수: R1 fixed 1 + R2 round_robin 5 + R3 moderator_pick 2*(1+5)=12 + R4 fixed 1
EXPECTED_TURNS = 19


@pytest.fixture(scope="module")
def registry():
    return load_registry()


def _setup(tmp_path, registry, llm):
    engine = MeetingEngine(MeetingStore(root=tmp_path / "meetings"), registry)
    meta = engine.create("scenario_build", "데모 리포트 시나리오 빌드", PARTICIPANTS)
    return engine, meta, AutoOrchestrator(engine, llm, registry)


def test_full_scenario_build_meeting_completes(tmp_path, registry):
    """R1~R4 무인 완주 → turns.jsonl·minutes.md·usage.json 생성, 토큰 집계."""
    engine, meta, orch = _setup(tmp_path, registry, FakeLLM())
    result = orch.run(meta)

    assert result.status == "closed"
    assert result.turns_submitted == EXPECTED_TURNS
    assert result.repairs == 0 and result.skips == []
    assert meta.status is MeetingStatus.closed and meta.round_index == 4

    d = engine.store.find_dir(meta.id)
    assert (d / "turns.jsonl").is_file()
    assert (d / "minutes.md").is_file() and result.minutes_path == d / "minutes.md"
    usage = json.loads((d / "usage.json").read_text(encoding="utf-8"))
    assert usage["calls"] == EXPECTED_TURNS  # repair 없음 → 턴당 1호출
    assert usage["total_tokens"] > 0
    assert result.usage["calls"] == EXPECTED_TURNS

    _, turns = engine.store.load(meta.id)
    speak = [t for t in turns if t.role in (SpeakerRole.expert, SpeakerRole.moderator)]
    assert len(speak) == EXPECTED_TURNS

    # R2(cross_rebuttal) — 5인 전원이 발언 순서대로, 실존 ref 인용
    r2 = [t for t in speak if t.round_no == 1]
    assert [t.expert_id for t in r2] == PARTICIPANTS
    assert all(t.citations and t.citations[0].ref != HALLUCINATED_REF for t in r2)
    # ST 의 scenario_patch 독점 작성권 (R3)
    r3_st = [t for t in speak if t.round_no == 2 and t.expert_id == "narr-story-architect"]
    assert any(a.type is ArtifactType.scenario_patch for t in r3_st for a in t.artifacts)
    # R4 verdict — decision 산출물
    r4 = [t for t in speak if t.round_no == 3]
    assert any(a.type is ArtifactType.decision for t in r4 for a in t.artifacts)


def test_persona_isolation_no_cross_speaker_utterance(tmp_path, registry):
    """발언자 아닌 명의 발화 0건 — 브리핑된 발언자와 기록된 신원이 전 턴 일치."""
    engine, meta, orch = _setup(tmp_path, registry, FakeLLM())
    orch.run(meta)
    _, turns = engine.store.load(meta.id)
    experts = [t for t in turns if t.role is SpeakerRole.expert]
    moderators = [t for t in turns if t.role is SpeakerRole.moderator]
    assert experts and moderators
    # FakeLLM 은 브리핑의 [발언자] id 를 content_md 머리에 새긴다 — 신원 불일치면 즉시 드러남
    violations = [t for t in experts if not t.content_md.startswith(f"[{t.expert_id}]")]
    assert violations == []
    assert all(t.content_md.startswith("[moderator]") for t in moderators)
    assert all(t.expert_id is None for t in moderators)


def test_citation_violation_triggers_repair_and_recovers(tmp_path, registry):
    """환각 인용 1회 주입 → 엔진 거부 → hint repair 1회로 회복, 회의는 완주."""
    # call#2 = R2 첫 발언자(ST) — 환각 ref 로 제출 → repair(call#3)는 정상
    fake = FakeLLM(bad_ref_calls={2})
    engine, meta, orch = _setup(tmp_path, registry, fake)
    result = orch.run(meta)

    assert result.status == "closed"
    assert result.repairs == 1 and result.skips == []
    assert result.turns_submitted == EXPECTED_TURNS
    assert result.usage["calls"] == EXPECTED_TURNS + 1  # repair 재호출 1회

    _, turns = engine.store.load(meta.id)
    st_r2 = next(
        t for t in turns
        if t.round_no == 1 and t.expert_id == "narr-story-architect"
    )
    assert st_r2.citations[0].ref != HALLUCINATED_REF  # 수리된 인용
    assert "수정요청을 반영" in st_r2.content_md


def test_brainstorm_meeting_completes_with_moderator_citation(tmp_path, registry):
    """brainstorm 완주 — converge(citation_required) 모더레이터 턴도 인용을 채워 closed 도달.

    회귀 방지: FakeLLM 이 expert 에게만 인용을 생성하던 시절에는 converge 첫
    모더레이터 턴이 거부→repair 실패→skip 으로 stalled 됐다.
    """
    engine = MeetingEngine(MeetingStore(root=tmp_path / "meetings"), registry)
    meta = engine.create("brainstorm", "컨셉 브레인스토밍", PARTICIPANTS)
    orch = AutoOrchestrator(engine, FakeLLM(), registry)
    result = orch.run(meta)

    # diverge 2×5 + build_on 1×5 + converge 1×(1+5) = 21
    assert result.status == "closed"
    assert result.turns_submitted == 21
    assert result.repairs == 0 and result.skips == []
    assert meta.status is MeetingStatus.closed

    _, turns = engine.store.load(meta.id)
    conv_mods = [
        t for t in turns if t.round_no == 2 and t.role is SpeakerRole.moderator
    ]
    assert conv_mods  # converge 는 moderator_pick — 모더레이터가 먼저 발언
    assert all(
        t.citations and t.citations[0].ref != HALLUCINATED_REF for t in conv_mods
    )


# ── 보고서 조각(fragments) 브리핑 배관 (PLAN §4 P1 — 경로 B) ──────────

FRAGMENTS = [
    {
        "frag_id": "RA-test-001", "type": "claim",
        "text": "플랫폼은 보고서 작성·게시·종합보고를 한 곳에서 처리한다.",
        "source": {"page": "1", "block_id": "b1"}, "confidence": 0.9,
    },
    {
        "frag_id": "RA-test-002", "type": "evidence",
        "text": "도입 후 보고 취합 시간이 4시간에서 30분으로 줄었다.",
        "source": {"page": "2", "block_id": "b2"}, "confidence": 0.8,
    },
    {
        "frag_id": "RA-test-003", "type": "metric",
        "text": "주간 활성 사용자 120명, 게시 보고서 340건.",
        "source": {"page": "3", "block_id": "b3"}, "confidence": 0.7,
    },
]
FRAG_IDS = {f["frag_id"] for f in FRAGMENTS}


@pytest.fixture
def frag_run(tmp_path, monkeypatch):
    """임시 data 루트에 run 디렉터리와 조각 3개짜리 fragments.json 을 만들어 run_id 를 반환한다."""
    monkeypatch.setenv("WDA_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    run_dir = tmp_path / "data" / "pipeline" / "run-test"
    run_dir.mkdir(parents=True)
    (run_dir / "fragments.json").write_text(
        json.dumps(FRAGMENTS, ensure_ascii=False), encoding="utf-8"
    )
    yield "run-test"
    get_settings.cache_clear()  # monkeypatch 해제 후 캐시된 임시 설정 제거


def test_scenario_build_with_fragments_cites_frag_ids(tmp_path, registry, frag_run):
    """run_id 조각 배관 완주 — R2(citation_required)에서 페르소나가 실존 frag_id 를 인용한다."""
    engine, meta, orch = _setup(tmp_path, registry, FakeLLM())
    result = orch.run(meta, run_id=frag_run)

    assert result.status == "closed"
    assert result.turns_submitted == EXPECTED_TURNS
    assert result.repairs == 0 and result.skips == []

    _, turns = engine.store.load(meta.id)
    r2 = [t for t in turns if t.round_no == 1 and t.role is SpeakerRole.expert]
    assert len(r2) == len(PARTICIPANTS)
    # 조각이 [F#] 근거 선두로 브리핑되어 전원이 frag_id 를 실제 인용
    assert all(t.citations and t.citations[0].ref in FRAG_IDS for t in r2)


def test_nonexistent_frag_citation_rejected_then_repaired(tmp_path, registry, frag_run):
    """존재하지 않는 frag 인용은 엔진이 거부한다 — repair 1회로 실존 frag_id 인용으로 회복."""
    fake = FakeLLM(bad_ref_calls={2})  # R2 첫 발언자(ST)가 HALLU-999 인용
    engine, meta, orch = _setup(tmp_path, registry, fake)
    result = orch.run(meta, run_id=frag_run)

    assert result.status == "closed"
    assert result.repairs == 1 and result.skips == []  # 거부 1회 발생 → 수리

    _, turns = engine.store.load(meta.id)
    st_r2 = next(
        t for t in turns
        if t.round_no == 1 and t.expert_id == "narr-story-architect"
    )
    assert st_r2.citations[0].ref != HALLUCINATED_REF
    assert st_r2.citations[0].ref in FRAG_IDS


def test_run_with_missing_fragments_file_raises(tmp_path, registry):
    """fragments_path 가 실존하지 않으면 즉시 FileNotFoundError — 조용한 무근거 진행 방지."""
    _, meta, orch = _setup(tmp_path, registry, FakeLLM())
    with pytest.raises(FileNotFoundError):
        orch.run(meta, fragments_path=tmp_path / "nope" / "fragments.json")


def test_repair_failure_records_skip_and_stalls(tmp_path, registry):
    """repair 도 실패하면 skip 기록 후 중단 (같은 발언자 재지목 무한루프 방지)."""
    fake = FakeLLM(bad_ref_calls={2}, stubborn=True)  # 수정요청에도 환각 인용 고집
    engine, meta, orch = _setup(tmp_path, registry, fake)
    result = orch.run(meta)

    assert result.status == "stalled"
    assert result.turns_submitted == 1  # R1 모더레이터만 수리됨
    assert len(result.skips) == 1
    skip = result.skips[0]
    assert skip["speaker"] == "narr-story-architect" and skip["round_name"] == "cross_rebuttal"
    assert "인용" in skip["reason"]
    assert meta.status is not MeetingStatus.closed

    # skip 은 system 턴으로도 감사 기록되고, usage.json 에 남는다
    _, turns = engine.store.load(meta.id)
    sys_turns = [t for t in turns if t.role is SpeakerRole.system]
    assert len(sys_turns) == 1 and sys_turns[0].content_md.startswith("[skip]")
    usage = json.loads(
        (engine.store.find_dir(meta.id) / "usage.json").read_text(encoding="utf-8")
    )
    assert usage["status"] == "stalled" and len(usage["skips"]) == 1
