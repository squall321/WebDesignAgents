# 사람 편집 왕복 — 시나리오 변경 대조 계약 (PLAN §11)
from __future__ import annotations

import pytest

from wdpipeline.revise import change_summary_md, diff_scenario


def _doc(scenes, **extra):
    return {"version": 1, "meta": {"title": "T"}, "scenes": scenes, **extra}


def _s(name, **kw):
    base = {"name": name, "dur": 10.0, "tpl": "opening@1", "narration": "원문",
            "stills": [], "nat": 10.0, "transition": None, "data_ref": None}
    base.update(kw)
    return base


def test_no_change_is_reported_as_no_change():
    d = _doc([_s("A"), _s("B")])
    assert diff_scenario(d, d)["changed"] is False
    assert "변경 없음" in change_summary_md(diff_scenario(d, d))


def test_build_filled_fields_are_not_human_edits():
    """빌드는 scenario.json 에 없는 format 을 해석해 scene-data.json 에 적는다.

    이걸 변경으로 세면 **모든 실행이** 매번 "format 이 사라졌다" 고 보고된다(실측).
    """
    current = _doc([_s("A")])                      # format 없음
    built = _doc([_s("A")], format="wide-16x9")    # 빌드가 채움
    assert diff_scenario(current, built)["changed"] is False


def test_real_format_change_is_still_caught():
    """빌드가 채운 경우만 면제한다 — 사람이 다른 포맷으로 바꾼 것은 변경이다."""
    d = diff_scenario(_doc([_s("A")], format="short-9x16"),
                      _doc([_s("A")], format="wide-16x9"))
    assert d["changed"] is True
    assert d["doc_fields"][0]["field"] == "format"


def test_scene_field_edits_are_listed_per_field():
    d = diff_scenario(_doc([_s("A", dur=14.0, narration="고친 문장")]),
                      _doc([_s("A")]))
    fields = {(f["field"], f["before"], f["after"]) for f in d["fields"]}
    assert ("dur", 10.0, 14.0) in fields
    assert ("narration", "원문", "고친 문장") in fields
    assert d["duration"]["delta"] == 4.0


def test_added_removed_and_reorder_are_distinguished():
    added = diff_scenario(_doc([_s("A"), _s("B")]), _doc([_s("A")]))
    assert added["scenes"]["added"] == ["B"] and not added["scenes"]["removed"]

    removed = diff_scenario(_doc([_s("A")]), _doc([_s("A"), _s("B")]))
    assert removed["scenes"]["removed"] == ["B"]

    moved = diff_scenario(_doc([_s("B"), _s("A")]), _doc([_s("A"), _s("B")]))
    assert moved["scenes"]["reordered"] is True, "순서는 논증의 흐름이다 — 변경으로 세야 한다"


def test_meta_is_compared_key_by_key():
    """통째로 비교하면 'meta 가 바뀜' 한 줄만 나와 무엇이 바뀌었는지 알 수 없다."""
    d = diff_scenario(_doc([_s("A")], meta={"title": "T", "core_message": "새 메시지"}),
                      _doc([_s("A")], meta={"title": "T", "core_message": "옛 메시지"}))
    assert [f["field"] for f in d["meta_fields"]] == ["core_message"]


def test_summary_is_usable_as_a_deliberation_brief():
    """재심의 발제문으로 그대로 쓰인다 — 무엇이 바뀌었고 무엇을 물어야 하는지가 있어야 한다."""
    md = change_summary_md(
        diff_scenario(_doc([_s("A", dur=14.0)]), _doc([_s("A")])), run_id="r1")
    assert "r1" in md and "dur" in md
    assert "심의가 물어야 할 것" in md


def test_revise_is_a_cli_command():
    import inspect

    from wdpipeline import cli

    params = inspect.signature(cli.revise).parameters
    assert {"run_id", "rebuild", "review"} <= set(params)
    # 기본은 보여주기만 한다 — 모르고 재렌더하면 편집이 의도대로 들어갔는지 알 수 없다
    assert params["rebuild"].default.default is False
    assert params["review"].default.default is False
