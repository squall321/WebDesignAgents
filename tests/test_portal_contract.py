# 포털 계약 회귀 — 신원·주인·오류 코드·한도·내려받기 머리 (W-1 ~ W-15 · W-22)
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wdweb import runs as runledger
from wdweb.app import ERROR_CODES, SECRET_HEADERS, app

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
ALICE = {"X-Heax-User-Email": "Alice@Corp.Example"}
BOB = {"X-Heax-User-Email": "bob@corp.example"}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def report():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


# ── W-1 주인 · W-5 id ────────────────────────────────────────────────────


def test_owner_comes_from_the_header_only(client, report):
    """본문의 어떤 owner 칸도 믿지 않는다 — 주인은 X-Heax-User-Email 뿐이다."""
    r = client.post("/api/runs",
                    json={"report_json": report, "owner": "mallory@evil.example"},
                    headers=ALICE)
    assert r.status_code == 202
    data = r.json()["data"]
    assert data["owner"] == "alice@corp.example"      # 대소문자는 접는다
    run = runledger.read_run(data["run_id"])
    assert run["owner"] == "alice@corp.example"


def test_no_header_means_no_owner(client, report):
    """신원이 없으면 주인 없는 run — 거부(401)하지 않는다. MCP·CLI 가 이쪽이다."""
    r = client.post("/api/runs", json={"report_json": report})
    assert r.status_code == 202
    assert r.json()["data"]["owner"] is None


def test_owned_run_id_has_128_bits(client, report):
    owned = client.post("/api/runs", json={"report_json": report}, headers=ALICE)
    free = client.post("/api/runs", json={"report_json": report})
    assert len(owned.json()["data"]["run_id"].split("-")[-1]) == 32   # 128비트
    assert len(free.json()["data"]["run_id"].split("-")[-1]) == 4     # 종전 꼴 유지


@pytest.mark.parametrize("bogus", ["../etc", "....", "%2e%2e", "a.b", "x/y", "a b"])
def test_run_id_shape_blocks_path_escape(client, bogus):
    """run_id 는 경로 조각으로 이어 붙는다 — 점·슬래시·퍼센트를 막으면 탈출이 불가능하다."""
    assert not runledger.valid_run_id(bogus)
    assert client.get(f"/api/runs/{bogus}").status_code == 404


@pytest.mark.parametrize("ok", ["wr-20261101-000000-abcd", "delib_v2", "ci-gates", "wr-parity"])
def test_run_id_shape_accepts_other_makers(ok):
    """검사의 뜻은 '경로로 안전한가' 이지 '우리가 만든 꼴인가' 가 아니다.

    시각 꼴까지 강제하면 MCP·CLI 가 붙인 id 와 테스트 픽스처가 통째로 404 가 된다.
    """
    assert runledger.valid_run_id(ok)


# ── W-2 주인만 · W-10 코드 ──────────────────────────────────────────────


@pytest.fixture(scope="module")
def owned_run(client, report):
    r = client.post("/api/runs", json={"report_json": report, "slug": "w2"}, headers=ALICE)
    return r.json()["data"]["run_id"]


@pytest.mark.parametrize("suffix", [
    "", "/artifacts", "/scenes", "/revise", "/qa", "/download/pptx", "/preview/index.html",
])
def test_owned_run_is_invisible_to_others(client, owned_run, suffix):
    """남이거나 신원이 없으면 **없는 것과 같은 404** — 있는지도 알리지 않는다."""
    for headers in (BOB, {}):
        res = client.get(f"/api/runs/{owned_run}{suffix}", headers=headers)
        assert res.status_code == 404, suffix
        assert res.json().get("code") == "NOT_FOUND"


def test_owner_sees_their_own_run(client, owned_run):
    assert client.get(f"/api/runs/{owned_run}", headers=ALICE).status_code == 200


def test_ownerless_run_stays_open(client, report):
    """주인 없는 run 은 비공개가 아니다 — 이 기능이 들어간 뒤에도 영영 열려 있다."""
    rid = client.post("/api/runs", json={"report_json": report}).json()["data"]["run_id"]
    for headers in (ALICE, BOB, {}):
        assert client.get(f"/api/runs/{rid}", headers=headers).status_code == 200


# ── W-3 목록 ────────────────────────────────────────────────────────────


def test_list_shows_mine_and_ownerless(client, report, owned_run):
    free = client.post("/api/runs", json={"report_json": report}).json()["data"]["run_id"]

    def ids(headers):
        return {r["run_id"] for r in client.get("/api/runs", headers=headers).json()["data"]["runs"]}

    assert owned_run in ids(ALICE) and free in ids(ALICE)
    assert owned_run not in ids(BOB) and free in ids(BOB)
    assert owned_run not in ids({}) and free in ids({})


# ── W-7 본문 상한 · W-10 코드 어휘 ──────────────────────────────────────


def test_body_over_limit_is_413(client, report):
    res = client.post("/api/runs", json={"report_json": report},
                      headers={"Content-Length": str(runledger_max() + 1)})
    assert res.status_code == 413
    assert res.json()["code"] == "TOO_LARGE"


def runledger_max() -> int:
    from wdweb.app import MAX_BODY_BYTES

    return MAX_BODY_BYTES


def test_unknown_format_is_400_invalid(client, report):
    res = client.post("/api/runs", json={"report_json": report, "format": "nope-1x1"})
    assert res.status_code == 400
    assert res.json()["code"] == "INVALID"
    assert "wide-16x9" in res.json()["message"]      # 쓸 수 있는 꼴을 알려준다


def test_error_codes_are_from_the_agreed_vocabulary(client):
    """포털은 code 로 가른다 — 어휘 밖 값이 새면 분기가 깨진다."""
    for res in (client.get("/api/runs/wr-20200101-000000-aaaa"),
                client.post("/api/runs", json={})):
        code = res.json().get("code")
        assert code in ERROR_CODES, code


# ── W-12 끊긴 실행 ──────────────────────────────────────────────────────


def test_interrupted_runs_are_marked_failed(tmp_path, monkeypatch):
    """데몬 스레드라 프로세스가 죽으면 running 인 채 남고 재개도 거절된다 — 유령이 된다."""
    monkeypatch.setattr(runledger, "data_dir", lambda: tmp_path)
    (tmp_path / "web_runs").mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    runledger.write_run({
        "run_id": "wr-20261101-000000-abcd", "slug": "ghost", "status": "running",
        "stages": [{"stage": "build", "status": "running", "error": None, "output": None}],
        "render": {"status": "rendering", "outputs": {}}, "owner": None,
        "created_at": now, "updated_at": now,
    })
    assert runledger.mark_interrupted() == ["wr-20261101-000000-abcd"]
    run = runledger.read_run("wr-20261101-000000-abcd")
    assert run["status"] == "failed" and run["error"] == "interrupted"
    assert run["stages"][0]["status"] == "failed"
    assert run["render"]["status"] == "failed" and run["render"]["error"] == "interrupted"


# ── W-13 보존 ───────────────────────────────────────────────────────────


def test_retention_is_off_by_default():
    """기한을 기본으로 켜면 기능이 들어간 첫 기동에 몇 달치가 사라진다 — 사고다."""
    assert runledger.RETENTION_DAYS == 0
    assert runledger.sweep_retention(days=0) == []


def test_retention_sweeps_old_artifacts_and_keeps_the_ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(runledger, "data_dir", lambda: tmp_path)
    (tmp_path / "web_runs").mkdir(parents=True, exist_ok=True)
    old = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    runledger.write_run({
        "run_id": "wr-20260901-000000-aaaa", "slug": "old-aaaa", "status": "done",
        "stages": [], "owner": None, "created_at": old, "updated_at": old,
        "build_dir": str(tmp_path / "build" / "old-aaaa"), "entry": "index.html",
        "render": {"status": "done", "outputs": {"pptx": "x"}},
    })
    for rel in ("pipeline/wr-20260901-000000-aaaa", "build/old-aaaa", "renders/old-aaaa"):
        (tmp_path / rel).mkdir(parents=True, exist_ok=True)
        (tmp_path / rel / "f.txt").write_text("x", encoding="utf-8")

    assert runledger.sweep_retention(days=30) == ["wr-20260901-000000-aaaa"]
    assert not (tmp_path / "build" / "old-aaaa").exists()
    assert not (tmp_path / "renders" / "old-aaaa").exists()
    run = runledger.read_run("wr-20260901-000000-aaaa")
    assert run["deleted_at"] and run["build_dir"] is None   # 원장은 남는다 → 410 을 답할 수 있다
    assert runledger.sweep_retention(days=30) == []          # 두 번 지우지 않는다


def test_recent_runs_are_not_swept(tmp_path, monkeypatch):
    monkeypatch.setattr(runledger, "data_dir", lambda: tmp_path)
    (tmp_path / "web_runs").mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    runledger.write_run({"run_id": "wr-20261101-000000-bbbb", "slug": "new-bbbb",
                         "status": "done", "stages": [], "owner": None,
                         "created_at": now, "updated_at": now})
    assert runledger.sweep_retention(days=30) == []


# ── W-22 토큰 위생 ──────────────────────────────────────────────────────


def test_secret_headers_are_never_read():
    """Authorization 은 그 사람의 허브 토큰이다 — 읽지도 남기지도 않는다."""
    for mod in ("src/wdweb/app.py", "src/wdweb/runs.py", "src/wdweb/scenes.py"):
        src = (REPO_ROOT / mod).read_text(encoding="utf-8").lower()
        for name in SECRET_HEADERS:
            # 선언(SECRET_HEADERS 상수)은 제외하고 **읽는 코드**가 없어야 한다
            assert f'headers.get("{name}")' not in src, f"{mod}: {name} 를 읽는다"
            assert f"headers['{name}']" not in src, f"{mod}: {name} 를 읽는다"


# ── W-4 MCP 는 주인 있는 run 에 닿지 않는다 ─────────────────────────────


def test_mcp_cannot_reach_an_owned_run(client, report):
    """MCP 의 신원은 확인할 수 없다 — 게이트웨이가 상주 세션 하나로 서비스 토큰을 싣는다."""
    from wdmcp import server as mcp_server
    from wdmcp.ownership import is_owned_path, is_owned_run

    rid = client.post("/api/runs", json={"report_json": report, "slug": "w4"},
                      headers=ALICE).json()["data"]["run_id"]
    assert is_owned_run(rid)
    out = mcp_server.scene_list(run_id=rid)
    assert out["ok"] is False
    assert out["error"]["code"] == "NOT_FOUND"
    # 경로로 들어오는 도구도 같다 — run_id 를 안 받는다고 뚫리면 안 된다
    assert is_owned_path(f"data/pipeline/{rid}/scenario.json")
    assert mcp_server.qa_run(build_path=f"data/build/w4-{rid[-4:]}")["ok"] is False


def test_mcp_still_reaches_ownerless_runs(client, report):
    """MCP·CLI 로 만든 주인 없는 run 은 지금처럼 돈다 — 깨지는 것이 없어야 한다."""
    from wdmcp.ownership import is_owned_run

    rid = client.post("/api/runs", json={"report_json": report}).json()["data"]["run_id"]
    assert not is_owned_run(rid)


# ── W-6 능력 표지 ───────────────────────────────────────────────────────


def test_health_advertises_capabilities(client):
    """포털은 features 의 owner 가 없으면 단추를 숨긴다. 표지는 실제로 있는 것에서 뽑는다."""
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    for cap in ("owner", "render_chain", "doc_formats", "skipped_report",
                "interrupted", "idempotency", "error_codes"):
        assert cap in body["features"], cap
    assert body["formats"]["delib-16x9"] in ("draft", "pilot", "active")


# ── W-11 내려받기 머리 ──────────────────────────────────────────────────


def test_download_headers_are_declared_for_every_kind(tmp_path):
    """허브 앱은 포털과 같은 오리진이다 — HTML 은 sandbox 로 오리진을 떼어 낸다."""
    from wdweb.app import _DOWNLOAD_META, download_headers

    probe = tmp_path / "artifact.bin"
    probe.write_bytes(b"x" * 11)
    for kind in _DOWNLOAD_META:
        h = download_headers(probe, kind)
        assert h["X-Content-Type-Options"] == "nosniff"
        assert h["Content-Length"] == "11"
        assert ("Content-Security-Policy" in h) is (kind == "html")

    # 렌더 잡 경로는 kind 가 'video' 여도 파일이 HTML 이면 sandbox 가 붙어야 한다
    # (잡 경로는 inline 으로 내므로 브라우저가 그 오리진에서 실행한다)
    page = tmp_path / "report.html"
    page.write_text("<p>x</p>", encoding="utf-8")
    assert download_headers(page, "video")["Content-Security-Policy"] == "sandbox"
    assert "Content-Security-Policy" not in download_headers(probe, "video")


# ── W-15 멱등 키 ────────────────────────────────────────────────────────


def test_same_idempotency_key_returns_the_same_run(client, report):
    """'결과 모름' 으로 다시 보낸 요청이 run 을 둘 만들지 않는다."""
    body = {"report_json": report, "slug": "idem"}
    h = {**ALICE, "Idempotency-Key": "portal-job-42"}
    first = client.post("/api/runs", json=body, headers=h).json()["data"]["run_id"]
    second = client.post("/api/runs", json=body, headers=h).json()["data"]["run_id"]
    assert first == second
    # 주인이 다르면 남의 것이므로 못 본다 — 새 run 이 생긴다
    other = client.post("/api/runs", json=body,
                        headers={**BOB, "Idempotency-Key": "portal-job-42"})
    assert other.json()["data"]["run_id"] != first


def test_render_request_is_stored_for_the_chain(client, report):
    """W-8 — 만들기의 render 칸은 원장에 남아야 재개에서도 이어진다."""
    opts = {"targets": ["pptx"], "doc_style": "report", "pptx_mode": "hybrid", "narration": False}
    rid = client.post("/api/runs", json={"report_json": report, "render": opts},
                      headers=ALICE).json()["data"]["run_id"]
    assert runledger.read_run(rid)["render_request"] == opts


def test_render_status_vocabulary_matches_the_contract():
    """포털이 화면 낱말 하나로 접는 표 — 낱말을 바꾸면 그쪽 매핑이 깨진다."""
    src = (REPO_ROOT / "src" / "wdweb" / "runs.py").read_text(encoding="utf-8")
    for state in ("queued", "building", "rendering", "done", "failed"):
        assert f'status="{state}"' in src, state


def test_render_concurrency_is_bounded():
    """chromium 이 뜨는 작업이라 요청마다 스레드를 띄우면 박스가 먼저 죽는다(W-14)."""
    assert runledger.RENDER_CONCURRENCY >= 1
    assert runledger._render_slots is not None


# ── root_path 회귀 (2026-11-01 실사고) ──────────────────────────────────
#
# 허브는 `--root-path /apps/web_design_agents` 로 띄우고, uvicorn 은 ASGI 규격대로
# root_path 를 **포함한** 전체 경로를 scope["path"] 에 싣는다. 라우팅은 Starlette 가
# 접두를 벗겨 맞추므로 핸들러는 멀쩡하지만, 날것의 경로를 보는 미들웨어는 걸리지 않아
# 소유권 검사가 통째로 무력해진다. **TestClient 는 이걸 재현하지 못한다** — 실기동으로만
# 잡힌다. 그래서 이 테스트만 진짜 uvicorn 을 띄운다.


def test_app_path_strips_the_proxy_prefix():
    """단위 — 접두를 뗀 경로를 돌려줘야 한다."""
    from types import SimpleNamespace

    from wdweb.app import app_path

    def req(path, root):
        return SimpleNamespace(scope={"path": path, "root_path": root},
                               url=SimpleNamespace(path=path))

    assert app_path(req("/apps/web_design_agents/api/runs/x", "/apps/web_design_agents")) \
        == "/api/runs/x"
    assert app_path(req("/api/runs/x", "")) == "/api/runs/x"
    assert app_path(req("/apps/web_design_agents", "/apps/web_design_agents")) == "/"
    # 접두가 선언됐지만 경로가 이미 벗겨진 경우(프록시가 떼고 보낸 경우)도 그대로 둔다
    assert app_path(req("/api/runs/x", "/apps/web_design_agents")) == "/api/runs/x"


@pytest.mark.parametrize("root_path", ["/apps/web_design_agents", ""])
def test_ownership_holds_behind_a_proxy_prefix(client, report, root_path):
    """실기동 — 허브와 같은 조건에서 남의 run 이 404 여야 한다."""
    import socket
    import subprocess
    import sys
    import time
    import urllib.error
    import urllib.request

    rid = client.post("/api/runs", json={"report_json": report, "slug": "rp"},
                      headers=ALICE).json()["data"]["run_id"]

    with socket.socket() as s:                      # 빈 포트를 OS 에게 받는다
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    argv = [sys.executable, "-m", "uvicorn", "wdweb.app:app",
            "--host", "127.0.0.1", "--port", str(port)]
    if root_path:
        argv += ["--root-path", root_path]
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def status(who: str) -> int:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/runs/{rid}",
                                     headers={"X-Heax-User-Email": who})
        try:
            return urllib.request.urlopen(req, timeout=10).status
        except urllib.error.HTTPError as exc:
            return exc.code

    try:
        for _ in range(60):                          # 기동 대기
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        else:
            pytest.skip("uvicorn 이 뜨지 않았다")
        assert status("alice@corp.example") == 200
        assert status("bob@corp.example") == 404, (
            f"root_path={root_path!r} 에서 남의 run 이 열렸다 — 미들웨어가 날것의 경로를 본다"
        )
    finally:
        proc.terminate()
        proc.wait(timeout=20)
