# wdpipeline.archive.build_report_draft 테스트 — 완성 보고서 역기록·위젯 타입 보존·왕복 무결성
from __future__ import annotations

import glob
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from wdpipeline.archive import build_archive_draft, build_report_draft, restore_widget
from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file
from wdpipeline.widgets import coverage_stats, extract_structured

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
SYNTHETIC = REPO_ROOT / "data" / "widget_check" / "synthetic_blocks.json"
RUN_DIR = REPO_ROOT / "data" / "pipeline" / "delib_v2"
STILLS_DIR = REPO_ROOT / "data" / "quality_compare" / "v2"
_MEETING_GLOB = str(REPO_ROOT / "data" / "meetings" / "20260726-165143_scenario_build_*")

# payload 재추출이 원본과 완전히 같아야 하는 위젯 (좌표/격자 스키마가 없는 것들)
LOSSLESS_TYPES = {
    "table", "comparison", "raci_matrix", "fmea", "record_table",
    "flowchart", "tree", "mind_map",
    "chart", "pie", "waffle", "treemap", "packing", "progress_bar",
    "milestone", "key_value", "record",
    "image", "video", "attachment", "cad_3d", "doc_viewer", "html_embed",
}

_has_delib = RUN_DIR.is_dir() and bool(glob.glob(_MEETING_GLOB))
needs_delib = pytest.mark.skipif(not _has_delib, reason="delib_v2 실데이터 없음")


def _meeting_dir() -> Path:
    return Path(sorted(glob.glob(_MEETING_GLOB))[0])


def _canon(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


@pytest.fixture(scope="module")
def source_norm() -> dict:
    if not _has_delib:
        pytest.skip("delib_v2 실데이터 없음")
    return json.loads((RUN_DIR / "report.norm.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def report_draft() -> dict:
    if not _has_delib:
        pytest.skip("delib_v2 실데이터 없음")
    return build_report_draft(RUN_DIR, meeting_dir=_meeting_dir())


def _draft_types(draft: dict) -> Counter:
    return Counter(b["type"] for p in draft["pages"] for b in p["extra_blocks"])


# ---------------------------------------------------------------------------
# 1. 페이로드 스키마 — 표지 + 섹션 + 부록
# ---------------------------------------------------------------------------


@needs_delib
def test_top_level_schema(report_draft: dict, source_norm: dict):
    assert report_draft["_type"] == "report_archive_draft_v1"
    assert report_draft["title"] == f"{source_norm['title']} (심의 정리본)"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_draft["report_date"])
    assert report_draft["tags"] == ["webdesignagents", "심의정리본"]
    assert report_draft["pending_assets"] == []


@needs_delib
def test_page_layout_is_cover_sections_appendix(report_draft: dict):
    scenario = json.loads((RUN_DIR / "scenario.json").read_text(encoding="utf-8"))
    names = [p["name"] for p in report_draft["pages"]]
    assert names[0] == "개요"
    assert names[-1].startswith("부록")
    assert names[1:-1] == [
        f"{i}. {s['name']}" for i, s in enumerate(scenario["scenes"], start=1)
    ]


@needs_delib
def test_page_block_structure(report_draft: dict):
    """페이지마다 extra_blocks + content + blocks_order 정합 (report_sample 실물 구조)."""
    for page in report_draft["pages"]:
        assert "template_id" in page and "template_version" in page
        ids = [b["id"] for b in page["extra_blocks"]]
        assert len(ids) == len(set(ids)), f"{page['name']}: 블록 id 중복"
        assert page["blocks_order"] == ids
        assert set(page["content"]) == set(ids)
        assert set(page.get("block_sections", {})) <= set(ids)
        for b in page["extra_blocks"]:
            assert isinstance(b.get("props"), dict)


@needs_delib
def test_cover_page_has_heading_kv_richtext(report_draft: dict):
    cover = report_draft["pages"][0]
    assert [b["type"] for b in cover["extra_blocks"]] == ["heading", "key_value", "rich_text"]
    scenario = json.loads((RUN_DIR / "scenario.json").read_text(encoding="utf-8"))
    core = scenario["meta"]["core_message"]
    assert core in cover["content"]["rt_cover"]["markdown"], "표지 요약이 core_message 를 담아야 한다"
    kv = cover["content"]["kv_cover"]
    assert {it["key"] for it in kv["items"]} >= {"source_report", "sections", "evidence"}


# ---------------------------------------------------------------------------
# 2. 위젯 타입 — 샘플 실물 집합의 부분집합이고, 원 보고서 타입을 보존한다
# ---------------------------------------------------------------------------


@needs_delib
def test_widget_types_subset_of_sample(report_draft: dict):
    """위젯 타입은 report_sample.json 실물에서 검증된 집합만 쓴다 (스키마 추측 금지)."""
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    allowed = {b["type"] for page in sample["pages"] for b in page["extra_blocks"]}
    used = set(_draft_types(report_draft))
    assert used <= allowed, f"샘플에 없는 위젯 타입: {used - allowed}"


@needs_delib
def test_source_widget_types_all_preserved(report_draft: dict, source_norm: dict):
    """원 보고서에 있던 위젯 타입은 하나도 빠지지 않고 정리본에 다시 나타난다."""
    source = {b["type"] for p in source_norm["pages"] for b in p["blocks"]}
    used = set(_draft_types(report_draft))
    assert source <= used, f"보존되지 않은 원 위젯 타입: {source - used}"


@needs_delib
def test_every_structured_block_becomes_evidence(report_draft: dict, source_norm: dict):
    """구조를 가진 원 블록은 전부 근거 위젯으로 되살아나고, 타입도 그대로다."""
    src = {
        b["id"]: b["type"]
        for p in source_norm["pages"] for b in p["blocks"]
        if extract_structured(b) is not None
    }
    restored = {
        b["id"][3:]: b["type"]
        for p in report_draft["pages"] for b in p["extra_blocks"]
        if b["id"].startswith("ev_")
    }
    assert set(restored) == set(src), f"누락={set(src) - set(restored)}"
    assert restored == src, "복원 위젯 타입이 원 블록 타입과 다르다"


@needs_delib
def test_evidence_caption_cites_source_block(report_draft: dict):
    """근거 위젯은 자기 출처(원 보고서 페이지·블록)를 라벨에 각주로 단다."""
    for page in report_draft["pages"]:
        for b in page["extra_blocks"]:
            if b["id"].startswith("ev_"):
                assert "출처: " in b["props"]["label"]
                assert b["id"][3:] in b["props"]["label"]


# ---------------------------------------------------------------------------
# 3. 근거 복원 무손실성 — 복원한 위젯을 다시 추출하면 원 payload 와 같아야 한다
# ---------------------------------------------------------------------------


@needs_delib
def test_restore_is_lossless_on_source_report(source_norm: dict):
    checked = 0
    for page in source_norm["pages"]:
        for block in page["blocks"]:
            payload = extract_structured(block)
            if payload is None:
                continue
            restored = restore_widget(block["type"], payload)
            assert restored is not None, f"{block['id']} 복원 실패"
            wtype, props, content = restored
            again = extract_structured({"id": block["id"], "type": wtype,
                                        "props": props, "content": content})
            assert _canon(again) == _canon(payload), f"{block['id']} payload 손실"
            checked += 1
    assert checked == 12, f"delib_v2 원 보고서 구조 블록 12개 기준 — 실제 {checked}"


def test_restore_covers_registry_and_is_lossless_where_possible():
    """합성 픽스처 전수 — 되살릴 수 없는 위젯이 조용히 사라지지 않는다."""
    if not SYNTHETIC.is_file():
        pytest.skip("synthetic_blocks.json 없음")
    blocks = json.loads(SYNTHETIC.read_text(encoding="utf-8"))["blocks"]
    lossless: set[str] = set()
    for block in blocks:
        payload = extract_structured(block)
        if payload is None:
            continue
        restored = restore_widget(block["type"], payload)
        assert restored is not None, f"{block['type']} 이 복원되지 않고 버려졌다"
        wtype, props, content = restored
        again = extract_structured({"id": block["id"], "type": wtype,
                                    "props": props, "content": content})
        assert again is not None, f"{block['type']} → {wtype} 재추출 실패"
        if _canon(again) == _canon(payload):
            lossless.add(block["type"])
    assert lossless == LOSSLESS_TYPES, (
        f"무손실 집합 변동 — 잃음={LOSSLESS_TYPES - lossless} 늘어남={lossless - LOSSLESS_TYPES}"
    )


def test_comparison_image_cell_keeps_file_id():
    """comparison 의 이미지 셀은 file_id 를 그대로 유지한다 (원 보고서 자산 재사용)."""
    block = {
        "id": "cmp", "type": "comparison",
        "props": {"label": "비교", "cases": [{"key": "a", "label": "A"}, {"key": "b", "label": "B"}]},
        "content": {"rows": [
            {"label": "화면", "values": {
                "a": {"file_id": "f-old", "alt": "구 화면", "caption": "이전"},
                "b": {"file_id": "f-new", "alt": "신 화면", "caption": "신규"},
            }},
        ]},
    }
    wtype, _props, content = restore_widget("comparison", extract_structured(block))
    assert wtype == "comparison"
    values = content["rows"][0]["values"]
    assert values["a"]["file_id"] == "f-old" and values["b"]["file_id"] == "f-new"


def test_distribution_widget_degrades_to_table_without_loss_of_values():
    """box·density 는 차트로 되살릴 수 없다 — 값을 표로 보존하고 블록을 버리지 않는다."""
    block = {
        "id": "d1", "type": "density", "props": {"label": "분포"},
        "content": {"groups": [{"name": "A", "values": [1, 2, 3]}]},
    }
    wtype, props, content = restore_widget("density", extract_structured(block))
    assert wtype == "table"
    assert props["label"] == "분포"
    assert content["rows"][0] == {"group": "A", "n": "3", "values": "1, 2, 3"}


# ---------------------------------------------------------------------------
# 4. 본문·부록 — 심의 산출물이 그대로 문서가 된다
# ---------------------------------------------------------------------------


@needs_delib
def test_section_body_is_scene_narration(report_draft: dict):
    scenario = json.loads((RUN_DIR / "scenario.json").read_text(encoding="utf-8"))
    for page, scene in zip(report_draft["pages"][1:-1], scenario["scenes"]):
        markdown = page["content"]["rt_body"]["markdown"]
        assert scene["narration"] in markdown, f"{page['name']}: 본문이 내레이션 정본이 아니다"
        assert page["content"]["h1_section"]["text"], "섹션 제목이 비었다"


@needs_delib
def test_appendix_carries_minutes_and_sources(report_draft: dict, source_norm: dict):
    appendix = report_draft["pages"][-1]
    types = [b["type"] for b in appendix["extra_blocks"]]
    assert types.count("bulleted_list") == 2 and "table" in types
    assert appendix["content"]["bl_decisions"]["items"], "심의 결정이 비었다"
    assert appendix["content"]["bl_open_issues"]["items"], "미해결 쟁점이 비었다"
    rows = appendix["content"]["tbl_sources"]["rows"]
    structured_ids = {
        b["id"] for p in source_norm["pages"] for b in p["blocks"]
        if extract_structured(b) is not None
    }
    assert {r["block"] for r in rows} == structured_ids
    assert all(r["frag"].startswith(f"RA-{source_norm['doc_id']}-") for r in rows), \
        "출처 표가 조각 id 를 잃었다"
    assert {r["page"] for r in rows} <= {p["name"] for p in source_norm["pages"]}


# ---------------------------------------------------------------------------
# 5. 왕복 무결성 — 우리가 만든 보고서를 우리 P0/P1 이 다시 소비한다
# ---------------------------------------------------------------------------


@needs_delib
def test_roundtrip_ingest_fragmentize(report_draft: dict, tmp_path: Path):
    path = tmp_path / "report.json"
    path.write_text(json.dumps(report_draft, ensure_ascii=False), encoding="utf-8")
    norm = ingest_report_file(path)
    assert norm["title"] == report_draft["title"]
    assert norm["source_format"] == "report_archive_draft_v1"
    assert len(norm["pages"]) == len(report_draft["pages"])
    assert sum(len(p["blocks"]) for p in norm["pages"]) == sum(
        len(p["extra_blocks"]) for p in report_draft["pages"]
    )
    stats = coverage_stats(norm)
    assert stats["failed"] == 0 and stats["unknown_types"] == {}
    assert stats["structured"] == 14, "표지 kv + 근거 12 + 부록 출처표 = 14"

    frags = fragmentize(norm)
    assert frags and all(f["frag_id"].startswith(f"RA-{norm['doc_id']}-") for f in frags)
    assert sum(1 for f in frags if "structured" in f) == stats["structured"]


@needs_delib
def test_roundtrip_preserves_evidence_payloads(report_draft: dict, tmp_path: Path):
    """재소비한 보고서의 근거 payload 가 원 보고서 payload 와 같다 (캡션만 각주가 붙는다)."""
    source = {}
    for page in json.loads((RUN_DIR / "report.norm.json").read_text(encoding="utf-8"))["pages"]:
        for block in page["blocks"]:
            payload = extract_structured(block)
            if payload is not None:
                source[block["id"]] = payload

    path = tmp_path / "report.json"
    path.write_text(json.dumps(report_draft, ensure_ascii=False), encoding="utf-8")
    norm = ingest_report_file(path)
    seen = 0
    for page in norm["pages"]:
        for block in page["blocks"]:
            if not str(block["id"]).startswith("ev_"):
                continue
            payload = extract_structured(block)
            assert payload is not None
            original = dict(source[str(block["id"])[3:]])
            original["caption"] = payload["caption"]  # 캡션에는 출처 각주가 붙는다
            assert _canon(payload) == _canon(original), block["id"]
            seen += 1
    assert seen == len(source) == 12


# ---------------------------------------------------------------------------
# 6. 씬 스틸 · 파라미터 · 최소 입력
# ---------------------------------------------------------------------------


@needs_delib
@pytest.mark.skipif(not STILLS_DIR.is_dir(), reason="delib_v2 스틸 캡처 없음")
def test_stills_become_image_widgets_with_pending_upload():
    draft = build_report_draft(RUN_DIR, meeting_dir=_meeting_dir(), stills_dir=STILLS_DIR)
    images = [
        (p["name"], b["id"]) for p in draft["pages"] for b in p["extra_blocks"]
        if b["type"] == "image"
    ]
    pending = draft["pending_assets"]
    assert images and len(pending) == len(images)
    assert [(a["page"], a["block_id"]) for a in pending] == images
    for a in pending:
        assert Path(a["local_path"]).is_file()
        page = next(p for p in draft["pages"] if p["name"] == a["page"])
        caption = page["content"][a["block_id"]]["caption"]
        assert "업로드 필요" in caption and a["local_path"] in caption


@needs_delib
def test_unknown_style_is_rejected():
    with pytest.raises(ValueError, match="알 수 없는 style"):
        build_report_draft(RUN_DIR, style="slides")


def _minimal_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    run.mkdir()
    (run / "report.norm.json").write_text(json.dumps({
        "doc_id": "abcd1234", "title": "미니 보고서", "report_date": "2026-01-01",
        "pages": [{"name": "1. 현황", "blocks": [
            {"id": "h1", "type": "heading", "props": {}, "content": {"text": "현황"}, "section": None},
            {"id": "tbl1", "type": "table",
             "props": {"columns": [{"key": "k", "label": "항목", "type": "text"}]},
             "content": {"rows": [{"k": "값"}]}, "section": "analysis"},
        ]}],
    }, ensure_ascii=False), encoding="utf-8")
    (run / "scenario.json").write_text(json.dumps({
        "meta": {"core_message": "핵심", "duration_sec": 10},
        "content": {"opening": {"title": "한 줄 카피"}},
        "scenes": [{"name": "오프닝", "dur": 10, "tpl": "opening@1",
                    "data_ref": "content.opening", "narration": "내레이션"}],
    }, ensure_ascii=False), encoding="utf-8")
    return run


def test_minimal_run_without_meeting_roundtrips(tmp_path: Path):
    """회의 기록·조각 파일이 없어도 유효한 draft_v1 이 나오고 왕복이 통과한다."""
    draft = build_report_draft(_minimal_run(tmp_path))
    assert draft["_type"] == "report_archive_draft_v1"
    assert [p["name"] for p in draft["pages"]] == ["개요", "1. 오프닝", "부록 — 심의 근거"]
    assert draft["pages"][1]["content"]["h1_section"]["text"] == "한 줄 카피"
    assert draft["pages"][-1]["content"]["bl_decisions"]["items"] == ["(심의 결정 기록 없음)"]
    # 조각 파일이 없어도 블록에서 직접 구조를 뽑아 근거를 세운다
    assert draft["pages"][-1]["content"]["tbl_sources"]["rows"][0]["block"] == "tbl1"

    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    assert fragmentize(ingest_report_file(path))


def test_archive_draft_still_builds_production_record(tmp_path: Path):
    """제작기록 빌더는 그대로 공존한다 — 완성 보고서와 다른 문서다."""
    run = _minimal_run(tmp_path)
    record = build_archive_draft(run)
    report = build_report_draft(run)
    assert record["title"].startswith("[제작기록] ")
    assert [p["name"] for p in record["pages"]] == [
        "1. 개요", "2. 심의 기록", "3. 씬 구성", "4. 품질 검증",
    ]
    assert record["title"] != report["title"] and record["tags"] != report["tags"]
