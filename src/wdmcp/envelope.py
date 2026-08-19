# 모든 wdmcp 툴이 공유하는 반환 봉투(ok/data/session/claude_instructions/error)와 상황별 지시문
from __future__ import annotations

from .schemas import Envelope, ErrorInfo, NextSpeakerInfo
from .session import SessionState


def ok_envelope(state: SessionState, data: dict, instructions: str,
                meeting_id: str | None = None) -> dict:
    """정상 응답 봉투."""
    return Envelope(
        ok=True, data=data, session=state.summary(meeting_id), claude_instructions=instructions, error=None,
    ).model_dump(mode="json")


def error_envelope(state: SessionState, code: str, message: str, hint: str = "",
                   meeting_id: str | None = None) -> dict:
    """오류 응답 봉투. MCP 예외 전파 대신 항상 구조화해 반환한다."""
    return Envelope(
        ok=False,
        data=None,
        session=state.summary(meeting_id),
        claude_instructions="오류 내용을 사용자에게 한국어로 알리고, hint가 있으면 함께 전하라.",
        error=ErrorInfo(code=code, message=message, hint=hint),
    ).model_dump(mode="json")


# ── 회의(클라이언트 구동 모드) 지시문 — ExpertAgents 04 §5.5 행동 규약 계승 ──

MEETING_RULES = (
    "[회의 진행 규약] 당신이 모더레이터 겸 각 참가 페르소나를 연기한다. "
    "1) 매 턴 meeting_get_briefing으로 서버가 지정한 발언자의 브리핑을 받고, "
    "브리핑의 페르소나로 발언을 생성하라. "
    "2) 생성한 발언은 반드시 meeting_submit_turn으로 제출하라. "
    "발언 순서를 임의로 바꾸거나 라운드를 건너뛰지 마라. "
    "3) citations의 ref에는 브리핑으로 전달된 카드 ID/조각(frag) ID만 사용하라. "
    "인용 없는 기술 주장 금지 — 기억나는 지식이라도 브리핑에 없는 출처를 지어내지 마라. "
    "4) 씬 양식은 모듈 축약 인덱스의 기존 템플릿(tpl.*)을 우선 재사용하고, "
    "in_scope로 소화 불가할 때만 신규 창작을 제안하라. "
    "5) 이견은 뭉개지 말고 stance='rebut'으로 드러내라. 합의를 서두르지 마라. "
    "6) 사용자가 개입하면 role='user' 턴으로 먼저 기록한 뒤 진행을 계속하라. "
    "7) 다음 발언자가 없다고 안내되면 meeting_close를 호출해 회의록을 생성하라."
)

# 씬(시안) 심의 시각 채널 절차 — PLAN §5.4 경로 A
STILL_REVIEW_PROCEDURE = (
    "[시각 심의 절차] 이 회의는 렌더 결과를 심의한다. 발언을 작성하기 전에 "
    "render_status의 outputs 경로(또는 data/renders/ 아래 스틸 PNG)를 Read 도구로 열어 "
    "실제 화면을 눈으로 확인하고, 그 이미지를 대화에 첨부한 상태에서 관찰 사실을 근거로 발언하라. "
    "이미지를 열지 못했으면 그 사실을 발언에 명시하고 추측 심의를 하지 마라."
)

INSTR_STATUS = "회의 진행 현황이다. 사용자에게 필요한 항목만 간결히 전하라."


def meeting_started_instructions(meeting_type: str) -> str:
    head = MEETING_RULES + " 먼저 meeting_get_briefing으로 첫 발언자의 브리핑을 받아라."
    if meeting_type in ("design_review", "module_review"):
        head += " " + STILL_REVIEW_PROCEDURE
    return head


def briefing_instructions(
    role: str,
    name_ko: str | None,
    expert_id: str | None,
    round_no: int,
    first_delivery: bool,
    meeting_type: str,
    citation_required: bool,
) -> str:
    """meeting_get_briefing 응답용 지시문 — 발언자 역할·페르소나 전달 모드·회의 유형에 따라 달라진다."""
    if role == "moderator":
        body = (
            "지금은 모더레이터 차례다. 라운드 지시에 따라 참가자 발언의 요약·군집화·중재 발언을 작성하고 "
            f"meeting_submit_turn(round_no={round_no}, role='moderator')으로 제출하라. "
            "모더레이터는 새 기술 주장을 만들지 않는다. 인용이 필요하면 참가자들이 이미 인용한 ref만 재인용하라."
        )
    else:
        head = (
            f"지금부터 persona.system_prompt의 페르소나 '{name_ko}'로서 발언을 생성하라."
            if first_delivery
            else f"'{name_ko}' 페르소나는 이 회의에서 이미 전달되었다. 그 페르소나를 유지한 채 발언을 생성하라."
        )
        body = (
            f"{head} 라운드 지시와 recent_turns의 논점을 반영하고, 생성한 발언은 반드시 "
            f"meeting_submit_turn(round_no={round_no}, role='expert', expert_id='{expert_id}')으로 제출하라. "
            "인용 없는 기술 주장 금지 — 수치·주장에는 cards/facts의 ref를 citations로 인용하라."
        )
        if citation_required:
            body += " 이 라운드는 citations가 비어 있으면 거부된다."
    if meeting_type in ("design_review", "module_review"):
        body += " " + STILL_REVIEW_PROCEDURE
    return body


def turn_accepted_instructions(next_speaker: NextSpeakerInfo | None) -> str:
    """meeting_submit_turn 성공 응답용 지시문 — 다음 발언자 유무로 갈린다."""
    if next_speaker is None:
        return "턴이 기록되었고 모든 라운드가 끝났다. meeting_close를 호출해 회의록을 생성하라."
    who = next_speaker.expert_id or "모더레이터"
    return f"턴이 기록되었다. 다음 발언자는 {who}다. meeting_get_briefing으로 브리핑을 받아 발언을 이어가라."


def meeting_closed_instructions(meeting_type: str, decisions: int) -> str:
    base = (
        "회의가 폐회되고 회의록이 저장되었다. minutes_path를 안내하고 "
        "결론·액션아이템 중심으로 사용자에게 한국어로 요약 보고하라."
    )
    if meeting_type == "scenario_build":
        base += (
            " 이 회의는 시나리오 빌드 심의다. 판정이 Go/Conditional-Go면 사용자 확정(HITL)을 받은 뒤 "
            "scenario_build 툴로 ScenarioDoc을 조립·검증하고, 통과하면 render_submit으로 렌더 잡을 등록하라. "
            "Conditional-Go의 조건 액션아이템은 이행 확인 후 진행하라."
        )
    elif meeting_type in ("design_review", "module_review"):
        base += (
            " 판정이 Go면 render_submit으로 최종 렌더 잡을 등록하거나 다음 단계로 진행하고, "
            "Conditional-Go면 조건 액션아이템 이행 후 재심의를 소집하라."
        )
    if decisions == 0:
        base += " decision 산출물이 없다 — 판정 없이 닫혔음을 사용자에게 알려라."
    return base


# ── 파이프라인·렌더·QA 지시문 ─────────────────────────────────────────

INSTR_INGESTED = (
    "보고서가 정규화되어 저장되었다. 이어서 report_fragmentize(run_id=...)를 호출해 "
    "Claim/Evidence/Case/Metric/CTA 조각으로 분해하라."
)

INSTR_FRAGMENTIZED = (
    "조각 분해가 완료되었다. 이 run_id를 meeting_start(run_id=...)에 넘기면 frag_id들이 "
    "회의 브리핑의 [F#] 근거이자 인용 화이트리스트(known_refs)가 된다. "
    "participants는 personas 로스터에서 5~8인을 명시해야 한다."
)


def scenario_built_instructions(errors: list[str]) -> str:
    if errors:
        return (
            "시나리오 검증에서 오류가 발견되었다. validation_errors를 사용자에게 보이고, "
            "회의 산출물(scenario_patch)이나 데이터(content)를 수정해 scenario_build를 다시 호출하라. "
            "오류가 남은 채로 render_submit을 호출하지 마라."
        )
    return (
        "ScenarioDoc이 조립·검증되었다. 사용자에게 씬 구성과 core_message를 요약 보고하고 "
        "확정(HITL)을 받은 뒤 render_submit(scenario_path=...)으로 렌더 잡을 등록하라."
    )


def render_submitted_instructions(job_id: str) -> str:
    return (
        f"렌더 잡 {job_id}이(가) 등록되었다. render_status(job_id=...)로 상태를 폴링하라. "
        "완료(done) 후 outputs의 산출물 경로를 사용자에게 안내하고, 시안 심의가 필요하면 "
        "design_review 회의를 열어 스틸 PNG를 첨부해 심의하라."
    )


def render_status_instructions(status: str) -> str:
    if status in ("queued", "building", "rendering"):
        return "잡이 아직 진행 중이다. 잠시 후 render_status를 다시 호출해 폴링하라."
    if status == "failed":
        return "렌더 잡이 실패했다. error를 사용자에게 한국어로 설명하고 수정 방향을 제안하라. 성공했다고 말하지 마라."
    return (
        "렌더가 완료되었다. **urls의 열람 링크를 마크다운 링크로 제시하라** "
        "(예: `[영상 보기](urls.video)`, `[PPTX 내려받기](urls.pptx)`) — 포털 챗은 영상 링크를 "
        "인라인 플레이어로 렌더하므로 사용자가 그 자리에서 재생할 수 있다. outputs의 파일 경로는 "
        "참고용으로만 덧붙이고, 경로만 알려주고 끝내지 마라. "
        "시안 심의가 필요하면 design_review 회의를 열고, 스틸 PNG를 Read 도구로 열어 첨부한 뒤 심의하라. "
        "품질 확인이 필요하면 qa_run(build_path=...)을 호출하라."
    )


def qa_instructions(passed: bool) -> str:
    if passed:
        return "품질 게이트를 전부 통과했다. 결과를 요약 보고하라. 이 리포트는 이후 심의의 인용 근거가 된다."
    return (
        "품질 게이트 위반이 있다. results를 심각도순으로 사용자에게 보이고 수정 방향을 제안하라. "
        "위반이 남은 산출물을 출하 승인하지 마라."
    )
