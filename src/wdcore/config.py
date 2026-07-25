# 환경변수/.env 기반 전역 설정 — 모든 모듈은 get_settings()로 접근 (WDA_ 접두)
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/config.py (copy-adapt: 임베딩/검색/라우팅 설정 제거, EXPERTS_→WDA_)
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="WDA_", env_file=".env", env_file_encoding="utf-8", extra="ignore",
    )

    # --- 경로 ---
    personas_root: Path = Field(default=Path("personas"), description="persona.yaml 루트 (PLAN §5.1)")
    data_dir: Path = Field(default=Path("data"), description="런타임 데이터 루트 (회의·파이프라인 산출물)")

    # --- 레지스트리 ---
    strict_refs: bool = Field(
        default=False,
        description="True면 related_personas 미존재 id를 오류로 처리 (14인 로스터 완성 후 True 전환)",
    )

    # --- 로깅 ---
    log_level: str = "INFO"

    @property
    def meetings_dir(self) -> Path:
        return self.data_dir / "meetings"

    @property
    def pipeline_dir(self) -> Path:
        return self.data_dir / "pipeline"


@lru_cache
def get_settings() -> Settings:
    return Settings()
