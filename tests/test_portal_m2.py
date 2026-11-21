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


# ── W-17 지우기 — 주인이 자기 실행과 산출물을 지운다 ─────────────────────────────
#
# RA 에서 보고서를 지운 사람이 WDA 의 사본도 지울 수 있어야 한다(포털 요청서 §9). 지금까지는 보존 만료
# (W-13 — 꺼 둔다)뿐이었다. 남의 실행 · 주인 없는 실행은 못 지우고, 도는 중인 실행은 거절한다(계약에
# 도는 실행의 처리가 없다 — 취소 W-20 이 없으므로 워커가 쓰는 디렉터리를 밑에서 빼지 않는다).

RID = "wr-20261121-000000-" + "ab" * 16


def _seed(tmp: Path, monkeypatch, *, owner: str | None = "alice@corp.example", run_id: str = RID,
          status: str = "done", render: dict | None = None, **extra) -> dict:
    """끝난 실행 하나를 임시 데이터 루트에 심는다 — 원장 + pipeline · build · renders 디렉터리."""
    monkeypatch.setattr(runledger, "data_dir", lambda: tmp)
    slug = f"ra-41-{run_id[-4:]}"
    for rel in (f"pipeline/{run_id}", f"build/{slug}", f"renders/{slug}"):
        (tmp / rel).mkdir(parents=True, exist_ok=True)
        (tmp / rel / "f.txt").write_text("보고서 본문 조각", encoding="utf-8")
    now = "2026-11-21T00:00:00+00:00"
    run = {
        "run_id": run_id, "slug": slug, "status": status, "owner": owner,
        "stages": [{"stage": s, "status": "done", "error": None, "output": f"/x/{s}"} for s in runledger.STAGES],
        "format": None, "idempotency_key": "portal-job-1", "render_request": {"targets": ["pptx"]},
        "scenario_summary": {"scene_count": 6, "total_dur": 72.0, "core_message": "비밀 결론"},
        "build_dir": str(tmp / "build" / slug), "entry": "index.html",
        "render": render if render is not None else {"status": "done", "outputs": {"pptx": str(tmp / "renders" / slug / "slides.pptx")}},
        "qa": None, "error": None, "chat": [{"role": "user", "text": "고쳐줘"}],
        "created_at": now, "updated_at": now, **extra,
    }
    runledger.write_run(run)
    return run


def _dirs(tmp: Path, run: dict) -> list[bool]:
    return [(tmp / "pipeline" / run["run_id"]).exists(), (tmp / "build" / run["slug"]).exists(),
            (tmp / "renders" / run["slug"]).exists()]


def test_owner_deletes_the_run_and_its_artifacts(client, tmp_path, monkeypatch):
    run = _seed(tmp_path, monkeypatch)
    res = client.delete(f"/api/runs/{RID}", headers=ALICE)
    assert res.status_code == 200, res.text
    assert res.json()["success"] is True and res.json()["data"]["deleted"] is True
    assert _dirs(tmp_path, run) == [False, False, False], "보고서 본문 · 빌드 · 산출물이 남았다"
    # 원장은 묘비로 남는다 — 지웠다는 사실(410)을 답하고, MCP 가 그 자리를 주인 없는 것으로 보지 않게
    tomb = runledger.read_run(RID)
    assert tomb["deleted_at"] and tomb["deleted_by"] == "owner" and tomb["owner"] == "alice@corp.example"
    assert tomb["slug"] == run["slug"]
    blob = json.dumps(tomb, ensure_ascii=False)
    for leak in ("비밀 결론", "고쳐줘", "portal-job-1", "/x/ingest"):
        assert leak not in blob, f"묘비에 내용이 남았다: {leak}"
    # 그 뒤 — 주인에게는 410(지워짐), 목록에서는 빠진다
    gone = client.get(f"/api/runs/{RID}", headers=ALICE)
    assert gone.status_code == 410 and gone.json()["code"] == "NOT_FOUND"
    assert RID not in {r["run_id"] for r in client.get("/api/runs", headers=ALICE).json()["data"]["runs"]}


def test_delete_is_idempotent(client, tmp_path, monkeypatch):
    run = _seed(tmp_path, monkeypatch)
    assert client.delete(f"/api/runs/{RID}", headers=ALICE).status_code == 200
    # 지운 뒤 남은 조각이 생겼다고 치자(뒤늦게 끝난 QA 등) — 다시 지우면 그것도 치운다
    (tmp_path / "build" / run["slug"]).mkdir(parents=True)
    again = client.delete(f"/api/runs/{RID}", headers=ALICE)
    assert again.status_code == 200 and again.json()["data"]["already"] is True
    assert _dirs(tmp_path, run) == [False, False, False]


@pytest.mark.parametrize("headers", [BOB, {}])
def test_others_cannot_delete_an_owned_run(client, tmp_path, monkeypatch, headers):
    """남이거나 신원이 없으면 없는 것과 같은 404 — 그리고 아무것도 지워지지 않는다."""
    run = _seed(tmp_path, monkeypatch)
    res = client.delete(f"/api/runs/{RID}", headers=headers)
    assert res.status_code == 404 and res.json()["code"] == "NOT_FOUND"
    assert _dirs(tmp_path, run) == [True, True, True]
    assert runledger.read_run(RID) == run


def test_delete_handler_checks_the_owner_itself(tmp_path, monkeypatch):
    """미들웨어만 믿지 않는다 — 지우기는 되돌릴 수 없으니 핸들러가 주인을 한 번 더 본다(두 겹).

    미들웨어 한 곳이 틀리면 전부 틀린다(2026-11-01 root_path 실사고). 여기서는 미들웨어를 거치지 않고
    핸들러를 바로 부른다.
    """
    from types import SimpleNamespace

    from fastapi import HTTPException

    from wdweb.app import delete_run as handler

    run = _seed(tmp_path, monkeypatch)
    for who in ("bob@corp.example", None):
        req = SimpleNamespace(headers={"X-Heax-User-Email": who} if who else {})
        with pytest.raises(HTTPException) as err:
            handler(RID, req)
        assert err.value.status_code == 404
    assert _dirs(tmp_path, run) == [True, True, True]


@pytest.mark.parametrize("headers", [ALICE, {}])
def test_ownerless_run_cannot_be_deleted(client, tmp_path, monkeypatch, headers):
    """주인 없는 실행은 모두에게 열려 있다 — 그래서 아무나 지우게 두지 않는다."""
    run = _seed(tmp_path, monkeypatch, owner=None)
    res = client.delete(f"/api/runs/{RID}", headers=headers)
    assert res.status_code == 403 and res.json()["success"] is False
    assert _dirs(tmp_path, run) == [True, True, True]
    assert "deleted_at" not in runledger.read_run(RID)


@pytest.mark.parametrize("status,render", [
    ("queued", None), ("running", None),
    ("done", {"status": "queued"}), ("done", {"status": "building"}), ("done", {"status": "rendering"}),
])
def test_running_run_is_refused(client, tmp_path, monkeypatch, status, render):
    """도는 중이면 409 BUSY — 워커가 쓰는 디렉터리를 밑에서 빼지 않는다(취소 W-20 이 없다)."""
    run = _seed(tmp_path, monkeypatch, status=status, render=render if render is not None else {})
    res = client.delete(f"/api/runs/{RID}", headers=ALICE)
    assert res.status_code == 409 and res.json()["code"] == "BUSY"
    assert _dirs(tmp_path, run) == [True, True, True]
    assert "deleted_at" not in runledger.read_run(RID)


@pytest.mark.parametrize("render", [None, {"status": "failed", "error": "x"}])
def test_failed_run_can_be_deleted(client, tmp_path, monkeypatch, render):
    """실패한 실행에도 보고서 본문(report.raw.json)이 남아 있다 — 지울 수 있어야 한다."""
    run = _seed(tmp_path, monkeypatch, status="failed", render=render if render is not None else {})
    assert client.delete(f"/api/runs/{RID}", headers=ALICE).status_code == 200
    assert _dirs(tmp_path, run) == [False, False, False]


def test_delete_spares_directories_shared_with_a_live_run(client, tmp_path, monkeypatch):
    """slug 꼬리는 run_id 끝 4자다 — 드물게 겹친 다른 실행의 build · renders 를 같이 지우지 않는다."""
    other = "wr-20261121-000001-" + "cd" * 14 + "abab"
    run = _seed(tmp_path, monkeypatch)
    _seed(tmp_path, monkeypatch, owner="bob@corp.example", run_id=other)
    assert runledger.read_run(other)["slug"] == run["slug"]
    res = client.delete(f"/api/runs/{RID}", headers=ALICE)
    assert res.status_code == 200 and res.json()["data"]["kept_shared"] == ["build", "renders"]
    assert _dirs(tmp_path, run) == [False, True, True], "내 보고서 본문은 지우고, 남과 겹친 자리는 둔다"


def test_delete_removes_the_qa_report_of_the_run(client, tmp_path, monkeypatch):
    qa = tmp_path / "qa_reports" / "20261121-000000-abc123"
    qa.mkdir(parents=True)
    (qa / "qa.json").write_text("{}", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "qa.json").write_text("{}", encoding="utf-8")
    _seed(tmp_path, monkeypatch, qa={"passed": True, "report_path": str(qa / "qa.json")})
    assert client.delete(f"/api/runs/{RID}", headers=ALICE).status_code == 200
    assert not qa.exists()
    # 원장이 데이터 루트 밖을 가리켜도 거기는 건드리지 않는다
    other = "wr-20261121-000002-" + "ef" * 16
    _seed(tmp_path, monkeypatch, run_id=other, qa={"passed": True, "report_path": str(outside / "qa.json")})
    assert client.delete(f"/api/runs/{other}", headers=ALICE).status_code == 200
    assert (outside / "qa.json").is_file()


def test_delete_that_leaves_pieces_says_so_and_can_be_retried(client, tmp_path, monkeypatch):
    """못 지운 조각을 숨기지 않는다 — 500 INTERNAL 이고, 묘비는 이미 섰으므로(그 실행은 닫혔다) 다시 부르면 마저 치운다."""
    import shutil

    run = _seed(tmp_path, monkeypatch)
    real = shutil.rmtree
    monkeypatch.setattr(shutil, "rmtree", lambda *a, **k: None)          # 지우기가 조용히 실패한다
    res = client.delete(f"/api/runs/{RID}", headers=ALICE)
    assert res.status_code == 500 and res.json()["code"] == "INTERNAL"
    assert runledger.read_run(RID)["deleted_at"], "실행은 닫혔다 — 남은 조각이 주인 없는 것으로 열리지 않는다"
    assert client.get(f"/api/runs/{RID}", headers=ALICE).status_code == 410
    monkeypatch.setattr(shutil, "rmtree", real)
    again = client.delete(f"/api/runs/{RID}", headers=ALICE)
    assert again.status_code == 200 and again.json()["data"]["already"] is True
    assert _dirs(tmp_path, run) == [False, False, False]
    # 닫힌 실행이어도 남은 지우지 못한다
    assert client.delete(f"/api/runs/{RID}", headers=BOB).status_code == 404


def test_deleted_run_stays_closed_to_mcp(client, tmp_path, monkeypatch):
    """묘비가 주인을 쥐고 있어야 한다 — 원장을 없애면 남은 조각이 '주인 없는 run' 으로 MCP 에 열린다."""
    from wdmcp import server as mcp_server
    from wdmcp.ownership import is_owned_path, is_owned_run

    run = _seed(tmp_path, monkeypatch)
    assert client.delete(f"/api/runs/{RID}", headers=ALICE).status_code == 200
    assert is_owned_run(RID) and is_owned_path(f"data/build/{run['slug']}")
    assert mcp_server.scene_list(run_id=RID)["error"]["code"] == "NOT_FOUND"


def test_health_advertises_delete(client):
    assert "delete" in client.get("/api/health").json()["features"]


@pytest.mark.parametrize("root_path", ["/apps/web_design_agents", ""])
def test_delete_ownership_holds_behind_a_proxy_prefix(client, report, root_path):
    """실기동 — 허브와 같은 조건(--root-path)에서 남의 지우기가 404 이고 실행이 남아야 한다.

    TestClient 는 root_path 를 scope path 에 싣지 않아 날것 경로 검사의 구멍을 재현하지 못한다
    (test_portal_contract 의 같은 시험 · 결정 77).
    """
    import socket
    import subprocess
    import sys
    import urllib.error
    import urllib.request

    rid = client.post("/api/runs", json={"report_json": report, "slug": "del"},
                      headers=ALICE).json()["data"]["run_id"]
    _wait(rid, lambda r: r["status"] in ("done", "failed"))     # 도는 중이면 409 다 — 끝난 뒤에 지운다

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    argv = [sys.executable, "-m", "uvicorn", "wdweb.app:app", "--host", "127.0.0.1", "--port", str(port)]
    if root_path:
        argv += ["--root-path", root_path]
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def call(method: str, who: str | None) -> int:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/runs/{rid}", method=method,
                                     headers={"X-Heax-User-Email": who} if who else {})
        try:
            return urllib.request.urlopen(req, timeout=20).status
        except urllib.error.HTTPError as exc:
            return exc.code

    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        else:
            pytest.skip("uvicorn 이 뜨지 않았다")
        assert call("DELETE", "bob@corp.example") == 404, f"root_path={root_path!r} 에서 남이 지웠다"
        assert call("DELETE", None) == 404
        assert call("GET", "alice@corp.example") == 200, "남의 지우기 뒤에도 실행은 그대로다"
        assert (runledger.data_dir() / "pipeline" / rid).is_dir()
        assert call("DELETE", "alice@corp.example") == 200
        assert call("GET", "alice@corp.example") == 410
        assert not (runledger.data_dir() / "pipeline" / rid).exists()
    finally:
        proc.terminate()
        proc.wait(timeout=20)


# ── W-18 MCP 쪽 주인 — 게이트웨이 사람별 위임(per_user_sso)으로 확인된 사람만 자기 실행에 닿는다 ───────
#
# MCP 길의 신원은 두 머리 어느 것도 아니다. X-Heax-User-Email 은 /mcp 에서 게이트웨이 서비스 토큰의
# 주인(허브 첫 관리자)으로 접히고, x-hwax-user 는 Caddy 가 지우지 않아 누구나 적어 보낸다(포털 WD-D4).
# 믿는 것은 **서명**이다 — 게이트웨이와만 나눠 가진 비밀로 POST /api/auth/sso 가 낸 단기 단언(wdsso_)을
# 게이트웨이가 X-Heax-Sso-Assertion 으로 싣는다(HWAXRisk 꼴, 포털 요청서 §9 W-18 · WD-D19).
# 비밀이 없으면(기본) 창구는 404 이고 단언 머리는 무시된다 — W-4 그대로(주인 있는 실행은 MCP 에 없다).

SECRET = "wda-gateway-secret-for-tests-0123456789"


@pytest.fixture()
def gateway_secret(monkeypatch, tmp_path):
    """박스에 게이트웨이 비밀이 있는 상태 — secrets.env 가 아니라 환경변수로 준다."""
    monkeypatch.setenv("WDA_GATEWAY_SECRET", SECRET)
    return SECRET


def _sso(client, **headers):
    return client.post("/api/auth/sso", headers=headers)


def test_sso_is_closed_without_a_secret(client, monkeypatch):
    monkeypatch.delenv("WDA_GATEWAY_SECRET", raising=False)
    res = _sso(client, **{"X-Heax-Gateway-Secret": SECRET, "X-Hwax-Delegate-Email": "alice@corp.example"})
    assert res.status_code == 404
    assert "mcp_owner" not in client.get("/api/health").json()["features"]


def test_short_secret_counts_as_no_secret(client, monkeypatch):
    """짧은 비밀은 서명을 지어낼 수 있다 — 켜지지 않은 것으로 본다."""
    monkeypatch.setenv("WDA_GATEWAY_SECRET", "short")
    res = _sso(client, **{"X-Heax-Gateway-Secret": "short", "X-Hwax-Delegate-Email": "alice@corp.example"})
    assert res.status_code == 404


def test_sso_needs_the_shared_secret(client, gateway_secret):
    for got in ({}, {"X-Heax-Gateway-Secret": "wrong-secret-wrong-secret"}):
        res = _sso(client, **got, **{"X-Hwax-Delegate-Email": "alice@corp.example"})
        assert res.status_code == 401 and res.json()["success"] is False


def test_sso_never_mints_from_the_folded_identity_header(client, gateway_secret):
    """X-Heax-User-Email 만으로는 내주지 않는다 — 이 길에서 그 머리는 허브 관리자로 접힌 값이다."""
    res = _sso(client, **{"X-Heax-Gateway-Secret": SECRET, "X-Heax-User-Email": "admin@corp.example"})
    assert res.status_code == 400 and res.json()["code"] == "INVALID"
    bad = _sso(client, **{"X-Heax-Gateway-Secret": SECRET, "X-Hwax-Delegate-Email": "not-an-email"})
    assert bad.status_code == 400


def test_sso_mints_a_short_lived_assertion_for_the_delegate(client, gateway_secret):
    from wdmcp import delegation

    res = _sso(client, **{"X-Heax-Gateway-Secret": SECRET, "X-Hwax-Delegate-Email": " Alice@Corp.Example ",
                          "X-Heax-User-Email": "admin@corp.example"})
    assert res.status_code == 200, res.text
    data = res.json()["data"]
    tok = data["access_token"]
    assert tok.startswith("wdsso_") and data["token_type"] == "bearer"
    # 게이트웨이는 수명이 호출 한도(600초)보다 길어야 한다고 본다(README 'ste 방식 사람별 위임')
    assert 600 < data["expires_in"] <= 3600
    assert delegation.verify(tok) == "alice@corp.example", "위임 머리의 사람이다 — 접힌 관리자가 아니다"
    assert "mcp_owner" in client.get("/api/health").json()["features"]


def test_assertion_is_rejected_when_forged_expired_or_from_another_secret(gateway_secret, monkeypatch):
    from wdmcp import delegation

    now = time.time()
    tok = delegation.mint("alice@corp.example", secret=SECRET, now=now)
    assert delegation.verify(tok, now=now + 10) == "alice@corp.example"
    assert delegation.verify(tok, now=now + delegation.TTL_S + 1) is None, "만료"
    body, _, sig = tok[len("wdsso_"):].partition(".")
    import base64

    forged = base64.urlsafe_b64encode(json.dumps({"e": "bob@corp.example", "x": int(now) + 600}).encode()).decode().rstrip("=")
    assert delegation.verify(f"wdsso_{forged}.{sig}", now=now) is None, "몸을 바꾸면 서명이 맞지 않는다"
    assert delegation.verify(f"wdsso_{body}.", now=now) is None and delegation.verify(f"wdsso_{body}", now=now) is None
    assert delegation.verify(delegation.mint("alice@corp.example", secret="another-secret-0123456789", now=now), now=now) is None
    assert delegation.verify("rrsso_" + tok[len("wdsso_"):], now=now) is None, "다른 앱의 단언 꼴은 받지 않는다"
    for junk in ("", "wdsso_", "wdsso_!!!.###", None, 7):
        assert delegation.verify(junk, now=now) is None
    monkeypatch.delenv("WDA_GATEWAY_SECRET")
    assert delegation.verify(tok, now=now) is None, "비밀이 없으면 어떤 단언도 받지 않는다"


def test_secret_can_live_in_the_data_dir_secrets_file(tmp_path, monkeypatch):
    """허브 앱의 비밀은 매니페스트(git)가 아니라 앱 데이터 디렉터리의 secrets.env 에 둔다 — 파일이 환경변수를 이긴다."""
    from wdmcp import delegation

    monkeypatch.setattr(runledger, "data_dir", lambda: tmp_path)
    monkeypatch.setenv("WDA_GATEWAY_SECRET", "env-secret-0123456789abcdef")
    assert delegation.gateway_secret() == "env-secret-0123456789abcdef"
    (tmp_path / "secrets.env").write_text('# 게이트웨이와만 나눈다\nOTHER=1\nWDA_GATEWAY_SECRET="file-secret-0123456789abcdef"\n',
                                         encoding="utf-8")
    assert delegation.gateway_secret() == "file-secret-0123456789abcdef"


def _as(monkeypatch, headers: dict | None):
    """이 MCP 요청의 머리를 흉내 낸다 — 진짜 머리 길은 아래 실기동 시험이 본다."""
    from wdmcp import delegation

    monkeypatch.setattr(delegation, "_request_headers", lambda: headers)


def _assertion(email: str) -> dict:
    from wdmcp import delegation

    return {"x-heax-sso-assertion": delegation.mint(email, secret=SECRET)}


def test_mcp_opens_an_owned_run_only_to_its_verified_owner(tmp_path, monkeypatch, gateway_secret):
    from wdmcp import server as mcp_server

    run = _seed(tmp_path, monkeypatch)

    def code(**kw):
        out = mcp_server.scene_list(**kw)
        return "OK" if out["ok"] else out["error"]["code"]

    _as(monkeypatch, None)
    assert code(run_id=RID) == "NOT_FOUND", "확인된 신원이 없으면 종전 그대로 닫힌다(W-4)"
    _as(monkeypatch, _assertion("bob@corp.example"))
    assert code(run_id=RID) == "NOT_FOUND", "남의 단언으로는 열리지 않는다"
    _as(monkeypatch, {"x-heax-user-email": "alice@corp.example", "x-hwax-user": "alice@corp.example"})
    assert code(run_id=RID) == "NOT_FOUND", "접히는 머리 · 위조할 수 있는 머리는 신원이 아니다"
    _as(monkeypatch, {"x-heax-sso-assertion": "wdsso_e30.AAAA"})
    assert code(run_id=RID) == "NOT_FOUND"
    _as(monkeypatch, _assertion("alice@corp.example"))
    assert code(run_id=RID) != "NOT_FOUND", "확인된 주인에게는 연다"
    # 경로로 들어오는 도구도 같은 판정이다
    build = str(tmp_path / "build" / run["slug"])
    assert mcp_server.qa_run(build_path=build).get("error", {}).get("code") != "NOT_FOUND"
    _as(monkeypatch, _assertion("bob@corp.example"))
    assert mcp_server.qa_run(build_path=build)["error"]["code"] == "NOT_FOUND"


def test_mcp_assertion_is_ignored_when_the_feature_is_off(tmp_path, monkeypatch):
    """비밀이 없는 박스(기본)에서는 단언 머리가 있어도 종전 그대로다."""
    from wdmcp import delegation
    from wdmcp import server as mcp_server

    _seed(tmp_path, monkeypatch)
    tok = delegation.mint("alice@corp.example", secret=SECRET)
    monkeypatch.delenv("WDA_GATEWAY_SECRET", raising=False)
    _as(monkeypatch, {"x-heax-sso-assertion": tok})
    assert mcp_server.scene_list(run_id=RID)["error"]["code"] == "NOT_FOUND"


def test_mcp_never_opens_a_deleted_run_even_to_its_owner(client, tmp_path, monkeypatch, gateway_secret):
    from wdmcp import server as mcp_server

    _seed(tmp_path, monkeypatch)
    assert client.delete(f"/api/runs/{RID}", headers=ALICE).status_code == 200
    _as(monkeypatch, _assertion("alice@corp.example"))
    assert mcp_server.scene_list(run_id=RID)["error"]["code"] == "NOT_FOUND"


def test_mcp_ownerless_runs_stay_open_to_everyone(tmp_path, monkeypatch, gateway_secret):
    from wdmcp.ownership import closed_to

    _seed(tmp_path, monkeypatch, owner=None)
    for who in (None, "alice@corp.example", "bob@corp.example"):
        assert closed_to(who, run_ids=[RID]) is False


def test_shared_slug_is_closed_unless_every_owner_is_the_caller(tmp_path, monkeypatch):
    """slug 가 겹친 두 주인의 build 자리 — 한 사람의 단언으로 다른 사람의 조각에 닿지 않는다."""
    from wdmcp.ownership import closed_to

    other = "wr-20261121-000001-" + "cd" * 14 + "abab"
    run = _seed(tmp_path, monkeypatch)
    _seed(tmp_path, monkeypatch, owner="bob@corp.example", run_id=other)
    path = f"data/build/{run['slug']}/index.html"
    assert closed_to("alice@corp.example", paths=[path]) and closed_to("bob@corp.example", paths=[path])
    assert closed_to("alice@corp.example", run_ids=[RID]) is False


def _job(tmp: Path, run: dict, monkeypatch, job_id: str = "job-m2"):
    """주인 있는 실행 위에 선 렌더 잡 하나(확인된 주인이 MCP render_submit 으로 만든 것)."""
    from wdmcp import jobs as mcp_jobs
    from wdmcp.schemas import RenderJob

    out = tmp / "renders" / run["slug"] / "slides.pptx"
    out.write_bytes(b"PK\x03\x04deck")
    job = RenderJob(job_id=job_id, status="done", targets=["pptx"], build_dir=run["build_dir"], entry="index.html",
                    outputs={"pptx": str(out)}, created_at="2026-11-21T00:00:00+00:00", updated_at="2026-11-21T00:00:00+00:00")
    monkeypatch.setattr(mcp_jobs, "read_job", lambda jid: job if jid == job_id else None)
    return job


def test_render_status_hides_jobs_on_someone_elses_run(tmp_path, monkeypatch, gateway_secret):
    """확인된 주인이 MCP 로 렌더를 맡길 수 있게 되면 그 잡이 생긴다 — 잡 id 만으로 남의 경로를 보여 주지 않는다(W-4)."""
    from wdmcp import server as mcp_server

    run = _seed(tmp_path, monkeypatch)
    _job(tmp_path, run, monkeypatch)
    _as(monkeypatch, None)
    assert mcp_server.render_status(job_id="job-m2")["error"]["code"] == "NOT_FOUND"
    _as(monkeypatch, _assertion("bob@corp.example"))
    assert mcp_server.render_status(job_id="job-m2")["error"]["code"] == "NOT_FOUND"
    _as(monkeypatch, _assertion("alice@corp.example"))
    assert mcp_server.render_status(job_id="job-m2")["ok"] is True


def test_render_job_download_opens_to_the_rest_identified_owner(client, tmp_path, monkeypatch):
    """렌더 잡 내려받기(REST)는 Caddy 가 실은 신원이 그 실행의 주인일 때만 — 남 · 신원 없음은 종전대로 404(W-4)."""
    import wdweb.app as webapp

    run = _seed(tmp_path, monkeypatch)
    _job(tmp_path, run, monkeypatch)
    monkeypatch.setattr(webapp, "data_dir", lambda: tmp_path)
    for headers in (BOB, {}):
        res = client.get("/api/render_jobs/job-m2/download/pptx", headers=headers)
        assert res.status_code == 404 and res.json()["code"] == "NOT_FOUND"
    ok = client.get("/api/render_jobs/job-m2/download/pptx", headers=ALICE)
    assert ok.status_code == 200 and ok.content.startswith(b"PK\x03\x04")
    assert ok.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize("root_path", ["/apps/web_design_agents", ""])
def test_mcp_owner_over_real_http(client, report, root_path, tmp_path):
    """실기동 — 진짜 uvicorn 의 /mcp 에 streamable HTTP 로 붙어 단언 머리가 도구까지 닿는지 본다.

    단위 시험은 머리 읽기를 흉내 낸다. 이 시험만이 '요청 머리 → MCP 도구 문맥 → 서명 검증' 길 전체와
    --root-path 뒤의 /api/auth/sso · /mcp 를 본다.
    """
    import os
    import socket
    import subprocess
    import sys
    import urllib.error
    import urllib.request

    import anyio
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    rid = client.post("/api/runs", json={"report_json": report, "slug": "mcp"},
                      headers=ALICE).json()["data"]["run_id"]
    run = _wait(rid, lambda r: r["status"] in ("done", "failed"))
    assert run["status"] == "done", run.get("error")

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    argv = [sys.executable, "-m", "uvicorn", "wdweb.app:app", "--host", "127.0.0.1", "--port", str(port)]
    if root_path:
        argv += ["--root-path", root_path]
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env={**os.environ, "WDA_GATEWAY_SECRET": SECRET})
    base = f"http://127.0.0.1:{port}"

    def mint(email: str) -> str:
        req = urllib.request.Request(f"{base}/api/auth/sso", method="POST", data=b"", headers={
            "X-Heax-Gateway-Secret": SECRET, "X-Hwax-Delegate-Email": email})
        return json.loads(urllib.request.urlopen(req, timeout=20).read())["data"]["access_token"]

    async def scene_list(headers: dict) -> dict:
        async with streamablehttp_client(f"{base}/mcp", headers=headers) as (read, write, _sid):
            async with ClientSession(read, write) as sess:
                await sess.initialize()
                res = await sess.call_tool("scene_list", {"run_id": rid})
                return json.loads(res.content[0].text)

    def code(headers: dict) -> str:
        out = anyio.run(scene_list, headers)
        return "OK" if out["ok"] else out["error"]["code"]

    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{base}/api/health", timeout=2)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        else:
            pytest.skip("uvicorn 이 뜨지 않았다")
        assert code({}) == "NOT_FOUND"
        assert code({"X-Heax-User-Email": "alice@corp.example", "x-hwax-user": "alice@corp.example"}) == "NOT_FOUND"
        assert code({"X-Heax-Sso-Assertion": mint("bob@corp.example")}) == "NOT_FOUND"
        assert code({"X-Heax-Sso-Assertion": mint("alice@corp.example")}) == "OK", (
            f"root_path={root_path!r} 에서 확인된 주인에게 열리지 않았다 — 단언 머리가 도구까지 닿지 않는다")
        # 창구 자체 — 비밀 없이는 401, 위임 머리 없이는 400
        for hdrs, want in (({"X-Hwax-Delegate-Email": "alice@corp.example"}, 401),
                           ({"X-Heax-Gateway-Secret": SECRET, "X-Heax-User-Email": "alice@corp.example"}, 400)):
            try:
                urllib.request.urlopen(urllib.request.Request(f"{base}/api/auth/sso", method="POST", data=b"", headers=hdrs),
                                       timeout=20)
                got = 200
            except urllib.error.HTTPError as exc:
                got = exc.code
            assert got == want, hdrs
    finally:
        proc.terminate()
        proc.wait(timeout=20)
