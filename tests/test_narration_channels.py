# 내레이션 창구 대칭 테스트 — CLI·MCP·웹·콘솔이 같은 narration 능력을 노출하고, 세 실행 경로가 실제로 먹싱까지 가는지
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from wdcore.config import get_settings
from wdcore.models.scenario import ScenarioDoc
from wdrender import tts_client
from wdrender.tts_fake import FakeVoiceRecorder

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg 없음")


@pytest.fixture()
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """임시 데이터 디렉터리 + 가짜 VoiceRecorder — 실행 경로가 만드는 클라이언트를 가짜로 돌린다."""
    data = tmp_path / "data"
    monkeypatch.setenv("WDA_DATA_DIR", str(data))
    monkeypatch.setenv("WDA_PERSONAS_ROOT", str(REPO_ROOT / "personas"))
    monkeypatch.setenv("WDA_ENV_FILE", str(tmp_path / "no.env"))
    get_settings.cache_clear()
    fake = FakeVoiceRecorder()
    real = tts_client._client
    monkeypatch.setattr(
        tts_client, "_client", lambda base_url=None, **kw: real(base_url, transport=fake.transport())
    )
    yield data, fake
    get_settings.cache_clear()


def _streams(path: Path) -> list[str]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return sorted(out.split())


def _demo_run(data: Path, run_id: str) -> tuple[Path, Path]:
    """예시 보고서 → 시나리오 → 빌드. (빌드 디렉터리, scenario.json) 을 돌려준다."""
    from wdpipeline.build import build_render_package
    from wdpipeline.fragmentize import fragmentize
    from wdpipeline.ingest import ingest_report_file
    from wdpipeline.scenario import assemble_demo_scenario

    norm = ingest_report_file(SAMPLE)
    doc = assemble_demo_scenario(norm, fragmentize(norm))
    scen = data / "pipeline" / run_id / "scenario.json"
    scen.parent.mkdir(parents=True)
    scen.write_text(json.dumps(doc.model_dump(), ensure_ascii=False), encoding="utf-8")
    build = data / "build" / run_id
    build_render_package(doc, build)
    return build, scen


def _measured(scen: Path) -> list[str]:
    doc = ScenarioDoc.model_validate_json(scen.read_text(encoding="utf-8"))
    return [s.name for s in doc.scenes if s.narration_sec]


# ── 대칭 계약 ────────────────────────────────────────────────────────────


def test_every_interface_can_ask_for_narration():
    """네 창구가 같은 능력을 노출해야 한다 (test_interface_parity.py 와 같은 계약)."""
    import inspect

    from wdmcp import jobs, server
    from wdmcp.schemas import RenderJob
    from wdpipeline import cli
    from wdweb import runs as webruns

    # 예전 잡 파일(narration 없음)도 읽혀야 한다
    assert RenderJob(job_id="x", status="queued", targets=[], created_at="", updated_at="").narration is False
    for fn in (server.render_submit, jobs.submit_render_job, webruns.submit_render):
        assert inspect.signature(fn).parameters["narration"].default is False, fn.__name__
    assert inspect.signature(cli.render).parameters["narration"].default.default is False
    assert inspect.signature(cli.run).parameters["narration"].default.default is False
    html = (REPO_ROOT / "frontend" / "dist" / "index.html").read_text(encoding="utf-8")
    js = (REPO_ROOT / "frontend" / "dist" / "app.js").read_text(encoding="utf-8")
    assert 'id="narration"' in html and 'id="narration-result"' in html
    assert "body.narration = true" in js


def test_mcp_and_web_refuse_narration_without_video(env):
    from fastapi.testclient import TestClient
    from mcp.shared.memory import create_connected_server_and_client_session

    from wdmcp import server
    from wdmcp.session import new_session
    from wdweb import runs as runledger
    from wdweb.app import app

    data, _ = env
    build, _ = _demo_run(data, "r-check")

    server.reset_services()
    new_session()

    async def submit():
        async with create_connected_server_and_client_session(server.mcp) as client:
            res = await client.call_tool("render_submit", {
                "build_dir": str(build), "targets": ["pptx"], "narration": True,
            })
            return res.structuredContent or json.loads(res.content[0].text)

    res = asyncio.run(submit())
    res = res.get("result", res)
    assert res["ok"] is False and res["error"]["code"] == "INVALID_INPUT"

    run_id = runledger.new_run_id()
    now = "2026-10-24T00:00:00+00:00"
    runledger.write_run({
        "run_id": run_id, "slug": run_id, "status": "done",
        "stages": [{"stage": s, "status": "done", "error": None, "output": None} for s in runledger.STAGES],
        "scenario_summary": {}, "build_dir": str(build), "entry": "index.html",
        "render": None, "qa": None, "error": None, "created_at": now, "updated_at": now,
    })
    client = TestClient(app)
    r = client.post(f"/api/runs/{run_id}/render", json={"targets": ["pptx"], "narration": True})
    assert r.status_code == 400 and "영상" in r.json()["message"]
    r = client.post(f"/api/runs/{run_id}/render", json={"targets": ["video"], "narration": "yes"})
    assert r.status_code == 400
    server.reset_services()


# ── 세 실행 경로 실렌더 (fps=1) ──────────────────────────────────────────────


@needs_ffmpeg
def test_cli_run_with_narration_goes_all_the_way(env):
    """wda run --narration — 전 단계 + 먹싱. pptx_mode 를 안 넘겨 PPTX 에서 죽던 것도 함께 막는다."""
    from typer.testing import CliRunner

    from wdpipeline import cli

    data, fake = env
    result = CliRunner().invoke(cli.app, [
        "run", "--file", str(SAMPLE), "--slug", "demo", "--fps", "1", "--narration",
    ])
    assert result.exit_code == 0, result.output
    renders = data / "renders" / "demo"
    assert _streams(renders / "demo.mp4") == ["audio", "subtitle", "video"]
    assert (renders / "demo.pptx").is_file()
    for name in ("narration.mp3", "narration.srt", "drift_report.json"):
        assert (renders / name).is_file(), name
    assert "[narration] 먹싱" in result.output
    assert _measured(data / "pipeline" / "demo" / "scenario.json")
    assert fake.projects == {}


@needs_ffmpeg
def test_mcp_job_with_narration(env):
    from mcp.shared.memory import create_connected_server_and_client_session

    from wdmcp import server
    from wdmcp.session import new_session

    data, _ = env
    _, scen = _demo_run(data, "m-demo")
    server.reset_services()
    new_session()

    async def scenario():
        async with create_connected_server_and_client_session(server.mcp) as client:
            async def call(name, args):
                res = await client.call_tool(name, args)
                sc = res.structuredContent or json.loads(res.content[0].text)
                return sc.get("result", sc)

            sub = await call("render_submit", {
                "scenario_path": str(scen), "targets": ["video"], "fps": 1, "narration": True,
            })
            assert sub["ok"] is True, sub
            for _ in range(600):
                st = await call("render_status", {"job_id": sub["data"]["job_id"]})
                if st["data"]["status"] in ("done", "failed"):
                    return st["data"]
                await asyncio.sleep(0.5)
            pytest.fail("MCP 렌더 잡이 끝나지 않았다")

    job = asyncio.run(scenario())
    server.reset_services()
    assert job["status"] == "done", job.get("error")
    assert _streams(Path(job["outputs"]["video"])) == ["audio", "subtitle", "video"]
    summary = job["detail"]["narration"]["summary"]
    assert summary["narrated"] > 0 and summary["new_total_sec"] > 0
    assert _measured(scen)   # scenario_path 에도 재조정이 반영된다


@needs_ffmpeg
def test_web_run_with_narration(env):
    from fastapi.testclient import TestClient

    from wdweb import runs as runledger
    from wdweb.app import app

    data, _ = env
    run_id = runledger.new_run_id()
    build, scen = _demo_run(data, run_id)
    now = "2026-10-24T00:00:00+00:00"
    runledger.write_run({
        "run_id": run_id, "slug": run_id, "status": "done",
        "stages": [{"stage": s, "status": "done", "error": None, "output": None} for s in runledger.STAGES],
        "scenario_summary": {}, "build_dir": str(build), "entry": "index.html",
        "render": None, "qa": None, "error": None, "created_at": now, "updated_at": now,
    })
    client = TestClient(app)
    r = client.post(f"/api/runs/{run_id}/render", json={"targets": ["video"], "fps": 1, "narration": True})
    assert r.status_code == 202, r.text
    deadline = time.monotonic() + 300
    while time.monotonic() < deadline:
        render = client.get(f"/api/runs/{run_id}").json()["data"].get("render") or {}
        if render.get("status") in ("done", "failed"):
            break
        time.sleep(0.5)
    assert render.get("status") == "done", render.get("error")
    assert render["narration"] is True
    assert render["detail"]["narration"]["summary"]["narrated"] > 0
    assert _streams(Path(render["outputs"]["video"])) == ["audio", "subtitle", "video"]
    assert _measured(scen)
