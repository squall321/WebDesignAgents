# MCP·웹 두 창구가 같은 능력 집합을 노출하는지 못박는 계약 — 한쪽만 되는 기능을 금지한다
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from wdmcp import server as mcp_server
from wdweb.app import app

# 능력 → (MCP 도구, 웹 라우트). 어느 쪽이든 비면 "그 창구에서는 못 하는 일" 이 생긴다.
# 새 능력을 추가할 때는 두 칸을 모두 채운 뒤 이 표에 한 줄 더한다.
CAPABILITIES: list[tuple[str, str, tuple[str, str]]] = [
    ("페르소나 로스터",   "meeting_personas",     ("GET",   "/api/personas/roster")),
    ("심의 개회",         "meeting_start",        ("POST",  "/api/meetings")),
    ("브리핑",            "meeting_get_briefing", ("GET",   "/api/meetings/{meeting_id}/briefing")),
    ("턴 제출",           "meeting_submit_turn",  ("POST",  "/api/meetings/{meeting_id}/turns")),
    ("심의 상태",         "meeting_status",       ("GET",   "/api/meetings/{meeting_id}")),
    ("폐회",              "meeting_close",        ("POST",  "/api/meetings/{meeting_id}/close")),
    ("심의 목록",         "meeting_list",         ("GET",   "/api/meetings")),
    ("회의록 열람",       "meeting_minutes",      ("GET",   "/api/meetings/{meeting_id}/minutes")),
    ("시나리오 조립",     "scenario_build",       ("POST",  "/api/meetings/{meeting_id}/scenario")),
    ("시나리오 핀포인트", "scenario_patch",       ("PATCH", "/api/runs/{run_id}/scenario")),
    ("렌더 제출",         "render_submit",        ("POST",  "/api/runs/{run_id}/render")),
    ("렌더 상태",         "render_status",        ("GET",   "/api/runs/{run_id}")),
    ("QA 게이트",         "qa_run",               ("POST",  "/api/runs/{run_id}/qa")),
    ("씬 목록",           "scene_list",           ("GET",   "/api/runs/{run_id}/scenes")),
    ("씬 HTML",           "scene_html",           ("GET",   "/api/runs/{run_id}/scenes/{scene_name}/html")),
    ("씬 스틸",           "scene_still",          ("GET",   "/api/runs/{run_id}/scenes/{scene_name}/still.png")),
    ("모듈 카탈로그",     "module_list",          ("GET",   "/api/modules")),
    ("보고서 인제스트",   "report_ingest",        ("POST",  "/api/runs")),
]


def _web_routes() -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for r in app.routes:
        for m in getattr(r, "methods", set()) or set():
            out.add((m, getattr(r, "path", "")))
    return out


@pytest.mark.parametrize("label,tool,route", CAPABILITIES, ids=[c[0] for c in CAPABILITIES])
def test_capability_exists_on_both_interfaces(label, tool, route):
    assert callable(getattr(mcp_server, tool, None)), f"MCP 에 {label} 도구가 없다: {tool}"
    assert route in _web_routes(), f"웹에 {label} 라우트가 없다: {route[0]} {route[1]}"


def test_render_targets_are_identical_on_both_interfaces():
    """타깃 집합이 갈리면 한쪽 창구에서만 나오는 산출물이 생긴다."""
    from wdmcp.schemas import RENDER_TARGETS as mcp_targets
    from wdweb.runs import RENDER_TARGETS as web_targets

    assert set(mcp_targets) == set(web_targets)


def test_doc_style_choices_are_identical_on_both_interfaces():
    from wdmcp.schemas import DOC_STYLES
    from wdweb.app import DOC_STYLES as web_styles

    assert DOC_STYLES is web_styles, "웹이 DOC_STYLES 를 따로 정의하면 허용값이 갈린다"


def test_web_render_rejects_unknown_doc_style(tmp_path, monkeypatch):
    """doc_style 검증은 빌드 확인 뒤에 온다 — 검증 지점까지 가려면 실행 원장이 필요하다."""
    from wdweb import runs as runledger

    monkeypatch.setattr(runledger, "data_dir", lambda: tmp_path)
    runledger.write_run({
        "run_id": "wr-parity", "slug": "parity", "status": "done", "stages": [],
        "build_dir": str(tmp_path / "b"), "entry": "index.html", "render": None,
        "created_at": "2026-08-28T00:00:00+00:00", "updated_at": "2026-08-28T00:00:00+00:00",
    })
    with TestClient(app) as c:
        r = c.post("/api/runs/wr-parity/render",
                   json={"targets": ["pdf"], "doc_style": "없는문체"})
        assert r.status_code == 400, r.text
        assert "doc_style" in r.json()["message"]


def test_web_render_default_targets_exclude_documents():
    """기본값에 문서를 넣으면 영상 하나 뽑자고 5종을 다 굽는다."""
    from pathlib import Path

    body = Path("src/wdweb/app.py").read_text(encoding="utf-8")
    assert 'body.get("targets") or ["video", "pptx"]' in body


def test_every_render_target_is_downloadable():
    """render_status 가 열람 URL 을 주는데 다운로드 표에 없으면 그 URL 은 404 다(실측 결함).

    MCP 는 문서 3형식 URL 을 돌려주면서 _JOB_DOWNLOAD_META 에는 video·pptx 만 있었다.
    """
    from wdmcp.schemas import RENDER_TARGETS
    from wdweb.app import _JOB_DOWNLOAD_META

    missing = set(RENDER_TARGETS) - set(_JOB_DOWNLOAD_META)
    assert not missing, f"열람 URL 은 주는데 받을 수 없는 타깃: {sorted(missing)}"


def test_run_artifact_paths_cover_documents():
    """웹 실행 원장의 산출물 목록에도 문서가 있어야 콘솔이 링크를 건다."""
    from wdweb.app import _DOWNLOAD_META
    from wdweb.runs import artifact_paths

    kinds = set(artifact_paths({"run_id": "x", "build_dir": "/tmp/b"}))
    for kind in ("html", "pdf", "docx"):
        assert kind in kinds, f"artifact_paths 에 {kind} 가 없다"
        assert kind in _DOWNLOAD_META, f"_DOWNLOAD_META 에 {kind} 가 없다"
