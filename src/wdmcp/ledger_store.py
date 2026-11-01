# 회의 원장(known_refs·전달 기록)의 디스크 영속화 — MCP·웹 두 창구의 공용 집
#
# 원장은 본래 "stdio 프로세스 1개 = 회의 1개" 전제로 메모리에만 있었다. 그 전제가 깨진
# 자리가 둘이다. 웹은 요청마다 프로세스가 이어지지 않고, MCP 도 서버가 재기동하면 원장이
# 사라진다. 원장이 비면 **브리핑으로 분명히 전달한 근거를 인용해도 환각으로 거부된다** —
# 회의 본문은 디스크에 있는데 인용 화이트리스트만 사라지므로 그 회의는 인용 필수 라운드를
# 더 진행할 수 없다(delib-16x9 제작 심의 F-TD-2 · C-7, 2026-11-01 실측).
from __future__ import annotations

import json
from pathlib import Path

from .session import MeetingLedger, SessionState

__all__ = ["ledger_path", "hydrate", "persist"]

_LEDGER_NAME = "web_ledger.json"   # 이름은 웹이 먼저 썼다 — 호환을 위해 유지한다


def _meetings_root() -> Path:
    """MCP 엔진이 실제로 쓰는 회의 디렉터리. 직접 계산하지 않는다.

    wdweb 은 repo 루트, wdmcp 는 CWD 를 기준으로 상대경로를 푼다. 여기서 따로 계산하면
    기동 위치에 따라 원장이 회의와 다른 곳에 떨어져 known_refs 가 통째로 사라진다.
    """
    from .server import _engine

    return Path(_engine().store.root)


def ledger_path(meeting_id: str) -> Path | None:
    """회의 디렉터리 안의 원장 파일 경로. 회의가 없으면 None."""
    from wdcore.meetings.store import MeetingStore

    try:
        return MeetingStore(_meetings_root()).find_dir(meeting_id) / _LEDGER_NAME
    except (FileNotFoundError, ValueError):
        return None


def hydrate(state: SessionState, meeting_id: str) -> None:
    """디스크의 원장을 세션에 되살린다 — 메모리 쪽이 이미 알고 있으면 건드리지 않는다.

    메모리를 우선하는 이유: 같은 프로세스가 진행 중인 회의는 디스크보다 앞서 있다.
    디스크는 **잃어버린 뒤 되찾는 길**이지 매 호출의 진실이 아니다.
    """
    if meeting_id in state.meetings:
        return
    path = ledger_path(meeting_id)
    if path is None or not path.is_file():
        return
    try:
        state.meetings[meeting_id] = MeetingLedger.from_dict(
            json.loads(path.read_text(encoding="utf-8"))
        )
    except ValueError:  # 손상된 원장은 빈 원장으로 되돌린다 (회의 자체는 파일이 진실)
        pass


def persist(state: SessionState, meeting_id: str) -> None:
    """세션의 원장을 회의 디렉터리에 저장한다 (원자적 교체)."""
    led = state.meetings.get(meeting_id)
    path = ledger_path(meeting_id)
    if led is None or path is None:
        return
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(led.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
