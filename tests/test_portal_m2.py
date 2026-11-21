# 포털 계약 M2 회귀 — 주인 있는 실행은 서비스 자격으로 RA 그림을 받지 않는다 · 지우기(W-17) · MCP 주인(W-18)
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wdpipeline import assets
from wdweb import runs as runledger
from wdweb.app import app

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
ALICE = {"X-Heax-User-Email": "Alice@Corp.Example"}
BOB = {"X-Heax-User-Email": "bob@corp.example"}

# 그림(file_id) 블록이 든 작은 보고서 — RA 의 ReportRead 꼴(쪽마다 extra_blocks + content)
IMG_REPORT = {
    "title": "그림 든 보고서", "report_date": "2026-11-21",
    "pages": [{
        "name": "1쪽",
        "extra_blocks": [{"id": "h", "type": "heading", "props": {"level": 1}},
                         {"id": "t", "type": "rich_text", "props": {}},
                         {"id": "img", "type": "image", "props": {"max_count": 1}}],
        "content": {"h": {"text": "그림 든 보고서"}, "t": {"markdown": "본문 한 줄이다."},
                    "img": {"files": [{"file_id": 77, "caption": "그림 1"}]}},
        "blocks_order": ["h", "t", "img"],
    }],
}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def report():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def _wait(run_id: str, pred, timeout: float = 90.0) -> dict:
    """원장이 pred 를 채울 때까지 — 파이프라인은 뒤 스레드에서 돈다."""
    end = time.time() + timeout
    run = None
    while time.time() < end:
        run = runledger.read_run(run_id)
        if run is not None and pred(run):
            return run
        time.sleep(0.05)
    raise AssertionError(f"기다리다 끝났다: {run_id} — {run}")


def _ingested(run: dict) -> bool:
    return run["stages"][0]["status"] in ("done", "failed")


# ── 주인 있는 실행은 서비스 자격(WDA_RA_*)으로 RA 그림을 받지 않는다 ─────────────
#
# 포털은 그 사람 명의로 RA 를 읽어 본문만 넘긴다. 그 본문의 file_id 를 WDA 가 제 서비스 계정으로
# 다시 받으면 '사람 대신 서비스 계정이 RA 를 읽는 길' 이 된다(요청서 §6 그림 · 포털 WD-D15).


@pytest.fixture()
def ra_calls(monkeypatch):
    """서비스 자격이 박스에 있는 상태 — RA 로 나가는 두 걸음(로그인/머리 · 받기)을 가짜로 바꿔 센다."""
    monkeypatch.setenv("WDA_RA_BASE_URL", "http://ra.invalid")
    monkeypatch.setenv("WDA_RA_TOKEN", "svc-token")
    calls: list[str] = []

    def ctx(base_url, token):
        calls.append("context")
        return {"base": "http://ra.invalid", "headers": {"Authorization": "Bearer svc-token"}}, ""

    def download(ctx_, file_id, dest_dir):
        calls.append(f"download:{file_id}")
        return None, "REST 다운로드 실패 (HTTP 404)."

    monkeypatch.setattr(assets, "_rest_context", ctx)
    monkeypatch.setattr(assets, "_download", download)
    return calls


def test_resolve_assets_skips_the_service_fetch_when_told(ra_calls):
    recs = assets.resolve_assets(["77", "78"], service_rest=False)
    assert ra_calls == [], "서비스 자격으로 RA 에 닿았다 — 로그인도 받기도 하면 안 된다"
    assert [r["status"] for r in recs] == ["unresolved", "unresolved"]
    assert all("서비스 자격" in r["reason"] for r in recs), recs[0]["reason"]


def test_resolve_assets_default_still_uses_the_service_fetch(ra_calls):
    """종전 길(주인 없는 실행 · CLI · MCP)은 그대로다."""
    assets.resolve_assets(["77"])
    assert ra_calls == ["context", "download:77"]


def test_owned_run_never_fetches_ra_images_with_service_credentials(client, ra_calls):
    rid = client.post("/api/runs", json={"report_json": IMG_REPORT, "slug": "img"},
                      headers=ALICE).json()["data"]["run_id"]
    run = _wait(rid, _ingested)
    assert run["stages"][0]["status"] == "done", run["stages"][0]
    assert ra_calls == [], "주인 있는 실행이 서비스 자격으로 RA 를 불렀다"
    # 그 사실이 결과에 드러난다 — 조용히 빠지지 않는다
    assert run["assets"]["service_fetch"] is False
    assert run["assets"]["total"] == 1 and run["assets"]["resolved"] == 0
    assert [s["file_id"] for s in run["assets"]["skipped"]] == ["77"]
    assert "서비스 자격" in run["assets"]["skipped"][0]["reason"]
    assert run["warnings"] and "1개" in run["warnings"][0]
    # 정규화본에도 지금처럼 까닭이 남는다(요청서 §6)
    norm = json.loads((runledger.data_dir() / "pipeline" / rid / "report.norm.json").read_text(encoding="utf-8"))
    assert norm["assets_meta"][0]["status"] == "unresolved" and "서비스 자격" in norm["assets_meta"][0]["reason"]


def test_ownerless_run_keeps_the_old_path(client, ra_calls):
    rid = client.post("/api/runs", json={"report_json": IMG_REPORT, "slug": "img"}).json()["data"]["run_id"]
    run = _wait(rid, _ingested)
    assert ra_calls == ["context", "download:77"], "주인 없는 실행은 종전대로 서비스 자격을 쓴다"
    assert "assets" not in run and "warnings" not in run, "주인 없는 실행의 원장 꼴은 바뀌지 않는다"


def test_owned_run_without_images_has_nothing_to_report(client, report, ra_calls):
    rid = client.post("/api/runs", json={"report_json": report, "slug": "noimg"},
                      headers=ALICE).json()["data"]["run_id"]
    run = _wait(rid, _ingested)
    assert run["assets"] == {"service_fetch": False, "total": 0, "resolved": 0, "skipped": [], "skipped_count": 0}
    assert "warnings" not in run


def test_resumed_owned_run_still_skips_the_service_fetch(client, ra_calls, monkeypatch):
    """재개(resume)가 ingest 부터 다시 돌아도 주인은 원장에서 읽는다 — 인자로 넘기면 재개 길에서 빠진다."""
    rid = client.post("/api/runs", json={"report_json": IMG_REPORT, "slug": "img"},
                      headers=ALICE).json()["data"]["run_id"]
    _wait(rid, lambda r: r["status"] in ("done", "failed"))
    (runledger.data_dir() / "pipeline" / rid / "report.norm.json").unlink()   # ingest 산출물이 없다 → 거기서 재개
    run = runledger.read_run(rid)
    run["status"] = "failed"
    runledger.write_run(run)
    assert client.post(f"/api/runs/{rid}/resume", headers=ALICE).json()["data"]["start_from"] == "ingest"
    _wait(rid, lambda r: r["status"] in ("done", "failed") and _ingested(r) and r["stages"][0]["status"] == "done")
    assert ra_calls == []
