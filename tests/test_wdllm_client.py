# wdllm 설정·클라이언트 검증 — toml+env 로드, GLM 5원칙 요청 본문, 400 폴백, 파싱 재시도, 실 vLLM 스모크
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from wdllm.client import (
    ChatResult,
    GLMClient,
    LLMContextError,
    LLMError,
    chat_json,
    extract_json,
)
from wdllm.config import LLMConfig, load_llm_config

TOML = Path(__file__).resolve().parents[1] / "configs" / "vllm.toml"


# --- config -----------------------------------------------------------------
def test_config_defaults_without_env():
    cfg = load_llm_config(TOML, env={})
    assert cfg.base_url == "http://127.0.0.1:8000/v1"
    assert cfg.model == "qwen2.5-7b-dev"
    assert cfg.api_key == "EMPTY"
    assert cfg.disable_streaming is True
    assert cfg.max_tokens == 0  # 0 = 미전송
    assert cfg.timeout_sec == 300
    assert cfg.reasoning_effort == "medium"
    assert cfg.json_object is True and cfg.fallback_on_400 is True
    assert cfg.parse_retries == 2


def test_config_env_overrides():
    env = {
        "LLM_BASE_URL": "http://10.198.143.137:10000/v1/",
        "LLM_MODEL": "GLM-5-2",
        "LLM_API_KEY": "secret",
        "LLM_DISABLE_STREAMING": "0",
    }
    cfg = load_llm_config(TOML, env=env)
    assert cfg.base_url == "http://10.198.143.137:10000/v1"  # 후행 슬래시 제거
    assert cfg.model == "GLM-5-2"
    assert cfg.api_key == "secret"
    assert cfg.disable_streaming is False


def test_config_missing_toml_falls_back_to_defaults(tmp_path):
    cfg = load_llm_config(tmp_path / "없는파일.toml", env={})
    assert cfg.model == "qwen2.5-7b-dev" and cfg.parse_retries == 2


# --- client (httpx.MockTransport) -------------------------------------------
def _cfg(**kw) -> LLMConfig:
    base = dict(
        base_url="http://test/v1", model="GLM-5-2", api_key="k", disable_streaming=True,
        max_tokens=0, timeout_sec=5, reasoning_effort="medium", json_object=True,
        fallback_on_400=True, parse_retries=2,
    )
    base.update(kw)
    return LLMConfig(**base)


def _ok_response(content='{"ok": true}', reasoning=" 사고 과정 "):
    return httpx.Response(200, json={
        "model": "GLM-5-2",
        "choices": [{
            "message": {"content": f"  {content}  ", "reasoning_content": reasoning},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    })


def test_chat_body_follows_glm_rules_and_splits_reasoning():
    """max_tokens 미전송·chat_template_kwargs 경유 reasoning·json_object·비스트리밍."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        assert request.headers["Authorization"] == "Bearer k"
        return _ok_response()

    client = GLMClient(_cfg(), transport=httpx.MockTransport(handler))
    res = client.chat([{"role": "user", "content": "질문"}])
    body = seen[0]
    assert "max_tokens" not in body  # 원칙③ 0 = 미전송
    assert body["chat_template_kwargs"] == {"reasoning_effort": "medium"}  # 원칙②
    assert "reasoning_effort" not in body  # 톱레벨 금지
    assert body["response_format"] == {"type": "json_object"}  # 원칙⑤
    assert "stream" not in body  # 원칙① 비스트리밍(완결 응답)
    assert res.content == '{"ok": true}'
    assert res.reasoning == "사고 과정"  # reasoning_content 분리
    assert res.usage["total_tokens"] == 15
    assert res.finish_reason == "stop"


def test_json_object_400_falls_back_without_response_format():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if "response_format" in body:
            return httpx.Response(400, text="response_format is not supported")
        return _ok_response()

    client = GLMClient(_cfg(), transport=httpx.MockTransport(handler))
    res = client.chat([{"role": "user", "content": "질문"}])
    assert len(seen) == 2
    assert "response_format" in seen[0] and "response_format" not in seen[1]
    assert res.content == '{"ok": true}'


def test_context_overflow_raises_dedicated_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, text="This model's maximum context length is 16384 tokens"
        )

    client = GLMClient(_cfg(), transport=httpx.MockTransport(handler))
    with pytest.raises(LLMContextError, match="토큰 한도"):
        client.chat([{"role": "user", "content": "긴 질문"}])


def test_non_400_error_raises_llm_error():
    client = GLMClient(
        _cfg(), transport=httpx.MockTransport(lambda r: httpx.Response(503, text="down"))
    )
    with pytest.raises(LLMError, match="호출 실패"):
        client.chat([{"role": "user", "content": "질문"}])


# --- extract_json / chat_json ------------------------------------------------
def test_extract_json_tolerates_fences_and_noise():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('설명입니다 {"a": 2} 끝') == {"a": 2}
    with pytest.raises(ValueError):
        extract_json("JSON 없음")
    with pytest.raises(ValueError):
        extract_json('[1, 2]')  # 객체가 아니면 거부


class _SeqLLM:
    """정해진 content 를 순서대로 돌려주는 스텁."""

    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = 0

    def chat(self, messages, **kwargs):
        c = self.contents[self.calls]
        self.calls += 1
        return ChatResult(content=c, reasoning=None, model="stub", usage=None, raw={})


def test_chat_json_retries_until_valid():
    llm = _SeqLLM(["잡담 — JSON 아님", '{"ok": 1}'])
    data, results = chat_json(llm, [{"role": "user", "content": "x"}], parse_retries=2)
    assert data == {"ok": 1}
    assert len(results) == 2 and llm.calls == 2


def test_chat_json_exhausts_retries():
    llm = _SeqLLM(["잡담1", "잡담2"])
    with pytest.raises(LLMError, match="JSON 파싱"):
        chat_json(llm, [{"role": "user", "content": "x"}], parse_retries=1)


# --- 실 vLLM 스모크 (로컬 :8000 미가동이면 skip) ------------------------------
def _local_vllm_model() -> str | None:
    try:
        r = httpx.get("http://127.0.0.1:8000/v1/models", timeout=2, trust_env=False)
        r.raise_for_status()
        data = r.json().get("data") or []
        return data[0]["id"] if data else None
    except Exception:
        return None


_VLLM_MODEL = _local_vllm_model()


@pytest.mark.skipif(_VLLM_MODEL is None, reason="로컬 vLLM(:8000) 미가동 — 실호출 스모크 skip")
def test_smoke_real_vllm_one_meeting_turn(tmp_path):
    """오케스트레이터로 scenario_build R1(모더레이터) 1턴을 실 vLLM 에 태운다."""
    from wdcore.meetings import MeetingEngine, MeetingStore
    from wdcore.registry.registry import load_registry
    from wdllm.orchestrator import AutoOrchestrator

    cfg = LLMConfig(
        base_url="http://127.0.0.1:8000/v1", model=_VLLM_MODEL, api_key="EMPTY",
        disable_streaming=True, max_tokens=0, timeout_sec=120, reasoning_effort="",
        json_object=True, fallback_on_400=True, parse_retries=2,
    )
    registry = load_registry()
    engine = MeetingEngine(MeetingStore(root=tmp_path / "meetings"), registry)
    meta = engine.create("scenario_build", "실호출 스모크", ["narr-story-architect"])
    result = AutoOrchestrator(engine, GLMClient(cfg), registry).run(meta, max_turns=1)
    assert result.status == "paused"
    assert result.turns_submitted == 1
    assert result.usage["calls"] >= 1 and result.usage["total_tokens"] > 0
    _, turns = engine.store.load(meta.id)
    accepted = [t for t in turns if t.role.value == "moderator"]
    assert len(accepted) == 1 and accepted[0].content_md
