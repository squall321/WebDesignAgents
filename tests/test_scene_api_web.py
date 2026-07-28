# 씬 API 웹 E2E — 씬 목록·HTML 두 모드 실렌더(file:// 포함)·스틸 PNG·PATCH 수정→재빌드
from __future__ import annotations

import io
import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wdcore.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"


@pytest.fixture(scope="module")
def scene_env(tmp_path_factory: pytest.TempPathFactory):
    data = tmp_path_factory.mktemp("scene-data")
    old = os.environ.get("WDA_DATA_DIR")
    os.environ["WDA_DATA_DIR"] = str(data)
    get_settings.cache_clear()
    yield data
    if old is None:
        os.environ.pop("WDA_DATA_DIR", None)
    else:
        os.environ["WDA_DATA_DIR"] = old
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def client(scene_env: Path) -> TestClient:
    from wdweb.app import app

    return TestClient(app)


@pytest.fixture(scope="module")
def built_run(client: TestClient) -> dict:
    """report_sample 로 파이프라인을 끝까지 돌린 실행 1건 (scenario+build 완료)."""
    report = json.loads(REPORT_SAMPLE.read_text(encoding="utf-8"))
    res = client.post("/api/runs", json={"report_json": report, "slug": "scene-e2e"})
    assert res.status_code == 202
    run_id = res.json()["data"]["run_id"]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()["data"]
        if run["status"] in ("done", "failed"):
            break
        time.sleep(0.3)
    assert run["status"] == "done", f"파이프라인 실패: {run.get('error')}"
    return run


def _scenario(scene_env: Path, run_id: str) -> dict:
    return json.loads(
        (scene_env / "pipeline" / run_id / "scenario.json").read_text(encoding="utf-8")
    )


# ── ① 씬 목록 ───────────────────────────────────────────────────────────────


def test_scene_list(client: TestClient, built_run: dict) -> None:
    res = client.get(f"/api/runs/{built_run['run_id']}/scenes")
    assert res.status_code == 200
    data = res.json()["data"]
    names = [s["name"] for s in data["scenes"]]
    assert data["count"] == len(names) >= 5
    assert "절차" in names
    row = next(s for s in data["scenes"] if s["name"] == "절차")
    assert row["tpl"] == "process@1" and row["dur"] > 0
    assert row["data_brief"].startswith("{")  # 데이터 요약 존재
    # 미빌드/유령 run 은 409/404 봉투
    assert client.get("/api/runs/no-such/scenes").status_code == 404


# ── ② 씬 HTML 두 모드 — 실렌더 (light: http, self: file://) ────────────────


def test_scene_html_two_modes_render(
    client: TestClient, built_run: dict, tmp_path: Path
) -> None:
    run_id = built_run["run_id"]
    build_dir = Path(built_run["build_dir"])

    # light — 라우트 응답: base href 로 프리뷰 루트 보정 + 해당 씬 하나만 주입
    res = client.get(f"/api/runs/{run_id}/scenes/절차/html?mode=light")
    assert res.status_code == 200
    light = res.text
    assert '<base href="../../preview/">' in light
    assert '"name":"절차"' in light.replace("\\", "")
    assert light.count('data-presets="react"') >= 5  # 로드 순서 계약 스크립트들

    # self — Content-Disposition 다운로드 겸용 + 외부 참조 0
    res = client.get(f"/api/runs/{run_id}/scenes/절차/html?mode=self&still=2.0")
    assert res.status_code == 200
    assert "attachment" in res.headers.get("content-disposition", "")
    selfh = res.text
    # 모든 JS·폰트 인라인 — script src 태그·상대 URL 참조가 하나도 없어야 한다
    assert "<script src=" not in selfh
    assert "url('./" not in selfh and "<base " not in selfh
    assert "data:font/woff2;base64," in selfh
    assert len(selfh.encode()) > 2_000_000  # vendor+폰트 인라인 실체

    # 실렌더 — self 는 http 서빙 없이 file:// 로, light 는 빌드 루트 서빙으로
    from playwright.sync_api import sync_playwright

    from wdrender.server import StaticServer
    from wdweb.scenes import scene_entry_html

    self_path = tmp_path / "scene-self.html"  # 단독 복사 — 빌드 자원과 격리
    self_path.write_text(selfh, encoding="utf-8")
    light_name = "scene-절차.light.html"
    (build_dir / light_name).write_text(
        scene_entry_html(build_dir, "절차", mode="light"), encoding="utf-8"
    )
    svg_sel = "svg[data-om-exportable-video-with-duration-secs]"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1980, "height": 1140})
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(self_path.as_uri(), wait_until="load")
        page.wait_for_selector(svg_sel, state="attached", timeout=60_000)
        scenes = json.loads(page.evaluate("() => window.OM_SCENES"))
        assert [s["name"] for s in scenes] == ["절차"]  # 해당 씬만 존재
        assert not errors, errors

        with StaticServer(build_dir) as srv:
            page2 = browser.new_page(viewport={"width": 1980, "height": 1140})
            errors2: list[str] = []
            page2.on("pageerror", lambda e: errors2.append(str(e)))
            page2.goto(srv.url_for(light_name), wait_until="load")
            page2.wait_for_selector(svg_sel, state="attached", timeout=60_000)
            scenes2 = json.loads(page2.evaluate("() => window.OM_SCENES"))
            assert [s["name"] for s in scenes2] == ["절차"]
            assert not errors2, errors2
        browser.close()

    # 모드 오류·유령 씬
    assert client.get(f"/api/runs/{run_id}/scenes/절차/html?mode=weird").status_code == 400
    assert client.get(f"/api/runs/{run_id}/scenes/유령/html").status_code == 404


# ── ③ 씬 스틸 PNG ───────────────────────────────────────────────────────────


def test_scene_still_png(client: TestClient, built_run: dict) -> None:
    from PIL import Image

    run_id = built_run["run_id"]
    res = client.get(f"/api/runs/{run_id}/scenes/절차/still.png")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/png"
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"
    im = Image.open(io.BytesIO(res.content))
    assert im.size == (1920, 1080)  # 포맷 스펙 stage 원척 (wide-16x9)
    assert len(res.content) > 30_000  # 실프레임 (빈 캔버스가 아니다)

    # 기본 스틸은 일괄 캡처로 캐시 — 두 번째 씬은 즉답이어야 한다
    t0 = time.monotonic()
    res2 = client.get(f"/api/runs/{run_id}/scenes/오프닝/still.png")
    assert res2.status_code == 200
    assert time.monotonic() - t0 < 2.0

    assert client.get(f"/api/runs/{run_id}/scenes/유령/still.png").status_code == 404


# ── ④ PATCH — 수정→재빌드→scene-data 반영, 실패는 422 + 무손상 ──────────────


def test_patch_e2e_applies_and_rebuilds(
    client: TestClient, scene_env: Path, built_run: dict
) -> None:
    run_id = built_run["run_id"]
    build_dir = Path(built_run["build_dir"])
    res = client.patch(f"/api/runs/{run_id}/scenario", json={"ops": [
        {"op": "set_dur", "scene": "절차", "dur": 14},
        {"op": "set_data", "scene": "오프닝", "path": "title.accent", "value": "핀포인트"},
    ]})
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    assert data["rebuilt"] is True
    assert len(data["applied"]) == 2
    assert any("dur" in d and "14" in d for d in data["applied"])
    assert any("핀포인트" in d for d in data["applied"])

    # scenario.json + 빌드 산출물(scene-data.json) 모두 반영
    doc = _scenario(scene_env, run_id)
    assert next(s for s in doc["scenes"] if s["name"] == "절차")["dur"] == 14
    built = json.loads((build_dir / "scene-data.json").read_text(encoding="utf-8"))
    assert next(s for s in built["scenes"] if s["name"] == "절차")["dur"] == 14
    assert built["content"]["opening"]["title"]["accent"] == "핀포인트"

    # 원장 요약 갱신
    run = client.get(f"/api/runs/{run_id}").json()["data"]
    assert run["scenario_summary"]["total_dur"] == pytest.approx(
        round(sum(s["dur"] for s in doc["scenes"]), 3)
    )


def test_patch_failure_422_no_side_effect(
    client: TestClient, scene_env: Path, built_run: dict
) -> None:
    run_id = built_run["run_id"]
    before = json.dumps(_scenario(scene_env, run_id), sort_keys=True)
    res = client.patch(f"/api/runs/{run_id}/scenario", json={"ops": [
        {"op": "set_dur", "scene": "절차", "dur": 400},
    ]})
    assert res.status_code == 422
    body = res.json()
    assert body["success"] is False and "취소" in body["message"]
    assert json.dumps(_scenario(scene_env, run_id), sort_keys=True) == before

    assert client.patch(f"/api/runs/{run_id}/scenario", json={}).status_code == 400
    assert client.patch(f"/api/runs/{run_id}/scenario", json={"ops": []}).status_code == 400
