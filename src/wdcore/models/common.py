# 전 모듈이 공유하는 공통 타입·열거형·베이스 모델 정의 (카테고리 8종 = PLAN §5.1)
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/models/common.py
# (copy-adapt: CATEGORIES 15종→8종 교체, ExpertId→PersonaId, ExpertStatus→PersonaStatus,
#  L2/RAG 전용 SourceType·API 전용 Page 제거)
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

# 페르소나 ID: 소문자 슬러그. 예: "vis-typographer" (접두어=카테고리)
PersonaId = Annotated[str, StringConstraints(pattern=r"^[a-z][a-z0-9-]{2,40}$")]

# 카드 ID: {abbr}-{TYPE코드}-{일련3자리}. 예: "TY-C-001"
CardId = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2,4}-[CRDFSQO]-\d{3}$")]

# 택소노미 카테고리 슬러그 (id 접두어와 일치). 웹디자인 심의 8종 (PLAN §5.1)
CATEGORIES: frozenset[str] = frozenset(
    {"dir", "narr", "vis", "mot", "ux", "impl", "av", "qa"}
)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    """모든 도메인 모델의 베이스. 오타 필드를 조기에 잡기 위해 extra 금지."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class PersonaStatus(str, Enum):
    draft = "draft"            # 정의 작성 중
    pilot = "pilot"            # 파일럿 운용
    active = "active"          # 정식 운용
    deprecated = "deprecated"  # 다른 페르소나로 대체됨


class CardType(str, Enum):
    """지식카드 7종 (ExpertAgents 05 §3.1 계승)."""

    concept = "concept"                    # 개념/메커니즘 (C)
    design_rule = "design-rule"            # 설계규칙 (R)
    data = "data"                          # 수치·표 데이터 (D) — 출처 필수
    failure_case = "failure-case"          # 실패사례 (F)
    standard_summary = "standard-summary"  # 표준 요약 (S) — 출처 필수
    faq = "faq"                            # FAQ/실무 팁 (Q)
    open_observation = "open-observation"  # 관측·미해결 (O) — 인과 미검증


# 카드 ID 내 TYPE 코드 ↔ CardType 매핑
CARD_TYPE_CODES: dict[str, CardType] = {
    "C": CardType.concept,
    "R": CardType.design_rule,
    "D": CardType.data,
    "F": CardType.failure_case,
    "S": CardType.standard_summary,
    "Q": CardType.faq,
    "O": CardType.open_observation,
}


class CardTier(str, Enum):
    """브리핑 조립 우선순위. frontmatter에서는 선택 필드."""

    core = "core"                  # 페르소나 정체성 핵심. 항상 포함
    deep = "deep"                  # 심화 지식. 유사도 기반 선택 포함
    checklist = "checklist"        # 심의/리뷰 체크리스트
    failure_mode = "failure_mode"  # 실패 모드·사례


class Confidence(str, Enum):
    """신뢰도 3단 라벨. 클라이언트는 격상 불가."""

    fact = "fact"                          # 출처 있는 사실
    heuristic = "heuristic"                # 경험칙
    expert_judgement = "expert-judgement"  # 전문가 판단


class CausalStatus(str, Enum):
    """인과 검증도. frontmatter 부재 시 validated 로 간주."""

    validated = "validated"        # 인과 메커니즘이 근거로 검증됨 (기본)
    hypothesized = "hypothesized"  # 메커니즘 가설은 있으나 미검증
    unknown = "unknown"            # 관측만 있고 메커니즘 미상 — 판정 근거 불가


class ReviewStatus(str, Enum):
    """카드 생산 파이프라인 상태. draft→approved 직행 금지."""

    draft = "draft"
    fact_checked = "fact-checked"
    approved = "approved"
    rejected = "rejected"
    deprecated = "deprecated"


class Lang(str, Enum):
    ko = "ko"
    en = "en"
    mixed = "mixed"


class RelationType(str, Enum):
    """related_personas[].relation."""

    upstream = "upstream"
    downstream = "downstream"
    sibling = "sibling"
    simulation_counterpart = "simulation-counterpart"
    reliability_counterpart = "reliability-counterpart"


class MeetingRole(str, Enum):
    """회의 기본 역할 (persona.yaml meeting.default_role)."""

    analyst = "analyst"
    challenger = "challenger"
    synthesizer = "synthesizer"
    domain_authority = "domain-authority"
