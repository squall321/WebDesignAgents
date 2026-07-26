# wdweb 웹 콘솔 API 테스트 — health/봉투/파이프라인 실행/프리뷰 경로 방어/페르소나/모듈/회의록
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wdcore.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
MEETING_FIXTURE = REPO_ROOT / "data" / "meetings" / "20260725-141604_scenario_build_adv-check_d954"


@pytest.fixture()
def web_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    data = tmp_path / "data"
    monkeypatch.setenv("WDA_DATA_DIR", str(data))
    monkeypatch.setenv("WDA_PERSONAS_ROOT", str(REPO_ROOT / "personas"))
    get_settings.cache_clear()
    # 회의록 API 픽스처 — 저장소의 실물 회의 1건을 임시 데이터 루트로 복사
    if MEETING_FIXTURE.is_dir():
        shutil.copytree(MEETING_FIXTURE, data / "meetings" / MEETING_FIXTURE.name)
    yield data
    get_settings.cache_clear()


@pytest.fixture()
def client(web_env: Path) -> TestClient:
    from wdweb.app import app

    return TestClient(app)


def _poll_run(client: TestClient, run_id: str, timeout: float = 90.0) -> dict:
    """실행이 종료 상태(done/failed)가 될 때까지 폴링한다."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/runs/{run_id}").json()
        assert body["success"] is True
        run = body["data"]
        if run["status"] in ("done", "failed"):
            return run
        time.sleep(0.3)
    pytest.fail(f"실행이 {timeout}초 안에 끝나지 않았다: {run_id}")


# ── health · 봉투 ────────────────────────────────────────────────────────────


def test_health(client: TestClient) -> None:
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_envelope_shape(client: TestClient) -> None:
    body = client.get("/api/runs").json()
    assert set(body) == {"success", "data", "message"}
    assert body["success"] is True

    # 오류도 같은 봉투로 나간다
    res = client.get("/api/runs/no-such-run")
    assert res.status_code == 404
    body = res.json()
    assert set(body) == {"success", "data", "message"}
    assert body["success"] is False
    assert body["message"]


# ── 파이프라인 실행 (report_sample end-to-end) ───────────────────────────────


def test_run_pipeline_end_to_end(client: TestClient, web_env: Path) -> None:
    report = json.loads(REPORT_SAMPLE.read_text(encoding="utf-8"))
    res = client.post("/api/runs", json={"report_json": report, "slug": "wdweb-e2e"})
    assert res.status_code == 202
    body = res.json()
    assert body["success"] is True
    run_id = body["data"]["run_id"]
    assert body["data"]["slug"] == "wdweb-e2e"

    run = _poll_run(client, run_id)
    assert run["status"] == "done", f"파이프라인 실패: {run.get('error')}"
    assert [s["status"] for s in run["stages"]] == ["done"] * 4

    # 시나리오 요약 — 씬 수·Σdur·core_message
    summary = run["scenario_summary"]
    assert summary["scene_count"] >= 1
    assert summary["total_dur"] > 0
    assert summary["core_message"]

    # 단계 산출 경로가 실제로 존재
    for stage in run["stages"]:
        assert Path(stage["output"]).is_file(), stage

    # 목록(최신순)에 포함
    runs = client.get("/api/runs").json()["data"]["runs"]
    assert runs[0]["run_id"] == run_id

    # 프리뷰 — 엔트리 서빙
    res = client.get(f"/api/runs/{run_id}/preview/{run['entry']}")
    assert res.status_code == 200
    assert "OM_SCENES" in res.text

    # 프리뷰 — 경로 탈출 차단 (../ 시도)
    res = client.get(f"/api/runs/{run_id}/preview/%2e%2e/%2e%2e/%2e%2e/pyproject.toml")
    assert res.status_code in (403, 404)
    res = client.get(f"/api/runs/{run_id}/preview/..%2f..%2fpyproject.toml")
    assert res.status_code in (403, 404)

    # 산출물 상태 — scenario 는 있고 mp4/pptx 는 아직 없다
    arts = client.get(f"/api/runs/{run_id}/artifacts").json()["data"]
    assert arts["scenario"]["exists"] is True
    assert arts["mp4"]["exists"] is False
    assert arts["pptx"]["exists"] is False

    # scenario 다운로드
    res = client.get(f"/api/runs/{run_id}/download/scenario")
    assert res.status_code == 200
    doc = json.loads(res.content)
    assert len(doc["scenes"]) == summary["scene_count"]

    # 미생성 산출물 다운로드는 404
    assert client.get(f"/api/runs/{run_id}/download/mp4").status_code == 404

    # QA — 게이트 2(데이터 단계)만 실행해 브라우저 없이 빠르게 검증
    res = client.post(f"/api/runs/{run_id}/qa", json={"gates": ["2"]})
    assert res.status_code == 200
    qa = res.json()["data"]
    assert "passed" in qa and "results" in qa
    assert Path(qa["report_path"]).is_file()
    # 원장에도 QA 요약이 기록된다
    run = client.get(f"/api/runs/{run_id}").json()["data"]
    assert run["qa"]["passed"] == qa["passed"]


def test_run_multipart_upload(client: TestClient) -> None:
    res = client.post(
        "/api/runs",
        files={"file": ("report.json", REPORT_SAMPLE.read_bytes(), "application/json")},
        data={"slug": "wdweb-multipart"},
    )
    assert res.status_code == 202
    run_id = res.json()["data"]["run_id"]
    run = _poll_run(client, run_id)
    assert run["status"] == "done", f"파이프라인 실패: {run.get('error')}"
    assert run["slug"] == "wdweb-multipart"


def test_run_bad_body(client: TestClient) -> None:
    res = client.post("/api/runs", json={"slug": "no-report"})
    assert res.status_code == 400
    assert res.json()["success"] is False


# ── 페르소나 · 모듈 · web 자산 ───────────────────────────────────────────────


def test_personas_14(client: TestClient) -> None:
    data = client.get("/api/personas").json()["data"]
    assert data["count"] == 14
    assert len(data["personas"]) == 14
    for p in data["personas"]:
        for key in ("id", "abbr", "name_ko", "category", "role"):
            assert p[key], (p, key)


def test_modules_registry(client: TestClient) -> None:
    data = client.get("/api/modules").json()["data"]
    modules = data["modules"]
    assert len(modules) >= 7
    ids = {m["id"] for m in modules}
    assert "tpl.opening" in ids


def test_module_preview_and_escape(client: TestClient) -> None:
    res = client.get("/api/modules/tpl.opening/preview/preview.html")
    assert res.status_code == 200
    assert "OM_SCENES" in res.text

    # 모듈 preview 경로 탈출 차단
    res = client.get("/api/modules/tpl.opening/preview/%2e%2e/%2e%2e/%2e%2e/pyproject.toml")
    assert res.status_code in (403, 404)

    # 미등록 모듈은 404
    assert client.get("/api/modules/tpl.nope/preview/preview.html").status_code == 404

    # preview.html 의 ../../../web/* 상대참조가 브라우저 정규화 후 닿는 자산 라우트
    res = client.get("/api/web/tokens/hwax-blue.json")
    assert res.status_code == 200
    assert json.loads(res.content)["id"] == "hwax-blue"
    res = client.get("/api/web/%2e%2e/pyproject.toml")
    assert res.status_code in (403, 404)


# ── 회의록 ──────────────────────────────────────────────────────────────────


def test_meetings_and_minutes(client: TestClient) -> None:
    if not MEETING_FIXTURE.is_dir():
        pytest.skip("저장소에 회의 픽스처가 없다")
    meetings = client.get("/api/meetings").json()["data"]["meetings"]
    assert len(meetings) >= 1
    meeting = meetings[0]
    res = client.get(f"/api/meetings/{meeting['id']}/minutes")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["meeting_id"] == meeting["id"]
    assert data["markdown"].strip()

    assert client.get("/api/meetings/00000000-dead-beef-0000-000000000000/minutes").status_code == 404


# ── SPA 마운트 ──────────────────────────────────────────────────────────────


def test_spa_served_after_api_routes(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "WebDesignAgents" in res.text
    # /api/* 가 SPA 에 먹히지 않는다 — 미지정 API 경로는 404 봉투/JSON 이어야 한다
    res = client.get("/api/no-such-endpoint")
    assert res.status_code == 404
