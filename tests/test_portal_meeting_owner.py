# 포털 계약 M3 — 회의 · ingest 도구의 주인(W-4 가 덮지 않던 길): 확인된 신원만 주인 있는 실행 · 원본 · 회의에 닿는다
"""사용자 결정(2026-11-22, 포털 WD-D94 ② 의 (나)) — 웹(REST) 길에서 확인된 신원을 회의 · ingest 도구에 넘기고 회의에 주인 칸을 둔다.

탐침(2026-11-21)이 재현한 길 — 신원 없이 `meeting_start(run_id=<주인 있는 실행>)` 이 조각 63개를 실었고, `report_ingest(file=<그 실행의
report.raw.json>)` 이 남의 원본을 주인 없는 새 실행으로 옮겼다. 회의에는 주인이 없어 목록 · 브리핑으로 조각이 나갔고, 거꾸로 콘솔의
심의 → 시나리오는 주인 있는 실행에서 주인에게도 막혔다(도구 문이 웹 길의 신원을 몰랐다).

막힌 꼴은 **없는 것과 같다** — 남 · 신원 없음에게 주인 있는 실행 · 회의는 없는 실행 · 없는 회의와 같은 답이다(있는지도 알리지 않는다).
주인 없는 실행 · 회의는 지금 그대로 열려 있다.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wdmcp import delegation
from wdmcp import server as mcp_server
from wdweb import runs as runledger
from wdweb.app import app

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
ALICE_EMAIL, BOB_EMAIL = "alice@corp.example", "bob@corp.example"
ALICE = {"X-Heax-User-Email": ALICE_EMAIL}
BOB = {"X-Heax-User-Email": BOB_EMAIL}
SECRET = "wda-gateway-secret-for-tests-0123456789"
MISSING = "wr-20261122-000000-" + "0f" * 16          # 어디에도 없는 실행


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


@pytest.fixture(scope="module")
def report():
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def _wait(run_id: str, timeout: float = 120.0) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        run = runledger.read_run(run_id)
        if run is not None and run["status"] in ("done", "failed"):
            return run
        time.sleep(0.05)
    raise AssertionError(f"기다리다 끝났다: {run_id}")


@pytest.fixture(scope="module")
def owned(client, report):
    """alice 가 REST 로 만든(주인 있는) 끝난 실행 — 조각(fragments.json)이 있다."""
    rid = client.post("/api/runs", json={"report_json": report, "slug": "mo"}, headers=ALICE).json()["data"]["run_id"]
    run = _wait(rid)
    assert run["status"] == "done"
    return run


@pytest.fixture(scope="module")
def ownerless(client, report):
    rid = client.post("/api/runs", json={"report_json": report, "slug": "mo-free"}).json()["data"]["run_id"]
    return _wait(rid)


@pytest.fixture()
def as_mcp(monkeypatch):
    """MCP 요청의 머리를 흉내 낸다 — None 이면 확인된 신원 없음, 이메일이면 게이트웨이 위임 단언."""
    monkeypatch.setenv("WDA_GATEWAY_SECRET", SECRET)

    def use(email: str | None):
        hdr = {"x-heax-sso-assertion": delegation.mint(email, secret=SECRET)} if email else None
        monkeypatch.setattr(delegation, "_request_headers", lambda: hdr)
    return use


def _personas() -> list[str]:
    return [p["id"] for p in mcp_server.meeting_personas()["data"]["personas"]][:3]


def _start(run_id: str | None) -> dict:
    kw = {"run_id": run_id} if run_id else {}
    return mcp_server.meeting_start(topic="발표자료 장면 구성", type="design_review", participants=_personas(), **kw)


def _err(out: dict, own_id: str, other_id: str) -> tuple:
    """오류 봉투를 id 를 지운 꼴로 — 주인 있는 것과 없는 것의 답이 같은지 견준다."""
    assert out["ok"] is False
    e = out["error"]
    return e["code"], e["message"].replace(own_id, "<id>").replace(other_id, "<id>"), e.get("hint")


# ── meeting_start(run_id) — 탐침 ① ──────────────────────────────────────


@pytest.mark.parametrize("who", [None, BOB_EMAIL])
def test_meeting_start_on_an_owned_run_is_like_a_missing_run(owned, as_mcp, who):
    as_mcp(who)
    got = _start(owned["run_id"])
    want = _start(MISSING)
    assert _err(got, owned["run_id"], MISSING) == _err(want, owned["run_id"], MISSING), "있는지도 알리지 않는다"
    assert got["error"]["code"] == "RUN_NOT_FOUND"


def test_owner_opens_a_meeting_on_their_run_and_it_becomes_theirs(owned, as_mcp):
    """이 결정으로 열리는 길 — 주인이 자기 실행으로 회의를 연다. 그 회의는 그 실행의 주인 것이다."""
    as_mcp(ALICE_EMAIL)
    out = _start(owned["run_id"])
    assert out["ok"] is True and out["data"]["fragments_loaded"] > 0
    meta, _ = mcp_server._engine().store.load(out["data"]["meeting_id"])
    assert meta.owner == ALICE_EMAIL


def test_meeting_on_an_ownerless_run_stays_ownerless(ownerless, as_mcp):
    for who in (None, BOB_EMAIL):
        as_mcp(who)
        out = _start(ownerless["run_id"])
        assert out["ok"] is True
        assert mcp_server._engine().store.load(out["data"]["meeting_id"])[0].owner is None


# ── 주인 있는 회의는 그 주인에게만 — 없는 회의와 같다 ─────────────────────────


@pytest.fixture()
def alice_meeting(owned, as_mcp):
    as_mcp(ALICE_EMAIL)
    return _start(owned["run_id"])["data"]["meeting_id"]


GHOST = "00000000-0000-4000-8000-000000000000"


@pytest.mark.parametrize("call", [
    lambda m: mcp_server.meeting_status(meeting_id=m),
    lambda m: mcp_server.meeting_get_briefing(meeting_id=m),
    lambda m: mcp_server.meeting_close(meeting_id=m),
    lambda m: mcp_server.meeting_minutes(meeting_id=m),
    lambda m: mcp_server.meeting_submit_turn(meeting_id=m, round_no=0, role="moderator", content_md="x"),
    lambda m: mcp_server.scenario_build(meeting_id=m),
], ids=["status", "briefing", "close", "minutes", "submit_turn", "scenario_build"])
@pytest.mark.parametrize("who", [None, BOB_EMAIL])
def test_an_owned_meeting_is_invisible_to_others(alice_meeting, as_mcp, call, who):
    as_mcp(who)
    got, want = call(alice_meeting), call(GHOST)
    assert _err(got, alice_meeting, GHOST) == _err(want, alice_meeting, GHOST)
    assert got["session"]["meetings"] == {}, "회의 원장(연결된 실행 id · 전달 기록)도 싣지 않는다"


def test_meeting_list_shows_mine_and_ownerless_only(alice_meeting, ownerless, as_mcp):
    as_mcp(BOB_EMAIL)
    free = _start(ownerless["run_id"])["data"]["meeting_id"]

    def ids(who):
        as_mcp(who)
        return {m["id"] for m in mcp_server.meeting_list(limit=500)["data"]["meetings"]}

    assert alice_meeting in ids(ALICE_EMAIL) and free in ids(ALICE_EMAIL)
    assert alice_meeting not in ids(BOB_EMAIL) and free in ids(BOB_EMAIL)
    assert alice_meeting not in ids(None)


def test_owner_reaches_their_meeting(alice_meeting, as_mcp):
    as_mcp(ALICE_EMAIL)
    assert mcp_server.meeting_status(meeting_id=alice_meeting)["ok"] is True
    assert mcp_server.meeting_get_briefing(meeting_id=alice_meeting)["ok"] is True


def test_a_legacy_ownerless_meeting_on_an_owned_run_gives_no_fragments(owned, ownerless, as_mcp):
    """이 고침 전에 열린 회의(주인 없음 · 연결된 실행은 주인 있음) — 브리핑에 그 실행의 조각을 싣지 않고, 시나리오는 그 실행에 쓰지 않는다."""
    as_mcp(None)
    mid = _start(ownerless["run_id"])["data"]["meeting_id"]
    path = mcp_server._engine().store.find_dir(mid) / "web_ledger.json"
    led = json.loads(path.read_text(encoding="utf-8"))
    led["run_id"] = owned["run_id"]                              # 옛 회의 — 막기 전에 주인 있는 실행을 물었다
    path.write_text(json.dumps(led), encoding="utf-8")
    mcp_server.reset_services()
    from wdmcp.session import new_session
    new_session()
    brief = mcp_server.meeting_get_briefing(meeting_id=mid)
    assert brief["ok"] is True and not (brief["data"].get("facts") or []), "주인 있는 실행의 조각이 나가지 않는다"
    sb = mcp_server.scenario_build(meeting_id=mid)
    assert sb["ok"] is False and sb["error"]["code"] in ("NOT_FOUND", "RUN_NOT_FOUND")


# ── report_ingest(file) — 탐침 ② ───────────────────────────────────────


def _raw(run: dict) -> str:
    return str(runledger.data_dir() / "pipeline" / run["run_id"] / "report.raw.json")


@pytest.mark.parametrize("who", [None, BOB_EMAIL])
def test_report_ingest_of_an_owned_original_is_like_a_missing_file(owned, as_mcp, who):
    as_mcp(who)
    nowhere = str(runledger.data_dir() / "pipeline" / MISSING / "report.raw.json")
    got, want = mcp_server.report_ingest(file=_raw(owned)), mcp_server.report_ingest(file=nowhere)
    assert _err(got, owned["run_id"], MISSING) == _err(want, owned["run_id"], MISSING)
    assert got["error"]["code"] == "FILE_NOT_FOUND"


def test_path_tricks_do_not_slip_past(owned, ownerless, as_mcp):
    """`..` 로 돌아 들어가는 경로도 실제 자리로 판정한다."""
    as_mcp(None)
    sneaky = str(runledger.data_dir() / "pipeline" / ownerless["run_id"] / ".." / owned["run_id"] / "report.raw.json")
    assert mcp_server.report_ingest(file=sneaky)["error"]["code"] == "FILE_NOT_FOUND"


@pytest.mark.parametrize("who", [None, BOB_EMAIL])
def test_report_ingest_cannot_write_into_or_read_assets_of_an_owned_run(owned, ownerless, as_mcp, who):
    as_mcp(who)
    into = mcp_server.report_ingest(file=_raw(ownerless), run_id=owned["run_id"])
    assert into["ok"] is False and into["error"]["code"] == "NOT_FOUND"
    norm = runledger.data_dir() / "pipeline" / owned["run_id"] / "report.norm.json"
    assert json.loads(norm.read_text(encoding="utf-8"))["title"], "남의 실행의 정규화본을 덮지 않았다"
    assets = mcp_server.report_ingest(file=_raw(ownerless),
                                      assets_dir=str(runledger.data_dir() / "pipeline" / owned["run_id"]))
    assert assets["ok"] is False and assets["error"]["code"] == "NOT_FOUND"


def test_owner_cannot_copy_their_report_into_an_ownerless_run(owned, as_mcp):
    """주인이어도 그 원본을 주인 없는 새 실행으로 옮기지 않는다 — 옮기면 누구에게나 열린 사본이 생긴다."""
    as_mcp(ALICE_EMAIL)
    out = mcp_server.report_ingest(file=_raw(owned))
    assert out["ok"] is False and out["error"]["code"] == "OWNED_COPY"
    again = mcp_server.report_ingest(file=_raw(owned), run_id=owned["run_id"])
    assert again["ok"] is True and again["data"]["run_id"] == owned["run_id"], "자기 실행에 다시 ingest 는 된다"


def test_ownerless_ingest_is_unchanged(ownerless, as_mcp):
    as_mcp(None)
    out = mcp_server.report_ingest(file=_raw(ownerless))
    assert out["ok"] is True


# ── 웹(REST) 길 — 확인된 신원을 도구에 넘긴다 ──────────────────────────────


def test_console_owner_opens_a_meeting_and_builds_the_scenario_into_their_run(client, owned):
    """종전에는 콘솔의 심의 → 시나리오가 주인 있는 실행에서 주인에게도 막혔다(도구 문이 웹 길의 신원을 몰랐다)."""
    body = {"topic": "발표자료 장면", "type": "design_review", "participants": _personas(), "run_id": owned["run_id"]}
    res = client.post("/api/meetings", json=body, headers=ALICE)
    assert res.status_code == 201, res.text
    mid = res.json()["data"]["meeting_id"]
    assert client.get(f"/api/meetings/{mid}", headers=ALICE).status_code == 200
    sb = client.post(f"/api/meetings/{mid}/scenario", json={"run_id": owned["run_id"]}, headers=ALICE)
    assert sb.status_code != 400 or "해당 run 을 찾을 수 없다" not in sb.text, "주인의 시나리오 만들기가 막히지 않는다"


@pytest.mark.parametrize("headers", [BOB, {}])
def test_console_others_cannot_open_or_see_an_owned_meeting(client, owned, headers):
    body = {"topic": "발표자료 장면", "type": "design_review", "participants": _personas()}
    mine = client.post("/api/meetings", json={**body, "run_id": owned["run_id"]}, headers=ALICE).json()["data"]["meeting_id"]
    got = client.post("/api/meetings", json={**body, "run_id": owned["run_id"]}, headers=headers)
    want = client.post("/api/meetings", json={**body, "run_id": MISSING}, headers=headers)
    assert got.status_code == want.status_code == 400
    assert got.json()["message"].replace(owned["run_id"], "<id>") == want.json()["message"].replace(MISSING, "<id>")
    assert mine not in {m["id"] for m in client.get("/api/meetings", headers=headers).json()["data"]["meetings"]}
    for path in ("", "/briefing", "/minutes", "/autorun"):
        a, b = client.get(f"/api/meetings/{mine}{path}", headers=headers), client.get(f"/api/meetings/{GHOST}{path}", headers=headers)
        assert a.status_code == b.status_code and a.status_code in (400, 404), path
    assert client.post(f"/api/meetings/{mine}/close", headers=headers).status_code in (400, 404)


@pytest.mark.parametrize("headers", [BOB, {}])
def test_console_autorun_cannot_feed_an_owned_run(client, owned, ownerless, headers):
    """자율 심의의 run_id 는 조각을 바로 읽는다 — 남의 실행이면 없는 실행과 같은 404(종전엔 없는 실행도 받아 놓고 뒤에서 실패했다)."""
    body = {"topic": "발표자료 장면", "type": "design_review", "participants": _personas()}
    mid = client.post("/api/meetings", json={**body, "run_id": ownerless["run_id"]}, headers=headers).json()["data"]["meeting_id"]
    got = client.post(f"/api/meetings/{mid}/autorun", json={"run_id": owned["run_id"]}, headers=headers)
    want = client.post(f"/api/meetings/{mid}/autorun", json={"run_id": MISSING}, headers=headers)
    assert got.status_code == want.status_code == 404
    assert got.json()["message"].replace(owned["run_id"], "<id>") == want.json()["message"].replace(MISSING, "<id>")
    bad = client.post(f"/api/meetings/{mid}/autorun", json={"run_id": "../x"}, headers=headers)
    assert bad.status_code == 404


# ── 실기동 — 진짜 uvicorn 을 --root-path 있는/없는 두 조건으로 ──────────────────


@pytest.mark.parametrize("root_path", ["/apps/web_design_agents", ""])
def test_meeting_owner_over_real_http(owned, root_path):
    """웹 길은 미들웨어가 아니라 도구 문이 신원을 본다 — 그래도 배치와 같은 조건(--root-path)에서 확인한다.
    MCP 길(단언)도 같은 프로세스에서 본다."""
    import os
    import socket
    import subprocess
    import sys
    import urllib.error
    import urllib.request

    import anyio
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    argv = [sys.executable, "-m", "uvicorn", "wdweb.app:app", "--host", "127.0.0.1", "--port", str(port)]
    if root_path:
        argv += ["--root-path", root_path]
    proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            env={**os.environ, "WDA_GATEWAY_SECRET": SECRET})
    base = f"http://127.0.0.1:{port}"
    personas = _personas()

    def post(path: str, body: dict, headers: dict) -> tuple[int, dict]:
        req = urllib.request.Request(f"{base}{path}", method="POST", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", **headers})
        try:
            r = urllib.request.urlopen(req, timeout=30)
            return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    def get(path: str, headers: dict) -> tuple[int, dict]:
        req = urllib.request.Request(f"{base}{path}", headers=headers)
        try:
            r = urllib.request.urlopen(req, timeout=30)
            return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read() or b"{}")

    async def mcp_start(headers: dict) -> dict:
        async with streamablehttp_client(f"{base}/mcp", headers=headers) as (read, write, _sid):
            async with ClientSession(read, write) as sess:
                await sess.initialize()
                res = await sess.call_tool("meeting_start", {"topic": "장면", "type": "design_review",
                                                             "participants": personas, "run_id": owned["run_id"]})
                return json.loads(res.content[0].text)

    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(f"{base}/api/health", timeout=2)
                break
            except Exception:  # noqa: BLE001
                time.sleep(0.5)
        else:
            pytest.skip("uvicorn 이 뜨지 않았다")
        body = {"topic": "장면", "type": "design_review", "participants": personas, "run_id": owned["run_id"]}
        st, j = post("/api/meetings", body, ALICE)
        assert st == 201, j
        mid = j["data"]["meeting_id"]
        assert post("/api/meetings", body, BOB)[0] == 400, f"root_path={root_path!r} 에서 남이 주인 있는 실행으로 회의를 열었다"
        assert get(f"/api/meetings/{mid}", BOB)[0] in (400, 404)
        assert get(f"/api/meetings/{mid}", ALICE)[0] == 200
        assert mid not in {m["id"] for m in get("/api/meetings", BOB)[1]["data"]["meetings"]}
        mint = urllib.request.Request(f"{base}/api/auth/sso", method="POST", data=b"",
                                      headers={"X-Heax-Gateway-Secret": SECRET, "X-Hwax-Delegate-Email": ALICE_EMAIL})
        tok = json.loads(urllib.request.urlopen(mint, timeout=20).read())["data"]["access_token"]
        assert anyio.run(mcp_start, {})["error"]["code"] == "RUN_NOT_FOUND"
        assert anyio.run(mcp_start, {"X-Heax-User-Email": ALICE_EMAIL})["error"]["code"] == "RUN_NOT_FOUND", \
            "MCP 길의 X-Heax-User-Email 은 신원이 아니다(허브 관리자로 접힌다)"
        assert anyio.run(mcp_start, {"X-Heax-Sso-Assertion": tok})["ok"] is True
    finally:
        proc.terminate()
        proc.wait(timeout=20)
