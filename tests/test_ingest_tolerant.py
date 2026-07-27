# wdpipeline.ingest 관용 입력 테스트 — draft/REST 봉투/pages 조각/마크다운 4형태와 기존 결과 회귀
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wdpipeline.ingest import (
    FORM_DRAFT,
    FORM_MARKDOWN,
    FORM_PAGES,
    FORM_REST,
    ingest_report_file,
    markdown_to_draft,
    normalize_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
FIXTURES = REPO_ROOT / "data" / "widget_check"

# 관용 파서 도입 전 실측값 — 이 숫자가 바뀌면 기존 입력의 정규화가 변한 것이다
BASELINE = {"doc_id": "d077508a", "pages": 5, "blocks": 44, "search_text_len": 8425}

RA_ENV = ("WDA_RA_BASE_URL", "WDA_RA_TOKEN", "WDA_RA_EMAIL", "WDA_RA_PASSWORD")


@pytest.fixture(autouse=True)
def no_rest_env(monkeypatch: pytest.MonkeyPatch):
    for key in RA_ENV:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture(scope="module")
def sample() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def _blocks(norm: dict) -> int:
    return sum(len(p["blocks"]) for p in norm["pages"])


# --- ① 기존 복붙 draft — 결과가 변하면 안 된다 -----------------------------


def test_draft_form_regression():
    norm = ingest_report_file(SAMPLE)
    assert norm["source_format"] == FORM_DRAFT
    assert norm["doc_id"] == BASELINE["doc_id"]
    assert len(norm["pages"]) == BASELINE["pages"]
    assert _blocks(norm) == BASELINE["blocks"]
    assert len(norm["search_text"]) == BASELINE["search_text_len"]
    assert norm["tags"] == ["설명서", "플랫폼 가이드", "온보딩"]
    assert norm["ai_summary"] is None
    assert norm["assets"] == []


def test_assets_meta_added_alongside_assets(tmp_path: Path):
    """assets 는 2키 계약 유지, 사유·이미지 메타는 assets_meta 로 덧붙는다."""
    raw = {
        "_type": "report_archive_draft_v1",
        "title": "자산", "report_date": "2026-01-01", "tags": [],
        "pages": [{
            "name": "p1",
            "extra_blocks": [{"id": "i1", "type": "image", "props": {"file_id": "f-x"}}],
            "content": {"i1": {"caption": "그림"}},
            "blocks_order": [], "block_sections": {},
        }],
    }
    norm = normalize_report(raw)
    assert norm["assets"] == [{"file_id": "f-x", "local_path": None}]
    (meta,) = norm["assets_meta"]
    assert meta["file_id"] == "f-x"
    assert meta["status"] == "unresolved"
    assert meta["reason"]


# --- ② REST 응답 원형 -------------------------------------------------------


def _rest_envelope(sample: dict) -> dict:
    """{success, data:{...}} 봉투 + ReportRead 메타 키 + 1페이지 인라인 content."""
    pages = []
    for i, page in enumerate(sample["pages"]):
        content = dict(page.get("content") or {})
        extra = []
        for b in page["extra_blocks"]:
            eb = {"id": b["id"], "type": b["type"], "props": b.get("props") or {}}
            if i == 0 and b["id"] in content:
                eb["content"] = content.pop(b["id"])
            extra.append(eb)
        pages.append({
            "name": page["name"], "extra_blocks": extra, "content": content,
            "blocks_order": page.get("blocks_order") or [],
            "block_sections": page.get("block_sections") or {},
        })
    return {
        "success": True,
        "data": {
            "id": 578,
            "title": sample["title"],
            "created_at": f"{sample['report_date']}T09:12:33Z",
            "tags": [{"name": t} for t in sample["tags"]],
            "search_text": "서버가 만들어 준 평탄화 평문",
            "ai_summary": {"core_message": "핵심"},
            "pages": pages,
        },
    }


def test_rest_envelope_normalizes_same_structure(sample: dict):
    norm = normalize_report(_rest_envelope(sample))
    assert norm["source_format"] == FORM_REST
    assert len(norm["pages"]) == BASELINE["pages"]
    assert _blocks(norm) == BASELINE["blocks"]          # 인라인 content 도 유실 없음
    assert norm["title"] == sample["title"]
    assert norm["report_date"] == sample["report_date"]  # created_at 에서 파생
    assert norm["tags"] == sample["tags"]                # [{name}] 표기 흡수
    assert norm["doc_id"] == "578"                       # 서버 id 를 doc_id 로
    assert norm["search_text"] == "서버가 만들어 준 평탄화 평문"  # 서버 제공분 우선
    assert norm["ai_summary"] == {"core_message": "핵심"}


def test_rest_inline_content_preserved(sample: dict):
    """extra_blocks 안의 content(ai-draft 형태)가 content 맵 없이도 살아야 한다."""
    norm = normalize_report(_rest_envelope(sample))
    first = norm["pages"][0]["blocks"][0]
    assert first["id"] == "h1_intro"
    assert first["content"] == {"text": "ReportArchive 플랫폼 개요"}


def test_rest_bare_reportread(sample: dict):
    """봉투 없이 GET /api/reports/{id} 본문만 와도 받는다."""
    norm = normalize_report(_rest_envelope(sample)["data"])
    assert norm["source_format"] == FORM_REST
    assert _blocks(norm) == BASELINE["blocks"]


def test_template_slot_blocks_recovered(sample: dict):
    """정의 없이 blocks 슬롯에만 있는 content 도 타입 추정으로 살린다(조용한 유실 금지)."""
    env = _rest_envelope(sample)
    env["data"]["pages"][0]["blocks"] = {"slot_note": {"markdown": "슬롯 문단"}}
    norm = normalize_report(env)
    slot = [b for b in norm["pages"][0]["blocks"] if b["id"] == "slot_note"]
    assert slot and slot[0]["type"] == "rich_text"
    assert slot[0]["content"] == {"markdown": "슬롯 문단"}
    # 서버 search_text 가 없는 입력이면 슬롯 내용까지 자체 생성 평문에 들어간다
    del env["data"]["search_text"]
    assert "슬롯 문단" in normalize_report(env)["search_text"]


# --- ③ pages 배열만 있는 조각 ----------------------------------------------


def test_pages_only_list(sample: dict):
    norm = normalize_report(sample["pages"][:2])
    assert norm["source_format"] == FORM_PAGES
    assert len(norm["pages"]) == 2
    assert norm["title"] == "ReportArchive 플랫폼 개요"  # 첫 heading 에서 승격
    assert norm["report_date"] == ""
    assert len(norm["doc_id"]) == 8                       # 메타 없으면 해시 파생


def test_pages_only_dict(sample: dict):
    norm = normalize_report({"pages": sample["pages"][:1]})
    assert norm["source_format"] == FORM_PAGES
    assert len(norm["pages"]) == 1


def test_single_page_without_pages_key(sample: dict):
    """페이지 한 장만 통째로 들어와도 한 페이지 보고서로 받는다."""
    norm = normalize_report(sample["pages"][0])
    assert len(norm["pages"]) == 1
    assert _blocks(norm) == len(sample["pages"][0]["extra_blocks"])


def test_blocks_order_partial_keeps_all_blocks():
    """blocks_order 에 빠진 블록도 뒤에 붙는다 — 순서 지정 실수로 내용이 사라지지 않게."""
    raw = {
        "pages": [{
            "name": "p1",
            "extra_blocks": [
                {"id": "a", "type": "heading", "props": {}},
                {"id": "b", "type": "heading", "props": {}},
                {"id": "c", "type": "heading", "props": {}},
            ],
            "content": {"a": {"text": "A"}, "b": {"text": "B"}, "c": {"text": "C"}},
            "blocks_order": ["c"],
        }],
    }
    norm = normalize_report(raw)
    assert [b["id"] for b in norm["pages"][0]["blocks"]] == ["c", "a", "b"]


# --- ④ 마크다운 --------------------------------------------------------------


MD = """# 심의 플랫폼 도입 검토

현행 검토는 담당자 개인의 감에 의존한다.

## 문제

- 기준이 문서마다 다르다
- 결론까지 9일이 걸린다

| 항목 | 현행 | 목표 |
| --- | --- | --- |
| 검토 소요 | 9일 | 2일 |
| 추적률 | 31% | 95% |

# 결론

1. 1분기 파일럿
2. 2분기 확대
"""


def test_markdown_structure_preserved():
    norm = normalize_report(MD)
    assert norm["source_format"] == FORM_MARKDOWN
    assert norm["title"] == "심의 플랫폼 도입 검토"
    assert [p["name"] for p in norm["pages"]] == ["심의 플랫폼 도입 검토", "결론"]

    types = [b["type"] for b in norm["pages"][0]["blocks"]]
    assert types == ["heading", "rich_text", "heading", "bulleted_list", "table"]

    heading = norm["pages"][0]["blocks"][2]
    assert heading["props"]["level"] == 2
    assert heading["content"] == {"text": "문제"}

    bullets = norm["pages"][0]["blocks"][3]["content"]["items"]
    assert bullets == ["기준이 문서마다 다르다", "결론까지 9일이 걸린다"]


def test_markdown_table_becomes_table_widget():
    norm = normalize_report(MD)
    table = norm["pages"][0]["blocks"][4]
    assert table["type"] == "table"
    assert [c["label"] for c in table["props"]["columns"]] == ["항목", "현행", "목표"]
    assert table["content"]["rows"][0] == {"c1": "검토 소요", "c2": "9일", "c3": "2일"}
    assert len(table["content"]["rows"]) == 2


def test_markdown_numbered_list_is_bulleted_list():
    norm = normalize_report(MD)
    last_page = norm["pages"][1]
    items = [b for b in last_page["blocks"] if b["type"] == "bulleted_list"][0]
    assert items["content"]["items"] == ["1분기 파일럿", "2분기 확대"]


def test_markdown_code_fence_preserved():
    norm = normalize_report("# 제목\n\n```python\nrun()\n```\n")
    fence = norm["pages"][0]["blocks"][1]
    assert fence["type"] == "rich_text"
    assert "```python" in fence["content"]["markdown"]
    assert "run()" in fence["content"]["markdown"]


def test_markdown_file_read_by_suffix(tmp_path: Path):
    path = tmp_path / "notes.md"
    path.write_text(MD, encoding="utf-8")
    norm = ingest_report_file(path)
    assert norm["source_format"] == FORM_MARKDOWN
    assert len(norm["pages"]) == 2


def test_non_json_file_falls_back_to_markdown(tmp_path: Path):
    path = tmp_path / "notes.json"  # 확장자는 json 인데 내용은 마크다운
    path.write_text(MD, encoding="utf-8")
    assert ingest_report_file(path)["source_format"] == FORM_MARKDOWN


def test_markdown_to_draft_roundtrips_through_draft_path():
    draft = markdown_to_draft(MD)
    assert draft["_type"] == "report_archive_draft_v1"
    assert normalize_report(draft)["source_format"] == FORM_DRAFT


# --- 판별 실패 시 안내 -------------------------------------------------------


def test_unknown_input_lists_expected_forms(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"foo": 1, "bar": 2}), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        ingest_report_file(bad)
    msg = str(exc.value)
    assert "report_archive_draft_v1" in msg   # ① 기대 형태
    assert "ReportRead" in msg                # ②
    assert "pages" in msg                     # ③
    assert "마크다운" in msg                  # ④
    assert "foo" in msg and "bar" in msg      # 받은 것 진단


def test_empty_pages_rejected():
    with pytest.raises(ValueError, match="pages 가 비어 있다"):
        normalize_report({"_type": "report_archive_draft_v1", "title": "t", "pages": []})


def test_untitled_pages_without_heading_rejected():
    raw = {"pages": [{"name": "", "extra_blocks": [
        {"id": "a", "type": "rich_text", "props": {}}], "content": {"a": {"markdown": "본문"}}}]}
    with pytest.raises(ValueError, match="title 을 찾지 못했다"):
        normalize_report(raw)


# --- data/widget_check 픽스처(있을 때만) -------------------------------------


@pytest.mark.skipif(
    not (FIXTURES / "rest_envelope.json").is_file(),
    reason="data/widget_check 픽스처 없음 — data/widget_check/make_fixtures.py 로 생성",
)
def test_stored_fixtures_ingest():
    forms = {
        "rest_envelope.json": FORM_REST,
        "pages_only.json": FORM_PAGES,
        "human_notes.md": FORM_MARKDOWN,
        "report_with_images.json": FORM_DRAFT,
    }
    for name, form in forms.items():
        norm = ingest_report_file(FIXTURES / name)
        assert norm["source_format"] == form, name
        assert norm["pages"], name
