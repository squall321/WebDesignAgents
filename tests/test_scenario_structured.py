# wdpipeline.scenario 구조 소비 테스트 — fragment["structured"] → 씬 슬롯 매핑·용량 초과 대응·slot_fit_report
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file
from wdpipeline.scenario import (
    TEMPLATE_ORDER,
    assemble_demo_scenario,
    slot_fit_report,
    validate_scenario,
)
from wdpipeline.scenario import (
    _category_column,
    _extreme_indices,
    _group_rows,
    _level_indices,
    _span_indices,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
MODULES = REPO_ROOT / "modules"


@pytest.fixture(scope="module")
def sample() -> tuple[dict, list[dict]]:
    norm = ingest_report_file(SAMPLE)
    return norm, fragmentize(norm)


def _norm_of(blocks: list[dict], *, title: str = "합성 보고서") -> dict:
    """블록 목록만으로 최소 norm 을 만든다 (ingest 를 거치지 않는 단위 픽스처)."""
    return {
        "doc_id": "synth001",
        "title": title,
        "report_date": "2026-07-27",
        "tags": ["합성", "검증"],
        "search_text": title,
        "pages": [{"name": "1. 본문", "blocks": blocks}],
    }


# ── 대표 선별 · 그룹 요약 유틸 (용량 초과 대응의 근간) ───────────────────


def test_span_indices_keeps_first_and_last():
    """순서군 표본은 첫·끝을 반드시 남긴다 — 앞 N개 절단은 절차의 결말을 지운다."""
    idx = _span_indices(10, 4)
    assert idx[0] == 0 and idx[-1] == 9
    assert len(idx) == 4 and idx == sorted(idx)
    assert _span_indices(6, 6) == list(range(6))     # 용량 이내면 손대지 않는다
    assert _span_indices(6, None) == list(range(6))
    assert _span_indices(3, 1) == [0]


def test_extreme_indices_keeps_min_max_median():
    """수치군 대표는 최대·최소·중앙값 — 앞 N개를 자르면 최댓값이 통째로 빠질 수 있다."""
    values = [100.0, 100.0, 100.0, 70.0, 30.0, 20.0, 0.0]
    idx = _extreme_indices(values, 3)
    picked = sorted(values[i] for i in idx)
    assert picked == [0.0, 70.0, 100.0]
    assert idx == sorted(idx)                        # 원 순서(= 서사 순서) 유지
    assert _extreme_indices(values, 99) == list(range(7))


def test_level_indices_prefers_shallow_nodes():
    nodes = [{"level": 2}, {"level": 0}, {"level": 1}, {"level": 2}]
    assert _level_indices(nodes, 2) == [1, 2]        # 루트 → 1단 순으로 남는다


def test_category_column_is_first_column_only():
    """분류 축은 첫 열만 본다 — '종류가 가장 적은 열'을 고르면 엉뚱한 축이 잡힌다."""
    good = {
        "columns": [{"key": "cat", "label": "분류"}, {"key": "name", "label": "이름"}],
        "rows": [{"cat": "A", "name": f"n{i}"} for i in range(3)]
        + [{"cat": "B", "name": "n3"}],
    }
    assert _category_column(good)["key"] == "cat"
    assert dict(_group_rows(good)) == {"A": 3, "B": 1}

    raci = {  # 첫 열(작업)이 전부 고유 → 축 없음. 역할 열로 요약하지 않는다.
        "columns": [{"key": "task"}, {"key": "owner"}],
        "rows": [{"task": f"t{i}", "owner": "R"} for i in range(4)],
    }
    assert _category_column(raci) is None
    assert _group_rows(raci) == []


# ── §3 정확 대응 매핑 (실물 report_sample.json) ─────────────────────────


def test_flowchart_nodes_reach_process_steps(sample):
    """flowchart 6단계가 process.steps 에 실제 노드 라벨로 들어간다."""
    norm, frags = sample
    payload = next(f["structured"] for f in frags
                   if f.get("structured", {}).get("shape") == "flow")
    labels = [n["label"] for n in payload["nodes"]]
    assert len(labels) == 6

    doc = assemble_demo_scenario(norm, frags)
    steps = doc.content["process"]["steps"]
    assert len(steps) == 6
    assert [s["n"] for s in steps] == ["01", "02", "03", "04", "05", "06"]
    for step, label in zip(steps, labels):
        head = step["name"].rstrip("…")
        assert label.startswith(head), f"{step['name']!r} 이 노드 라벨 {label!r} 에서 오지 않았다"
    # description → desc
    notes = [n.get("note") for n in payload["nodes"]]
    assert steps[0]["desc"].rstrip("…") in notes[0]


def test_tree_nodes_reach_concept_nodes(sample):
    """tree(graph) 가 concept.nodes 로 — 루트가 첫 노드, 얕은 레벨 우선."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags)
    nodes = doc.content["concept"]["nodes"]
    payload = next(f["structured"] for f in frags
                   if f.get("structured", {}).get("shape") == "tree")
    labels = [n["label"] for n in payload["nodes"]]
    assert nodes[0]["name"].rstrip("…") == labels[0][: len(nodes[0]["name"].rstrip("…"))]
    assert len(nodes) == 8 <= len(labels)
    # 페이지 이름 폴백(기존 경로)이 아니라 트리 노드에서 왔는지 — 두 집합은 겹치지 않는다
    from wdpipeline.scenario import _concept_nodes

    fallback = {n["name"] for n in _concept_nodes(norm)}
    assert not ({n["name"] for n in nodes} & fallback)
    assert {n["name"].rstrip("…") for n in nodes} <= {
        lb[: len(lb)] for lb in labels
    } | {lb[:i] for lb in labels for i in range(1, len(lb) + 1)}


def test_progress_bar_reaches_dataviz_bars(sample):
    """progress_bar 7계열이 dataviz.bars 에 수치로 들어간다 (강조 1개·0 기준선·축 상한)."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    assert [s.tpl.split("@")[0] for s in doc.scenes][5] == "dataviz"
    dv = doc.content["proof"]                      # 역할 키는 proof, 템플릿이 dataviz
    values = [b["value"] for b in dv["bars"]]
    assert values == [100.0, 70.0, 30.0, 20.0, 0.0]     # 극단+중앙값, 원 순서 유지
    assert sum(1 for b in dv["bars"] if b.get("emphasis")) == 1
    assert all(b["value"] >= 0 for b in dv["bars"])
    assert dv["axisMax"] == 100.0 and dv["unit"] == "%"
    assert dv["headline"]["value"] == "100%"
    assert "외 2계열" in dv["insights"][0]["text"]        # 생략 명시
    assert validate_scenario(doc, modules_root=MODULES) == []


def test_comparison_reaches_compare_panels(sample):
    """comparison 2안(table) → tpl.compare — cases 가 a/b 패널, rows 가 행 짝."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    cmp_data = doc.content["differentiator"]
    payload = next(f["structured"] for f in frags
                   if f.get("widget") == "comparison"
                   and len(f["structured"]["columns"]) == 3)
    cols = payload["columns"]
    assert cmp_data["panels"]["a"]["label"].rstrip("…") in cols[1]["label"]
    assert cmp_data["panels"]["b"]["label"].rstrip("…") in cols[2]["label"]
    assert 2 <= len(cmp_data["rows"]) <= 4
    first = payload["rows"][0]
    assert cmp_data["rows"][0]["a"].rstrip("…") in first[cols[1]["key"]]
    assert cmp_data["rows"][0]["b"].rstrip("…") in first[cols[2]["key"]]


def test_key_value_reaches_proof_cases(sample):
    """key_value(pairs) → proof.cases 근거 카드 (closing.stats 3칸을 넘는 스펙 목록)."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags)
    cases = doc.content["proof"]["cases"]
    pairs = next(f["structured"] for f in frags if f.get("widget") == "key_value")
    label, value = pairs["pairs"][0]["label"], pairs["pairs"][0]["value"]
    assert cases[0]["desc"].startswith(f"{label}: {value[:10]}")
    assert "외 7쌍" in cases[0]["badge"]                  # 9쌍 중 2쌍 → 생략 명시


def test_milestone_reaches_timeline_milestones():
    """milestone(timeline) → tpl.timeline.milestones — status 3태 그대로, current 정확히 1개."""
    blocks = [
        {"id": "b1", "type": "heading", "content": {"text": "합성 로드맵"}},
        {
            "id": "b2",
            "type": "milestone",
            "section": "schedule",
            "props": {"label": "로드맵", "start_date": "2026-01-01", "end_date": "2026-12-31"},
            "content": {
                "items": [
                    {"date": "2026-02", "label": "착수", "status": "done"},
                    {"date": "2026-06", "label": "중간 검증", "status": "current",
                     "note": "필드 테스트"},
                    {"date": "2026-11", "label": "양산", "status": "planned"},
                ]
            },
        },
    ]
    norm = _norm_of(blocks)
    doc = assemble_demo_scenario(norm, fragmentize(norm), structured_templates=True)
    shorts = [s.tpl.split("@")[0] for s in doc.scenes]
    assert shorts[3] == "timeline"                      # process 역할이 timeline 으로 대체
    ms = doc.content["process"]["milestones"]
    assert [m["name"] for m in ms] == ["착수", "중간 검증", "양산"]
    assert [m["status"] for m in ms] == ["done", "current", "planned"]
    assert [m["date"] for m in ms] == ["2026-02", "2026-06", "2026-11"]
    assert ms[1]["desc"] == "필드 테스트"
    assert "2026-01-01 ~ 2026-12-31" in doc.content["process"]["footnote"]["pre"]
    assert validate_scenario(doc, modules_root=MODULES) == []


def test_timeline_forces_exactly_one_current():
    """원문에 current 가 없어도 스키마(contains 1개)를 만족시켜야 한다."""
    blocks = [
        {"id": "b1", "type": "heading", "content": {"text": "완료된 일정"}},
        {
            "id": "b2",
            "type": "milestone",
            "content": {
                "items": [
                    {"date": f"2026-0{i}", "label": f"단계 {i}", "status": "done"}
                    for i in range(1, 5)
                ]
            },
        },
    ]
    norm = _norm_of(blocks)
    doc = assemble_demo_scenario(norm, fragmentize(norm), structured_templates=True)
    ms = doc.content["process"]["milestones"]
    assert sum(1 for m in ms if m["status"] == "current") == 1
    assert validate_scenario(doc, modules_root=MODULES) == []


# ── 용량 초과 대응 (§8) ─────────────────────────────────────────────────


def test_group_summary_covers_every_row(sample):
    """33행 표는 앞 4행 절단이 아니라 카테고리 그룹 집계로 압축된다 — 합이 33이어야 한다."""
    norm, frags = sample
    payload = next(f["structured"] for f in frags
                   if f.get("widget") == "table" and len(f["structured"]["rows"]) > 10)
    groups = _group_rows(payload)
    assert sum(n for _, n in groups) == len(payload["rows"]) == 33

    doc = assemble_demo_scenario(norm, frags)
    card = next(c for c in doc.content["proof"]["cases"] if c["rpt"] == "표 집계")
    assert card["meta"] == "3열×33행"
    total = sum(int(seg.rsplit(" ", 1)[1]) for seg in card["desc"].split(" · "))
    assert total == 33, f"그룹 집계가 전 행을 대표하지 않는다: {card['desc']}"


def test_omission_is_stated_never_silent(sample):
    """생략이 있으면 화면 어딘가에 '외 N' 이 남는다 — 무언의 절단 금지."""
    norm, frags = sample
    report = slot_fit_report(norm, frags)
    doc = assemble_demo_scenario(norm, frags)
    blob = json.dumps(doc.model_dump(), ensure_ascii=False)
    for row in report["rows"]:
        if row["placed"] and row["omitted"] > 0:
            assert f"외 {row['omitted']}" in blob, (
                f"{row['widget']} 가 {row['omitted']}건을 말없이 잘랐다"
            )


def test_labels_are_truncated_on_word_boundary(sample):
    """라벨 축약은 어절 경계에서 — 원문은 structured 에 그대로 남는다."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags)
    trimmed = [s["name"] for s in doc.content["process"]["steps"] if s["name"].endswith("…")]
    assert trimmed, "실물 흐름도 라벨은 12자 슬롯을 넘는다 (§8 trim)"
    payload = next(f["structured"] for f in frags
                   if f.get("structured", {}).get("shape") == "flow")
    originals = " ".join(n["label"] for n in payload["nodes"])
    for name in trimmed:
        assert not name.rstrip("…").endswith(" ")     # 꼬리 공백 없이 어절에서 끊는다
        assert name.rstrip("…") in originals          # 원문 라벨의 접두


# ── slot_fit_report ─────────────────────────────────────────────────────


def test_slot_fit_report_counts_every_structured_fragment(sample):
    norm, frags = sample
    report = slot_fit_report(norm, frags)
    assert report["structured_blocks"] == sum(1 for f in frags if "structured" in f) == 12
    assert sum(report["tally"].values()) == 12
    assert set(report["tally"]) == {"ok", "trim", "summarized", "split", "none"}
    assert set(r["fit"] for r in report["rows"]) <= set(report["tally"])
    # §8 기존 기준(ok+trim)은 25% 그대로 — 개선은 '요약 수용'을 새로 세는 데서 온다
    assert report["strict_reach_pct"] == 25.0
    assert report["reach_pct"] == 75.0
    assert report["placed_pct"] > 25.0


def test_slot_fit_report_marks_placement_and_competition(sample):
    """같은 슬롯을 여러 payload 가 다투면 실제로 실리는 건 하나다."""
    norm, frags = sample
    report = slot_fit_report(norm, frags)
    flows = [r for r in report["rows"] if r["widget"] == "flowchart"]
    assert len(flows) == 3
    assert sum(1 for r in flows if r["placed"]) == 1
    assert all(r["slot"] == "process.steps" for r in flows)
    for r in report["rows"]:
        assert (r["placed_slot"] is not None) == r["placed"]


def test_slot_fit_report_split_hints(sample):
    """한 슬롯에 못 담으면 씬 분할 씬 수를 제안한다."""
    norm, frags = sample
    report = slot_fit_report(norm, frags)
    assert report["split_hints"], "용량의 2배를 넘는 payload 가 실물에 있다"
    for hint in report["split_hints"]:
        assert hint["scenes"] >= 2 and hint["frag_id"] and hint["detail"]
    pb = next(r for r in report["rows"] if r["widget"] == "progress_bar")
    assert pb["split_hint"]["scenes"] == 3          # 7계열 / 3칸


def test_alt_templates_change_routing(sample):
    """structured_templates 는 라우팅만 바꾼다 — 두 모드 모두 검증 0오류."""
    norm, frags = sample
    default = slot_fit_report(norm, frags)
    alt = slot_fit_report(norm, frags, structured_templates=True)
    assert "dataviz" not in default["templates"] and "dataviz" in alt["templates"]
    assert "compare" in alt["templates"]
    pb_default = next(r for r in default["rows"] if r["widget"] == "progress_bar")
    pb_alt = next(r for r in alt["rows"] if r["widget"] == "progress_bar")
    assert pb_default["slot"] == "closing.stats" and pb_alt["slot"] == "dataviz.bars"
    for flag in (False, True):
        doc = assemble_demo_scenario(norm, frags, structured_templates=flag)
        assert validate_scenario(doc, modules_root=MODULES) == []


# ── 폴백 무손상 ─────────────────────────────────────────────────────────


def test_default_keeps_seven_template_skeleton(sample):
    """기본 조립은 기존 7종 골격 그대로 — 대체 템플릿은 명시적 선택으로만 켠다."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags)
    assert [s.tpl.split("@")[0] for s in doc.scenes] == TEMPLATE_ORDER


def test_text_only_report_falls_back_to_text_path():
    """structured 가 하나도 없어도 조립·검증이 통과한다 (기존 텍스트 경로)."""
    blocks = [
        {"id": "h", "type": "heading", "section": "purpose", "content": {"text": "텍스트 보고서"}},
        {"id": "r", "type": "rich_text", "section": "background",
         "content": {"markdown": "배경 설명이 이어진다. 근거는 원문 참조."}},
        {"id": "b", "type": "bulleted_list", "section": "analysis",
         "content": {"items": ["첫째 항목", "둘째 항목", "셋째 항목"]}},
    ]
    norm = _norm_of(blocks, title="텍스트 전용 보고서")
    frags = fragmentize(norm)
    assert not any("structured" in f for f in frags)
    doc = assemble_demo_scenario(norm, frags)
    assert [s.tpl.split("@")[0] for s in doc.scenes] == TEMPLATE_ORDER
    assert validate_scenario(doc, modules_root=MODULES) == []
    report = slot_fit_report(norm, frags)
    assert report["structured_blocks"] == 0 and report["reach_pct"] == 0.0


def test_empty_report_still_assembles():
    norm = _norm_of([], title="빈 보고서")
    doc = assemble_demo_scenario(norm, [])
    assert validate_scenario(doc, modules_root=MODULES) == []
