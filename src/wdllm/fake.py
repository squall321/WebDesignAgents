# 테스트용 결정적 FakeLLM — 브리핑을 규칙 기반으로 파싱해 라운드에 맞는 부분 스키마 JSON 생성
"""네트워크 없이 오케스트레이터 전체 루프를 검증하기 위한 가짜 LLM.

GLMClient 와 같은 `.chat(messages, **kwargs) -> ChatResult` 인터페이스를 구현한다.
브리핑의 라벨 라인([라운드]/[발언자]/[F#] ref=...)을 파싱해 라운드 지시에 맞는
stance/artifacts/citations 를 규칙으로 생성한다. 같은 입력 → 같은 출력.

고장 주입:
- bad_ref_calls: 해당 호출 번호(1부터)에서 환각 인용(ref=HALLU-999) 생성 → repair 경로 검증.
- stubborn=True: repair 요청([수정요청] 마커)에도 계속 환각 인용 → skip 경로 검증.
"""
from __future__ import annotations

import json
import re

from .client import ChatResult, Message

HALLUCINATED_REF = "HALLU-999"

_ROUND_RE = re.compile(r"\[라운드\] no=(\d+) name=(\S+) citation_required=(\S+)")
_SPEAKER_RE = re.compile(r"\[발언자\] role=(\S+) id=(\S+)")
_REF_RE = re.compile(r"ref=([A-Za-z0-9_-]+)")

# 라운드 이름 → (stance, artifact type). 없으면 ("propose", "idea").
_ROUND_BEHAVIOR: dict[str, tuple[str, str | None]] = {
    # scenario_build
    "structure_diverge": ("summarize", "scene_draft"),
    "cross_rebuttal": ("rebut", "finding"),
    "converge_timeline": ("propose", "idea"),
    "verdict": ("summarize", "decision"),
    # brainstorm
    "diverge": ("propose", "idea"),
    "build_on": ("support", "idea"),
    "converge": ("summarize", "finding"),
    # design_review / module_review
    "present": ("summarize", None),
    "review": ("concern", "finding"),
    "rebuttal": ("rebut", "finding"),
    # tradeoff
    "advocate": ("propose", "idea"),
    "attack": ("rebut", "finding"),
    "score": ("propose", "finding"),
    "decide": ("summarize", "decision"),
}


class FakeLLM:
    """결정적 응답 생성기. calls 로 호출 수를 관찰할 수 있다."""

    def __init__(self, *, bad_ref_calls: set[int] | None = None, stubborn: bool = False) -> None:
        self.bad_ref_calls = bad_ref_calls or set()
        self.stubborn = stubborn
        self.calls = 0

    def chat(self, messages: list[Message], **kwargs) -> ChatResult:  # noqa: ARG002 — 인터페이스 호환
        self.calls += 1
        briefing = "\n".join(
            m.get("content", "") for m in messages if m.get("role") == "user"
        )
        is_repair = "[수정요청]" in briefing

        round_name, citation_required = "unknown", False
        if m := _ROUND_RE.search(briefing):
            round_name = m.group(2)
            citation_required = m.group(3) == "true"
        role, speaker = "expert", "moderator"
        if m := _SPEAKER_RE.search(briefing):
            role = m.group(1)
            speaker = m.group(2) if m.group(2) != "-" else "moderator"
        refs = _REF_RE.findall(briefing)

        stance, artifact_type = _ROUND_BEHAVIOR.get(round_name, ("propose", "idea"))
        if role == "moderator":
            # 모더레이터는 조직화만 — 산출물은 라운드 규칙(scene_draft/decision)만 유지
            if artifact_type not in ("scene_draft", "decision"):
                artifact_type = None
            stance = "summarize"
        elif round_name == "converge_timeline" and speaker.startswith("narr-story"):
            artifact_type = "scenario_patch"  # ST 의 scenario_patch 독점 작성권

        sabotage = self.calls in self.bad_ref_calls or (is_repair and self.stubborn)
        citations = []
        # 인용 필수 라운드는 역할 무관 인용 의무 — 엔진은 모더레이터 턴도 citations 를 검증한다
        if citation_required:
            ref = HALLUCINATED_REF if sabotage else (refs[0] if refs else HALLUCINATED_REF)
            citations = [{"ref": ref, "quote": f"{ref} 근거 인용 (결정적)"}]

        artifacts = []
        if artifact_type == "decision":
            artifacts = [{"type": "decision", "content": "Go — 검증기 결과 이상 없음 (결정적 판정)"}]
        elif artifact_type:
            artifacts = [{
                "type": artifact_type,
                "content": f"{speaker}의 {round_name} {artifact_type} 산출물 (call #{self.calls})",
            }]

        content_md = (
            f"[{speaker}] {round_name} 라운드 발언 (call #{self.calls})."
            f" 라운드 지시에 따라 {stance} 입장을 결정적으로 생성한다."
            + (" 수정요청을 반영해 재제출한다." if is_repair else "")
        )
        payload = {
            "stance": stance,
            "content_md": content_md,
            "citations": citations,
            "artifacts": artifacts,
        }
        content = json.dumps(payload, ensure_ascii=False)
        prompt_tokens = max(1, len(briefing) // 4)
        completion_tokens = max(1, len(content) // 4)
        return ChatResult(
            content=content,
            reasoning=None,
            model="fake-llm",
            usage={
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
            raw={"fake": True, "call": self.calls},
            finish_reason="stop",
        )
