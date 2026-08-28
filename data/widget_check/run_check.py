# 위젯 구조 어댑터 커버리지 실측 — 실물 보고서 + 합성 픽스처 38종을 훑어 coverage_report.json 을 낸다
"""실행: uv run python data/widget_check/run_check.py

산출: data/widget_check/coverage_report.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from wdpipeline.fragmentize import fragmentize          # noqa: E402
from wdpipeline.ingest import ingest_report_file        # noqa: E402
from wdpipeline.widgets import (                        # noqa: E402
    GROUP_BY_TYPE,
    collect_media,
    coverage_stats,
    extract_structured,
    structured_summary,
)

HERE = Path(__file__).parent


def _real() -> dict:
    norm = ingest_report_file(REPO / "examples" / "reportarchive" / "report_sample.json")
    frags = fragmentize(norm)
    return {
        "source": "examples/reportarchive/report_sample.json",
        "coverage": coverage_stats(norm),
        "fragments": len(frags),
        "fragments_with_structured": sum(1 for f in frags if "structured" in f),
        "media": len(collect_media(norm)),
        "summaries": [
            {"block_id": f["source"]["block_id"], "widget": f["widget"],
             "summary": f["text"].split(" — ")[0]}
            for f in frags if "structured" in f
        ],
    }


def _synthetic() -> dict:
    blocks = json.loads((HERE / "synthetic_blocks.json").read_text(encoding="utf-8"))["blocks"]
    rows, ok, failed, text, unknown = [], 0, 0, 0, 0
    for b in blocks:
        group = GROUP_BY_TYPE.get(b["type"])
        payload = extract_structured(b)
        if group is None:
            unknown += 1
            status = "unknown"
        elif group == "text":
            text += 1
            status = "text" if payload is None else "UNEXPECTED_PAYLOAD"
        elif payload is None:
            failed += 1
            status = "FAILED"
        else:
            ok += 1
            status = "ok"
        rows.append({
            "type": b["type"], "group": group, "status": status,
            "kind": payload.get("kind") if payload else None,
            "summary": structured_summary(payload),
        })
    return {
        "source": "data/widget_check/synthetic_blocks.json",
        "blocks": len(blocks),
        "structured_ok": ok, "failed": failed, "text_group": text, "unknown": unknown,
        "rows": rows,
    }


def main() -> int:
    report = {"real": _real(), "synthetic": _synthetic()}
    (HERE / "coverage_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    r, s = report["real"], report["synthetic"]
    c = r["coverage"]
    print(f"[실물] 블록 {c['total_blocks']} · 구조 성공 {c['structured']} · 실패 {c['failed']} "
          f"· 텍스트군 {c['text_group']} · 미지 {c['unknown_types']}")
    print(f"[실물] 조각 {r['fragments']} (구조 동반 {r['fragments_with_structured']}) "
          f"· 미디어 자산 {r['media']}")
    print(f"[합성] 블록 {s['blocks']} · 구조 성공 {s['structured_ok']} · 실패 {s['failed']} "
          f"· 텍스트군 {s['text_group']} · 미지 {s['unknown']}")
    return 1 if (c["failed"] or s["failed"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
