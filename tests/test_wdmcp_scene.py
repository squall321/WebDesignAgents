# wdmcp 씬 툴 4종 인프로세스 왕복 — scene_list/scene_html/scene_still/scenario_patch 봉투 계약
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from wdcore.config import get_settings
from wdmcp import server
from wdmcp.session import new_session

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
RUN_ID = "run-scenetool-0001"


@pytest.fixture(scope="module")
def mcp_env(tmp_path_factory: pytest.TempPathFactory):
    """모듈 공유 데이터 루트 + 파이프라인 run(scenario.json) 1건 준비."""
    import os

    data = tmp_path_factory.mktemp("mcp-scene-data")
    old = os.environ.get("WDA_DATA_DIR")
    os.environ["WDA_DATA_DIR"] = str(data)
    get_settings.cache_clear()
    server.reset_services()
    new_session()

    from wdpipeline.fragmentize import fragmentize
    from wdpipeline.ingest import ingest_report_file
    from wdpipeline.scenario import assemble_demo_scenario

    norm = ingest_report_file(REPORT_SAMPLE)
    doc = assemble_demo_scenario(norm, fragmentize(norm))
    run_dir = data / "pipeline" / RUN_ID
    run_dir.mkdir(parents=True)
    (run_dir / "scenario.json").write_text(doc.model_dump_json(indent=2), encoding="utf-8")

    yield data
    if old is None:
        os.environ.pop("WDA_DATA_DIR", None)
    else:
        os.environ["WDA_DATA_DIR"] = old
    get_settings.cache_clear()
    server.reset_services()


def run_mcp(scenario):
    async def _run():
        async with create_connected_server_and_client_session(server.mcp) as client:
            return await scenario(client)

    return asyncio.run(_run())


async def call(client, name: str, args: dict | None = None) -> dict:
    res = await client.call_tool(name, args or {})
    sc = res.structuredContent
    if isinstance(sc, dict) and set(sc) == {"result"}:
        sc = sc["result"]
    if sc is not None:
        return sc
    return json.loads(res.content[0].text)


def test_scene_list_builds_on_demand(mcp_env: Path) -> None:
    """scenario.json 만 있는 run — scene_list 가 온디맨드 빌드 후 씬 목록을 준다."""

    async def scenario(client):
        return await call(client, "scene_list", {"run_id": RUN_ID})

    env = run_mcp(scenario)
    assert env["ok"] is True, env
    data = env["data"]
    assert data["count"] >= 5
    assert "절차" in [s["name"] for s in data["scenes"]]
    assert (mcp_env / "build" / RUN_ID / "index.html").is_file()  # 온디맨드 빌드 실체
    assert env["claude_instructions"]


def test_scenario_patch_roundtrip_and_rejection(mcp_env: Path) -> None:
    async def scenario(client):
        ok = await call(client, "scenario_patch", {"run_id": RUN_ID, "ops": [
            {"op": "set_dur", "scene": "절차", "dur": 14},
        ]})
        bad = await call(client, "scenario_patch", {"run_id": RUN_ID, "ops": [
            {"op": "set_tpl", "scene": "절차", "tpl": "megachart@1"},
        ]})
        ghost = await call(client, "scene_list", {"run_id": "run-없는것"})
        return ok, bad, ghost

    ok, bad, ghost = run_mcp(scenario)
    assert ok["ok"] is True, ok
    assert any("dur" in d and "14" in d for d in ok["data"]["applied"])
    assert ok["data"]["scene_count"] >= 5

    # scenario.json 이 실제로 갱신되고 재빌드까지 반영됐다
    scen = json.loads(
        (mcp_env / "pipeline" / RUN_ID / "scenario.json").read_text(encoding="utf-8")
    )
    assert next(s for s in scen["scenes"] if s["name"] == "절차")["dur"] == 14
    built = json.loads(
        (mcp_env / "build" / RUN_ID / "scene-data.json").read_text(encoding="utf-8")
    )
    assert next(s for s in built["scenes"] if s["name"] == "절차")["dur"] == 14

    assert bad["ok"] is False and bad["error"]["code"] == "PATCH_REJECTED"
    assert "megachart" in bad["error"]["message"]
    assert ghost["ok"] is False and ghost["error"]["code"] == "RUN_NOT_FOUND"


def test_scene_html_and_still_save_files(mcp_env: Path) -> None:
    async def scenario(client):
        selfh = await call(client, "scene_html", {"run_id": RUN_ID, "scene": "절차", "mode": "self"})
        still = await call(client, "scene_still", {"run_id": RUN_ID, "scene": "절차"})
        return selfh, still

    selfh, still = run_mcp(scenario)
    assert selfh["ok"] is True, selfh
    hp = Path(selfh["data"]["html_path"])
    assert hp.is_file() and hp.stat().st_size > 2_000_000  # 자립형 인라인 실체
    assert "file://" in selfh["claude_instructions"]

    assert still["ok"] is True, still
    pp = Path(still["data"]["png_path"])
    assert pp.is_file() and pp.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert still["data"]["size_bytes"] > 30_000
