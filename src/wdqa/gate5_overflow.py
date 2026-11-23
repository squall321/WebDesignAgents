# 게이트 5 — 오버플로: 자기 상자 넘침·스테이지 이탈·safe margin·형제 글자 겹침·부모 상자 이탈
#
# 규칙 다섯 — ①자기 상자 넘침 ②스테이지 이탈 ③safe margin ④**형제 글자 겹침**
# ⑤**부모 상자(카드·패널) 이탈**.
#
# ④는 2026-11-17 모듈 심의가 남긴 것이다. 전제 3줄이 결정 패널을 14px 뚫고 확정 메타와
# 23px 겹친 화면이 그때 `passed: true` 0건으로 나왔다 — 각 요소가 **자기** 상자에는 꼭
# 맞고 스테이지 안에 있었기 때문이다. 겹친 글자는 대비·크기를 통과해도 읽을 수 없으니
# 하한선 문제이고(AX), 그래서 error 다.
#
# ④와 ⑤는 서로를 대신하지 못한다 — 전제 3줄 화면은 상자만 넘고 글자는 패널 안이라 ⑤가
# 0건이고 ④가 잡으며, 전제 4줄이 되어 글자가 나가면 ⑤가 잡는다. 둘 다 넣기 전에 산출물
# 9건(포맷 6종)으로 재서 거짓 양성 0건을 확인했다.

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
    results += _box_exits(scan, scene, cfg, seen)
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
def _box_exits(scan: dict, scene: str, cfg: QAConfig, seen: set) -> list[dict]:
    """글자가 자기 카드·패널 밖으로 나갔는가.

    상자는 **배경이나 테두리를 자기가 그리는 가장 가까운 조상**이다 — 사람이 "카드 밖으로
    삐져나왔다" 고 말할 때의 그 카드다. 스테이지 전체는 ②가 이미 보므로 여기서 다시 보지
    않는다(하네스가 foreignObject 바깥을 올라가지 않아 자연히 제외된다).

    **글자(textRect)로 잰다. 상자(rect)로 재지 않는다** — 그림자·절대배치 칩처럼 레이아웃
    상자가 부모를 넘는 정상 요소가 많고, 눈에 보이는 손상은 글자가 나갔을 때 난다. 실측:
    전제 3줄 화면은 상자만 넘고 글자는 패널 안이라 여기서 0건이고(그 화면의 피해는 메타와의
    겹침이라 ④가 잡는다), 전제 4줄이 되어 글자가 나가면 68px 넘침으로 잡힌다.

    **대비 게이트의 전제도 함께 깨진다** — 게이트 3 은 조상들의 배경(bgChain)을 그 글자의
    바탕으로 보는데, 글자가 상자 밖에 그려지면 실제 바탕은 그게 아니다. 그래서 error 다.
    """
    out: list[dict] = []
    tol = cfg.overflow_tol_px
    for it in scan.get("items", []):
        if not (it.get("hasText") and it.get("textRect") and it.get("boxRect")):
            continue
        if it.get("clipOk"):
            continue
        g, b = it["textRect"], it["boxRect"]
        over = max(b["x"] - g["x"], g["x"] + g["w"] - (b["x"] + b["w"]),
                   b["y"] - g["y"], g["y"] + g["h"] - (b["y"] + b["h"]))
        if over <= tol:
            continue
        label = it["text"][:24]
        key = ("boxexit", scene, label)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            row(GATE, "box-exit", "error",
                f"{label!r} 의 글자가 자기 상자({b['w']:.0f}x{b['h']:.0f})를 "
                f"{over:.0f}px 벗어났다 — 카드 밖에 그려지면 대비 판정의 바탕도 틀려진다 "
                "(의도한 삐져나옴이면 data-qa-clip-ok)",
                scene=scene)
        )
    return out
