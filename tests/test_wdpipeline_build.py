# wdpipeline.build 테스트 — 렌더 패키지 산출 구조·엔진 무수정 사본·OM_SCENES 주입 계약
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from wdcore.models.scenario import ScenarioDoc, om_scenes_json
from wdpipeline.build import build_render_package
from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"


@pytest.fixture(scope="module")
def doc() -> ScenarioDoc:
    from wdpipeline.scenario import assemble_demo_scenario

    norm = ingest_report_file(SAMPLE)
    return assemble_demo_scenario(norm, fragmentize(norm))


@pytest.fixture(scope="module")
def build_dir(doc: ScenarioDoc, tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("build") / "demo"
    entry = build_render_package(doc, out)
    assert entry == out / "index.html"
    return out


def test_package_structure(build_dir: Path):
    for rel in (
        "index.html",
        "scenes.jsx",
        "scene-data.json",
        "runtime/animations-v2.jsx",
        "tokens/loader.jsx",
        "tokens/hwax-blue.json",
        "templates/omx-metaphors.jsx",
        "templates/omx-templates.jsx",
        "vendor/react.production.min.js",
        "vendor/react-dom.production.min.js",
        "vendor/babel.min.js",
    ):
        assert (build_dir / rel).is_file(), f"산출물 누락: {rel}"


def test_engine_copied_unmodified(build_dir: Path):
    """엔진 불가침 — 사본은 원본과 바이트 동일해야 한다."""
    src = (REPO_ROOT / "web" / "runtime" / "animations-v2.jsx").read_bytes()
    assert (build_dir / "runtime" / "animations-v2.jsx").read_bytes() == src


def test_om_scenes_injection(build_dir: Path, doc: ScenarioDoc):
    """OM_SCENES 는 축약형(name/dur/nat/stills/tpl) JSON 문자열 리터럴이어야 한다."""
    html = (build_dir / "index.html").read_text(encoding="utf-8")
    m = re.search(r"window\.OM_SCENES = (\".*?\");</script>", html)
    assert m, "OM_SCENES 주입 스크립트가 없다"
    injected = json.loads(m.group(1))          # JS 리터럴 → 파이썬 문자열
    assert injected == om_scenes_json(doc)
    scenes = json.loads(injected)
    assert len(scenes) == len(doc.scenes)
    for sc in scenes:
        assert set(sc.keys()) <= {"name", "dur", "nat", "stills", "tpl"}
    # OM_THEME/OM_PLAYBACK 주입 채널
    assert "window.OM_THEME = " in html
    assert "window.OM_PLAYBACK = " in html


def test_load_order_contract(build_dir: Path):
    """로드 순서: 엔진 → 토큰 로더 → 은유 → 템플릿 → scenes.jsx (레지스트리 계약)."""
    html = (build_dir / "index.html").read_text(encoding="utf-8")
    order = [
        'src="./runtime/animations-v2.jsx"',
        'src="./tokens/loader.jsx"',
        'src="./templates/omx-metaphors.jsx"',
        'src="./templates/omx-templates.jsx"',
        'src="./scenes.jsx"',
    ]
    positions = [html.index(p) for p in order]
    assert positions == sorted(positions)


def test_scenes_jsx_bindings(build_dir: Path, doc: ScenarioDoc):
    """scenes.jsx 는 씬 name → 템플릿 바인딩 맵 + 비충돌 별칭 규약을 지켜야 한다."""
    jsx = (build_dir / "scenes.jsx").read_text(encoding="utf-8")
    assert "const SceneRoot = window.SceneStage" in jsx  # const 충돌 규약
    for s in doc.scenes:
        assert json.dumps(s.name, ensure_ascii=False) in jsx
        assert f'"tpl.{s.tpl.split("@")[0]}"' in jsx
        assert json.dumps(s.data_ref) in jsx
    # 엔진 최상위 선언과 겹치는 이름을 새로 선언하지 않는다
    for banned in ("const Easing", "const Stage", "const animate", "function SceneStage"):
        assert banned not in jsx


def test_scene_data_roundtrip(build_dir: Path, doc: ScenarioDoc):
    """scene-data.json 은 ScenarioDoc 전체 덤프 — data_ref 가 그 안에서 해석돼야 한다."""
    data = json.loads((build_dir / "scene-data.json").read_text(encoding="utf-8"))
    assert ScenarioDoc.model_validate(data) == doc
    for s in doc.scenes:
        node = data
        for seg in s.data_ref.split("."):
            assert seg in node, f"data_ref {s.data_ref} 해석 실패"
            node = node[seg]
        assert isinstance(node, dict)


def test_unknown_theme_raises(doc: ScenarioDoc, tmp_path: Path):
    bad = doc.model_copy(update={"tokens_theme": "no-such-theme"})
    with pytest.raises(FileNotFoundError, match="no-such-theme"):
        build_render_package(bad, tmp_path / "x")
