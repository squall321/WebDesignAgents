# 헤드리스 영상 exporter — seek 프레임 루프로 PNG 시퀀스를 캡처하고 ffmpeg로 mp4 조립
from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .config import RenderConfig, load_config
from .page_session import RenderSession
from .server import StaticServer


def export_video(
    root_dir: str | Path,
    page_relpath: str | Path,
    out_path: str | Path,
    *,
    config: RenderConfig | None = None,
    resources: dict[str, str] | None = None,
    frames_dir: str | Path | None = None,
    keep_frames: bool = False,
    progress_every: int = 100,
    log: Callable[[str], None] = print,
) -> dict:
    """root_dir 서빙 트리의 page_relpath 엔트리를 mp4로 export 한다.

    반환: {duration, fps, frames, out} 요약 dict.
    """
    cfg = config or load_config()
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_frames = Path(frames_dir) if frames_dir else Path(tempfile.mkdtemp(prefix="wdr_frames_"))
    tmp_frames.mkdir(parents=True, exist_ok=True)

    with StaticServer(root_dir) as srv:
        url = srv.url_for(page_relpath)
        log(f"[export_video] 페이지 로드 {url}")
        with RenderSession(
            url,
            width=cfg.width,
            height=cfg.height,
            viewport_margin=cfg.viewport_margin,
            resources=resources,
        ) as sess:
            duration = sess.duration
            n_frames = round(duration * cfg.fps)
            log(
                f"[export_video] duration={duration}s fps={cfg.fps} frames={n_frames} "
                f"sync_seek={sess.sync_seek}"
            )
            for i in range(n_frames):
                t = i / cfg.fps
                sess.seek(t)
                sess.capture(tmp_frames / f"f_{i:06d}.png")
                if progress_every and (i + 1) % progress_every == 0:
                    log(f"[export_video] {i + 1}/{n_frames} 프레임 캡처")
            log(f"[export_video] 캡처 완료 → ffmpeg 조립")

    _assemble_mp4(tmp_frames, out_path, cfg)
    if not keep_frames and frames_dir is None:
        shutil.rmtree(tmp_frames, ignore_errors=True)
    log(f"[export_video] 완료 {out_path}")
    return {"duration": duration, "fps": cfg.fps, "frames": n_frames, "out": str(out_path)}


def _assemble_mp4(frames_dir: Path, out_path: Path, cfg: RenderConfig) -> None:
    """PNG 시퀀스를 ffmpeg로 mp4 조립한다."""
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(cfg.fps),
        "-i",
        str(frames_dir / "f_%06d.png"),
        *cfg.ffmpeg_args,
        str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.splitlines()[-15:])
        raise RuntimeError(f"ffmpeg 실패 (exit {proc.returncode})\n{tail}")


def verify_seek_determinism(
    sess: RenderSession, times: list[float], *, decoy_offset: float = 0.5
) -> list[dict]:
    """표본 시각별로 seek→캡처→다른 t 이탈→재-seek→재캡처 후 픽셀 해시 일치를 검사한다."""
    results = []
    for t in times:
        sess.seek(t)
        h1 = hashlib.sha256(sess.capture()).hexdigest()
        sess.seek((t + decoy_offset) % max(sess.duration, 1e-9))  # 이탈 프레임
        sess.seek(t)
        h2 = hashlib.sha256(sess.capture()).hexdigest()
        results.append({"time": t, "hash1": h1, "hash2": h2, "match": h1 == h2})
    return results


def _frame_max_channel_diff_ratio(png_a: Path, png_b: Path, channel_tol: int) -> float:
    """두 PNG 의 픽셀별 최대 채널 차이가 channel_tol 을 넘는 픽셀 비율(0~1)."""
    from PIL import Image
    import numpy as np

    a = np.asarray(Image.open(png_a).convert("RGB"), dtype=np.int16)
    b = np.asarray(Image.open(png_b).convert("RGB"), dtype=np.int16)
    if a.shape != b.shape:
        return 1.0
    diff = np.abs(a - b).max(axis=2)
    return float((diff > channel_tol).mean())


def verify_render_determinism(
    root_dir: str | Path,
    page_relpath: str | Path,
    *,
    config: RenderConfig | None = None,
    resources: dict[str, str] | None = None,
    channel_tol: int = 0,
    log: Callable[[str], None] = print,
) -> dict:
    """동일 입력을 **두 번 독립 렌더**(별도 세션·별도 PNG 시퀀스)해 결정성을 잰다.

    checklist M0 의 "동일 입력 2회 렌더 해시 일치 + perceptual diff 임계값 실측"을 충족한다.
    반환: {frames, hash_identical(bool), hash_mismatch(int), max_diff_ratio(float),
           mean_diff_ratio(float), mismatches:[{frame, sha_a, sha_b, diff_ratio}]}
    """
    cfg = config or load_config()
    d1 = Path(tempfile.mkdtemp(prefix="wdr_det_a_"))
    d2 = Path(tempfile.mkdtemp(prefix="wdr_det_b_"))
    try:
        r1 = export_video(root_dir, page_relpath, d1 / "a.mp4", config=cfg,
                          resources=resources, frames_dir=d1 / "frames", keep_frames=True, log=log)
        r2 = export_video(root_dir, page_relpath, d2 / "b.mp4", config=cfg,
                          resources=resources, frames_dir=d2 / "frames", keep_frames=True, log=log)
        n = min(r1["frames"], r2["frames"])
        mismatches, ratios, hash_mismatch = [], [], 0
        for i in range(n):
            pa, pb = d1 / "frames" / f"f_{i:06d}.png", d2 / "frames" / f"f_{i:06d}.png"
            ha = hashlib.sha256(pa.read_bytes()).hexdigest()
            hb = hashlib.sha256(pb.read_bytes()).hexdigest()
            if ha != hb:
                hash_mismatch += 1
                ratio = _frame_max_channel_diff_ratio(pa, pb, channel_tol)
                ratios.append(ratio)
                if len(mismatches) < 20:
                    mismatches.append({"frame": i, "sha_a": ha[:12], "sha_b": hb[:12], "diff_ratio": ratio})
        return {
            "frames": n,
            "frame_count_match": r1["frames"] == r2["frames"],
            "hash_identical": hash_mismatch == 0,
            "hash_mismatch": hash_mismatch,
            "max_diff_ratio": max(ratios) if ratios else 0.0,
            "mean_diff_ratio": (sum(ratios) / len(ratios)) if ratios else 0.0,
            "mismatches": mismatches,
        }
    finally:
        shutil.rmtree(d1, ignore_errors=True)
        shutil.rmtree(d2, ignore_errors=True)
