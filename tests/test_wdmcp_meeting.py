# wdmcp 회의 툴 통합 테스트 — 인프로세스 MCP 클라이언트로 생성→브리핑→턴→거부→폐회 전 흐름 검증
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from wdcore.config import get_settings
from wdmcp import server
from wdmcp.envelope import meeting_closed_instructions
from wdmcp.session import new_session

REPO_ROOT = Path(__file__).resolve().parents[1]
ENVELOPE_KEYS = {"ok", "data", "session", "claude_instructions", "error"}

ST = "narr-story-architect"  # 카드 2장 보유
TY = "vis-typographer"       # 카드 없음

FRAGMENTS = [
    {
        "frag_id": f"RA-1-{i:03d}",
        "type": t,
        "text": txt,
        "source": {"page": 1, "block_id": f"b{i}"},
        "confidence": 0.9,
    }
    for i, (t, txt) in enumerate(
        [
            ("claim", "전문가 심의 플랫폼은 보고서를 소개영상으로 자동 변환한다"),
            ("evidence", "회의 엔진이 발언 순서와 인용을 결정론적으로 강제한다"),
            ("metric", "게이트 7종 통과율 95퍼센트를 목표로 한다"),
            ("case", "HWAX 소개영상 7씬을 90초로 제작한 사례가 있다"),
            ("cta", "지금 보고서를 업로드해 심의를 시작하라"),
            ("evidence", "씬 템플릿 7종이 모듈 레지스트리에 등록되어 재사용된다"),
        ],
        start=1,
    )
]


@pytest.fixture()
def mcp_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """실제 personas 로스터 + 임시 데이터 루트 + 조각 run(run-test) + 새 세션."""
    monkeypatch.setenv("WDA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("WDA_PERSONAS_ROOT", str(REPO_ROOT / "personas"))
    get_settings.cache_clear()
    server.reset_services()
    new_session()
    run_dir = tmp_path / "data" / "pipeline" / "run-test"
    run_dir.mkdir(parents=True)
    (run_dir / "fragments.json").write_text(
        json.dumps(FRAGMENTS, ensure_ascii=False), encoding="utf-8"
    )
    yield tmp_path
    get_settings.cache_clear()
    server.reset_services()


def run_mcp(scenario):
    """인프로세스 MCP 클라이언트 세션에서 async 시나리오를 실행한다."""

    async def _run():
        async with create_connected_server_and_client_session(server.mcp) as client:
            return await scenario(client)

    return asyncio.run(_run())


async def call(client, name: str, args: dict | None = None) -> dict:
    """툴을 호출해 봉투 dict를 반환한다 (structured/text 양쪽 대응)."""
    res = await client.call_tool(name, args or {})
    if res.structuredContent is not None:
        sc = res.structuredContent
        if isinstance(sc, dict) and set(sc) == {"result"}:
            sc = sc["result"]
        return sc
    return json.loads(res.content[0].text)


# ── 생성 단계 오류 경로 ───────────────────────────────────────────────


def test_meeting_start_requires_participants(mcp_env):
    async def scenario(client):
        return await call(
            client, "meeting_start", {"topic": "컨셉 도출", "type": "brainstorm", "participants": []}
        )

    res = run_mcp(scenario)
    assert set(res) == ENVELOPE_KEYS
    assert res["ok"] is False
    assert res["error"]["code"] == "PARTICIPANTS_REQUIRED"
    assert ST in res["error"]["hint"], "hint에 로스터가 안내되어야 한다"


def test_meeting_start_rejects_bad_type_and_unknown_persona(mcp_env):
    async def scenario(client):
        bad_type = await call(
            client, "meeting_start", {"topic": "t", "type": "dfmea", "participants": [ST]}
        )
        unknown = await call(
            client, "meeting_start", {"topic": "t", "type": "brainstorm", "participants": ["vis-nobody"]}
        )
        bad_run = await call(
            client,
            "meeting_start",
            {"topic": "t", "type": "brainstorm", "participants": [ST], "run_id": "run-none"},
        )
        return bad_type, unknown, bad_run

    bad_type, unknown, bad_run = run_mcp(scenario)
    assert bad_type["error"]["code"] == "INVALID_TYPE"
    assert "scenario_build" in bad_type["error"]["hint"]
    assert unknown["error"]["code"] == "PERSONA_NOT_FOUND"
    assert bad_run["error"]["code"] == "RUN_NOT_FOUND"


def test_design_review_start_instructs_still_attachment(mcp_env):
    """PLAN §5.4 — 씬(시안) 심의는 스틸 PNG 첨부 절차를 지시문에 포함해야 한다."""

    async def scenario(client):
        return await call(
            client,
            "meeting_start",
            {"topic": "시안 크리틱", "type": "design_review", "participants": [ST, TY]},
        )

    res = run_mcp(scenario)
    assert res["ok"] is True
    assert "시각 심의 절차" in res["claude_instructions"]
    assert "PNG" in res["claude_instructions"]


def test_close_instructions_route_to_render_submit():
    """시나리오 빌드 회의 폐회 지시문은 Go 후 scenario_build→render_submit 경로를 안내한다."""
    text = meeting_closed_instructions("scenario_build", decisions=1)
    assert "scenario_build" in text
    assert "render_submit" in text


# ── 전 흐름 (생성→브리핑→턴→거부→폐회) ───────────────────────────────


def test_full_meeting_flow(mcp_env):
    async def scenario(client):
        out: dict = {}
        started = await call(
            client,
            "meeting_start",
            {
                "topic": "전문가 심의 플랫폼 소개영상 컨셉",
                "type": "brainstorm",
                "participants": [ST, TY],
                "run_id": "run-test",
            },
        )
        assert started["ok"] is True, started
        assert started["data"]["fragments_loaded"] == len(FRAGMENTS)
        assert [r["name"] for r in started["data"]["rounds"]] == ["diverge", "build_on", "converge"]
        assert started["data"]["next_speaker"]["expert_id"] == ST
        assert "meeting_get_briefing" in started["claude_instructions"]
        mid = started["data"]["meeting_id"]

        # ── R0 diverge: ST→TY→ST→TY (round_robin cycles=2) ──
        b1 = await call(client, "meeting_get_briefing", {"meeting_id": mid})
        assert b1["ok"] is True
        d1 = b1["data"]
        assert d1["speaker"]["expert_id"] == ST
        assert d1["persona"]["delivery"] == "full"
        assert d1["persona"]["system_prompt"]
        assert d1["modules"]["delivery"] == "full", "모듈 축약 인덱스는 회의 최초 1회 full"
        assert any(m["id"] == "tpl.opening" for m in d1["modules"]["index"])
        assert [c["card_id"] for c in d1["cards"]] == ["ST-C-001", "ST-C-002"]
        assert d1["facts"], "run 조각이 [F#] 근거로 전달되어야 한다"
        assert d1["facts"][0]["marker"] == "[F1]"
        assert all(f["ref"].startswith("RA-1-") for f in d1["facts"])
        assert "meeting_submit_turn" in b1["claude_instructions"]
        out["first_fact_refs"] = [f["ref"] for f in d1["facts"]]

        # 차례 위반 — TY가 ST 차례에 제출
        rej = await call(
            client,
            "meeting_submit_turn",
            {
                "meeting_id": mid, "round_no": 0, "role": "expert",
                "expert_id": TY, "content_md": "새치기 발언",
            },
        )
        assert rej["ok"] is False
        assert rej["error"]["code"] == "TURN_REJECTED"
        assert "차례" in rej["error"]["message"]
        assert rej["error"]["hint"]

        t1 = await call(
            client,
            "meeting_submit_turn",
            {
                "meeting_id": mid, "round_no": 0, "role": "expert", "expert_id": ST,
                "stance": "propose", "content_md": "서사 관점 아이디어 1",
                "artifacts": [{"type": "idea", "content": "문제→해결 구조의 90초 영상"}],
            },
        )
        assert t1["ok"] is True and t1["data"]["turn_no"] == 1
        assert t1["data"]["next_speaker"]["expert_id"] == TY

        b2 = await call(client, "meeting_get_briefing", {"meeting_id": mid})
        d2 = b2["data"]
        assert d2["speaker"]["expert_id"] == TY
        assert d2["persona"]["delivery"] == "full"
        assert d2["modules"]["delivery"] == "recall", "모듈 인덱스는 2회차부터 ID recall"
        assert d2["modules"]["index"] is None
        assert d2["modules"]["module_ids"]
        assert d2["cards"] == [], "TY는 카드가 없다"
        # 조각 6개 중 5개 기전달 → 남은 1개만 신규 전달
        assert len(d2["facts"]) == len(FRAGMENTS) - len(out["first_fact_refs"])
        await call(
            client,
            "meeting_submit_turn",
            {
                "meeting_id": mid, "round_no": 0, "role": "expert", "expert_id": TY,
                "stance": "propose", "content_md": "타이포 관점 아이디어",
            },
        )

        # 같은 페르소나 두 번째 브리핑 → recall (delivered_personas full→recall 전환)
        b3 = await call(client, "meeting_get_briefing", {"meeting_id": mid})
        d3 = b3["data"]
        assert d3["speaker"]["expert_id"] == ST
        assert d3["persona"]["delivery"] == "recall"
        assert d3["persona"]["system_prompt"] is None
        assert "이미 전달" in d3["persona"]["recall"]
        assert d3["cards"] == [], "기전달 카드 본문은 재전송하지 않는다"
        assert set(d3["already_delivered_cards"]) == {"ST-C-001", "ST-C-002"}
        assert d3["facts"] == [], "조각 6개 전부 기전달"
        await call(
            client,
            "meeting_submit_turn",
            {
                "meeting_id": mid, "round_no": 0, "role": "expert", "expert_id": ST,
                "stance": "support", "content_md": "아이디어 2",
            },
        )
        await call(client, "meeting_get_briefing", {"meeting_id": mid})
        r0_last = await call(
            client,
            "meeting_submit_turn",
            {
                "meeting_id": mid, "round_no": 0, "role": "expert", "expert_id": TY,
                "stance": "support", "content_md": "아이디어 3",
            },
        )
        assert r0_last["data"]["round_no"] == 1, "diverge 2사이클 완료 → build_on 전이"

        # ── R1 build_on: ST→TY ──
        for pid in (ST, TY):
            b = await call(client, "meeting_get_briefing", {"meeting_id": mid})
            assert b["data"]["round"]["name"] == "build_on"
            assert b["data"]["speaker"]["expert_id"] == pid
            await call(
                client,
                "meeting_submit_turn",
                {
                    "meeting_id": mid, "round_no": 1, "role": "expert", "expert_id": pid,
                    "stance": "support", "content_md": f"{pid} build-on 발언",
                },
            )

        # ── R2 converge (citation_required): 모더레이터→ST→TY ──
        bm = await call(client, "meeting_get_briefing", {"meeting_id": mid})
        dm = bm["data"]
        assert dm["round"]["name"] == "converge"
        assert dm["round"]["citation_required"] is True
        assert dm["speaker"]["role"] == "moderator"
        assert dm["persona"]["delivery"] == "none"

        # 인용 필수 위반 — citations 비움
        no_cite = await call(
            client,
            "meeting_submit_turn",
            {"meeting_id": mid, "round_no": 2, "role": "moderator", "content_md": "정리 발언"},
        )
        assert no_cite["ok"] is False
        assert no_cite["error"]["code"] == "TURN_REJECTED"
        assert "인용" in no_cite["error"]["message"]

        # known_refs 밖 인용 — 지어낸 ref 거부
        fake_cite = await call(
            client,
            "meeting_submit_turn",
            {
                "meeting_id": mid, "round_no": 2, "role": "moderator",
                "content_md": "정리 발언",
                "citations": [{"ref": "RA-9-999", "quote": "없는 근거"}],
            },
        )
        assert fake_cite["ok"] is False
        assert fake_cite["error"]["code"] == "TURN_REJECTED"
        assert "RA-9-999" in fake_cite["error"]["message"]

        # 브리핑으로 전달된 ref는 수리
        ok_mod = await call(
            client,
            "meeting_submit_turn",
            {
                "meeting_id": mid, "round_no": 2, "role": "moderator",
                "content_md": "Top 후보 정리",
                "citations": [{"ref": out["first_fact_refs"][0], "quote": "심의 플랫폼"}],
            },
        )
        assert ok_mod["ok"] is True, ok_mod

        await call(client, "meeting_get_briefing", {"meeting_id": mid})
        st_final = await call(
            client,
            "meeting_submit_turn",
            {
                "meeting_id": mid, "round_no": 2, "role": "expert", "expert_id": ST,
                "stance": "accept", "content_md": "후보 평가 — 카드 근거 인용",
                "citations": [{"ref": "ST-C-001", "quote": "카드 근거"}],
                "artifacts": [{"type": "decision", "content": "core_message는 자동 변환 신뢰성"}],
            },
        )
        assert st_final["ok"] is True, "브리핑으로 전달된 카드 ID 인용은 수리되어야 한다"

        await call(client, "meeting_get_briefing", {"meeting_id": mid})
        ty_final = await call(
            client,
            "meeting_submit_turn",
            {
                "meeting_id": mid, "round_no": 2, "role": "expert", "expert_id": TY,
                "stance": "accept", "content_md": "가독성 리스크 평가",
                "citations": [{"ref": out["first_fact_refs"][1], "quote": "근거"}],
                "artifacts": [
                    {"type": "action_item", "content": "타이틀 최소 24px 확인"},
                    {"type": "open_issue", "content": "톤 후보 2안 취향 충돌"},
                ],
            },
        )
        assert ty_final["ok"] is True
        assert ty_final["data"]["next_speaker"] is None
        assert "meeting_close" in ty_final["claude_instructions"]

        # 전 라운드 종료 후 브리핑 → NO_NEXT_SPEAKER
        done = await call(client, "meeting_get_briefing", {"meeting_id": mid})
        assert done["ok"] is False
        assert done["error"]["code"] == "NO_NEXT_SPEAKER"

        status = await call(client, "meeting_status", {"meeting_id": mid})
        sd = status["data"]
        assert sd["turns_total"] == 9
        assert sd["delivered_personas"] == sorted([ST, TY])
        assert sd["known_refs_count"] == len(FRAGMENTS) + 2  # 조각 6 + ST 카드 2
        assert sd["modules_delivered"] is True
        # 봉투 session 원장에도 동일 요약이 실린다
        assert status["session"]["meetings"][mid]["known_refs_count"] == len(FRAGMENTS) + 2

        closed = await call(client, "meeting_close", {"meeting_id": mid})
        assert closed["ok"] is True
        cd = closed["data"]
        assert cd["status"] == "closed"
        assert cd["decisions"] == 1 and cd["action_items"] == 1 and cd["open_issues"] == 1
        minutes = Path(cd["minutes_path"])
        assert minutes.is_file(), "폐회 후 minutes.md가 존재해야 한다"
        assert "회의" in minutes.read_text(encoding="utf-8")

        again = await call(client, "meeting_close", {"meeting_id": mid})
        assert again["error"]["code"] == "ALREADY_CLOSED"
        after = await call(
            client,
            "meeting_submit_turn",
            {"meeting_id": mid, "round_no": 2, "role": "expert", "expert_id": ST, "content_md": "지각 발언"},
        )
        assert after["error"]["code"] == "TURN_REJECTED"
        return True

    assert run_mcp(scenario) is True


def test_unknown_meeting_id_everywhere(mcp_env):
    async def scenario(client):
        results = []
        for name, args in [
            ("meeting_get_briefing", {"meeting_id": "no-such-id"}),
            ("meeting_status", {"meeting_id": "no-such-id"}),
            ("meeting_close", {"meeting_id": "no-such-id"}),
            (
                "meeting_submit_turn",
                {"meeting_id": "no-such-id", "round_no": 0, "role": "expert", "content_md": "x"},
            ),
        ]:
            results.append(await call(client, name, args))
        return results

    for res in run_mcp(scenario):
        assert res["ok"] is False
        assert res["error"]["code"] == "NOT_FOUND"
