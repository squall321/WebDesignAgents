# 내레이션 단계 — VoiceRecorder 실측 길이로 씬 dur 를 다시 잡고, 씬 음성을 새 시각에 놓아 트랙·자막을 만들어 먹싱한다
"""렌더 앞뒤 두 단계로 나뉜다 (결정 56~59).

prepare: 실측 → dur 재조정 → 검증 → 시나리오 반영·재빌드   (영상 렌더 전에)
finish : 트랙·자막 조립 → 먹싱(기본 영상 파일 교체) → drift_report  (영상 렌더 뒤에)

CLI·MCP·웹이 같은 두 함수를 부른다. VoiceRecorder 가 네트워크 너머에 있어
오프라인 렌더 노드(--network=none)에서는 prepare 가 연결 실패로 멈춘다.
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import wave
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import httpx

from wdcore.models.scenario import ScenarioDoc, narration_sha
from wdqa.config import QAConfig

# 컷 뒤 말이 시작되기 전 여유, 말이 끝나고 다음 컷까지의 숨 (결정 56)
LEAD_SEC = 0.3
TAIL_SEC = 0.5
# 포맷에 presets.narration.max_silence 가 없을 때의 무음 경고 기준 (결정 18 의 (a))
DEFAULT_MAX_SILENCE_SEC = 3.0
# 화면 늘이기 한계는 게이트 2 와 같은 값이어야 한다 — 어긋나면 재조정이 통과시킨 씬을 게이트가 경고한다
STRETCH_LIMIT = QAConfig().stretch_limit
# 씬 dur 최대 (SceneEntry 계약, 렌더 엔진 ssParse)
_MAX_DUR = 300.0
_WS_RE = re.compile(r"\s+")


class NarrationError(RuntimeError):
    """내레이션 때문에 렌더를 멈춰야 하는 실패 — 메시지는 사람이 고칠 거리를 말한다."""


@dataclass
class SceneTiming:
    """씬 하나의 재조정 결과 — drift_report 의 한 줄."""

    name: str
    old_dur: float
    new_dur: float
    nat: float | None
    start_sec: float                    # 새 타임라인에서 씬이 시작하는 시각
    spoken_sec: float | None = None     # 실측 낭독 (내레이션 없는 씬은 None)
    text: str = ""
    audio_path: str | None = None
    flags: list[str] = field(default_factory=list)
    advice: list[str] = field(default_factory=list)

    @property
    def speech_start_sec(self) -> float:
        return self.start_sec + LEAD_SEC

    @property
    def silence_sec(self) -> float | None:
        return None if self.spoken_sec is None else round(self.new_dur - self.spoken_sec, 3)


def _nonspace(text: str) -> int:
    return len(_WS_RE.sub("", text))


def _ceil_tenth(value: float) -> float:
    """0.1초 단위로 올린다 — 게이트 2 의 최소 dur 제안과 같은 단위."""
    return round(math.ceil(value * 10 - 1e-6) / 10, 1)


def retime(
    doc: ScenarioDoc,
    spoken: dict[str, float],
    *,
    max_silence: float = DEFAULT_MAX_SILENCE_SEC,
    stretch_limit: float = STRETCH_LIMIT,
) -> tuple[ScenarioDoc, list[SceneTiming]]:
    """실측 낭독 길이(씬 이름 → 초)로 씬 dur 를 다시 잡는다 (결정 56).

    - 내레이션 씬: dur = 앞 여유 + 실측 + 뒤 여유. 단 nat×(1−한계) 아래로는 줄이지 않는다.
      nat×(1+한계)를 넘어도 늘리고 stretch-limit 로 남긴다 — 말은 자르거나 빨리 하지 않는다.
    - 말 없는 씬: dur 그대로.
    - stills 는 새 dur 에 비례해 옮긴다. 화면 안무가 nat/dur 로 늘고 줄어서 같은 장면을 가리킨다.
    - 실측 길이·원문 해시를 씬에 남겨 게이트 2 가 추정 대신 쓰게 한다 (결정 57).
    """
    timings: list[SceneTiming] = []
    scenes = []
    cursor = 0.0
    for s in doc.scenes:
        text = s.narration.strip()
        sec = spoken.get(s.name) if text else None
        if sec is None:
            new = s.dur
        else:
            ref = s.nat or s.dur   # nat 이 없으면 지금 dur 를 화면 기준으로 본다
            new = max(_ceil_tenth(LEAD_SEC + sec + TAIL_SEC), _ceil_tenth(ref * (1 - stretch_limit)))
            if new > _MAX_DUR:
                raise NarrationError(
                    f"씬 {s.name!r} 의 내레이션이 {sec:.1f}초라 씬 최대 길이 {_MAX_DUR:g}초를 넘는다 — 씬을 나누라"
                )
        t = SceneTiming(
            name=s.name, old_dur=s.dur, new_dur=new, nat=s.nat,
            start_sec=round(cursor, 3), spoken_sec=sec, text=text,
        )
        if sec is not None:
            cps = _nonspace(text) / sec if sec > 0 else 0.0
            if s.nat and new > s.nat * (1 + stretch_limit) + 1e-9:
                over = new - s.nat * (1 + stretch_limit)
                t.flags.append("stretch-limit")
                t.advice.append(
                    f"내레이션이 화면 늘이기 한계(nat {s.nat:g}초의 +{stretch_limit:.0%})를 {over:.1f}초 넘는다 "
                    f"— 약 {math.ceil(over * cps)}자 줄이면 한계 안에 든다"
                )
            if t.silence_sec is not None and t.silence_sec > max_silence + 1e-9:
                t.flags.append("silence")
                t.advice.append(
                    f"말 없는 시간이 {t.silence_sec:.1f}초다(기준 {max_silence:g}초) — 화면 문구를 읽는 문장을 "
                    f"약 {math.ceil((t.silence_sec - max_silence) * cps)}자 덧붙이면 무음이 줄어든다"
                )
        timings.append(t)

        scale = new / s.dur
        update: dict = {"dur": new, "stills": [min(new, round(x * scale, 2)) for x in s.stills]}
        if sec is not None:
            update |= {"narration_sec": round(sec, 3), "narration_sha": narration_sha(text)}
        scenes.append(s.model_copy(update=update))
        cursor += new

    meta = doc.meta.model_copy(update={"duration_sec": round(cursor, 2)})
    # model_copy 는 검증을 건너뛴다 — 한 번 더 통째로 검증해 stills 범위 등을 확인한다
    new_doc = ScenarioDoc.model_validate(doc.model_copy(update={"scenes": scenes, "meta": meta}).model_dump())
    return new_doc, timings


# ── 트랙·자막 ────────────────────────────────────────────────────────────────


def _wav_params(path: Path) -> tuple[int, int, int]:
    with wave.open(str(path), "rb") as w:
        return w.getnchannels(), w.getsampwidth(), w.getframerate()


def _ffmpeg(args: list[str], what: str) -> None:
    proc = subprocess.run(["ffmpeg", "-y", "-v", "error", *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"{what} 실패 (ffmpeg exit {proc.returncode})\n{proc.stderr.strip()[-800:]}")


def assemble_track(placements: list[tuple[float, Path]], total_sec: float, out_wav: Path) -> Path:
    """씬 음성 wav 들을 절대 시각(초)에 놓아 total_sec 길이의 16비트 wav 하나로 만든다.

    첫 파일의 채널·레이트가 기준이다. 형식이 다른 파일은 ffmpeg 로 맞춘다.
    시각 계산을 WDA 가 하는 이유는 결정 58 — VoiceRecorder 의 씬 간격은 10초 상한이 있다.
    """
    if not placements:
        raise ValueError("놓을 씬 음성이 없다")
    channels, _, rate = _wav_params(placements[0][1])
    frame = channels * 2
    buf = bytearray(int(math.ceil(total_sec * rate)) * frame)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    for start, path in placements:
        src = path
        if _wav_params(path) != (channels, 2, rate):
            src = out_wav.parent / f"_conv_{path.stem}.wav"
            _ffmpeg(["-i", str(path), "-ac", str(channels), "-ar", str(rate), "-c:a", "pcm_s16le", str(src)],
                    f"씬 음성 형식 맞추기({path.name})")
        with wave.open(str(src), "rb") as w:
            data = w.readframes(w.getnframes())
        offset = int(round(start * rate)) * frame
        end = min(len(buf), offset + len(data))
        if end > offset:
            buf[offset:end] = data[: end - offset]
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(buf))
    return out_wav


def _srt_time(sec: float) -> str:
    ms = int(round(max(0.0, sec) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _wrap(text: str, width: int = 42) -> str:
    lines: list[str] = []
    cur = ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}" if cur else word
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def write_srt(cues: list[tuple[float, float, str]], path: Path) -> Path:
    """(시작, 끝, 문장) 목록을 SRT 로 쓴다 — 한 씬 = 한 자막, 42자 안팎에서 줄을 바꾼다."""
    blocks = [
        f"{i}\n{_srt_time(a)} --> {_srt_time(b)}\n{_wrap(text)}\n"
        for i, (a, b, text) in enumerate(cues, start=1)
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(blocks), encoding="utf-8")
    return path


# ── 단계 ─────────────────────────────────────────────────────────────────────


@dataclass
class NarrationPlan:
    """prepare 가 만들어 finish 에 넘기는 것."""

    doc: ScenarioDoc
    timings: list[SceneTiming]
    engine: str
    speed: float | None
    voice_id: str | None
    work_dir: Path
    old_total_sec: float
    max_silence: float
    scenario_written: str | None = None

    def warnings(self) -> list[str]:
        return [f"{t.name}: {a}" for t in self.timings for a in t.advice]


def _max_silence(spec) -> float:
    value = spec.presets.narration.max_silence
    return value if value > 0 else DEFAULT_MAX_SILENCE_SEC


def _same_scenes(path: Path, doc: ScenarioDoc) -> bool:
    """scenario.json 이 이 빌드의 원본인지 — 씬 이름 순서가 같을 때만 덮어쓴다."""
    try:
        names = [s.get("name") for s in json.loads(path.read_text(encoding="utf-8")).get("scenes") or []]
    except (OSError, ValueError):
        return False
    return names == [s.name for s in doc.scenes]


def prepare(
    build_dir: Path,
    work_dir: Path,
    *,
    scenario_path: Path | None = None,
    modules_root: Path | None = None,
    transport: httpx.BaseTransport | None = None,
    log: Callable[[str], None] = print,
) -> NarrationPlan:
    """실측 → dur 재조정 → 검증 → 시나리오 반영·재빌드. 영상 렌더 전에 부른다.

    scenario_path 를 주면(그리고 같은 씬 구성이면) 재조정한 dur 를 그 파일에도 쓴다 —
    이후 렌더·PPTX·QA 가 같은 타이밍을 쓰게. 빌드(scene-data.json·index.html)는 늘 다시 만든다.
    """
    from wdpipeline.build import build_render_package
    from wdpipeline.format import load_format
    from wdpipeline.scenario import validate_scenario
    from wdrender.tts_client import measure_scenes, resolve_base_url

    build_dir, work_dir = Path(build_dir), Path(work_dir)
    doc = ScenarioDoc.model_validate_json((build_dir / "scene-data.json").read_text(encoding="utf-8"))
    spec = load_format(doc.format, modules_root=modules_root)
    if not spec.wants("video"):
        raise NarrationError(f"포맷 {doc.format} 은 영상을 만들지 않아 내레이션을 입힐 수 없다")
    narrated = [(s.name, s.narration.strip()) for s in doc.scenes if s.narration.strip()]
    if not narrated:
        raise NarrationError("내레이션이 있는 씬이 없다 — 시나리오의 narration 을 채우거나 내레이션 없이 렌더하라")

    try:
        measured = measure_scenes(
            narrated, out_dir=work_dir / "scenes",
            title=f"WDA {doc.meta.core_message}"[:80], transport=transport, log=log,
        )
    except httpx.TransportError as exc:
        raise NarrationError(
            f"VoiceRecorder({resolve_base_url()})에 연결하지 못했다 — 서버를 켜거나 WDA_TTS_BASE_URL 을 확인하라. "
            f"오프라인 렌더 노드(--network=none)에서는 내레이션을 쓸 수 없다 ({type(exc).__name__}: {exc})"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise NarrationError(
            f"VoiceRecorder 요청 실패 {exc.response.status_code} {exc.request.method} {exc.request.url.path}: "
            f"{exc.response.text[:300]}"
        ) from exc

    max_silence = _max_silence(spec)
    new_doc, timings = retime(doc, {m["name"]: m["duration_sec"] for m in measured["scenes"]},
                              max_silence=max_silence)
    by_name = {m["name"]: m for m in measured["scenes"]}
    for t in timings:
        m = by_name.get(t.name)
        if m is None:
            continue
        t.audio_path = m["audio_path"]
        if m["unread_latin"]:
            t.flags.append("unread-latin")
            t.advice.append(
                f"영문 {', '.join(m['unread_latin'])} 은 합성기가 건너뛸 수 있다 — "
                "VoiceRecorder 발음 사전에 읽는 소리를 넣어라"
            )

    old_total = round(sum(s.dur for s in doc.scenes), 2)
    errors = validate_scenario(new_doc, modules_root=modules_root)
    if errors:
        grown = sorted((t for t in timings if t.spoken_sec is not None),
                       key=lambda t: t.new_dur - t.old_dur, reverse=True)[:3]
        tops = ", ".join(f"{t.name} {t.old_dur:g}→{t.new_dur:g}초" for t in grown)
        raise NarrationError(
            "내레이션 길이로 다시 잡은 시나리오가 검증을 통과하지 못했다 — " + "; ".join(errors)
            + (f" · 가장 많이 늘어난 씬: {tops}" if tops else "")
        )

    # 시나리오를 먼저 쓰고 빌드한다 — 빌드가 시나리오보다 낡아 보이면 씬 툴이 다시 빌드한다
    # (wdmcp.server._ensure_scene_build 는 index.html 과 scenario.json 의 mtime 을 비교한다)
    written = None
    if scenario_path is not None and Path(scenario_path).is_file() and _same_scenes(Path(scenario_path), new_doc):
        Path(scenario_path).write_text(
            json.dumps(new_doc.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        written = str(scenario_path)
    build_render_package(new_doc, build_dir, modules_root=modules_root)
    new_total = round(sum(t.new_dur for t in timings), 2)
    log(
        f"[narration] 씬 {len(narrated)}개 실측(엔진 {measured['engine']}, 속도 {measured['speed']}) "
        f"→ Σdur {old_total:g}s → {new_total:g}s, 경고 {sum(len(t.advice) for t in timings)}건"
    )
    return NarrationPlan(
        doc=new_doc, timings=timings, engine=measured["engine"], speed=measured["speed"],
        voice_id=measured["voice_id"], work_dir=work_dir, old_total_sec=old_total,
        max_silence=max_silence, scenario_written=written,
    )


def drift_report(plan: NarrationPlan, *, mux: dict | None = None) -> dict:
    """씬별 실측·재조정·무음·경고를 한 장으로 — 골든 산출물 목록의 drift_report.json 과 같은 자리."""
    voiced = [t for t in plan.timings if t.spoken_sec is not None]
    total = sum(t.new_dur for t in plan.timings)
    spoken = sum(t.spoken_sec for t in voiced)
    return {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": plan.engine,
        "speed": plan.speed,
        "voice_id": plan.voice_id,
        "rules": {
            "lead_sec": LEAD_SEC, "tail_sec": TAIL_SEC,
            "stretch_limit": STRETCH_LIMIT, "max_silence_sec": plan.max_silence,
        },
        "summary": {
            "scenes": len(plan.timings),
            "narrated": len(voiced),
            "old_total_sec": plan.old_total_sec,
            "new_total_sec": round(total, 2),
            "spoken_sec": round(spoken, 2),
            "silence_sec": round(total - spoken, 2),
            "silence_ratio": round((total - spoken) / total, 3) if total else 0.0,
            "stretch_limit_scenes": [t.name for t in voiced if "stretch-limit" in t.flags],
            "silence_scenes": [t.name for t in voiced if "silence" in t.flags],
        },
        "scenes": [
            {
                "name": t.name,
                "old_dur": t.old_dur,
                "new_dur": t.new_dur,
                "nat": t.nat,
                "stretch": round(t.new_dur / t.nat - 1, 3) if t.nat else None,
                "start_sec": t.start_sec,
                "spoken_sec": t.spoken_sec,
                "silence_sec": t.silence_sec,
                "flags": t.flags,
                "advice": t.advice,
            }
            for t in plan.timings
        ],
        "scenario_written": plan.scenario_written,
        "mux": mux,
    }


def finish(
    plan: NarrationPlan,
    video_mp4: Path,
    out_dir: Path,
    *,
    log: Callable[[str], None] = print,
) -> dict:
    """트랙·자막 조립 → 먹싱 → drift_report. 영상 렌더 뒤에 부른다.

    목소리 입힌 영상이 video_mp4 자리를 대신한다(결정 59). 옆에 narration.mp3 ·
    narration.srt · drift_report.json 을 남긴다.
    """
    from wdrender.mux import mux_audio

    video_mp4, out_dir = Path(video_mp4), Path(out_dir)
    voiced = [t for t in plan.timings if t.spoken_sec is not None]
    total = round(sum(t.new_dur for t in plan.timings), 3)
    wav = assemble_track(
        [(t.speech_start_sec, Path(t.audio_path)) for t in voiced], total, plan.work_dir / "narration.wav"
    )
    mp3 = out_dir / "narration.mp3"
    _ffmpeg(["-i", str(wav), "-c:a", "libmp3lame", "-q:a", "2", str(mp3)], "내레이션 mp3 만들기")
    srt = write_srt(
        [(t.speech_start_sec, t.speech_start_sec + t.spoken_sec, t.text) for t in voiced],
        out_dir / "narration.srt",
    )
    tmp = video_mp4.with_name(video_mp4.stem + ".voiced.mp4")
    info = mux_audio(video_mp4, mp3, tmp, srt_path=srt)
    tmp.replace(video_mp4)
    info["out"] = str(video_mp4)

    report = drift_report(plan, mux=info)
    report_path = out_dir / "drift_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = report["summary"]
    log(
        f"[narration] 먹싱 → {video_mp4.name} ({info['out_sec']}s) · 무음 {summary['silence_ratio']:.0%} · "
        f"한계 초과 {len(summary['stretch_limit_scenes'])}씬 · 무음 경고 {len(summary['silence_scenes'])}씬"
    )
    return {
        "audio": str(mp3),
        "srt": str(srt),
        "drift_report": str(report_path),
        "summary": summary,
        "warnings": plan.warnings(),
    }
