# 레이아웃 카탈로그 실측 스캔 — 21종 schema.json 에서 주 슬롯 상한·라벨 자수를 뽑아 표 재료를 만든다
"""실행: uv run python data/layout_check/catalog_scan.py

docs/analysis/layout-catalog.md 의 수치는 전부 이 스캔 결과다. 상한을 손으로 옮겨 적으면
스키마가 바뀔 때 문서가 조용히 거짓이 되므로, 표를 쓸 때마다 이 스크립트를 다시 돌린다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

# (템플릿 짧은 이름, 주 슬롯 경로) — 그 씬이 '데이터를 담는 자리'로 쓰는 배열
SLOTS: list[tuple[str, tuple[str, ...]]] = [
    ("opening", ("title",)), ("problem", ("failures",)), ("concept", ("nodes",)),
    ("process", ("steps",)), ("differentiator", ("flow",)), ("proof", ("cases",)),
    ("closing", ("stats",)), ("dataviz", ("bars",)), ("timeline", ("milestones",)),
    ("compare", ("rows",)), ("d-matrix", ("rows",)), ("d-media", ("files",)),
    ("d-multi", ("series",)),
    ("l-split", ("bullets",)), ("l-split", ("visual", "table", "rows")),
    ("l-list", ("rows",)), ("l-tree", ("nodes",)), ("l-quote", ("quote",)),
    ("l-kpi", ("metrics",)), ("l-quad", ("items",)), ("l-ba", ("before", "items")),
    ("l-mix", ("table", "rows")), ("l-mix", ("chart", "bars")),
]


def main() -> int:
    from wdpipeline.scenario import _cap, _floor, _lim, _node

    out = []
    for short, path in SLOTS:
        node = _node(short, *path)
        item = (node.get("items") or {}).get("properties") or {}
        labels = {k: v.get("maxLength") for k, v in item.items()
                  if isinstance(v, dict) and v.get("maxLength")}
        row = {
            "template": f"tpl.{short}",
            "slot": ".".join(path),
            "min": _floor(short, *path, default=0) or None,
            "max": _cap(short, *path, default=0) or None,
            "text_max": _lim(short, *path, default=0) or None,
            "labels": labels,
        }
        out.append(row)
        print(f"{row['template']:18s} {row['slot']:20s} "
              f"{str(row['min'] or '-'):>3s}~{str(row['max'] or row['text_max'] or '-'):<3s} "
              f"{json.dumps(labels, ensure_ascii=False)}")
    path = Path(__file__).parent / "catalog_slots.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"→ {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
