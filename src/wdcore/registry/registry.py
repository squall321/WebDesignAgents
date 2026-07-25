# 인메모리 페르소나 레지스트리 — 전체 로드, 전역 검증(abbr/related/카드 id), 조회의 단일 창구
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/registry/registry.py
# (copy-adapt: experts_root→personas_root, expert.yaml→persona.yaml, Expert→Persona)
from __future__ import annotations

from pathlib import Path
from typing import Literal

import structlog

from wdcore.config import get_settings
from wdcore.errors import PersonaNotFoundError
from wdcore.models import KnowledgeCard, Persona, PersonaSummary, StrictModel

log = structlog.get_logger("wdcore.registry")


class Issue(StrictModel):
    """로드/검증 중 발견된 문제 1건. error여도 로드는 계속된다 (fail-fast 판단은 호출자 몫)."""

    level: Literal["error", "warning"]
    where: str
    message: str


class Registry:
    """로드 완료된 페르소나·카드 스냅샷. 조회 전용."""

    def __init__(
        self,
        personas: dict[str, Persona],
        cards: dict[str, list[KnowledgeCard]],
        issues: list[Issue],
    ) -> None:
        self.personas = personas
        self.cards = cards  # 소유자 persona_id 기준
        self.issues = issues

    def get(self, persona_id: str) -> Persona:
        try:
            return self.personas[persona_id]
        except KeyError:
            raise PersonaNotFoundError(f"페르소나 없음: {persona_id}", persona_id=persona_id) from None

    def list_personas(self, statuses: list[str] | None = None) -> list[Persona]:
        xs = sorted(self.personas.values(), key=lambda p: p.id)
        if statuses is None:
            return xs
        return [p for p in xs if p.status.value in statuses]

    def cards_for(self, persona_id: str) -> list[KnowledgeCard]:
        self.get(persona_id)  # 존재 검증
        return self.cards.get(persona_id, [])

    def all_cards(self) -> list[KnowledgeCard]:
        return [c for cs in self.cards.values() for c in cs]

    def summaries(self) -> list[PersonaSummary]:
        return [PersonaSummary.from_persona(p) for p in self.list_personas()]


def load_registry(root: Path | None = None) -> Registry:
    """root(기본 settings.personas_root) 아래 전 페르소나를 로드하고 전역 검사를 수행한다.

    전역 검사: (1) 디렉터리명=id 일치, (2) abbr 전역 유일, (3) related_personas[].id
    존재(strict_refs=False면 warning, True면 error), (4) 카드 id 전역 유일.
    error가 있어도 Registry는 반환하고 issues에 담는다.
    """
    from .loader import PERSONA_FILENAME, load_persona_dir  # 순환 import 회피 (loader가 Issue를 쓴다)

    settings = get_settings()
    root = Path(root) if root is not None else settings.personas_root

    personas: dict[str, Persona] = {}
    cards: dict[str, list[KnowledgeCard]] = {}
    issues: list[Issue] = []
    abbr_owner: dict[str, str] = {}
    card_owner: dict[str, str] = {}

    for yaml_path in sorted(root.glob(f"*/{PERSONA_FILENAME}")):
        persona_dir = yaml_path.parent
        try:
            persona, persona_cards, sub_issues = load_persona_dir(persona_dir)
        except Exception as exc:  # 페르소나 1명 실패가 전체 로드를 막지 않는다
            issues.append(Issue(level="error", where=str(yaml_path), message=str(exc)))
            log.warning("persona_load_failed", path=str(yaml_path), error=str(exc))
            continue
        issues.extend(sub_issues)

        if persona_dir.name != persona.id:
            issues.append(
                Issue(
                    level="error",
                    where=str(persona_dir),
                    message=f"디렉터리명({persona_dir.name})과 페르소나 id({persona.id}) 불일치",
                )
            )
        if persona.abbr in abbr_owner:
            issues.append(
                Issue(
                    level="error",
                    where=persona.id,
                    message=f"abbr {persona.abbr!r} 전역 중복: {abbr_owner[persona.abbr]}와 충돌",
                )
            )
        else:
            abbr_owner[persona.abbr] = persona.id
        for card in persona_cards:
            if card.id in card_owner:
                issues.append(
                    Issue(
                        level="error",
                        where=card.source_path,
                        message=f"카드 id {card.id} 전역 중복: {card_owner[card.id]} 소유 카드와 충돌",
                    )
                )
            else:
                card_owner[card.id] = persona.id

        personas[persona.id] = persona
        cards[persona.id] = persona_cards

    ref_level: Literal["error", "warning"] = "error" if settings.strict_refs else "warning"
    for p in personas.values():
        for rel in p.related_personas:
            if rel.id not in personas:
                issues.append(
                    Issue(level=ref_level, where=p.id, message=f"related_personas 미존재 id: {rel.id}")
                )

    log.info(
        "registry_loaded",
        personas=len(personas),
        cards=sum(len(cs) for cs in cards.values()),
        errors=sum(1 for i in issues if i.level == "error"),
        warnings=sum(1 for i in issues if i.level == "warning"),
    )
    return Registry(personas=personas, cards=cards, issues=issues)
