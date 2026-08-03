# wdmcp 렌더 툴 통합 테스트 — render_submit 백그라운드 잡의 상태 전이와 실렌더(2씬 합성 엔트리) 검증
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session
from pptx import Presentation

from wdcore.config import get_settings
from wdmcp import server
from wdmcp.session import new_session

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "web" / "runtime"
VENDOR_DIR = REPO_ROOT / "web" / "vendor"

# test_wdrender_smoke.py의 합성 2씬×2초 엔트리 재사용 — 오프라인(__resources) 경로
_SMOKE_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
<style>html, body { margin: 0; padding: 0; height: 100%; background: #111; }</style>
<script>window.OM_SCENES = '[{"name":"A","dur":2},{"name":"B","dur":2}]';</script>
<script>window.OM_PLAYBACK = '{"mode":"times","count":1}';</script>
</helmet>
<x-import component-from-global-scope="SmokeVideo" from="./animations-v2.jsx ./scenes.jsx" style="position:fixed;inset:0" hint-size="100%,100%"></x-import>
</x-dc>
</body>
</html>
"""

_SMOKE_SCENES = """/* 스모크 테스트용 2씬 — 씬은 localTime의 순수 함수 (엔진 계약 준수) */
const { SceneStage } = window;

function SceneA({ localTime: t }) {
  return (
    <div style={{ position: 'absolute', inset: 0, background: '#123456', color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 160, fontFamily: 'sans-serif' }}>
      A {Math.floor(t * 10)}
    </div>
  );
}

function SceneB({ localTime: t }) {
  return (
    <div style={{ position: 'absolute', inset: 0, background: '#654321', color: '#fff',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: 160, fontFamily: 'sans-serif' }}>
      B {Math.floor(t * 10)}
    </div>
  );
}

function SmokeVideo() {
  return (
    <div style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <SceneStage width={1920} height={1080} bg="#000" scenes={window.OM_SCENES}
                  playback={window.OM_PLAYBACK}>
        {{ 'A': SceneA, 'B': SceneB }}
      </SceneStage>
    </div>
  );
}
window.SmokeVideo = SmokeVideo;
"""


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


@pytest.fixture()
def build_dir(tmp_path_factory) -> Path:
    """support.js + 엔진 + 합성 씬 + 로컬 vendor로 구성된 기성 렌더 패키지."""
    d = tmp_path_factory.mktemp("wdmcp_build")
    shutil.copy2(RUNTIME_DIR / "support.js", d / "support.js")
    shutil.copy2(RUNTIME_DIR / "animations-v2.jsx", d / "animations-v2.jsx")
    (d / "vendor").mkdir()
    for f in ("react.production.min.js", "react-dom.production.min.js", "babel.min.js"):
        shutil.copy2(VENDOR_DIR / f, d / "vendor" / f)
    (d / "smoke.dc.html").write_text(_SMOKE_HTML, encoding="utf-8")
    (d / "scenes.jsx").write_text(_SMOKE_SCENES, encoding="utf-8")
    return d


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


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


# ── 접수 단계 오류 경로 (실렌더 없이 즉시 검증) ────────────────────────


def test_render_submit_input_validation(mcp_env):
    async def scenario(client):
        both_missing = await call(client, "render_submit", {})
        bad_target = await call(
            client, "render_submit", {"build_dir": "/tmp", "targets": ["gif"]}
        )
        no_dir = await call(
            client, "render_submit", {"build_dir": str(mcp_env / "no-such-dir")}
        )
        unknown_job = await call(client, "render_status", {"job_id": "rj-none"})
        return both_missing, bad_target, no_dir, unknown_job

    both_missing, bad_target, no_dir, unknown_job = run_mcp(scenario)
    assert both_missing["error"]["code"] == "INVALID_INPUT"
    assert bad_target["error"]["code"] == "INVALID_TARGETS"
    assert no_dir["error"]["code"] == "BUILD_DIR_NOT_FOUND"
    assert unknown_job["error"]["code"] == "NOT_FOUND"


def test_render_submit_entry_not_found(mcp_env, tmp_path):
    empty = tmp_path / "empty_build"
    empty.mkdir()

    async def scenario(client):
        return await call(client, "render_submit", {"build_dir": str(empty)})

    res = run_mcp(scenario)
    assert res["ok"] is False
    assert res["error"]["code"] == "ENTRY_NOT_FOUND"


# ── 실렌더 상태 전이 (queued→rendering→done) ─────────────────────────


def test_render_submit_to_done_with_real_export(mcp_env, build_dir):
    async def scenario(client):
        submitted = await call(
            client,
            "render_submit",
            {"build_dir": str(build_dir), "targets": ["video", "pptx"], "fps": 8},
        )
        assert submitted["ok"] is True, submitted
        data = submitted["data"]
        assert data["status"] == "queued"
        assert "render_status" in submitted["claude_instructions"]
        job_id = data["job_id"]
        job_path = Path(data["job_path"])
        assert job_path.is_file(), "잡 파일이 data/render_jobs/에 기록되어야 한다"
        assert job_path.parent.name == "render_jobs"

        seen = set()
        final = None
        for _ in range(360):  # 최대 180초
            st = await call(client, "render_status", {"job_id": job_id})
            assert st["ok"] is True, st
            seen.add(st["data"]["status"])
            if st["data"]["status"] in ("done", "failed"):
                final = st
                break
            await asyncio.sleep(0.5)
        assert final is not None, f"타임아웃 — 관측 상태: {seen}"
        assert final["data"]["status"] == "done", final["data"].get("error")
        assert "rendering" in seen or "queued" in seen, f"중간 상태 관측 실패: {seen}"
        # 렌더 완료 지시문은 열람 URL 제시를 요구한다 (fe0095a — 챗에서 바로 재생)
        instr = final["claude_instructions"]
        assert "urls" in instr and "링크" in instr, instr
        return final["data"]

    job = run_mcp(scenario)
    # 산출물 실검증 — mp4 길이 = Σdur(4s), PPTX 슬라이드 = 씬 수(2)
    video = Path(job["outputs"]["video"])
    pptx = Path(job["outputs"]["pptx"])
    assert video.is_file() and video.stat().st_size > 0
    assert _ffprobe_duration(video) == pytest.approx(4.0, abs=0.1)
    prs = Presentation(str(pptx))
    assert len(prs.slides) == 2
    assert job["detail"]["video"]["frames"] == 32  # 4s × 8fps
    # 잡 파일(원장)에도 동일 결과가 영속화되었는지 확인
    persisted = json.loads(
        (get_settings().data_dir / "render_jobs" / f"{job['job_id']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert persisted["status"] == "done"
    assert persisted["outputs"] == job["outputs"]


def test_render_job_failure_is_recorded(mcp_env, tmp_path):
    """엔트리가 dc 계약을 안 지키면 잡이 failed로 전이하고 error가 기록된다."""
    broken = tmp_path / "broken_build"
    broken.mkdir()
    (broken / "index.html").write_text("<html><body>not a dc entry</body></html>", encoding="utf-8")

    async def scenario(client):
        submitted = await call(
            client, "render_submit", {"build_dir": str(broken), "targets": ["video"], "fps": 8}
        )
        assert submitted["ok"] is True
        job_id = submitted["data"]["job_id"]
        for _ in range(240):  # 최대 120초 (Playwright 셀렉터 타임아웃 60s 포함)
            st = await call(client, "render_status", {"job_id": job_id})
            if st["data"]["status"] in ("done", "failed"):
                return st
            await asyncio.sleep(0.5)
        raise AssertionError("타임아웃")

    final = run_mcp(scenario)
    assert final["data"]["status"] == "failed"
    assert final["data"]["error"]
    assert "성공했다고 말하지 마라" in final["claude_instructions"]
