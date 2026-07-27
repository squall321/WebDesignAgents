# wdpipeline.widgets 테스트 — 군별 구조 추출·미지 타입 안전 처리·fragmentize 하위 호환
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file
from wdpipeline.widgets import (
    GROUP_BY_TYPE,
    STRUCTURED_TYPES,
    collect_media,
    coverage_stats,
    extract_structured,
    structured_summary,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
SYNTHETIC = REPO_ROOT / "data" / "widget_check" / "synthetic_blocks.json"

# ReportArchive registry.WIDGET_REGISTRY 전수 (2026-07 기준 38종)
REGISTRY_TYPES = {
    "heading", "rich_text", "key_value", "bulleted_list", "table", "record",
    "record_table", "image", "attachment", "video", "html_embed", "doc_viewer",
    "chart", "scatter", "scatter3d", "heatmap", "contour", "treemap", "packing",
    "tree", "network", "mind_map", "pie", "waffle", "box", "density", "radar",
    "equation", "milestone", "flowchart", "progress_bar", "raci_matrix",
    "comparison", "cad_3d", "quadrant", "sankey", "fmea", "card",
}


@pytest.fixture(scope="module")
def blocks() -> dict[str, list[dict]]:
    """합성 픽스처를 위젯 타입별로 묶는다 (quadrant 는 plot/bucket 2건)."""
    out: dict[str, list[dict]] = {}
    for b in json.loads(SYNTHETIC.read_text(encoding="utf-8"))["blocks"]:
        out.setdefault(b["type"], []).append(b)
    return out


@pytest.fixture(scope="module")
def norm() -> dict:
    return ingest_report_file(SAMPLE)


# ── 군 분류가 registry 전수를 덮는가 ──────────────────────────────────────


def test_group_table_covers_registry():
    assert set(GROUP_BY_TYPE) == REGISTRY_TYPES, (
        "GROUP_BY_TYPE 가 registry.WIDGET_REGISTRY 38종과 어긋난다 — "
        f"누락={REGISTRY_TYPES - set(GROUP_BY_TYPE)} 초과={set(GROUP_BY_TYPE) - REGISTRY_TYPES}"
    )
    assert len(GROUP_BY_TYPE) == 38


def test_synthetic_fixture_covers_every_type(blocks: dict):
    assert REGISTRY_TYPES <= set(blocks), f"픽스처 미포함 타입: {REGISTRY_TYPES - set(blocks)}"


# ── 군별 최소 1건 ────────────────────────────────────────────────────────


def test_table_group(blocks: dict):
    """표군 — columns 는 props 에, rows 는 content 에 산다 (실물 스키마)."""
    p = extract_structured(blocks["table"][0])
    assert p["kind"] == "table"
    assert [c["key"] for c in p["columns"]] == ["step", "owner", "due", "status"]
    assert [c["label"] for c in p["columns"]] == ["단계", "담당", "기한", "상태"]
    assert len(p["rows"]) == 2
    assert p["rows"][0] == {"step": "요구 정리", "owner": "박", "due": "2026-01-10",
                            "status": "완료"}
    assert structured_summary(p) == "표 4열×2행: 단계/담당/기한/상태"


def test_comparison_cases_become_columns_and_image_cells_become_files(blocks: dict):
    p = extract_structured(blocks["comparison"][0])
    assert [c["key"] for c in p["columns"]] == ["__aspect", "asis", "tobe"]
    assert p["rows"][0] == {"__aspect": "속도", "asis": "3일", "tobe": "4시간"}
    # 이미지 셀은 텍스트(alt)로 낮추고 file_id 는 files 로 승격 — 자산 채널로 흐른다
    assert p["rows"][1]["asis"] == "구 화면"
    assert [f["file_id"] for f in p["files"]] == ["f-old-ui", "f-new-ui"]


def test_raci_and_fmea_and_record_table(blocks: dict):
    raci = extract_structured(blocks["raci_matrix"][0])
    assert [c["key"] for c in raci["columns"]] == ["__task", "pm", "dev"]
    assert raci["rows"][0] == {"__task": "설계 승인", "pm": "R/A", "dev": "C"}

    fmea = extract_structured(blocks["fmea"][0])
    assert len(fmea["columns"]) == 12
    # failure_mode 는 {name, entity_id} 온톨로지 엔티티 — name 으로 평탄화
    assert fmea["rows"][0]["failure_mode"] == "셀 단락"
    assert fmea["rows"][0]["rpn"] == "108"

    rt = extract_structured(blocks["record_table"][0])
    assert [c["key"] for c in rt["columns"]] == ["__name", "tonnage", "line"]
    assert rt["rows"][0]["__name"] == "프레스 1호"


def test_graph_group_flowchart_is_linear(blocks: dict):
    p = extract_structured(blocks["flowchart"][0])
    assert p["kind"] == "graph" and p["shape"] == "flow"
    assert [n["label"] for n in p["nodes"]] == ["수집", "정규화", "배포"]
    assert [n["level"] for n in p["nodes"]] == [0, 1, 2]
    assert p["edges"] == [{"from": "n1", "to": "n2"}, {"from": "n2", "to": "n3"}]
    assert p["nodes"][0]["note"] == "원천 데이터 적재"
    assert structured_summary(p) == "흐름도 3노드 선형"


def test_graph_group_tree_parent_edges_and_levels(blocks: dict):
    p = extract_structured(blocks["tree"][0])
    assert p["shape"] == "tree"
    levels = {n["label"]: n["level"] for n in p["nodes"]}
    assert levels == {"루트": 0, "가지 A": 1, "잎 A1": 2, "가지 B": 1}
    assert {"from": "루트", "to": "가지 A"} in p["edges"]
    assert structured_summary(p) == "트리 4노드 3단"


def test_graph_group_network_and_sankey(blocks: dict):
    net = extract_structured(blocks["network"][0])
    assert net["shape"] == "network"
    assert {"from": "n1", "to": "n2", "label": "도면"} in net["edges"]
    assert net["nodes"][0]["group"] == "내부"

    sk = extract_structured(blocks["sankey"][0])
    assert [n["id"] for n in sk["nodes"]] == ["입고", "가공", "출하"]
    assert sk["edges"][0] == {"from": "입고", "to": "가공", "label": "120톤", "value": 120.0}


def test_series_group_progress_bar(blocks: dict):
    p = extract_structured(blocks["progress_bar"][0])
    assert p["kind"] == "series" and p["chart_type"] == "progress_bar"
    assert p["series"][0] == {"label": "Phase 1", "value": 100.0, "unit": "%", "max": 100.0}
    assert p["axis"] == {"min": 0.0, "max": 100.0}
    assert structured_summary(p) == "진행률 2계열: 100%/60%"


def test_series_group_chart_multi_column(blocks: dict):
    """chart 는 x_column_key 를 제외한 number 열마다 계열이 된다."""
    p = extract_structured(blocks["chart"][0])
    assert len(p["series"]) == 4
    assert p["series"][0] == {"label": "1월", "value": 100.0, "group": "계획"}
    assert p["axis"] == {"min": 0.0, "max": 150.0}


def test_series_group_pie_radar_heatmap_distribution(blocks: dict):
    pie = extract_structured(blocks["pie"][0])
    assert [e["value"] for e in pie["series"]] == [82.0, 13.0, 5.0]
    assert pie["chart_type"] == "doughnut"

    radar = extract_structured(blocks["radar"][0])
    assert len(radar["series"]) == 6  # 2계열 × 3축
    assert radar["series"][0]["label"] == "현행 · 속도"

    hm = extract_structured(blocks["heatmap"][0])
    assert [e["label"] for e in hm["series"]] == ["A라인 × 1분기", "A라인 × 2분기", "B라인 × 1분기"]

    # box/density 는 통계를 지어내지 않고 원시 분포를 values 로 보존한다
    box = extract_structured(blocks["box"][0])
    assert box["series"][0] == {"label": "A", "group": "A", "values": [10.1, 10.4],
                                "n": 2, "unit": "mm"}
    den = extract_structured(blocks["density"][0])
    assert den["series"][0]["values"] == [1.0, 1.2, 1.4]


def test_series_group_treemap_keeps_hierarchy(blocks: dict):
    p = extract_structured(blocks["treemap"][0])
    assert p["series"][1] == {"label": "국내", "value": 120.0, "unit": "억원", "parent": "전사"}


def test_timeline_group(blocks: dict):
    p = extract_structured(blocks["milestone"][0])
    assert p["kind"] == "timeline"
    assert p["milestones"][1] == {"label": "중간 검증", "date": "2026-06",
                                  "status": "current", "note": "필드 테스트"}
    assert p["range"] == {"start": "2026-01-01", "end": "2026-12-31"}
    assert structured_summary(p) == "일정 3건: 2026-02 ~ 2026-11"


def test_pairs_group(blocks: dict):
    """key_value 는 items 가 필드 선언이고 값은 content 최상위에 key 로 놓인다."""
    p = extract_structured(blocks["key_value"][0])
    assert p["kind"] == "pairs"
    assert p["pairs"] == [
        {"key": "cpu", "label": "CPU", "value": "Xeon 6338"},
        {"key": "mem", "label": "메모리", "value": "256GB"},
    ]
    rec = extract_structured(blocks["record"][0])
    assert rec["pairs"][0] == {"key": "__name", "label": "이름", "value": "프레스 1호"}


def test_media_group(blocks: dict):
    img = extract_structured(blocks["image"][0])
    assert img == {
        "kind": "media", "media_type": "image", "caption": "시험 장면",
        "files": [
            {"file_id": "f-shot-1", "caption": "정면", "alt": "시험기 정면"},
            {"file_id": "f-shot-2", "caption": "시험 장면", "alt": "측면"},
        ],
    }
    assert structured_summary(img) == "이미지 2건"
    # 단일 file_id 를 content 최상위에 두는 위젯들
    for t, fid in (("cad_3d", "f-cad-1"), ("doc_viewer", "f-doc-1"), ("html_embed", "f-bundle-1")):
        p = extract_structured(blocks[t][0])
        assert p["kind"] == "media" and p["files"][0]["file_id"] == fid, t


def test_media_file_id_in_props_is_found():
    """일부 보고서는 image 의 file_id 를 props 에 둔다 — content 만 보면 자산을 통째로 놓친다."""
    block = {"id": "img1", "type": "image", "props": {"file_id": "f-hero"},
             "content": {"caption": "히어로"}}
    p = extract_structured(block)
    assert p["files"] == [{"file_id": "f-hero", "caption": "히어로", "alt": ""}]


def test_text_group_returns_none(blocks: dict):
    for t in ("heading", "rich_text", "bulleted_list", "card", "equation"):
        assert extract_structured(blocks[t][0]) is None, t
        assert GROUP_BY_TYPE[t] == "text"


# ── 미지 타입·깨진 입력 안전 처리 ────────────────────────────────────────


def test_unknown_type_is_safe_and_tracked(blocks: dict):
    unknown = blocks["gantt_v2"][0]
    assert unknown["type"] not in GROUP_BY_TYPE
    assert extract_structured(unknown) is None
    stats = coverage_stats({"pages": [{"name": "p", "blocks": [unknown]}]})
    assert stats["unknown_types"] == {"gantt_v2": 1}
    assert stats["structured"] == 0


@pytest.mark.parametrize(
    "block",
    [
        {},
        {"type": "table"},
        {"type": "table", "content": None, "props": None},
        {"type": "table", "content": {"rows": []}},
        {"type": "flowchart", "content": {"items": ["문자열이지 dict 가 아님"]}},
        {"type": "tree", "content": {"rows": [{"label": "A", "parent": "A"}]}},  # 자기 참조
        {"type": "chart", "content": {"rows": [{"x": "a"}]}},
        {"type": "image", "content": {"files": [{"caption": "file_id 없음"}]}},
    ],
)
def test_malformed_blocks_never_raise(block: dict):
    payload = extract_structured(block)
    assert payload is None or isinstance(payload, dict)
    assert isinstance(structured_summary(payload), str)


def test_structured_summary_of_none_is_empty():
    assert structured_summary(None) == ""
    assert structured_summary({"kind": "미지"}) == ""


def test_every_structured_type_yields_payload(blocks: dict):
    """구조군 33종은 합성 픽스처에서 전부 payload 가 나와야 한다."""
    failed = [t for t in sorted(STRUCTURED_TYPES) if extract_structured(blocks[t][0]) is None]
    assert not failed, f"구조 추출 실패 타입: {failed}"
    assert len(STRUCTURED_TYPES) == 33


# ── 실물 보고서 커버리지 ─────────────────────────────────────────────────


def test_real_sample_coverage(norm: dict):
    stats = coverage_stats(norm)
    assert stats["total_blocks"] == 44
    assert stats["structured"] == 12       # key_value 2·tree 1·flowchart 3·comparison 2·table 2·raci 1·progress 1
    assert stats["text_group"] == 32
    assert stats["failed"] == 0
    assert stats["unknown_types"] == {}
    assert stats["by_kind"] == {"pairs": 2, "graph": 4, "table": 5, "series": 1}


def test_real_sample_structures_are_not_flattened(norm: dict):
    """흐름도의 노드/엣지, 표의 행/열, 진행률의 수치가 평문으로 뭉개지지 않는다."""
    by_id = {b["id"]: b for p in norm["pages"] for b in p["blocks"]}

    flow = extract_structured(by_id["fc_flow"])
    assert len(flow["nodes"]) == 6 and len(flow["edges"]) == 5
    assert flow["nodes"][0]["label"] == "엔지니어 — 개인 공간 작성"

    tbl = extract_structured(by_id["tbl_widgets"])
    assert len(tbl["columns"]) == 3 and len(tbl["rows"]) == 33
    assert tbl["rows"][0]["widget"] == "heading"

    pb = extract_structured(by_id["pb_progress"])
    assert [e["value"] for e in pb["series"]] == [100.0, 100.0, 100.0, 70.0, 30.0, 20.0, 0.0]

    raci = extract_structured(by_id["raci_perm"])
    assert raci["rows"][0]["owner"] == "R/A"

    tree = extract_structured(by_id["tree_layers"])
    assert len(tree["nodes"]) == 15
    assert max(n["level"] for n in tree["nodes"]) == 2


# ── fragmentize 통합 · 하위 호환 ─────────────────────────────────────────


def test_fragments_keep_legacy_fields(norm: dict):
    """기존 계약 필드(frag_id/type/text/source/confidence/widget/section) 무손상."""
    frags = fragmentize(norm)
    assert frags
    for f in frags:
        assert set(f) >= {"frag_id", "type", "text", "source", "confidence",
                          "widget", "widget_type", "section"}
        assert f["widget_type"] == f["widget"]
        assert f["text"] and len(f["text"]) <= 200
        assert f["source"]["page"] and f["source"]["block_id"]


def test_structured_widgets_collapse_to_one_fragment(norm: dict):
    """구조 위젯은 대표 조각 1건 — 표 35행이 조각 35건이 되던 과분할을 없앤다."""
    frags = fragmentize(norm)
    per_block: dict[str, int] = {}
    for f in frags:
        per_block[f["source"]["block_id"]] = per_block.get(f["source"]["block_id"], 0) + 1
    for bid in ("tbl_widgets", "cmp_rel", "fc_flow", "pb_progress", "raci_perm", "tree_layers"):
        assert per_block[bid] == 1, f"{bid}: 대표 조각 1건이어야 한다"
    # 텍스트군은 기존대로 항목당 1조각
    assert per_block["bl_purpose"] == 5
    assert len(frags) == 63


def test_structured_payload_rides_on_fragment(norm: dict):
    frags = fragmentize(norm)
    structured = [f for f in frags if "structured" in f]
    assert len(structured) == 12
    tbl = next(f for f in structured if f["source"]["block_id"] == "tbl_widgets")
    assert tbl["structured"]["kind"] == "table"
    assert len(tbl["structured"]["rows"]) == 33          # 행이 조각 밖으로 사라지지 않는다
    assert tbl["text"].startswith("표 3열×33행: 카테고리/위젯/용도")
    # 텍스트군 조각에는 structured 가 붙지 않는다
    assert all("structured" not in f for f in frags if f["widget"] == "heading")


def test_media_widgets_make_no_text_fragment():
    """미디어군은 텍스트 조각을 만들지 않는다 — 캡션이 claim 으로 둔갑하면 안 된다."""
    norm = {
        "doc_id": "abcd1234",
        "pages": [{"name": "p", "blocks": [
            {"id": "i1", "type": "image", "props": {},
             "content": {"caption": "그림", "files": [{"file_id": "f1", "alt": "a"}]},
             "section": None},
            {"id": "v1", "type": "video", "props": {},
             "content": {"files": [{"file_id": "f2", "filename": "a.mp4"}]}, "section": None},
            {"id": "a1", "type": "attachment", "props": {},
             "content": {"files": [{"file_id": "f3", "filename": "a.csv"}]}, "section": None},
            {"id": "h1", "type": "heading", "props": {}, "content": {"text": "제목"},
             "section": None},
        ]}],
    }
    assert [f["source"]["block_id"] for f in fragmentize(norm)] == ["h1"]
    # 대신 자산은 블록 문맥과 함께 media 채널로 흐른다
    media = collect_media(norm)
    assert [(m["file_id"], m["media_type"], m["block_id"]) for m in media] == [
        ("f1", "image", "i1"), ("f2", "video", "v1"), ("f3", "attachment", "a1"),
    ]
    assert media[0]["caption"] == "그림" and media[0]["asset"] is None


def test_collect_media_joins_assets_meta(blocks: dict):
    norm = {
        "pages": [{"name": "p1", "blocks": [blocks["image"][0], blocks["comparison"][0]]}],
        "assets_meta": [
            {"file_id": "f-shot-1", "status": "resolved", "local_path": "/tmp/a.png",
             "width": 800, "height": 600},
        ],
    }
    media = collect_media(norm)
    ids = [m["file_id"] for m in media]
    # comparison 의 이미지 셀도 자산으로 잡힌다
    assert ids == ["f-shot-1", "f-shot-2", "f-old-ui", "f-new-ui"]
    assert media[0]["asset"]["width"] == 800
    assert media[1]["asset"] is None
    assert media[2]["media_type"] == "image" and media[2]["block_id"] == "w_comparison"
