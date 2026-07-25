# 회의록 렌더러 — 턴의 artifacts·citations를 집계해 마크다운 회의록 생성 (미응답 반박 자동 추출 포함)
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/meetings/minutes.py
# (copy-adapt: 회의 유형 라벨을 wdcore 5종으로 교체, import 경로만 wdcore로)
from __future__ import annotations

from collections.abc import Mapping

from wdcore.models.meeting import (
    ArtifactType,
    MeetingMeta,
    MeetingTurn,
    SpeakerRole,
)

from .templates import MEETING_TEMPLATES

_TYPE_LABELS: dict[str, str] = {
    "brainstorm": "컨셉 브레인스토밍",
    "design_review": "시안 크리틱",
    "tradeoff": "트레이드오프 결정",
    "scenario_build": "시나리오 빌드",
    "module_review": "모듈 승격 심사",
}

_ROLE_LABELS: dict[str, str] = {
    "moderator": "모더레이터",
    "user": "사용자",
    "system": "시스템",
}


def _speaker_label(turn: MeetingTurn, experts: Mapping[str, str]) -> str:
    if turn.role is SpeakerRole.expert and turn.expert_id:
        name = experts.get(turn.expert_id)
        if name and name != turn.expert_id:
            return f"{name}({turn.expert_id})"
        return turn.expert_id
    return _ROLE_LABELS.get(turn.role.value, turn.role.value)


def _cell(text: str, limit: int = 80) -> str:
    """마크다운 표 셀용 요약: 첫 줄만, 파이프 이스케이프, 길이 제한."""
    stripped = text.strip()
    first = stripped.splitlines()[0] if stripped else ""
    if len(first) > limit:
        first = first[: limit - 1] + "…"
    return first.replace("|", "\\|")


def _fmt_ts(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "-"


def render_minutes(
    meta: MeetingMeta,
    turns: list[MeetingTurn],
    experts: Mapping[str, str] | None = None,
) -> str:
    """meta와 턴 목록으로 마크다운 회의록을 생성한다.

    experts는 persona_id → 표시 이름 매핑 (없으면 id 그대로 표기).
    미해결 쟁점은 open_issue 산출물과 'rebut 이후 타 발언자의 accept가 없는 턴'을 자동 추출한다.
    """
    experts = experts or {}
    specs = MEETING_TEMPLATES[meta.type]
    doc: list[str] = [
        f"# [회의록] {meta.topic}",
        "",
        f"- 회의 ID: {meta.id[:8]} / 유형: {_TYPE_LABELS.get(meta.type.value, meta.type.value)}"
        f" / 상태: {meta.status.value}",
        f"- 일시: {_fmt_ts(meta.created_at)} ~ {_fmt_ts(meta.closed_at)} ({len(turns)}턴)",
        "",
        "## 1. 참가자",
        "",
        "| ID | 이름 |",
        "|---|---|",
    ]
    for pid in meta.participants:
        doc.append(f"| {pid} | {experts.get(pid, pid)} |")

    # --- 라운드별 발언 요약 ---
    doc += ["", "## 2. 라운드별 발언 요약"]
    round_nos = sorted({t.round_no for t in turns})
    for rno in round_nos:
        name = specs[rno].name if rno < len(specs) else f"round-{rno}"
        doc += ["", f"### R{rno + 1} {name}", "", "| 턴 | 발언자 | 태도 | 요지 | 인용 |", "|---|---|---|---|---|"]
        for t in turns:
            if t.round_no != rno:
                continue
            refs = ", ".join(c.ref for c in t.citations) or "-"
            doc.append(
                f"| #{t.turn_no} | {_speaker_label(t, experts)} | {t.stance or '-'}"
                f" | {_cell(t.content_md)} | {refs} |"
            )

    # --- 결론 (decision 집계) ---
    doc += ["", "## 3. 결론", ""]
    decisions = [
        (t, a) for t in turns for a in t.artifacts if a.type is ArtifactType.decision
    ]
    if decisions:
        for t, a in decisions:
            doc.append(f"- {a.content} (턴 #{t.turn_no})")
    else:
        doc.append("(기록된 결정 없음)")

    # --- 액션아이템 ---
    doc += ["", "## 4. 액션아이템", "", "| # | 내용 | 담당 | 제출 턴 |", "|---|---|---|---|"]
    actions = [
        (t, a) for t in turns for a in t.artifacts if a.type is ArtifactType.action_item
    ]
    for i, (t, a) in enumerate(actions, start=1):
        owner = a.owner_expert_id or _speaker_label(t, experts)
        doc.append(f"| {i} | {_cell(a.content)} | {owner} | #{t.turn_no} |")
    if not actions:
        doc.append("| - | (없음) | - | - |")

    # --- 인용 근거 목록 (ref 기준 dedupe + 턴 역참조) ---
    doc += ["", "## 5. 인용 근거 목록", "", "| # | 출처 ref | 인용 턴 |", "|---|---|---|"]
    cited: dict[str, list[int]] = {}
    for t in turns:
        for c in t.citations:
            cited.setdefault(c.ref, [])
            if t.turn_no not in cited[c.ref]:
                cited[c.ref].append(t.turn_no)
    for i, (ref, turn_nos) in enumerate(cited.items(), start=1):
        doc.append(f"| {i} | {ref} | {', '.join(f'#{n}' for n in turn_nos)} |")
    if not cited:
        doc.append("| - | (없음) | - |")

    # --- 미해결 쟁점 ---
    doc += ["", "## 6. 미해결 쟁점", ""]
    issues = _open_issues(turns, experts)
    if issues:
        doc += [f"- {issue}" for issue in issues]
    else:
        doc.append("(없음)")

    doc.append("")
    return "\n".join(doc)


def _open_issues(turns: list[MeetingTurn], experts: Mapping[str, str]) -> list[str]:
    """미해결 쟁점 추출: open_issue 산출물 + rebut 이후 타 발언자 accept가 없는 반박 (합의 연출 방지)."""
    issues: list[str] = []
    for t in turns:
        for a in t.artifacts:
            if a.type is ArtifactType.open_issue:
                issues.append(f"{_cell(a.content)} (턴 #{t.turn_no})")
    for t in turns:
        if t.stance != "rebut":
            continue
        resolved = any(
            u.turn_no > t.turn_no and u.stance == "accept" and u.expert_id != t.expert_id
            for u in turns
        )
        if not resolved:
            issues.append(
                f"[미응답 반박] {_cell(t.content_md)} — {_speaker_label(t, experts)} (턴 #{t.turn_no})"
            )
    return issues
