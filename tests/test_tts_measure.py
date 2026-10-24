# VoiceRecorder 측정 클라이언트 테스트 — 가짜 서버로 원문 그대로 측정·실패 시 정리·.env/PAT 설정 확인
from __future__ import annotations

import wave

import pytest

from wdrender import tts_client
from wdrender.tts_fake import FakeVoiceRecorder


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch, tmp_path):
    # 개발 박스의 .env(WDA_TTS_*)가 테스트에 새어 들지 않게
    monkeypatch.setenv("WDA_ENV_FILE", str(tmp_path / "no.env"))
    for key in ("WDA_TTS_BASE_URL", "WDA_TTS_PAT", "WDA_TTS_ENGINE", "WDA_TTS_VOICE_ID", "WDA_TTS_SPEED"):
        monkeypatch.delenv(key, raising=False)




def test_measure_sends_text_verbatim_and_always_cleans_up(tmp_path):
    fake = FakeVoiceRecorder()
    texts = [("열기", '질문 하나가 "의사결정문"이 되기까지'), ("닫기", "NA: 0:05 라벨처럼 보여도 원문 그대로")]
    out = tts_client.measure_scenes(texts, out_dir=tmp_path, transport=fake.transport(), log=lambda m: None)
    assert [s["text"] for s in out["scenes"]] == [t for _, t in texts]
    assert [s["duration_sec"] for s in out["scenes"]] == [fake.seconds_for(t) for _, t in texts]
    assert out["engine"] == "melo" and out["speed"] == 1.2
    for s in out["scenes"]:
        with wave.open(s["audio_path"], "rb") as w:
            assert w.getnframes() / w.getframerate() == pytest.approx(s["duration_sec"], abs=1e-3)
    assert fake.projects == {} and len(fake.deleted) == 1
    # 대본 파서를 거치지 않는다 — 첫 씬은 PATCH, 나머지는 씬 추가
    assert ("PATCH" in {m for m, _ in fake.requests}) and ("POST", f"/api/projects/{fake.deleted[0]}/scenes") in fake.requests


def test_measure_reports_failed_scenes_and_still_deletes_the_project(tmp_path):
    fake = FakeVoiceRecorder(fail_scenes={"닫기"})
    with pytest.raises(RuntimeError, match="닫기: 가짜 합성 오류"):
        tts_client.measure_scenes([("열기", "가"), ("닫기", "나")], out_dir=tmp_path,
                                  transport=fake.transport(), log=lambda m: None)
    assert fake.projects == {}


def test_measure_reads_tts_settings_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("WDA_TTS_PAT", "tok-123")
    monkeypatch.setenv("WDA_TTS_SPEED", "1.1")
    monkeypatch.setenv("WDA_TTS_ENGINE", "chatterbox")   # 없는 엔진 → 서버 기본으로 폴백
    fake = FakeVoiceRecorder()
    out = tts_client.measure_scenes([("열기", "가나다")], out_dir=tmp_path, transport=fake.transport(),
                                    log=lambda m: None)
    assert out["speed"] == 1.1 and out["engine"] == "melo"
    assert set(fake.auth) == {"Bearer tok-123"}


def test_base_url_reads_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("WDA_TTS_BASE_URL=http://127.0.0.1:4180/apps/voice_recorder/\n", encoding="utf-8")
    monkeypatch.setenv("WDA_ENV_FILE", str(env))
    assert tts_client.resolve_base_url() == "http://127.0.0.1:4180/apps/voice_recorder"
    assert tts_client.resolve_base_url("http://x:1") == "http://x:1"   # 인자가 이긴다
