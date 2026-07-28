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

    def summary(self) -> SessionSummary:
        """envelope session 필드용 요약."""
        return SessionSummary(
            session_id=self.session_id,
            started_at=self.started_at,
            meetings={mid: led.summary() for mid, led in sorted(self.meetings.items())},
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


def get_session() -> SessionState:
    """프로세스 단일 세션 상태를 반환한다."""
    return _state


def new_session() -> SessionState:
    """세션을 새 인스턴스로 교체한다 (테스트용)."""
    global _state
    _state = SessionState()
    return _state
