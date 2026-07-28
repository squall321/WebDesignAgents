# wdmcp stdio 통합 테스트 — 서브프로세스로 서버를 기동해 initialize·툴 15종 노출·봉투 계약 검증
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parents[1]

EXPECTED_TOOLS = {
    "meeting_start",
    "meeting_get_briefing",
    "meeting_submit_turn",
    "meeting_status",
    "meeting_close",
    "report_ingest",
    "report_fragmentize",
    "scenario_build",
    "render_submit",
    "render_status",
    "qa_run",
    # 씬 툴 4종 — 핀포인트 수정 (PLAN §5.9)
    "scene_list",
    "scene_html",
    "scene_still",
    "scenario_patch",
}


def test_stdio_server_lists_15_tools_and_returns_envelope(tmp_path: Path):
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "wdmcp.server"],
        env={
            **os.environ,
            "WDA_DATA_DIR": str(tmp_path / "data"),
            "WDA_PERSONAS_ROOT": str(REPO_ROOT / "personas"),
        },
        cwd=str(REPO_ROOT),
    )

    async def scenario():
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                init = await session.initialize()
                assert init.serverInfo.name == "webdesignagents"

                tools = await session.list_tools()
                names = {t.name for t in tools.tools}
                assert names == EXPECTED_TOOLS, f"툴 15종 정확 노출 실패: {sorted(names)}"

                # participants 미명시 → 오류 봉투 (예외 전파가 아니라 구조화 응답)
                res = await session.call_tool(
                    "meeting_start",
                    {"topic": "stdio 스모크", "type": "brainstorm", "participants": []},
                )
                payload = res.structuredContent or json.loads(res.content[0].text)
                if isinstance(payload, dict) and set(payload) == {"result"}:
                    payload = payload["result"]
                assert set(payload) == {"ok", "data", "session", "claude_instructions", "error"}
                assert payload["ok"] is False
                assert payload["error"]["code"] == "PARTICIPANTS_REQUIRED"

                # 정상 생성도 stdio로 1회 확인
                ok = await session.call_tool(
                    "meeting_start",
                    {
                        "topic": "stdio 스모크",
                        "type": "brainstorm",
                        "participants": ["narr-story-architect", "vis-typographer"],
                    },
                )
                ok_payload = ok.structuredContent or json.loads(ok.content[0].text)
                if isinstance(ok_payload, dict) and set(ok_payload) == {"result"}:
                    ok_payload = ok_payload["result"]
                assert ok_payload["ok"] is True
                assert ok_payload["data"]["next_speaker"]["expert_id"] == "narr-story-architect"

    asyncio.run(scenario())
