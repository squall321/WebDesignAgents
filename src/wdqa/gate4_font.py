# 게이트 4 — 최소 폰트 크기: 스틸 실측 computed fontSize ≥ 24px (data-qa-icon 면제)
from __future__ import annotations

from .config import QAConfig
from .report import row

GATE = 4


def run_runtime_scan(scan: dict, scene: str, cfg: QAConfig, seen: set) -> list[dict]:
    results: list[dict] = []
    for it in scan.get("items", []):
        if not it.get("hasText") or it.get("iconOk"):
            continue
        size = float(it["fontSize"])
        if size + 1e-6 < cfg.min_font_px:
            key = (scene, round(size, 1), it["text"][:20])
            if key in seen:
                continue
            seen.add(key)
            results.append(
                row(GATE, "min-font", "error",
                    f"텍스트 {it['text'][:24]!r} fontSize {size:.1f}px < {cfg.min_font_px:.0f}px",
                    scene=scene)
            )
    return results
