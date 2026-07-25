# 게이트 5 — 텍스트 오버플로: scrollWidth/Height 초과·스테이지(1920×1080) 이탈·safe margin 위반
from __future__ import annotations

from .config import QAConfig
from .report import row

GATE = 5


def run_runtime_scan(scan: dict, scene: str, cfg: QAConfig, seen: set) -> list[dict]:
    results: list[dict] = []
    stage = scan.get("stage") or {}
    sw, sh = float(stage.get("w", 1920)), float(stage.get("h", 1080))

    for it in scan.get("items", []):
        clip_ok = bool(it.get("clipOk"))
        r = it["rect"]
        # 텍스트 요소는 글리프 실측 rect(Range) 우선 — 중앙정렬 전폭 컨테이너 오탐 방지
        tr = it.get("textRect") if it.get("hasText") else None
        geo = tr or r
        label = it["text"][:24] if it.get("hasText") else f"<{it['tag']}>"

        # 1) 텍스트 스크롤 오버플로 — 내용이 컨테이너를 넘침
        if it.get("hasText") and (it["clientW"] > 0 or it["clientH"] > 0) and not clip_ok:
            over_w = it["scrollW"] - it["clientW"]
            over_h = it["scrollH"] - it["clientH"]
            if over_w > cfg.overflow_tol_px or over_h > cfg.overflow_tol_px:
                clipped = it.get("overflowX") != "visible" or it.get("overflowY") != "visible"
                key = ("scroll", scene, label)
                if key not in seen:
                    seen.add(key)
                    results.append(
                        row(GATE, "text-overflow", "error" if clipped else "warning",
                            f"{label!r} 내용 초과 — scroll {it['scrollW']}x{it['scrollH']} > "
                            f"client {it['clientW']}x{it['clientH']}"
                            + (" (클리핑됨)" if clipped else " (카드 밀림)"),
                            scene=scene)
                    )

        # 2) 스테이지 이탈 — 텍스트는 오류(내용 손실), 비텍스트는 경고(장식 블리드 가능)
        if not clip_ok:
            tol = cfg.stage_tol_px
            if (geo["x"] < -tol or geo["y"] < -tol
                    or geo["x"] + geo["w"] > sw + tol or geo["y"] + geo["h"] > sh + tol):
                sev = "error" if it.get("hasText") else "warning"
                key = ("stage", scene, label, round(geo["x"]), round(geo["y"]))
                if key not in seen:
                    seen.add(key)
                    results.append(
                        row(GATE, "stage-exit", sev,
                            f"{label!r} 가 스테이지 {sw:.0f}x{sh:.0f} 를 벗어남 — "
                            f"rect({geo['x']:.0f},{geo['y']:.0f},{geo['w']:.0f}x{geo['h']:.0f})"
                            + ("" if it.get("hasText") else " (비텍스트 — 의도 시 data-qa-clip-ok)"),
                            scene=scene)
                    )
                continue  # 이탈이면 safe margin 중복 보고 생략

        # 3) safe margin (텍스트 글리프 rect 기준, 경고)
        if it.get("hasText") and not clip_ok:
            m = cfg.safe_margin_px
            if (geo["x"] < m or geo["y"] < m
                    or geo["x"] + geo["w"] > sw - m or geo["y"] + geo["h"] > sh - m):
                key = ("margin", scene, label)
                if key not in seen:
                    seen.add(key)
                    results.append(
                        row(GATE, "safe-margin", "warning",
                            f"{label!r} 텍스트가 safe margin {m:.0f}px 이내로 접근 — "
                            f"rect({geo['x']:.0f},{geo['y']:.0f},{geo['w']:.0f}x{geo['h']:.0f})",
                            scene=scene)
                    )
    return results
