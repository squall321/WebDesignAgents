# 클로징 변주 3종(tpl.x-summary/x-quote/x-next)의 스키마·픽스처·module.yaml·병합 대기 레지스트리 정합
# + 마무리 전략이 tpl.closing 과 실제로 갈리는지(퇴장 없음·when/owner 필수·display 스케일) 계약 검증
import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
JSX_FILE = ROOT / "web" / "templates" / "omx-closings.jsx"
PENDING = ROOT / "modules" / "_pending" / "closings.registry.yaml"
FORMAT_ID = "wide-16x9"
STAGE = {"w": 1920, "h": 1080}
ORIGIN = "창작 모드 클로징 변주 2026-07-29"
MODULES = {"x-summary": "tpl.x-summary", "x-quote": "tpl.x-quote", "x-next": "tpl.x-next"}
FIXTURES = ["min", "typical", "max"]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
CAPTION_CPS = 9.0  # wdqa 게이트 2 자막 낭독 속도와 동일 기준


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


def test_modules_present():
    for name in MODULES:
        assert (TPL_DIR / name).is_dir(), f"{name} 모듈 디렉터리가 없다"
    assert JSX_FILE.exists()
    assert (ROOT / "modules" / "registry.yaml").is_file()  # 병합 완료 — _pending 조각은 제거됐다


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
    assert doc["in_scope"] and doc["out_of_scope"]
    assert doc["closing_strategy"], f"{name}: 마무리 전략 선언이 없다 (tpl.closing 과의 차이 기술)"
    assert doc["metaphors"] == ["frame-chrome", "dot-grid"], "허용 은유는 공통 크롬 2종뿐"
    entry = doc["entry"]
    tpl_file = ROOT / entry["template"].split("#")[0]
    assert tpl_file == JSX_FILE and tpl_file.exists()
    assert (TPL_DIR / name / entry["schema"]).exists()
    for fx in entry["fixtures"]:
        assert (TPL_DIR / name / fx).exists()
    assert (TPL_DIR / name / entry["preview"]).exists()
    assert (TPL_DIR / name / "fixtures" / "snapshots" / "typical.png").exists()


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
    assert "omx-closings.jsx" in html, f"{name}: 프리뷰 로드 순서에 자기 jsx 가 없다"
    assert f"templateIndex['{MODULES[name]}']" in html


def test_pending_registry_fragment():
    """병합 완료 검증 — 이 모듈들이 registry.yaml 에 실제로 등재됐는가.

    (과거에는 modules/_pending 조각 존재를 봤으나, 오케스트레이터 병합이
     끝나 조각은 제거됐다. 정본은 registry.yaml 이다.)
    """
    reg = yaml.safe_load((ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    ids = {m["id"] for m in reg["modules"]}
    for name in MODULES:
        assert f"tpl.{name}" in ids, f"tpl.{name} 이 registry.yaml 에 없다"
    contract = reg["load_order_contract"]
    assert any(JSX_FILE.name in str(x) for x in contract), (
        f"{JSX_FILE.name} 이 load_order_contract 에 없다")

def test_registry_merge_is_consistent_when_already_merged():
    """오케스트레이터가 조각을 합친 뒤에도 이 테스트가 계약을 지킨다 (병합 전에는 no-op)."""
    reg = yaml.safe_load((ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    ids = [m["id"] for m in reg["modules"]]
    assert len(ids) == len(set(ids)), "레지스트리 id 중복"
    merged = [tid for tid in MODULES.values() if tid in ids]
    if not merged:
        pytest.skip("아직 registry.yaml 에 병합되지 않았다 — modules/_pending 조각이 정본")
    order = reg["load_order_contract"]
    assert "web/templates/omx-closings.jsx" in order, "병합됐는데 로드 순서에 jsx 가 없다"
    assert order.index("web/templates/omx-closings.jsx") < order.index("<project scenes.jsx>")
    for name, tid in MODULES.items():
        entry = next(m for m in reg["modules"] if m["id"] == tid)
        assert entry["nat_default"] == load_module(name)["nat_default"]


# ── 마무리 전략이 실제로 갈리는가 — tpl.closing 과의 대조 ──────────────────


def test_closings_declare_no_exit_in_source():
    """3종 모두 schedule 에 kind:'exit' 을 만들지 않는다.

    tpl.closing 은 stats-exit(통계 트리오 퇴장)을 갖는다 — 마지막에 남는 게 슬로건이라 가능한
    연출이다. 변주 3종은 마지막 상태가 곧 내용이므로 퇴장을 소스 차원에서 배제한다.
    """
    src = JSX_FILE.read_text(encoding="utf-8")
    assert "'exit'" not in src and '"exit"' not in src, (
        "omx-closings.jsx 에 exit 이벤트 선언이 있다 — 마지막 프레임 안정성 규율 위반"
    )
    base = (ROOT / "web" / "templates" / "omx-templates.jsx").read_text(encoding="utf-8")
    assert "kind: 'exit'" in base, "대조군 전제가 변했다 — tpl.closing 의 stats-exit 이 사라졌다"


def test_x_next_requires_when_and_owner():
    """다음 단계 카드는 시점·담당이 필수 — 주체 없는 권유(tpl.closing 의 CTA)와 갈리는 지점."""
    schema = load_schema("x-next")
    item = schema["properties"]["steps"]["items"]
    assert sorted(item["required"]) == ["owner", "what", "when"]
    assert schema["properties"]["steps"]["minItems"] == 3
    assert schema["properties"]["steps"]["maxItems"] == 4
    # 담당 없는 카드는 거부 — CTA 필로 둔갑하는 경로 차단
    bad = json.loads(json.dumps(load_fixture("x-next", "typical")))
    bad["steps"][0].pop("owner")
    assert schema_errors(schema, bad), "owner 없는 단계가 통과되면 안 된다"
    bad2 = json.loads(json.dumps(load_fixture("x-next", "typical")))
    bad2["steps"][1].pop("when")
    assert schema_errors(schema, bad2), "when 없는 단계가 통과되면 안 된다"
    # 5건은 거부 — 마무리가 아니라 일정표
    over = json.loads(json.dumps(load_fixture("x-next", "typical")))
    over["steps"] = over["steps"] + [over["steps"][0]]
    assert schema_errors(schema, over), "단계 5건이 통과되면 안 된다"


def test_x_summary_requires_metric_per_line():
    """회수 줄마다 근거 수치가 붙는다 — 주장만 되짚는 슬로건형(tpl.x-quote)과 갈리는 지점."""
    schema = load_schema("x-summary")
    item = schema["properties"]["points"]["items"]
    assert sorted(item["required"]) == ["metric", "text"]
    assert schema["properties"]["points"]["minItems"] == 3
    assert schema["properties"]["points"]["maxItems"] == 5
    assert schema["properties"]["standby"]["minLength"] == 1, "질의응답 대기 문구는 필수"
    assert "standby" in schema["required"]
    no_metric = json.loads(json.dumps(load_fixture("x-summary", "typical")))
    no_metric["points"][0].pop("metric")
    assert schema_errors(schema, no_metric), "metric 없는 회수 줄이 통과되면 안 된다"
    over = json.loads(json.dumps(load_fixture("x-summary", "max")))
    over["points"] = over["points"] + [over["points"][0]]
    assert schema_errors(schema, over), "6줄이 통과되면 안 된다 (요약이 아니라 본문)"


def test_schemas_have_no_layout_or_scale_fields():
    """배치·크기는 렌더가 정한다 — 스키마에 크기 필드가 있으면 밀도 왜곡 경로가 열린다."""
    forbidden = {"cols", "rows", "columns", "fontSize", "font_size", "size", "scale",
                 "cardWidth", "cardHeight", "layout", "density", "top", "left", "width", "height"}
    for name in MODULES:
        keys = deep_keys(load_schema(name))
        hit = keys & forbidden
        assert not hit, f"{name}: 배치/크기 지정 필드가 스키마에 있다 — {sorted(hit)}"


def test_x_quote_typography_matches_opening_statement_scale():
    """각인 문장은 theme.type.display(92px) — 오프닝 각인형과 같은 층위(수미상관)."""
    theme = json.loads((ROOT / "web" / "tokens" / "hwax-blue.json").read_text(encoding="utf-8"))
    display = theme["semantic"]["type"]["display"]
    assert 80 <= display <= 100, f"type.display 가 요구 대역(80~100px)을 벗어났다 — {display}"
    mod = load_module("x-quote")
    assert mod["typography_contract"]["quote_size_token"] == "type.display"
    src = JSX_FILE.read_text(encoding="utf-8")
    assert "quoteSize: theme.type.display" in src, "각인 문장이 display 토큰을 쓰지 않는다"
    # 배경을 비운다 — 킥커/타이틀/푸터 필드가 스키마에 아예 없다
    keys = deep_keys(load_schema("x-quote"))
    assert not (keys & {"kicker", "title", "frame"}), (
        f"x-quote 스키마에 크롬 필드가 있다 — {sorted(keys & {'kicker', 'title', 'frame'})}"
    )


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
    """최대 밀도 픽스처도 nat 안에 읽힌다 — 폭 상한(maxLength)과 낭독 예산이 동시에 성립한다."""
    from wdqa.gate2_length import collect_read_chars

    chars = collect_read_chars(load_schema(name), load_fixture(name, "max"))
    nat = load_module(name)["nat_default"]
    need = chars / CAPTION_CPS
    assert need <= nat, (
        f"{name}: max x-read {chars}자 → {need:.1f}s > nat {nat}s "
        f"— 자수 상한을 줄이거나 nat 를 올려야 한다"
    )
