# ScenarioDoc 스키마 검증 — 유효/무효 케이스와 OM_SCENES 축약형 16KB 예산 검사
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from wdcore.models import (
    OM_SCENES_MAX_BYTES,
    ScenarioDoc,
    check_om_scenes_budget,
    om_scenes_json,
)


def _doc(scenes=None, playback=None):
    return {
        "version": "1.0",
        "meta": {
            "core_message": "전문가 심의로 발표자료를 자동 생성한다",
            "audience": "사내 엔지니어",
            "duration_sec": 90,
            "tone": "신뢰-기술",
            "meeting_id": "m-0001",
            "source_report_id": 578,
        },
        "content": {"opening": {"title": "WebDesignAgents"}},
        "scenes": scenes if scenes is not None else [
            {
                "name": "오프닝", "dur": 8, "nat": 8, "tpl": "opening@1",
                "stills": [6.5], "data_ref": "content.opening",
                "narration": "전문가 심의 플랫폼을 소개합니다", "transition": "cut",
            },
            {"name": "문제", "dur": 13, "tpl": "problem@1"},
        ],
        "tokens_theme": "hwax-blue",
        "playback": playback or {"mode": "times", "count": 1},
    }


# --- 유효 케이스 ---

def test_valid_doc_parses():
    doc = ScenarioDoc.model_validate(_doc())
    assert doc.version == "1.0"
    assert len(doc.scenes) == 2
    assert doc.scenes[0].stills == [6.5]
    assert doc.playback.count == 1


def test_boundary_values_accepted():
    """dur=300(상한), stills=dur(경계), count=99(상한), 씬 50개(상한)는 모두 유효."""
    scenes = [{"name": f"s{i}", "dur": 300, "tpl": "t@1", "stills": [300]} for i in range(50)]
    doc = ScenarioDoc.model_validate(_doc(scenes=scenes, playback={"mode": "times", "count": 99}))
    assert len(doc.scenes) == 50


# --- 무효 케이스 ---

def test_empty_scenes_rejected():
    with pytest.raises(ValidationError):
        ScenarioDoc.model_validate(_doc(scenes=[]))


def test_more_than_50_scenes_rejected():
    scenes = [{"name": f"s{i}", "dur": 1, "tpl": "t@1"} for i in range(51)]
    with pytest.raises(ValidationError):
        ScenarioDoc.model_validate(_doc(scenes=scenes))


def test_dur_out_of_range_rejected():
    with pytest.raises(ValidationError):  # dur=0 → (0,300] 위반
        ScenarioDoc.model_validate(_doc(scenes=[{"name": "s", "dur": 0, "tpl": "t@1"}]))
    with pytest.raises(ValidationError):  # dur=300.5 → 상한 초과
        ScenarioDoc.model_validate(_doc(scenes=[{"name": "s", "dur": 300.5, "tpl": "t@1"}]))


def test_stills_outside_dur_rejected():
    with pytest.raises(ValidationError, match="stills"):
        ScenarioDoc.model_validate(_doc(scenes=[{"name": "s", "dur": 8, "tpl": "t@1", "stills": [8.1]}]))
    with pytest.raises(ValidationError, match="stills"):
        ScenarioDoc.model_validate(_doc(scenes=[{"name": "s", "dur": 8, "tpl": "t@1", "stills": [-0.1]}]))


def test_playback_count_out_of_range_rejected():
    with pytest.raises(ValidationError):
        ScenarioDoc.model_validate(_doc(playback={"mode": "times", "count": 0}))
    with pytest.raises(ValidationError):
        ScenarioDoc.model_validate(_doc(playback={"mode": "times", "count": 100}))


def test_unknown_extra_field_rejected():
    data = _doc()
    data["unknown_field"] = 1
    with pytest.raises(ValidationError):
        ScenarioDoc.model_validate(data)


# --- OM_SCENES 축약형 직렬화·예산 ---

def test_om_scenes_json_keeps_only_inject_keys():
    """축약형은 name/dur/nat/stills/tpl만 남긴다 — narration/data_ref/transition 제외."""
    doc = ScenarioDoc.model_validate(_doc())
    entries = json.loads(om_scenes_json(doc))
    assert len(entries) == 2
    for e in entries:
        assert set(e) <= {"name", "dur", "nat", "stills", "tpl"}
    assert entries[0]["name"] == "오프닝"
    assert "narration" not in entries[0]
    # nat 미지정·stills 빈 씬은 키 생략
    assert "nat" not in entries[1] and "stills" not in entries[1]


def test_om_scenes_budget_within_limit():
    doc = ScenarioDoc.model_validate(_doc())
    size = check_om_scenes_budget(doc)
    assert 0 < size <= OM_SCENES_MAX_BYTES


def test_om_scenes_budget_exceeded_raises():
    """씬 이름을 부풀려 축약형이 16KB를 넘으면 ValueError."""
    scenes = [{"name": f"긴이름{'가' * 400}{i}", "dur": 1, "tpl": "t@1"} for i in range(50)]
    doc = ScenarioDoc.model_validate(_doc(scenes=scenes))
    with pytest.raises(ValueError, match="16KB"):
        check_om_scenes_budget(doc)
