# 내레이션 단계 테스트 — 실측 재조정 규칙·트랙 배치·자막·게이트 2 실측 규칙·가짜 VoiceRecorder 왕복
from __future__ import annotations

import json
import shutil
import subprocess
import wave
from pathlib import Path

import pytest

from wdcore.models.scenario import ScenarioDoc, narration_sha
from wdpipeline import narration as nar
from wdqa.config import QAConfig
from wdqa.gate2_length import run_data
from wdrender.tts_fake import FakeVoiceRecorder, tone_wav

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg 없음")


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch, tmp_path):
    # 개발 박스의 .env(WDA_TTS_*)가 테스트에 새어 들지 않게
    monkeypatch.setenv("WDA_ENV_FILE", str(tmp_path / "no.env"))
    for key in ("WDA_TTS_BASE_URL", "WDA_TTS_PAT", "WDA_TTS_ENGINE", "WDA_TTS_VOICE_ID", "WDA_TTS_SPEED"):
        monkeypatch.delenv(key, raising=False)


def _doc(*scenes: dict) -> ScenarioDoc:
    return ScenarioDoc.model_validate({
        "meta": {"core_message": "테스트", "duration_sec": sum(s["dur"] for s in scenes)},
        "scenes": [{"tpl": "opening@1", **s} for s in scenes],
    })


# ── 재조정 규칙 (결정 49) ──────────────────────────────────────────────────


def test_dur_follows_speech_inside_the_stretch_band():
    doc, [t] = nar.retime(_doc({"name": "a", "dur": 10, "nat": 10, "narration": "가" * 63}), {"a": 9.0})
    # 앞 여유 0.3 + 실측 9.0 + 뒤 여유 0.5 = 9.8 — 하한 8.5·상한 11.5 사이라 그대로
    assert doc.scenes[0].dur == 9.8 and t.new_dur == 9.8
    assert t.flags == [] and t.advice == []


def test_short_speech_keeps_the_visual_floor_and_warns_silence():
    doc, [t] = nar.retime(_doc({"name": "a", "dur": 10, "nat": 10, "narration": "짧다"}), {"a": 2.0},
                          max_silence=3.0)
    assert doc.scenes[0].dur == 8.5            # nat × 0.85 아래로 줄이지 않는다
    assert t.silence_sec == 6.5
    assert t.flags == ["silence"]
    assert "덧붙이면" in t.advice[0]


def test_long_speech_extends_past_the_limit_and_says_how_much_to_cut():
    # 사용자 선택 — 말은 그대로 두고 씬을 늘린 뒤 경고한다
    doc, [t] = nar.retime(_doc({"name": "a", "dur": 10, "nat": 10, "narration": "가" * 84}), {"a": 12.0})
    assert doc.scenes[0].dur == 12.8
    assert t.flags == ["stretch-limit"]
    # 1.3초 초과 × 7자/초 → 약 10자
    assert "1.3초 넘는다" in t.advice[0] and "약 10자" in t.advice[0]


def test_silent_scenes_and_the_timeline():
    doc, timings = nar.retime(
        _doc({"name": "a", "dur": 4, "nat": 4},
             {"name": "b", "dur": 10, "nat": 10, "narration": "말", "stills": [9.0]}),
        {"b": 12.0},
    )
    a, b = doc.scenes
    assert a.dur == 4 and a.narration_sec is None          # 말 없는 씬은 그대로
    assert b.dur == 12.8 and b.stills == [11.52]           # 정지 캡처는 새 dur 에 비례
    assert timings[1].start_sec == 4.0 and timings[1].speech_start_sec == pytest.approx(4.3)
    assert doc.meta.duration_sec == 16.8
    assert b.narration_sec == 12.0 and b.narration_sha == narration_sha("말")


def test_scene_without_nat_uses_its_current_dur_as_the_visual_reference():
    doc, [t] = nar.retime(_doc({"name": "a", "dur": 10, "narration": "말"}), {"a": 2.0})
    assert doc.scenes[0].dur == 8.5 and "stretch-limit" not in t.flags


# ── 게이트 2 가 실측을 쓴다 (결정 50) ───────────────────────────────────────


def _gate2(scene: dict) -> list[dict]:
    return [r for r in run_data({"scenes": [scene]}, QAConfig()) if r["severity"] == "error"]


def test_gate2_trusts_the_measured_length_over_the_estimate():
    text = "가" * 70   # 추정 70÷5.5 = 12.7초 > dur 9
    scene = {"name": "a", "dur": 9, "nat": 9, "narration": text, "tpl": "opening@1",
             "narration_sec": 8.1, "narration_sha": narration_sha(text)}
    assert _gate2(scene) == []
    # 원고를 고치면 해시가 어긋나 추정으로 돌아간다
    edited = {**scene, "narration": text + "추가"}
    assert [r["rule"] for r in _gate2(edited)] == ["narration-rate"]


def test_gate2_flags_measured_speech_longer_than_the_scene():
    scene = {"name": "a", "dur": 5, "narration": "말", "tpl": "opening@1",
             "narration_sec": 6.0, "narration_sha": narration_sha("말")}
    [err] = _gate2(scene)
    assert err["rule"] == "narration-measured" and "실측 낭독 6.0s" in err["detail"]


# ── 트랙·자막 ────────────────────────────────────────────────────────────


def _write(path: Path, data: bytes) -> Path:
    path.write_bytes(data)
    return path


def _frames(path: Path) -> tuple[int, bytes]:
    with wave.open(str(path), "rb") as w:
        return w.getframerate(), w.readframes(w.getnframes())


def test_track_places_each_scene_at_its_start(tmp_path):
    a = _write(tmp_path / "a.wav", tone_wav(0.5))
    b = _write(tmp_path / "b.wav", tone_wav(0.5))
    out = nar.assemble_track([(0.5, a), (2.0, b)], 3.0, tmp_path / "track.wav")
    rate, data = _frames(out)
    assert rate == 24000 and len(data) == 3 * 24000 * 2

    def loud(t0: float, t1: float) -> bool:
        chunk = data[int(t0 * rate) * 2:int(t1 * rate) * 2]
        return any(chunk)

    assert not loud(0.0, 0.49) and loud(0.5, 1.0)
    assert not loud(1.01, 1.99) and loud(2.0, 2.5)
    assert not loud(2.51, 3.0)


@needs_ffmpeg
def test_track_converts_other_formats_to_the_first(tmp_path):
    a = _write(tmp_path / "a.wav", tone_wav(0.5, rate=24000))
    b = _write(tmp_path / "b.wav", tone_wav(0.5, rate=16000, channels=2))
    out = nar.assemble_track([(0.0, a), (1.0, b)], 2.0, tmp_path / "track.wav")
    rate, data = _frames(out)
    assert rate == 24000 and len(data) == 2 * 24000 * 2
    assert any(data[24000 * 2:int(1.4 * 24000) * 2])


def test_srt_one_cue_per_scene(tmp_path):
    path = nar.write_srt([(0.3, 2.25, "첫 문장"), (65.0, 70.5, "둘째 문장")], tmp_path / "n.srt")
    assert path.read_text(encoding="utf-8") == (
        "1\n00:00:00,300 --> 00:00:02,250\n첫 문장\n\n"
        "2\n00:01:05,000 --> 00:01:10,500\n둘째 문장\n"
    )


# ── prepare → 렌더 → finish (가짜 VoiceRecorder + 실렌더 fps=1) ─────────────────


@pytest.fixture(scope="module")
def demo_build(tmp_path_factory):
    """예시 보고서로 조립한 실제 시나리오(wide-16x9)의 빌드와 scenario.json."""
    from wdpipeline.build import build_render_package
    from wdpipeline.fragmentize import fragmentize
    from wdpipeline.ingest import ingest_report_file
    from wdpipeline.scenario import assemble_demo_scenario

    norm = ingest_report_file(SAMPLE)
    doc = assemble_demo_scenario(norm, fragmentize(norm))
    root = tmp_path_factory.mktemp("narr")
    build = root / "build" / "demo"
    build_render_package(doc, build)
    scen = root / "pipeline" / "demo" / "scenario.json"
    scen.parent.mkdir(parents=True)
    scen.write_text(json.dumps(doc.model_dump(), ensure_ascii=False), encoding="utf-8")
    return doc, build, scen


def _streams(path: Path) -> list[str]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout
    return sorted(out.split())


@needs_ffmpeg
def test_prepare_render_finish_end_to_end(demo_build, tmp_path):
    from wdpipeline.build import ENTRY_NAME
    from wdrender.config import load_config
    from wdrender.exporter_video import export_video
    from wdrender.mux import probe_duration
    from wdrender.page_session import vendor_resources

    doc, build, scen = demo_build
    narrated = [s.name for s in doc.scenes if s.narration.strip()]
    assert narrated, "예시 시나리오에는 내레이션이 있어야 한다"
    fake = FakeVoiceRecorder()
    plan = nar.prepare(build, tmp_path / "work", scenario_path=scen,
                       transport=fake.transport(), log=lambda m: None)

    # 빌드와 scenario.json 이 재조정된 dur·실측 길이를 갖는다
    built = ScenarioDoc.model_validate_json((build / "scene-data.json").read_text(encoding="utf-8"))
    assert [s.dur for s in built.scenes] == [t.new_dur for t in plan.timings]
    assert plan.scenario_written == str(scen)
    # 빌드가 시나리오보다 늦게 써져야 씬 툴이 낡은 빌드로 보고 다시 빌드하지 않는다
    assert (build / "index.html").stat().st_mtime >= scen.stat().st_mtime
    saved = ScenarioDoc.model_validate_json(scen.read_text(encoding="utf-8"))
    assert [s.name for s in saved.scenes if s.narration_sec] == narrated
    assert fake.projects == {}

    cfg = load_config()
    cfg.fps = 1
    out_dir = tmp_path / "renders"
    video = out_dir / "demo.mp4"
    export_video(build, ENTRY_NAME, video, config=cfg, format_id=built.format,
                 resources=vendor_resources("/vendor"), log=lambda m: None)
    silent_sec = probe_duration(video)
    result = nar.finish(plan, video, out_dir, log=lambda m: None)

    # 목소리 입힌 영상이 같은 자리를 대신하고 길이는 그대로다 (결정 52)
    assert _streams(video) == ["audio", "subtitle", "video"]
    assert probe_duration(video) == pytest.approx(silent_sec, abs=0.1)
    assert probe_duration(Path(result["audio"])) == pytest.approx(sum(t.new_dur for t in plan.timings), abs=0.1)
    srt = Path(result["srt"]).read_text(encoding="utf-8")
    assert srt.count(" --> ") == len(narrated)

    report = json.loads(Path(result["drift_report"]).read_text(encoding="utf-8"))
    assert report["summary"]["narrated"] == len(narrated)
    assert report["engine"] == "melo" and report["speed"] == 1.2
    assert [r["name"] for r in report["scenes"]] == [s.name for s in doc.scenes]

    # 게이트 2 는 이제 실측을 쓴다 — 짧게 잡은 씬이 5.5자/초 추정에 걸리지 않는다
    data = json.loads((build / "scene-data.json").read_text(encoding="utf-8"))
    errors = [r for r in run_data(data, QAConfig()) if r["severity"] == "error"]
    assert [r for r in errors if r["rule"].startswith("narration")] == []


def test_prepare_explains_an_unreachable_voicerecorder(demo_build, tmp_path, monkeypatch):
    import httpx

    _, build, _ = demo_build

    def refuse(request):
        raise httpx.ConnectError("연결 거부", request=request)

    before = (build / "scene-data.json").read_text(encoding="utf-8")
    with pytest.raises(nar.NarrationError, match="VoiceRecorder.*연결하지 못했다.*오프라인 렌더 노드"):
        nar.prepare(build, tmp_path / "work", transport=httpx.MockTransport(refuse), log=lambda m: None)
    assert (build / "scene-data.json").read_text(encoding="utf-8") == before   # 빌드는 건드리지 않는다
