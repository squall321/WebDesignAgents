# wdpipeline.scenario 테스트 — 규칙 기반 조립·스키마 준수·narration x-read 연결·검증 실패 케이스
from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from wdcore.models.scenario import ScenarioDoc
from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file
from wdpipeline.scenario import (
    TEMPLATE_ORDER,
    assemble_demo_scenario,
    validate_scenario,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
MODULES = REPO_ROOT / "modules"


@pytest.fixture(scope="module")
def doc() -> ScenarioDoc:
    norm = ingest_report_file(SAMPLE)
    return assemble_demo_scenario(norm, fragmentize(norm))


def test_assembles_seven_scenes(doc: ScenarioDoc):
    assert len(doc.scenes) == 7
    assert [s.tpl.split("@")[0] for s in doc.scenes] == TEMPLATE_ORDER
    assert doc.meta.core_message == "ReportArchive 플랫폼 사용 설명서"  # ai_summary 없음 → 제목
    assert doc.meta.duration_sec == sum(s.dur for s in doc.scenes)
    # 씬 이름은 유일해야 한다 (children 맵 키)
    names = [s.name for s in doc.scenes]
    assert len(set(names)) == 7


def test_scene_data_passes_template_schemas(doc: ScenarioDoc):
    """각 씬 data 는 템플릿 schema.json 의 maxLength 포함 전 제약을 지켜야 한다."""
    for name in TEMPLATE_ORDER:
        schema = json.loads(
            (MODULES / "scene-templates" / name / "schema.json").read_text(encoding="utf-8")
        )
        errors = list(Draft202012Validator(schema).iter_errors(doc.content[name]))
        assert not errors, f"{name}: {[e.message for e in errors]}"


def test_narration_links_x_read(doc: ScenarioDoc):
    """narration 은 x-read 필드 연결 — 오프닝 낭독에 badge/title/subtitle 이 들어가야 한다."""
    op = next(s for s in doc.scenes if s.tpl.startswith("opening@"))
    data = doc.content["opening"]
    assert data["badge"] in op.narration
    assert data["subtitle"].rstrip("…") in op.narration or data["subtitle"] in op.narration
    for s in doc.scenes:
        assert s.narration.strip(), f"씬 {s.name} narration 이 비었다"


def test_validate_passes(doc: ScenarioDoc):
    assert validate_scenario(doc, modules_root=MODULES) == []


# ── 검증 실패 케이스 ────────────────────────────────────────────────────


def _clone(doc: ScenarioDoc) -> dict:
    return doc.model_dump()


def test_validate_unknown_template(doc: ScenarioDoc):
    d = _clone(doc)
    d["scenes"][0]["tpl"] = "nope@1"
    errors = validate_scenario(ScenarioDoc.model_validate(d), modules_root=MODULES)
    assert any("레지스트리에 없는 템플릿" in e for e in errors)


def test_validate_bad_tpl_ref_format(doc: ScenarioDoc):
    d = _clone(doc)
    d["scenes"][0]["tpl"] = "opening"  # @major 누락
    errors = validate_scenario(ScenarioDoc.model_validate(d), modules_root=MODULES)
    assert any("tpl 참조 형식 오류" in e for e in errors)


def test_validate_dangling_data_ref(doc: ScenarioDoc):
    d = _clone(doc)
    d["scenes"][0]["data_ref"] = "content.missing"
    errors = validate_scenario(ScenarioDoc.model_validate(d), modules_root=MODULES)
    assert any("경로가 문서에 없다" in e for e in errors)


def test_validate_schema_violation(doc: ScenarioDoc):
    d = _clone(doc)
    d["content"]["opening"]["badge"] = "긴" * 40  # maxLength 30 위반
    errors = validate_scenario(ScenarioDoc.model_validate(d), modules_root=MODULES)
    assert any("데이터 스키마 위반" in e and "badge" in e for e in errors)


def test_validate_duplicate_scene_names(doc: ScenarioDoc):
    d = _clone(doc)
    d["scenes"][1]["name"] = d["scenes"][0]["name"]
    errors = validate_scenario(ScenarioDoc.model_validate(d), modules_root=MODULES)
    assert any("씬 이름 중복" in e for e in errors)


def test_validate_om_scenes_budget(doc: ScenarioDoc):
    """긴 씬 이름 50개로 축약형 16KB 예산 초과를 유발한다."""
    d = _clone(doc)
    base = d["scenes"][0]
    d["scenes"] = [
        {**base, "name": f"씬-{i:02d}-" + "가" * 200, "stills": []} for i in range(50)
    ]
    errors = validate_scenario(ScenarioDoc.model_validate(d), modules_root=MODULES)
    assert any("16KB 상한" in e for e in errors)
