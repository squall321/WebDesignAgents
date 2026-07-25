# GLM-5-2 OpenAI 호환 클라이언트 — httpx 비스트리밍, json_object 400 폴백, reasoning_content 분리
"""vLLM `/v1/chat/completions` 호출 클라이언트 (경로 B).

원본(copy-adapt): /home/koopark/claude/ReportArchive/backend/app/ai/llm.py
- RA `app.config` 결합부를 `wdllm.config.LLMConfig` 로 대체.
- mock/ollama/스트리밍 경로 제거 — GLM-5.2 + vLLM 0.23.0 스트리밍 tool_calls
  유실 결함으로 비스트리밍 완결 응답만 쓴다 (glm-client-rules.md 원칙①).
- 유지한 패턴: reasoning_content/reasoning 분리 파싱, response_format
  json_object 400 폴백, 컨텍스트 초과 휴리스틱(LLMContextError),
  trust_env=False(사내 프록시 우회 — RA llm_no_proxy 패턴).
- 추가: chat_json — 프롬프트 JSON 계약 + 파싱 재시도(설정 parse_retries,
  RA DELIB_PARSE_RETRIES 패턴). FakeLLM 등 `.chat` 을 가진 어떤 객체와도 동작.
"""
from __future__ import annotations

import json as _json
import re
from dataclasses import dataclass
from typing import Optional, Protocol

import httpx

from .config import LLMConfig, load_llm_config


class LLMError(RuntimeError):
    """LLM 호출 실패(백엔드 오류·타임아웃·응답 형식 이상)."""


class LLMContextError(LLMError):
    """요청(prompt+생성)이 모델 컨텍스트 한도를 초과해 서버가 거부(보통 400).

    같은 입력으로 재시도해도 동일하므로 호출부는 즉시 멈추고 입력을 줄여야 한다."""


@dataclass
class ChatResult:
    """생성 1회 결과. 기능 코드는 보통 `.content` 만 쓴다."""

    content: str
    reasoning: Optional[str]
    model: Optional[str]
    usage: Optional[dict]
    raw: dict
    # 'stop'|'length'|... — 'length' 면 토큰 한도에서 잘림(미완 JSON 원인). 없으면 None.
    finish_reason: Optional[str] = None


Message = dict  # {"role": "system"|"user"|"assistant", "content": str}


class SupportsChat(Protocol):
    """오케스트레이터가 요구하는 최소 인터페이스 — GLMClient·FakeLLM 공용."""

    def chat(self, messages: list[Message], **kwargs) -> ChatResult: ...


# 400 본문이 '컨텍스트/토큰 초과'를 가리키는 신호들(서버마다 문구가 달라 넓게 잡음).
_CONTEXT_OVERFLOW_HINTS = (
    "context length",
    "context window",
    "maximum context",
    "context_length_exceeded",
    "max_tokens",
    "max_model_len",
    "too many tokens",
    "exceeds",
    "reduce the length",
    "토큰",
)


def _is_context_overflow(detail: str) -> bool:
    low = (detail or "").lower()
    return any(h in low for h in _CONTEXT_OVERFLOW_HINTS)


class GLMClient:
    """OpenAI 호환 비스트리밍 chat completion 클라이언트.

    - max_tokens: config.max_tokens == 0 이면 미전송 (원칙③).
    - reasoning_effort: 톱레벨 필드 금지 — 요청 본문의 `chat_template_kwargs`
      (openai SDK 의 extra_body 경유와 동일한 wire 포맷)로만 전달 (원칙②).
    - response_format json_object 시도 후 400 이면 옵션 제거 재시도 (원칙⑤).
    - transport: 테스트용 httpx.MockTransport 주입 지점.
    """

    def __init__(
        self, config: LLMConfig | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.config = config or load_llm_config()
        self._transport = transport

    def chat(
        self,
        messages: list[Message],
        *,
        json_mode: bool | None = None,
        reasoning_effort: str | None = None,
        timeout: float | None = None,
    ) -> ChatResult:
        cfg = self.config
        json_on = cfg.json_object if json_mode is None else json_mode
        effort = cfg.reasoning_effort if reasoning_effort is None else reasoning_effort
        timeout = cfg.timeout_sec if timeout is None else timeout

        body: dict = {"model": cfg.model, "messages": messages}
        if cfg.max_tokens > 0:
            body["max_tokens"] = cfg.max_tokens
        if json_on:
            body["response_format"] = {"type": "json_object"}
        if effort:
            body["chat_template_kwargs"] = {"reasoning_effort": effort}

        headers = {"Content-Type": "application/json"}
        if cfg.api_key:
            headers["Authorization"] = f"Bearer {cfg.api_key}"

        def _post(b: dict) -> httpx.Response:
            with httpx.Client(timeout=timeout, transport=self._transport, trust_env=False) as c:
                resp = c.post(f"{cfg.base_url}/chat/completions", json=b, headers=headers)
                resp.raise_for_status()
                return resp

        try:
            resp = _post(body)
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            detail = ""
            if exc.response is not None:
                try:
                    detail = exc.response.text or ""
                except Exception:  # noqa: BLE001 — 본문 못 읽어도 진행
                    detail = ""
            # 컨텍스트(토큰) 초과는 같은 입력으로 재시도해도 동일 → 별도 예외.
            if status_code == 400 and _is_context_overflow(detail):
                raise LLMContextError(
                    f"요청(프롬프트+생성)이 모델 토큰 한도를 초과했습니다: {detail[:300]}"
                ) from exc
            # response_format 미지원 서버도 400 — 그 옵션만 빼고 1회 재시도.
            if status_code == 400 and json_on and cfg.fallback_on_400:
                body.pop("response_format", None)
                try:
                    resp = _post(body)
                except httpx.HTTPError as exc2:
                    raise LLMError(f"openai 호환 호출 실패: {exc2}") from exc2
            else:
                raise LLMError(f"openai 호환 호출 실패: {exc}") from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"openai 호환 호출 실패: {exc}") from exc

        return _parse_openai_response(resp.json(), fallback_model=cfg.model)

    def chat_json(self, messages: list[Message], **kwargs) -> tuple[dict, list[ChatResult]]:
        """유효 JSON 객체가 나올 때까지 config.parse_retries 회 재호출한다."""
        return chat_json(self, messages, parse_retries=self.config.parse_retries, **kwargs)


def _parse_openai_response(data: dict, *, fallback_model: str) -> ChatResult:
    """OpenAI 호환 응답을 관대하게 파싱 — content 본문, reasoning_content/reasoning 분리."""
    choices = data.get("choices")
    if not choices:
        raise LLMError(f"openai 호환 응답에 choices 가 없음: {str(data)[:200]}")
    msg = (choices[0] or {}).get("message") or {}
    content = (msg.get("content") or "").strip()
    reasoning = msg.get("reasoning_content") or msg.get("reasoning")
    if isinstance(reasoning, str):
        reasoning = reasoning.strip() or None
    if not content and not reasoning:
        raise LLMError("openai 호환 응답에 content/reasoning 둘 다 없음")
    return ChatResult(
        content=content,
        reasoning=reasoning,
        model=data.get("model") or fallback_model,
        usage=data.get("usage"),
        raw=data,
        finish_reason=(choices[0] or {}).get("finish_reason"),
    )


_FENCE_OPEN = re.compile(r"^```[a-zA-Z]*\s*")
_FENCE_CLOSE = re.compile(r"\s*```$")


def extract_json(text: str) -> dict:
    """응답 텍스트에서 JSON 객체 1개를 관대하게 추출한다 (코드펜스·앞뒤 잡음 허용)."""
    t = (text or "").strip()
    if t.startswith("```"):
        t = _FENCE_CLOSE.sub("", _FENCE_OPEN.sub("", t))
    try:
        obj = _json.loads(t)
    except ValueError:
        s, e = t.find("{"), t.rfind("}")
        if s == -1 or e <= s:
            raise ValueError(f"JSON 객체를 찾지 못했다: {t[:120]!r}") from None
        obj = _json.loads(t[s : e + 1])
    if not isinstance(obj, dict):
        raise ValueError(f"JSON 객체가 아니다: {type(obj).__name__}")
    return obj


_PARSE_RETRY_NUDGE = (
    "직전 응답이 유효한 JSON 객체가 아니다. 설명·코드펜스 없이 "
    "요구된 키만 가진 JSON 객체 하나만 다시 출력하라."
)


def chat_json(
    llm: SupportsChat, messages: list[Message], *, parse_retries: int = 2, **chat_kwargs
) -> tuple[dict, list[ChatResult]]:
    """`.chat` 을 가진 어떤 클라이언트로든 JSON 객체 응답을 강제한다.

    파싱 실패 시 실패 응답 + 교정 지시를 덧붙여 최대 parse_retries 회 재호출.
    반환: (파싱된 dict, 시도한 모든 ChatResult 목록 — 토큰 집계용).
    """
    results: list[ChatResult] = []
    msgs = list(messages)
    last_exc: Exception | None = None
    for _ in range(parse_retries + 1):
        res = llm.chat(msgs, **chat_kwargs)
        results.append(res)
        try:
            return extract_json(res.content), results
        except ValueError as exc:
            last_exc = exc
            msgs = msgs + [
                {"role": "assistant", "content": res.content},
                {"role": "user", "content": _PARSE_RETRY_NUDGE},
            ]
    raise LLMError(f"JSON 파싱 {parse_retries + 1}회 모두 실패: {last_exc}")
