# 게이트 3 — 대비: 정적(contrastPairs 전수 WCAG 계산) + 런타임(스틸 텍스트 실측·미선언 조합 경고)
from __future__ import annotations

import json
from pathlib import Path

from .config import QAConfig
from .report import row
from .wcag import (
    RGB,
    composite_chain,
    composite_over,
    contrast_ratio,
    parse_css_color,
    rgb_close,
    to_hex,
)

GATE = 3


# ── 테마 로드 + 참조 해석 (web/tokens/loader.jsx lookupRef 미러) ────────────

def find_theme_file(theme: str, serve_root: Path, cfg: QAConfig) -> Path | None:
    candidates = [
        serve_root / "web" / "tokens" / f"{theme}.json",
        serve_root / "tokens" / f"{theme}.json",
        *(d / f"{theme}.json" for d in cfg.tokens_dirs),
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _lookup_ref(doc: dict, path: str):
    """"{palette.blue}" 참조 해석 — raw.* 우선, 다음 semantic.* (loader.jsx 미러)."""
    segs = path.split(".")
    for space in (doc.get("raw") or {}, doc.get("semantic") or {}):
        cur = space
        ok = True
        for seg in segs:
            if isinstance(cur, dict) and seg in cur:
                cur = cur[seg]
            else:
                ok = False
                break
        if ok:
            return cur
    raise KeyError(path)


def resolve_token(doc: dict, value):
    """문자열이 "{a.b}" 형태면 재귀 해석, 아니면 그대로."""
    while isinstance(value, str) and value.startswith("{") and value.endswith("}"):
        value = _lookup_ref(doc, value[1:-1])
    return value


def resolved_pairs(doc: dict) -> list[dict]:
    """contrastPairs 를 (fg 색문자열, bg 색문자열, role)로 해석한다."""
    pairs = (doc.get("semantic") or {}).get("contrastPairs") or []
    out = []
    for p in pairs:
        out.append(
            {
                "fg": resolve_token(doc, p.get("fg")),
                "bg": resolve_token(doc, p.get("bg")),
                "role": p.get("role", ""),
            }
        )
    return out


def _pair_effective(fg_s: str, bg_s: str, stage_bg: RGB) -> tuple[RGB, RGB] | None:
    """선언 페어의 유효 (fg, bg) — 알파는 스테이지 배경 위 합성으로 해소한다."""
    fg = parse_css_color(str(fg_s))
    bg = parse_css_color(str(bg_s))
    if fg is None or bg is None:
        return None
    bg_eff = composite_over(bg, stage_bg)
    fg_eff = composite_over(fg, bg_eff)
    return fg_eff, bg_eff


def run_static(theme: str, serve_root: Path, cfg: QAConfig) -> list[dict]:
    """테마 contrastPairs 전수 WCAG 2.1 계산 — <3.0 오류, <4.5 경고(대형 전용)."""
    results: list[dict] = []
    theme_path = find_theme_file(theme, serve_root, cfg)
    if theme_path is None:
        results.append(
            row(GATE, "theme-missing", "error", f"테마 토큰 파일을 찾지 못했다: {theme}.json")
        )
        return results
    doc = json.loads(theme_path.read_text(encoding="utf-8"))
    try:
        pairs = resolved_pairs(doc)
    except KeyError as e:
        results.append(
            row(GATE, "token-ref", "error",
                f"해석할 수 없는 토큰 참조 {{{e.args[0]}}}", path=str(theme_path))
        )
        return results
    if not pairs:
        results.append(
            row(GATE, "no-pairs", "warning",
                "contrastPairs 가 선언되지 않았다 — 정적 대비 검증 불가", path=str(theme_path))
        )
        return results

    stage_bg_raw = parse_css_color(
        str(resolve_token(doc, ((doc.get("raw") or {}).get("palette") or {}).get("bg", "#FFFFFF")))
    )
    stage_bg: RGB = (
        composite_over(stage_bg_raw, (255.0, 255.0, 255.0)) if stage_bg_raw else (255.0, 255.0, 255.0)
    )

    for p in pairs:
        eff = _pair_effective(p["fg"], p["bg"], stage_bg)
        if eff is None:
            results.append(
                row(GATE, "pair-parse", "warning",
                    f"색 파싱 실패: fg={p['fg']!r} bg={p['bg']!r} ({p['role']})",
                    path=str(theme_path))
            )
            continue
        ratio = contrast_ratio(*eff)
        detail = (
            f"{p['role']} — fg {to_hex(eff[0])} / bg {to_hex(eff[1])} 대비 {ratio:.2f}:1"
        )
        if ratio < cfg.contrast_large:
            results.append(
                row(GATE, "pair-contrast", "error",
                    detail + f" < {cfg.contrast_large} (대형 기준 미달)", path=str(theme_path))
            )
        elif ratio < cfg.contrast_normal:
            results.append(
                row(GATE, "pair-contrast-large-only", "warning",
                    detail + f" < {cfg.contrast_normal} — 대형 텍스트(≥24px) 전용",
                    path=str(theme_path))
            )
    return results


# ── 런타임 — 스틸 스캔 결과에서 텍스트 대비 실측 ────────────────────────────

def _is_large(font_size: float, font_weight: int) -> bool:
    """WCAG 대형 텍스트 — ≥24px, 또는 ≥18.66px 이면서 bold."""
    return font_size >= 24.0 or (font_size >= 18.66 and font_weight >= 700)


def run_runtime_scan(
    scan: dict,
    scene: str,
    declared: list[tuple[RGB, RGB]],
    cfg: QAConfig,
    seen: set,
) -> list[dict]:
    """스틸 스캔 items 의 텍스트 요소 대비를 재계산한다. seen 으로 중복 행을 제거한다."""
    results: list[dict] = []
    for it in scan.get("items", []):
        if not it.get("hasText"):
            continue
        fg_raw = parse_css_color(it["color"])
        if fg_raw is None:
            continue
        chain = [parse_css_color(c) for c in reversed(it.get("bgChain") or [])]
        bg_eff = composite_chain([c for c in chain if c], (255.0, 255.0, 255.0))
        fg_eff = composite_over(fg_raw, bg_eff)
        op = float(it.get("opacity", 1.0))
        if op < 1.0:
            # 누적 opacity 만큼 배경과 섞인 것으로 근사
            fg_eff = composite_over((*fg_eff, op), bg_eff)
        ratio = contrast_ratio(fg_eff, bg_eff)
        threshold = (
            cfg.contrast_large
            if _is_large(float(it["fontSize"]), int(it["fontWeight"]))
            else cfg.contrast_normal
        )
        pair_key = (to_hex(fg_eff), to_hex(bg_eff))

        if ratio + 1e-9 < threshold:
            key = ("low", scene, *pair_key)
            if key not in seen:
                seen.add(key)
                results.append(
                    row(GATE, "runtime-contrast", "error",
                        f"텍스트 {it['text'][:20]!r} fg {pair_key[0]} / bg {pair_key[1]} "
                        f"대비 {ratio:.2f}:1 < {threshold} "
                        f"(fontSize {it['fontSize']:.0f}px, opacity {op:.2f})",
                        scene=scene)
                )

        matched = any(
            rgb_close(fg_eff, d_fg, cfg.pair_match_tol)
            and rgb_close(bg_eff, d_bg, cfg.pair_match_tol)
            for d_fg, d_bg in declared
        )
        if not matched:
            key = ("undeclared", scene, *pair_key)
            if key not in seen:
                seen.add(key)
                # 대비 자체가 기준을 통과하면 정보성(선언 누락 안내), 미달이면 경고 —
                # 애니메이션 중간 합성색 등 선언 불가능한 통과 조합의 노이즈를 줄인다
                sev = "info" if ratio + 1e-9 >= threshold else "warning"
                results.append(
                    row(GATE, "undeclared-pair", sev,
                        f"미선언 색 조합 fg {pair_key[0]} / bg {pair_key[1]} "
                        f"(대비 {ratio:.2f}:1, 예: {it['text'][:20]!r}) — contrastPairs 에 없다",
                        scene=scene)
                )
    return results


def declared_effective_pairs(
    theme: str, serve_root: Path, cfg: QAConfig
) -> list[tuple[RGB, RGB]]:
    """런타임 대조용 — 선언 페어의 유효 (fg, bg) RGB 목록. 테마가 없으면 빈 리스트."""
    theme_path = find_theme_file(theme, serve_root, cfg)
    if theme_path is None:
        return []
    doc = json.loads(theme_path.read_text(encoding="utf-8"))
    try:
        pairs = resolved_pairs(doc)
    except KeyError:
        return []
    stage_bg_raw = parse_css_color(
        str(resolve_token(doc, ((doc.get("raw") or {}).get("palette") or {}).get("bg", "#FFFFFF")))
    )
    stage_bg: RGB = (
        composite_over(stage_bg_raw, (255.0, 255.0, 255.0)) if stage_bg_raw else (255.0, 255.0, 255.0)
    )
    out = []
    for p in pairs:
        eff = _pair_effective(p["fg"], p["bg"], stage_bg)
        if eff is not None:
            out.append(eff)
    return out
