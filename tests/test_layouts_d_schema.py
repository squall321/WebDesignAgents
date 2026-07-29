# 구조·목록 레이아웃 2종(tpl.c-branch/c-grid)의 스키마·픽스처·module.yaml·병합 대기 레지스트리 정합 + 구조 payload 수용 검증
import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
JSX_FILE = ROOT / "web" / "templates" / "omx-layouts-d.jsx"
PENDING = ROOT / "modules" / "_pending" / "layouts-d.registry.yaml"
FORMAT_ID = "wide-16x9"
STAGE = {"w": 1920, "h": 1080}
ORIGIN = "창작 모드 커버리지 1순위 2026-07-29"
MODULES = {"c-branch": "tpl.c-branch", "c-grid": "tpl.c-grid"}
FIXTURES = ["min", "typical", "max"]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
CAPTION_CPS = 9.0  # wdqa 게이트 2 자막 낭독 속도와 동일 기준
SAMPLE = ROOT / "examples" / "reportarchive" / "report_sample.json"


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
    assert doc["in_scope"] and doc["out_of_scope"]
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
    assert "omx-layouts-d.jsx" in html, f"{name}: 프리뷰 로드 순서에 자기 jsx 가 없다"
    assert f"templateIndex['{MODULES[name]}']" in html


def test_pending_registry_fragment():
    """registry.yaml 은 병렬 작업자 소유 — 조각이 병합에 필요한 값을 전부 들고 있어야 한다."""
    frag = yaml.safe_load(PENDING.read_text(encoding="utf-8"))
    order = frag["merge"]["load_order_contract"]
    assert order["entries"] == ["web/templates/omx-layouts-d.jsx"]
    assert order["insert_before"] == "<project scenes.jsx>"
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
    assert "web/templates/omx-layouts-d.jsx" in order, "병합됐는데 로드 순서에 jsx 가 없다"
    assert order.index("web/templates/omx-layouts-d.jsx") < order.index("<project scenes.jsx>")
    for name, tid in MODULES.items():
        entry = next(m for m in reg["modules"] if m["id"] == tid)
        assert entry["nat_default"] == load_module(name)["nat_default"]


# ── 구조 왜곡 방지 계약 — 스키마가 실제로 거르는지 ────────────────────────


def test_branch_schema_forbids_linear_and_deep_flows():
    """분기 없는 선형 절차·5레벨은 스키마가 거른다 (tpl.process 로 가라는 뜻)."""
    schema = load_schema("c-branch")
    props = schema["properties"]
    assert props["nodes"]["maxItems"] == 12 and props["nodes"]["minItems"] == 3
    assert props["nodes"]["items"]["properties"]["level"]["maximum"] == 3, "레벨 상한 3(열 4개)"
    assert props["edges"]["minItems"] == 2, "엣지 없는 '흐름 없는 흐름도' 금지"
    assert props["edges"]["items"]["properties"]["label"]["maxLength"] == 3, "분기 라벨 3자 상한"
    # 판단 노드가 하나도 없으면 거부 — 선형 절차의 둔갑 차단
    linear = json.loads(json.dumps(load_fixture("c-branch", "min")))
    for n in linear["nodes"]:
        n.pop("kind", None)
    assert schema_errors(schema, linear), "판단(decision) 없는 흐름이 통과되면 안 된다"
    # 레벨 4(5단계)는 거부 — 자동 축소로 폰트를 줄이는 경로 차단
    deep = json.loads(json.dumps(load_fixture("c-branch", "min")))
    deep["nodes"][2]["level"] = 4
    assert schema_errors(schema, deep), "레벨 4가 통과되면 안 된다"
    # 판단 노드 라벨은 마름모 내접 사각 기준 12자 — 초과 거부
    long_label = json.loads(json.dumps(load_fixture("c-branch", "min")))
    long_label["nodes"][1]["label"] = "판단 문구가 열세자"[:13] + "글자넘침"
    assert schema_errors(schema, long_label), "판단 라벨 12자 초과가 통과되면 안 된다"


def test_branch_fixtures_keep_forward_edges_and_level_capacity():
    """픽스처는 전진 엣지만 쓰고 레벨당 3개를 넘지 않는다 (렌더 역산 전제)."""
    for fixture in FIXTURES:
        d = load_fixture("c-branch", fixture)
        level_of = {n["id"]: n["level"] for n in d["nodes"]}
        per_level: dict[int, int] = {}
        for n in d["nodes"]:
            per_level[n["level"]] = per_level.get(n["level"], 0) + 1
        assert max(per_level.values()) <= 3, (
            f"c-branch/{fixture}: 레벨당 노드 {max(per_level.values())}개 — 3개 상한 초과"
        )
        for e in d["edges"]:
            assert e["from"] in level_of and e["to"] in level_of, (
                f"c-branch/{fixture}: 존재하지 않는 노드 참조 — {e}"
            )
            assert level_of[e["to"]] > level_of[e["from"]], (
                f"c-branch/{fixture}: 역류 엣지 — {e} (전진 엣지만 그려진다)"
            )
    # max 픽스처는 레벨 건너뛰기 엣지를 반드시 포함한다 — 우회 레인 실렌더 검증용
    d = load_fixture("c-branch", "max")
    level_of = {n["id"]: n["level"] for n in d["nodes"]}
    spans = [level_of[e["to"]] - level_of[e["from"]] for e in d["edges"]]
    assert max(spans) >= 2, "max 픽스처에 레벨 건너뛰기 엣지가 없다 (우회 레인이 검증되지 않는다)"


def test_grid_schema_has_no_layout_fields():
    """배치는 렌더가 정한다 — 스키마에 열·행·폰트 필드가 있으면 밀도 왜곡 경로가 열린다."""
    schema = load_schema("c-grid")
    keys = deep_keys(schema)
    forbidden = {"cols", "rows", "columns", "fontSize", "font_size", "cardWidth", "cardHeight",
                 "layout", "density", "scale"}
    assert not (keys & forbidden), f"배치 지정 필드가 스키마에 있다 — {sorted(keys & forbidden)}"
    props = schema["properties"]
    assert props["cards"]["minItems"] == 4 and props["cards"]["maxItems"] == 9
    assert props["omitted"]["type"] == "integer" and props["omitted"]["minimum"] == 1
    item = props["cards"]["items"]["properties"]
    assert item["label"]["maxLength"] == 16, "3×3 밀집 기준 제목 자수 역산(26px 1줄)"
    assert item["desc"]["maxLength"] == 36, "3×3 밀집 기준 설명 자수 역산(24px 2줄)"
    # 10장은 거부 — 잘라 넣기 금지, 초과분은 omitted 로 계상
    over = json.loads(json.dumps(load_fixture("c-grid", "max")))
    over["cards"] = over["cards"] + [over["cards"][0]]
    assert len(over["cards"]) == 10
    assert schema_errors(schema, over), "10장이 통과되면 안 된다"
    # 3장도 거부 — 3열 고정 tpl.proof 영역
    few = json.loads(json.dumps(load_fixture("c-grid", "min")))
    few["cards"] = few["cards"][:3]
    assert schema_errors(schema, few), "3장이 통과되면 안 된다 (tpl.proof 영역)"


# ── 구조 payload 수용 — widgets.py 산출을 필드명 그대로 받는가 ─────────────


def _structured_payloads() -> dict:
    from wdpipeline.fragmentize import fragmentize
    from wdpipeline.ingest import ingest_report_file

    norm = ingest_report_file(SAMPLE)
    out: dict = {}
    for f in fragmentize(norm):
        s = f.get("structured")
        if s:
            out.setdefault(f.get("widget"), []).append(s)
    return out


def test_real_graph_payload_fits_c_branch_without_renaming():
    """widgets.py graph payload(nodes[id,label,level] · edges[from,to])를 필드명 그대로 받는다."""
    payloads = _structured_payloads()
    assert payloads.get("tree"), "report_sample 에 tree(graph payload) 가 없다"
    p = payloads["tree"][0]
    keep = {n["id"] for n in p["nodes"] if n.get("level", 0) <= 3}
    nodes = []
    for n in p["nodes"]:
        if n["id"] not in keep or len(nodes) >= 12:
            continue
        node = {"id": n["id"][:40], "label": n["label"][:22], "level": n["level"]}
        if n.get("note"):
            node["note"] = n["note"][:20]
        nodes.append(node)
    ids = {n["id"] for n in nodes}
    level_of = {n["id"]: n["level"] for n in nodes}
    # 심의가 판단 노드 1개를 지정한다 (분기 흐름도의 존재 조건)
    for n in nodes:
        if n["level"] == 1:
            n["kind"] = "decision"
            n["label"] = n["label"][:12]
            break
    edges = [
        {"from": e["from"], "to": e["to"]}
        for e in p["edges"]
        if e["from"] in ids and e["to"] in ids and level_of[e["to"]] > level_of[e["from"]]
    ][:14]
    assert len(nodes) >= 3 and len(edges) >= 2, f"실물 규모 전제가 변했다 — {len(nodes)}/{len(edges)}"
    data = {"kicker": "구조", "title": "ReportArchive 공간 구조", "nodes": nodes, "edges": edges}
    msgs = schema_errors(load_schema("c-branch"), data)
    assert not msgs, f"실물 graph payload 가 스키마에 안 들어간다: {msgs}"


def test_real_pairs_payload_fits_c_grid_nine_cards():
    """§ key_value 9쌍 — 담을 그릇이 없던 목록이 3×3 카드 그리드에 그대로 들어간다."""
    payloads = _structured_payloads()
    assert payloads.get("key_value"), "report_sample 에 key_value(pairs payload) 가 없다"
    p = max(payloads["key_value"], key=lambda x: len(x["pairs"]))
    pairs = p["pairs"]
    assert len(pairs) == 9, f"실물 규모 전제(9쌍)가 변했다 — {len(pairs)}쌍"
    data = {
        "kicker": "기술 스택",
        "title": (p.get("caption") or "기술 스택")[:26],
        # 배선 계약: pairs.label → cards[].label, pairs.value → cards[].desc (축약은 심의 몫)
        "cards": [{"label": x["label"][:16], "desc": x["value"][:36]} for x in pairs],
    }
    msgs = schema_errors(load_schema("c-grid"), data)
    assert not msgs, f"실물 pairs 9쌍이 스키마에 안 들어간다: {msgs}"


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
