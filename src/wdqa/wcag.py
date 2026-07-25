# WCAG 2.1 상대 휘도·대비 계산 + CSS 색 파싱·알파 합성 유틸 (게이트 3 공용)
from __future__ import annotations

import re

RGB = tuple[float, float, float]
RGBA = tuple[float, float, float, float]

_HEX_RE = re.compile(r"^#([0-9a-fA-F]{3,8})$")
_RGB_RE = re.compile(
    r"^rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*(?:,\s*([\d.]+)\s*)?\)$"
)


def parse_css_color(s: str) -> RGBA | None:
    """#rgb/#rrggbb/#rrggbbaa/rgb()/rgba() 문자열을 (r,g,b,a) 0~255/0~1 로 파싱한다."""
    s = s.strip()
    m = _HEX_RE.match(s)
    if m:
        h = m.group(1)
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        if len(h) == 4:
            h = "".join(c * 2 for c in h)
        if len(h) == 6:
            h += "FF"
        if len(h) != 8:
            return None
        r, g, b, a = (int(h[i : i + 2], 16) for i in (0, 2, 4, 6))
        return (float(r), float(g), float(b), a / 255.0)
    m = _RGB_RE.match(s)
    if m:
        r, g, b = (float(m.group(i)) for i in (1, 2, 3))
        a = float(m.group(4)) if m.group(4) is not None else 1.0
        return (r, g, b, a)
    if s == "transparent":
        return (0.0, 0.0, 0.0, 0.0)
    return None


def composite_over(fg: RGBA, bg: RGB) -> RGB:
    """알파 있는 fg 를 불투명 bg 위에 합성한다."""
    r, g, b, a = fg
    return (
        r * a + bg[0] * (1 - a),
        g * a + bg[1] * (1 - a),
        b * a + bg[2] * (1 - a),
    )


def composite_chain(chain: list[RGBA], base: RGB = (255.0, 255.0, 255.0)) -> RGB:
    """가장 먼 배경부터 순서대로 합성해 유효 배경색을 만든다 (chain[0]=가장 아래)."""
    cur = base
    for c in chain:
        cur = composite_over(c, cur)
    return cur


def relative_luminance(rgb: RGB) -> float:
    """WCAG 2.1 상대 휘도."""

    def lin(c: float) -> float:
        c = c / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast_ratio(fg: RGB, bg: RGB) -> float:
    """WCAG 2.1 대비비 (1.0~21.0)."""
    l1 = relative_luminance(fg)
    l2 = relative_luminance(bg)
    hi, lo = (l1, l2) if l1 >= l2 else (l2, l1)
    return (hi + 0.05) / (lo + 0.05)


def to_hex(rgb: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(int(round(max(0, min(255, c)))) for c in rgb))


def rgb_close(a: RGB, b: RGB, tol: int) -> bool:
    return all(abs(x - y) <= tol for x, y in zip(a, b))
