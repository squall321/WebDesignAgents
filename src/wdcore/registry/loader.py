# 페르소나 디렉터리(persona.yaml + cards/*.md) 로더 — 카드 단위 실패는 Issue로 수집하고 계속 진행
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/registry/loader.py
# (copy-adapt: knowledge/{id}/expert.yaml → personas/{id}/persona.yaml, Expert→Persona)
from __future__ import annotations

from pathlib import Path

import structlog
import yaml

from wdcore.models import KnowledgeCard, Persona

from .cards import check_forbidden_sections, check_required_sections, parse_card
from .registry import Issue

log = structlog.get_logger("wdcore.registry.loader")

PERSONA_FILENAME = "persona.yaml"


def load_persona_dir(dir_path: Path) -> tuple[Persona, list[KnowledgeCard], list[Issue]]:
    """personas/{persona_id}/ 디렉터리 1개를 로드한다.

    persona.yaml 실패는 예외로 전파하고, 카드 1장 실패는 Issue(error)로 수집한 뒤
    나머지 카드를 계속 읽는다. 필수 섹션 누락은 Issue(warning)로 남긴다.
    """
    yaml_path = dir_path / PERSONA_FILENAME
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    raw["dir_path"] = str(dir_path)
    persona = Persona.model_validate(raw)

    cards: list[KnowledgeCard] = []
    issues: list[Issue] = []
    cards_dir = dir_path / persona.knowledge.cards_dir
    if cards_dir.is_dir():
        for md_path in sorted(cards_dir.glob("*.md")):
            try:
                card = parse_card(md_path)
            except Exception as exc:  # 카드 1장 실패가 페르소나 로드를 막지 않는다
                issues.append(Issue(level="error", where=str(md_path), message=str(exc)))
                log.warning("card_load_failed", path=str(md_path), error=str(exc))
                continue
            for missing in check_required_sections(card):
                issues.append(
                    Issue(level="warning", where=card.id, message=f"필수 섹션 누락(KL-009): {missing}")
                )
            for forbidden in check_forbidden_sections(card):
                issues.append(
                    Issue(level="error", where=card.id, message=f"금지 섹션 사용(KL-017): {forbidden}")
                )
            cards.append(card)
    return persona, cards, issues
