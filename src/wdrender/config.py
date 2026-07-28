# configs/render.toml 을 읽어 렌더/export 공용 설정(RenderConfig)으로 제공하는 로더
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path

# repo 루트 = src/wdrender/config.py 기준 두 단계 위
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "render.toml"

EMU_PER_INCH = 914_400
# PowerPoint 표준 16:9 (13.333in × 7.5in) — 포맷 미지정 시 폴백
DEFAULT_SLIDE_W_EMU = 12_192_000
DEFAULT_SLIDE_H_EMU = 6_858_000


@dataclass
class RenderConfig:
    fps: int = 24
    width: int = 1920
    height: int = 1080
    viewport_margin: int = 60
    ffmpeg_args: list[str] = field(
        default_factory=lambda: ["-c:v", "libx264", "-pix_fmt", "yuv420p"]
    )
    default_still_progress: float = 0.9
    vendor_dir: Path | None = None
    slide_w_emu: int = DEFAULT_SLIDE_W_EMU
    slide_h_emu: int = DEFAULT_SLIDE_H_EMU
    format_id: str | None = None


def load_config(path: str | Path | None = None) -> RenderConfig:
    """render.toml 을 RenderConfig 로 로드한다. 파일이 없으면 기본값."""
    p = Path(path) if path else DEFAULT_CONFIG_PATH
    if not p.exists():
        return RenderConfig()
    with p.open("rb") as f:
        raw = tomllib.load(f)
    video = raw.get("video", {})
    vendor = raw.get("vendor", {})
    vendor_dir = vendor.get("dir")
    return RenderConfig(
        fps=int(video.get("fps", 24)),
        width=int(video.get("width", 1920)),
        height=int(video.get("height", 1080)),
        viewport_margin=int(video.get("viewport_margin", 60)),
        ffmpeg_args=list(raw.get("ffmpeg", {}).get("args", ["-c:v", "libx264", "-pix_fmt", "yuv420p"])),
        default_still_progress=float(raw.get("pptx", {}).get("default_still_progress", 0.9)),
        vendor_dir=(REPO_ROOT / vendor_dir) if vendor_dir else None,
    )


def inches_to_emu(inches: float) -> int:
    """인치 → EMU. 1000 EMU 격자로 반올림해 13.333in 표기가 PowerPoint 표준
    13⅓in(=12,192,000 EMU)으로 정확히 떨어지게 한다."""
    return int(round(inches * EMU_PER_INCH / 1000.0)) * 1000


def apply_format(cfg: RenderConfig, format_id: str | None) -> RenderConfig:
    """포맷 스펙의 stage·pptx 규격을 렌더 설정에 반영한다 (format_id 가 없으면 그대로).

    무대 크기의 정본은 포맷이고 render.toml 의 width/height 는 포맷 미지정 시의 폴백이다.
    """
    if not format_id:
        return cfg
    from wdpipeline.format import load_format  # 지연 import — wdrender 는 파이프라인에 의존하지 않는다

    spec = load_format(format_id)
    return replace(
        cfg,
        width=spec.stage.w,
        height=spec.stage.h,
        slide_w_emu=inches_to_emu(spec.pptx.slide_w_in),
        slide_h_emu=inches_to_emu(spec.pptx.slide_h_in),
        format_id=spec.id,
    )
