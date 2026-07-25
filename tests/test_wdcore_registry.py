# 페르소나 레지스트리 검증 — persona.yaml 로드, PyYAML frontmatter 카드 파싱, 전역 검사
from __future__ import annotations

import textwrap

import pytest

from wdcore.errors import PersonaNotFoundError
from wdcore.registry import load_registry, parse_frontmatter

PERSONA_YAML = """\
id: vis-typographer
abbr: TY
name_ko: 타이포그래퍼
name_en: Typographer
category: vis
status: active
persona:
  title: 영상 타이포그래피 15년 경력 디자이너
  career_background: 브랜드 필름과 모션 타이틀을 주로 다뤘다. 가독성과 위계를 최우선한다.
  speaking_style: 결론 먼저, 수치 근거, 불확실성 명시
  system_prompt: 당신은 타이포그래피 전문가다. 폰트 스택·위계·최소 가독 크기를 심의한다.
expertise:
  in_scope: [폰트 스택, 타입 스케일, 최소 가독 크기, 자간·행간, 위계]
  out_of_scope: [컬러 팔레트 (→ vis-color-brand)]
  boundary_statement: 글자가 화면에서 읽히는 방식까지만 다룬다.
maintenance:
  owner: koopark
  created: 2026-07-01
  updated: 2026-07-20
"""

CARD_MD = """\
---
id: TY-C-001
expert_id: [vis-typographer]
title: 타입 스케일 위계의 원리
type: concept
confidence: heuristic
tags: [type-scale]
updated: 2026-07-20
---
## 정의
타입 스케일은 크기 비율의 사다리다.

## 메커니즘
비율이 일정하면 위계가 스캔 가능해진다.

## 실무에서 왜 중요한가
1920x1080 프레임에서 최소 24px을 지켜야 한다.
"""


@pytest.fixture()
def personas_root(tmp_path):
    d = tmp_path / "personas" / "vis-typographer"
    (d / "cards").mkdir(parents=True)
    (d / "persona.yaml").write_text(PERSONA_YAML, encoding="utf-8")
    (d / "cards" / "TY-C-001.md").write_text(CARD_MD, encoding="utf-8")
    return tmp_path / "personas"


def test_parse_frontmatter_with_pyyaml():
    meta, body = parse_frontmatter("---\nid: X\ntags: [a, b]\n---\n본문 시작\n")
    assert meta == {"id": "X", "tags": ["a", "b"]}
    assert body.strip() == "본문 시작"
    # frontmatter 없는 문서는 빈 메타
    meta2, body2 = parse_frontmatter("그냥 본문")
    assert meta2 == {} and body2 == "그냥 본문"


def test_load_registry_personas_and_cards(personas_root):
    reg = load_registry(root=personas_root)
    assert [i for i in reg.issues if i.level == "error"] == []
    p = reg.get("vis-typographer")
    assert p.abbr == "TY"
    assert p.category == "vis"
    assert p.persona.system_prompt.startswith("당신은 타이포그래피")
    cards = reg.cards_for("vis-typographer")
    assert len(cards) == 1
    card = cards[0]
    assert card.id == "TY-C-001"
    assert card.owner_id == "vis-typographer"
    assert "타입 스케일은 크기 비율의 사다리다" in card.body_md
    assert card.token_estimate > 0 and card.checksum


def test_unknown_persona_raises(personas_root):
    reg = load_registry(root=personas_root)
    with pytest.raises(PersonaNotFoundError):
        reg.get("vis-nobody")


def test_bad_card_collected_as_issue_not_fatal(personas_root):
    """파일명-id 불일치 카드는 Issue(error)로 수집되고 페르소나 로드는 계속된다."""
    bad = personas_root / "vis-typographer" / "cards" / "TY-C-999.md"
    bad.write_text(CARD_MD, encoding="utf-8")  # frontmatter id=TY-C-001 ≠ 파일명
    reg = load_registry(root=personas_root)
    errors = [i for i in reg.issues if i.level == "error"]
    assert any("KL-002" in i.message for i in errors)
    assert len(reg.cards_for("vis-typographer")) == 1  # 정상 카드만 남는다


def test_category_prefix_mismatch_rejected(personas_root):
    """id 접두어와 category 불일치 페르소나는 로드 실패로 Issue(error)에 남는다."""
    d = personas_root / "mot-easing-guru"
    d.mkdir()
    broken = PERSONA_YAML.replace("id: vis-typographer", "id: mot-easing-guru").replace(
        "abbr: TY", "abbr: EG"
    )  # category는 vis 그대로 → 접두어 mot와 불일치
    (d / "persona.yaml").write_text(textwrap.dedent(broken), encoding="utf-8")
    reg = load_registry(root=personas_root)
    assert "mot-easing-guru" not in reg.personas
    assert any("일치해야 한다" in i.message for i in reg.issues if i.level == "error")
