# 오프닝 변주 3종(tpl.o-statement/o-metric/o-question)의 스키마·픽스처·module.yaml·병합 대기 레지스트리 정합
# + 각인 전략이 서로(그리고 기존 tpl.opening 과) 다른 데이터 구조인지, 자수 상한이 폰트 하한의 역산인지 검증
import json
import math
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
JSX_FILE = ROOT / "web" / "templates" / "omx-openings.jsx"
PENDING = ROOT / "modules" / "_pending" / "openings.registry.yaml"
FORMAT_ID = "wide-16x9"
STAGE = {"w": 1920, "h": 1080}
ORIGIN = "창작 모드 오프닝 변주 2026-07-29"
MODULES = {
    "o-statement": "tpl.o-statement",
    "o-metric": "tpl.o-metric",
    "o-question": "tpl.o-question",
}
FIXTURES = ["min", "typical", "max"]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
CAPTION_CPS = 9.0  # wdqa 게이트 2 자막 낭독 속도와 동일 기준

# 렌더 상수 (omx-openings.jsx 와 같은 값 — 자수 상한이 이 값들의 역산임을 증명한다)
ST_W = 1720
ST_CHAR_EM = 0.99
ST_MIN_SIZE = 96
ST_MAX_SIZE = 120


def load_schema(name: str) -> dict:
    return json.loads((TPL_DIR / name / "schema.json").read_text(encoding="utf-8"))


def load_fixture(name: str, fixture: str) -> dict:
    return json.loads(
        (TPL_DIR / name / "fixtures" / f"{fixture}.json").read_text(encoding="utf-8")
    )


def load_module(name: str) -> dict:
    return yaml.safe_load((TPL_DIR / name / "module.yaml").read_text(encoding="utf-8"))


def schema_errors(schema: dict, data) -> list[str]:
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    return [f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors]


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


def deep_keys(node, out=None) -> set:
    """스키마 전체에 등장하는 properties 키 이름 집합."""
    out = set() if out is None else out
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "properties" and isinstance(v, dict):
                out |= set(v)
            deep_keys(v, out)
    elif isinstance(node, list):
        for v in node:
            deep_keys(v, out)
    return out


def st_fit_size(max_chars: int) -> int:
    """클램프 전 '자수에 맞는 폭' — 자수 상한이 96px 하한의 역산임을 보이는 데 쓴다."""
    return math.floor(ST_W / (max_chars * ST_CHAR_EM))


def st_font_size(lines: list[dict]) -> int:
    """omx-openings.jsx stGeo 의 폰트 산식 미러 — 테스트가 렌더와 같은 식을 쓴다."""
    max_chars = max(len(ln["text"]) for ln in lines)
    return max(ST_MIN_SIZE, min(ST_MAX_SIZE, st_fit_size(max_chars)))


# ── 기본 계약 ────────────────────────────────────────────────────────────


def test_modules_present():
    for name in MODULES:
        assert (TPL_DIR / name).is_dir(), f"{name} 모듈 디렉터리가 없다"
    assert JSX_FILE.exists()
    assert PENDING.exists(), "registry.yaml 병합 대기 조각이 없다 (소유권 규칙상 직접 수정 금지)"


@pytest.mark.parametrize("name", MODULES)
def test_schema_is_valid_jsonschema(name):
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema.get("type") == "object"
    assert schema["$id"].startswith(f"wda:{MODULES[name]}/")
    assert schema.get("additionalProperties") is False


@pytest.mark.parametrize("name", MODULES)
def test_schema_has_x_read_and_maxlength(name):
    schema = load_schema(name)
    assert walk_has_x_read(schema), f"{name}: x-read 낭독 필드가 하나도 없다"
    missing = walk_strings_have_maxlength(schema)
    assert not missing, f"{name}: maxLength 누락 문자열 선언 — {missing}"


@pytest.mark.parametrize("name", MODULES)
@pytest.mark.parametrize("fixture", FIXTURES)
def test_fixture_passes_schema(name, fixture):
    msgs = schema_errors(load_schema(name), load_fixture(name, fixture))
    assert not msgs, f"{name}/{fixture}: {msgs}"


@pytest.mark.parametrize("name", MODULES)
def test_module_yaml_contract(name):
    doc = load_module(name)
    assert doc["id"] == MODULES[name]
    assert doc["type"] == "scene-template"
    assert doc["status"] == "draft"
    assert SEMVER.match(str(doc["version"]))
    assert doc["engine_compat"] == "animations-v2"
    assert doc["origin"] == ORIGIN
    assert doc["formats"] == [FORMAT_ID]
    assert doc["stage"] == STAGE
    assert isinstance(doc["nat_default"], (int, float)) and doc["nat_default"] > 0
    assert doc["scene_name_default"] == "오프닝"
    assert doc["in_scope"] and doc["out_of_scope"]
    assert doc["imprint_strategy"], "각인 전략 선언이 없다 — 이 라운드의 존재 이유"
    assert doc["metaphors"] == ["frame-chrome", "dot-grid"], "허용 은유는 공통 크롬 2종뿐"
    entry = doc["entry"]
    tpl_file = ROOT / entry["template"].split("#")[0]
    assert tpl_file == JSX_FILE and tpl_file.exists()
    assert (TPL_DIR / name / entry["schema"]).exists()
    for fx in entry["fixtures"]:
        assert (TPL_DIR / name / fx).exists()
    assert (TPL_DIR / name / entry["preview"]).exists()


@pytest.mark.parametrize("name", MODULES)
def test_component_registered_in_jsx(name):
    src = JSX_FILE.read_text(encoding="utf-8")
    assert f"'{MODULES[name]}'" in src, f"{MODULES[name]} 이 templateIndex 에 등록되지 않았다"
    comp = load_module(name)["entry"]["template"].split("#")[1]
    assert f"function {comp}(" in src and f"{comp}.nat" in src and f"{comp}.schedule" in src, (
        f"{comp}: .nat/.schedule 정적 계약 누락"
    )


@pytest.mark.parametrize("name", MODULES)
def test_preview_contract(name):
    html = (TPL_DIR / name / "preview.html").read_text(encoding="utf-8")
    assert "width={1920} height={1080}" in html, f"{name}: 프리뷰 무대가 1920×1080 이 아니다"
    assert "omx-openings.jsx" in html, f"{name}: 프리뷰 로드 순서에 자기 jsx 가 없다"
    assert f"templateIndex['{MODULES[name]}']" in html


def test_jsx_has_no_nondeterministic_identifiers():
    """카운트업·점등 모두 localTime 순수 함수 — 시각/난수/타이머 식별자가 소스에 없다."""
    from wdqa.entry import strip_js_comments

    src = strip_js_comments(JSX_FILE.read_text(encoding="utf-8"))
    banned = re.compile(
        r"\b(Date\s*\.\s*now|Math\s*\.\s*random|setTimeout|setInterval"
        r"|requestAnimationFrame|useEffect)\b"
    )
    hits = [m.group(0) for m in banned.finditer(src)]
    assert not hits, f"결정성 파괴 식별자 — {hits}"


def test_pending_registry_fragment():
    """registry.yaml 은 병렬 작업자 소유 — 조각이 병합에 필요한 값을 전부 들고 있어야 한다."""
    frag = yaml.safe_load(PENDING.read_text(encoding="utf-8"))
    order = frag["merge"]["load_order_contract"]
    assert order["entries"] == ["web/templates/omx-openings.jsx"]
    assert order["insert_before"] == "<project scenes.jsx>"
    hint = frag["merge"]["format_pool_hint"]
    assert hint["format"] == FORMAT_ID and hint["role"] == "opening"
    assert sorted(hint["add"]) == sorted(MODULES.values())
    ids = [m["id"] for m in frag["modules"]]
    assert sorted(ids) == sorted(MODULES.values())
    for name, tid in MODULES.items():
        entry = next(m for m in frag["modules"] if m["id"] == tid)
        mod = load_module(name)
        assert entry["type"] == "scene-template"
        assert Path(entry["path"]) == Path("modules/scene-templates") / name
        assert entry["formats"] == [FORMAT_ID]
        assert entry["stage"] == STAGE
        assert entry["nat_default"] == mod["nat_default"], f"{name}: nat_default 불일치"
        assert entry["status"] == mod["status"]
        assert entry["summary"] == mod["summary"]


def test_registry_merge_is_consistent_when_already_merged():
    """오케스트레이터가 조각을 합친 뒤에도 이 테스트가 계약을 지킨다 (병합 전에는 no-op)."""
    reg = yaml.safe_load((ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    ids = [m["id"] for m in reg["modules"]]
    assert len(ids) == len(set(ids)), "레지스트리 id 중복"
    merged = [tid for tid in MODULES.values() if tid in ids]
    if not merged:
        pytest.skip("아직 registry.yaml 에 병합되지 않았다 — modules/_pending 조각이 정본")
    order = reg["load_order_contract"]
    assert "web/templates/omx-openings.jsx" in order, "병합됐는데 로드 순서에 jsx 가 없다"
    assert order.index("web/templates/omx-openings.jsx") < order.index("<project scenes.jsx>")
    for name, tid in MODULES.items():
        entry = next(m for m in reg["modules"] if m["id"] == tid)
        assert entry["nat_default"] == load_module(name)["nat_default"]


# ── 각인 전략이 실제로 다른가 — 데이터 구조 층위 ─────────────────────────


def test_three_openings_take_disjoint_required_fields():
    """세 오프닝은 필수 입력이 서로 겹치지 않는다 — 같은 그릇의 변형이 아니라는 증거."""
    required = {name: set(load_schema(name)["required"]) for name in MODULES}
    assert required["o-statement"] == {"lines"}
    assert required["o-metric"] == {"value", "meaning", "title"}
    assert required["o-question"] == {"question", "promise", "topics"}
    names = list(MODULES)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            common = required[names[i]] & required[names[j]]
            assert not common, f"{names[i]}·{names[j]} 필수 필드가 겹친다 — {common}"


def test_no_opening_reuses_badge_or_dot_decoration():
    """기존 tpl.opening 의 각인 장치(배지·도트 라인·pre/accent/post 타이틀)를 복제하지 않았다."""
    legacy = set(load_schema("opening")["properties"])
    assert {"badge", "dotCount"} <= legacy, "전제가 변했다 — tpl.opening 스키마 확인 필요"
    for name in MODULES:
        keys = deep_keys(load_schema(name))
        assert "badge" not in keys, f"{name}: 배지를 다시 들여왔다"
        assert "dotCount" not in keys, f"{name}: 도트 장식을 다시 들여왔다"
        assert not {"pre", "post"} & keys, f"{name}: tpl.opening 의 pre/accent/post 타이틀 복제"


def test_statement_line_cap_is_the_96px_floor_inverse():
    """행 18자 상한은 '폰트를 줄이지 않기 위한' 역산 — 상한 자수에서 정확히 96px 이 나온다."""
    schema = load_schema("o-statement")
    line = schema["properties"]["lines"]["items"]["properties"]
    assert schema["properties"]["lines"]["minItems"] == 2
    assert schema["properties"]["lines"]["maxItems"] == 3
    assert line["text"]["maxLength"] == 18
    assert st_fit_size(18) == ST_MIN_SIZE, "18자에 맞는 폭이 96px 이 아니다"
    assert st_fit_size(19) < ST_MIN_SIZE, "19자를 허용하면 폭이 96px 아래로 내려간다"
    assert st_font_size([{"text": "가" * 18}]) == ST_MIN_SIZE
    assert st_font_size([{"text": "가" * 8}]) == ST_MAX_SIZE, "짧은 문장은 상한 120px"
    # 4행은 거부 — 문장 하나가 화면을 채우는 템플릿이지 목록이 아니다
    four = json.loads(json.dumps(load_fixture("o-statement", "max")))
    four["lines"] = four["lines"] + [four["lines"][0]]
    assert schema_errors(schema, four), "4행이 통과되면 안 된다"
    # 행 19자는 거부
    over = json.loads(json.dumps(load_fixture("o-statement", "min")))
    over["lines"][0]["text"] = "가" * 19
    assert schema_errors(schema, over), "19자 행이 통과되면 안 된다"


def test_statement_fixtures_exercise_the_full_font_band():
    """min/typical/max 가 120·108·96px 을 각각 짚는다 — 자수 기반 폰트 결정이 죽은 코드가 아니라는 증거."""
    sizes = {fx: st_font_size(load_fixture("o-statement", fx)["lines"]) for fx in FIXTURES}
    assert sizes == {"min": 120, "typical": 108, "max": 96}, sizes


def test_statement_accent_is_a_substring_of_its_line():
    """accent 는 text 안의 부분 문자열이어야 실제로 강조된다 (렌더는 indexOf 로 찾는다)."""
    for fixture in FIXTURES:
        for i, line in enumerate(load_fixture("o-statement", fixture)["lines"]):
            acc = line.get("accent")
            if acc:
                assert acc in line["text"], f"o-statement/{fixture} 행{i}: accent 가 text 에 없다"


def test_metric_bounds_keep_the_220px_number_inside_the_stage():
    """수치 상한(6자리·소수 1·단위 3자)은 220px 수치가 1720px 안에 남는다는 역산."""
    schema = load_schema("o-metric")
    props = schema["properties"]
    assert props["value"]["maximum"] == 999999 and props["value"]["minimum"] == 0
    assert props["decimals"]["maximum"] == 1
    assert props["suffix"]["maxLength"] == 3

    def width_px(value: float, decimals: int, suffix: str) -> float:
        """omx-openings.jsx mtWidthEm 의 미러 (0.05em 은 글리프 잉크 오버행 여유)."""
        text = f"{value:,.{decimals}f}"
        em = 0.05 + sum(0.3 if c in ",." else 0.6 for c in text)
        if suffix:
            em += len(suffix) * 0.5 + 12 / 220
        return em * 220

    worst = width_px(999999, 1, "가나다")
    assert worst <= ST_W, f"최악 수치 폭 {worst:.0f}px 이 {ST_W}px 을 넘는다"
    # 상한을 넘는 입력은 스키마가 거른다
    over = json.loads(json.dumps(load_fixture("o-metric", "max")))
    over["value"] = 1000000
    assert schema_errors(schema, over), "1,000,000 이 통과되면 안 된다"
    over2 = json.loads(json.dumps(load_fixture("o-metric", "max")))
    over2["decimals"] = 2
    assert schema_errors(schema, over2), "소수 2자리가 통과되면 안 된다"


def test_question_requires_exactly_three_topics():
    """항목 3개 고정 — 2개는 예고가 되지 않고, 4개 이상은 예고가 아니라 목차다(tpl.c-grid 영역)."""
    schema = load_schema("o-question")
    topics = schema["properties"]["topics"]
    assert topics["minItems"] == 3 and topics["maxItems"] == 3
    assert topics["items"]["maxLength"] == 10
    # 칩 3개 행은 최악 자수에서도 무대를 채우지 않는다 (여백이 계층 — UI 원칙 7항)
    chip_row = (10 * 34 + 68) * 3 + 24 * 2
    assert chip_row <= ST_W * 0.8, f"칩 3개 행 폭 {chip_row}px 이 무대를 가득 채운다"
    for n in (2, 4):
        bad = json.loads(json.dumps(load_fixture("o-question", "typical")))
        bad["topics"] = (bad["topics"] * 2)[:n]
        assert schema_errors(schema, bad), f"항목 {n}개가 통과되면 안 된다"
    # 질문 3행도 거부 — 상단 질문은 1~2행
    three = json.loads(json.dumps(load_fixture("o-question", "max")))
    three["question"] = three["question"] + [three["question"][0]]
    assert schema_errors(schema, three), "질문 3행이 통과되면 안 된다"


def test_no_layout_fields_in_any_opening_schema():
    """배치·크기는 렌더가 정한다 — 스키마에 폰트·좌표 필드가 있으면 밀도 왜곡 경로가 열린다."""
    forbidden = {"fontSize", "font_size", "cols", "rows", "top", "left", "width", "height",
                 "align", "layout", "density", "scale", "color"}
    for name in MODULES:
        keys = deep_keys(load_schema(name))
        assert not (keys & forbidden), f"{name}: 배치 지정 필드 — {sorted(keys & forbidden)}"


# ── 게이트 2 예산 — typical 픽스처의 x-read 글자수가 nat 안에 낭독 가능한지 ──


@pytest.mark.parametrize("name", MODULES)
def test_typical_fixture_fits_caption_budget(name):
    from wdqa.gate2_length import collect_read_chars

    schema = load_schema(name)
    data = load_fixture(name, "typical")
    chars = collect_read_chars(schema, data)
    nat = load_module(name)["nat_default"]
    assert chars > 0, f"{name}: typical 에 x-read 글자가 없다"
    need = chars / CAPTION_CPS
    assert need <= nat, f"{name}: x-read {chars}자 ÷ {CAPTION_CPS}자/초 = {need:.1f}s > nat {nat}s"


@pytest.mark.parametrize("name", MODULES)
def test_max_fixture_also_fits_caption_budget(name):
    """최악 자수에서도 nat 안에 읽힌다 — 상한을 채운 카피가 곧바로 게이트 2 실패가 되지 않게."""
    from wdqa.gate2_length import collect_read_chars

    chars = collect_read_chars(load_schema(name), load_fixture(name, "max"))
    nat = load_module(name)["nat_default"]
    need = chars / CAPTION_CPS
    assert need <= nat, f"{name}/max: {chars}자 ÷ {CAPTION_CPS} = {need:.1f}s > nat {nat}s"
