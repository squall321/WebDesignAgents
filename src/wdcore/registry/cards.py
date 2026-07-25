# 지식카드 마크다운(frontmatter) 파서 — KnowledgeCard 변환, 파생 필드 계산, KL 규칙 검증
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/registry/cards.py
# (copy-adapt: python-frontmatter 의존 제거 — PyYAML로 frontmatter 직접 파싱)
from __future__ import annotations

import hashlib
import re
from datetime import date
from pathlib import Path

import yaml

from wdcore.errors import CardValidationError
from wdcore.models import CardType, KnowledgeCard

# 유형별 필수 ## 섹션 (순서 고정)
REQUIRED_SECTIONS: dict[CardType, tuple[str, ...]] = {
    CardType.concept: ("## 정의", "## 메커니즘", "## 실무에서 왜 중요한가"),
    CardType.design_rule: ("## 규칙", "## 적용 조건", "## 예외와 한계", "## 근거"),
    CardType.data: ("## 데이터", "## 조건과 정의", "## 해석 시 주의"),
    CardType.failure_case: ("## 증상", "## 원인 메커니즘", "## 판별 방법", "## 대책"),
    CardType.standard_summary: (
        "## 표준 개요",
        "## 핵심 요구사항",
        "## 이 도메인에서의 적용 포인트",
        "## 원문 참조 안내",
    ),
    CardType.faq: ("## 질문", "## 답"),
    CardType.open_observation: (
        "## 관측",
        "## 재현성",
        "## 관측된 상관",
        "## 배제한 것",
        "## 미해결",
        "## 사용 주의",
    ),
}

# 유형별 금지 ## 섹션 (KL-017 — open-observation은 인과 미검증이므로 원인 메커니즘 단정 금지)
FORBIDDEN_SECTIONS: dict[CardType, tuple[str, ...]] = {
    CardType.open_observation: ("## 원인 메커니즘",),
}

# frontmatter 블록: 파일 선두 '---' 줄 ~ 다음 '---' 줄
_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.DOTALL)

_HANGUL_RE = re.compile(r"[가-힣]")
_ENG_WORD_RE = re.compile(r"[A-Za-z]+")
_NUM_SYM_RE = re.compile(r"\d+|[^\w\s가-힣]")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """마크다운 선두의 '---' YAML frontmatter를 PyYAML로 직접 파싱한다.

    (metadata dict, 본문) 튜플을 반환한다. frontmatter가 없으면 빈 dict.
    python-frontmatter 미설치 환경 대응 — 계약은 frontmatter.load와 동일한 부분집합.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    meta = yaml.safe_load(m.group(1))
    if meta is None:
        meta = {}
    if not isinstance(meta, dict):
        raise ValueError(f"frontmatter가 매핑이 아니다: {type(meta).__name__}")
    return meta, text[m.end():]


def estimate_tokens(text: str) -> int:
    """단순·결정적 토큰 수 휴리스틱 (실제 토크나이저 아님 — 예산 판단용 근사).

    한글 문자 수 / 1.5 + 영단어 수 * 1.3 + 숫자·기호 토큰 수를 정수 반올림한다.
    """
    hangul = len(_HANGUL_RE.findall(text))
    eng_words = len(_ENG_WORD_RE.findall(text))
    num_sym = len(_NUM_SYM_RE.findall(text))
    return round(hangul / 1.5 + eng_words * 1.3 + num_sym)


def parse_card(path: Path) -> KnowledgeCard:
    """카드 md 파일 1개를 KnowledgeCard로 파싱한다.

    frontmatter를 모델 필드에 매핑하고 body_md/source_path/checksum/token_estimate
    파생 필드를 채운다. 파일명-id 불일치(KL-002)와 미래 updated(KL-005)는
    CardValidationError로, 그 외 스키마 위반(id-type 정합, fact 출처 필수 등)은
    모델 검증의 pydantic ValidationError로 드러난다.
    """
    metadata, content = parse_frontmatter(path.read_text(encoding="utf-8"))
    body = content.strip()
    data = dict(metadata)
    data.update(
        body_md=body,
        source_path=str(path),
        checksum=hashlib.sha256(body.encode("utf-8")).hexdigest(),
        token_estimate=estimate_tokens(body),
    )
    card = KnowledgeCard.model_validate(data)
    if path.stem != card.id:
        raise CardValidationError(
            f"파일명-카드 id 불일치(KL-002): {path.name} vs id={card.id}", path=str(path)
        )
    if card.updated > date.today():
        raise CardValidationError(
            f"updated가 미래 날짜(KL-005): {card.id} updated={card.updated}", path=str(path)
        )
    return card


def check_required_sections(card: KnowledgeCard) -> list[str]:
    """유형별 필수 ## 섹션 중 본문에 없는 것을 반환한다 (오류가 아닌 경고 용도)."""
    headings = {
        line.strip() for line in card.body_md.splitlines() if line.lstrip().startswith("## ")
    }
    return [s for s in REQUIRED_SECTIONS[card.type] if s not in headings]


def check_forbidden_sections(card: KnowledgeCard) -> list[str]:
    """유형별 금지 ## 섹션(KL-017)이 본문에 존재하면 반환한다."""
    headings = {
        line.strip() for line in card.body_md.splitlines() if line.lstrip().startswith("## ")
    }
    return [s for s in FORBIDDEN_SECTIONS.get(card.type, ()) if s in headings]
