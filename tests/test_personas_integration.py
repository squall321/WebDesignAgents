# 페르소나 14인이 wdcore 레지스트리 로더로 무결 로드되는지 통합 검증
from wdcore.registry.registry import load_registry


def test_all_personas_load():
    reg = load_registry()
    assert len(reg.personas) == 14
    assert not [i for i in reg.issues if i.level == "error"]


def test_cards_loaded():
    reg = load_registry()
    total_cards = sum(len(c) for c in reg.cards.values()) if isinstance(reg.cards, dict) else len(reg.cards)
    assert total_cards >= 8
