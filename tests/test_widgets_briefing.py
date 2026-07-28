# 위젯 구조가 심의 브리핑([F#] fact)까지 도달하는지 실증 — 실물 report_sample.json 조각으로 MCP·오케스트레이터 양 경로 검증
"""구조 보존의 종착점은 씬 템플릿 선택이다.

`wdpipeline.widgets` 가 표/흐름도/진행률의 구조를 조각에 실어도, 심의 브리핑이
평문만 보여주면 페르소나는 "이 보고서엔 6노드 흐름도와 7계열 진행률이 있다"를
알 수 없고 dataviz/timeline 템플릿을 고를 근거가 없다. 이 파일은 그 마지막 배관
(fragments.structured → BriefingFact.structured / [F#] 라벨)을 실물 데이터로 건다.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from wdcore.config import get_settings
from wdcore.meetings import MeetingEngine, MeetingStore
from wdcore.registry.registry import load_registry
from wdllm.fake import FakeLLM
from wdllm.orchestrator import AutoOrchestrator
from wdmcp import server
from wdmcp.session import new_session, split_fact_structure
from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"

ST = "narr-story-architect"
TY = "vis-typographer"


@pytest.fixture(scope="module")
def real_fragments() -> list[dict]:
    """실물 보고서 → 정규화 → 조각. 구조 payload 를 실은 조각이 반드시 있어야 한다."""
    frags = fragmentize(ingest_report_file(SAMPLE))
    assert any("structured" in f for f in frags), "실물에 구조 조각이 없다 — 픽스처 전제 붕괴"
    return frags


# ── 1. split_fact_structure 단위 ─────────────────────────────────────


def test_structured_fragment_splits_summary_from_body(real_fragments):
    """구조 조각은 (요약, 본문)으로 갈리고 본문에 요약이 남지 않는다 (중복 토큰 0)."""
    checked = 0
    for f in real_fragments:
        if "structured" not in f:
            continue
        summary, body = split_fact_structure(f)
        assert summary, f"{f['frag_id']} 구조 조각인데 요약이 비었다"
        assert not body.startswith(summary), f"{f['frag_id']} 본문에 요약이 중복됐다"
        # 원문 = 요약 + 구분자 + 본문 — 정보가 사라지지 않았다
        assert f["text"].startswith(summary)
        if body:
            assert body in f["text"]
        checked += 1
    assert checked >= 10, f"구조 조각 표본 부족: {checked}"


def test_text_fragment_has_no_structure(real_fragments):
    """텍스트군 조각은 요약이 빈 문자열이고 본문은 원문 그대로다."""
    plain = [f for f in real_fragments if "structured" not in f]
    assert plain, "텍스트 조각이 하나도 없다 — 픽스처 전제 붕괴"
    for f in plain:
        summary, body = split_fact_structure(f)
        assert summary == ""
        assert body == f["text"]


@pytest.mark.parametrize(
    "frag",
    [
        {"text": "본문만 있는 조각"},
        {"text": "payload 가 dict 아님", "structured": ["rows"]},
        {"text": "payload 가 None", "structured": None},
        {"text": "미지 kind 는 요약 불가", "structured": {"kind": "no-such-kind"}},
    ],
)
def test_malformed_fragment_falls_back_to_plain_text(frag):
    """구조가 깨졌거나 없으면 브리핑은 조용히 텍스트 경로로 떨어진다 (예외 금지)."""
    summary, body = split_fact_structure(frag)
    assert summary == ""
    assert body == frag.get("text", "")


def test_summary_without_body_survives():
    """text 가 없어도(요약만 있는 조각) 요약은 살아서 브리핑에 간다."""
    summary, body = split_fact_structure({"structured": {"kind": "pairs", "pairs": []}})
    assert summary == "키값 0쌍"
    assert body == ""


def test_summary_is_a_summary_not_the_data(real_fragments):
    """요약은 한 줄·짧고 원 데이터를 담지 않는다 — 브리핑 토큰 예산 방어선."""
    for f in real_fragments:
        if "structured" not in f:
            continue
        summary, _ = split_fact_structure(f)
        assert "\n" not in summary
        assert len(summary) <= 120, f"{f['frag_id']} 요약 {len(summary)}자 — 한 줄 예산 초과"
        # rows/nodes 를 직렬화해 흘리면 여기서 잡힌다
        assert "{" not in summary and "[" not in summary


# ── 2. MCP 브리핑 경로 (meeting_get_briefing) ────────────────────────


@pytest.fixture()
def mcp_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, real_fragments):
    """실물 조각을 run-widget 으로 심은 임시 데이터 루트 + 새 세션."""
    monkeypatch.setenv("WDA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WDA_PERSONAS_ROOT", str(REPO_ROOT / "personas"))
    get_settings.cache_clear()
    server.reset_services()
    new_session()
    run_dir = tmp_path / "data" / "pipeline" / "run-widget"
    run_dir.mkdir(parents=True)
    (run_dir / "fragments.json").write_text(
        json.dumps(real_fragments, ensure_ascii=False), encoding="utf-8"
    )
    yield tmp_path
    get_settings.cache_clear()
    server.reset_services()


async def _call(client, name: str, args: dict) -> dict:
    res = await client.call_tool(name, args)
    if res.structuredContent is not None:
        sc = res.structuredContent
        if isinstance(sc, dict) and set(sc) == {"result"}:
            sc = sc["result"]
        return sc
    return json.loads(res.content[0].text)


def _collect_facts(rounds: int = 14) -> list[dict]:
    """브리핑을 반복 호출해(발언 제출 없이 미전달분 소진) 전달된 fact 를 모은다."""

    async def scenario(client):
        started = await _call(
            client,
            "meeting_start",
            {
                "topic": "보고서 구조를 어떤 씬 템플릿에 태울까",
                "type": "brainstorm",
                "participants": [ST, TY],
                "run_id": "run-widget",
            },
        )
        assert started["ok"] is True, started
        mid = started["data"]["meeting_id"]
        seen: list[dict] = []
        for _ in range(rounds):
            b = await _call(client, "meeting_get_briefing", {"meeting_id": mid})
            assert b["ok"] is True, b
            facts = b["data"]["facts"]
            if not facts:
                break
            seen += facts
        return seen

    async def _run():
        async with create_connected_server_and_client_session(server.mcp) as client:
            return await scenario(client)

    return asyncio.run(_run())


def test_briefing_fact_carries_structured_summary(mcp_env, real_fragments):
    """구조 조각이 브리핑에 실릴 때 structured 한 줄과 widget 타입이 함께 간다."""
    facts = _collect_facts()
    assert facts, "브리핑에 fact 가 하나도 전달되지 않았다"

    by_ref = {f["frag_id"]: f for f in real_fragments}
    structured_facts = [f for f in facts if f["structured"]]
    assert structured_facts, "구조 요약을 실은 fact 가 0건 — 배관이 끊겼다"

    for fact in facts:
        frag = by_ref[fact["ref"]]
        assert ("structured" in frag) == bool(fact["structured"]), (
            f"{fact['ref']} 구조 유무와 structured 필드가 어긋난다"
        )
        assert fact["widget"] == frag["widget"]
        # 요약은 text 에 중복되지 않는다
        if fact["structured"]:
            assert not fact["text"].startswith(fact["structured"])


def test_briefing_delivers_every_structured_fragment(mcp_env, real_fragments):
    """구조 조각 전건이 브리핑까지 도달한다 (top_k 선별에 밀려 유실되지 않음)."""
    facts = _collect_facts()
    delivered = {f["ref"] for f in facts if f["structured"]}
    expected = {f["frag_id"] for f in real_fragments if "structured" in f}
    assert delivered == expected, f"미도달 구조 조각: {sorted(expected - delivered)}"


def test_briefing_shows_widget_scale_for_template_choice(mcp_env):
    """페르소나가 씬 템플릿을 고를 수 있게 위젯 종류·규모가 문자열로 드러난다."""
    facts = _collect_facts()
    summaries = [f["structured"] for f in facts if f["structured"]]
    joined = " | ".join(summaries)
    for token in ("표 ", "흐름도 ", "트리 ", "진행률 ", "키값 "):
        assert token in joined, f"{token.strip()} 요약이 브리핑에 없다: {summaries}"
    assert any("흐름도 6노드" in s for s in summaries)
    assert any("진행률 7계열" in s for s in summaries)
    assert any("×33행" in s for s in summaries)


# ── 3. 오케스트레이터 [F#] 프롬프트 경로 ─────────────────────────────


class CapturingFake(FakeLLM):
    """FakeLLM 그대로 응답하되 프롬프트를 보관한다 (브리핑 문자열 실측용)."""

    def __init__(self) -> None:
        super().__init__()
        self.prompts: list[str] = []

    def chat(self, messages, **kwargs):
        self.prompts.append(
            "\n".join(m.get("content", "") for m in messages if m.get("role") == "user")
        )
        return super().chat(messages, **kwargs)


@pytest.fixture()
def frag_run(tmp_path, monkeypatch, real_fragments) -> str:
    monkeypatch.setenv("WDA_DATA_DIR", str(tmp_path / "data"))
    get_settings.cache_clear()
    run_dir = tmp_path / "data" / "pipeline" / "run-widget"
    run_dir.mkdir(parents=True)
    (run_dir / "fragments.json").write_text(
        json.dumps(real_fragments, ensure_ascii=False), encoding="utf-8"
    )
    yield "run-widget"
    get_settings.cache_clear()


def test_orchestrator_fact_line_labels_structure(tmp_path, frag_run):
    """[F#] 줄의 라벨 칸이 '조각:evidence' 대신 구조 요약이 된다."""
    registry = load_registry()
    engine = MeetingEngine(MeetingStore(root=tmp_path / "meetings"), registry)
    meta = engine.create("brainstorm", "구조 요약이 프롬프트에 실리는가", [ST, TY])
    llm = CapturingFake()
    AutoOrchestrator(engine, llm, registry).run(meta, run_id=frag_run, max_turns=1)

    assert llm.prompts, "LLM 호출이 없었다"
    lines = [ln for ln in llm.prompts[0].splitlines() if ln.startswith("[F")]
    assert lines, "브리핑에 [F#] 줄이 없다"

    structured = [ln for ln in lines if " | 흐름도 " in ln or " | 표 " in ln]
    assert structured, "구조 요약 라벨이 붙은 [F#] 줄이 없다:\n" + "\n".join(lines[:5])
    sample = next(ln for ln in structured if " | 흐름도 6노드" in ln)
    ref, label, body = sample.split(" | ", 2)
    assert ref.startswith("[F") and "ref=RA-" in ref
    assert label == "흐름도 6노드 선형"
    assert not body.startswith(label), "라벨이 본문에 중복됐다"

    # 구조 없는 조각은 종전 라벨을 유지한다 (회귀)
    assert any(" | 조각:" in ln for ln in lines)
