# 게이트 7 — frame-match: 씬 첫/끝 인접 프레임 픽셀 diff 비율이 임계 이하인지 검사
from __future__ import annotations

import io

from PIL import Image, ImageChops

from .config import QAConfig
from .harness import QASession, scene_starts
from .report import row

GATE = 7


def pixel_diff_ratio(png_a: bytes, png_b: bytes, channel_tol: int) -> float:
    """채널 diff 가 tol 초과인 픽셀의 비율 (0.0~1.0)."""
    im_a = Image.open(io.BytesIO(png_a)).convert("RGB")
    im_b = Image.open(io.BytesIO(png_b)).convert("RGB")
    if im_a.size != im_b.size:
        return 1.0
    diff = ImageChops.difference(im_a, im_b)
    r, g, b = diff.split()
    m = ImageChops.lighter(ImageChops.lighter(r, g), b)
    hist = m.histogram()
    changed = sum(hist[channel_tol + 1 :])
    total = im_a.size[0] * im_a.size[1]
    return changed / total if total else 1.0


def _capture_at(qs: QASession, t: float) -> bytes:
    qs.seek(t)
    return qs.capture()


def run_runtime(qs: QASession, cfg: QAConfig) -> list[dict]:
    """씬별 (t=0 vs 1/fps), (t=end-2/fps vs end-1/fps) 프레임 diff 비율 검사.

    end = min(nat, dur) — nat 미지정 씬은 dur. 경계 프레임이 정적이어야 컷이 깨끗하다.
    """
    results: list[dict] = []
    scenes = qs.scenes()
    if not scenes:
        results.append(row(GATE, "runtime-scenes", "error", "런타임 OM_SCENES 를 읽지 못했다"))
        return results
    fps = cfg.resolved_fps()
    step = 1.0 / fps
    starts = scene_starts(scenes)
    for i, s in enumerate(scenes):
        name = s["name"]
        dur = float(s["dur"])
        end_local = min(float(s.get("nat") or dur), dur)
        pairs = [("head", starts[i], starts[i] + step)]
        if end_local >= 2 * step:
            pairs.append(
                ("tail", starts[i] + end_local - 2 * step, starts[i] + end_local - step)
            )
        for kind, ta, tb in pairs:
            ratio = pixel_diff_ratio(
                _capture_at(qs, ta), _capture_at(qs, tb), cfg.frame_diff_channel_tol
            )
            if ratio > cfg.frame_match_max_ratio:
                results.append(
                    row(GATE, f"frame-match-{kind}", "error",
                        f"{kind} 프레임 diff 비율 {ratio:.4f} > {cfg.frame_match_max_ratio} "
                        f"(t={ta:.3f}s vs {tb:.3f}s, fps={fps})",
                        scene=name)
                )
    return results
