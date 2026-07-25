# 페르소나 정의 모델 — personas/{persona_id}/persona.yaml(SSOT)의 파이썬 표현
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/models/expert.py
# (copy-adapt: 필드 구조는 원본 그대로, Expert→Persona / ExpertSummary→PersonaSummary /
#  RelatedExpert→RelatedPersona 등 이름만 wdcore 문맥으로 교체)
from __future__ import annotations

import re
from datetime import date

from pydantic import AliasChoices, Field, field_validator, model_validator

from .common import CATEGORIES, MeetingRole, PersonaId, PersonaStatus, RelationType, StrictModel


class PersonaSpec(StrictModel):
    """페르소나 연기 정의. system_prompt가 완성형이며 어댑터가 그대로 반환한다."""

    title: str = Field(description="한 줄 직함. 예: '모션 그래픽 15년 경력 모션 디렉터'")
    career_background: str = Field(description="경력 서사 2~5문장. 답변 관점을 형성")
    speaking_style: str = Field(description="화법 지시. 예: '결론 먼저, 수치 근거, 불확실성 명시'")
    system_prompt: str = Field(description="완성형 시스템프롬프트. 브리핑 persona 필드로 반환")


class ExpertiseSpec(StrictModel):
    """전문성 경계. out_of_scope가 심의 영역의 경계 중복을 막는다."""

    in_scope: list[str] = Field(min_length=1, description="다루는 주제 5~15개")
    out_of_scope: list[str] = Field(default_factory=list, description="명시적으로 다루지 않는 주제 (→ 위임 대상)")
    boundary_statement: str = Field(description="내 영역의 경계 1~2문장")


class KnowledgeSpec(StrictModel):
    """지식 자산 경로 (persona.yaml 디렉터리 기준 상대경로)."""

    cards_dir: str = "cards/"
    facts_manifest: str = "facts/manifest.yaml"
    golden_qa: str = "eval/golden.jsonl"
    target_card_count: int = Field(default=45, ge=1, le=200)


class RoutingSpec(StrictModel):
    """라우팅 힌트. 시맨틱 라우터 구현은 스코프 밖 — 필드 계약만 유지."""

    keywords_ko: list[str] = Field(default_factory=list)
    keywords_en: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list, description="템플릿 ID·토큰명 정규식")
    example_questions: list[str] = Field(default_factory=list, description="라우터 앵커 씨앗")
    anti_examples: list[str] = Field(default_factory=list, description="오분류 회귀 테스트용")

    @field_validator("patterns", mode="after")
    @classmethod
    def _compilable(cls, v: list[str]) -> list[str]:
        for p in v:
            try:
                re.compile(p)
            except re.error as e:
                raise ValueError(f"컴파일 불가능한 라우팅 패턴: {p!r} ({e})") from e
        return v

    @field_validator("keywords_ko", "keywords_en", mode="after")
    @classmethod
    def _lower(cls, v: list[str]) -> list[str]:
        return [s.lower() for s in v]


class RelatedPersona(StrictModel):
    id: PersonaId
    relation: RelationType
    when_to_refer: str = Field(description="언제 이 페르소나에게 넘길지 1문장")


class MeetingSpec(StrictModel):
    default_role: MeetingRole | None = None
    stance: str | None = Field(default=None, description="회의에서의 기본 태도 1문장")


class MaintenanceSpec(StrictModel):
    owner: str
    created: date
    updated: date
    review_cycle_months: int = Field(default=6, ge=1, le=24)

    @model_validator(mode="after")
    def _order(self) -> "MaintenanceSpec":
        if self.updated < self.created:
            raise ValueError("maintenance.updated가 created보다 과거일 수 없다")
        return self


class Persona(StrictModel):
    """페르소나 1명의 전체 정의. personas/{id}/persona.yaml 로드 결과."""

    id: PersonaId
    abbr: str = Field(pattern=r"^[A-Z]{2,4}$", description="카드 ID 접두어. 전역 유일")
    name_ko: str
    name_en: str
    category: str = Field(description="8개 카테고리 슬러그 중 하나 (id 접두어와 일치)")
    status: PersonaStatus = PersonaStatus.draft
    version: int = Field(default=1, ge=1)
    persona: PersonaSpec
    expertise: ExpertiseSpec
    knowledge: KnowledgeSpec = Field(default_factory=KnowledgeSpec)
    routing: RoutingSpec = Field(default_factory=RoutingSpec)
    # YAML은 ExpertAgents expert.yaml 포맷을 계승하므로 related_experts 표기도 허용한다
    related_personas: list[RelatedPersona] = Field(
        default_factory=list,
        validation_alias=AliasChoices("related_personas", "related_experts"),
    )
    meeting: MeetingSpec | None = None
    maintenance: MaintenanceSpec
    # 로더가 채우는 파생 필드
    dir_path: str = Field(default="", description="persona.yaml이 있는 디렉터리 절대경로")

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        if v not in CATEGORIES:
            raise ValueError(f"알 수 없는 카테고리 슬러그: {v!r} (허용: {sorted(CATEGORIES)})")
        return v

    @model_validator(mode="after")
    def _prefix_matches_category(self) -> "Persona":
        prefix = self.id.split("-", 1)[0]
        if prefix != self.category:
            raise ValueError(
                f"페르소나 id 접두어({prefix})와 category({self.category})가 일치해야 한다: {self.id}"
            )
        return self


class PersonaSummary(StrictModel):
    """목록·추천 응답용 축약형."""

    id: PersonaId
    abbr: str
    category: str
    name_ko: str
    name_en: str
    status: PersonaStatus
    boundary_statement: str = ""

    @classmethod
    def from_persona(cls, p: Persona) -> "PersonaSummary":
        return cls(
            id=p.id, abbr=p.abbr, category=p.category, name_ko=p.name_ko, name_en=p.name_en,
            status=p.status, boundary_statement=p.expertise.boundary_statement,
        )
