# 커버리지 1순위 4종(tpl.c-ratio·c-trend·c-branch·c-grid) 구조 매핑 배선 검증 — 판별 규칙·빌더 산출·옵트인 경계
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file
from wdpipeline.scenario import (
    _branch_graph,
    _candidates,
    _grid_cards,
    _ratio_series,
    _trend_series,
    assemble_demo_scenario,
    slot_fit_report,
    validate_scenario,
)
from wdpipeline.widgets import extract_structured

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
MODULES = REPO_ROOT / "modules"

# 4종 옵트인 풀 — formats/wide-16x9/format.yaml 에 이 4줄을 열면 기본 경로에도 붙는다.
TIER1_POOL = {
    # 분기 흐름도는 '절차' 역할의 대체다 — tpl.concept(방사형 개념도)와는 목적이 다르다.
    "process": ["tpl.process", "tpl.c-branch"],
    "differentiator": ["tpl.differentiator", "tpl.c-ratio", "tpl.compare"],
    "proof": ["tpl.proof", "tpl.c-trend", "tpl.c-grid"],
}


@pytest.fixture()
def merged_modules_root(tmp_path: Path, monkeypatch) -> Path:
    """실제 registry.yaml 을 그대로 쓰는 모듈 루트.

    (구현 초기에는 modules/_pending 조각을 합쳐 '병합 후'를 재현했으나, 오케스트레이터
     병합이 끝나 registry.yaml 자체가 그 상태다 — 조각은 제거됐다.)
    """
    reg = yaml.safe_load((MODULES / "registry.yaml").read_text(encoding="utf-8"))
    ids = {m["id"] for m in reg["modules"]}
    for tid in ("tpl.c-ratio", "tpl.c-trend", "tpl.c-branch", "tpl.c-grid"):
        assert tid in ids, f"{tid} 이 registry.yaml 에 없다 — 병합 누락"
    root = tmp_path / "modules"
    root.mkdir()
    (root / "registry.yaml").write_text(yaml.safe_dump(reg, allow_unicode=True), encoding="utf-8")
    (root / "scene-templates").symlink_to(MODULES / "scene-templates")
    monkeypatch.setenv("WDA_MODULES_ROOT", str(root))
    return root


@pytest.fixture()
def tier1_formats_root(tmp_path: Path, monkeypatch, merged_modules_root: Path) -> Path:
    spec = yaml.safe_load(
        (REPO_ROOT / "formats" / "wide-16x9" / "format.yaml").read_text(encoding="utf-8")
    )
    spec["template_pool"].update(TIER1_POOL)
    out = tmp_path / "formats" / "wide-16x9"
    out.mkdir(parents=True)
    (out / "format.yaml").write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    monkeypatch.setenv("WDA_FORMATS_ROOT", str(tmp_path / "formats"))
    return tmp_path / "formats"


def _schema(short: str) -> dict:
    return json.loads(
        (MODULES / "scene-templates" / short / "schema.json").read_text(encoding="utf-8")
    )


def _norm(blocks: list[dict], **extra) -> dict:
    return {
        "doc_id": "tier1",
        "title": "커버리지 1순위 매핑 검증 보고서",
        "report_date": "2026-07-29",
        "tags": ["매핑", "검증"],
        "search_text": "커버리지 1순위 매핑 검증",
        "pages": [{"name": "1. 본문", "blocks": blocks}],
        **extra,
    }


# ── 블록 픽스처 (ReportArchive 실 스키마 형태) ──────────────────────────


def _pie_block() -> dict:
    return {
        "id": "pie1", "type": "pie", "section": None,
        "props": {"label": "군별 구성", "unit": "종"},
        "content": {"rows": [
            {"label": "수치군", "value": 14}, {"label": "미디어군", "value": 6},
            {"label": "표군", "value": 5}, {"label": "다이어그램군", "value": 5},
            {"label": "텍스트군", "value": 5},
        ]},
    }


def _line_chart_block() -> dict:
    return {
        "id": "ch1", "type": "chart", "section": None,
        "props": {
            "label": "월별 게시 추세", "chart_type": "line",
            "columns": [{"key": "m", "label": "월"},
                        {"key": "v", "label": "게시", "type": "number"}],
            "x_column_key": "m",
        },
        "content": {"rows": [{"m": f"26.0{i}", "v": 40 + 8 * i} for i in range(1, 7)]},
    }


def _branch_flow_block() -> dict:
    """분기 있는 절차 — tree 위젯의 parent 행으로 판단·병렬을 만든다."""
    return {
        "id": "tr1", "type": "tree", "section": None,
        "props": {"label": "승인 절차"},
        "content": {"rows": [
            {"label": "접수"},
            {"label": "형식 검토", "parent": "접수"},
            {"label": "승인", "parent": "형식 검토", "subtitle": "요건 충족"},
            {"label": "반려", "parent": "형식 검토", "subtitle": "보완 필요"},
            {"label": "게시", "parent": "승인"},
        ]},
    }


def _keyvalue_block(n: int = 9) -> dict:
    items = [{"key": f"k{i}", "label": f"항목 {i}"} for i in range(1, n + 1)]
    content = {"items": items}
    for i in range(1, n + 1):
        content[f"k{i}"] = f"값 {i}"
    return {"id": "kv1", "type": "key_value", "section": None,
            "props": {"label": "사양 목록"}, "content": content}


def _two_col_table_block(rows: int = 8) -> dict:
    return {
        "id": "tb1", "type": "table", "section": None,
        "props": {"label": "용어 정의",
                  "columns": [{"key": "t", "label": "용어"}, {"key": "d", "label": "정의"}]},
        "content": {"rows": [{"t": f"용어 {i + 1}", "d": f"정의 문장 {i + 1}"}
                             for i in range(rows)]},
    }


def _payload(block: dict) -> dict:
    p = extract_structured(block)
    assert p is not None, f"{block['type']} payload 추출 실패"
    return p


# ── ① 판별 규칙 — 어떤 신호로 무엇이 갈리는가 ────────────────────────────


def test_ratio_signal_is_chart_type_or_sum_100():
    """비율 판정 신호 두 갈래 — chart_type 이 비율 계열이거나 합이 100 근사."""
    assert _ratio_series(_payload(_pie_block())) is not None       # chart_type=pie
    pct = {"kind": "series", "chart_type": "bar",
           "series": [{"label": f"항목{i}", "value": v}
                      for i, v in enumerate([40.0, 30.0, 20.0, 10.0])]}
    assert _ratio_series(pct) is not None                          # 합 100.0
    off = dict(pct, series=[{"label": "가", "value": 40.0}, {"label": "나", "value": 30.0},
                            {"label": "다", "value": 20.0}, {"label": "라", "value": 20.0}])
    assert _ratio_series(off) is None                              # 합 110 — 구성비가 아니다


def test_trend_signal_is_chart_type_or_time_labels():
    """추세 판정 신호 — chart_type line/area 이거나 항목 라벨 2/3 이상이 시점 표기."""
    payload = _payload(_line_chart_block())
    trend = _trend_series(payload)
    assert trend is not None
    lines, points, _ = trend
    assert points == ["26.01", "26.02", "26.03", "26.04", "26.05", "26.06"]
    assert lines == [""]                                           # 단일 계열
    bar_time = {"kind": "series", "chart_type": "bar",
                "series": [{"label": lb, "value": float(i)}
                           for i, lb in enumerate(["1월", "2월", "3월", "4월", "5월"])]}
    assert _trend_series(bar_time) is not None                     # 시점 라벨 신호만으로 성립
    named = {"kind": "series", "chart_type": "bar",
             "series": [{"label": lb, "value": 1.0}
                        for lb in ["서울", "부산", "대구", "광주", "대전"]]}
    assert _trend_series(named) is None                            # 지명 축은 추세가 아니다


def test_ratio_and_trend_are_mutually_exclusive():
    """구성비와 시계열이 동시에 서지 않는다 — 시점 축이면 추세가 먼저다."""
    monthly_pct = {"kind": "series", "chart_type": "pie",
                   "series": [{"label": lb, "value": v} for lb, v in
                              [("26.01", 25.0), ("26.02", 25.0),
                               ("26.03", 25.0), ("26.04", 25.0)]]}
    assert _ratio_series(monthly_pct) is None                      # 시점 라벨 → 구성비 아님
    assert _trend_series(monthly_pct) is not None
    assert _trend_series(_payload(_pie_block())) is None           # 구성비 → 추세 아님


def test_branch_signal_is_edge_label_or_multiple_children():
    """분기 판정 — 한 부모의 자식이 2개 이상(또는 엣지 라벨). 선형 절차는 부적격."""
    branch = _branch_graph(_payload(_branch_flow_block()))
    assert branch is not None
    nodes, edges = branch
    assert len(nodes) == 5 and len(edges) == 4
    out_deg: dict[str, int] = {}
    for e in edges:
        out_deg[e["from"]] = out_deg.get(e["from"], 0) + 1
    assert max(out_deg.values()) >= 2                              # 판단 노드가 있다
    linear = {"kind": "graph", "shape": "flow",
              "nodes": [{"id": f"n{i}", "label": f"단계{i}", "level": i} for i in range(4)],
              "edges": [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(3)]}
    assert _branch_graph(linear) is None                           # 선형 → tpl.process 몫


def test_branch_rejects_more_than_four_levels():
    """레벨 5단 이상은 부적격 — 축소·폰트 감소 금지 계약(c-branch level 0~3)."""
    deep = {"kind": "graph", "shape": "tree",
            "nodes": [{"id": f"n{i}", "label": f"단계{i}", "level": i} for i in range(6)]
                     + [{"id": "b", "label": "분기", "level": 1}],
            "edges": [{"from": f"n{i}", "to": f"n{i + 1}"} for i in range(5)]
                     + [{"from": "n0", "to": "b"}]}
    assert _branch_graph(deep) is None


def test_grid_signal_is_six_or_more_items():
    """카드 그리드 — 키값 6쌍 이상 또는 2열 표 6행 이상. 3열 이상 표는 d-matrix 몫."""
    assert len(_grid_cards(_payload(_keyvalue_block(9))) or []) == 9
    assert len(_grid_cards(_payload(_two_col_table_block(8))) or []) == 8
    assert _grid_cards(_payload(_keyvalue_block(4))) is None        # 5쌍 이하는 기존 경로
    three_col = {"kind": "table",
                 "columns": [{"key": "a", "label": "A"}, {"key": "b", "label": "B"},
                             {"key": "c", "label": "C"}],
                 "rows": [{"a": str(i), "b": "x", "c": "y"} for i in range(8)]}
    assert _grid_cards(three_col) is None                          # 격자는 d-matrix 정본


# ── ② 후보 색인 — _candidates 가 신규 키를 채운다 ────────────────────────


def test_candidates_index_new_keys():
    norm = _norm([_pie_block(), _line_chart_block(),
                  _branch_flow_block(), _keyvalue_block(9)])
    cand = _candidates(fragmentize(norm), norm)
    assert cand["ratio"] is not None and cand["ratio"][0]["widget"] == "pie"
    assert cand["trend"] is not None and cand["trend"][0]["widget"] == "chart"
    assert cand["branch"] is not None and cand["branch"][0]["widget"] == "tree"
    assert cand["grid"] is not None and cand["grid"][0]["widget"] == "key_value"


# ── ③ 조립 — 옵트인 풀에서 신규 4종이 자리를 가져가고 스키마를 통과한다 ──


@pytest.mark.parametrize(
    "block_fn,short,role",
    [
        (_pie_block, "c-ratio", "differentiator"),
        (_line_chart_block, "c-trend", "proof"),
        (_branch_flow_block, "c-branch", "process"),
        (_keyvalue_block, "c-grid", "proof"),
    ],
)
def test_new_templates_take_their_role(tier1_formats_root, merged_modules_root,
                                       block_fn, short, role):
    norm = _norm([block_fn()])
    doc = assemble_demo_scenario(norm, fragmentize(norm), structured_templates=True)
    errs = validate_scenario(doc, modules_root=merged_modules_root)
    assert errs == [], f"{short} 시나리오 검증 실패: {errs}"
    scene = next((s for s in doc.scenes if s.tpl.startswith(f"{short}@")), None)
    assert scene is not None, f"{short} 가 씬에 없다 — tpl {[s.tpl for s in doc.scenes]}"
    assert scene.data_ref == f"content.{role}"
    errors = list(Draft202012Validator(_schema(short)).iter_errors(doc.content[role]))
    assert not errors, [e.message for e in errors]


def test_c_ratio_never_truncates_the_whole(tier1_formats_root):
    """8항목 → 상한 7. 잘라 버리지 않고 total 로 넘겨 '기타(미표기)'로 편입한다."""
    block = _pie_block()
    block["content"]["rows"] = [{"label": f"군 {i}", "value": float(10 * (i + 1))}
                                for i in range(8)]
    norm = _norm([block])
    doc = assemble_demo_scenario(norm, fragmentize(norm), structured_templates=True)
    data = doc.content["differentiator"]
    assert len(data["series"]) == 6                      # cap 7 - 1 (기타 자리 확보)
    assert data["total"]["value"] == pytest.approx(sum(10.0 * (i + 1) for i in range(8)))
    listed = sum(x["value"] for x in data["series"])
    assert data["total"]["value"] > listed                # 차액이 기타로 자동 편입된다
    assert "외 2항목은 기타로 편입" in data["footnote"]["text"]


def test_c_ratio_always_fills_display_within_six_chars(tier1_formats_root):
    """심의 F1 — display 를 생략하면 렌더 fallback 이 값존을 넘는다. 조립기는 항상 채운다."""
    block = _pie_block()
    block["props"]["unit"] = "억원"
    block["content"]["rows"] = [{"label": f"군 {i}", "value": float(v)}
                                for i, v in enumerate([1234567, 890123, 456789, 123456])]
    norm = _norm([block])
    doc = assemble_demo_scenario(norm, fragmentize(norm), structured_templates=True)
    for item in doc.content["differentiator"]["series"]:
        assert item.get("display"), "display 미기재 — 렌더 fallback 경로가 열린다"
        assert len(item["display"]) <= 6


def test_c_trend_never_raises_axis_min_above_data(tier1_formats_root):
    """심의 F1 — axis.min 이 데이터 최솟값 위면 라인이 기준선 아래로 잘린다. 싣지 않는다."""
    block = _line_chart_block()
    block["props"]["y_min"] = 80          # 데이터 최솟값 48 보다 위
    norm = _norm([block])
    doc = assemble_demo_scenario(norm, fragmentize(norm), structured_templates=True)
    data = doc.content["proof"]
    lowest = min(v for ln in data["lines"] for v in ln["values"])
    assert data.get("axis", {}).get("min", 0) <= lowest
    assert data["readout"]["delta"]["polarity"] == "neutral"   # 좋고 나쁨은 심의 몫


def test_c_branch_caps_three_nodes_per_level(tier1_formats_root):
    """심의 F2 — 스키마가 레벨당 상한을 강제하지 않는다. 조립기가 레벨당 3개로 막는다."""
    payload = {"kind": "graph", "shape": "tree",
               "nodes": [{"id": "s", "label": "접수", "level": 0}]
                        + [{"id": f"p{i}", "label": f"검토 {i}", "level": 1} for i in range(9)]
                        + [{"id": "e", "label": "종결", "level": 2}],
               "edges": [{"from": "s", "to": f"p{i}"} for i in range(9)]
                        + [{"from": "p0", "to": "e"}]}
    nodes, edges = _branch_graph(payload)
    per_level: dict[int, int] = {}
    for n in nodes:
        per_level[n["level"]] = per_level.get(n["level"], 0) + 1
    assert max(per_level.values()) <= 3
    assert len(nodes) <= 12 and len(edges) >= 2


def test_c_grid_counts_omitted_instead_of_cutting(tier1_formats_root):
    """12쌍 → 카드 9장 + omitted 3. 무언의 절단 금지."""
    norm = _norm([_keyvalue_block(12)])
    doc = assemble_demo_scenario(norm, fragmentize(norm), structured_templates=True)
    data = doc.content["proof"]
    assert len(data["cards"]) == 9
    assert data["omitted"] == 3
    assert data["cards"][0]["label"] == "항목 1" and data["cards"][0]["desc"] == "값 1"


# ── ④ 옵트인 경계 — 현행 포맷 풀에서는 켜지지 않는다 (회귀 안전) ─────────


def test_default_pool_keeps_tier1_off():
    norm = ingest_report_file(SAMPLE)
    frags = fragmentize(norm)
    report = slot_fit_report(norm, frags, structured_templates=True)
    assert not any(t.startswith("c-") for t in report["templates"])
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    assert not any(s.tpl.startswith("c-") for s in doc.scenes)
    assert validate_scenario(doc, modules_root=MODULES) == []


def test_slot_fit_report_counts_tier1_slots(tier1_formats_root):
    """옵트인 풀에서 slot_fit_report 가 신규 슬롯을 none 이 아니라 c-* 로 센다."""
    norm = _norm([_pie_block(), _branch_flow_block(), _keyvalue_block(9)])
    report = slot_fit_report(norm, fragmentize(norm), structured_templates=True)
    rows = {r["widget"]: r for r in report["rows"]}
    assert rows["pie"]["slot"] == "c-ratio.series" and rows["pie"]["fit"] != "none"
    assert rows["tree"]["slot"] == "c-branch.nodes" and rows["tree"]["fit"] != "none"
    assert rows["key_value"]["slot"] == "c-grid.cards"
    assert rows["key_value"]["items"] == 9 and rows["key_value"]["carried"] == 9


def test_real_report_pairs_reach_c_grid(tier1_formats_root):
    """실물 report_sample 의 key_value 다항목이 c-grid 슬롯에 도달한다."""
    norm = ingest_report_file(SAMPLE)
    report = slot_fit_report(norm, fragmentize(norm), structured_templates=True)
    grid_rows = [r for r in report["rows"] if r["slot"] == "c-grid.cards"]
    assert grid_rows, "실물에서 c-grid 슬롯 도달 0건"
    assert all(r["fit"] != "none" for r in grid_rows)
