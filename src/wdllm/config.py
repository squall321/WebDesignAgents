# vLLM(GLM-5-2) 접속 설정 로더 — configs/vllm.toml + LLM_* 환경변수 결합 (경로 B)
"""configs/vllm.toml 의 [server]/[call]/[structured_output] 절과 환경변수
(LLM_BASE_URL / LLM_MODEL / LLM_API_KEY / LLM_DISABLE_STREAMING)를 결합해
불변 LLMConfig 를 만든다. RA(ReportArchive) llm.py 의 app.config 결합부를
이 모듈이 대체한다 (docs/analysis/glm-client-rules.md 5원칙 반영).

dev 기본값은 로컬 vLLM(http://127.0.0.1:8000/v1, qwen2.5-7b-dev, 무인증)이다 —
운영(cae00)은 env-kits 상속으로 LLM_* 환경변수가 주입된다 (PLAN §10.1).
"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

# dev 폴백 (PLAN §10.1 — RA에 값이 없는 dev 박스는 로컬 vLLM으로)
DEFAULT_BASE_URL = "http://127.0.0.1:8000/v1"
DEFAULT_MODEL = "qwen2.5-7b-dev"
DEFAULT_API_KEY = "EMPTY"

DISABLE_STREAMING_ENV = "LLM_DISABLE_STREAMING"

_DEFAULT_TOML = Path(__file__).resolve().parents[2] / "configs" / "vllm.toml"


@dataclass(frozen=True)
class LLMConfig:
    """GLM-5-2 호출 5원칙이 반영된 클라이언트 설정 (불변)."""

    base_url: str
    model: str
    api_key: str
    disable_streaming: bool  # 원칙① 스트리밍+tool_calls 조합 금지 — 비스트리밍 기본
    max_tokens: int          # 원칙③ 0 = 미전송 (8192 미만 지정 금지)
    timeout_sec: float       # 원칙④ 120~600s 여유
    reasoning_effort: str    # 원칙② extra_body.chat_template_kwargs 로만. "" = 미전달
    json_object: bool        # 원칙⑤ response_format json_object 까지만 신뢰
    fallback_on_400: bool    # 원칙⑤ 400 시 response_format 제거 후 재시도
    parse_retries: int       # 파싱 실패 시 재호출 횟수


def _as_bool(raw: str) -> bool:
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_llm_config(
    toml_path: Path | None = None, env: Mapping[str, str] | None = None
) -> LLMConfig:
    """vllm.toml 과 환경변수를 읽어 LLMConfig 를 만든다.

    toml [server] 절은 접속값 자체가 아니라 *환경변수 이름*을 선언한다
    (base_url_env 등). env 인자는 테스트용 — 기본은 os.environ.
    """
    env = os.environ if env is None else env
    path = toml_path or _DEFAULT_TOML
    data: dict = {}
    if path.is_file():
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    server = data.get("server", {})
    call = data.get("call", {})
    so = data.get("structured_output", {})

    base_url = env.get(server.get("base_url_env", "LLM_BASE_URL"), "") or DEFAULT_BASE_URL
    model = env.get(server.get("model_env", "LLM_MODEL"), "") or DEFAULT_MODEL
    api_key = env.get(server.get("api_key_env", "LLM_API_KEY"), "") or DEFAULT_API_KEY

    disable_streaming = bool(call.get("disable_streaming", True))
    if DISABLE_STREAMING_ENV in env:
        disable_streaming = _as_bool(env[DISABLE_STREAMING_ENV])

    return LLMConfig(
        base_url=base_url.rstrip("/"),
        model=model,
        api_key=api_key,
        disable_streaming=disable_streaming,
        max_tokens=int(call.get("max_tokens", 0)),
        timeout_sec=float(call.get("timeout_sec", 300)),
        reasoning_effort=str(call.get("reasoning_effort", "") or ""),
        json_object=(so.get("mode", "json_object") == "json_object"),
        fallback_on_400=bool(so.get("fallback_on_400", True)),
        parse_retries=int(so.get("parse_retries", 2)),
    )
