# 심의 장르 테스트 — 심의 보고서의 결정문·근거·액션 담당이 씬 데이터까지 도달하는지 검증
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wdpipeline.fragmentize import fragmentize, infer_section
from wdpipeline.format import list_formats, load_format
from wdpipeline.ingest import normalize_report
from wdpipeline.scenario import _BUILDERS, assemble_demo_scenario, validate_scenario

REPO_ROOT = Path(__file__).resolve().parents[1]
FORMAT_ID = "delib-16x9"

# 포털(hwax-deliberation) 심의 템플릿 꼴 — heading 4 + rich_text 4.
# rich_text content 는 {"markdown": ...}, heading 은 {"text": ...} 다(RA 실제 꼴).
DELIB_REPORT = {
    "_type": "report_archive_draft_v1",
    "title": "리스크 심의 — 배터리 셀 팽창 여유 설계 검토",
    "report_date": "2026-11-01",
    "tags": ["심의", "리스크"],
    "pages": [
        {
            "template_id": "deliberation",
            "template_version": 1,
            "name": "심의 결과",
            "extra_blocks": [
                {"id": "h_q", "type": "heading", "props": {"level": 1, "default_text": "화두"}},
                {"id": "rt_q", "type": "rich_text", "props": {}},
                {"id": "h_r", "type": "heading", "props": {"level": 1, "default_text": "라운드 요지"}},
                {"id": "rt_r", "type": "rich_text", "props": {}},
                {"id": "h_d", "type": "heading", "props": {"level": 1, "default_text": "의사결정문"}},
                {"id": "rt_d", "type": "rich_text", "props": {}},
                {"id": "h_a", "type": "heading", "props": {"level": 1, "default_text": "액션아이템"}},
                {"id": "rt_a", "type": "rich_text", "props": {}},
            ],
            "content": {
                "h_q": {"text": "화두"},
                "rt_q": {"markdown": "셀 팽창 여유를 현행 **1.2mm** 에서 줄일 수 있는가. "
                                     "줄이면 에너지 밀도가 오르지만 수명 말기 변형을 감당해야 한다."},
                "h_r": {"text": "라운드 요지"},
                "rt_r": {"markdown": "- **R1** 구조는 0.9mm 까지 견딘다고 보고.\n"
                                     "- **R2** 구조가 열의 경계조건을 반박했다.\n"
                                     "- **R3** 양측이 1.0mm 로 수렴했다."},
                "h_d": {"text": "의사결정문"},
                "rt_d": {"markdown": "셀 팽창 여유를 **1.0mm** 로 정한다. "
                                     "근거는 수명 말기 변형 실측 0.82mm 에 안전율 1.2 다. "
                                     "에너지 밀도는 2.1% 오른다."},
                "h_a": {"text": "액션아이템"},
                "rt_a": {"markdown": "- **A1 구조** 0.9mm 조건의 최악 경계조건을 재계산한다.\n"
                                     "- **A2 열** 1.0mm 에서 국부 온도를 재측정한다.\n"
                                     "- **A3 품질** 수명 말기 변형 표본을 30개로 확대한다."},
            },
            "blocks_order": ["h_q", "rt_q", "h_r", "rt_r", "h_d", "rt_d", "h_a", "rt_a"],
        }
    ],
}


@pytest.fixture(scope="module")
def delib():
    norm = normalize_report(DELIB_REPORT)
    return norm, fragmentize(norm)


# ── 섹션 추론 ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "heading,expected",
    [
        ("화두", "topic"), ("심의 주제", "topic"),
        ("라운드 요지", "round"), ("논의 경과", "round"),
        ("의사결정문", "decision"), ("결론", "decision"),
        ("액션아이템", "action_item"), ("후속 조치", "action_item"),
        ("쟁점 정리", "problem"), ("리스크", "problem"),
    ],
)
def test_infer_section(heading, expected):
    assert infer_section(heading) == expected


def test_infer_section_ignores_unrelated_headings():
    """심의 어휘가 아닌 제목은 추론하지 않는다 — 기존 보고서 조립을 건드리지 않기 위함."""
    for h in ("기술 스택", "도입 목적", "3계층 시스템 구조", ""):
        assert infer_section(h) is None


def test_heading_propagates_section_to_following_blocks(delib):
    _, frags = delib
    by_section: dict[str | None, list[str]] = {}
    for f in frags:
        by_section.setdefault(f.get("section"), []).append(f["text"])
    assert set(by_section) == {"topic", "round", "decision", "action_item"}


# ── 빌더 도달 경로 ───────────────────────────────────────────────────────


def test_every_scene_template_has_a_builder():
    """템플릿이 있어도 _BUILDERS 에 없으면 조립이 거부한다 — 등록만 된 템플릿을 잡는다."""
    shorts = {d.name for d in (REPO_ROOT / "modules" / "scene-templates").iterdir() if d.is_dir()}
    # vtpl.* 는 v- 접두를 떼고 등록돼 있다 (vtpl.hook → "hook")
    unreachable = {s for s in shorts
                   if s not in _BUILDERS and s.removeprefix("v-") not in _BUILDERS}
    assert unreachable == set(), f"조립 경로가 없는 템플릿: {sorted(unreachable)}"


# ── 포맷 ─────────────────────────────────────────────────────────────────


def test_format_registered_and_loadable():
    assert FORMAT_ID in list_formats()
    spec = load_format(FORMAT_ID)
    assert spec.skeleton == ["topic", "stakes", "rounds", "decision", "action", "summary"]
    assert [spec.primary_tpl(r) for r in spec.skeleton] == [
        "tpl.o-question", "tpl.l-quote", "tpl.concept",
        "tpl.o-statement", "tpl.x-next", "tpl.x-summary",
    ]


def test_scene_names_are_distinct_across_skeleton():
    """한 골격에 같은 scene_name_default 둘이 들어가면 이름이 역할명으로 떨어진다."""
    doc = assemble_demo_scenario(*_built())
    names = [s.name for s in doc.scenes]
    assert len(set(names)) == len(names), names
    assert "decision" not in names   # 역할명 노출 회귀 방지


def _built():
    norm = normalize_report(DELIB_REPORT)
    return norm, fragmentize(norm), FORMAT_ID


def test_delib_scenario_validates():
    doc = assemble_demo_scenario(*_built())
    assert validate_scenario(doc) == []
    assert len(doc.scenes) == 6
    assert sum(s.dur for s in doc.scenes) == pytest.approx(64.0)


# 이 테스트가 이 작업의 존재 이유다 — 조립은 늘 "성공" 했고, 유실된 것은 내용이었다.
@pytest.mark.parametrize(
    "needle",
    [
        "1.0mm",    # 결정값
        "0.82mm",   # 결정 근거 실측
        "2.1%",     # 결정의 효과
        "구조", "열", "품질",   # 액션 담당 3인
        "30개",     # 액션 세부
    ],
)
def test_delib_substance_reaches_scenes(needle):
    blob = json.dumps(assemble_demo_scenario(*_built()).model_dump(), ensure_ascii=False)
    assert needle in blob, f"심의 보고서의 '{needle}' 이 씬 데이터에 없다"


@pytest.mark.parametrize("filler", ["보고서 참조", "보고서 내용 정리", "보고서 근거로 정리", "항목 1"])
def test_delib_has_no_filler(filler):
    """자리 채우기 문자열이 납품물로 나가지 않는다 — 조용한 오납의 표지였다."""
    blob = json.dumps(assemble_demo_scenario(*_built()).model_dump(), ensure_ascii=False)
    assert filler not in blob


def test_action_owners_and_steps():
    doc = assemble_demo_scenario(*_built())
    action = doc.model_dump()["content"]["action"]
    owners = [s["owner"] for s in action["steps"]]
    assert owners[:3] == ["구조", "열", "품질"]
    # 원문에 시점이 없으면 지어내지 않는다
    assert all(s["when"] == "후속" for s in action["steps"])
    assert action["decision"]["headline"].startswith("셀 팽창 여유")


def test_rounds_carry_codes_and_subjects():
    rounds = assemble_demo_scenario(*_built()).model_dump()["content"]["rounds"]["rounds"]
    assert [r["chip"] for r in rounds] == ["R1", "R2", "R3"]
    assert all(r["desc"] for r in rounds)


# ── 기존 포맷 불변 ───────────────────────────────────────────────────────


def test_wide_format_unaffected_by_delib_sections():
    """심의 섹션 어휘는 오늘 신설했다 — 심의 섹션이 없는 보고서는 종전 골격 그대로다."""
    sample = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
    norm = normalize_report(json.loads(sample.read_text(encoding="utf-8")))
    frags = fragmentize(norm)
    # 표본은 block_sections 를 명시로 갖는다(RA 정본 어휘). 심의 전용 round 는 없으므로
    # concept 의 라운드 분기가 걸리지 않는다 — 이것이 wide 골격 불변의 근거다.
    assert "round" not in {f.get("section") for f in frags}
    doc = assemble_demo_scenario(norm, frags)
    assert [s.name for s in doc.scenes] == [
        "오프닝", "문제", "개념", "절차", "차별점", "실증", "클로징",
    ]


# ── 명시 태그 경로 (block_sections 가 RA 정본 어휘로 들어오는 보고서) ─────────


def _explicit_report() -> dict:
    """heading 으로는 알 수 없고 block_sections 만으로 심의임을 알리는 보고서.

    추론 경로가 아니라 **정본 어휘 경로**를 탄다. 섹션 id 를 새로 지어냈다면 이 테스트가
    실패한다 — RA 가 쓰는 이름(action_item·alternatives·decision)과 같아야 한다.
    """
    page = {
        "template_id": "deliberation", "template_version": 1, "name": "심의",
        "extra_blocks": [
            {"id": f"rt{i}", "type": "rich_text", "props": {}} for i in range(1, 5)
        ],
        "content": {
            "rt1": {"markdown": "셀 팽창 여유를 현행 1.2mm 에서 줄일 수 있는가."},
            "rt2": {"markdown": "- A1 구조 0.9mm 안을 제시했다.\n"
                                "- A2 열 1.1mm 안을 제시했다.\n"
                                "- A3 품질 1.0mm 안을 제시했다."},
            "rt3": {"markdown": "셀 팽창 여유를 1.0mm 로 정한다. 근거는 실측 0.82mm 다."},
            "rt4": {"markdown": "- B1 구조 경계조건을 재계산한다.\n"
                                "- B2 열 국부 온도를 재측정한다.\n"
                                "- B3 품질 표본을 30개로 확대한다."},
        },
        "block_sections": {"rt1": "purpose", "rt2": "alternatives",
                           "rt3": "decision", "rt4": "action_item"},
        "blocks_order": ["rt1", "rt2", "rt3", "rt4"],
    }
    return {"_type": "report_archive_draft_v1", "title": "셀 팽창 여유 심의",
            "report_date": "2026-11-01", "tags": ["심의"], "pages": [page]}


def test_explicit_ra_sections_are_consumed():
    norm = normalize_report(_explicit_report())
    frags = fragmentize(norm)
    assert {"alternatives", "decision", "action_item"} <= {f.get("section") for f in frags}
    doc = assemble_demo_scenario(norm, frags, FORMAT_ID)
    assert validate_scenario(doc) == []
    blob = json.dumps(doc.model_dump(), ensure_ascii=False)
    for needle in ("1.0mm", "0.82mm", "30개"):
        assert needle in blob, needle
    action = doc.model_dump()["content"]["action"]
    assert [s["owner"] for s in action["steps"]][:3] == ["구조", "열", "품질"]
    # alternatives 가 라운드 자리를 채운다 — 검토된 입장이 곧 라운드다
    assert [r["chip"] for r in doc.model_dump()["content"]["rounds"]["rounds"]] == \
        ["A1", "A2", "A3"]


def test_explicit_sections_win_over_heading_inference():
    """명시 태그가 있으면 heading 추론은 덮지 않는다."""
    rep = _explicit_report()
    rep["pages"][0]["extra_blocks"].insert(
        0, {"id": "h0", "type": "heading", "props": {"level": 1, "default_text": "액션아이템"}})
    rep["pages"][0]["content"]["h0"] = {"text": "액션아이템"}
    rep["pages"][0]["blocks_order"].insert(0, "h0")
    frags = fragmentize(normalize_report(rep))
    by_id = {f["source"]["block_id"]: f.get("section") for f in frags}
    assert by_id["rt3"] == "decision"      # 명시 태그 유지 (추론값 action_item 이 아니다)
    assert by_id["h0"] == "action_item"    # 태그 없는 heading 은 추론값


# ── C-6 / C-7 (제작 심의 2026-11-01 조건) ────────────────────────────────


def test_presets_audience_reaches_meta():
    """청중·톤은 포맷 프리셋이 정본이다 — 선언만 하고 도달하지 않으면 빈칸과 같다."""
    from wdpipeline.format import load_format

    spec = load_format(FORMAT_ID)
    assert spec.presets.audience and spec.presets.tone, "프리셋에 청중·톤이 비었다"
    doc = assemble_demo_scenario(*_built())
    assert doc.meta.audience == spec.presets.audience
    assert doc.meta.tone == spec.presets.tone


def test_core_message_is_the_decision_not_the_title():
    """심의 보고서가 남길 한 문장은 결정이다. 제목은 '무엇에 대한' 일 뿐이다."""
    doc = assemble_demo_scenario(*_built())
    assert "1.0mm" in doc.meta.core_message
    assert doc.meta.core_message != normalize_report(DELIB_REPORT)["title"]


def test_stakes_scene_keeps_the_tradeoff_sentence():
    """화두의 둘째 문장(득실)은 질문 슬롯(1~2행×18자)에 들어가지 않아 통째로 사라졌었다."""
    doc = assemble_demo_scenario(*_built())
    assert "stakes" in doc.content, doc.content.keys()
    quote = doc.content["stakes"]["quote"]
    assert "에너지 밀도" in quote and "수명 말기 변형" in quote
    assert not quote.endswith("…"), f"쟁점 문장이 잘렸다: {quote}"


def test_mcp_ledger_survives_a_fresh_session():
    """MCP 서버가 재기동해도 known_refs 가 살아 있어야 한다 — 없으면 정당한 인용이 거부된다."""
    from wdmcp.ledger_store import hydrate, ledger_path, persist
    from wdmcp.session import MeetingLedger, SessionState

    from wdweb.deliberation import call_tool

    out = call_tool("meeting_start", topic="원장 영속 회귀", type="design_review",
                    participants=["impl-technical-director", "qa-consistency"])
    mid = out["data"]["meeting_id"]
    assert ledger_path(mid) is not None

    seeded = SessionState()
    seeded.meetings[mid] = MeetingLedger(known_refs={"AX-C-001"}, format_id=FORMAT_ID)
    persist(seeded, mid)

    fresh = SessionState()                 # 재기동한 프로세스를 흉내낸다
    hydrate(fresh, mid)
    assert "AX-C-001" in fresh.meetings[mid].known_refs
    assert fresh.meetings[mid].format_id == FORMAT_ID


def test_stakes_falls_back_to_the_question_not_the_rounds():
    """득실 문장이 없으면 화두 자체를 싣는다 — 라운드 경과가 쟁점 자리에 들어가면 안 된다."""
    rep = json.loads(json.dumps(DELIB_REPORT))
    rep["pages"][0]["content"]["rt_q"] = {"markdown": "셀 팽창 여유를 줄일 수 있는가."}
    norm = normalize_report(rep)
    doc = assemble_demo_scenario(norm, fragmentize(norm), FORMAT_ID)
    quote = doc.content["stakes"]["quote"]
    assert "줄일 수 있는가" in quote
    assert "R1" not in quote and "수렴" not in quote
