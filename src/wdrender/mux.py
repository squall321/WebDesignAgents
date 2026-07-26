# 렌더된 mp4 에 내레이션 mp3(+SRT soft subtitle)를 ffmpeg 로 먹싱하는 후처리 단계
from __future__ import annotations

import subprocess
from pathlib import Path


def probe_duration(path: str | Path) -> float:
    """ffprobe 로 컨테이너 길이(초)를 읽는다."""
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe 실패: {path}\n{proc.stderr.strip()}")
    return float(proc.stdout.strip())


def _has_stream(path: str | Path, kind: str) -> bool:
    """kind('a'|'s' 등) 스트림 존재 여부."""
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", kind,
            "-show_entries", "stream=codec_name",
            "-of", "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0 and bool(proc.stdout.strip())


def mux_audio(
    video_mp4: str | Path,
    audio_mp3: str | Path,
    out_mp4: str | Path,
    *,
    srt_path: str | Path | None = None,
    tolerance_sec: float = 1.0,
) -> dict:
    """영상+오디오를 결합한다 — 영상은 재인코딩 없이 복사(-c:v copy), 오디오는 aac.

    출력 길이는 항상 영상 길이 기준이다. 오디오가 짧으면 apad 로 무음을 채우고,
    길면 -t(영상 길이)로 잘라낸다(-shortest 미사용). srt_path 를 주면 soft subtitle
    트랙(mov_text)으로 임베드한다. 결과는 ffprobe 로 길이·오디오 스트림을 검증한다.

    반환: {out, video_sec, audio_sec, out_sec, has_subtitles}
    """
    video_mp4, audio_mp3, out_mp4 = Path(video_mp4), Path(audio_mp3), Path(out_mp4)
    video_sec = probe_duration(video_mp4)
    audio_sec = probe_duration(audio_mp3)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["ffmpeg", "-y", "-i", str(video_mp4), "-i", str(audio_mp3)]
    if srt_path:
        cmd += ["-i", str(srt_path)]
    cmd += ["-map", "0:v:0", "-map", "1:a:0"]
    if srt_path:
        cmd += ["-map", "2:s:0", "-c:s", "mov_text", "-metadata:s:s:0", "language=kor"]
    cmd += [
        "-c:v", "copy",
        "-c:a", "aac",
        "-af", "apad",          # 짧은 오디오는 무음 패드
        "-t", f"{video_sec:.3f}",  # 출력은 영상 길이 기준(긴 오디오는 절단)
        str(out_mp4),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.splitlines()[-15:])
        raise RuntimeError(f"ffmpeg 먹싱 실패 (exit {proc.returncode})\n{tail}")

    out_sec = probe_duration(out_mp4)
    if not _has_stream(out_mp4, "a"):
        raise RuntimeError(f"먹싱 결과에 오디오 스트림이 없습니다: {out_mp4}")
    if abs(out_sec - video_sec) > tolerance_sec:
        raise RuntimeError(
            f"먹싱 결과 길이 불일치: out={out_sec:.3f}s vs video={video_sec:.3f}s "
            f"(허용 ±{tolerance_sec}s)"
        )
    return {
        "out": str(out_mp4),
        "video_sec": round(video_sec, 3),
        "audio_sec": round(audio_sec, 3),
        "out_sec": round(out_sec, 3),
        "has_subtitles": _has_stream(out_mp4, "s"),
    }
