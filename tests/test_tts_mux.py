# mux 테스트 — 합성 미디어(lavfi)로 영상 길이 기준 먹싱·무음 패드·자막 트랙을 검증
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from wdrender.mux import mux_audio, probe_duration

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg 없음")


def _make_video(path: Path, sec: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c=black:s=320x240:d={sec}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def _make_audio(path: Path, sec: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"sine=frequency=440:duration={sec}",
            "-c:a", "libmp3lame",
            str(path),
        ],
        check=True,
        capture_output=True,
    )


def test_mux_pads_short_audio(tmp_path):
    """오디오(2s)가 영상(4s)보다 짧으면 무음 패드로 영상 길이를 유지한다."""
    video, audio, out = tmp_path / "v.mp4", tmp_path / "a.mp3", tmp_path / "out.mp4"
    _make_video(video, 4.0)
    _make_audio(audio, 2.0)
    result = mux_audio(video, audio, out)
    assert out.exists()
    assert abs(result["out_sec"] - result["video_sec"]) <= 1.0
    assert abs(result["video_sec"] - 4.0) <= 0.5
    assert result["has_subtitles"] is False


def test_mux_trims_long_audio(tmp_path):
    """오디오(6s)가 영상(3s)보다 길어도 출력은 영상 길이 기준이다."""
    video, audio, out = tmp_path / "v.mp4", tmp_path / "a.mp3", tmp_path / "out.mp4"
    _make_video(video, 3.0)
    _make_audio(audio, 6.0)
    result = mux_audio(video, audio, out)
    assert abs(result["out_sec"] - result["video_sec"]) <= 1.0
    assert probe_duration(out) < 4.5  # 6s 오디오에 끌려가지 않는다


def test_mux_embeds_srt(tmp_path):
    """srt_path 를 주면 mov_text soft subtitle 트랙이 실린다."""
    video, audio, out = tmp_path / "v.mp4", tmp_path / "a.mp3", tmp_path / "out.mp4"
    srt = tmp_path / "s.srt"
    _make_video(video, 3.0)
    _make_audio(audio, 2.0)
    srt.write_text("1\n00:00:00,000 --> 00:00:02,000\n자막 테스트\n", encoding="utf-8")
    result = mux_audio(video, audio, out, srt_path=srt)
    assert result["has_subtitles"] is True
