# wdcore 도메인 예외 계층 — 어댑터(wdmcp/wdllm)가 오류 코드로 매핑한다
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/errors.py (copy-adapt: RAG 계열 예외 제거, Expert→Persona)
from __future__ import annotations


class WebDesignAgentsError(Exception):
    """모든 도메인 예외의 베이스."""

    error_code = "internal_error"

    def __init__(self, message: str, **context: object) -> None:
        super().__init__(message)
        self.message = message
        self.context = context


class RegistryError(WebDesignAgentsError):
    """레지스트리 로드/검증 실패 (fail-fast)."""

    error_code = "registry_error"


class PersonaNotFoundError(WebDesignAgentsError):
    error_code = "persona_not_found"


class CardValidationError(WebDesignAgentsError):
    """지식카드 frontmatter/본문 규약 위반."""

    error_code = "card_validation_error"
