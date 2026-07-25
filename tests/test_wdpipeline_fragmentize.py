# wdpipeline.fragmentize 테스트 — 위젯 타입별 매핑 표·frag_id 형식·source 추적
from __future__ import annotations

import re
from pathlib import Path

import pytest

from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"


@pytest.fixture(scope="module")
def norm() -> dict:
    return ingest_report_file(SAMPLE)


@pytest.fixture(scope="module")
def frags(norm: dict) -> list[dict]:
    return fragmentize(norm)


def test_frag_id_format_and_sequence(norm: dict, frags: list[dict]):
    pat = re.compile(rf"^RA-{norm['doc_id']}-(\d{{3}})$")
    for i, f in enumerate(frags, start=1):
        m = pat.match(f["frag_id"])
        assert m, f"frag_id 형식 위반: {f['frag_id']}"
        assert int(m.group(1)) == i, "seq 는 1부터 연속이어야 한다"


def test_widget_type_mapping(frags: list[dict]):
    """PLAN §4 P1 매핑 표 — 위젯 타입별 기본 조각 타입."""
    by_widget = {}
    for f in frags:
        by_widget.setdefault(f["widget"], set()).add(f["type"])
    assert by_widget["heading"] == {"claim"}
    assert by_widget["bulleted_list"] <= {"claim", "case"}
    assert by_widget["rich_text"] <= {"claim", "case"}
    assert by_widget["table"] <= {"metric", "evidence"}
    assert by_widget["comparison"] <= {"metric", "evidence"}
    assert by_widget["key_value"] <= {"metric", "evidence"}
    assert by_widget["flowchart"] == {"evidence"}    # 절차 Evidence
    assert by_widget["tree"] == {"evidence"}         # 구조 Evidence
    assert by_widget["raci_matrix"] == {"evidence"}
    assert by_widget["progress_bar"] == {"metric"}   # chart 계열 → Metric


def test_source_traceability(frags: list[dict]):
    """모든 조각은 원 블록으로 되짚을 수 있어야 한다 (known_refs 인용 근거)."""
    f = next(f for f in frags if f["widget"] == "flowchart")
    assert f["source"]["page"] == "2. 보고서 워크플로"
    assert f["source"]["block_id"] == "fc_flow"
    for f in frags:
        assert f["source"]["page"]
        assert f["source"]["block_id"]
        assert 0.0 <= f["confidence"] <= 1.0
        assert f["text"]
        assert len(f["text"]) <= 200


def test_itemized_widgets_split_per_item(norm: dict, frags: list[dict]):
    """bulleted_list 는 항목당 1조각 — 씬 배치 단위와 일치."""
    purpose = [f for f in frags if f["source"]["block_id"] == "bl_purpose"]
    src_items = None
    for page in norm["pages"]:
        for b in page["blocks"]:
            if b["id"] == "bl_purpose":
                src_items = b["content"]["items"]
    assert len(purpose) == len(src_items) == 5
    assert purpose[0]["section"] == "purpose"


def test_visual_assets_skipped():
    norm = {
        "doc_id": "abcd1234",
        "pages": [
            {
                "name": "p",
                "blocks": [
                    {"id": "i1", "type": "image", "props": {}, "content": {"caption": "그림"},
                     "section": None},
                    {"id": "h1", "type": "heading", "props": {}, "content": {"text": "제목"},
                     "section": None},
                ],
            }
        ],
    }
    frags = fragmentize(norm)
    assert [f["source"]["block_id"] for f in frags] == ["h1"]  # image 는 조각 미생성
