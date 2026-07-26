# P6 아카이브 역기록 — 실행 산출물(정규화 보고서·회의록·QA·렌더)을 report_archive_draft_v1 제작 기록 초안으로 조립
from __future__ import annotations

import datetime
import json
import os
import re
from pathlib import Path
from typing import Any

DRAFT_TYPE = "report_archive_draft_v1"

# examples/reportarchive/report_sample.json 실물과 동일한 템플릿 좌표.
# submit_draft 는 서버 템플릿 목록과 대조해 없으면 첫 템플릿으로 폴백한다.
DEFAULT_TEMPLATE_ID = "1da9d132-fe8d-4139-9176-4184be86c011"
DEFAULT_TEMPLATE_VERSION = 2

# 심의 기록 테이블 상한 — 초과분은 마지막 행에 생략 표기
_MAX_TURN_ROWS = 20

_ROLE_MODERATOR = "모더레이터"

# 마크다운 강조/헤딩/리스트 마커만 걷어내는 한 줄 요지용 평문화
_PLAIN_RES = [
    re.compile(r"`([^`]*)`"),
    re.compile(r"\[([^\]]*)\]\([^)]*\)"),
    # 단어 내부 언더스코어(scenario_build 등)는 강조로 오인하지 않는다
    re.compile(r"(?<!\w)[*_]{1,3}([^*_]+)[*_]{1,3}(?!\w)"),
    re.compile(r"^#{1,6}\s*"),
    re.compile(r"^[-*+]\s+"),
]


def _plain(line: str) -> str:
    out = line
    for pat in _PLAIN_RES:
        out = pat.sub(r"\1" if pat.groups else "", out)
    return re.sub(r"\s+", " ", out).strip()


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _first_line(md: str, limit: int = 90) -> str:
    """content_md 의 첫 비어있지 않은 줄을 평문 요지로 만든다."""
    for line in md.splitlines():
        p = _plain(line)
        if p:
            return _clip(p, limit)
    return ""


def _load_json(path: Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _minutes_bullets(md: str, title: str) -> list[str]:
    """minutes.md 의 `## N. {title}` 절 아래 불릿(- ...)만 추출한다."""
    lines = md.splitlines()
    out: list[str] = []
    inside = False
    header = re.compile(rf"^##\s*(?:\d+\.\s*)?{re.escape(title)}\s*$")
    for line in lines:
        if line.startswith("## "):
            inside = bool(header.match(line))
            continue
        if inside and line.lstrip().startswith("- "):
            out.append(_plain(line.lstrip()[2:]))
    return [b for b in out if b]


# ---------------------------------------------------------------------------
# 페이지 조립 — 위젯 content 는 report_sample.json 실물 형식을 그대로 따른다
#   heading: {text} / rich_text: {markdown} / bulleted_list: {items:[str]}
#   key_value: {items:[{key,label,type}], <key>: str} / table: {rows:[{col: str}]}
# ---------------------------------------------------------------------------


def _page(name: str, blocks: list[tuple[str, str, dict, dict, str | None]]) -> dict:
    """블록 목록 [(id, type, props, content, section)] → draft_v1 페이지 dict."""
    extra_blocks = [{"id": bid, "type": btype, "props": props} for bid, btype, props, _, _ in blocks]
    content = {bid: c for bid, _, _, c, _ in blocks}
    sections = {bid: sec for bid, _, _, _, sec in blocks if sec}
    return {
        "template_id": DEFAULT_TEMPLATE_ID,
        "template_version": DEFAULT_TEMPLATE_VERSION,
        "name": name,
        "extra_blocks": extra_blocks,
        "content": content,
        "layout_overrides": None,
        "props_overrides": None,
        "blocks_order": [bid for bid, _, _, _, _ in blocks],
        "block_sections": sections,
    }


def _kv(items: list[tuple[str, str, str]]) -> dict:
    """[(key, label, value)] → key_value content."""
    out: dict[str, Any] = {
        "items": [{"key": k, "label": lbl, "type": "text"} for k, lbl, _ in items]
    }
    for k, _, v in items:
        out[k] = v
    return out


def _scene_copy(scenario: dict, scene: dict) -> str:
    """씬의 핵심 카피 — data_ref 가 가리키는 content 의 title(문자열 또는 pre/accent/post)."""
    ref = str(scene.get("data_ref", ""))
    node: Any = scenario
    for part in ref.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            node = None
            break
    title = node.get("title") if isinstance(node, dict) else None
    if isinstance(title, dict):
        text = "".join(str(title.get(k, "")) for k in ("pre", "accent", "post"))
    else:
        text = str(title or "")
    return _clip(text or str(scene.get("narration", "")), 60)


def _overview_page(norm: dict, scenario: dict, meeting_meta: dict | None,
                   minutes_md: str, n_turns: int, n_frags: int,
                   renders_dir: Path | None) -> dict:
    meta = scenario.get("meta", {})
    scenes = scenario.get("scenes", [])
    duration = meta.get("duration_sec") or sum(s.get("dur", 0) for s in scenes)
    outputs = "(산출물 없음)"
    if renders_dir and Path(renders_dir).is_dir():
        names = sorted(p.name for p in Path(renders_dir).iterdir() if p.is_file())
        if names:
            outputs = " · ".join(names)

    summary_parts = []
    if meeting_meta:
        summary_parts.append(
            f"**{meeting_meta.get('type', '?')}** 회의 「{meeting_meta.get('topic', '')}」 — "
            f"참가 {len(meeting_meta.get('participants', []))}인, {n_turns}턴, "
            f"상태 {meeting_meta.get('status', '?')}."
        )
    if n_frags:
        summary_parts.append(f"원본 보고서에서 추출한 조각 {n_frags}건이 심의의 초기 인용 화이트리스트로 쓰였다.")
    verdict = [b for b in _minutes_bullets(minutes_md, "결론") if b.startswith("판정")]
    if verdict:
        summary_parts.append(verdict[0])
    if not summary_parts:
        summary_parts.append("회의 기록이 제공되지 않아 심의 요약을 생략한다.")

    return _page("1. 개요", [
        ("h1_overview", "heading", {"level": 1, "default_text": "제작 기록 개요"},
         {"text": "제작 기록 개요"}, None),
        ("kv_overview", "key_value", {"label": "제작 개요"},
         _kv([
             ("source_report", "원본 보고서", f"{norm.get('title', '')} ({norm.get('report_date', '')}, doc {norm.get('doc_id', '')})"),
             ("core_message", "핵심 메시지", str(meta.get("core_message", ""))),
             ("duration", "총 길이", f"{duration:g}초"),
             ("scene_count", "씬 수", f"{len(scenes)}씬"),
             ("outputs", "산출물 목록", outputs),
         ]), "current_state"),
        ("rt_delib_summary", "rich_text", {},
         {"markdown": "\n\n".join(summary_parts)}, "background"),
    ])


def _deliberation_page(turns: list[dict], minutes_md: str) -> dict:
    rows = []
    shown = turns if len(turns) <= _MAX_TURN_ROWS else turns[: _MAX_TURN_ROWS - 1]
    for t in shown:
        rows.append({
            "round": f"R{int(t.get('round_no', 0)) + 1}",
            "speaker": t.get("expert_id") or _ROLE_MODERATOR,
            "stance": str(t.get("stance", "")),
            "gist": _first_line(str(t.get("content_md", ""))),
        })
    if len(turns) > _MAX_TURN_ROWS:
        rows.append({
            "round": "…", "speaker": "…", "stance": "…",
            "gist": f"이하 {len(turns) - len(shown)}턴 생략",
        })
    decisions = _minutes_bullets(minutes_md, "결론") or ["(결정 사항 기록 없음)"]
    open_issues = _minutes_bullets(minutes_md, "미해결 쟁점") or ["(미해결 쟁점 없음)"]

    return _page("2. 심의 기록", [
        ("h1_delib", "heading", {"level": 1, "default_text": "심의 기록"},
         {"text": "심의 기록"}, None),
        ("tbl_turns", "table", {
            "label": f"발언 기록 (총 {len(turns)}턴)",
            "columns": [
                {"key": "round", "label": "라운드", "type": "text"},
                {"key": "speaker", "label": "발언자", "type": "text"},
                {"key": "stance", "label": "stance", "type": "text"},
                {"key": "gist", "label": "요지", "type": "text"},
            ],
        }, {"rows": rows}, "analysis"),
        ("bl_decisions", "bulleted_list", {"label": "결정 사항"},
         {"items": decisions}, "decision"),
        ("bl_open_issues", "bulleted_list", {"label": "미해결 쟁점"},
         {"items": open_issues}, None),
    ])


def _scenes_page(scenario: dict, meeting_meta: dict | None, minutes_md: str) -> dict:
    rows = []
    for s in scenario.get("scenes", []):
        rows.append({
            "scene": str(s.get("name", "")),
            "tpl": str(s.get("tpl", "")),
            "dur": f"{s.get('dur', 0):g}s",
            "copy": _scene_copy(scenario, s),
        })
    rationale_parts = []
    if meeting_meta:
        rationale_parts.append(
            f"씬 구성은 회의 `{meeting_meta.get('id', '')}` 「{meeting_meta.get('topic', '')}」 의 심의로 확정되었다."
        )
    rationale_parts += [f"- {b}" for b in _minutes_bullets(minutes_md, "결론")]
    if not rationale_parts:
        rationale_parts.append("구성 결정 근거 기록이 제공되지 않았다.")

    return _page("3. 씬 구성", [
        ("h1_scenes", "heading", {"level": 1, "default_text": "씬 구성"},
         {"text": "씬 구성"}, None),
        ("tbl_scenes", "table", {
            "label": f"씬 타임라인 ({len(rows)}씬)",
            "columns": [
                {"key": "scene", "label": "씬", "type": "text"},
                {"key": "tpl", "label": "템플릿", "type": "text"},
                {"key": "dur", "label": "길이", "type": "text"},
                {"key": "copy", "label": "핵심 카피", "type": "text"},
            ],
        }, {"rows": rows}, "reference"),
        ("rt_rationale", "rich_text", {},
         {"markdown": "\n".join(rationale_parts)}, "analysis"),
    ])


def _qa_page(qa: dict | None) -> dict:
    blocks: list[tuple[str, str, dict, dict, str | None]] = [
        ("h1_qa", "heading", {"level": 1, "default_text": "품질 검증"},
         {"text": "품질 검증"}, None),
    ]
    if qa is None:
        blocks.append(("rt_qa_missing", "rich_text", {},
                       {"markdown": "QA 리포트가 제공되지 않았다 — 게이트 실행 기록 없음."}, None))
        return _page("4. 품질 검증", blocks)

    summary = qa.get("summary", {})
    blocks.append(("kv_qa", "key_value", {"label": "게이트 실행 결과"},
                   _kv([
                       ("passed", "게이트 통과 여부", "통과" if qa.get("passed") else "실패"),
                       ("errors", "error", str(summary.get("error", 0))),
                       ("warnings", "warning", str(summary.get("warning", 0))),
                       ("infos", "info", str(summary.get("info", 0))),
                       ("gates_run", "실행 게이트", " · ".join(qa.get("gates_run", [])) or "(없음)"),
                       ("build_dir", "검증 대상", str(qa.get("build_dir", ""))),
                   ]), "current_state"))
    results = qa.get("results", [])
    if results:
        rows = [{
            "gate": str(r.get("gate", "")),
            "rule": str(r.get("rule", "")),
            "scene": str(r.get("scene") or "-"),
            "severity": str(r.get("severity", "")),
            "detail": _clip(str(r.get("detail", "")), 160),
        } for r in results]
        blocks.append(("tbl_findings", "table", {
            "label": f"주요 소견 ({len(rows)}건)",
            "columns": [
                {"key": "gate", "label": "게이트", "type": "text"},
                {"key": "rule", "label": "규칙", "type": "text"},
                {"key": "scene", "label": "씬", "type": "text"},
                {"key": "severity", "label": "심각도", "type": "text"},
                {"key": "detail", "label": "내용", "type": "text"},
            ],
        }, {"rows": rows}, "analysis"))
    return _page("4. 품질 검증", blocks)


def build_archive_draft(run_dir: Path, *, meeting_dir: Path | None = None,
                        qa_report: Path | None = None,
                        renders_dir: Path | None = None) -> dict:
    """실행 산출물 → report_archive_draft_v1 제작 기록 초안 (모듈 간 계약).

    run_dir 의 report.norm.json·scenario.json 은 필수, fragments.json 은 선택.
    meeting_dir(meta.json·turns.jsonl·minutes.md)·qa_report(qa.json)·renders_dir 는
    선택 — 없으면 해당 절이 축소 기록된다. 출력은 P0 ingest 가 그대로 재소비할 수
    있는 포맷(왕복 대칭성)이다.
    """
    run_dir = Path(run_dir)
    norm = _load_json(run_dir / "report.norm.json")
    scenario = _load_json(run_dir / "scenario.json")
    frags_path = run_dir / "fragments.json"
    n_frags = len(_load_json(frags_path)) if frags_path.is_file() else 0

    meeting_meta: dict | None = None
    turns: list[dict] = []
    minutes_md = ""
    if meeting_dir is not None:
        meeting_dir = Path(meeting_dir)
        meta_path = meeting_dir / "meta.json"
        if meta_path.is_file():
            meeting_meta = _load_json(meta_path)
        turns_path = meeting_dir / "turns.jsonl"
        if turns_path.is_file():
            turns = [json.loads(line) for line in
                     turns_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        minutes_path = meeting_dir / "minutes.md"
        if minutes_path.is_file():
            minutes_md = minutes_path.read_text(encoding="utf-8")

    qa: dict | None = None
    if qa_report is not None:
        qa_path = Path(qa_report)
        if qa_path.is_dir():
            qa_path = qa_path / "qa.json"
        if qa_path.is_file():
            qa = _load_json(qa_path)

    # 보고 일자 — 회의 폐회일 우선(결정론), 없으면 오늘
    closed_at = (meeting_meta or {}).get("closed_at", "")
    report_date = closed_at[:10] if closed_at else datetime.date.today().isoformat()

    pages = [
        _overview_page(norm, scenario, meeting_meta, minutes_md, len(turns), n_frags, renders_dir),
        _deliberation_page(turns, minutes_md) if turns else _page("2. 심의 기록", [
            ("h1_delib", "heading", {"level": 1, "default_text": "심의 기록"},
             {"text": "심의 기록"}, None),
            ("rt_delib_missing", "rich_text", {},
             {"markdown": "회의 기록(turns.jsonl)이 제공되지 않았다."}, None),
        ]),
        _scenes_page(scenario, meeting_meta, minutes_md),
        _qa_page(qa),
    ]
    return {
        "_type": DRAFT_TYPE,
        "title": f"[제작기록] {norm.get('title', '')} 발표자료",
        "report_date": report_date,
        "tags": ["webdesignagents", "제작기록"],
        "pages": pages,
    }


# ---------------------------------------------------------------------------
# 업로드 (선택) — ReportArchive REST 역추적 경로
#   mcp_server/server.py 의 create_report_draft 가 POST /api/reports/ai-draft 를
#   호출한다. 인증은 POST /api/auth/login(JWT) + X-Workspace-Slug 헤더.
#   ai-draft 의 extra_blocks 는 content 를 인라인으로 받는다(_build_ai_page →
#   normalize_extra_blocks). 실호출 검증은 자격증명이 채워진 뒤의 몫이다.
# ---------------------------------------------------------------------------


def _unwrap(resp) -> Any:
    """백엔드 표준 봉투 {success, data, message} 언래핑 — 실패면 RuntimeError."""
    try:
        body = resp.json()
    except Exception as exc:
        raise RuntimeError(f"ReportArchive 응답이 JSON 이 아니다 (HTTP {resp.status_code})") from exc
    if resp.status_code >= 400 or not body.get("success", True):
        raise RuntimeError(f"ReportArchive 요청 실패: {body.get('message') or f'HTTP {resp.status_code}'}")
    return body.get("data", body)


def _draft_to_ai_draft_body(draft: dict, template_id: str, template_version: int) -> dict:
    """report_archive_draft_v1 → POST /api/reports/ai-draft 요청 본문."""
    pages = []
    for p in draft.get("pages", []):
        content = p.get("content") or {}
        extra = []
        for b in p.get("extra_blocks", []):
            eb = {"id": b["id"], "type": b["type"], "props": b.get("props") or {}}
            if b["id"] in content:
                eb["content"] = content[b["id"]]
            extra.append(eb)
        pages.append({
            "name": p.get("name"),
            "blocks": {},
            "extra_blocks": extra,
            "block_sections": p.get("block_sections") or {},
        })
    return {
        "template_id": template_id,
        "template_version": template_version,
        "title": draft["title"],
        "blocks": {},
        "extra_blocks": [],
        "block_sections": {},
        "pages": pages,
        "report_date": draft.get("report_date"),
        "tags": draft.get("tags", []),
    }


def submit_draft(draft: dict, *, base_url: str | None = None) -> dict:
    """초안을 ReportArchive 에 업로드한다 — WDA_RA_* 자격증명이 전부 있을 때만.

    로그인 → 템플릿 좌표 확정(초안의 template_id 가 서버에 없으면 첫 템플릿 폴백)
    → POST /api/reports/ai-draft. 반환은 서버 data(생성된 report + warnings).
    """
    base = (base_url or os.environ.get("WDA_RA_BASE_URL") or "").rstrip("/")
    email = os.environ.get("WDA_RA_EMAIL") or ""
    password = os.environ.get("WDA_RA_PASSWORD") or ""
    if not (base and email and password):
        raise RuntimeError("자격증명 미설정 — .env 의 WDA_RA_* 를 채우면 업로드가 켜진다")

    import httpx

    with httpx.Client(base_url=base, timeout=60) as client:
        login = _unwrap(client.post("/api/auth/login", json={"email": email, "password": password}))
        token = login["access_token"]
        # ai-draft 는 개인 공간에 초안을 만들지만 인증 컨텍스트로 워크스페이스 헤더가 필요
        workspace = os.environ.get("WDA_RA_WORKSPACE") or f"personal-{login['user_id']}"
        headers = {"Authorization": f"Bearer {token}", "X-Workspace-Slug": workspace}

        pages = draft.get("pages", [])
        template_id = str((pages[0] if pages else {}).get("template_id") or DEFAULT_TEMPLATE_ID)
        template_version = int((pages[0] if pages else {}).get("template_version") or DEFAULT_TEMPLATE_VERSION)
        try:
            templates = _unwrap(client.get("/api/templates", headers=headers))
            ids = {(str(t.get("template_id")), int(t.get("version", 1))) for t in templates}
            if templates and (template_id, template_version) not in ids:
                template_id = str(templates[0].get("template_id"))
                template_version = int(templates[0].get("version", 1))
        except Exception:
            pass  # 목록 조회 실패 시 초안에 박힌 좌표 그대로 시도

        body = _draft_to_ai_draft_body(draft, template_id, template_version)
        return _unwrap(client.post("/api/reports/ai-draft", json=body, headers=headers))
