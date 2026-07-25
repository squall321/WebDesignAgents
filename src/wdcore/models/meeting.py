# 회의 도메인 모델 — 회의 유형·상태·턴·라운드 스펙·메타 정의
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/models/meeting.py
# (copy-adapt: MeetingType에서 dfmea/rca 제거·scenario_build/module_review 추가,
#  ArtifactType에서 dfmea_row 제거·scene_draft/scenario_patch/module_candidate 추가.
#  expert_id/SpeakerRole.expert 등 턴 필드명은 MCP 계약 하위 호환을 위해 원본 그대로 유지)
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import Field

from .common import PersonaId, StrictModel, utcnow


class MeetingType(str, Enum):
    """회의 유형 5종 (PLAN §5.2 회의 파이프라인)."""

    brainstorm = "brainstorm"            # 컨셉 발산 → 상호보완 → 수렴 (M1)
    design_review = "design_review"      # 시안 크리틱 (발표 → 리뷰 → 반론 → 판정, M3)
    tradeoff = "tradeoff"                # 시안 A/B/C 선정 (입장 → 교차반박 → 평가 → 결정)
    scenario_build = "scenario_build"    # 시나리오 빌드 (구조발산 → 교차반박 → 수렴타임라인 → 검증판정, M2)
    module_review = "module_review"      # 모듈 승격 심사 (design_review 파생, M4)


class MeetingStatus(str, Enum):
    created = "created"          # 생성됨 (첫 턴 제출 전)
    in_progress = "in_progress"  # 진행 중
    closed = "closed"            # 폐회 (minutes.md 생성 완료)


class SpeakerRole(str, Enum):
    expert = "expert"        # 참가 페르소나
    moderator = "moderator"  # 모더레이터 (기술적 주장 생성 금지 — 조직화만)
    user = "user"            # 사용자 개입 발언 (진행 순서에 영향 없음)
    system = "system"        # 시스템 이벤트 기록용


class ArtifactType(str, Enum):
    """턴에 첨부되는 구조화 산출물 종류. 회의록의 표는 전부 이 조각의 집계다."""

    idea = "idea"
    finding = "finding"
    decision = "decision"
    action_item = "action_item"
    open_issue = "open_issue"
    scene_draft = "scene_draft"            # 씬 구성 초안 (scenario_build R1)
    scenario_patch = "scenario_patch"      # 시나리오 통합 패치 (ST 독점 작성권)
    module_candidate = "module_candidate"  # 모듈 승격 후보 (module_review)


# 발언 태도. 회의록의 미해결 쟁점 추출은 rebut 이후 accept 여부로 판단한다.
Stance = Literal["propose", "support", "concern", "rebut", "question", "accept", "summarize"]


class Artifact(StrictModel):
    """구조화 산출물 조각."""

    type: ArtifactType
    content: str = Field(min_length=1)
    owner_expert_id: PersonaId | None = Field(default=None, description="담당/제안 페르소나 (선택)")


class Citation(StrictModel):
    """발언 근거 인용. ref는 지식카드 ID 또는 브리핑으로 전달된 근거 라벨."""

    ref: str = Field(min_length=1)
    quote: str = ""


class MeetingTurn(StrictModel):
    """발언 1건. turn_no는 0이면 미부여 상태이며 엔진이 제출 시 채번한다."""

    turn_no: int = Field(default=0, ge=0, description="전체 회의 내 일련번호 (엔진 부여)")
    round_no: int = Field(ge=0, description="라운드 인덱스 (0부터). 현재 라운드와 일치해야 수리")
    role: SpeakerRole
    expert_id: PersonaId | None = Field(default=None, description="role=expert일 때 발언 페르소나 ID")
    stance: Stance | None = None
    content_md: str = Field(min_length=1, description="발언 본문 (마크다운)")
    citations: list[Citation] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class RoundSpec(StrictModel):
    """라운드 진행 규칙. speaker_order의 결정론 규칙은 engine.next_speaker 참조.

    - fixed: 모더레이터 단독 발언 (cycles회)
    - round_robin: 참가 확정 순서로 전원 발언 × cycles사이클
    - moderator_pick: 사이클마다 모더레이터가 먼저 정리·지목 후 전원 발언 (결정론 구현)
    """

    name: str
    instruction: str
    speaker_order: Literal["fixed", "round_robin", "moderator_pick"]
    cycles: int = Field(default=1, ge=1)
    citation_required: bool = False
    allow_early_close: bool = Field(
        default=False, description="True면 decision 산출물 제출 시 라운드 조기 종료"
    )


class MeetingMeta(StrictModel):
    """회의 메타 (meta.json의 파이썬 표현)."""

    id: str = Field(min_length=8, description="UUID4 전체 문자열. 모든 호출의 키")
    type: MeetingType
    topic: str = Field(min_length=1)
    participants: list[PersonaId] = Field(min_length=1, description="참가 확정 순서 = 발언 순서")
    status: MeetingStatus = MeetingStatus.created
    created_at: datetime = Field(default_factory=utcnow)
    closed_at: datetime | None = None
    round_index: int = Field(default=0, ge=0, description="현재 라운드 인덱스 (템플릿 길이 도달 시 전 라운드 종료)")
