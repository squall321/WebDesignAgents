# 콘솔 심의 화면 계약 — API 만 열고 화면에 없으면 사용자에게는 없는 기능이다
from __future__ import annotations

import re
from pathlib import Path

import pytest

APP_JS = Path("frontend/dist/app.js").read_text(encoding="utf-8")
INDEX = Path("frontend/dist/index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("element_id", [
    "meeting-new-btn", "mt-topic", "mt-type", "mt-personas", "mt-open", "mt-cancel",
    "meeting-actions", "mt-autorun", "mt-close", "meeting-state",
])
def test_console_exposes_deliberation_controls(element_id):
    assert f'id="{element_id}"' in INDEX, f"콘솔에 {element_id} 가 없다"


@pytest.mark.parametrize("path", [
    "api/personas/roster", "api/meetings", "api/meetings/", "/autorun", "/close",
])
def test_console_calls_the_deliberation_api(path):
    assert path in APP_JS, f"콘솔이 {path} 를 호출하지 않는다"


def test_state_panel_uses_the_real_status_fields():
    """meeting_status 스키마와 어긋나면 상태판이 통째로 '-' 로 뜬다(실측)."""
    for field in ("round_index", "total_rounds", "turns_total", "known_refs_count"):
        assert field in APP_JS, f"상태판이 {field} 를 읽지 않는다"
    for wrong in ("state.round_no", "state.turn_count"):
        assert wrong not in APP_JS, f"존재하지 않는 필드를 읽는다: {wrong}"


def test_every_round_name_has_a_korean_label():
    """엔진 라운드 이름은 영어다 — 화면에 그대로 나오면 무슨 라운드인지 읽히지 않는다."""
    from wdcore.meetings.templates import MEETING_TEMPLATES

    body = re.search(r"const ROUND_KO = \{(.*?)\};", APP_JS, re.S)
    assert body, "ROUND_KO 표가 없다"
    labelled = set(re.findall(r"(\w+):", body.group(1)))
    names = {sp.name for specs in MEETING_TEMPLATES.values() for sp in specs}
    assert not (names - labelled), f"한국어 라벨 없는 라운드: {sorted(names - labelled)}"


def test_console_offers_document_outputs():
    for kind in ("html", "pdf", "docx"):
        assert f"add('{kind}'" in APP_JS, f"다운로드 목록에 {kind} 가 없다"
    assert "doc_style" in APP_JS, "콘솔이 문체를 보내지 않는다"


@pytest.mark.parametrize("element_id", ["mt-run", "mt-scenario"])
def test_console_closes_the_loop(element_id):
    """심의로 만든 시나리오가 렌더까지 못 가면 심의 화면은 장식이다."""
    assert f'id="{element_id}"' in INDEX, f"콘솔에 {element_id} 가 없다"


def test_autorun_is_polled_not_awaited():
    """전 라운드 완주는 LLM 턴이 수십 번 — 동기 요청이면 프록시 타임아웃에 먼저 걸린다."""
    assert "pollAutorun" in APP_JS
    assert "api/meetings/' + encodeURIComponent(id) + '/autorun'" in APP_JS
