# 웹 콘솔의 심의 창구 — MCP 도구 본체를 그대로 호출하고 회의별 원장만 파일로 영속시킨다
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wdcore.config import get_settings
from wdmcp.session import MeetingLedger, SessionState, use_session

__all__ = ["call_tool", "ledger_path", "autonomous_run"]

_LEDGER_NAME = "web_ledger.json"


def _meetings_root() -> Path:
    """MCP 엔진이 실제로 쓰는 회의 디렉터리. 직접 계산하지 않는다.

    wdweb 은 repo 루트, wdmcp 는 CWD 를 기준으로 상대경로를 푼다. 여기서 따로 계산하면
    기동 위치에 따라 원장이 회의와 다른 곳에 떨어져 known_refs 가 통째로 사라진다.
    """
    from wdmcp.server import _engine

    return Path(_engine().store.root)


def ledger_path(meeting_id: str) -> Path | None:
    """회의 디렉터리 안의 원장 파일 경로. 회의가 없으면 None."""
    from wdcore.meetings.store import MeetingStore

    try:
        return MeetingStore(_meetings_root()).find_dir(meeting_id) / _LEDGER_NAME
    except (FileNotFoundError, ValueError):
        return None


def _load(meeting_id: str) -> SessionState:
    state = SessionState()
    path = ledger_path(meeting_id)
    if path is not None and path.is_file():
        try:
            state.meetings[meeting_id] = MeetingLedger.from_dict(
                json.loads(path.read_text(encoding="utf-8"))
            )
        except ValueError:  # 손상된 원장은 빈 원장으로 되돌린다 (회의 자체는 파일이 진실)
            pass
    return state


def _save(meeting_id: str, state: SessionState) -> None:
    led = state.meetings.get(meeting_id)
    path = ledger_path(meeting_id)
    if led is None or path is None:
        return
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(led.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def call_tool(name: str, *, meeting_id: str | None = None, **kwargs) -> dict[str, Any]:
    """MCP 도구를 웹에서 호출한다 — 같은 함수, 같은 검증, 같은 산출.

    브리핑·턴 검증 로직을 웹에 복제하지 않는 이유는 하나다. 복제하는 순간 두 창구의
    심의 규칙이 갈라지고, 갈라진 쪽에서 만든 자료는 다른 쪽 기준을 통과하지 못한다.
    """
    from wdmcp import server as mcp_server

    fn = getattr(mcp_server, name, None)
    if not callable(fn):
        raise ValueError(f"알 수 없는 도구: {name}")
    # meeting_id 는 원장 키이자 대부분 도구의 인자다 — 받는 도구에만 넘긴다
    # (meeting_start·meeting_personas 는 받지 않는다).
    import inspect

    if meeting_id and "meeting_id" in inspect.signature(fn).parameters:
        kwargs.setdefault("meeting_id", meeting_id)

    # meeting_start 는 아직 meeting_id 가 없다 — 호출 후 응답의 id 로 원장을 저장한다.
    state = _load(meeting_id) if meeting_id else SessionState()
    with use_session(state):
        out = fn(**kwargs)
    mid = meeting_id or ((out.get("data") or {}).get("meeting_id") if out.get("ok") else None)
    if mid:
        _save(mid, state)
    return out


def autonomous_run(meeting_id: str, *, max_turns: int | None = None,
                   run_id: str | None = None) -> dict[str, Any]:
    """vLLM(GLM)이 전 라운드를 무인 완주한다 — 웹에는 페르소나를 연기할 사람이 없다.

    MCP 는 클라이언트(Claude)가 페르소나를 연기하지만 브라우저에는 그 주체가 없다.
    같은 엔진·같은 검증 위에 발언자만 LLM 으로 바꾼 경로다(PLAN 경로 B).
    """
    from wdcore.meetings.engine import MeetingEngine
    from wdcore.meetings.store import MeetingStore
    from wdcore.registry.registry import load_registry
    from wdllm.client import GLMClient
    from wdllm.config import load_llm_config
    from wdllm.orchestrator import Orchestrator

    store = MeetingStore(_meetings_root())
    engine = MeetingEngine(store, load_registry())
    meta, _turns = store.load(meeting_id)

    frag_path = None
    if run_id:
        p = (get_settings().data_dir / "pipeline" / run_id / "fragments.json")
        frag_path = p if p.is_file() else None

    orch = Orchestrator(engine, GLMClient(load_llm_config()), registry=engine.registry)
    result = orch.run(meta, max_turns=max_turns, run_id=run_id, fragments_path=frag_path)
    return result.model_dump(mode="json") if hasattr(result, "model_dump") else dict(result)
