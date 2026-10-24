# env-kits 상속 경로 계약 — .env 의 LLM_* 가 실제로 닿는가 (PLAN §10.1, cae00 실연결 전제)
from __future__ import annotations

import os
from pathlib import Path

import pytest

from wdllm.config import DEFAULT_BASE_URL, load_llm_config


@pytest.fixture
def envdir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for key in ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY", "LLM_DISABLE_STREAMING",
                "WDA_ENV_FILE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_dotenv_llm_vars_reach_the_client(envdir: Path):
    """env-kits 는 .env 에 LLM_* 를 적는다. 이게 안 닿으면 조용히 dev 폴백으로 떨어진다.

    cae00 에서 그 폴백은 Errno 111 이다 — 설정이 틀린 게 아니라 안 읽힌 것이라
    원인을 찾기 어렵다. LLM_* 는 WDA_ 접두가 없어 pydantic-settings 가 안 가져간다.
    """
    (envdir / ".env").write_text(
        "LLM_BASE_URL=http://10.0.0.1:10000/v1\n"
        "LLM_MODEL=GLM-5-2\n"
        "LLM_API_KEY=secret-token\n",
        encoding="utf-8",
    )
    cfg = load_llm_config()
    assert cfg.base_url == "http://10.0.0.1:10000/v1"
    assert cfg.model == "GLM-5-2"
    assert cfg.api_key == "secret-token"


def test_real_environment_wins_over_dotenv(envdir: Path, monkeypatch: pytest.MonkeyPatch):
    """컨테이너는 APPTAINERENV_ 로 진짜 환경변수를 넣는다 — 그게 파일을 이겨야 한다."""
    (envdir / ".env").write_text("LLM_MODEL=from-file\n", encoding="utf-8")
    monkeypatch.setenv("LLM_MODEL", "from-env")
    assert load_llm_config().model == "from-env"


def test_no_dotenv_falls_back_to_dev_default(envdir: Path):
    """.env 가 없으면 dev 폴백이 맞다 — 로컬 개발이 그걸로 돈다."""
    assert load_llm_config().base_url == DEFAULT_BASE_URL.rstrip("/")


def test_env_file_path_is_overridable(envdir: Path, monkeypatch: pytest.MonkeyPatch):
    """컨테이너는 작업 디렉터리가 리포 루트가 아닐 수 있다."""
    other = envdir / "cfg" / "app.env"
    other.parent.mkdir()
    other.write_text("LLM_MODEL=from-custom\n", encoding="utf-8")
    monkeypatch.setenv("WDA_ENV_FILE", str(other))
    assert load_llm_config().model == "from-custom"


def test_broken_dotenv_does_not_crash(envdir: Path):
    """.env 가 깨져도 기동은 돼야 한다 — 폴백이 있는 쪽이 죽는 것보다 낫다."""
    (envdir / ".env").write_text("이건 올바른 형식이 아니다\n\x00", encoding="utf-8")
    cfg = load_llm_config()
    assert cfg.base_url  # 무엇이든 값이 나온다
