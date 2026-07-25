# wdpipeline.ingest 테스트 — 복붙 JSON 파싱·블록 정렬·섹션 보존·search_text 자체 생성
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wdpipeline.ingest import block_text, ingest_report_file, normalize_report

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"


@pytest.fixture(scope="module")
def norm() -> dict:
    return ingest_report_file(SAMPLE)


def test_sample_normalizes(norm: dict):
    assert norm["title"] == "ReportArchive 플랫폼 사용 설명서"
    assert len(norm["pages"]) == 5
    assert norm["report_date"] == "2026-05-27"
    assert norm["tags"] == ["설명서", "플랫폼 가이드", "온보딩"]
    # 복붙 모드에는 ai_summary 가 없다 → None
    assert norm["ai_summary"] is None


def test_doc_id_stable(norm: dict):
    """doc_id 는 title|report_date 해시 — 같은 입력이면 항상 같아야 한다 (frag_id 안정성)."""
    again = ingest_report_file(SAMPLE)
    assert norm["doc_id"] == again["doc_id"]
    assert len(norm["doc_id"]) == 8


def test_block_order_follows_extra_blocks_when_order_empty(norm: dict):
    """샘플의 blocks_order 는 빈 배열 — extra_blocks 선언 순서 폴백."""
    page1 = norm["pages"][0]
    ids = [b["id"] for b in page1["blocks"]]
    assert ids[:3] == ["h1_intro", "rt_intro", "h2_purpose"]


def test_blocks_order_respected():
    raw = {
        "_type": "report_archive_draft_v1",
        "title": "순서 테스트",
        "report_date": "2026-01-01",
        "tags": [],
        "pages": [
            {
                "name": "p1",
                "extra_blocks": [
                    {"id": "a", "type": "heading", "props": {}},
                    {"id": "b", "type": "heading", "props": {}},
                ],
                "content": {"a": {"text": "A"}, "b": {"text": "B"}},
                "blocks_order": ["b", "a"],
                "block_sections": {},
            }
        ],
    }
    out = normalize_report(raw)
    assert [b["id"] for b in out["pages"][0]["blocks"]] == ["b", "a"]


def test_sections_preserved(norm: dict):
    """block_sections 태그(purpose/background/…)는 설득 골격 배치 힌트로 보존."""
    page1 = norm["pages"][0]
    sections = {b["id"]: b["section"] for b in page1["blocks"]}
    assert sections["bl_purpose"] == "purpose"
    assert sections["rt_intro"] == "background"
    assert sections["h1_intro"] is None


def test_search_text_generated(norm: dict):
    """search_text 는 위젯 텍스트 평탄화로 자체 생성 — 대표 위젯의 내용을 담아야 한다."""
    st = norm["search_text"]
    assert "ReportArchive 플랫폼 개요" in st          # heading
    assert "live link" in st                            # bulleted_list 항목
    assert "FastAPI" in st                              # key_value 값
    assert "엔지니어 — 개인 공간 작성" in st           # flowchart label
    assert "**" not in st                               # 마크다운 기호 제거


def test_block_text_by_type():
    assert block_text("heading", {"text": "제목"}) == "제목"
    assert block_text("rich_text", {"markdown": "**굵게** 그리고 [링크](http://x)"}) == "굵게 그리고 링크"
    assert block_text("bulleted_list", {"items": ["하나", "둘"]}) == "하나 둘"
    assert "라벨: 값" in block_text(
        "key_value", {"items": [{"key": "k", "label": "라벨", "type": "text"}], "k": "값"}
    )
    assert block_text("image", {"caption": "사진 설명"}) == "사진 설명"
    # 미지 타입 폴백 — 문자열 재귀 수집
    assert block_text("unknown_widget", {"deep": {"x": "텍스트"}}) == "텍스트"


def test_unsupported_type_raises(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"_type": "something_else", "title": "t"}), encoding="utf-8")
    with pytest.raises(ValueError, match="report_archive_draft_v1"):
        ingest_report_file(bad)


def test_assets_skip_recorded(tmp_path: Path):
    raw = {
        "_type": "report_archive_draft_v1",
        "title": "자산 테스트",
        "report_date": "2026-01-01",
        "tags": [],
        "pages": [
            {
                "name": "p1",
                "extra_blocks": [{"id": "img1", "type": "image", "props": {"file_id": "f-123"}}],
                "content": {"img1": {"caption": "그림"}},
                "blocks_order": [],
                "block_sections": {},
            }
        ],
    }
    # assets_dir 없음 → local_path=None 스킵 기록
    out = normalize_report(raw)
    assert out["assets"] == [{"file_id": "f-123", "local_path": None}]
    # assets_dir 에 파일이 있으면 매핑
    (tmp_path / "f-123.png").write_bytes(b"png")
    out2 = normalize_report(raw, assets_dir=tmp_path)
    assert out2["assets"][0]["local_path"] == str(tmp_path / "f-123.png")
