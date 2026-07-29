# 수치 표현 템플릿 2종(tpl.c-ratio/c-trend)의 스키마·픽스처·module.yaml·대기 레지스트리 조각 정합 + 수치 왜곡 방지 선언 검증
import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
LAYOUTS_C = ROOT / "web" / "templates" / "omx-layouts-c.jsx"
PENDING = ROOT / "modules" / "_pending" / "layouts-c.registry.yaml"
FORMAT_ID = "wide-16x9"
STAGE = {"w": 1920, "h": 1080}
ORIGIN = "창작 모드 커버리지 1순위 2026-07-29"
# 디렉터리 → 템플릿 id
LAYOUTS = {"c-ratio": "tpl.c-ratio", "c-trend": "tpl.c-trend"}
FIXTURES = ["min", "typical", "max"]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
CAPTION_CPS = 9.0   # wdqa.config.QAConfig.caption_cps — x-read 는 자막 속도로 환산한다

# 비율 씬에서 "저작하면 왜곡이 되는" 금지 필드 — 스키마 어디에도 있으면 안 된다
RATIO_BANNED_KEYS = {
    "percent", "percentage", "share", "ratio", "angle", "startAngle", "endAngle",
    "rotate", "rotation", "tilt", "depth", "explode",
}


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
        if node.get("type") == "string" and "maxLength" not in node and "enum" not in node:
            missing.append(path)
        for k, v in node.items():
            if k in ("enum", "const"):
                continue
            missing += walk_strings_have_maxlength(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            missing += walk_strings_have_maxlength(v, f"{path}/{i}")
    return missing


def collect_property_names(node, out=None) -> set:
    out = set() if out is None else out
    if isinstance(node, dict):
        for k in (node.get("properties") or {}):
            out.add(k)
        for v in node.values():
            collect_property_names(v, out)
    elif isinstance(node, list):
        for v in node:
            collect_property_names(v, out)
    return out


def test_modules_and_jsx_present():
    for name in LAYOUTS:
        assert (TPL_DIR / name).is_dir(), f"{name} 모듈 디렉터리가 없다"
    assert LAYOUTS_C.exists()


@pytest.mark.parametrize("name", LAYOUTS)
def test_schema_is_valid_jsonschema(name):
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema.get("type") == "object"
    assert schema["$id"].startswith(f"wda:{LAYOUTS[name]}/")
    assert schema.get("additionalProperties") is False


@pytest.mark.parametrize("name", LAYOUTS)
def test_schema_has_x_read_and_maxlength(name):
    schema = load_schema(name)
    assert walk_has_x_read(schema), f"{name}: x-read 낭독 필드가 하나도 없다"
    missing = walk_strings_have_maxlength(schema)
    assert not missing, f"{name}: maxLength 누락 문자열 선언 — {missing}"


@pytest.mark.parametrize("name", LAYOUTS)
def test_schema_documents_measured_derivation(name):
    """maxLength 는 1920×1080 실측 역산 — 근거가 description 에 남아 있어야 한다."""
    blob = json.dumps(load_schema(name), ensure_ascii=False)
    assert "실측 역산" in blob, f"{name}: maxLength 역산 근거가 description 에 없다"
    assert blob.count("실측 역산") >= 5, f"{name}: 역산 근거가 {blob.count('실측 역산')}건뿐"


@pytest.mark.parametrize("name", LAYOUTS)
@pytest.mark.parametrize("fixture", FIXTURES)
def test_fixture_passes_schema(name, fixture):
    schema = load_schema(name)
    data = load_fixture(name, fixture)
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    msgs = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors]
    assert not msgs, f"{name}/{fixture}: {msgs}"


# ── 수치 왜곡 방지 — 스키마 구조 검증 ────────────────────────────────────

def test_ratio_schema_forbids_authored_percentages():
    """비율은 value/Σvalue 파생만 허용 — 백분율·각도·3D 필드를 저작할 수 없어야 한다."""
    schema = load_schema("c-ratio")
    names = collect_property_names(schema)
    leaked = names & RATIO_BANNED_KEYS
    assert not leaked, f"c-ratio: 저작 가능한 왜곡 필드가 열려 있다 — {sorted(leaked)}"
    item = schema["properties"]["series"]["items"]
    assert item["additionalProperties"] is False
    assert item["properties"]["value"]["minimum"] == 0, "음수 조각을 막는 minimum:0 이 없다"
    assert schema["properties"]["series"]["minItems"] == 4
    assert schema["properties"]["series"]["maxItems"] == 7
    desc = schema["description"]
    for token in ("360", "value/Σvalue", "minimum:0", "5%"):
        assert token in desc, f"c-ratio: 왜곡 방지 설명에 {token!r} 근거가 없다"


@pytest.mark.parametrize("fixture", FIXTURES)
def test_ratio_fixture_sum_is_consistent(fixture):
    """지분 합 검증 — 파생 백분율 합은 항상 100(±0.5), total 선언 시 잔량은 음수가 될 수 없다."""
    data = load_fixture("c-ratio", fixture)
    values = [float(s["value"]) for s in data["series"]]
    assert all(v >= 0 for v in values), "음수 값"
    declared = (data.get("total") or {}).get("value")
    total = float(declared) if declared is not None else sum(values)
    # 렌더러 계산과 동일: 명시 합이 total 보다 작으면 '기타(미표기)' 로 자동 편입
    gap = total - sum(values)
    assert gap >= -0.005 * total, (
        f"c-ratio/{fixture}: 명시 합 {sum(values)} 이 선언 전체 {total} 를 0.5% 넘게 초과"
    )
    denom = total if gap > 0 else sum(values)
    shares = [v / denom * 100 for v in values] + ([gap / denom * 100] if gap > 0 else [])
    assert abs(sum(shares) - 100.0) <= 0.5, (
        f"c-ratio/{fixture}: 파생 지분 합 {sum(shares)} 이 100±0.5 를 벗어났다"
    )


def test_trend_schema_enforces_zero_baseline_and_polarity_split():
    """추세는 y 하한 기본 0 · 값 음수 금지 · 방향과 평가색 분리를 스키마로 못박는다."""
    schema = load_schema("c-trend")
    axis = schema["properties"]["axis"]
    assert axis["additionalProperties"] is False
    assert axis["properties"]["min"]["default"] == 0
    assert axis["properties"]["min"]["minimum"] == 0
    assert "축 절단" in axis["properties"]["min"]["description"]
    assert "승격" in axis["properties"]["max"]["description"], "max 승격(라인 절단 금지) 근거 누락"
    values = schema["properties"]["lines"]["items"]["properties"]["values"]
    assert values["items"]["minimum"] == 0, "0 기준선 아래 값을 막는 minimum:0 이 없다"
    delta = schema["properties"]["readout"]["properties"]["delta"]["properties"]
    assert set(delta["direction"]["enum"]) == {"up", "down", "flat"}
    assert set(delta["polarity"]["enum"]) == {"good", "bad", "neutral"}
    assert "direction" in schema["properties"]["readout"]["properties"]["delta"]["required"]
    assert "polarity" not in schema["properties"]["readout"]["properties"]["delta"]["required"], (
        "평가색은 선택 — 방향만으로 좋고 나쁨을 단정하지 않는다"
    )
    for token in ("0 기준선", "축 절단", "값 비례", "y = plotH"):
        assert token in schema["description"], f"c-trend: 왜곡 방지 설명에 {token!r} 근거가 없다"


@pytest.mark.parametrize("fixture", FIXTURES)
def test_trend_fixture_series_align_with_points(fixture):
    """계열 값 개수는 시점 개수를 넘지 않는다 (없는 값을 지어내는 그림 방지)."""
    data = load_fixture("c-trend", fixture)
    n = len(data["points"])
    for i, ln in enumerate(data["lines"]):
        assert len(ln["values"]) <= n, f"c-trend/{fixture}: lines[{i}] 값이 시점보다 많다"
        assert len(ln["values"]) >= 2
        lo = (data.get("axis") or {}).get("min", 0)
        assert all(v >= lo for v in ln["values"]), (
            f"c-trend/{fixture}: lines[{i}] 에 축 하한 {lo} 미만 값이 있다 — 잘려 그려진다"
        )


def test_trend_max_fixture_exercises_axis_truncation():
    """축 절단 표기 경로가 픽스처로 실제 렌더되는지 — max 가 그 케이스를 잡는다."""
    data = load_fixture("c-trend", "max")
    assert (data.get("axis") or {}).get("min", 0) != 0, "축 절단 케이스를 어떤 픽스처도 덮지 않는다"


def test_ratio_min_fixture_exercises_waffle():
    assert load_fixture("c-ratio", "min").get("style") == "waffle", "와플 경로를 픽스처가 덮지 않는다"


# ── module.yaml · jsx · 프리뷰 · 대기 레지스트리 조각 ────────────────────

@pytest.mark.parametrize("name", LAYOUTS)
def test_module_yaml_contract(name):
    doc = load_module(name)
    assert doc["id"] == LAYOUTS[name]
    assert doc["type"] == "scene-template"
    assert doc["status"] == "draft"
    assert SEMVER.match(str(doc["version"]))
    assert doc["engine_compat"] == "animations-v2"
    assert doc["origin"] == ORIGIN
    assert doc["formats"] == [FORMAT_ID]
    assert doc["stage"] == STAGE
    assert isinstance(doc["nat_default"], (int, float)) and doc["nat_default"] > 0
    assert doc["in_scope"] and doc["out_of_scope"]
    assert doc["distortion_guards"], "왜곡 방지 근거가 module.yaml 에 없다"
    assert doc["widget_intake"]["payload_kind"] == "series"
    entry = doc["entry"]
    tpl_file = ROOT / entry["template"].split("#")[0]
    assert tpl_file == LAYOUTS_C and tpl_file.exists()
    assert (TPL_DIR / name / entry["schema"]).exists()
    for fx in entry["fixtures"]:
        assert (TPL_DIR / name / fx).exists()
    assert (TPL_DIR / name / entry["preview"]).exists()
    assert (TPL_DIR / name / "fixtures" / "snapshots" / "typical.png").exists()


@pytest.mark.parametrize("name", LAYOUTS)
def test_component_registered_in_jsx(name):
    src = LAYOUTS_C.read_text(encoding="utf-8")
    assert f"'{LAYOUTS[name]}'" in src, f"{LAYOUTS[name]} 이 templateIndex 에 등록되지 않았다"
    comp = load_module(name)["entry"]["template"].split("#")[1]
    assert f"function {comp}(" in src and f"{comp}.nat" in src and f"{comp}.schedule" in src, (
        f"{comp}: .nat/.schedule 정적 계약 누락"
    )


def test_jsx_uses_engine_atoms_and_tokens_only():
    """엔진 원자·토큰만 소비하고 결정성 파괴 식별자를 쓰지 않는다 (게이트 6 정적 규칙 미러)."""
    src = LAYOUTS_C.read_text(encoding="utf-8")
    banned = re.compile(r"\b(Date\s*\.\s*now|Math\s*\.\s*random|setTimeout|setInterval"
                        r"|requestAnimationFrame|useEffect)\b")
    assert not banned.search(src), "결정성 파괴 식별자 검출"
    assert "OMX.metaphors['frame-chrome']" in src
    # 색 하드코딩 금지 — '#' 리터럴은 rgb2hex 조립 한 곳(토큰 색 보간)만 허용
    hexes = re.findall(r"'#[0-9A-Fa-f]{3,8}'", src)
    assert not hexes, f"hex 하드코딩 검출 — {hexes}"


@pytest.mark.parametrize("name", LAYOUTS)
def test_preview_declares_wide_stage_and_load_order(name):
    html = (TPL_DIR / name / "preview.html").read_text(encoding="utf-8")
    assert "width={1920} height={1080}" in html, f"{name}: 프리뷰 무대가 1920×1080 이 아니다"
    assert f"templateIndex['{LAYOUTS[name]}']" in html
    order = ["animations-v2.jsx", "loader.jsx", "omx-metaphors.jsx",
             "omx-templates.jsx", "omx-layouts-c.jsx"]
    idx = [html.index(f) for f in order]
    assert idx == sorted(idx), f"{name}: 프리뷰 로드 순서 위반 — {order}"
    assert "?fixture=" in html or "fixture=" in html


def test_pending_registry_fragment_declares_both_modules():
    """registry.yaml 직접 수정 금지 — 대기 조각이 두 모듈과 로드 순서를 선언한다."""
    frag = yaml.safe_load(PENDING.read_text(encoding="utf-8"))
    ids = [m["id"] for m in frag["modules"]]
    assert set(ids) == set(LAYOUTS.values()), ids
    for m in frag["modules"]:
        name = Path(m["path"]).name
        mod = load_module(name)
        assert m["type"] == "scene-template"
        assert Path(m["path"]) == Path("modules/scene-templates") / name
        assert m["formats"] == [FORMAT_ID] and m["stage"] == STAGE
        assert m["nat_default"] == mod["nat_default"], f"{name}: nat_default 불일치"
        assert m["status"] == mod["status"]
    ins = frag["load_order_contract_insert"]
    assert any(x["file"] == "web/templates/omx-layouts-c.jsx" for x in ins)


def test_registry_yaml_untouched_by_this_agent():
    """소유 규칙 확인 — 본 에이전트는 registry.yaml 에 c-* 항목을 직접 넣지 않는다."""
    reg = yaml.safe_load((ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    ids = {m["id"] for m in reg["modules"]}
    if ids & set(LAYOUTS.values()):
        # 오케스트레이터가 이미 병합했다면 정합성만 확인한다
        for name, tid in LAYOUTS.items():
            entry = next(m for m in reg["modules"] if m["id"] == tid)
            assert Path(entry["path"]) == Path("modules/scene-templates") / name
            assert "web/templates/omx-layouts-c.jsx" in reg["load_order_contract"]


@pytest.mark.parametrize("name", LAYOUTS)
def test_typical_fixture_fits_caption_budget(name):
    """x-read 글자수가 nat 안에 자막으로 흐를 수 있는지 — 게이트 2 계산과 동일(9자/초)."""
    from wdqa.gate2_length import collect_read_chars

    chars = collect_read_chars(load_schema(name), load_fixture(name, "typical"))
    nat = load_module(name)["nat_default"]
    assert chars > 0, f"{name}: typical 에 x-read 글자가 없다"
    need = chars / CAPTION_CPS
    assert need <= nat, f"{name}: x-read {chars}자 ÷ {CAPTION_CPS}자/초 = {need:.1f}s > nat {nat}s"
