# 게이트 5 — 텍스트 오버플로: 자기 상자 넘침·스테이지 이탈·safe margin·형제 글자 겹침
#
# 규칙 넷 — ①자기 상자 넘침 ②스테이지 이탈 ③safe margin ④**형제 글자 겹침**.
#
# ④는 2026-11-17 모듈 심의가 남긴 것이다. 전제 3줄이 결정 패널을 14px 뚫고 확정 메타와
# 23px 겹친 화면이 그때 `passed: true` 0건으로 나왔다 — 각 요소가 **자기** 상자에는 꼭
# 맞고 스테이지 안에 있었기 때문이다. 겹친 글자는 대비·크기를 통과해도 읽을 수 없으니
# 하한선 문제이고(AX), 그래서 error 다.
#
# ⚠ 아직 **부모 상자(카드·패널) 이탈은 보지 않는다.** 겹칠 상대 없이 패널만 뚫고 나간
# 경우는 지금도 통과한다 — 하네스가 부모의 상자를 싣지 않는다. 자리를 옮기는 변경은
# 여전히 경계 조합을 직접 렌더해 확인해야 한다.

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

    results += _text_collisions(scan, scene, cfg, seen)
    return results


def _is_ancestor(items: list[dict], anc: int, desc: int) -> bool:
    """items[anc] 가 items[desc] 의 조상인가 — 하네스가 실어 준 parent 사슬을 탄다."""
    cur = items[desc].get("parent", -1)
    while isinstance(cur, int) and cur >= 0:
        if cur == anc:
            return True
        cur = items[cur].get("parent", -1)
    return False


def _text_collisions(scan: dict, scene: str, cfg: QAConfig, seen: set) -> list[dict]:
    """형제 글자 겹침 — 글리프 상자가 서로 침범하면 읽을 수 없다.

    **조상·자손 쌍은 뺀다.** 부모의 textRect 는 직계 텍스트 노드들의 합집합이라 그 사이에
    낀 자식 span(강조 수치 등)을 기하적으로 품는다 — 안 빼면 강조가 있는 문장이 전부
    겹침으로 잡힌다(실측으로 확인). 품는지로 판별하지 않고 **parent 사슬**로 판별하는
    까닭은, 큰 글자 안에 완전히 들어앉은 남남 글자가 진짜 겹침이기 때문이다.

    data-qa-clip-ok 가 붙은 쪽은 의도된 겹침으로 보고 건너뛴다.
    """
    items = scan.get("items", [])
    texts = [
        i for i, it in enumerate(items)
        if it.get("hasText") and it.get("textRect") and not it.get("clipOk")
    ]
    out: list[dict] = []
    tol = cfg.overflow_tol_px
    for a_pos, a in enumerate(texts):
        ra = items[a]["textRect"]
        for b in texts[a_pos + 1:]:
            if _is_ancestor(items, a, b) or _is_ancestor(items, b, a):
                continue
            rb = items[b]["textRect"]
            ox = min(ra["x"] + ra["w"], rb["x"] + rb["w"]) - max(ra["x"], rb["x"])
            oy = min(ra["y"] + ra["h"], rb["y"] + rb["h"]) - max(ra["y"], rb["y"])
            if ox <= tol or oy <= tol:
                continue
            la, lb = items[a]["text"][:24], items[b]["text"][:24]
            key = ("collide", scene, la, lb)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                row(GATE, "text-collision", "error",
                    f"{la!r} 와 {lb!r} 의 글자가 {ox:.0f}x{oy:.0f}px 겹친다 — "
                    "겹친 글자는 대비·크기를 통과해도 읽을 수 없다 "
                    "(의도한 겹침이면 data-qa-clip-ok)",
                    scene=scene)
            )
    return out
