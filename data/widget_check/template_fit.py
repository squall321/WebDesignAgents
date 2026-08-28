# 구조 payload 가 현 씬 템플릿 카탈로그에 실제로 실리는지 실측 — 용량(maxItems)·라벨 길이(maxLength)를 schema.json 에서 읽어 대조
"""실행: uv run python data/widget_check/template_fit.py

산출: data/widget_check/template_fit_report.json

`extract_structured` 가 구조를 살려도 그것을 **받아줄 씬 템플릿 슬롯**이 없으면
화면까지 못 간다. 이 스크립트는 카탈로그 schema.json 의 maxItems/maxLength 를 직접
읽어 payload 를 대조하고, 담기는 건 / 넘치는 건 / 받을 슬롯 자체가 없는 건을 센다.
'신규 템플릿 필요' 목록은 여기서 나온 미수용 목록이 근거다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from wdpipeline.fragmentize import fragmentize          # noqa: E402
from wdpipeline.ingest import ingest_report_file        # noqa: E402
from wdpipeline.widgets import extract_structured       # noqa: E402

HERE = Path(__file__).parent
TPL_ROOT = REPO / "modules" / "scene-templates"

# payload 의 항목 배열을 받아줄 템플릿 슬롯 — (템플릿 id, 배열 프로퍼티, 라벨 필드)
SLOTS: dict[str, tuple[str, str]] = {
    "process": ("steps", "name"),
    "timeline": ("milestones", "name"),
    "dataviz": ("bars", "label"),
    "compare": ("rows", "aspect"),
    "concept": ("nodes", "name"),
    "proof": ("cases", "title"),
    "closing": ("stats", "d"),
    "v-stack": ("cards", "title"),
    # 창작 모드 위젯 수용 3종 (2026-07-27) — §9 #1·#2·#4 해소분
    "d-matrix": ("rows", "label"),
    "d-media": ("files", "caption"),
    "d-multi": ("series", "name"),
}


def slot_caps() -> dict[str, dict]:
    """schema.json 에서 슬롯별 maxItems / 라벨 maxLength 를 읽는다 (하드코딩 금지)."""
    caps: dict[str, dict] = {}
    for tpl, (prop, label_key) in SLOTS.items():
        sch = json.loads((TPL_ROOT / tpl / "schema.json").read_text(encoding="utf-8"))
        node = sch["properties"][prop]
        item_props = (node.get("items") or {}).get("properties") or {}
        caps[tpl] = {
            "prop": prop,
            "max_items": node.get("maxItems"),
            "label_key": label_key,
            "label_max": (item_props.get(label_key) or {}).get("maxLength"),
        }
    return caps


def target_slot(payload: dict) -> tuple[str | None, list[str], str]:
    """payload → (템플릿 id, 항목 라벨 목록, 사유). 받을 슬롯이 없으면 (None, [], 사유)."""
    kind = payload.get("kind")

    if kind == "graph":
        nodes = payload.get("nodes") or []
        labels = [str(n.get("label", "")) for n in nodes]
        shape = payload.get("shape")
        if shape == "flow":
            return "process", labels, "순차 단계 → steps"
        # tree/network 는 concept 의 방사형 nodes 로만 받는다 — 계층/엣지는 잃는다
        return "concept", labels, f"{shape} → concept.nodes (계층·엣지 손실)"

    if kind == "series":
        entries = payload.get("series") or []
        labels = [str(e.get("label", "")) for e in entries]
        if any(e.get("group") for e in entries):
            groups = list(dict.fromkeys(str(e["group"]) for e in entries if e.get("group")))
            return "d-multi", groups, "다계열 → d-multi.series (그룹 막대 2~4계열)"
        if any(e.get("value") is None for e in entries):
            return None, labels, "분포형(values/n) — 단일 수치 막대로 환원 불가 (§9 #7 잔존)"
        return "dataviz", labels, "단일 계열 → bars"

    if kind == "timeline":
        ms = payload.get("milestones") or []
        return "timeline", [str(m.get("label", "")) for m in ms], "milestone → milestones"

    if kind == "table":
        cols = payload.get("columns") or []
        rows = payload.get("rows") or []
        first = cols[0]["key"] if cols else ""
        labels = [str(r.get(first, "")) for r in rows]
        if len(cols) == 3:
            return "compare", labels, "2안 비교 → compare.rows(a/b)"
        if len(cols) >= 3:
            return "d-matrix", labels, f"{len(cols)}열 격자 → d-matrix.rows (열≤8·행≤8)"
        return None, labels, f"{len(cols)}열 — 격자 스키마 하한(3열) 미달"

    if kind == "pairs":
        pairs = payload.get("pairs") or []
        return "closing", [str(p.get("label", "")) for p in pairs], "키값 → closing.stats"

    if kind == "media":
        files = payload.get("files") or []
        return ("d-media", [str(f.get("caption", "")) for f in files],
                "미디어 자산 → d-media.files (1~3장, 해결 자산 전제)")

    return None, [], f"미지 kind={kind}"


def judge(payload: dict, caps: dict[str, dict]) -> dict:
    tpl, labels, reason = target_slot(payload)
    out = {
        "kind": payload.get("kind"),
        "shape": payload.get("shape"),
        "items": len(labels),
        "template": tpl,
        "reason": reason,
    }
    if tpl is None:
        out["fit"] = "none"
        return out
    cap = caps[tpl]
    out["slot"] = f"{tpl}.{cap['prop']}"
    out["capacity"] = cap["max_items"]
    lmax = cap["label_max"]
    long = [x for x in labels if lmax and len(x) > lmax] if lmax else []
    out["label_max"] = lmax
    out["labels_over_limit"] = len(long)
    out["label_sample"] = long[0][:40] if long else ""
    if cap["max_items"] is not None and len(labels) > cap["max_items"]:
        out["fit"] = "overflow"        # 항목 수가 슬롯 용량을 넘는다 — 잘라야 들어간다
    elif long:
        out["fit"] = "trim"            # 개수는 맞지만 라벨이 maxLength 초과 — 요약 필요
    else:
        out["fit"] = "ok"              # 구조를 그대로 실을 수 있다
    # d-* 는 2축 격자라 행/계열 외에 열/항목 축도 상한이 있다 — 넘으면 overflow 로 강등
    if tpl == "d-matrix":
        ncols = len(payload.get("columns") or [])
        out["cols"] = ncols
        if ncols > 8:
            out["fit"] = "overflow"
            out["reason"] += f" · 열 {ncols}>8 — 열 선별 필요"
    if tpl == "d-multi":
        ncats = len({str(e.get("label", "")) for e in payload.get("series") or []})
        out["categories"] = ncats
        if ncats > 7:
            out["fit"] = "overflow"
            out["reason"] += f" · 항목 {ncats}>7 — 항목 선별 필요"
    return out


def scan(name: str, blocks: list[tuple[str, dict]], caps: dict) -> dict:
    rows = []
    for block_id, block in blocks:
        payload = extract_structured(block)
        if payload is None:
            continue
        rec = judge(payload, caps)
        rec["block_id"] = block_id
        rec["widget"] = block.get("type")
        rows.append(rec)
    tally = {"ok": 0, "trim": 0, "overflow": 0, "none": 0}
    for r in rows:
        tally[r["fit"]] += 1
    return {"source": name, "structured_blocks": len(rows), "tally": tally, "rows": rows}


def main() -> int:
    caps = slot_caps()

    norm = ingest_report_file(REPO / "examples" / "reportarchive" / "report_sample.json")
    real_blocks = [
        (str(b.get("id")), b) for p in norm.get("pages", []) for b in p.get("blocks", [])
    ]
    frags = fragmentize(norm)

    syn = json.loads((HERE / "synthetic_blocks.json").read_text(encoding="utf-8"))["blocks"]
    syn_blocks = [(str(b.get("type")), b) for b in syn]

    report = {
        "slot_caps": caps,
        "real": scan("examples/reportarchive/report_sample.json", real_blocks, caps),
        "synthetic": scan("data/widget_check/synthetic_blocks.json", syn_blocks, caps),
        "fragments": {
            "total": len(frags),
            "with_structured": sum(1 for f in frags if "structured" in f),
        },
    }
    (HERE / "template_fit_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    for key in ("real", "synthetic"):
        s = report[key]
        t = s["tally"]
        n = s["structured_blocks"]
        pct = (100 * (t["ok"] + t["trim"]) / n) if n else 0.0
        print(f"[{key}] 구조 블록 {n} · 그대로 {t['ok']} · 라벨 축약 필요 {t['trim']} "
              f"· 용량 초과 {t['overflow']} · 슬롯 없음 {t['none']} → 슬롯 도달 {pct:.0f}%")
    miss: dict[str, set[str]] = {}
    for key in ("real", "synthetic"):
        for r in report[key]["rows"]:
            if r["fit"] in ("overflow", "none"):
                miss.setdefault(r["reason"], set()).add(str(r["widget"]))
    print("[신규 템플릿 필요 — 미수용 사유별]")
    for reason, widgets in sorted(miss.items()):
        print(f"  - {reason}: {', '.join(sorted(widgets))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
