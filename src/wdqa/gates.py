# 품질 게이트 오케스트레이션 — S(정적)→D(데이터)→R(런타임)→V(결정성), run_gates 공개 계약 (PLAN §7)
from __future__ import annotations

from pathlib import Path

from . import (
    gate1_mapping,
    gate2_length,
    gate3_contrast,
    gate4_font,
    gate5_overflow,
    gate6_determinism,
    gate7_framematch,
)
from .config import GATE_NAMES, QAConfig
from .entry import load_static_context
from .harness import open_session, scene_starts, still_times_for_scene
from .report import row, save_report

# 단계 구성 — 각 단계의 (게이트 번호, 단계 내 식별자)
_PHASES: list[tuple[str, list[int]]] = [
    ("S", [1, 3, 6]),   # 정적: 매핑·대비 페어·금지 식별자
    ("D", [2]),         # 데이터: 글자수 대비 길이
    ("R", [1, 3, 4, 5]),  # 런타임: 레이어·대비 실측·폰트·오버플로
    ("V", [6, 7]),      # 결정성: 이중 seek·frame-match
]

_NAME_TO_NUM = {v: k for k, v in GATE_NAMES.items()}


def _normalize_gates(gates: list[str] | None) -> set[int]:
    if not gates:
        return set(GATE_NAMES)
    out: set[int] = set()
    for g in gates:
        s = str(g).strip().lower()
        if s.startswith("gate"):
            s = s[4:]
        if s.isdigit() and int(s) in GATE_NAMES:
            out.add(int(s))
        elif s in _NAME_TO_NUM:
            out.add(_NAME_TO_NUM[s])
        else:
            raise ValueError(f"알 수 없는 게이트: {g!r} (1~7 또는 {sorted(_NAME_TO_NUM)})")
    return out


def run_gates(
    build_dir: Path,
    scenario: dict | None = None,
    gates: list[str] | None = None,
    *,
    config: QAConfig | None = None,
) -> dict:
    """빌드 엔트리에 품질 게이트를 실행한다.

    반환: {"passed": bool, "results": [{gate, rule, scene, path, severity, detail}, ...],
           "summary": {...}, "report_path": str}
    리포트는 data/qa_reports/{stamp}/qa.json 에도 저장된다.
    """
    cfg = config or QAConfig()
    requested = _normalize_gates(gates)
    results: list[dict] = []

    ctx = load_static_context(Path(build_dir))
    theme = (scenario or {}).get("tokens_theme") or "hwax-blue"
    scenario_scenes = {
        s.get("name"): s for s in ((scenario or {}).get("scenes") or [])
    }

    skipped_from: str | None = None

    def phase_failed(rows: list[dict]) -> bool:
        return any(r["severity"] == "error" for r in rows)

    # ── S 단계: 정적 ─────────────────────────────────────────────────────
    s_rows: list[dict] = []
    if 1 in requested:
        s_rows += gate1_mapping.run_static(ctx)
    if 3 in requested:
        s_rows += gate3_contrast.run_static(theme, ctx.serve_root, cfg)
    if 6 in requested:
        s_rows += gate6_determinism.run_static(ctx)
    results += s_rows
    if cfg.skip_on_phase_failure and phase_failed(s_rows):
        skipped_from = "D"

    # ── D 단계: 데이터 ───────────────────────────────────────────────────
    if skipped_from is None and 2 in requested:
        d_rows = gate2_length.run_data(scenario, cfg)
        results += d_rows
        if cfg.skip_on_phase_failure and phase_failed(d_rows):
            skipped_from = "R"

    # ── R + V 단계: 런타임 (하네스 1회 공유) ─────────────────────────────
    runtime_gates = ({1, 3, 4, 5} | {6, 7}) & requested
    if skipped_from is None and runtime_gates:
        r_rows: list[dict] = []
        v_rows: list[dict] = []
        try:
            with open_session(ctx.serve_root, ctx.entry_rel, cfg) as qs:
                # R — 씬 레이어 확인
                if 1 in requested:
                    r_rows += gate1_mapping.run_runtime(qs, cfg)
                # R — 스틸 시각 스캔 공유 (게이트 3R/4/5)
                scan_gates = {3, 4, 5} & requested
                if scan_gates:
                    runtime_scenes = qs.scenes() or ctx.scenes or []
                    starts = scene_starts(runtime_scenes)
                    preview = qs.preview_meta()
                    preview_still = (
                        float(preview["still"])
                        if preview and len(runtime_scenes) == 1
                        and isinstance(preview.get("still"), (int, float))
                        else None
                    )
                    declared = (
                        gate3_contrast.declared_effective_pairs(theme, ctx.serve_root, cfg)
                        if 3 in requested
                        else []
                    )
                    seen3: set = set()
                    seen4: set = set()
                    seen5: set = set()
                    for i, sc in enumerate(runtime_scenes):
                        name = sc["name"]
                        stills = still_times_for_scene(
                            sc, scenario_scenes.get(name), preview_still, cfg
                        )
                        for t_local in stills:
                            qs.seek(starts[i] + t_local)
                            scan = qs.scan()
                            if scan.get("error"):
                                r_rows.append(
                                    row(5, "scan-error", "error",
                                        f"스틸 스캔 실패: {scan['error']}", scene=name)
                                )
                                continue
                            if 3 in requested:
                                r_rows += gate3_contrast.run_runtime_scan(
                                    scan, name, declared, cfg, seen3
                                )
                            if 4 in requested:
                                r_rows += gate4_font.run_runtime_scan(scan, name, cfg, seen4)
                            if 5 in requested:
                                r_rows += gate5_overflow.run_runtime_scan(scan, name, cfg, seen5)
                results += r_rows
                if cfg.skip_on_phase_failure and phase_failed(r_rows):
                    skipped_from = "V"

                # V — 결정성·frame-match (같은 세션 재사용)
                if skipped_from is None:
                    if 6 in requested:
                        v_rows += gate6_determinism.run_runtime(qs, cfg)
                    if 7 in requested:
                        v_rows += gate7_framematch.run_runtime(qs, cfg)
                    results += v_rows
        except Exception as e:  # 하네스 자체 실패 — 리포트로 남긴다
            results.append(
                row(0, "harness-failure", "error",
                    f"런타임 하네스 실패: {type(e).__name__}: {e}", path=ctx.entry_rel)
            )

    if skipped_from is not None:
        results.append(
            row(0, "phase-skipped", "info",
                f"{skipped_from} 단계 이후를 생략했다 — 앞 단계 실패 (PLAN §7 S→D→R→V)")
        )

    gates_run = sorted(GATE_NAMES[g] for g in requested)
    report_path, report = save_report(
        results,
        build_dir=str(build_dir),
        entry=ctx.entry_rel,
        gates_run=gates_run,
        reports_root=cfg.reports_root,
    )
    return {
        "passed": report["passed"],
        "results": results,
        "summary": report["summary"],
        "report_path": str(report_path),
    }
