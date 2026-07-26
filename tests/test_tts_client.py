# tts_client 테스트 — 타임코드/스크립트 조립 단위 테스트 + (서비스 가동 시) 1문장 왕복 스모크
from __future__ import annotations

import httpx
import pytest

from wdrender.tts_client import (
    build_raw_script,
    format_timecode,
    oneshot_tts,
    resolve_base_url,
    synthesize_scenario,
)


def _service_up() -> bool:
    try:
        r = httpx.get(f"{resolve_base_url()}/api/health", timeout=2.0)
        return r.status_code == 200 and r.json().get("status") == "ok"
    except Exception:
        return False


requires_service = pytest.mark.skipif(
    not _service_up(), reason="VoiceRecorder(:8177) 미가동 — 실서비스 스모크 skip"
)


# ── 타임코드 형식 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (0, "0:00"),
        (8, "0:08"),
        (66, "1:06"),
        (90, "1:30"),
        (3723, "1:02:03"),
        (8.5, "0:08.5"),
    ],
)
def test_format_timecode(seconds, expected):
    assert format_timecode(seconds) == expected


# ── 스크립트 조립 ───────────────────────────────────────────────────────────


def _mini_scenario():
    return {
        "meta": {"core_message": "테스트"},
        "scenes": [
            {"name": "오프닝", "dur": 8.0, "narration": "첫 문장입니다."},
            {"name": "본론", "dur": 13.0, "narration": "둘째 문장입니다."},
            {"name": "클로징", "dur": 12.0, "narration": "마지막 문장입니다."},
        ],
    }


def test_build_raw_script_format():
    script = build_raw_script(_mini_scenario())
    blocks = script.split("\n\n")
    assert blocks == [
        '01 오프닝 (0:00-0:08) "첫 문장입니다."',
        '02 본론 (0:08-0:21) "둘째 문장입니다."',
        '03 클로징 (0:21-0:33) "마지막 문장입니다."',
    ]


def test_build_raw_script_skips_no_narration_but_keeps_timeline():
    scenario = _mini_scenario()
    scenario["scenes"][1]["narration"] = ""  # 내레이션 없는 씬 — 슬롯(13s)은 유지돼야 한다
    script = build_raw_script(scenario)
    blocks = script.split("\n\n")
    assert blocks == [
        '01 오프닝 (0:00-0:08) "첫 문장입니다."',
        '02 클로징 (0:21-0:33) "마지막 문장입니다."',
    ]


def test_build_raw_script_empty_raises():
    with pytest.raises(ValueError):
        build_raw_script({"scenes": []})
    with pytest.raises(ValueError):
        build_raw_script({"scenes": [{"name": "무음", "dur": 5.0, "narration": ""}]})


# ── 실서비스 왕복 스모크 (가동 시에만) ──────────────────────────────────────


@requires_service
def test_roundtrip_parse_matches_server():
    """조립한 스크립트를 서버 파서(POST /api/scripts/parse)가 동일하게 해석하는지 확인."""
    script = build_raw_script(_mini_scenario())
    r = httpx.post(
        f"{resolve_base_url()}/api/scripts/parse", json={"raw_script": script}, timeout=10.0
    )
    r.raise_for_status()
    data = r.json()
    assert data["structured"] is True
    assert [s["title"] for s in data["scenes"]] == ["오프닝", "본론", "클로징"]
    assert [s["target_start_sec"] for s in data["scenes"]] == [0.0, 8.0, 21.0]
    assert [s["target_end_sec"] for s in data["scenes"]] == [8.0, 21.0, 33.0]


@requires_service
def test_mini_project_smoke(tmp_path):
    """1문장 미니 프로젝트 왕복 — 합성→fit→export→다운로드→삭제 전체 플로우."""
    scenario = {
        "meta": {"core_message": "스모크"},
        "scenes": [{"name": "스모크", "dur": 6.0, "narration": "안녕하세요. 스모크 테스트입니다."}],
    }
    # CPU 사이드카(melo)를 우선해 GPU 부하 없이 빠르게 돈다 — 불가면 클라이언트가 폴백
    result = synthesize_scenario(
        scenario,
        engine="melo",
        out_dir=tmp_path,
        scene_timeout_sec=180.0,
        poll_interval_sec=1.0,
        log=lambda m: None,
    )
    audio = tmp_path / "narration.mp3"
    srt = tmp_path / "narration.srt"
    assert audio.exists() and audio.stat().st_size > 0
    assert srt.exists() and srt.stat().st_size > 0
    assert result["audio_path"] == str(audio)
    assert result["total_sec"] and result["total_sec"] > 0
    assert len(result["scenes"]) == 1
    assert result["scenes"][0]["name"] == "스모크"
    assert result["scenes"][0]["duration_sec"] and result["scenes"][0]["duration_sec"] > 0


@requires_service
def test_oneshot_tts_smoke(tmp_path):
    """원샷 TTS(POST /api/tts) — 문장 하나의 실측 길이와 wav 다운로드·정리."""
    wav = tmp_path / "oneshot.wav"
    result = oneshot_tts(
        "원샷 티티에스 스모크 테스트입니다.",
        engine="melo",
        out_path=wav,
        timeout_sec=180.0,
        poll_interval_sec=1.0,
        log=lambda m: None,
    )
    assert result["duration_sec"] and result["duration_sec"] > 0
    assert wav.exists() and wav.stat().st_size > 0
