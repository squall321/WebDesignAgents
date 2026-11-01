# 카메라 워크 계약 — 씬 전체에 거는 변환. 게이트 7(경계 정적)을 설계상 지켜야 한다
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
TOKENS = REPO_ROOT / "web" / "tokens"
KINDS = ("hold", "pushIn", "pullOut", "panRight", "kenBurns")


def _themes() -> list[str]:
    reg = yaml.safe_load((REPO_ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    return [m["id"].split(".", 1)[1] for m in reg["modules"] if m["type"] == "theme"]


@pytest.mark.parametrize("theme", _themes())
def test_every_theme_declares_every_camera_kind(theme: str):
    """한 테마만 빠져도 그 테마에서 그 연출이 조용히 사라진다."""
    cam = (json.loads((TOKENS / f"{theme}.json").read_text(encoding="utf-8"))
           ["semantic"]["motion"].get("camera") or {})
    missing = [k for k in KINDS if k not in cam]
    assert not missing, f"{theme} 에 없는 카메라: {missing}"
    for k in KINDS:
        for field in ("scaleFrom", "scaleTo", "panXFrom", "panXTo", "panYFrom", "panYTo"):
            assert field in cam[k], f"{theme}.{k} 에 {field} 가 없다"


@pytest.mark.parametrize("theme", _themes())
def test_hold_is_truly_still(theme: str):
    """hold 는 '카메라를 안 쓴다' 다 — 값이 하나라도 움직이면 기존 산출물이 바뀐다."""
    cam = (json.loads((TOKENS / f"{theme}.json").read_text(encoding="utf-8"))
           ["semantic"]["motion"]["camera"]["hold"])
    assert cam["scaleFrom"] == cam["scaleTo"] == 1.0
    assert cam["panXFrom"] == cam["panXTo"] == cam["panYFrom"] == cam["panYTo"] == 0.0


def test_scene_model_rejects_unknown_camera():
    """오타가 조용히 'hold' 로 떨어지면 연출이 사라진 걸 아무도 모른다."""
    from wdcore.models.scenario import SceneEntry

    base = dict(name="s", tpl="opening@1", dur=8.0, data_ref="content.s")
    assert SceneEntry(**base).camera == "hold", "기본은 hold 여야 기존 동작이 보존된다"
    assert SceneEntry(**base, camera="pushIn").camera == "pushIn"
    with pytest.raises(Exception):
        SceneEntry(**base, camera="없는카메라")


def test_camera_is_applied_at_the_binding_layer_not_in_templates():
    """바인딩 층에 걸어야 템플릿 40종이 하나도 안 고쳐지고 같은 연출을 얻는다."""
    build_src = (REPO_ROOT / "src" / "wdpipeline" / "build.py").read_text(encoding="utf-8")
    assert "OMX.motion.camera" in build_src, "바인딩 층이 카메라를 걸지 않는다"
    assert 'data-qa-clip-ok="true"' in build_src, (
        "카메라는 무대 밖으로 확대한다 — 의도된 넘침을 선언하지 않으면 게이트 5 가 경고한다")

    engine = (REPO_ROOT / "web" / "templates" / "omx-metaphors.jsx").read_text(encoding="utf-8")
    assert "function camera(" in engine
    assert "easeInOutCubic" in engine, (
        "양 끝 속도 0 이 아니면 컷 순간에도 카메라가 움직여 게이트 7 이 깨진다")


def test_hold_scenes_emit_no_wrapper():
    """hold 면 DOM 이 그대로여야 한다 — 래퍼가 생기면 기존 골든이 흔들린다."""
    build_src = (REPO_ROOT / "src" / "wdpipeline" / "build.py").read_text(encoding="utf-8")
    assert "if (!camera || camera === 'hold') return inner;" in build_src
