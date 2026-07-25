# wdmcp 파이프라인·QA 툴 테스트 — wdpipeline/wdqa 병렬 개발 대응 (부재 시 오류 봉투, 존재 시 계약 흐름)
from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from wdcore.config import get_settings
from wdmcp import server
from wdmcp.session import new_session

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
ST = "narr-story-architect"


def _importable(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError):
        return False


HAS_INGEST = _importable("wdpipeline.ingest")
HAS_FRAGMENTIZE = _importable("wdpipeline.fragmentize")
HAS_SCENARIO = _importable("wdpipeline.scenario")
HAS_QA = _importable("wdqa.gates")


@pytest.fixture()
def mcp_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("WDA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WDA_PERSONAS_ROOT", str(REPO_ROOT / "personas"))
    get_settings.cache_clear()
    server.reset_services()
    new_session()
    yield tmp_path
    get_settings.cache_clear()
    server.reset_services()


def run_mcp(scenario):
    async def _run():
        async with create_connected_server_and_client_session(server.mcp) as client:
            return await scenario(client)

    return asyncio.run(_run())


async def call(client, name: str, args: dict | None = None) -> dict:
    res = await client.call_tool(name, args or {})
    if res.structuredContent is not None:
        sc = res.structuredContent
        if isinstance(sc, dict) and set(sc) == {"result"}:
            sc = sc["result"]
        return sc
    return json.loads(res.content[0].text)


# ── wdpipeline/wdqa 부재 시 — 예외 전파 대신 오류 봉투 (AGENT_BRIEF 계약) ──


@pytest.mark.skipif(HAS_INGEST, reason="wdpipeline.ingest 존재 — 오류 봉투 경로는 부재 시에만")
def test_report_ingest_unavailable_envelope(mcp_env):
    async def scenario(client):
        return await call(client, "report_ingest", {"file": str(REPORT_SAMPLE)})

    res = run_mcp(scenario)
    assert res["ok"] is False
    assert res["error"]["code"] == "PIPELINE_UNAVAILABLE"
    assert "wdpipeline.ingest" in res["error"]["message"]
    assert res["error"]["hint"]


@pytest.mark.skipif(
    HAS_FRAGMENTIZE, reason="wdpipeline.fragmentize 존재 — 오류 봉투 경로는 부재 시에만"
)
def test_report_fragmentize_unavailable_envelope(mcp_env):
    async def scenario(client):
        return await call(client, "report_fragmentize", {"run_id": "run-x"})

    res = run_mcp(scenario)
    assert res["ok"] is False
    assert res["error"]["code"] == "PIPELINE_UNAVAILABLE"


@pytest.mark.skipif(HAS_SCENARIO, reason="wdpipeline.scenario 존재 — 오류 봉투 경로는 부재 시에만")
def test_scenario_build_unavailable_envelope(mcp_env):
    async def scenario(client):
        return await call(client, "scenario_build", {"meeting_id": "m-x"})

    res = run_mcp(scenario)
    assert res["ok"] is False
    assert res["error"]["code"] == "PIPELINE_UNAVAILABLE"


@pytest.mark.skipif(HAS_QA, reason="wdqa.gates 존재 — 오류 봉투 경로는 부재 시에만")
def test_qa_run_unavailable_envelope(mcp_env, tmp_path):
    async def scenario(client):
        return await call(client, "qa_run", {"build_path": str(tmp_path)})

    res = run_mcp(scenario)
    assert res["ok"] is False
    assert res["error"]["code"] == "QA_UNAVAILABLE"


# ── wdpipeline 존재 시 — 브리프 시그니처 계약 흐름 (병렬 개발 완료 후 활성화) ──


@pytest.mark.skipif(
    not (HAS_INGEST and HAS_FRAGMENTIZE), reason="wdpipeline.ingest/fragmentize 미구현 — 병렬 개발 중"
)
def test_ingest_then_fragmentize_flow(mcp_env):
    assert REPORT_SAMPLE.is_file(), "examples/reportarchive/report_sample.json 픽스처 필요"

    async def scenario(client):
        ingested = await call(client, "report_ingest", {"file": str(REPORT_SAMPLE)})
        assert ingested["ok"] is True, ingested
        run_id = ingested["data"]["run_id"]
        assert Path(ingested["data"]["norm_path"]).is_file()
        assert "report_fragmentize" in ingested["claude_instructions"]

        frag = await call(client, "report_fragmentize", {"run_id": run_id})
        assert frag["ok"] is True, frag
        assert frag["data"]["fragments_total"] >= 1
        assert Path(frag["data"]["fragments_path"]).is_file()
        assert "meeting_start" in frag["claude_instructions"]

        # frag_id들이 회의 인용 화이트리스트로 연결되는지 (meeting_start run_id 배선)
        started = await call(
            client,
            "meeting_start",
            {
                "topic": "샘플 보고서 심의",
                "type": "brainstorm",
                "participants": [ST],
                "run_id": run_id,
            },
        )
        assert started["ok"] is True
        assert started["data"]["fragments_loaded"] == frag["data"]["fragments_total"]
        return run_id, started["data"]["meeting_id"]

    run_mcp(scenario)


@pytest.mark.skipif(
    not (HAS_INGEST and HAS_FRAGMENTIZE and HAS_SCENARIO),
    reason="wdpipeline ingest/fragmentize/scenario 미구현 — 병렬 개발 중",
)
def test_scenario_build_contract_flow(mcp_env):
    async def scenario(client):
        ingested = await call(client, "report_ingest", {"file": str(REPORT_SAMPLE)})
        assert ingested["ok"] is True, ingested
        run_id = ingested["data"]["run_id"]
        frag = await call(client, "report_fragmentize", {"run_id": run_id})
        assert frag["ok"] is True, frag
        started = await call(
            client,
            "meeting_start",
            {"topic": "시나리오 심의", "type": "brainstorm", "participants": [ST], "run_id": run_id},
        )
        mid = started["data"]["meeting_id"]

        built = await call(client, "scenario_build", {"meeting_id": mid})
        assert built["ok"] is True, built
        d = built["data"]
        assert d["run_id"] == run_id and d["meeting_id"] == mid
        assert d["scene_count"] >= 1
        assert isinstance(d["validation_errors"], list)
        sp = Path(d["scenario_path"])
        assert sp.is_file()
        saved = json.loads(sp.read_text(encoding="utf-8"))
        assert saved["meta"]["meeting_id"] == mid, "회의 추적 meta.meeting_id가 기록되어야 한다"
        return True

    assert run_mcp(scenario) is True


@pytest.mark.skipif(not HAS_SCENARIO, reason="wdpipeline.scenario 미구현 — 병렬 개발 중")
def test_scenario_build_requires_run(mcp_env):
    async def scenario(client):
        started = await call(
            client,
            "meeting_start",
            {"topic": "run 없는 회의", "type": "brainstorm", "participants": [ST]},
        )
        mid = started["data"]["meeting_id"]
        return await call(client, "scenario_build", {"meeting_id": mid})

    res = run_mcp(scenario)
    assert res["ok"] is False
    assert res["error"]["code"] == "RUN_REQUIRED"


@pytest.mark.skipif(not HAS_QA, reason="wdqa.gates 미구현 — 병렬 개발 중")
def test_qa_run_returns_report_envelope(mcp_env, tmp_path):
    """wdqa 존재 시 — run_gates 계약({passed, results}) 봉투 반영을 확인한다."""
    build = tmp_path / "qa_build"
    build.mkdir()

    async def scenario(client):
        return await call(client, "qa_run", {"build_path": str(build)})

    res = run_mcp(scenario)
    assert set(res) == {"ok", "data", "session", "claude_instructions", "error"}
    if res["ok"]:
        assert isinstance(res["data"]["passed"], bool)
        assert isinstance(res["data"]["results"], list)
    else:
        assert res["error"]["code"] == "QA_FAILED"
