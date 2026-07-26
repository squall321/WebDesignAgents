# wdpipeline.archive 테스트 — report_archive_draft_v1 스키마·왕복(ingest→fragmentize)·업로드 게이트
from __future__ import annotations

import glob
import json
import re
from pathlib import Path

import pytest

from wdpipeline.archive import build_archive_draft, submit_draft
from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
RUN_DIR = REPO_ROOT / "data" / "pipeline" / "delib_v1"
QA_REPORT = REPO_ROOT / "data" / "qa_reports" / "20260726-070738-a32d81" / "qa.json"
RENDERS_DIR = REPO_ROOT / "data" / "renders" / "delib_v1"

_has_delib = RUN_DIR.is_dir() and bool(
    glob.glob(str(REPO_ROOT / "data" / "meetings" / "20260726-041245_scenario_build_*"))
)
needs_delib = pytest.mark.skipif(not _has_delib, reason="delib_v1 실데이터 없음")


def _sample_widget_types() -> set[str]:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    return {
        b["type"] for page in sample["pages"] for b in page["extra_blocks"]
    }


@pytest.fixture(scope="module")
def delib_draft() -> dict:
    if not _has_delib:
        pytest.skip("delib_v1 실데이터 없음")
    meeting = Path(sorted(
        glob.glob(str(REPO_ROOT / "data" / "meetings" / "20260726-041245_scenario_build_*"))
    )[0])
    return build_archive_draft(
        RUN_DIR, meeting_dir=meeting, qa_report=QA_REPORT, renders_dir=RENDERS_DIR
    )


# ---------------------------------------------------------------------------
# 1. 페이로드 스키마
# ---------------------------------------------------------------------------


@needs_delib
def test_top_level_schema(delib_draft: dict):
    assert delib_draft["_type"] == "report_archive_draft_v1"
    assert delib_draft["title"].startswith("[제작기록] ")
    assert delib_draft["title"].endswith(" 발표자료")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", delib_draft["report_date"])
    assert delib_draft["tags"] == ["webdesignagents", "제작기록"]
    assert [p["name"] for p in delib_draft["pages"]] == [
        "1. 개요", "2. 심의 기록", "3. 씬 구성", "4. 품질 검증",
    ]


@needs_delib
def test_page_block_structure(delib_draft: dict):
    """페이지마다 extra_blocks + content + blocks_order 정합 (report_sample 실물 구조)."""
    for page in delib_draft["pages"]:
        assert "template_id" in page and "template_version" in page
        ids = [b["id"] for b in page["extra_blocks"]]
        assert len(ids) == len(set(ids)), "블록 id 중복"
        assert page["blocks_order"] == ids, "blocks_order 는 extra_blocks 선언 순서와 일치"
        assert set(page["content"].keys()) == set(ids), "content 키는 블록 id 와 1:1"
        assert set(page.get("block_sections", {})) <= set(ids)
        for b in page["extra_blocks"]:
            assert isinstance(b.get("props"), dict)


@needs_delib
def test_widget_types_subset_of_sample(delib_draft: dict):
    """위젯 타입은 report_sample.json 실물에서 검증된 집합의 부분집합만 쓴다 (스키마 추측 금지)."""
    used = {b["type"] for p in delib_draft["pages"] for b in p["extra_blocks"]}
    assert used <= _sample_widget_types(), f"샘플에 없는 위젯 타입 사용: {used - _sample_widget_types()}"


@needs_delib
def test_deliberation_table(delib_draft: dict):
    page = delib_draft["pages"][1]
    rows = page["content"]["tbl_turns"]["rows"]
    assert 0 < len(rows) <= 20
    for row in rows:
        assert set(row) == {"round", "speaker", "stance", "gist"}
    # delib_v1 은 19턴 — 전 턴 수록, 생략 행 없음
    assert len(rows) == 19
    assert page["content"]["bl_decisions"]["items"], "결정 사항 불릿이 비어 있다"
    assert page["content"]["bl_open_issues"]["items"], "미해결 쟁점 불릿이 비어 있다"


@needs_delib
def test_scene_table_matches_scenario(delib_draft: dict):
    scenario = json.loads((RUN_DIR / "scenario.json").read_text(encoding="utf-8"))
    rows = delib_draft["pages"][2]["content"]["tbl_scenes"]["rows"]
    assert [r["scene"] for r in rows] == [s["name"] for s in scenario["scenes"]]
    assert all(r["copy"] for r in rows), "핵심 카피 빈 칸"


@needs_delib
def test_qa_page(delib_draft: dict):
    kv = delib_draft["pages"][3]["content"]["kv_qa"]
    got = {it["key"]: kv[it["key"]] for it in kv["items"]}
    assert got["passed"] == "통과"
    assert got["errors"] == "0" and got["warnings"] == "0" and got["infos"] == "1"


# ---------------------------------------------------------------------------
# 2. 왕복 무결성 — 우리가 만든 보고서를 우리 P0/P1 이 다시 소비한다
# ---------------------------------------------------------------------------


@needs_delib
def test_roundtrip_ingest_fragmentize(delib_draft: dict, tmp_path: Path):
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(delib_draft, ensure_ascii=False), encoding="utf-8")
    norm = ingest_report_file(path)
    assert norm["title"] == delib_draft["title"]
    assert len(norm["pages"]) == 4
    assert norm["search_text"]
    frags = fragmentize(norm)
    assert len(frags) > 0
    assert all(f["frag_id"].startswith(f"RA-{norm['doc_id']}-") for f in frags)


def test_minimal_run_roundtrip(tmp_path: Path):
    """선택 입력(회의·QA·렌더) 없이도 유효한 draft_v1 이 나오고 왕복이 통과한다."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "report.norm.json").write_text(json.dumps({
        "doc_id": "abcd1234", "title": "미니 보고서", "report_date": "2026-01-01",
    }), encoding="utf-8")
    (run / "scenario.json").write_text(json.dumps({
        "meta": {"core_message": "핵심", "duration_sec": 10},
        "content": {"opening": {"title": "한 줄 카피"}},
        "scenes": [{"name": "오프닝", "dur": 10, "tpl": "opening@1",
                    "data_ref": "content.opening", "narration": "내레이션"}],
    }), encoding="utf-8")
    draft = build_archive_draft(run)
    assert draft["_type"] == "report_archive_draft_v1"
    assert len(draft["pages"]) == 4
    path = tmp_path / "draft.json"
    path.write_text(json.dumps(draft, ensure_ascii=False), encoding="utf-8")
    frags = fragmentize(ingest_report_file(path))
    assert len(frags) > 0


def test_turns_table_omission_marker(tmp_path: Path):
    """20턴 초과 시 20행으로 캡하고 마지막 행에 생략을 표기한다."""
    run = tmp_path / "run"
    run.mkdir()
    (run / "report.norm.json").write_text(json.dumps({
        "doc_id": "abcd1234", "title": "긴 회의", "report_date": "2026-01-01",
    }), encoding="utf-8")
    (run / "scenario.json").write_text(json.dumps({
        "meta": {}, "content": {}, "scenes": [],
    }), encoding="utf-8")
    meeting = tmp_path / "meeting"
    meeting.mkdir()
    turns = [
        {"turn_no": i, "round_no": 1, "role": "expert",
         "expert_id": f"p{i}", "stance": "propose", "content_md": f"발언 {i}"}
        for i in range(1, 26)
    ]
    (meeting / "turns.jsonl").write_text(
        "\n".join(json.dumps(t, ensure_ascii=False) for t in turns), encoding="utf-8"
    )
    draft = build_archive_draft(run, meeting_dir=meeting)
    rows = draft["pages"][1]["content"]["tbl_turns"]["rows"]
    assert len(rows) == 20
    assert "생략" in rows[-1]["gist"]
    assert "6턴" in rows[-1]["gist"]  # 25 - 19


# ---------------------------------------------------------------------------
# 3. 업로드 게이트 — 자격증명 없으면 명확히 실패
# ---------------------------------------------------------------------------


def test_submit_draft_without_credentials(monkeypatch: pytest.MonkeyPatch):
    for var in ("WDA_RA_BASE_URL", "WDA_RA_EMAIL", "WDA_RA_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="자격증명 미설정"):
        submit_draft({"title": "x", "pages": []})


def test_submit_draft_partial_credentials(monkeypatch: pytest.MonkeyPatch):
    """base_url 만 있어도 이메일·비밀번호가 없으면 켜지지 않는다."""
    monkeypatch.setenv("WDA_RA_BASE_URL", "http://localhost:3000")
    for var in ("WDA_RA_EMAIL", "WDA_RA_PASSWORD"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="자격증명 미설정"):
        submit_draft({"title": "x", "pages": []})
