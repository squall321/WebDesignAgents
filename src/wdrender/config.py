# configs/render.toml 을 읽어 렌더/export 공용 설정(RenderConfig)으로 제공하는 로더
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# repo 루트 = src/wdrender/config.py 기준 두 단계 위
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "configs" / "render.toml"


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
