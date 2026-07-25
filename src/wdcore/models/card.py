# L1 지식카드 모델 — personas/{id}/cards/*.md frontmatter의 파이썬 표현
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/models/knowledge.py
# (copy-adapt: L2 FactChunk는 RAG 스코프 밖이라 제거, ExpertId→PersonaId. 필드명 expert_id는
#  카드 frontmatter 하위 호환을 위해 원본 그대로 유지)
from __future__ import annotations

from datetime import date

from pydantic import Field, field_validator, model_validator

from .common import (
    CARD_TYPE_CODES,
    CardId,
    CardTier,
    CardType,
    CausalStatus,
    Confidence,
    Lang,
    PersonaId,
    ReviewStatus,
    StrictModel,
)


class CardSource(StrictModel):
    """카드 출처 1건. ref는 문서 ID 또는 URL."""

    ref: str = Field(description="문서 ID(예: DOC-WCAG-22) 또는 URL")
    locator: str = Field(default="", description="페이지/절/표 위치. 예: 'p.9 Table 2'")
    note: str = ""


class KnowledgeCard(StrictModel):
    """L1 지식카드. personas/{persona_id}/cards/{id}.md 1파일 = 1카드."""

    id: CardId
    expert_id: list[PersonaId] = Field(min_length=1, description="첫 원소가 소유자. 공유 카드면 복수")
    title: str = Field(min_length=8, max_length=60)
    type: CardType
    confidence: Confidence
    causal_status: CausalStatus | None = Field(
        default=None,
        description="인과 검증도. 부재=validated. open-observation은 unknown/hypothesized 필수",
    )
    tier: CardTier = Field(default=CardTier.deep, description="브리핑 조립 우선순위 (선택)")
    sources: list[CardSource] = Field(default_factory=list)

    @field_validator("sources", mode="before")
    @classmethod
    def _coerce_source_strings(cls, v):
        # 손으로 쓴 카드는 sources를 평문 문자열로 적는 경우가 많다 — {ref: 문자열}로 승격
        if isinstance(v, list):
            return [{"ref": item} if isinstance(item, str) else item for item in v]
        return v
    standard_refs: list[str] = Field(default_factory=list)
    fact_refs: list[str] = Field(default_factory=list, description="참조 문서 doc_id")
    tags: list[str] = Field(default_factory=list)
    lang: Lang = Lang.ko
    version: int = Field(default=1, ge=1)
    review_status: ReviewStatus = ReviewStatus.draft
    updated: date
    # 로더가 채우는 파생 필드
    body_md: str = Field(default="", description="frontmatter 제외 마크다운 본문")
    source_path: str = Field(default="", description="원본 md 파일 절대경로")
    checksum: str = Field(default="", description="본문 sha256 — 재색인 판정")
    token_estimate: int = Field(default=0, ge=0)
    score: float | None = Field(default=None, description="검색 결과일 때만 채워짐")

    @property
    def owner_id(self) -> str:
        return self.expert_id[0]

    @property
    def type_code(self) -> str:
        return self.id.split("-")[1]

    @model_validator(mode="after")
    def _id_type_consistent(self) -> "KnowledgeCard":
        expected = CARD_TYPE_CODES[self.type_code]
        if expected is not self.type:
            raise ValueError(
                f"카드 ID의 TYPE 코드({self.type_code})와 type({self.type.value})이 불일치: {self.id}"
            )
        return self

    @model_validator(mode="after")
    def _fact_requires_sources(self) -> "KnowledgeCard":
        # KL-006: data/standard-summary 유형과 confidence=fact는 출처 1개 이상 필수
        needs = self.type in (CardType.data, CardType.standard_summary) or (
            self.confidence is Confidence.fact
        )
        if needs and not self.sources:
            raise ValueError(
                f"출처 필수 위반(KL-006): {self.id} — type={self.type.value}, "
                f"confidence={self.confidence.value}에는 sources가 1개 이상 필요"
            )
        return self

    @model_validator(mode="after")
    def _open_observation_causal(self) -> "KnowledgeCard":
        # KL-017: open-observation은 causal_status가 unknown/hypothesized 필수 (인과 미검증)
        if self.type is CardType.open_observation and self.causal_status not in (
            CausalStatus.unknown,
            CausalStatus.hypothesized,
        ):
            raise ValueError(
                f"open-observation 위반(KL-017): {self.id} — "
                f"causal_status가 unknown/hypothesized여야 함 (현재 {self.causal_status})"
            )
        return self

    @property
    def effective_causal_status(self) -> CausalStatus:
        """causal_status 부재 시 validated 로 간주 (하위호환)."""
        return self.causal_status or CausalStatus.validated
