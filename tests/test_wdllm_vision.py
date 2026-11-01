# 비전(VLM) 메시지 계약 — 렌더된 씬을 페르소나가 보고 비평하는 채널 (PLAN 경로 B 시각 심의)
from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
import pytest

from wdllm.client import GLMClient, image_block, user_message
from wdllm.config import LLMConfig

PNG = Path("modules/scene-templates/opening/fixtures/snapshots/typical.png")


def test_text_only_message_stays_a_plain_string():
    """이미지가 없는데 블록 배열로 보내면 비전을 안 쓰는 모델에서 불필요한 위험을 진다."""
    assert user_message("안녕")["content"] == "안녕"


def test_image_block_is_an_inline_data_url(tmp_path: Path):
    """vLLM 서버는 우리 파일 시스템을 못 본다 — 링크가 아니라 인라인이어야 한다."""
    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
    block = image_block(img)
    assert block["type"] == "image_url"
    url = block["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == img.read_bytes()


def test_bytes_source_works_without_a_file(tmp_path: Path):
    """스틸을 디스크에 떨구지 않고도 실을 수 있어야 한다."""
    assert image_block(b"RAW", mime="image/jpeg")["image_url"]["url"].startswith(
        "data:image/jpeg;base64,")


@pytest.mark.skipif(not PNG.is_file(), reason="골든 스냅샷 없음")
def test_vision_message_reaches_the_request_body():
    """전송 계층은 messages 를 그대로 직렬화한다 — 블록 배열이 몸통에 실려야 한다."""
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            "model": "glm-vision", "usage": {},
        })

    cfg = LLMConfig(
        base_url="http://x/v1", model="glm-vision", api_key="k", disable_streaming=True,
        max_tokens=0, timeout_sec=5, reasoning_effort="", json_object=False,
        fallback_on_400=True, parse_retries=1,
    )
    client = GLMClient(cfg, transport=httpx.MockTransport(handler))
    client.chat([user_message("이 화면을 평가하라", [PNG])])

    content = captured["messages"][0]["content"]
    assert isinstance(content, list), "블록 배열이 문자열로 뭉개졌다 — 이미지가 사라진다"
    kinds = [b["type"] for b in content]
    assert kinds == ["text", "image_url"], kinds
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,")
