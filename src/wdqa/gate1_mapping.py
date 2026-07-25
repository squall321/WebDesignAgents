# 게이트 1 — OM_SCENES ↔ 씬 맵 키 일치 (정적 정규식 근사 + 런타임 씬 레이어 DOM 확인)
from __future__ import annotations

from .config import QAConfig
from .entry import StaticContext, extract_scene_map_keys
from .harness import QASession, scene_starts
from .report import row

GATE = 1


def run_static(ctx: StaticContext) -> list[dict]:
    """엔트리 OM_SCENES 파싱(ssParse 미러) + scenes.jsx 씬 맵 키 양방향 대조."""
    results: list[dict] = []
    if ctx.scenes is None:
        results.append(
            row(GATE, "om-scenes-parse", "error",
                ctx.scenes_error or "OM_SCENES 파싱 실패", path=ctx.entry_rel)
        )
        return results

    names = [s["name"] for s in ctx.scenes]
    dup = {n for n in names if names.count(n) > 1}
    if dup:
        results.append(
            row(GATE, "om-scenes-duplicate", "error",
                f"OM_SCENES 씬 이름 중복: {sorted(dup)}", path=ctx.entry_rel)
        )

    keys, src_label = extract_scene_map_keys(ctx.sources)
    if keys is None:
        results.append(
            row(GATE, "scene-map-extract", "info",
                "씬 맵 객체 리터럴을 정적으로 찾지 못했다 — 런타임 검사로 위임",
                path=ctx.entry_rel)
        )
        return results

    missing = [n for n in names if n not in keys]      # OM_SCENES 에 있으나 맵에 없음
    orphan = [k for k in keys if k not in names]       # 맵에 있으나 OM_SCENES 에 없음
    for n in missing:
        results.append(
            row(GATE, "map-missing", "error",
                f"OM_SCENES 씬 {n!r} 이 씬 맵({src_label})에 없다", scene=n, path=src_label)
        )
    for k in orphan:
        results.append(
            row(GATE, "map-orphan", "error",
                f"씬 맵 키 {k!r} 가 OM_SCENES 에 없다 (죽은 씬)", scene=k, path=src_label)
        )
    return results


def run_runtime(qs: QASession, cfg: QAConfig) -> list[dict]:
    """각 씬 시작+offset 으로 seek 후 활성 씬 레이어 DOM 이 비어있지 않은지 확인."""
    results: list[dict] = []
    scenes = qs.scenes()
    if not scenes:
        results.append(
            row(GATE, "runtime-scenes", "error",
                "런타임 window.OM_SCENES 를 읽지 못했다")
        )
        return results
    starts = scene_starts(scenes)
    for i, s in enumerate(scenes):
        t = min(starts[i] + cfg.seek_probe_offset, starts[i + 1] - 1e-3)
        qs.seek(t)
        chk = qs.layer_check(i)
        if not chk.get("ok"):
            results.append(
                row(GATE, "runtime-layer", "error",
                    f"씬 레이어[{i}] 검사 실패 (t={t:.2f}s): {chk}", scene=s["name"])
            )
    return results
