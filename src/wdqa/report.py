# 게이트 결과 행 생성·요약·qa.json 저장 (반환 계약: {"passed","results":[{gate,rule,scene,severity,detail}]})
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from .config import REPO_ROOT

SEVERITIES = ("error", "warning", "info")


def row(
    gate: int,
    rule: str,
    severity: str,
    detail: str,
    scene: str | None = None,
    path: str | None = None,
) -> dict:
    """리포트 행 1개. PLAN §7 형식 {gate, rule, scene, path, severity, detail}."""
    if severity not in SEVERITIES:
        raise ValueError(f"severity 는 {SEVERITIES} 중 하나: {severity!r}")
    return {
        "gate": gate,
        "rule": rule,
        "scene": scene,
        "path": path,
        "severity": severity,
        "detail": detail,
    }


def summarize(results: list[dict]) -> dict:
    """severity 별·게이트 별 건수 요약."""
    by_gate: dict[str, dict[str, int]] = {}
    counts = {s: 0 for s in SEVERITIES}
    for r in results:
        counts[r["severity"]] += 1
        g = by_gate.setdefault(str(r["gate"]), {s: 0 for s in SEVERITIES})
        g[r["severity"]] += 1
    return {**counts, "by_gate": by_gate}


def _reports_root(override: Path | None) -> Path:
    if override is not None:
        return Path(override)
    try:
        from wdcore.config import get_settings

        data_dir = Path(get_settings().data_dir)
    except Exception:
        data_dir = Path("data")
    if not data_dir.is_absolute():
        data_dir = REPO_ROOT / data_dir
    return data_dir / "qa_reports"


def save_report(
    results: list[dict],
    *,
    build_dir: str,
    entry: str,
    gates_run: list[str],
    reports_root: Path | None = None,
) -> tuple[Path, dict]:
    """data/qa_reports/{stamp}/qa.json 으로 저장하고 (경로, 리포트 dict)를 반환한다."""
    passed = not any(r["severity"] == "error" for r in results)
    report = {
        "passed": passed,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "build_dir": build_dir,
        "entry": entry,
        "gates_run": gates_run,
        "summary": summarize(results),
        "results": results,
    }
    stamp = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    out_dir = _reports_root(reports_root) / stamp
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "qa.json"
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_path, report
