# 미디어 자산 채널 통합 테스트 — 보고서 JSON의 image 위젯이 블록 문맥 + 해결된 로컬 파일까지 이어지는지
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file
from wdpipeline.widgets import collect_media

pytest.importorskip("PIL.Image", reason="이미지 메타 확인에 Pillow 필요")


def _report(tmp: Path) -> Path:
    """image 위젯 1개 + comparison 이미지 셀 1개를 가진 최소 복붙 보고서."""
    raw = {
        "_type": "report_archive_draft_v1",
        "title": "자산 경로 확인 보고서",
        "report_date": "2026-07-27",
        "tags": [],
        "pages": [
            {
                "name": "1. 시험 결과",
                "blocks_order": ["h1", "img1", "cmp1"],
                "block_sections": {"h1": "purpose"},
                "extra_blocks": [
                    {"id": "h1", "type": "heading", "props": {"level": 2}},
                    {"id": "img1", "type": "image", "props": {"label": "사진"}},
                    {
                        "id": "cmp1",
                        "type": "comparison",
                        "props": {
                            "label": "전후 비교",
                            "cases": [{"key": "before", "label": "개선 전"},
                                      {"key": "after", "label": "개선 후"}],
                        },
                    },
                ],
                "content": {
                    "h1": {"text": "낙하 시험 결과"},
                    "img1": {
                        "caption": "시험 장면",
                        "files": [{"file_id": "shot01", "caption": "정면", "alt": "시험기 정면"}],
                    },
                    "cmp1": {
                        "rows": [
                            {"key": "look", "label": "외관", "kind": "image",
                             "values": {"before": {"file_id": "shot01", "alt": "전"},
                                        "after": {"file_id": "missing99", "alt": "후"}}},
                        ]
                    },
                },
            }
        ],
    }
    path = tmp / "report.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return path


@pytest.fixture()
def staged(tmp_path: Path) -> dict:
    from PIL import Image

    assets_dir = tmp_path / "assets"
    assets_dir.mkdir()
    Image.new("RGB", (640, 480), "navy").save(assets_dir / "shot01.png")
    norm = ingest_report_file(_report(tmp_path), assets_dir=assets_dir)
    return {"norm": norm, "assets_dir": assets_dir}


def test_image_widget_makes_no_fragment_but_reaches_media_channel(staged: dict):
    norm = staged["norm"]
    frags = fragmentize(norm)
    # 이미지 블록은 텍스트 조각을 만들지 않는다 (캡션이 claim 으로 둔갑 금지)
    assert "img1" not in {f["source"]["block_id"] for f in frags}
    # comparison 은 표 구조 조각 1건 (이미지 셀 텍스트는 alt 로)
    cmp_frag = next(f for f in frags if f["source"]["block_id"] == "cmp1")
    assert cmp_frag["structured"]["kind"] == "table"
    assert cmp_frag["structured"]["rows"][0] == {"__aspect": "외관", "before": "전", "after": "후"}


def test_collect_media_carries_block_context_and_resolved_file(staged: dict):
    media = collect_media(staged["norm"])
    by_block = {(m["block_id"], m["file_id"]): m for m in media}
    assert set(by_block) == {("img1", "shot01"), ("cmp1", "shot01"), ("cmp1", "missing99")}

    shot = by_block[("img1", "shot01")]
    assert shot["media_type"] == "image"
    assert shot["page"] == "1. 시험 결과"
    assert shot["caption"] == "정면" and shot["alt"] == "시험기 정면"
    # assets.resolve_assets 레코드가 조인되어 실제 파일 경로·크기가 붙는다
    assert shot["asset"]["status"] == "resolved"
    assert Path(shot["asset"]["local_path"]).is_file()
    assert (shot["asset"]["width"], shot["asset"]["height"]) == (640, 480)

    # comparison 셀의 이미지도 같은 채널로 잡힌다 (block_id 는 comparison 블록)
    assert by_block[("cmp1", "shot01")]["asset"]["status"] == "resolved"


def test_unresolved_file_is_reported_not_silently_dropped(staged: dict):
    media = collect_media(staged["norm"])
    missing = next(m for m in media if m["file_id"] == "missing99")
    assert missing["asset"]["status"] == "unresolved"
    assert missing["asset"]["reason"], "미해결 자산은 사유가 있어야 한다"


def test_media_absent_when_no_media_widgets():
    norm = {"pages": [{"name": "p", "blocks": [
        {"id": "h", "type": "heading", "props": {}, "content": {"text": "t"}, "section": None}
    ]}]}
    assert collect_media(norm) == []
