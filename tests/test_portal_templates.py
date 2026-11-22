# 포털 계약 M3 — RA 템플릿 보고서를 템플릿 스키마(template_schemas)로 풀어 ingest 한다(실물 꼴 · 세 출처 · 저장 · 재개)
"""실물 꼴(Report Archive v0.186.3 · dev RA 의 심의 보고서 70건을 읽기 전용으로 본 것, 2026-11-22).

  · 템플릿 보고서의 쪽은 `content` 에 **템플릿 블록 id 만** 있고 `extra_blocks` 가 비어 있다 — 블록 정의(종류 · 라벨)는 RA 의 템플릿 스키마
    (`GET /api/templates/{id}/versions/{v}` 의 `data.schema`)에 있다. 정의가 없으면 ingest 는 그 블록을 건너뛰어 '블록 0개' 로 거절했다.
  · 긴 글(rich_text)의 내용은 `{"items": [{"depth": 0, "text": "…"}]}` 다(RA ai-draft 가 문자열 목록을 이 꼴로 바꾼다) — `markdown` 이 아니다.
  · 쪽 이름은 None 이다. 내용 키 순서는 JSONB 가 바꾼다(minutes · results · background · recommendation) — 순서는 `blocks_order` 가 정한다.
  · 여러 줄짜리 항목이 있다.

세 출처(심의 결과 · '/보고서' 저장 답 · 분석 루틴 초안)는 모두 `deliberation` 템플릿이고 블록 넷을 채우는 방식만 다르다(에이전트 서버
deliberation.py · 포털 procedures/routines.py 가 채우는 칸을 그대로 흉내 냈다 — 글은 지어낸 것이다).
"""
from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import block_text, normalize_report
from wdweb import runs as runledger
from wdweb.app import app

ALICE = {"X-Heax-User-Email": "alice@corp.example"}

# dev RA 에 손으로 둔 deliberation 템플릿 v1 의 스키마(data.schema) — 블록 넷 · 모두 rich_text · 블록 칸은 id · type · props 뿐이다
DELIB_SCHEMA = {"version": "widget-v1", "blocks": [
    {"id": "background", "type": "rich_text", "props": {"label": "심의 주제", "required": True}},
    {"id": "results", "type": "rich_text", "props": {"label": "심화 논의(2R)"}},
    {"id": "recommendation", "type": "rich_text", "props": {"label": "의사결정문"}},
    {"id": "minutes", "type": "rich_text", "props": {"label": "회의록(참여·라운드)"}},
]}
SCHEMAS = {"deliberation@1": DELIB_SCHEMA}


def _items(*texts: str) -> dict:
    return {"items": [{"depth": 0, "text": t} for t in texts]}


def _ra(title: str, content: dict, *, order=("background", "results", "recommendation", "minutes"), rid: int = 58) -> dict:
    """RA `GET /api/reports/{id}` 의 data(ReportRead) 꼴 — pages 가 있으면 최상위 content 는 빠진다."""
    # JSONB 가 내용 키 순서를 바꾼다 — 실물에서 본 순서로 넣는다
    jsonb = {k: content[k] for k in ("minutes", "results", "background", "recommendation") if k in content}
    return {"id": rid, "workspace_slug": "personal-5", "template_id": "deliberation", "template_version": 1, "title": title,
            "phase": "draft", "lifecycle": "active", "tags": ["심의"], "pages": [{
                "name": None, "template_id": "deliberation", "template_version": 1, "content": jsonb, "extra_blocks": [],
                "blocks_order": list(order), "block_sections": {}, "block_updated_at": {}, "layout_overrides": None,
                "props_overrides": None}]}


# ① 심의 결과 — 에이전트 서버가 심의를 마치고 남기는 보고서
DELIB_RESULT = _ra("심의 — 힌지 굽힘 수명", {
    "background": _items("심의 주제: 힌지 FPCB 의 구리 두께를 12um 로 낮출 것인가"),
    "results": _items("• [기구] 굽힘 반경 3.0mm 에서 12um 는 피로 수명이 30% 준다는 시험 근거가 있다.",
                      "• [재료] 압연 동박이면 차이가 줄지만 공급처가 하나다."),
    "recommendation": _items("■ 핵심 요약", "• 12um 전환은 보류한다.", "• 압연 동박 시험을 먼저 한다.",
                             "## 의사결정문", "(2) 결정사항 — 이번 차수는 18um 를 유지한다.",
                             "(6) 미해결 쟁점 + 담당·다음 액션 — 압연 동박 굽힘 시험(재료, 다음 주)",
                             "■ 쉬운 설명\n### 한마디로\n얇게 하면 더 잘 부러질 수 있어 지금은 바꾸지 않는다."),
    "minutes": _items("참여: 기구, 재료, 신뢰성", "3라운드 심의(초기 입장 → 상호 반박 → 수렴)",
                      "— 1라운드 — 도메인별 초기 입장 —", "[기구] 굽힘 반경이 작아 위험하다.", "[재료] 동박 종류에 달렸다."),
})
# ② '/보고서' 저장 답 — 대화를 정리해 저장한 보고서(사용자 결론 · 질문 전문이 붙는다)
SAVED_ANSWER = _ra("대화 정리 — 커버 글라스 낙하", {
    "background": _items("심의 주제: 커버 글라스 1.2m 낙하에서 모서리 파손", "질문 전문:\n모서리 R 을 키우면 파손이 줄까?"),
    "results": _items("모서리 R 0.5 → 1.0 에서 응력이 18% 낮아졌다는 해석 결과가 있다."),
    "recommendation": _items("사용자 결론: R 1.0 으로 다음 차수에 반영한다.", "추가로 범퍼 두께를 0.2mm 늘리는 안을 검토한다."),
    "minutes": _items("대화 3턴 · 도구 2회(해석 조회 · 시험 이력)"),
}, rid=77)
# ③ 분석 루틴 초안 — 루틴 실행기가 단계별 결과를 절마다 싣는다
ROUTINE_DRAFT = _ra("분석 루틴 보고서 — 스웰링 시장불량", {
    "background": _items("루틴 「시장불량 원인 분석」 판 3 — S26 스웰링 원인 · 시험 · 대책"),
    "results": _items("기준 키 — SM-S938 계열로 확인했다.", "시장불량 이력 — 최근 분기 12건, 고온 보관 뒤 발생이 많다."),
    "recommendation": _items("인사이트 — 고온 보관 조건의 셀 팽창 시험을 우선한다."),
    "minutes": _items("근거 부록\n· 시장불량 이력 조회 2회\n· PLM 문제점 연결 없음"),
}, order=("background", "results", "recommendation", "minutes"), rid=91)
SOURCES = {"delib_result": DELIB_RESULT, "saved_answer": SAVED_ANSWER, "routine_draft": ROUTINE_DRAFT}


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _wait(run_id: str, pred, timeout: float = 120.0) -> dict:
    end = time.time() + timeout
    run = None
    while time.time() < end:
        run = runledger.read_run(run_id)
        if run is not None and pred(run):
            return run
        time.sleep(0.05)
    raise AssertionError(f"기다리다 끝났다: {run_id} — {run}")


def _settled(run: dict) -> bool:
    return run["status"] in ("done", "failed")


# ── ingest — 스키마로 블록을 푼다 ─────────────────────────────────────────


@pytest.mark.parametrize("name", list(SOURCES))
def test_real_template_report_is_refused_without_its_schema(name):
    """스키마 없이는 종전 그대로다 — 정의 없는 내용 키를 건너뛰어 블록 0개로 거절한다(지어내지 않는다)."""
    with pytest.raises(ValueError, match="텍스트를 가진 블록이 없다"):
        normalize_report(copy.deepcopy(SOURCES[name]))


@pytest.mark.parametrize("name", list(SOURCES))
def test_schema_resolves_template_blocks_with_label_and_type(name):
    raw = copy.deepcopy(SOURCES[name])
    norm = normalize_report(raw, template_schemas=SCHEMAS)
    (page,) = norm["pages"]
    assert [b["id"] for b in page["blocks"]] == ["background", "results", "recommendation", "minutes"], \
        "순서는 blocks_order 다(JSONB 가 바꾼 내용 키 순서가 아니다)"
    assert {b["type"] for b in page["blocks"]} == {"rich_text"}
    assert [b["props"]["label"] for b in page["blocks"]] == ["심의 주제", "심화 논의(2R)", "의사결정문", "회의록(참여·라운드)"]
    assert all(block_text(b["type"], b["content"]) for b in page["blocks"]), "긴 글의 items 꼴에서 글을 읽는다"
    assert page["name"] == "", "쪽 이름 None 은 빈 이름이다('None' 이 아니다)"
    assert raw == SOURCES[name], "받은 보고서를 고치지 않는다"


def test_empty_blocks_order_follows_the_template_order():
    """blocks_order 가 비면 RA 는 템플릿 순서로 그린다 — JSONB 의 내용 키 순서를 따르지 않는다."""
    raw = copy.deepcopy(DELIB_RESULT)
    raw["pages"][0]["blocks_order"] = []
    norm = normalize_report(raw, template_schemas=SCHEMAS)
    assert [b["id"] for b in norm["pages"][0]["blocks"]] == ["background", "results", "recommendation", "minutes"]


def test_mixed_page_keeps_extra_blocks_and_template_blocks():
    """실물 70건 가운데 넷은 템플릿 블록 + 덧붙인 블록(extra_blocks)이 섞여 있다 — 둘 다 산다."""
    raw = copy.deepcopy(DELIB_RESULT)
    page = raw["pages"][0]
    page["extra_blocks"] = [{"id": "compare_table", "type": "heading", "props": {"level": 2}}]
    page["content"]["compare_table"] = {"text": "대안 비교"}
    page["blocks_order"] = ["background", "results", "recommendation", "minutes", "compare_table"]
    norm = normalize_report(raw, template_schemas=SCHEMAS)
    assert [b["id"] for b in norm["pages"][0]["blocks"]] == ["background", "results", "recommendation", "minutes", "compare_table"]
    assert norm["pages"][0]["blocks"][-1]["type"] == "heading"


def test_schema_is_found_by_the_page_template_and_version():
    """키는 `<template_id>@<version>` — 쪽의 판이 이긴다. 판이 다르면 그 스키마를 쓰지 않는다(다른 판의 블록을 지어내지 않는다)."""
    raw = copy.deepcopy(DELIB_RESULT)
    with pytest.raises(ValueError, match="텍스트를 가진 블록이 없다"):
        normalize_report(raw, template_schemas={"deliberation@2": DELIB_SCHEMA})
    raw["pages"][0].pop("template_id")
    raw["pages"][0].pop("template_version")
    assert len(normalize_report(raw, template_schemas=SCHEMAS)["pages"][0]["blocks"]) == 4, "쪽에 없으면 보고서의 템플릿 · 판"


def test_schema_blocks_not_used_by_the_page_are_not_invented():
    """스키마에는 있지만 쪽이 쓰지 않는 블록(내용 · 순서 어디에도 없다)은 만들지 않는다."""
    raw = copy.deepcopy(SAVED_ANSWER)
    page = raw["pages"][0]
    page["content"].pop("minutes")
    page["blocks_order"] = ["background", "results", "recommendation"]
    norm = normalize_report(raw, template_schemas=SCHEMAS)
    assert [b["id"] for b in norm["pages"][0]["blocks"]] == ["background", "results", "recommendation"]


def test_legacy_markdown_rich_text_is_unchanged():
    assert block_text("rich_text", {"markdown": "**굵게** 본문"}) == "굵게 본문"
    assert block_text("rich_text", {"markdown": "", "items": [{"depth": 0, "text": "항목"}]}) == "항목"
    assert block_text("rich_text", {"items": ["문자열 항목", {"text": "  "}, 7]}) == "문자열 항목"


def test_items_become_one_fragment_each_and_labels_tag_sections():
    """긴 글의 항목은 항목마다 한 조각이다(bulleted_list 와 같은 단위) — 결정문 14항목이 200자 한 조각으로 잘리지 않는다.
    블록 라벨은 그 블록의 머리글이다 — '심의 주제' 는 화두, '의사결정문' 은 결정, 회의록 · 심화 논의는 라운드."""
    norm = normalize_report(copy.deepcopy(DELIB_RESULT), template_schemas=SCHEMAS)
    frags = fragmentize(norm)
    by_block: dict[str, list[dict]] = {}
    for f in frags:
        by_block.setdefault(f["source"]["block_id"], []).append(f)
    assert len(by_block["recommendation"]) == 7 and len(by_block["minutes"]) == 5
    assert {f["section"] for f in by_block["background"]} == {"topic"}
    assert {f["section"] for f in by_block["recommendation"]} == {"decision"}
    assert {f["section"] for f in by_block["minutes"]} == {"round"}
    assert {f["section"] for f in by_block["results"]} == {"round"}
    assert not any("■" in f["text"] and "##" in f["text"] for f in frags)


def test_explicit_block_section_beats_the_label():
    raw = copy.deepcopy(DELIB_RESULT)
    raw["pages"][0]["block_sections"] = {"recommendation": "action_item"}
    frags = fragmentize(normalize_report(raw, template_schemas=SCHEMAS))
    assert {f["section"] for f in frags if f["source"]["block_id"] == "recommendation"} == {"action_item"}


# ── 웹 — 만들기 칸 · 저장 · 재개 · 세 출처 끝까지 ──────────────────────────────


@pytest.mark.parametrize("name", list(SOURCES))
def test_each_source_runs_through_the_delib_format(client, name):
    """세 출처가 다 통과한다 — 보고서 읽기 · 조각 · 장면 · 빌드까지(심의 꼴 delib-16x9)."""
    rid = client.post("/api/runs", json={"report_json": SOURCES[name], "slug": f"tpl-{name}", "format": "delib-16x9",
                                         "template_schemas": SCHEMAS}, headers=ALICE).json()["data"]["run_id"]
    run = _wait(rid, _settled)
    assert run["status"] == "done", (run.get("error"), run["stages"])
    assert run["template_schemas"] == ["deliberation@1"]
    norm = json.loads((runledger.data_dir() / "pipeline" / rid / "report.norm.json").read_text(encoding="utf-8"))
    assert len(norm["pages"][0]["blocks"]) == 4
    assert (runledger.data_dir() / "pipeline" / rid / "template_schemas.json").is_file(), "재개가 읽도록 원장 곁에 둔다"


def test_without_schemas_the_run_still_fails_at_ingest(client):
    """스키마를 싣지 않은 만들기는 종전 그대로 '보고서 읽기' 에서 실패한다 — 포털은 그 전에 막는다."""
    rid = client.post("/api/runs", json={"report_json": DELIB_RESULT, "slug": "tpl-none"}, headers=ALICE).json()["data"]["run_id"]
    run = _wait(rid, _settled)
    assert run["status"] == "failed" and run["stages"][0]["status"] == "failed"
    assert "template_schemas" not in run or run["template_schemas"] is None


def test_resume_reads_the_stored_schemas(client):
    rid = client.post("/api/runs", json={"report_json": DELIB_RESULT, "slug": "tpl-resume", "template_schemas": SCHEMAS},
                      headers=ALICE).json()["data"]["run_id"]
    _wait(rid, _settled)
    (runledger.data_dir() / "pipeline" / rid / "report.norm.json").unlink()      # ingest 산출물이 없다 → 거기서 재개
    led = runledger.read_run(rid)
    led["status"] = "failed"
    runledger.write_run(led)
    res = client.post(f"/api/runs/{rid}/resume", headers=ALICE)
    assert res.json()["data"]["start_from"] == "ingest"
    run = _wait(rid, lambda r: _settled(r) and r["stages"][0]["status"] in ("done", "failed"))
    assert run["stages"][0]["status"] == "done", run["stages"][0]


@pytest.mark.parametrize("bad", [
    [],                                                        # 객체가 아니다
    {"deliberation": DELIB_SCHEMA},                            # 판이 없다
    {"../x@1": DELIB_SCHEMA},                                  # 경로가 될 이름
    {"deliberation@1": {"version": "widget-v1"}},              # blocks 가 없다
    {"deliberation@1": {"blocks": [{"id": 3, "type": "rich_text"}]}},
    {f"t{i}@1": DELIB_SCHEMA for i in range(65)},              # 너무 많다
])
def test_bad_template_schemas_are_400_invalid(client, bad):
    res = client.post("/api/runs", json={"report_json": DELIB_RESULT, "template_schemas": bad}, headers=ALICE)
    assert res.status_code == 400 and res.json()["code"] == "INVALID"


def test_health_advertises_template_schemas(client):
    assert "template_schemas" in client.get("/api/health").json()["features"]


def test_ingest_file_entry_takes_schemas(tmp_path: Path):
    from wdpipeline.ingest import ingest_report_file

    f = tmp_path / "r.json"
    f.write_text(json.dumps(DELIB_RESULT, ensure_ascii=False), encoding="utf-8")
    assert len(ingest_report_file(f, template_schemas=SCHEMAS)["pages"][0]["blocks"]) == 4
