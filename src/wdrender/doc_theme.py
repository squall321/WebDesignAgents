# 문서 exporter 전용 테마 — web/tokens/{id}.json 의 raw 팔레트를 읽어 HTML/DOCX 공용 색·폰트로 제공한다
from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .config import REPO_ROOT

TOKENS_DIR = REPO_ROOT / "web" / "tokens"
FONT_PATH = REPO_ROOT / "web" / "fonts" / "PretendardVariable.woff2"
FONT_FAMILY = "Pretendard Variable"

# 토큰 raw.palette 키 → 문서 역할. 값이 없으면 아래 기본값(hwax-blue 원본)을 쓴다.
_PALETTE_DEFAULTS: dict[str, str] = {
    "bg": "#F6F7FA",
    "ink": "#101B3E",
    "sub": "#57607A",
    "faint": "#667085",
    "line": "#E2E6F0",
    "blue": "#1428A0",
    "blue2": "#3D53C6",
    "blueSoft": "#EBEEFA",
    "blueBorder": "#C9D1F0",
    "card": "#FFFFFF",
    "red": "#A8402F",
    "redSoft": "#F8ECE8",
    "green": "#1F7A55",
    "greenSoft": "#E7F2EC",
}

# 시스템 폴백 — 임베드 폰트가 없거나 DOCX(폰트 임베딩 불가)에서 쓰는 이름
DOCX_FONT = "맑은 고딕"


@dataclass(frozen=True)
class DocTheme:
    """영상·PPT 와 같은 브랜드 색을 문서 조판 역할 이름으로 노출한다."""

    id: str = "hwax-blue"
    palette: dict[str, str] = field(default_factory=lambda: dict(_PALETTE_DEFAULTS))
    font_stack: str = (
        f"'{FONT_FAMILY}', Pretendard, 'Noto Sans KR', 'Malgun Gothic', sans-serif"
    )

    def color(self, key: str) -> str:
        return self.palette.get(key) or _PALETTE_DEFAULTS[key]

    # 문서 역할 별칭 — 조판 코드가 팔레트 키를 직접 알 필요가 없게 한다
    @property
    def ink(self) -> str:
        return self.color("ink")

    @property
    def sub(self) -> str:
        return self.color("sub")

    @property
    def faint(self) -> str:
        return self.color("faint")

    @property
    def line(self) -> str:
        return self.color("line")

    @property
    def accent(self) -> str:
        return self.color("blue")

    @property
    def accent2(self) -> str:
        return self.color("blue2")

    @property
    def accent_soft(self) -> str:
        return self.color("blueSoft")

    @property
    def accent_border(self) -> str:
        return self.color("blueBorder")

    @property
    def page(self) -> str:
        return self.color("card")

    @property
    def shade(self) -> str:
        return self.color("bg")


@lru_cache(maxsize=8)
def load_doc_theme(theme_id: str = "hwax-blue") -> DocTheme:
    """web/tokens/{theme_id}.json 의 raw.palette 를 읽는다. 파일이 없으면 기본 팔레트."""
    path = TOKENS_DIR / f"{theme_id}.json"
    if not path.exists():
        return DocTheme(id=theme_id)
    raw = json.loads(path.read_text(encoding="utf-8")).get("raw", {})
    palette = {**_PALETTE_DEFAULTS, **(raw.get("palette") or {})}
    font = (raw.get("font") or {}).get("base") or ""
    if not font:
        stack = DocTheme().font_stack
    else:
        # 토큰 폰트 스택이 이미 Pretendard 를 첫머리에 두면 중복해서 얹지 않는다
        stack = font if FONT_FAMILY in font else f"'{FONT_FAMILY}', {font}"
    return DocTheme(id=theme_id, palette=palette, font_stack=stack)


@lru_cache(maxsize=1)
def font_data_uri() -> str | None:
    """Pretendard woff2 를 base64 data URI 로. 폰트 파일이 없으면 None(시스템 폴백)."""
    if not FONT_PATH.exists():
        return None
    b64 = base64.b64encode(FONT_PATH.read_bytes()).decode("ascii")
    return f"data:font/woff2;base64,{b64}"


def font_face_css(src_url: str) -> str:
    """@font-face 한 덩어리 — src_url 은 data URI 또는 상대 경로."""
    return (
        "@font-face{"
        f"font-family:'{FONT_FAMILY}';"
        f"src:url('{src_url}') format('woff2-variations');"
        "font-weight:45 920;font-style:normal;font-display:swap;}"
    )


def font_relpath(out_dir: Path) -> str | None:
    """out_dir 기준 폰트 파일 상대 경로(light 모드용). 파일이 없으면 None."""
    if not FONT_PATH.exists():
        return None
    import os

    return os.path.relpath(FONT_PATH, out_dir).replace("\\", "/")
