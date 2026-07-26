# 창작 모드 확장 씬 템플릿 3종(dataviz/timeline/compare)의 스키마·픽스처·module.yaml·registry 정합 검증
import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
EXT = ["compare", "dataviz", "timeline"]
FIXTURES = ["min", "typical", "max"]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
EXT_TEMPLATE_FILE = ROOT / "web" / "templates" / "omx-templates-ext.jsx"
CAPTION_CPS = 9.0  # wdqa 게이트 2 자막 낭독 속도와 동일 기준


def load_schema(name: str) -> dict:
    return json.loads((TPL_DIR / name / "schema.json").read_text(encoding="utf-8"))


def load_fixture(name: str, fixture: str) -> dict:
    return json.loads(
        (TPL_DIR / name / "fixtures" / f"{fixture}.json").read_text(encoding="utf-8")
    )


def walk_has_x_read(node) -> bool:
    if isinstance(node, dict):
        if node.get("x-read") is True:
            return True
        return any(walk_has_x_read(v) for v in node.values())
    if isinstance(node, list):
        return any(walk_has_x_read(v) for v in node)
    return False


def walk_strings_have_maxlength(node, path="") -> list:
    """문자열 타입 선언 중 maxLength 가 빠진 경로 목록."""
    missing = []
    if isinstance(node, dict):
        if node.get("type") == "string" and "maxLength" not in node:
            missing.append(path)
        for k, v in node.items():
            if k in ("enum", "const"):
                continue
            missing += walk_strings_have_maxlength(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            missing += walk_strings_have_maxlength(v, f"{path}/{i}")
    return missing


def test_ext_templates_present():
    for name in EXT:
        assert (TPL_DIR / name).is_dir(), f"{name} 모듈 디렉터리가 없다"
    assert EXT_TEMPLATE_FILE.exists()


@pytest.mark.parametrize("name", EXT)
def test_schema_is_valid_jsonschema(name):
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema.get("type") == "object"


@pytest.mark.parametrize("name", EXT)
def test_schema_has_x_read_and_maxlength(name):
    schema = load_schema(name)
    assert walk_has_x_read(schema), f"{name}: x-read 낭독 필드가 하나도 없다"
    missing = walk_strings_have_maxlength(schema)
    assert not missing, f"{name}: maxLength 누락 문자열 선언 — {missing}"


@pytest.mark.parametrize("name", EXT)
@pytest.mark.parametrize("fixture", FIXTURES)
def test_fixture_passes_schema(name, fixture):
    schema = load_schema(name)
    data = load_fixture(name, fixture)
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    msgs = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors]
    assert not msgs, f"{name}/{fixture}: {msgs}"


@pytest.mark.parametrize("name", EXT)
def test_module_yaml_contract(name):
    doc = yaml.safe_load((TPL_DIR / name / "module.yaml").read_text(encoding="utf-8"))
    assert doc["id"] == f"tpl.{name}"
    assert doc["type"] == "scene-template"
    # status 는 수명주기 필드 — module_review 심의가 승격시킨다 (dataviz 는 Go → pilot)
    assert doc["status"] in ("draft", "pilot", "active")
    assert SEMVER.match(str(doc["version"]))
    assert doc["engine_compat"] == "animations-v2"
    assert doc["origin"] == "창작 모드 2026-07-26 — 외부 샘플 없음"
    assert isinstance(doc["nat_default"], (int, float)) and doc["nat_default"] > 0
    assert doc["in_scope"] and doc["out_of_scope"]
    assert doc["metaphors"] == ["frame-chrome", "dot-grid"], "허용 은유는 공통 크롬 2종뿐"
    entry = doc["entry"]
    tpl_file = ROOT / entry["template"].split("#")[0]
    assert tpl_file == EXT_TEMPLATE_FILE and tpl_file.exists()
    assert (TPL_DIR / name / entry["schema"]).exists()
    for fx in entry["fixtures"]:
        assert (TPL_DIR / name / fx).exists()
    assert (TPL_DIR / name / entry["preview"]).exists()


@pytest.mark.parametrize("name", EXT)
def test_ext_component_registered_in_jsx(name):
    """ext jsx 가 tpl.* id 를 templateIndex 에 병합 등록하는지 소스 수준 확인."""
    src = EXT_TEMPLATE_FILE.read_text(encoding="utf-8")
    assert f"'tpl.{name}'" in src, f"tpl.{name} 이 omx-templates-ext.jsx 에 등록되지 않았다"


def test_registry_indexes_ext_modules():
    reg = yaml.safe_load((ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    ids = [m["id"] for m in reg["modules"]]
    assert len(ids) == len(set(ids)), "레지스트리 id 중복"
    for name in EXT:
        assert f"tpl.{name}" in ids
        entry = next(m for m in reg["modules"] if m["id"] == f"tpl.{name}")
        assert entry["type"] == "scene-template"
        assert (ROOT / entry["path"] / "module.yaml").exists()
        mod = yaml.safe_load((ROOT / entry["path"] / "module.yaml").read_text(encoding="utf-8"))
        assert mod["nat_default"] == entry["nat_default"], f"{name}: nat_default 불일치"
    order = reg["load_order_contract"]
    base = order.index("web/templates/omx-templates.jsx")
    assert order[base + 1] == "web/templates/omx-templates-ext.jsx", (
        "ext 파일은 omx-templates.jsx 직후에 로드되어야 한다"
    )
    assert order.index("web/templates/omx-templates-ext.jsx") < order.index("<project scenes.jsx>")


# ── 창작 모드 고유 계약 — 수치 왜곡 방지·상태 구성 강제 ──────────────────────


def test_dataviz_schema_enforces_zero_baseline_and_proportion():
    schema = load_schema("dataviz")
    props = schema["properties"]
    assert schema["additionalProperties"] is False and "axisMin" not in props, (
        "축 하한 필드가 존재하면 0 기준선 강제가 깨진다"
    )
    bar_props = props["bars"]["items"]["properties"]
    assert bar_props["value"]["minimum"] == 0, "value 는 minimum:0 (음수 막대 금지)"
    assert props["axisMax"]["exclusiveMinimum"] == 0
    assert props["bars"]["minContains"] == 1 and props["bars"]["maxContains"] == 1, (
        "강조 막대는 정확히 1개"
    )
    # 강조 2개 데이터는 스키마가 거부해야 한다
    bad = load_fixture("dataviz", "min")
    bad = json.loads(json.dumps(bad))
    for b in bad["bars"]:
        b["emphasis"] = True
    assert list(Draft202012Validator(schema).iter_errors(bad)), "emphasis 2개가 통과되면 안 된다"


def test_timeline_schema_enforces_single_current():
    schema = load_schema("timeline")
    ms = schema["properties"]["milestones"]
    assert ms["minContains"] == 1 and ms["maxContains"] == 1
    bad = load_fixture("timeline", "min")
    bad = json.loads(json.dumps(bad))
    for m in bad["milestones"]:
        m["status"] = "planned"
    assert list(Draft202012Validator(schema).iter_errors(bad)), "current 0개가 통과되면 안 된다"


def test_compare_rows_are_paired():
    schema = load_schema("compare")
    row_req = schema["properties"]["rows"]["items"]["required"]
    assert set(row_req) == {"aspect", "a", "b"}, "행은 항상 A/B 짝으로 강제"


# ── 게이트 2 예산 — typical 픽스처의 x-read 글자수가 nat 안에 낭독 가능한지 ──


def _collect_read_chars(schema: dict, data) -> int:
    from wdqa.gate2_length import collect_read_chars

    return collect_read_chars(schema, data)


@pytest.mark.parametrize("name", EXT)
def test_typical_fixture_fits_caption_budget(name):
    schema = load_schema(name)
    data = load_fixture(name, "typical")
    mod = yaml.safe_load((TPL_DIR / name / "module.yaml").read_text(encoding="utf-8"))
    chars = _collect_read_chars(schema, data)
    assert chars > 0, f"{name}: typical 에 x-read 글자가 없다"
    need = chars / CAPTION_CPS
    assert need <= mod["nat_default"], (
        f"{name}: x-read {chars}자 ÷ {CAPTION_CPS}자/초 = {need:.1f}s > nat {mod['nat_default']}s"
    )
