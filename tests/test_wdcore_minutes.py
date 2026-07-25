# 회의록 렌더러 검증 — 집계형 섹션 렌더와 미응답 반박 자동 추출 (합의 연출 방지)
from __future__ import annotations

from wdcore.meetings import render_minutes
from wdcore.meetings.minutes import _open_issues
from wdcore.models import (
    Artifact,
    ArtifactType,
    Citation,
    MeetingMeta,
    MeetingTurn,
    SpeakerRole,
)

P1 = "impl-technical-director"
P2 = "ux-accessibility"
NAMES = {P1: "테크니컬 디렉터", P2: "접근성 전문가"}


def _meta(**over):
    base = dict(
        id="12345678-abcd-abcd-abcd-1234567890ab",
        type="scenario_build",
        topic="소개영상 시나리오",
        participants=[P1, P2],
    )
    base.update(over)
    return MeetingMeta.model_validate(base)


def _turn(turn_no, round_no, expert_id, stance=None, content="발언", citations=None, artifacts=None,
          role=SpeakerRole.expert):
    return MeetingTurn(
        turn_no=turn_no, round_no=round_no, role=role, expert_id=expert_id,
        stance=stance, content_md=content, citations=citations or [], artifacts=artifacts or [],
    )


def test_render_minutes_aggregates_artifacts_and_citations():
    turns = [
        _turn(1, 0, None, role=SpeakerRole.moderator, content="구조 초안 대독"),
        _turn(
            2, 1, P1, stance="concern", content="씬 12는 엔진 계약을 위반한다",
            citations=[Citation(ref="TD-R-001", quote="dur는 (0,300]")],
            artifacts=[Artifact(type=ArtifactType.finding, content="dur 초과 씬 존재")],
        ),
        _turn(
            3, 1, P2, stance="summarize", content="타임라인 확정",
            citations=[Citation(ref="TD-R-001")],
            artifacts=[
                Artifact(type=ArtifactType.decision, content="시나리오 v1 Go 판정"),
                Artifact(type=ArtifactType.action_item, content="씬 12 dur 재조정", owner_expert_id=P1),
                Artifact(type=ArtifactType.open_issue, content="톤 취향 충돌은 미봉합"),
            ],
        ),
    ]
    md = render_minutes(_meta(), turns, NAMES)
    # 헤더·참가자
    assert "# [회의록] 소개영상 시나리오" in md
    assert "시나리오 빌드" in md
    assert f"| {P1} | {NAMES[P1]} |" in md
    # 라운드 이름은 템플릿에서 온다
    assert "### R1 structure_diverge" in md
    assert "### R2 cross_rebuttal" in md
    # 결론(decision 집계)·액션아이템·인용 dedupe
    assert "- 시나리오 v1 Go 판정 (턴 #3)" in md
    assert "| 1 | 씬 12 dur 재조정 | impl-technical-director | #3 |" in md
    assert "| 1 | TD-R-001 | #2, #3 |" in md
    # open_issue 산출물이 미해결 쟁점에 나온다
    assert "톤 취향 충돌은 미봉합 (턴 #3)" in md


def test_unanswered_rebut_extracted_as_open_issue():
    """rebut 이후 타 발언자의 accept가 없으면 [미응답 반박]으로 추출된다."""
    turns = [
        _turn(1, 1, P1, stance="rebut", content="대비비 4.5:1 미달 — 이 팔레트는 불가"),
        _turn(2, 1, P2, stance="support", content="다른 논점 지지"),
    ]
    md = render_minutes(_meta(), turns, NAMES)
    assert "[미응답 반박] 대비비 4.5:1 미달 — 이 팔레트는 불가" in md
    assert f"{NAMES[P1]}({P1})" in md


def test_rebut_followed_by_other_speaker_accept_is_resolved():
    """rebut 뒤 타 발언자의 accept가 있으면 미해결 쟁점에서 빠진다."""
    turns = [
        _turn(1, 1, P1, stance="rebut", content="대비비 미달"),
        _turn(2, 1, P2, stance="accept", content="수용하고 팔레트를 교체한다"),
    ]
    assert _open_issues(turns, NAMES) == []
    md = render_minutes(_meta(), turns, NAMES)
    assert "[미응답 반박]" not in md
    assert "(없음)" in md.split("## 6. 미해결 쟁점")[1]


def test_self_accept_does_not_resolve_rebut():
    """자기 자신의 accept로는 반박이 해소되지 않는다."""
    turns = [
        _turn(1, 1, P1, stance="rebut", content="엔진 계약 위반"),
        _turn(2, 1, P1, stance="accept", content="스스로 납득"),
    ]
    issues = _open_issues(turns, NAMES)
    assert len(issues) == 1 and "[미응답 반박]" in issues[0]


def test_empty_meeting_renders_placeholders():
    md = render_minutes(_meta(), [], NAMES)
    assert "(기록된 결정 없음)" in md
    assert "| - | (없음) | - | - |" in md  # 액션아이템 표
    assert "(없음)" in md.split("## 6. 미해결 쟁점")[1]
