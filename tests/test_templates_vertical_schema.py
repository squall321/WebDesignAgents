# 세로 숏폼 템플릿 4종(vtpl.hook/stack/metric/cta)의 스키마·픽스처·module.yaml·registry·formats 선언 정합 검증
import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
VERTICAL_FILE = ROOT / "web" / "templates" / "omx-templates-vertical.jsx"
FORMAT_ID = "short-9x16"
STAGE = {"w": 1080, "h": 1920}
ORIGIN = "창작 모드 세로 포맷 2026-07-26"
# 디렉터리 → 템플릿 id (가로 tpl.* 와 이름공간 분리)
VERTICAL = {"v-hook": "vtpl.hook", "v-stack": "vtpl.stack",
            "v-metric": "vtpl.metric", "v-cta": "vtpl.cta"}
FIXTURES = ["min", "typical", "max"]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
NARRATION_CPS = 5.5   # 포맷 계약 narration.rate — 세로 숏폼 낭독 속도(공백 제외 글자/초)
HORIZONTAL_FILES = ["omx-templates.jsx", "omx-templates-ext.jsx", "omx-metaphors.jsx"]


def load_schema(name: str) -> dict:
    return json.loads((TPL_DIR / name / "schema.json").read_text(encoding="utf-8"))


def load_fixture(name: str, fixture: str) -> dict:
    return json.loads((TPL_DIR / name / "fixtures" / f"{fixture}.json").read_text(encoding="utf-8"))


def load_module(name: str) -> dict:
    return yaml.safe_load((TPL_DIR / name / "module.yaml").read_text(encoding="utf-8"))


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


def collect_maxlengths(node, out=None) -> list:
    out = [] if out is None else out
    if isinstance(node, dict):
        if node.get("type") == "string" and "maxLength" in node:
            out.append(node["maxLength"])
        for v in node.values():
            collect_maxlengths(v, out)
    elif isinstance(node, list):
        for v in node:
            collect_maxlengths(v, out)
    return out


def test_vertical_modules_present():
    for name in VERTICAL:
        assert (TPL_DIR / name).is_dir(), f"{name} 모듈 디렉터리가 없다"
    assert VERTICAL_FILE.exists()


@pytest.mark.parametrize("name", VERTICAL)
def test_schema_is_valid_jsonschema(name):
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema.get("type") == "object"
    assert schema["$id"].startswith(f"wda:{VERTICAL[name]}/"), "세로 스키마는 vtpl 이름공간을 쓴다"
    assert schema.get("additionalProperties") is False


@pytest.mark.parametrize("name", VERTICAL)
def test_schema_has_x_read_and_maxlength(name):
    schema = load_schema(name)
    assert walk_has_x_read(schema), f"{name}: x-read 낭독 필드가 하나도 없다"
    missing = walk_strings_have_maxlength(schema)
    assert not missing, f"{name}: maxLength 누락 문자열 선언 — {missing}"


@pytest.mark.parametrize("name", VERTICAL)
def test_schema_documents_vertical_derivation(name):
    """maxLength 는 세로 폭 1080(본문 912) 실측 역산 — 근거가 스키마에 남아 있어야 한다."""
    schema = load_schema(name)
    assert "912" in json.dumps(schema, ensure_ascii=False), (
        f"{name}: 세로 본문 폭 912px 역산 근거가 description 에 없다"
    )
    assert all(v <= 40 for v in collect_maxlengths(schema)), (
        f"{name}: 세로 무대에 비해 과대한 maxLength — 가로 값 재사용 의심"
    )


@pytest.mark.parametrize("name", VERTICAL)
@pytest.mark.parametrize("fixture", FIXTURES)
def test_fixture_passes_schema(name, fixture):
    schema = load_schema(name)
    data = load_fixture(name, fixture)
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    msgs = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors]
    assert not msgs, f"{name}/{fixture}: {msgs}"


@pytest.mark.parametrize("name", VERTICAL)
def test_module_yaml_contract(name):
    doc = load_module(name)
    assert doc["id"] == VERTICAL[name]
    assert doc["type"] == "scene-template"
    assert doc["status"] == "draft"
    assert SEMVER.match(str(doc["version"]))
    assert doc["engine_compat"] == "animations-v2"
    assert doc["origin"] == ORIGIN
    assert doc["formats"] == [FORMAT_ID], "세로 템플릿은 formats: [short-9x16] 를 선언한다"
    assert doc["stage"] == STAGE
    assert isinstance(doc["nat_default"], (int, float)) and doc["nat_default"] > 0
    assert doc["in_scope"] and doc["out_of_scope"]
    assert doc["metaphors"] == ["v-frame", "v-dot-column"], "세로 크롬은 세로 전용 2종뿐"
    entry = doc["entry"]
    tpl_file = ROOT / entry["template"].split("#")[0]
    assert tpl_file == VERTICAL_FILE and tpl_file.exists()
    assert (TPL_DIR / name / entry["schema"]).exists()
    for fx in entry["fixtures"]:
        assert (TPL_DIR / name / fx).exists()
    assert (TPL_DIR / name / entry["preview"]).exists()
    assert (TPL_DIR / name / "fixtures" / "snapshots" / "typical.png").exists()


@pytest.mark.parametrize("name", VERTICAL)
def test_component_registered_in_jsx(name):
    src = VERTICAL_FILE.read_text(encoding="utf-8")
    assert f"'{VERTICAL[name]}'" in src, f"{VERTICAL[name]} 이 templateIndex 에 등록되지 않았다"
    comp = load_module(name)["entry"]["template"].split("#")[1]
    assert f"function {comp}(" in src and f"{comp}.nat" in src and f"{comp}.schedule" in src, (
        f"{comp}: .nat/.schedule 정적 계약 누락"
    )


def test_vertical_jsx_is_self_contained():
    """세로 크롬은 가로 은유(OMX.metaphors)를 재사용하지 않고 자체 구현한다."""
    src = VERTICAL_FILE.read_text(encoding="utf-8")
    assert "OMX.metaphors[" not in src, "가로 은유 재사용 — 세로 크롬은 신규 저작이어야 한다"
    assert "function VFrame(" in src and "function VDotColumn(" in src
    assert "OMX.vertical" in src and "'short-9x16'" in src
    # 무대 상수는 세로 값이어야 한다 (가로 1920×1080 전제 금지)
    assert "stage: { w: 1080, h: 1920 }" in src


@pytest.mark.parametrize("name", VERTICAL)
def test_preview_declares_vertical_stage(name):
    html = (TPL_DIR / name / "preview.html").read_text(encoding="utf-8")
    assert "width={1080} height={1920}" in html, f"{name}: 프리뷰 무대가 1080×1920 이 아니다"
    assert "omx-templates-vertical.jsx" in html
    for horiz in HORIZONTAL_FILES:
        assert horiz not in html, f"{name}: 프리뷰가 가로 자산({horiz})을 로드한다"
    assert f"templateIndex['{VERTICAL[name]}']" in html


def test_registry_indexes_vertical_modules():
    reg = yaml.safe_load((ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    ids = [m["id"] for m in reg["modules"]]
    assert len(ids) == len(set(ids)), "레지스트리 id 중복"
    for name, tid in VERTICAL.items():
        assert tid in ids
        entry = next(m for m in reg["modules"] if m["id"] == tid)
        assert entry["type"] == "scene-template"
        assert Path(entry["path"]) == Path("modules/scene-templates") / name
        assert entry["formats"] == [FORMAT_ID]
        assert entry["stage"] == STAGE
        mod = load_module(name)
        assert entry["nat_default"] == mod["nat_default"], f"{name}: nat_default 불일치"
        assert entry["status"] == mod["status"]
    order = reg["load_order_contract"]
    assert "web/templates/omx-templates-vertical.jsx" in order
    assert order.index("web/templates/omx-templates-vertical.jsx") < order.index("<project scenes.jsx>")


@pytest.mark.parametrize("name", VERTICAL)
def test_typical_fixture_fits_narration_budget(name):
    """x-read 글자수가 nat 안에 낭독 가능한지 — 포맷 rate 5.5자/초 기준."""
    from wdqa.gate2_length import collect_read_chars

    chars = collect_read_chars(load_schema(name), load_fixture(name, "typical"))
    nat = load_module(name)["nat_default"]
    assert chars > 0, f"{name}: typical 에 x-read 글자가 없다"
    need = chars / NARRATION_CPS
    assert need <= nat, f"{name}: x-read {chars}자 ÷ {NARRATION_CPS}자/초 = {need:.1f}s > nat {nat}s"


def test_format_declaration_matches_format_yaml():
    """formats/short-9x16/format.yaml 이 있으면 template_pool·stage 와 정합해야 한다 (없으면 skip)."""
    fmt_path = ROOT / "formats" / FORMAT_ID / "format.yaml"
    if not fmt_path.exists():
        pytest.skip("formats/short-9x16/format.yaml 미생성 — 포맷 정의 작업 완료 후 검증")
    fmt = yaml.safe_load(fmt_path.read_text(encoding="utf-8"))
    assert fmt["stage"] == STAGE
    pool_ids = {tid for ids in (fmt.get("template_pool") or {}).values() for tid in ids}
    ours = set(VERTICAL.values())
    unknown = {t for t in pool_ids if t.startswith("vtpl.")} - ours
    assert not unknown, f"format.yaml 이 없는 세로 템플릿을 참조한다 — {unknown}"
    nat_sum = sum(load_module(n)["nat_default"] for n in VERTICAL)
    assert nat_sum <= fmt["duration"]["max"], (
        f"세로 4종 nat 합 {nat_sum}s 가 포맷 최대 길이 {fmt['duration']['max']}s 를 넘는다"
    )
