# patch_scenario 정본 테스트 — 원자 연산 8종·diff 요약·실패 시 전체 취소(원본 무손상)
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file
from wdpipeline.patch import PatchError, apply_op, patch_scenario
from wdpipeline.scenario import assemble_demo_scenario

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"


@pytest.fixture(scope="module")
def scenario() -> dict:
    """규칙 기반 데모 조립 시나리오 (검증 통과 상태) — 각 테스트는 사본으로 시작한다."""
    norm = ingest_report_file(REPORT_SAMPLE)
    doc = assemble_demo_scenario(norm, fragmentize(norm))
    return doc.model_dump()


def _snap(d: dict) -> str:
    return json.dumps(d, sort_keys=True, ensure_ascii=False)


def _scene(doc: dict, name: str) -> dict:
    return next(s for s in doc["scenes"] if s["name"] == name)


# ── 성공 경로 — 연산별 적용 + diff 요약 ─────────────────────────────────────


def test_set_data_applies_with_readable_diff(scenario: dict) -> None:
    before = _snap(scenario)
    patched, diffs = patch_scenario(scenario, [
        {"op": "set_data", "scene": "절차", "path": "steps.0.name", "value": "개인 워크스페이스"},
    ])
    assert patched["content"]["process"]["steps"][0]["name"] == "개인 워크스페이스"
    assert len(diffs) == 1
    # 사람이 읽는 diff — "절차.steps.0.name: '옛값'→'새값'"
    assert diffs[0].startswith("절차.steps.0.name: ")
    assert "→'개인 워크스페이스'" in diffs[0]
    assert _snap(scenario) == before  # 원본 무변형


def test_set_data_bracket_path_and_dur_reclamp(scenario: dict) -> None:
    patched, diffs = patch_scenario(scenario, [
        {"op": "set_data", "scene": "절차", "path": "steps[1].name", "value": "게시"},
        {"op": "set_dur", "scene": "절차", "dur": 14},
    ])
    assert patched["content"]["process"]["steps"][1]["name"] == "게시"
    scene = _scene(patched, "절차")
    assert scene["dur"] == 14
    # 기존 스틸 17.0 은 14 초과 → dur-1.0 으로 재클램프
    assert scene["stills"] and all(t <= 14 for t in scene["stills"])
    assert any("dur" in d and "14" in d for d in diffs)


def test_narration_stills_tpl_ops(scenario: dict) -> None:
    patched, diffs = patch_scenario(scenario, [
        {"op": "set_narration", "scene": "오프닝", "text": "새 인트로 대본입니다."},
        {"op": "set_stills", "scene": "오프닝", "stills": [3.5, 7.0]},
        {"op": "set_tpl", "scene": "절차", "tpl": "process"},  # major 미지정 → 레지스트리 보정
    ])
    assert _scene(patched, "오프닝")["narration"] == "새 인트로 대본입니다."
    assert _scene(patched, "오프닝")["stills"] == [3.5, 7.0]
    assert _scene(patched, "절차")["tpl"] == "process@1"
    assert len(diffs) == 3 and all(isinstance(d, str) and "→" in d for d in diffs)


def test_reorder_remove_insert(scenario: dict) -> None:
    names = [s["name"] for s in scenario["scenes"]]
    swapped = [names[1], names[0], *names[2:]]
    proof_data = copy.deepcopy(scenario["content"]["proof"])
    patched, diffs = patch_scenario(scenario, [
        {"op": "reorder", "names": swapped},
        {"op": "remove_scene", "scene": "차별점"},
        {"op": "insert_scene", "after": "실증", "tpl": "proof", "name": "실증-추가",
         "data": proof_data, "dur": 10},
    ])
    got = [s["name"] for s in patched["scenes"]]
    assert got[0] == names[1] and got[1] == names[0]
    assert "차별점" not in got
    assert got[got.index("실증") + 1] == "실증-추가"
    ins = _scene(patched, "실증-추가")
    assert ins["dur"] == 10 and ins["tpl"] == "proof@1"
    assert ins["data_ref"].startswith("content.")
    assert diffs and any("씬 삽입" in d for d in diffs) and any("씬 제거" in d for d in diffs)


# ── 실패 경로 — 전체 취소 + 오류 목록 ───────────────────────────────────────


def test_validation_failure_rolls_back_everything(scenario: dict) -> None:
    """앞 연산이 유효해도 뒤 연산이 검증을 깨면 전량 취소 — 원본 무손상."""
    before = _snap(scenario)
    with pytest.raises(PatchError) as ei:
        patch_scenario(scenario, [
            {"op": "set_dur", "scene": "절차", "dur": 14},   # 단독으로는 유효
            {"op": "set_dur", "scene": "오프닝", "dur": 400},  # ssParse (0,300] 위반
        ])
    assert ei.value.errors  # 오류 목록 보존
    assert _snap(scenario) == before


def test_op_level_rejection_is_atomic(scenario: dict) -> None:
    before = _snap(scenario)
    with pytest.raises(PatchError) as ei:
        patch_scenario(scenario, [
            {"op": "set_dur", "scene": "절차", "dur": 14},
            {"op": "set_tpl", "scene": "절차", "tpl": "megachart@1"},  # 레지스트리에 없음
        ])
    assert any("megachart" in e for e in ei.value.errors)
    assert _snap(scenario) == before


def test_unknown_scene_op_path_and_empty_ops(scenario: dict) -> None:
    with pytest.raises(PatchError):
        patch_scenario(scenario, [{"op": "set_dur", "scene": "없는씬", "dur": 5}])
    with pytest.raises(PatchError):
        patch_scenario(scenario, [{"op": "폭파", "scene": "절차"}])
    with pytest.raises(PatchError):
        patch_scenario(scenario, [{"op": "set_data", "scene": "절차", "path": "no.such", "value": 1}])
    with pytest.raises(PatchError):
        patch_scenario(scenario, [])
    with pytest.raises(PatchError):
        patch_scenario(scenario, [{"op": "set_stills", "scene": "절차", "stills": [999.0]}])
    with pytest.raises(PatchError):
        patch_scenario(scenario, [{"op": "reorder", "names": ["절차"]}])


def test_apply_op_single_returns_diff_or_error(scenario: dict) -> None:
    """챗 액션 루프가 소비하는 단건 API — (diff, None) | (None, 사유)."""
    work = copy.deepcopy(scenario)
    diff, err = apply_op(work, {"op": "set_dur", "scene": "절차", "dur": 12})
    assert err is None and "dur" in diff and "12" in diff
    diff2, err2 = apply_op(work, {"op": "set_dur", "scene": "유령", "dur": 12})
    assert diff2 is None and "유령" in err2
