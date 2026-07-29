# 문서 조립기 테스트 — 번호 매김·참조 정합·미해결 쟁점 필수 수록·빈 입력 거부·구어체 잔존 0
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from wdpipeline.document import (
    REF_CATEGORIES,
    SPOKEN_RESIDUE,
    STYLE_BUDGETS,
    assemble_document,
    to_written,
    validate_document,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
RUN = REPO_ROOT / "data" / "pipeline" / "delib_v2"
STILLS = REPO_ROOT / "data" / "quality_compare" / "v2"

_REF_TOKEN = re.compile(r"\((그림|표) (\d+)\)")


@pytest.fixture(scope="module")
def doc() -> dict:
    if not (RUN / "scenario.json").is_file():
        pytest.skip(f"확정 심의 산출물이 없다: {RUN}")
    return assemble_document(RUN)


def _bodies(doc: dict) -> list[str]:
    return [p for s in doc["sections"] for p in s["body"]]


# ── 문체 변환 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("spoken", "written"),
    [
        ("보고서는 한 번만 작성합니다.", "보고서는 한 번만 작성한다."),
        ("구조는 세 계층입니다.", "구조는 세 계층이다."),
        ("개인 초안과 공식 보고가 뒤섞입니다.", "개인 초안과 공식 보고가 뒤섞인다."),
        ("최신본은 메일함 사본 속에 숨었습니다.", "최신본은 메일함 사본 속에 숨었다."),
        ("수정은 즉시 반영됩니다.", "수정은 즉시 반영된다."),
        ("위젯이 본문 작성을 받칩니다.", "위젯이 본문 작성을 받친다."),
        ("취합은 리포트아카이브에 맡기십시오.", "취합은 리포트아카이브에 맡기는 것을 권한다."),
        ("보시다시피 사본이 넷입니다.", "그림에서 보듯 사본이 넷이다."),
        ("최신본이 어느 파일입니까?", "최신본이 어느 파일인가?"),
        ("브리핑을 시작하겠습니다.", "브리핑을 시작한다."),
    ],
)
def test_to_written_maps_spoken_to_prose(spoken: str, written: str):
    assert to_written(spoken) == written


def test_to_written_keeps_plain_style_intact():
    # "아니다"는 종성 ㅂ이 없어 합쇼체 탐지에 걸리지 않는다 (오검출 회귀 방지)
    text = "사본이 아니라 살아 있는 연결이다. 그것은 사본이 아니다."
    assert to_written(text) == text
    assert not SPOKEN_RESIDUE.search(text)


# ── 본문 ────────────────────────────────────────────────────────────────


def test_no_spoken_residue_in_prose(doc: dict):
    targets = (
        _bodies(doc)
        + [doc["summary"]["lead"], *doc["summary"]["bullets"]]
        + [s["heading"] for s in doc["sections"]]
        + [f["caption"] for s in doc["sections"] for f in s["figures"]]
    )
    hits = [(t, SPOKEN_RESIDUE.search(t).group(0)) for t in targets if SPOKEN_RESIDUE.search(t)]
    assert hits == []


def test_paragraphs_have_reading_breath(doc: dict):
    lo, hi = STYLE_BUDGETS["report"]["sent"]
    for para in _bodies(doc):
        n = len(re.findall(r"[.!?](\s|$)", para))
        assert n <= hi, f"문단이 {n}문장 — 상한 {hi}: {para[:60]}"
    first = doc["sections"][0]["body"][0]
    assert len(re.findall(r"[.!?](\s|$)", first)) >= lo


# ── 번호 매김 · 참조 정합 ───────────────────────────────────────────────


def test_figure_and_table_numbering_is_sequential(doc: dict):
    fig_word, fig_anchor = REF_CATEGORIES["figure"]
    tbl_word, tbl_anchor = REF_CATEGORIES["table"]
    figs = [f for s in doc["sections"] for f in s["figures"]]
    tbls = [t for s in doc["sections"] for t in s["tables"]]
    assert [f["no"] for f in figs] == list(range(1, len(figs) + 1))
    assert [t["no"] for t in tbls] == list(range(1, len(tbls) + 1))
    for f in figs:
        assert f["ref"] == f"{fig_word} {f['no']}"
        assert f["anchor"] == f"{fig_anchor}-{f['no']}"
    for t in tbls:
        assert t["ref"] == f"{tbl_word} {t['no']}"
        assert t["anchor"] == f"{tbl_anchor}-{t['no']}"


def test_body_references_match_declared_figures(doc: dict):
    declared = {f["ref"] for s in doc["sections"] for f in s["figures"]}
    declared |= {t["ref"] for s in doc["sections"] for t in s["tables"]}
    referenced = {f"{w} {n}" for p in _bodies(doc) for w, n in _REF_TOKEN.findall(p)}
    assert referenced == declared


def test_figure_ref_points_at_a_real_paragraph(doc: dict):
    for sec in doc["sections"]:
        for ref in sec["figure_ref"]:
            assert 0 <= ref["paragraph"] < len(sec["body"])
            assert ref["ref"] in sec["body"][ref["paragraph"]]
            assert ref["kind"] in ("figure", "table")


def test_toc_matches_sections(doc: dict):
    assert [t["no"] for t in doc["toc"]] == [s["no"] for s in doc["sections"]]
    assert [t["anchor"] for t in doc["toc"]] == [s["anchor"] for s in doc["sections"]]


# ── 출처 추적 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("style", ["report", "brief", "memo"])
def test_notes_are_traceable_to_appendix_sources(style: str):
    d = assemble_document(RUN, style=style)
    refs = {r["ref"] for r in d["appendix"]["sources"]}
    assert refs, "부록 출처가 비었다"
    cited = {
        re.match(r"^\[([^\]]+)\]", n).group(1)
        for s in d["sections"] for n in s["notes"]
    }
    assert cited <= refs
    for src in d["appendix"]["sources"]:
        assert src["page"] and src["block_id"], src


def test_tables_keep_original_row_count_when_truncated(doc: dict):
    limit = STYLE_BUDGETS["report"]["table_rows"]
    tbls = [t for s in doc["sections"] for t in s["tables"]]
    assert tbls, "표가 하나도 실리지 않았다"
    for t in tbls:
        assert len(t["rows"]) <= limit
        assert t["rows_total"] >= len(t["rows"])
        assert all(len(row) == len(t["columns"]) for row in t["rows"])


# ── 심의 부록 ───────────────────────────────────────────────────────────


def test_appendix_carries_deliberation_with_open_issues(doc: dict):
    delib = doc["appendix"]["deliberation"]
    assert delib["meeting_id"]
    assert len(delib["participants"]) == 7
    assert delib["decisions"], "결정이 비었다"
    assert delib["action_items"], "액션아이템이 비었다"
    assert delib["open_issues"], "미해결 쟁점이 비었다 — 합의 연출 방지 원칙"
    assert [r["round"] for r in delib["rounds"]] == ["R1", "R2", "R3", "R4"]
    assert sum(r["turns"] for r in delib["rounds"]) == 25


# ── 문체 예산 ───────────────────────────────────────────────────────────


def test_styles_differ_in_volume(doc: dict):
    sizes = {}
    for style in ("report", "brief", "memo"):
        d = assemble_document(RUN, style=style)
        assert validate_document(d) == []
        sizes[style] = sum(len(p) for s in d["sections"] for p in s["body"])
        assert len(d["sections"]) == (
            len(d["toc"])
        )
    assert sizes["report"] > sizes["brief"] > sizes["memo"]


def test_brief_and_memo_merge_sections():
    brief = assemble_document(RUN, style="brief")
    memo = assemble_document(RUN, style="memo")
    assert len(brief["sections"]) == 3
    assert [s["heading"] for s in brief["sections"]] == list(STYLE_BUDGETS["brief"]["headings"])
    assert len(memo["sections"]) == 1
    assert sum(len(s["tables"]) for s in memo["sections"]) == 0


def test_stills_resolve_when_capture_dir_given():
    if not STILLS.is_dir():
        pytest.skip(f"스틸 캡처본이 없다: {STILLS}")
    d = assemble_document(RUN, build_dir=STILLS)
    figs = [f for s in d["sections"] for f in s["figures"]]
    assert figs and all(f["source_path"] for f in figs)
    assert len({f["source_path"] for f in figs}) == len(figs)


# ── 검증기 ──────────────────────────────────────────────────────────────


def test_validate_passes_on_confirmed_run(doc: dict):
    assert validate_document(doc) == []


def test_validate_detects_duplicate_numbers(doc: dict):
    broken = json.loads(json.dumps(doc))
    figs = [f for s in broken["sections"] for f in s["figures"]]
    figs[1]["no"] = figs[0]["no"]
    assert any("그림 번호 중복" in e for e in validate_document(broken))


def test_validate_detects_dangling_reference(doc: dict):
    broken = json.loads(json.dumps(doc))
    broken["sections"][0]["body"][0] += " (그림 99)"
    assert any("그림 99" in e for e in validate_document(broken))


def test_validate_detects_unreferenced_figure(doc: dict):
    broken = json.loads(json.dumps(doc))
    sec = broken["sections"][0]
    sec["body"] = [p.replace(f" ({sec['figures'][0]['ref']})", "") for p in sec["body"]]
    assert any("참조되지 않는다" in e for e in validate_document(broken))


def test_validate_detects_empty_section(doc: dict):
    broken = json.loads(json.dumps(doc))
    broken["sections"][1]["body"] = []
    assert any("본문이 비었다" in e for e in validate_document(broken))


def test_validate_requires_open_issues_slot(doc: dict):
    broken = json.loads(json.dumps(doc))
    broken["appendix"]["deliberation"].pop("open_issues")
    assert any("미해결 쟁점" in e for e in validate_document(broken))


def test_validate_detects_spoken_residue(doc: dict):
    broken = json.loads(json.dumps(doc))
    broken["sections"][0]["body"][0] = "보고서는 한 번만 작성합니다."
    assert any("구어체" in e for e in validate_document(broken))


# ── 빈 입력 거부 ────────────────────────────────────────────────────────


def test_rejects_missing_run_dir(tmp_path: Path):
    with pytest.raises(ValueError, match="디렉터리가 아니다"):
        assemble_document(tmp_path / "없는run")


def test_rejects_run_without_scenario(tmp_path: Path):
    with pytest.raises(ValueError, match="scenario.json"):
        assemble_document(tmp_path)


def test_rejects_scenario_without_scenes(tmp_path: Path):
    (tmp_path / "scenario.json").write_text(
        json.dumps({"version": "1.0", "meta": {"core_message": "x", "duration_sec": 1}, "scenes": []}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        assemble_document(tmp_path)


def test_rejects_unknown_style():
    with pytest.raises(ValueError, match="style"):
        assemble_document(RUN, style="poster")
