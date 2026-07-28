# 창작 모드 위젯 수용 템플릿 3종(tpl.d-matrix/d-media/d-multi)의 스키마·픽스처·module.yaml·registry 정합 + 실물 규모 수용 검증
import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
DATA_FILE = ROOT / "web" / "templates" / "omx-templates-data.jsx"
FORMAT_ID = "wide-16x9"
STAGE = {"w": 1920, "h": 1080}
ORIGIN = "창작 모드 위젯 수용 2026-07-27"
DATA = {"d-matrix": "tpl.d-matrix", "d-media": "tpl.d-media", "d-multi": "tpl.d-multi"}
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


def test_data_modules_present():
    for name in DATA:
        assert (TPL_DIR / name).is_dir(), f"{name} 모듈 디렉터리가 없다"
    assert DATA_FILE.exists()


@pytest.mark.parametrize("name", DATA)
def test_schema_is_valid_jsonschema(name):
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema.get("type") == "object"
    assert schema["$id"].startswith(f"wda:{DATA[name]}/"), "데이터 스키마는 tpl.d-* 이름공간을 쓴다"
    assert schema.get("additionalProperties") is False


@pytest.mark.parametrize("name", DATA)
def test_schema_has_x_read_and_maxlength(name):
    schema = load_schema(name)
    assert walk_has_x_read(schema), f"{name}: x-read 낭독 필드가 하나도 없다"
    missing = walk_strings_have_maxlength(schema)
    assert not missing, f"{name}: maxLength 누락 문자열 선언 — {missing}"


@pytest.mark.parametrize("name", DATA)
@pytest.mark.parametrize("fixture", FIXTURES)
def test_fixture_passes_schema(name, fixture):
    msgs = schema_errors(load_schema(name), load_fixture(name, fixture))
    assert not msgs, f"{name}/{fixture}: {msgs}"


@pytest.mark.parametrize("name", DATA)
def test_module_yaml_contract(name):
    doc = load_module(name)
    assert doc["id"] == DATA[name]
    assert doc["type"] == "scene-template"
    assert doc["status"] == "draft"
    assert SEMVER.match(str(doc["version"]))
    assert doc["engine_compat"] == "animations-v2"
    assert doc["origin"] == ORIGIN
    assert doc["formats"] == [FORMAT_ID], "위젯 수용 3종은 formats: [wide-16x9] 를 선언한다"
    assert doc["stage"] == STAGE
    assert isinstance(doc["nat_default"], (int, float)) and doc["nat_default"] > 0
    assert doc["in_scope"] and doc["out_of_scope"]
    assert doc["metaphors"] == ["frame-chrome", "dot-grid"], "허용 은유는 공통 크롬 2종뿐"
    entry = doc["entry"]
    tpl_file = ROOT / entry["template"].split("#")[0]
    assert tpl_file == DATA_FILE and tpl_file.exists()
    assert (TPL_DIR / name / entry["schema"]).exists()
    for fx in entry["fixtures"]:
        assert (TPL_DIR / name / fx).exists()
    assert (TPL_DIR / name / entry["preview"]).exists()
    assert (TPL_DIR / name / "fixtures" / "snapshots" / "typical.png").exists()


@pytest.mark.parametrize("name", DATA)
def test_component_registered_in_jsx(name):
    src = DATA_FILE.read_text(encoding="utf-8")
    assert f"'{DATA[name]}'" in src, f"{DATA[name]} 이 templateIndex 에 등록되지 않았다"
    comp = load_module(name)["entry"]["template"].split("#")[1]
    assert f"function {comp}(" in src and f"{comp}.nat" in src and f"{comp}.schedule" in src, (
        f"{comp}: .nat/.schedule 정적 계약 누락"
    )


@pytest.mark.parametrize("name", DATA)
def test_preview_contract(name):
    html = (TPL_DIR / name / "preview.html").read_text(encoding="utf-8")
    assert "width={1920} height={1080}" in html, f"{name}: 프리뷰 무대가 1920×1080 이 아니다"
    assert "omx-templates-data.jsx" in html
    assert f"templateIndex['{DATA[name]}']" in html


def test_registry_indexes_data_modules():
    reg = yaml.safe_load((ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    ids = [m["id"] for m in reg["modules"]]
    assert len(ids) == len(set(ids)), "레지스트리 id 중복"
    for name, tid in DATA.items():
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
    data_jsx = "web/templates/omx-templates-data.jsx"
    assert data_jsx in order, "load_order_contract 에 데이터 템플릿 파일이 없다 — 엔트리에서 누락된다"
    assert order.index(data_jsx) == order.index("web/templates/omx-templates-ext.jsx") + 1, (
        "데이터 템플릿 파일은 omx-templates-ext.jsx 직후에 로드되어야 한다"
    )
    assert order.index(data_jsx) < order.index("<project scenes.jsx>")


# ── 창작 모드 고유 계약 — 용량 강제·0 기준선·칩 코드값 ──────────────────────


def test_matrix_schema_enforces_grid_capacity():
    schema = load_schema("d-matrix")
    props = schema["properties"]
    assert props["columns"]["maxItems"] == 8, "격자 열 상한 8 (§8 실물 역산 — raci 6열 수용)"
    assert props["rows"]["maxItems"] == 8, "격자 행 상한 8 — 초과분은 omitted"
    assert props["omitted"]["type"] == "integer" and props["omitted"]["minimum"] == 1
    # 칩 셀은 코드값 전용 — chip:true 인데 4자를 넘으면 거부
    bad = json.loads(json.dumps(load_fixture("d-matrix", "min")))
    bad["rows"][0]["cells"][0] = {"v": "코드값다섯자", "chip": True}
    assert schema_errors(schema, bad), "칩 셀 5자 초과가 통과되면 안 된다"
    # 9행은 스키마가 거부한다 (잘라 넣기 금지 — omitted 로 계상)
    bad2 = json.loads(json.dumps(load_fixture("d-matrix", "min")))
    bad2["rows"] = bad2["rows"] + [bad2["rows"][0]] * 7
    assert len(bad2["rows"]) == 9
    assert schema_errors(schema, bad2), "9행이 통과되면 안 된다"


def test_multi_schema_enforces_zero_baseline_and_series_capacity():
    schema = load_schema("d-multi")
    props = schema["properties"]
    assert schema["additionalProperties"] is False and "axisMin" not in props, (
        "축 하한 필드가 존재하면 0 기준선 강제가 깨진다"
    )
    assert props["axisMax"]["exclusiveMinimum"] == 0
    assert props["series"]["minItems"] == 2 and props["series"]["maxItems"] == 4
    assert props["categories"]["maxItems"] == 7, "다계열 항목 상한 7 (progress_bar 7계열 수용)"
    vals = props["series"]["items"]["properties"]["values"]
    assert vals["items"]["minimum"] == 0, "values 는 minimum:0 (음수 막대 금지)"
    assert vals["maxItems"] == 7
    bad = json.loads(json.dumps(load_fixture("d-multi", "min")))
    bad["series"][0]["values"][0] = -1
    assert schema_errors(schema, bad), "음수 값이 통과되면 안 된다"


def test_media_schema_requires_caption_and_alt():
    schema = load_schema("d-media")
    files = schema["properties"]["files"]
    assert files["minItems"] == 1 and files["maxItems"] == 3
    assert set(files["items"]["required"]) == {"src", "caption", "alt"}, (
        "도판은 항상 src+caption+alt (출처·접근성 강제)"
    )


# ── 실물 규모 수용 — §8 미수용 블록이 실제로 들어가는지 (이 라운드의 존재 이유) ──


def _structured_payloads() -> dict:
    """report_sample.json 실물에서 위젯별 structured payload 를 뽑는다."""
    from wdpipeline.fragmentize import fragmentize
    from wdpipeline.ingest import ingest_report_file

    norm = ingest_report_file(SAMPLE)
    out: dict = {}
    for f in fragmentize(norm):
        s = f.get("structured")
        if s:
            out.setdefault(f.get("widget"), []).append(s)
    return out


def test_real_raci_matrix_fits_d_matrix():
    """§8 'raci_matrix (6열) — 슬롯 없음' 이 tpl.d-matrix 에 그대로 들어간다 (축약 무필요)."""
    payloads = _structured_payloads()
    assert payloads.get("raci_matrix"), "report_sample 에 raci_matrix 가 없다"
    p = payloads["raci_matrix"][0]
    data = {
        "kicker": "역할과 책임",
        "title": p["caption"][:26],
        "columns": [{"label": c["label"]} for c in p["columns"]],
        "rows": [
            {
                "label": r[p["columns"][0]["key"]],
                "cells": [{"v": r[c["key"]], "chip": True} for c in p["columns"][1:]],
            }
            for r in p["rows"]
        ],
    }
    assert len(data["columns"]) == 6 and len(data["rows"]) == 8, "실물 규모 전제(6열×8행)가 변했다"
    msgs = schema_errors(load_schema("d-matrix"), data)
    assert not msgs, f"실물 raci 가 스키마에 안 들어간다: {msgs}"


def test_real_progress_bar_series_fits_d_multi_capacity():
    """§8 'progress_bar 7계열 — dataviz 5칸 초과' 가 tpl.d-multi 7항목 용량에 들어간다.

    라벨 축약은 심의 몫(§8 trim 정책)이므로 여기서는 개수 용량만 실물로 증명한다.
    """
    payloads = _structured_payloads()
    assert payloads.get("progress_bar"), "report_sample 에 progress_bar 가 없다"
    p = payloads["progress_bar"][0]
    items = p["series"]
    assert len(items) == 7, "실물 규모 전제(7계열)가 변했다"
    schema = load_schema("d-multi")
    cap = schema["properties"]["categories"]["maxItems"]
    assert len(items) <= cap, f"실물 7계열이 categories 용량 {cap} 을 넘는다"
    values = [it["value"] for it in items]
    remain = [(it.get("max") or 100.0) - it["value"] for it in items]
    data = {
        "kicker": "구현 현황",
        "title": (p.get("caption") or "진척")[:26],
        "unit": "%",
        "axisMax": 100,
        "categories": [{"label": f"P{i}"} for i in range(len(items))],  # 라벨 축약은 심의 몫
        "series": [
            {"name": "완료율", "tone": "primary", "values": values},
            {"name": "잔여", "tone": "muted", "values": remain},
        ],
    }
    msgs = schema_errors(schema, data)
    assert not msgs, f"실물 진행률(값 그대로)이 스키마에 안 들어간다: {msgs}"


def test_resolved_assets_fit_d_media():
    """§6 '해결된 자산이 들어갈 씬 슬롯 0건' 해소 — 자산 3건이 files 슬롯에 들어간다."""
    imgs = ROOT / "data" / "widget_check" / "report_with_images.json"
    if not imgs.exists():
        pytest.skip("report_with_images.json 픽스처 없음")
    from wdpipeline.ingest import ingest_report_file
    from wdpipeline.widgets import collect_media

    norm = ingest_report_file(imgs, assets_dir=imgs.parent / "assets")
    media = [m for m in collect_media(norm) if (m.get("asset") or {}).get("local_path")]
    assert len(media) >= 3, f"해결된 자산이 {len(media)}건뿐 — §6 전제(3건)와 다르다"
    data = {
        "kicker": "자산",
        "title": "자산 참조 보고서"[:26],
        "files": [
            {
                "src": m["asset"]["local_path"][:200],
                "caption": (m.get("caption") or m.get("alt") or "도판")[:18],
                "alt": (m.get("alt") or m.get("caption") or "도판")[:80],
            }
            for m in media[:3]
        ],
    }
    msgs = schema_errors(load_schema("d-media"), data)
    assert not msgs, f"해결된 자산이 스키마에 안 들어간다: {msgs}"


# ── 게이트 2 예산 — typical 픽스처의 x-read 글자수가 nat 안에 낭독 가능한지 ──


@pytest.mark.parametrize("name", DATA)
def test_typical_fixture_fits_caption_budget(name):
    from wdqa.gate2_length import collect_read_chars

    schema = load_schema(name)
    data = load_fixture(name, "typical")
    chars = collect_read_chars(schema, data)
    nat = load_module(name)["nat_default"]
    assert chars > 0, f"{name}: typical 에 x-read 글자가 없다"
    need = chars / CAPTION_CPS
    assert need <= nat, f"{name}: x-read {chars}자 ÷ {CAPTION_CPS}자/초 = {need:.1f}s > nat {nat}s"
