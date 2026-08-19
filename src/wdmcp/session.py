# wdmcp 세션 원장 — 회의별 known_refs 인용 화이트리스트와 페르소나/카드/조각/모듈 델타 전달 기록
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .schemas import MeetingLedgerSummary, SessionSummary


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class MeetingLedger:
    """회의 1건에 대한 클라이언트 전달 상태. stdio 프로세스 수명 동안 유지된다.

    known_refs는 브리핑으로 실제 전달한 카드 ID/조각(frag_id) ID의 집합이며,
    엔진 submit_turn의 환각 인용 차단(citations.ref 실존 검증)에 그대로 쓰인다.
    delivered_personas/delivered_modules 원장은 full→recall 델타 전달(토큰 최소화,
    PLAN §6.3)의 근거다 — 같은 회의에서 같은 전문을 반복 전송하지 않는다.
    """

    run_id: str | None = None  # meeting_start에 연결된 파이프라인 run (조각 화이트리스트 원천)
    delivered_personas: set[str] = field(default_factory=set)
    delivered_cards: set[str] = field(default_factory=set)
    delivered_fragments: set[str] = field(default_factory=set)
    modules_delivered: bool = False  # 모듈 축약 인덱스는 회의당 최초 1회만 full
    known_refs: set[str] = field(default_factory=set)
    fact_counter: int = 0  # 이 회의의 [F#] 연번

    def next_fact_markers(self, n: int) -> list[str]:
        """[F#] 마커를 회의 전역 연번으로 n개 발급한다."""
        markers = [f"[F{self.fact_counter + i + 1}]" for i in range(n)]
        self.fact_counter += n
        return markers

    def summary(self) -> MeetingLedgerSummary:
        return MeetingLedgerSummary(
            run_id=self.run_id,
            delivered_personas=sorted(self.delivered_personas),
            delivered_cards=len(self.delivered_cards),
            delivered_fragments=len(self.delivered_fragments),
            modules_delivered=self.modules_delivered,
            known_refs_count=len(self.known_refs),
            fact_counter=self.fact_counter,
        )


@dataclass
class SessionState:
    """stdio 프로세스 1개 = 세션 1개. 회의 파일(store)이 진실이고 이 원장은 전달 기록만 담당한다."""

    session_id: str = field(default_factory=lambda: f"s-{uuid.uuid4().hex[:8]}")
    started_at: str = field(default_factory=_now_iso)
    meetings: dict[str, MeetingLedger] = field(default_factory=dict)

    def ledger(self, meeting_id: str) -> MeetingLedger:
        """회의 id별 원장을 반환한다 (없으면 생성)."""
        return self.meetings.setdefault(meeting_id, MeetingLedger())

    def summary(self, meeting_id: str | None = None) -> SessionSummary:
        """envelope session 필드용 요약. meeting_id 를 주면 그 회의만 싣는다.

        ⚠ 종전에는 모든 응답이 **이 프로세스의 전체 회의 목록**을 실었다. 그리고 이 앱은
        transport: streamable_http 로 한 프로세스가 전원을 받는다. 게이트웨이는 백엔드마다
        영속 세션 하나를 열고 전 사용자를 그 위에 다중화하므로(gateway.py _Backend.run —
        연결 생성 시 헤더가 한 번 정해지고 세션은 하나다), 앱 쪽에서 호출자를 구분할 방법이
        아예 없다. 실측으로 서로 다른 PAT 의 두 사용자가 같은 session_id 를 받고 서로의
        회의를 봤다.

        식별이 불가능하니 격리가 아니라 **비공개**로 푼다 — 묻지 않은 회의는 싣지 않는다.
        회의 본문은 원래도 meeting_id 를 알아야 접근할 수 있었으므로 잃는 기능이 없다.
        """
        if meeting_id is None:
            return SessionSummary(session_id=self.session_id, started_at=self.started_at,
                                  meetings={})
        led = self.meetings.get(meeting_id)
        return SessionSummary(
            session_id=self.session_id,
            started_at=self.started_at,
            meetings={meeting_id: led.summary()} if led is not None else {},
        )


# ── 브리핑 [F#] fact 포맷 ────────────────────────────────────────────────
#
# fragmentize 는 구조 위젯(표/흐름도/진행률/일정/키값)의 대표 조각 text 를
# `"{한 줄 요약}{_SUMMARY_JOIN}{평탄화 본문}"` 으로 만든다. 브리핑은 그 요약을
# 별도 필드로 끌어올려 페르소나가 "표 4열×7행 / 흐름도 6노드 / 진행률 7계열" 을
# 한눈에 보고 씬 템플릿(dataviz·timeline·process…)을 고르게 한다.
_SUMMARY_JOIN = " — "


def split_fact_structure(frag: dict) -> tuple[str, str]:
    """조각 → (구조 요약 한 줄, 요약을 뗀 본문 텍스트).

    조각에 `structured` payload 가 없거나 요약을 만들 수 없으면 `("", 원문)` 이다.
    **원 데이터(rows·nodes·values)는 절대 싣지 않는다** — 브리핑 토큰 예산 때문에
    한 줄 요약만 올리고, 구조 본체는 fragments.json 에 남아 씬 조립이 직접 읽는다.
    """
    text = str(frag.get("text", ""))
    payload = frag.get("structured")
    if not isinstance(payload, dict):
        return "", text
    try:
        from wdpipeline.widgets import structured_summary
    except ImportError:  # 파이프라인 없이도 브리핑은 텍스트만으로 동작해야 한다
        return "", text
    summary = structured_summary(payload)
    if not summary:
        return "", text
    if not text.startswith(summary):
        # 요약이 200자 상한에 잘렸거나 text 를 다른 경로로 만든 조각 — 원문을 그대로 둔다
        return summary, text
    body = text[len(summary):]
    if body.startswith(_SUMMARY_JOIN):
        body = body[len(_SUMMARY_JOIN):]
    return summary, body.strip()


_state = SessionState()


# 호출자별 세션 상태. 키는 아래 _session_key() 가 정한다.
_sessions: "dict[str, SessionState]" = {}
_SESSIONS_MAX = 256          # 폭주 방지 — 넘으면 가장 오래된 것부터 버린다


def _session_key() -> str | None:
    """이 요청의 호출자 식별자. 못 정하면 None(= 프로세스 단일 세션으로 폴백).

    ⚠ 이 파일은 원래 "stdio 프로세스 1개 = 세션 1개" 를 전제로 썼다. 그 전제에서는
    프로세스 싱글턴이 맞다. 그런데 지금은 매니페스트가 transport: streamable_http 라
    **한 프로세스가 전원을 받는다.** 그래서 전제가 깨졌고, 실측으로 완전히 새 MCP
    세션에서 남이 만든 회의 목록이 그대로 보였다(envelope 의 session.meetings).
    회의 본문은 meeting_id 로 접근하니 내용까지 새지는 않지만, 누가 무슨 회의를 열었는지가
    전원에게 노출된다.

    키 우선순위.
      1) 게이트웨이가 넣어 주는 x-hwax-user — 검증된 PAT 의 이메일이다(위조본은 게이트웨이가
         버린다). 재접속해도 같은 사람이면 같은 세션이라 이게 가장 자연스럽다.
      2) MCP ServerSession 객체 id — 헤더가 없는 직결 http 클라이언트용. 연결 단위로 갈린다.
      3) None — stdio. 원래 전제가 그대로 성립하므로 싱글턴을 쓴다.
    """
    try:
        from mcp.server.fastmcp import FastMCP  # noqa: F401  (지연 import — 순환 회피)
        from .server import mcp as _mcp
        ctx = _mcp.get_context()
        rc = getattr(ctx, "request_context", None)
        if rc is None:
            return None
        req = getattr(rc, "request", None)
        if req is not None:
            user = (getattr(req, "headers", {}) or {}).get("x-hwax-user")
            if user:
                return f"u:{user.strip().lower()}"
        sess = getattr(rc, "session", None)
        if sess is not None:
            return f"s:{id(sess)}"
    except Exception:  # noqa: BLE001 — 식별 실패가 도구를 죽이면 안 된다
        return None
    return None


def get_session() -> SessionState:
    """이 호출자의 세션 상태를 반환한다(없으면 생성)."""
    key = _session_key()
    if key is None:
        return _state
    st = _sessions.get(key)
    if st is None:
        if len(_sessions) >= _SESSIONS_MAX:
            _sessions.pop(next(iter(_sessions)), None)
        st = SessionState()
        _sessions[key] = st
    return st


def new_session() -> SessionState:
    """세션을 새 인스턴스로 교체한다 (테스트용)."""
    global _state
    _state = SessionState()
    _sessions.clear()
    return _state
