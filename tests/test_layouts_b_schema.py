# 수치·대비 레이아웃 4종(tpl.l-kpi/l-quad/l-ba/l-mix)의 스키마·픽스처·module.yaml·병합 대기 레지스트리 조각 정합 + 실물 structured payload 수용 검증
import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
JSX_FILE = ROOT / "web" / "templates" / "omx-layouts-b.jsx"
FORMAT_ID = "wide-16x9"
STAGE = {"w": 1920, "h": 1080}
ORIGIN = "창작 모드 레이아웃 확장 2026-07-29"
LAYOUTS = {
    "l-kpi": "tpl.l-kpi",
    "l-quad": "tpl.l-quad",
    "l-ba": "tpl.l-ba",
    "l-mix": "tpl.l-mix",
}
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
@pytest.mark.parametrize("fixture", FIXTURES)
def test_fixture_passes_schema(name, fixture):
    msgs = schema_errors(load_schema(name), load_fixture(name, fixture))
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
    assert "omx-layouts-b.jsx" in html, f"{name}: 프리뷰 로드 순서에 자기 jsx 가 없다"
    assert f"templateIndex['{LAYOUTS[name]}']" in html
    # 로드 순서 — 엔진 → 토큰 → 은유 → 템플릿 → 레이아웃 B
    order = [
        html.index("runtime/animations-v2.jsx"),
        html.index("tokens/loader.jsx"),
        html.index("templates/omx-metaphors.jsx"),
        html.index("templates/omx-templates.jsx"),
        html.index("templates/omx-layouts-b.jsx"),
    ]
    assert order == sorted(order), f"{name}: 프리뷰 스크립트 로드 순서가 계약과 다르다"


def test_pending_registry_fragment_is_mergeable():
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
    assert any("omx-layouts-b.jsx" in x for x in contract), (
        "omx-layouts-b.jsx 이 load_order_contract 에 없으면 빌드 엔트리에서 누락된다")

# ── 이 라운드의 존재 이유 — 배치 다양성 계약 ────────────────────────────────


def test_kpi_capacity_exceeds_closing_stats():
    """closing.stats 3개 상한이 못 담던 4~6 지표를 담는다 (이 템플릿의 존재 이유)."""
    closing = json.loads((TPL_DIR / "closing" / "schema.json").read_text(encoding="utf-8"))
    assert closing["properties"]["stats"]["maxItems"] == 3, "closing.stats 상한 전제(3)가 변했다"
    kpi = load_schema("l-kpi")["properties"]["metrics"]
    assert kpi["minItems"] == 4 and kpi["maxItems"] == 6


def test_kpi_delta_separates_direction_and_verdict():
    """증감은 방향(dir)과 평가(tone)를 **따로** 요구한다 — 방향만으로 색을 정할 수 없게."""
    delta = load_schema("l-kpi")["properties"]["metrics"]["items"]["properties"]["delta"]
    assert set(delta["required"]) == {"dir", "text", "tone"}
    assert delta["properties"]["dir"]["enum"] == ["up", "down", "flat"]
    assert delta["properties"]["tone"]["enum"] == ["good", "bad", "neutral"]
    # 실제 픽스처에 (감소=좋음), (증가=나쁨) 이 둘 다 있어야 규칙이 살아있는 증거가 된다
    metrics = load_fixture("l-kpi", "typical")["metrics"]
    combos = {(m["delta"]["dir"], m["delta"]["tone"]) for m in metrics if "delta" in m}
    assert ("down", "good") in combos, "감소가 좋음인 사례가 typical 에 없다"
    assert ("up", "bad") in combos, "증가가 나쁨인 사례가 typical 에 없다"


def test_quad_coordinates_are_normalized():
    """좌표는 0~1 정규화로 강제 — 범위 밖 값은 스키마가 막고 렌더가 clamp 한다."""
    items = load_schema("l-quad")["properties"]["items"]
    assert items["minItems"] == 4 and items["maxItems"] == 10
    for axis in ("x", "y"):
        prop = items["items"]["properties"][axis]
        assert prop["minimum"] == 0 and prop["maximum"] == 1
    bad = json.loads(json.dumps(load_fixture("l-quad", "min")))
    bad["items"][0]["x"] = 1.4
    assert schema_errors(load_schema("l-quad"), bad), "1 초과 좌표가 통과되면 안 된다"
    bad2 = json.loads(json.dumps(load_fixture("l-quad", "min")))
    bad2["items"][0]["y"] = -0.2
    assert schema_errors(load_schema("l-quad"), bad2), "0 미만 좌표가 통과되면 안 된다"
    # 사분면 네 칸 모두 이름이 있어야 매트릭스가 논증이 된다
    assert set(load_schema("l-quad")["properties"]["quadrants"]["required"]) == {
        "tl", "tr", "bl", "br"
    }


def test_ba_is_whole_state_contrast_not_row_pairs():
    """l-ba 는 전체 상태 대비다 — tpl.compare(행 짝 비교)와 스키마 모양이 다르다."""
    ba = load_schema("l-ba")
    side = ba["$defs"]["side"]
    assert set(side["required"]) == {"label", "title", "items", "summary"}
    assert side["properties"]["items"]["minItems"] == 3
    assert side["properties"]["items"]["maxItems"] == 5
    cmp_schema = json.loads((TPL_DIR / "compare" / "schema.json").read_text(encoding="utf-8"))
    assert "rows" in cmp_schema["properties"], "compare 는 행 짝(rows) 구조가 정본이다"
    assert "rows" not in ba["properties"], "l-ba 에 rows 가 생기면 compare 와 겹친다"


def test_mix_takes_table_and_series_together():
    """structured table 과 series 를 동시에 받는 유일한 템플릿."""
    mix = load_schema("l-mix")
    assert set(mix["required"]) >= {"table", "chart"}
    assert mix["properties"]["table"]["properties"]["columns"]["maxItems"] == 4
    assert mix["properties"]["table"]["properties"]["rows"]["maxItems"] == 5
    assert mix["properties"]["chart"]["properties"]["bars"]["maxItems"] == 4
    assert mix["properties"]["chart"]["properties"]["bars"]["items"]["properties"]["value"][
        "minimum"
    ] == 0, "막대 값은 0 기준선 고정 (음수 금지)"
    # 요약은 수치 3개 **또는** 한 줄 결론 — 둘 다는 겹쳐 그려지므로 배타
    both = json.loads(json.dumps(load_fixture("l-mix", "typical")))
    both["lead"] = "요약 수치와 결론을 동시에 넣으면 겹친다"
    assert schema_errors(mix, both), "stats 와 lead 동시 지정이 통과되면 안 된다"
    neither = json.loads(json.dumps(load_fixture("l-mix", "typical")))
    neither.pop("stats")
    assert schema_errors(mix, neither), "요약이 아예 없으면 상단 40% 가 빈다"


# ── 실물 structured payload 수용 — report_sample 로 증명 ────────────────────


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


def test_real_progress_series_fits_l_kpi():
    """structured series(progress_bar 7계열)를 KPI 6타일 + '외 1개' 로 그대로 받는다."""
    payloads = _structured_payloads()
    assert payloads.get("progress_bar"), "report_sample 에 progress_bar 가 없다"
    items = payloads["progress_bar"][0]["series"]
    assert len(items) == 7, "실물 규모 전제(7계열)가 변했다"
    cap = load_schema("l-kpi")["properties"]["metrics"]["maxItems"]
    data = {
        "kicker": "구현 현황",
        "title": (payloads["progress_bar"][0].get("caption") or "진척")[:26],
        # 라벨 축약은 심의 몫(§8 trim 정책) — 여기서는 값·용량 수용만 실물로 증명한다
        "metrics": [
            {
                "label": f"Phase {i}",
                "value": f"{it['value']:g}",
                "unit": it.get("unit") or "%",
            }
            for i, it in enumerate(items[:cap])
        ],
        "omitted": len(items) - cap,
    }
    msgs = schema_errors(load_schema("l-kpi"), data)
    assert not msgs, f"실물 진행률이 l-kpi 스키마에 안 들어간다: {msgs}"
    assert data["omitted"] == 1


def test_real_progress_series_fits_l_quad_as_quadrant():
    """structured series 의 값을 y(0~1)로 정규화해 4분면 좌표로 받는다 (quadrant 모드)."""
    payloads = _structured_payloads()
    items = payloads["progress_bar"][0]["series"]
    cap = load_schema("l-quad")["properties"]["items"]["maxItems"]
    assert len(items) <= cap, f"실물 {len(items)}계열이 항목 용량 {cap} 을 넘는다"
    data = {
        "kicker": "우선순위",
        "title": "난이도 × 진척 사분면",
        "xAxis": {"name": "구현 난이도", "low": "낮음", "high": "높음"},
        "yAxis": {"name": "진척률", "low": "0%", "high": "100%"},
        "quadrants": {"tl": "이미 끝냄", "tr": "핵심 성과", "bl": "빠른 승리", "br": "다음 고비"},
        "items": [
            {
                "label": f"Phase {i}",
                # 세로는 실측 진척률의 정규화(값/최대), 가로는 심의가 매기는 난이도 자리
                "y": round(it["value"] / (it.get("max") or 100.0), 3),
                "x": round(0.1 + i * 0.12, 3),
            }
            for i, it in enumerate(items)
        ],
    }
    msgs = schema_errors(load_schema("l-quad"), data)
    assert not msgs, f"실물 series 가 l-quad 스키마에 안 들어간다: {msgs}"
    ys = [it["y"] for it in data["items"]]
    assert max(ys) == 1.0 and min(ys) == 0.0, "정규화가 0~1 을 채우지 못했다"


def test_real_comparison_and_series_fit_l_mix_together():
    """structured table(comparison 4열×5행)과 structured series 를 한 씬에 동시에 받는다."""
    payloads = _structured_payloads()
    assert payloads.get("comparison"), "report_sample 에 comparison 이 없다"
    tbl = payloads["comparison"][0]
    assert len(tbl["columns"]) == 4 and len(tbl["rows"]) == 5, "실물 규모 전제(4열×5행)가 변했다"
    series = payloads["progress_bar"][0]["series"]
    schema = load_schema("l-mix")
    key0 = tbl["columns"][0]["key"]
    data = {
        "kicker": "구조 비교",
        "title": (tbl.get("caption") or "비교")[:26],
        "stats": [
            {"value": str(len(tbl["rows"])), "unit": "행", "label": "비교 항목"},
            {"value": str(len(tbl["columns"]) - 1), "unit": "안", "label": "비교 대상"},
        ],
        "table": {
            # 열 이름·행 라벨 축약은 심의 몫 — 여기서는 열·행 개수 수용을 실물로 증명한다
            "columns": [{"label": c["label"][:10]} for c in tbl["columns"]],
            "rows": [
                {
                    "label": r[key0][:13],
                    "cells": [{"v": str(r[c["key"]])[:6]} for c in tbl["columns"][1:]],
                }
                for r in tbl["rows"]
            ],
        },
        "chart": {
            "axisMax": 100,
            "bars": [
                {
                    "label": f"Phase {i}",
                    "value": it["value"],
                    "display": f"{it['value']:g}%",
                }
                for i, it in enumerate(series[:4])
            ],
        },
    }
    msgs = schema_errors(schema, data)
    assert not msgs, f"실물 table+series 동시 수용 실패: {msgs}"


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
def test_max_fixture_fits_caption_budget(name):
    """상한 픽스처도 nat 안에서 읽힌다 — maxLength 합이 낭독 예산을 넘지 않는다."""
    from wdqa.gate2_length import collect_read_chars

    chars = collect_read_chars(load_schema(name), load_fixture(name, "max"))
    nat = load_module(name)["nat_default"]
    assert chars / CAPTION_CPS <= nat, (
        f"{name}: max x-read {chars}자 ÷ {CAPTION_CPS} = {chars / CAPTION_CPS:.1f}s > nat {nat}s"
    )
