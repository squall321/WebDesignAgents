# 웹 콘솔의 심의 창구 — MCP 도구 본체를 그대로 호출하고 회의별 원장만 파일로 영속시킨다
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from wdcore.config import get_settings
from wdmcp.session import MeetingLedger, SessionState, use_session

__all__ = ["call_tool", "ledger_path", "start_autorun", "autorun_state"]

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


# ── 자율 심의 (백그라운드) ──────────────────────────────────────────────────
#
# 전 라운드 완주는 LLM 턴이 수십 번이다. 동기 요청으로 돌리면 프록시·브라우저
# 타임아웃에 먼저 걸린다 — 렌더 잡과 같은 방식(파일이 진실 + 폴링)으로 뺀다.

_AUTORUN_NAME = "autorun.json"
_autorun_lock = threading.Lock()


def _autorun_path(meeting_id: str) -> Path | None:
    from wdcore.meetings.store import MeetingStore

    try:
        return MeetingStore(_meetings_root()).find_dir(meeting_id) / _AUTORUN_NAME
    except (FileNotFoundError, ValueError):
        return None


def autorun_state(meeting_id: str) -> dict[str, Any] | None:
    path = _autorun_path(meeting_id)
    if path is None or not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def _write_autorun(meeting_id: str, **fields) -> dict[str, Any]:
    with _autorun_lock:
        path = _autorun_path(meeting_id)
        if path is None:
            raise FileNotFoundError(f"회의를 찾을 수 없다: {meeting_id}")
        state = autorun_state(meeting_id) or {"meeting_id": meeting_id}
        state.update(fields)
        state["updated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
        return state


def start_autorun(meeting_id: str, *, max_turns: int | None = None,
                  run_id: str | None = None) -> dict[str, Any]:
    """무인 완주를 백그라운드 스레드로 시작하고 초기 상태를 반환한다."""
    cur = autorun_state(meeting_id)
    if cur and cur.get("status") == "running":
        raise RuntimeError("이미 자율 실행이 진행 중입니다")
    state = _write_autorun(meeting_id, status="running", error=None, result=None,
                           started_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
    threading.Thread(
        target=_run_autorun, args=(meeting_id, max_turns, run_id), daemon=True,
        name=f"wdweb-autorun-{meeting_id[:8]}",
    ).start()
    return state


def _run_autorun(meeting_id: str, max_turns: int | None, run_id: str | None) -> None:
    try:
        result = _autonomous_run(meeting_id, max_turns=max_turns, run_id=run_id)
        _write_autorun(meeting_id, status="done", result=result)
    except Exception as exc:  # noqa: BLE001 — 어떤 실패든 상태 파일에 남긴다
        try:
            _write_autorun(meeting_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        except Exception:
            pass


def _autonomous_run(meeting_id: str, *, max_turns: int | None = None,
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
    from wdllm.orchestrator import AutoOrchestrator

    store = MeetingStore(_meetings_root())
    engine = MeetingEngine(store, load_registry())
    meta, _turns = store.load(meeting_id)

    frag_path = None
    if run_id:
        p = (get_settings().data_dir / "pipeline" / run_id / "fragments.json")
        frag_path = p if p.is_file() else None

    orch = AutoOrchestrator(engine, GLMClient(load_llm_config()), registry=engine.registry)
    result = orch.run(meta, max_turns=max_turns, run_id=run_id, fragments_path=frag_path)
    return _as_json(result)


def _as_json(result: Any) -> dict[str, Any]:
    """RunResult 는 데이터클래스다 — dict() 로 감싸면 TypeError 가 난다(실측).

    minutes_path 는 Path 라 asdict 만으로는 여전히 JSON 이 안 된다 — default=str 로 굽는다.
    """
    import dataclasses

    if dataclasses.is_dataclass(result) and not isinstance(result, type):
        return json.loads(json.dumps(dataclasses.asdict(result), default=str))
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return dict(result)
