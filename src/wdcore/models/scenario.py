# ScenarioDoc — 심의 산출 시나리오 JSON의 단일 정본 스키마 + OM_SCENES 주입 축약형 검사 (PLAN §4 P3, 신규)
from __future__ import annotations

import json
from typing import Literal

from pydantic import Field, model_validator

from .common import StrictModel

# 렌더 엔진 ssParse 계약 (docs/analysis/engine-analysis.md): OM_SCENES ≤16KB, 1~50씬, dur∈(0,300]
OM_SCENES_MAX_BYTES = 16 * 1024
# OM_SCENES 주입 시 남기는 축약형 키 (설계안 2 규칙 — 16KB 상한 대응)
OM_SCENES_INJECT_KEYS = ("name", "dur", "nat", "stills", "tpl")


class ScenarioMeta(StrictModel):
    """시나리오 헤더 — 심의가 확정한 단일 메시지·청중·러닝타임."""

    core_message: str = Field(min_length=1)
    audience: str = ""
    duration_sec: float = Field(gt=0)
    tone: str = ""
    meeting_id: str | None = Field(default=None, description="산출 근거 회의 ID (P2 추적)")
    source_report_id: int | None = Field(default=None, description="원천 ReportArchive 보고서 ID")


class SceneEntry(StrictModel):
    """씬 1개. dur/stills 제약은 렌더 엔진 ssParse + PPT 추출 계약을 따른다."""

    name: str = Field(min_length=1, description="씬 이름 — children 맵 키와 정확 일치 필수")
    dur: float = Field(gt=0, le=300, description="재생 길이(초). ssParse 계약 (0,300]")
    nat: float | None = Field(default=None, gt=0, description="자연 길이(초). 타임 스트레치 기준")
    tpl: str = Field(min_length=1, description="템플릿 참조. 예: 'opening@1'")
    stills: list[float] = Field(default_factory=list, description="PPT 정지 캡처 시각(씬 로컬 초)")
    data_ref: str = Field(default="", description="content 하위 데이터 경로. 예: 'content.opening'")
    narration: str = Field(default="", description="TTS 내레이션 대본")
    transition: str = "cut"

    @model_validator(mode="after")
    def _stills_in_range(self) -> "SceneEntry":
        for s in self.stills:
            if not 0 <= s <= self.dur:
                raise ValueError(
                    f"stills 시각 {s}가 [0, dur={self.dur}] 범위를 벗어났다 (씬 {self.name!r})"
                )
        return self


class PlaybackSpec(StrictModel):
    """OM_PLAYBACK 계약 — '{\"mode\":\"loop\"}' 또는 '{\"mode\":\"times\",\"count\":1..99}'."""

    mode: Literal["loop", "times"] = "times"
    count: int = Field(default=1, ge=1, le=99)


class ScenarioDoc(StrictModel):
    """시나리오 문서 정본 (PLAN §4 P3 스키마). P3 검증·P4 빌드·P5 export가 공유한다."""

    version: Literal["1.0"] = "1.0"
    meta: ScenarioMeta
    content: dict[str, dict] = Field(
        default_factory=dict, description="템플릿별 데이터 (opening/problem/… — 스키마 검증은 템플릿 레지스트리 몫)"
    )
    scenes: list[SceneEntry] = Field(min_length=1, max_length=50)
    tokens_theme: str = "hwax-blue"
    playback: PlaybackSpec = Field(default_factory=PlaybackSpec)


def om_scenes_json(doc: ScenarioDoc) -> str:
    """OM_SCENES 주입용 축약형 직렬화 — name/dur/nat/stills/tpl만 남긴다 (설계안 2 규칙).

    nat 미지정·stills 빈 씬은 해당 키를 생략해 바이트를 아낀다. 여분 필드(narration 등)는
    엔진이 scene prop으로 무가공 전달하는 확장 지점이지만 주입 시에는 16KB 상한 때문에 뺀다.
    """
    entries: list[dict] = []
    for s in doc.scenes:
        e: dict = {"name": s.name, "dur": s.dur, "tpl": s.tpl}
        if s.nat is not None:
            e["nat"] = s.nat
        if s.stills:
            e["stills"] = s.stills
        entries.append(e)
    return json.dumps(entries, ensure_ascii=False, separators=(",", ":"))


def check_om_scenes_budget(doc: ScenarioDoc) -> int:
    """축약형 직렬화의 UTF-8 바이트 수를 반환한다. ssParse 16KB 상한 초과면 ValueError."""
    size = len(om_scenes_json(doc).encode("utf-8"))
    if size > OM_SCENES_MAX_BYTES:
        raise ValueError(
            f"OM_SCENES 축약형이 16KB 상한을 초과한다: {size} > {OM_SCENES_MAX_BYTES} bytes"
        )
    return size
