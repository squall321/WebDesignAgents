# wdweb 렌더 API 테스트 — 2씬 합성 픽스처로 pptx-only 백그라운드 렌더를 실검증 (mp4 는 시간상 제외)
from __future__ import annotations

import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pptx import Presentation

from wdcore.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "web" / "runtime"
VENDOR_DIR = REPO_ROOT / "web" / "vendor"

# test_wdmcp_render.py 의 합성 2씬×2초 엔트리 재사용 — 오프라인(__resources) 경로
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
def web_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    data = tmp_path / "data"
    monkeypatch.setenv("WDA_DATA_DIR", str(data))
    monkeypatch.setenv("WDA_PERSONAS_ROOT", str(REPO_ROOT / "personas"))
    get_settings.cache_clear()
    yield data
    get_settings.cache_clear()


@pytest.fixture()
def smoke_run(web_env: Path) -> str:
    """빌드 완료 상태의 실행 원장 1건 — 합성 2씬 build 패키지를 가리킨다."""
    from wdweb import runs as runledger

    build = web_env / "build" / "smoke"
    build.mkdir(parents=True)
    shutil.copy2(RUNTIME_DIR / "support.js", build / "support.js")
    shutil.copy2(RUNTIME_DIR / "animations-v2.jsx", build / "animations-v2.jsx")
    (build / "vendor").mkdir()
    for f in ("react.production.min.js", "react-dom.production.min.js", "babel.min.js"):
        shutil.copy2(VENDOR_DIR / f, build / "vendor" / f)
    (build / "smoke.dc.html").write_text(_SMOKE_HTML, encoding="utf-8")
    (build / "scenes.jsx").write_text(_SMOKE_SCENES, encoding="utf-8")

    run_id = runledger.new_run_id()
    now = "2026-07-26T00:00:00+00:00"
    runledger.write_run({
        "run_id": run_id,
        "slug": "smoke",
        "status": "done",
        "stages": [
            {"stage": s, "status": "done", "error": None, "output": None}
            for s in runledger.STAGES
        ],
        "scenario_summary": {"scene_count": 2, "total_dur": 4.0, "core_message": "스모크"},
        "build_dir": str(build),
        "entry": "smoke.dc.html",
        "render": None,
        "qa": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    })
    return run_id


@pytest.fixture()
def client(web_env: Path) -> TestClient:
    from wdweb.app import app

    return TestClient(app)


def _poll_render(client: TestClient, run_id: str, timeout: float = 180.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()["data"]
        render = run.get("render") or {}
        if render.get("status") in ("done", "failed"):
            return run
        time.sleep(0.5)
    pytest.fail(f"렌더가 {timeout}초 안에 끝나지 않았다: {run_id}")


def test_render_pptx_only(client: TestClient, smoke_run: str, web_env: Path) -> None:
    res = client.post(f"/api/runs/{smoke_run}/render", json={"targets": ["pptx"]})
    assert res.status_code == 202
    body = res.json()
    assert body["success"] is True
    assert body["data"]["render"]["status"] in ("queued", "rendering")

    run = _poll_render(client, smoke_run)
    render = run["render"]
    assert render["status"] == "done", f"렌더 실패: {render.get('error')}"
    assert "pptx" in render["outputs"]

    # 산출물 상태 — pptx 존재·크기, mp4 는 대상 밖
    arts = client.get(f"/api/runs/{smoke_run}/artifacts").json()["data"]
    assert arts["pptx"]["exists"] is True
    assert arts["pptx"]["size"] > 0
    assert arts["mp4"]["exists"] is False

    # 다운로드 — PPTX 슬라이드 수 = 씬 수(2)
    res = client.get(f"/api/runs/{smoke_run}/download/pptx")
    assert res.status_code == 200
    tmp = web_env / "downloaded.pptx"
    tmp.write_bytes(res.content)
    assert len(Presentation(str(tmp)).slides) == 2


def test_render_requires_build(client: TestClient, web_env: Path) -> None:
    from wdweb import runs as runledger

    now = "2026-07-26T00:00:00+00:00"
    run_id = runledger.new_run_id()
    runledger.write_run({
        "run_id": run_id, "slug": "unbuilt", "status": "failed",
        "stages": [], "scenario_summary": None, "build_dir": None, "entry": None,
        "render": None, "qa": None, "error": "x", "created_at": now, "updated_at": now,
    })
    res = client.post(f"/api/runs/{run_id}/render", json={"targets": ["pptx"]})
    assert res.status_code == 409
    assert res.json()["success"] is False

    res = client.post(f"/api/runs/{run_id}/qa", json={})
    assert res.status_code == 409
