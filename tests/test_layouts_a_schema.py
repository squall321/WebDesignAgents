# 발표 레이아웃 템플릿 4종(tpl.l-split/l-list/l-tree/l-quote)의 스키마·픽스처·module.yaml·병합 대기 레지스트리 정합 + 실물 수용 검증
import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
JSX_FILE = ROOT / "web" / "templates" / "omx-layouts-a.jsx"
FORMAT_ID = "wide-16x9"
STAGE = {"w": 1920, "h": 1080}
ORIGIN = "창작 모드 레이아웃 확장 2026-07-29"
LAYOUTS = {
    "l-split": "tpl.l-split",
    "l-list": "tpl.l-list",
    "l-tree": "tpl.l-tree",
    "l-quote": "tpl.l-quote",
}
BASE_FIXTURES = ["min", "typical", "max"]
EXTRA_FIXTURES = {"l-split": ["image", "note"], "l-tree": ["deep"]}
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
CAPTION_CPS = 9.0  # wdqa 게이트 2 자막 낭독 속도와 동일 기준
SAMPLE = ROOT / "examples" / "reportarchive" / "report_sample.json"


def load_schema(name: str) -> dict:
    return json.loads((TPL_DIR / name / "schema.json").read_text(encoding="utf-8"))


def load_fixture(name: str, fixture: str) -> dict:
    return json.loads((TPL_DIR / name / "fixtures" / f"{fixture}.json").read_text(encoding="utf-8"))


def load_module(name: str) -> dict:
    return yaml.safe_load((TPL_DIR / name / "module.yaml").read_text(encoding="utf-8"))


def all_fixtures(name: str) -> list[str]:
    return BASE_FIXTURES + EXTRA_FIXTURES.get(name, [])


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


def test_layout_modules_present():
    for name in LAYOUTS:
        assert (TPL_DIR / name).is_dir(), f"{name} 모듈 디렉터리가 없다"
    assert JSX_FILE.exists()


@pytest.mark.parametrize("name", LAYOUTS)
def test_schema_is_valid_jsonschema(name):
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema.get("type") == "object"
    assert schema["$id"].startswith(f"wda:{LAYOUTS[name]}/"), "레이아웃 스키마는 tpl.l-* 이름공간을 쓴다"
    assert schema.get("additionalProperties") is False


@pytest.mark.parametrize("name", LAYOUTS)
def test_schema_has_x_read_and_maxlength(name):
    schema = load_schema(name)
    assert walk_has_x_read(schema), f"{name}: x-read 낭독 필드가 하나도 없다"
    missing = walk_strings_have_maxlength(schema)
    assert not missing, f"{name}: maxLength 누락 문자열 선언 — {missing}"


@pytest.mark.parametrize("name", LAYOUTS)
def test_fixtures_pass_schema(name):
    schema = load_schema(name)
    for fixture in all_fixtures(name):
        msgs = schema_errors(schema, load_fixture(name, fixture))
        assert not msgs, f"{name}/{fixture}: {msgs}"


@pytest.mark.parametrize("name", LAYOUTS)
def test_module_yaml_contract(name):
    doc = load_module(name)
    assert doc["id"] == LAYOUTS[name]
    assert doc["type"] == "scene-template"
    assert doc["status"] == "draft"
    assert SEMVER.match(str(doc["version"]))
    assert doc["engine_compat"] == "animations-v2"
    assert doc["origin"] == ORIGIN
    assert doc["formats"] == [FORMAT_ID], "레이아웃 4종은 formats: [wide-16x9] 를 선언한다"
    assert doc["stage"] == STAGE
    assert isinstance(doc["nat_default"], (int, float)) and doc["nat_default"] > 0
    assert doc["in_scope"] and doc["out_of_scope"]
    assert doc["metaphors"] == ["frame-chrome", "dot-grid"], "허용 은유는 공통 크롬 2종뿐"
    entry = doc["entry"]
    tpl_file = ROOT / entry["template"].split("#")[0]
    assert tpl_file == JSX_FILE and tpl_file.exists()
    assert (TPL_DIR / name / entry["schema"]).exists()
    declared = [Path(fx).stem for fx in entry["fixtures"]]
    assert declared == all_fixtures(name), f"{name}: module.yaml fixtures 목록 불일치 — {declared}"
    for fx in entry["fixtures"]:
        assert (TPL_DIR / name / fx).exists()
    assert (TPL_DIR / name / entry["preview"]).exists()
    assert (TPL_DIR / name / "fixtures" / "snapshots" / "typical.png").exists()


@pytest.mark.parametrize("name", LAYOUTS)
def test_component_registered_in_jsx(name):
    src = JSX_FILE.read_text(encoding="utf-8")
    assert f"'{LAYOUTS[name]}'" in src, f"{LAYOUTS[name]} 이 templateIndex 에 등록되지 않았다"
    comp = load_module(name)["entry"]["template"].split("#")[1]
    assert f"function {comp}(" in src and f"{comp}.nat" in src and f"{comp}.schedule" in src, (
        f"{comp}: .nat/.schedule 정적 계약 누락"
    )


@pytest.mark.parametrize("name", LAYOUTS)
def test_preview_contract(name):
    html = (TPL_DIR / name / "preview.html").read_text(encoding="utf-8")
    assert "width={1920} height={1080}" in html, f"{name}: 프리뷰 무대가 1920×1080 이 아니다"
    assert "omx-layouts-a.jsx" in html, f"{name}: 프리뷰 로드 순서에 자기 jsx 가 없다"
    order = [html.index(f"web/templates/{f}") for f in
             ("omx-metaphors.jsx", "omx-templates.jsx", "omx-layouts-a.jsx")]
    assert order == sorted(order), f"{name}: 은유 → 템플릿 → 레이아웃 A 순서가 아니다"
    assert f"templateIndex['{LAYOUTS[name]}']" in html


def test_pending_registry_fragment_matches_modules():
    """병합 완료 검증 — registry.yaml 등재가 module.yaml 과 일치하는가.

    (구 _pending 조각 검사에서 전환: 오케스트레이터 병합이 끝나 조각은 제거됐고
     정본은 registry.yaml 이다.)
    """
    reg = yaml.safe_load((ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    by_id = {m["id"]: m for m in reg["modules"]}
    for name, tid in LAYOUTS.items():
        assert tid in by_id, f"{tid} 이 registry.yaml 에 없다"
        entry, mod = by_id[tid], load_module(name)
        assert entry["type"] == "scene-template"
        assert Path(entry["path"]) == Path("modules/scene-templates") / name
        assert entry.get("nat_default") == mod["nat_default"], f"{name}: nat_default 불일치"
        assert entry.get("status") == mod["status"]
        assert entry.get("version") == mod["version"]
    contract = [str(x) for x in reg["load_order_contract"]]
    assert any("omx-layouts-a.jsx" in x for x in contract), (
        "omx-layouts-a.jsx 이 load_order_contract 에 없으면 빌드 엔트리에서 누락된다")

# ── 밀도 조임의 실제 강제 — 스키마가 상한을 지키는지 (이 라운드의 존재 이유) ──


def test_split_tightens_bullets_when_five():
    """불릿 5개면 22자로 조인다 — 세로 예산(소결론 하단 고정) 위반을 스키마가 먼저 막는다."""
    schema = load_schema("l-split")
    d = json.loads(json.dumps(load_fixture("l-split", "typical")))
    long_text = "가" * 30
    d["bullets"] = [{"text": long_text}] * 4
    assert not schema_errors(schema, d), "4개일 때 30자는 통과해야 한다"
    d["bullets"] = [{"text": long_text}] * 5
    assert schema_errors(schema, d), "5개일 때 30자가 통과되면 세로 예산이 깨진다"
    d["bullets"] = [{"text": "가" * 22}] * 5
    assert not schema_errors(schema, d), "5개 × 22자는 통과해야 한다"
    d["bullets"] = [{"text": "가"}] * 6
    assert schema_errors(schema, d), "불릿 6개는 거부해야 한다"


def test_split_visual_requires_matching_payload():
    """visual.kind 가 가리키는 슬롯이 없으면 거부한다 (빈 근거 패널 금지)."""
    schema = load_schema("l-split")
    for kind in ("table", "bars", "image", "note"):
        d = json.loads(json.dumps(load_fixture("l-split", "min")))
        d["visual"] = {"kind": kind}
        assert schema_errors(schema, d), f"kind={kind} 인데 payload 없음이 통과되면 안 된다"
    d = json.loads(json.dumps(load_fixture("l-split", "min")))
    d["ratio"] = "7:3"
    assert schema_errors(schema, d), "비율은 고정값 2안(6:4·5:5) 뿐이다"


def test_list_tightens_desc_when_six_rows():
    """6행 이상이면 설명 1행(50자) — 행 높이가 100px 아래로 내려가기 때문."""
    schema = load_schema("l-list")
    d = json.loads(json.dumps(load_fixture("l-list", "typical")))
    row = {"title": "제목", "desc": "가" * 100}
    d["rows"] = [row] * 5
    assert not schema_errors(schema, d), "5행일 때 100자 설명은 통과해야 한다"
    d["rows"] = [row] * 6
    assert schema_errors(schema, d), "6행일 때 100자 설명이 통과되면 행 높이가 깨진다"
    d["rows"] = [{"title": "제목", "desc": "가" * 50}] * 8
    assert not schema_errors(schema, d), "8행 × 50자는 통과해야 한다"
    d["rows"] = [{"title": "제목"}] * 9
    assert schema_errors(schema, d), "9행은 거부해야 한다 (최소 폰트 24px 를 깬다)"


def test_tree_enforces_level_capacity():
    """루트 1 · 중간 2~4 · 리프 ≤8 을 contains/maxContains 로 강제한다."""
    schema = load_schema("l-tree")
    base = load_fixture("l-tree", "min")

    def with_nodes(extra):
        d = json.loads(json.dumps(base))
        d["nodes"] = d["nodes"] + extra
        return d

    assert schema_errors(schema, with_nodes([{"id": "r2", "label": "루트둘", "level": 0}])), \
        "루트 2개가 통과되면 안 된다"
    assert schema_errors(schema, with_nodes(
        [{"id": f"b{i}", "label": f"가지{i}", "level": 1} for i in range(3)]
    )), "중간 노드 5개(2+3)가 통과되면 안 된다"
    assert schema_errors(schema, with_nodes(
        [{"id": f"l{i}", "label": f"리프{i}", "level": 2} for i in range(7)]
    )), "리프 9개(2+7)가 통과되면 안 된다"
    # 레벨별 라벨 상한 — 루트 14자·중간 18자·리프 22자
    d = json.loads(json.dumps(base))
    d["nodes"][0]["label"] = "가" * 15
    assert schema_errors(schema, d), "루트 15자가 통과되면 nowrap 상자를 넘친다"
    d = json.loads(json.dumps(base))
    d["nodes"][1]["label"] = "가" * 19
    assert schema_errors(schema, d), "중간 19자가 통과되면 안 된다"
    d = json.loads(json.dumps(base))
    d["nodes"][3]["label"] = "가" * 22
    assert not schema_errors(schema, d), "리프 22자는 통과해야 한다"
    d["nodes"][3]["label"] = "가" * 23
    assert schema_errors(schema, d), "리프 23자가 통과되면 안 된다"


def test_quote_size_ladder_bounds():
    """각인 문장은 70자 상한 — 60px 3행이 폭 1400px 안에 드는 경계."""
    schema = load_schema("l-quote")
    assert not schema_errors(schema, {"quote": "가" * 70})
    assert schema_errors(schema, {"quote": "가" * 71})
    assert schema_errors(schema, {"quote": "짧은 문장", "texture": "shadow"}), \
        "텍스처는 none/rule/marks 3안 뿐"
    assert "title" not in schema["properties"], "각인 씬은 타이틀을 두지 않는다(문장이 타이틀)"


# ── 실물 수용 — report_sample 의 structured payload 가 그대로 들어가는지 ──


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


def test_real_tree_payload_fits_l_tree_verbatim():
    """§8 'tree(15노드 3단) — 슬롯 없음' 해소: graph payload 의 nodes/edges 를 이름 그대로 받는다."""
    payloads = _structured_payloads()
    assert payloads.get("tree"), "report_sample 에 tree 위젯이 없다"
    p = payloads["tree"][0]
    assert p["shape"] == "tree"
    node_schema = load_schema("l-tree")["properties"]["nodes"]["items"]["properties"]
    edge_schema = load_schema("l-tree")["properties"]["edges"]["items"]["properties"]
    # 필드 이름 개명 없이 그대로 받는지 — payload 키가 스키마 속성의 부분집합이어야 한다
    for n in p["nodes"]:
        assert set(n) <= set(node_schema), f"노드 키 개명 필요: {set(n) - set(node_schema)}"
    for e in p["edges"]:
        assert set(e) <= set(edge_schema), f"엣지 키 개명 필요: {set(e) - set(edge_schema)}"
    assert len(p["nodes"]) == 15 and max(n["level"] for n in p["nodes"]) == 2, \
        "실물 규모 전제(15노드 3단)가 변했다"

    # 용량 상한(루트1·중간3·리프8)까지 추린 뒤 스키마 통과 — 추리기는 심의 몫, 잔여는 omitted
    caps = {0: 1, 1: 3, 2: 8}
    trim = {0: 14, 1: 18, 2: 22}
    kept, used = [], {0: 0, 1: 0, 2: 0}
    for n in p["nodes"]:
        lv = n["level"]
        if used[lv] >= caps[lv]:
            continue
        used[lv] += 1
        node = {"id": n["id"], "label": n["label"][:trim[lv]], "level": lv}
        if lv == 1 and n.get("note"):
            node["note"] = n["note"][:13]
        kept.append(node)
    ids = {n["id"] for n in kept}
    data = {
        "kicker": "시스템 계층",
        "title": p["caption"][:26],
        "nodes": kept,
        "edges": [e for e in p["edges"] if e["from"] in ids and e["to"] in ids],
        "omitted": len(p["nodes"]) - len(kept),
    }
    msgs = schema_errors(load_schema("l-tree"), data)
    assert not msgs, f"실물 tree 가 스키마에 안 들어간다: {msgs}"
    assert data["omitted"] == 3


def test_real_comparison_fits_l_split_table_slot():
    """§8 comparison(3열 5행)이 l-split 근거 슬롯 간이표에 들어간다 (셀 축약은 심의 몫)."""
    payloads = _structured_payloads()
    assert payloads.get("comparison"), "report_sample 에 comparison 이 없다"
    p = next(x for x in payloads["comparison"] if len(x["columns"]) == 3)
    cols = p["columns"]
    data = {
        "kicker": "배포 구성",
        "title": (p.get("caption") or "비교")[:26],
        "bullets": [{"text": "실물 비교표를 근거 슬롯에 얹는다"}] * 3,
        "visual": {
            "kind": "table",
            "table": {
                "columns": [{"label": c["label"][:12]} for c in cols],
                "rows": [
                    {"label": r[cols[0]["key"]][:20],
                     "cells": [{"v": r[c["key"]][:14]} for c in cols[1:]]}
                    for r in p["rows"]
                ],
            },
        },
    }
    assert len(data["visual"]["table"]["rows"]) == 5, "실물 규모 전제(5행)가 변했다"
    msgs = schema_errors(load_schema("l-split"), data)
    assert not msgs, f"실물 비교표가 근거 슬롯에 안 들어간다: {msgs}"


def test_real_key_value_fits_l_list_rows():
    """§8 key_value(9쌍)가 l-list 8행 용량에 들어간다 — 초과 1건은 심의가 추린다."""
    payloads = _structured_payloads()
    assert payloads.get("key_value"), "report_sample 에 key_value 가 없다"
    pairs = payloads["key_value"][0]["pairs"]
    assert len(pairs) >= 8, f"실물 규모 전제가 변했다 — {len(pairs)}쌍"
    data = {
        "kicker": "기술 스택",
        "title": "무엇으로 만들었는가",
        "rows": [
            {"num": str(i + 1).zfill(2), "title": p["label"][:30], "desc": p["value"][:50]}
            for i, p in enumerate(pairs[:8])
        ],
    }
    msgs = schema_errors(load_schema("l-list"), data)
    assert not msgs, f"실물 키값 목록이 스키마에 안 들어간다: {msgs}"


# ── 게이트 2 예산 — typical 픽스처의 x-read 글자수가 nat 안에 낭독 가능한지 ──


@pytest.mark.parametrize("name", LAYOUTS)
def test_typical_fixture_fits_caption_budget(name):
    from wdqa.gate2_length import collect_read_chars

    schema = load_schema(name)
    data = load_fixture(name, "typical")
    chars = collect_read_chars(schema, data)
    nat = load_module(name)["nat_default"]
    assert chars > 0, f"{name}: typical 에 x-read 글자가 없다"
    need = chars / CAPTION_CPS
    assert need <= nat, f"{name}: x-read {chars}자 ÷ {CAPTION_CPS}자/초 = {need:.1f}s > nat {nat}s"


@pytest.mark.parametrize("name", LAYOUTS)
def test_max_fixture_also_fits_caption_budget(name):
    """상한 픽스처도 nat 안에 낭독 가능해야 밀도 상한과 시간 예산이 어긋나지 않는다."""
    from wdqa.gate2_length import collect_read_chars

    chars = collect_read_chars(load_schema(name), load_fixture(name, "max"))
    nat = load_module(name)["nat_default"]
    need = chars / CAPTION_CPS
    assert need <= nat, f"{name}/max: {chars}자 ÷ {CAPTION_CPS} = {need:.1f}s > nat {nat}s"
