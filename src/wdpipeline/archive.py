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
# 완성 보고서 역기록 — 심의가 정리한 내용 자체를 ReportArchive 보고서로 되돌린다
#
# build_archive_draft 가 만드는 것은 "어떻게 만들었나"(메타 문서)이고, 여기서
# 만드는 것은 "무엇을 정리했나"(본 문서)다. 원 보고서 → 심의 → 더 나은 보고서.
#   씬 narration      → 섹션 본문(rich_text)
#   fragments.structured → 근거 위젯(원 위젯 타입으로 복원)
#   meta.core_message → 표지 요약
#   minutes.md        → 부록(결정·미해결 쟁점)
#   조각 source{page,block_id} → 부록 출처 표(각주)
# ---------------------------------------------------------------------------

REPORT_STYLES = ("report",)

# 근거 배정 점수용 토큰 — 한글/영숫자 2자 이상
_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")

# 원 위젯 타입을 그대로 되살리는 수치군 (content.rows[{label,value}] 스키마 공유)
_PIE_FAMILY = ("pie", "waffle", "treemap", "packing")

# chart 위젯 props.chart_type 이 실제로 받는 값 (그 밖의 계열은 bar 로 낮춘다)
_CHART_TYPES_OK = ("bar", "line", "pie", "doughnut")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text))


def _strings(node: Any, acc: list[str]) -> None:
    """중첩 dict/list 에서 문자열 값을 전부 모은다 (씬 카피 평탄화)."""
    if isinstance(node, str):
        if node.strip():
            acc.append(node.strip())
    elif isinstance(node, dict):
        for v in node.values():
            _strings(v, acc)
    elif isinstance(node, list):
        for v in node:
            _strings(v, acc)


def _scene_node(scenario: dict, scene: dict) -> dict:
    """씬의 data_ref 가 가리키는 content 노드."""
    node: Any = scenario
    for part in str(scene.get("data_ref", "")).split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return {}
    return node if isinstance(node, dict) else {}


def _flat_title(value: Any) -> str:
    """title 이 문자열이거나 {pre,accent,post} 조각일 수 있다."""
    if isinstance(value, dict):
        return "".join(str(value.get(k, "")) for k in ("pre", "accent", "post")).strip()
    return str(value or "").strip()


# ── 근거 위젯 복원 — structured payload → 원 위젯의 props/content ───────────
# 스키마는 examples/reportarchive/report_sample.json 실물 블록을 역산한 것이다
# (comparison=props.cases+content.rows[].values, raci_matrix=content.roles+
#  rows[].assignments, tree=content.rows[{label,parent,subtitle}], …).


def _restore_table(widget: str, payload: dict, caption: str) -> tuple[str, dict, dict] | None:
    cols = payload.get("columns") or []
    rows = payload.get("rows") or []
    if not cols or not rows:
        return None
    if widget == "comparison" and cols[0]["key"] == "__aspect":
        cases = [{"key": c["key"], "label": c["label"]} for c in cols[1:]]
        # 이미지 셀은 payload 에서 alt(없으면 caption) 텍스트로 낮춰지고 file_id 는 files 로
        # 승격된다. 그 텍스트가 정확히 일치하는 셀만 이미지 참조로 되돌려 file_id 를 지킨다.
        by_text: dict[str, dict] = {}
        for f in payload.get("files") or []:
            key = f.get("alt") or f.get("caption")
            if key:
                by_text.setdefault(str(key), f)
        out = []
        for i, r in enumerate(rows, start=1):
            values: dict[str, Any] = {}
            for c in cases:
                cell = r.get(c["key"], "")
                f = by_text.get(cell)
                values[c["key"]] = (
                    {"file_id": f["file_id"], "alt": f.get("alt", ""),
                     "caption": f.get("caption", "")} if f else cell
                )
            out.append({"key": f"r{i}", "label": r.get("__aspect", ""), "values": values})
        return "comparison", {"label": caption, "cases": cases}, {"rows": out}
    if widget == "raci_matrix" and cols[0]["key"] == "__task":
        roles = [{"key": c["key"], "label": c["label"]} for c in cols[1:]]
        out = [
            {
                "label": r.get("__task", ""),
                "assignments": {c["key"]: r.get(c["key"], "") for c in roles},
            }
            for r in rows
        ]
        return "raci_matrix", {"label": caption}, {"roles": roles, "rows": out}
    columns = [{"key": c["key"], "label": c["label"], "type": "text"} for c in cols]
    return "table", {"label": caption, "columns": columns}, {"rows": [dict(r) for r in rows]}


def _restore_graph(widget: str, payload: dict, caption: str) -> tuple[str, dict, dict] | None:
    nodes = payload.get("nodes") or []
    edges = payload.get("edges") or []
    if not nodes:
        return None
    if payload.get("shape") == "flow":
        items = []
        for n in nodes:
            item = {"label": n.get("label", "")}
            if n.get("note"):
                item["description"] = n["note"]
            items.append(item)
        props = {"label": caption}
        if payload.get("orientation"):
            props["orientation"] = payload["orientation"]
        return "flowchart", props, {"items": items}
    label_of = {n["id"]: n.get("label", n["id"]) for n in nodes}
    if payload.get("shape") == "tree":
        parent_of = {e["to"]: label_of.get(e["from"], "") for e in edges}
        rows = []
        for n in nodes:
            row = {"label": n.get("label", "")}
            if parent_of.get(n["id"]):
                row["parent"] = parent_of[n["id"]]
            if n.get("note"):
                row["subtitle"] = n["note"]
            rows.append(row)
        return ("mind_map" if widget == "mind_map" else "tree"), {"label": caption}, {"rows": rows}
    # network · sankey — 노드 배치 스키마를 지어내지 않고 연결 목록 표로 보존한다
    if not edges:
        return None
    columns = [
        {"key": "from", "label": "출발", "type": "text"},
        {"key": "to", "label": "도착", "type": "text"},
        {"key": "rel", "label": "관계", "type": "text"},
    ]
    rows = [
        {
            "from": label_of.get(e["from"], e["from"]),
            "to": label_of.get(e["to"], e["to"]),
            "rel": str(e.get("label", "")),
        }
        for e in edges
    ]
    return "table", {"label": caption, "columns": columns}, {"rows": rows}


def _restore_series(widget: str, payload: dict, caption: str) -> tuple[str, dict, dict] | None:
    entries = payload.get("series") or []
    if not entries:
        return None
    unit = str(payload.get("unit") or "")
    ctype = str(payload.get("chart_type") or "")
    axis = payload.get("axis") or {}

    if ctype == "progress_bar":
        props: dict = {"label": caption, "unit": unit or "%"}
        default_max = axis.get("max")
        if default_max is not None:
            props["default_max"] = default_max
        items = []
        for e in entries:
            item: dict = {"label": e["label"], "value": e.get("value")}
            if e.get("max") is not None and e["max"] != default_max:
                item["max"] = e["max"]
            for k in ("note", "status"):
                if e.get(k):
                    item[k] = e[k]
            items.append(item)
        return "progress_bar", props, {"items": items}

    if widget in _PIE_FAMILY:
        props = {"label": caption}
        if unit:
            props["unit"] = unit
        rows = []
        for e in entries:
            row: dict = {"label": e["label"], "value": e.get("value")}
            if e.get("parent"):
                row["parent"] = e["parent"]
            rows.append(row)
        content: dict = {"rows": rows}
        if ctype:
            content["chart_type"] = ctype
        return widget, props, content

    scalar = [e for e in entries if e.get("value") is not None]
    if not scalar:
        # box · density 의 원시 분포 — 차트 스키마로 되살릴 수 없다. 값을 표로 보존해
        # 블록이 조용히 사라지는 것만은 막는다.
        columns = [
            {"key": "group", "label": "그룹", "type": "text"},
            {"key": "n", "label": "표본수", "type": "text"},
            {"key": "values", "label": "값", "type": "text"},
        ]
        rows = [
            {
                "group": str(e.get("label", "")),
                "n": str(e.get("n") if e.get("n") is not None else len(e.get("values") or [])),
                "values": ", ".join(f"{v:g}" for v in (e.get("values") or [])),
            }
            for e in entries
        ]
        return "table", {"label": caption, "columns": columns}, {"rows": rows}

    # chart — 계열(group)이 곧 수치 열이다. 다계열도 열 분리로 그대로 되살린다.
    groups: list[str] = []
    for e in scalar:
        g = str(e.get("group") or "")
        if g not in groups:
            groups.append(g)
    key_of = {g: f"v{i}" for i, g in enumerate(groups, start=1)}
    columns = [{"key": "label", "label": "항목", "type": "text"}] + [
        {"key": key_of[g], "label": g or unit or "값", "type": "number"} for g in groups
    ]
    rows_by_x: dict[str, dict] = {}
    order: list[str] = []
    for e in scalar:
        x = str(e["label"])
        if x not in rows_by_x:
            rows_by_x[x] = {"label": x}
            order.append(x)
        rows_by_x[x][key_of[str(e.get("group") or "")]] = e["value"]
    props = {
        "label": caption,
        "columns": columns,
        "x_column_key": "label",
        "chart_type": ctype if ctype in _CHART_TYPES_OK else "bar",
    }
    for prop_key, axis_key in (("y_min", "min"), ("y_max", "max")):
        if axis.get(axis_key) is not None:
            props[prop_key] = axis[axis_key]
    return "chart", props, {"rows": [rows_by_x[x] for x in order]}


def _restore_timeline(payload: dict, caption: str) -> tuple[str, dict, dict] | None:
    ms = payload.get("milestones") or []
    if not ms:
        return None
    items = []
    for m in ms:
        item = {"label": m.get("label", ""), "date": m.get("date", ""), "status": m.get("status", "")}
        if m.get("note"):
            item["note"] = m["note"]
        items.append(item)
    props = {"label": caption}
    for k, v in (payload.get("range") or {}).items():
        props[f"{k}_date"] = v
    return "milestone", props, {"items": items}


def _restore_pairs(payload: dict, caption: str) -> tuple[str, dict, dict] | None:
    pairs = payload.get("pairs") or []
    if not pairs:
        return None
    content = _kv([(p["key"], p.get("label") or p["key"], p.get("value", "")) for p in pairs])
    return "key_value", {"label": caption}, content


def _restore_media(payload: dict, caption: str) -> tuple[str, dict, dict] | None:
    """미디어는 file_id 를 그대로 유지한다 — 원 보고서 자산을 다시 쓰는 것이 목적."""
    files = [f for f in (payload.get("files") or []) if f.get("file_id")]
    if not files:
        return None
    content: dict = {
        "files": [
            {"file_id": f["file_id"], "caption": f.get("caption", ""), "alt": f.get("alt", "")}
            for f in files
        ]
    }
    if caption:
        content["caption"] = caption
    return str(payload.get("media_type") or "image"), {"label": caption}, content


def restore_widget(widget: str, payload: dict) -> tuple[str, dict, dict] | None:
    """structured payload → (위젯 타입, props, content). 되살릴 수 없으면 None.

    `widget`(원 보고서의 위젯 타입)을 최대한 그대로 되살린다 — comparison/raci_matrix/
    tree 처럼 payload 가 table·graph 로 평탄화된 위젯도 원형으로 복원한다.

    무손실(payload 재추출이 원본과 동일) 23종: table·comparison·raci_matrix·fmea·
    record_table·flowchart·tree·mind_map·chart·pie·waffle·treemap·packing·
    progress_bar·milestone·key_value·record·image·video·attachment·cad_3d·
    doc_viewer·html_embed.
    나머지 10종(network·sankey·scatter·scatter3d·heatmap·contour·radar·box·
    density·quadrant)은 좌표/격자 스키마가 payload 에 남지 않아 chart 또는 표로
    낮춘다 — 값은 보존하되 위젯 타입은 바뀐다.
    """
    if not isinstance(payload, dict):
        return None
    kind = payload.get("kind")
    caption = str(payload.get("caption") or "")
    if kind == "table":
        return _restore_table(widget, payload, caption)
    if kind == "graph":
        return _restore_graph(widget, payload, caption)
    if kind == "series":
        return _restore_series(widget, payload, caption)
    if kind == "timeline":
        return _restore_timeline(payload, caption)
    if kind == "pairs":
        return _restore_pairs(payload, caption)
    if kind == "media":
        return _restore_media(payload, caption)
    return None


# ── 근거 수집·배정 ────────────────────────────────────────────────────────


def _collect_evidence(norm: dict, fragments: list[dict]) -> list[dict]:
    """정규화 보고서의 구조 블록 → 근거 항목 목록 (문서 순서 유지).

    payload 는 조각의 structured 를 우선 쓰고, 없으면(구버전 fragments.json) 블록에서
    다시 뽑는다. frag_id 는 조각의 source.block_id 로 이어 붙여 각주 추적을 유지한다.
    """
    from .ingest import block_text
    from .widgets import extract_structured, structured_summary

    frag_of: dict[str, dict] = {}
    for f in fragments:
        bid = str((f.get("source") or {}).get("block_id") or "")
        if bid and bid not in frag_of:
            frag_of[bid] = f

    out: list[dict] = []
    for page in norm.get("pages", []):
        pname = page.get("name", "")
        for block in page.get("blocks", []):
            bid = str(block.get("id") or "")
            frag = frag_of.get(bid) or {}
            payload = frag.get("structured")
            if not isinstance(payload, dict):
                payload = extract_structured(block)
            if not isinstance(payload, dict):
                continue
            widget = str(block.get("type") or "")
            restored = restore_widget(widget, payload)
            if restored is None:
                continue
            summary = structured_summary(payload)
            out.append(
                {
                    "block_id": bid,
                    "page": pname,
                    "widget": widget,
                    "frag_id": str(frag.get("frag_id") or ""),
                    "summary": summary,
                    "restored": restored,
                    "tokens": _tokens(f"{summary} {block_text(widget, block.get('content'))}"),
                }
            )
    return out


def _assign_evidence(evidence: list[dict], scene_tokens: list[set[str]]) -> list[list[dict]]:
    """근거를 씬에 배정한다 — 토큰 겹침 최대 씬으로, 겹침이 0이면 문서 순서 비례 배분."""
    n = len(scene_tokens)
    buckets: list[list[dict]] = [[] for _ in range(n)]
    if n == 0:
        return buckets
    for i, ev in enumerate(evidence):
        scores = [len(ev["tokens"] & st) for st in scene_tokens]
        best = max(scores)
        idx = scores.index(best) if best > 0 else (i * n) // max(len(evidence), 1)
        buckets[min(idx, n - 1)].append(ev)
    return buckets


def _still_files(stills_dir: Path | None, index: int, scene_name: str) -> list[Path]:
    """씬 스틸 파일 — 파일명에 씬 이름이 있으면 그것, 없으면 `{index:02d}_` 접두 매칭."""
    if stills_dir is None or not Path(stills_dir).is_dir():
        return []
    files = sorted(p for p in Path(stills_dir).iterdir() if p.suffix.lower() in (".png", ".jpg"))
    named = [p for p in files if scene_name and scene_name in p.stem]
    return named or [p for p in files if p.stem.startswith(f"{index:02d}_")]


# ── 페이지 조립 ──────────────────────────────────────────────────────────


def _report_cover_page(norm: dict, scenario: dict, meeting_meta: dict | None,
                       n_scenes: int, n_evidence: int, n_turns: int) -> dict:
    meta = scenario.get("meta", {})
    core = str(meta.get("core_message", ""))
    items = [
        ("source_report", "원 보고서",
         f"{norm.get('title', '')} ({norm.get('report_date', '')}, doc {norm.get('doc_id', '')})"),
        ("audience", "대상 독자", str(meta.get("audience", "")) or "-"),
        ("sections", "본문 섹션", f"{n_scenes}개"),
        ("evidence", "근거 위젯", f"{n_evidence}개"),
    ]
    if meeting_meta:
        items.append((
            "deliberation", "심의 회의",
            f"{meeting_meta.get('topic', '')} — 참가 {len(meeting_meta.get('participants', []))}인 · {n_turns}턴",
        ))
    lines = [f"**{core or '심의가 확정한 핵심 메시지가 기록되지 않았다.'}**"]
    if meeting_meta:
        lines.append(
            f"이 보고서는 원 보고서 「{norm.get('title', '')}」 를 전문가 심의 "
            f"`{str(meeting_meta.get('id', ''))[:8]}` 로 다시 정리한 것이다. "
            f"본문 문장은 심의가 집필한 내레이션 정본이고, 각 절의 근거 위젯은 원 보고서 블록을 "
            f"타입 그대로 되살린 것이다(출처는 부록 표 참조)."
        )
    else:
        lines.append("본문 문장은 심의가 집필한 내레이션 정본이고, 근거 위젯은 원 보고서 블록을 타입 그대로 되살린 것이다.")
    return _page("개요", [
        ("h1_cover", "heading", {"level": 1, "default_text": norm.get("title", "")},
         {"text": norm.get("title", "")}, None),
        ("kv_cover", "key_value", {"label": "보고 개요"}, _kv(items), "current_state"),
        ("rt_cover", "rich_text", {}, {"markdown": "\n\n".join(lines)}, "background"),
    ])


def _report_section_page(idx: int, scene: dict, node: dict, evidence: list[dict],
                         stills: list[Path]) -> tuple[dict, list[dict]]:
    """씬 1개 → 섹션 페이지 1장. (페이지, 업로드 대기 자산 목록) 반환."""
    name = str(scene.get("name", "")) or f"섹션 {idx}"
    title = _flat_title(node.get("title")) or name
    body = [str(scene.get("narration", "")).strip() or f"{title} 절이다."]
    for key in ("conclusion", "subtitle", "footnote"):
        extra = node.get(key)
        if isinstance(extra, str) and extra.strip():
            body.append(extra.strip())
        elif isinstance(extra, dict):
            flat = _flat_title({"pre": extra.get("pre", ""), "accent": extra.get("strong", ""),
                                "post": extra.get("post", "")})
            if flat:
                body.append(flat)

    blocks: list[tuple[str, str, dict, dict, str | None]] = [
        ("h1_section", "heading", {"level": 1, "default_text": title}, {"text": title}, None),
        ("rt_body", "rich_text", {}, {"markdown": "\n\n".join(body)}, "background"),
    ]
    pending: list[dict] = []
    for k, path in enumerate(stills, start=1):
        bid = f"img_still_{k}"
        caption = f"{name} 씬 스틸 — 업로드 필요: {path}"
        blocks.append((bid, "image", {"label": f"{name} 화면"},
                       {"caption": caption, "alt": f"{name} 씬 화면"}, "reference"))
        pending.append({"page": f"{idx}. {name}", "block_id": bid,
                        "local_path": str(path), "scene": name})
    for ev in evidence:
        wtype, props, content = ev["restored"]
        props = dict(props)
        # 각주 — 근거가 원 보고서 어느 블록에서 왔는지 라벨에 박는다
        label = props.get("label") or ev["summary"]
        ref = f"{ev['page']} · {ev['block_id']}"
        props["label"] = _clip(f"{label} (출처: {ref})", 90)
        blocks.append((f"ev_{ev['block_id']}", wtype, props, content, "reference"))
    return _page(f"{idx}. {name}", blocks), pending


def _report_appendix_page(minutes_md: str, evidence: list[dict],
                          meeting_meta: dict | None) -> dict:
    decisions = _minutes_bullets(minutes_md, "결론") or ["(심의 결정 기록 없음)"]
    open_issues = _minutes_bullets(minutes_md, "미해결 쟁점") or ["(미해결 쟁점 없음)"]
    rows = [
        {
            "frag": ev["frag_id"] or "-",
            "page": ev["page"],
            "block": ev["block_id"],
            "widget": ev["widget"],
            "gist": _clip(ev["summary"], 120),
        }
        for ev in evidence
    ]
    intro = "본문 각 절의 근거 위젯은 아래 원 보고서 블록에서 왔다. 결정·미해결 쟁점은 심의 회의록 정본이다."
    if meeting_meta:
        intro += f" (회의 {meeting_meta.get('id', '')} · 폐회 {str(meeting_meta.get('closed_at', ''))[:10]})"
    blocks: list[tuple[str, str, dict, dict, str | None]] = [
        ("h1_appendix", "heading", {"level": 1, "default_text": "부록 — 심의 근거"},
         {"text": "부록 — 심의 근거"}, None),
        ("rt_appendix", "rich_text", {}, {"markdown": intro}, "background"),
        ("bl_decisions", "bulleted_list", {"label": "심의 결정"}, {"items": decisions}, "decision"),
        ("bl_open_issues", "bulleted_list", {"label": "미해결 쟁점"},
         {"items": open_issues}, "constraint"),
    ]
    if rows:
        blocks.append(("tbl_sources", "table", {
            "label": f"근거 출처 ({len(rows)}건)",
            "columns": [
                {"key": "frag", "label": "조각", "type": "text"},
                {"key": "page", "label": "원 보고서 페이지", "type": "text"},
                {"key": "block", "label": "블록 id", "type": "text"},
                {"key": "widget", "label": "위젯", "type": "text"},
                {"key": "gist", "label": "요지", "type": "text"},
            ],
        }, {"rows": rows}, "reference"))
    return _page("부록 — 심의 근거", blocks)


def build_report_draft(run_dir: Path, *, meeting_dir: Path | None = None,
                       style: str = "report", stills_dir: Path | None = None) -> dict:
    """실행 산출물 → report_archive_draft_v1 **완성 보고서** 초안.

    build_archive_draft 가 제작기록(메타 문서)을 만드는 것과 달리, 이쪽은 심의가
    정리한 내용 자체를 되돌린다 — 원 보고서 → 심의 → 더 나은 보고서.

    페이지 = 표지 격 개요 1장 + 씬 1개당 섹션 1장 + 부록 1장.
    본문은 씬 narration(심의 집필 정본), 근거 위젯은 원 보고서 블록을 위젯 타입
    그대로 복원한 것이며, 부록은 회의록의 결정·미해결 쟁점과 출처 표다.

    stills_dir 를 주면 씬 스틸을 image 위젯으로 얹고 로컬 경로를 캡션에 박은 뒤
    반환 dict 의 `pending_assets` 로 업로드 필요 목록을 함께 낸다.
    """
    if style not in REPORT_STYLES:
        raise ValueError(f"알 수 없는 style={style!r} — 지원: {', '.join(REPORT_STYLES)}")

    run_dir = Path(run_dir)
    norm = _load_json(run_dir / "report.norm.json")
    scenario = _load_json(run_dir / "scenario.json")
    frags_path = run_dir / "fragments.json"
    fragments = _load_json(frags_path) if frags_path.is_file() else []

    meeting_meta: dict | None = None
    minutes_md = ""
    n_turns = 0
    if meeting_dir is not None:
        meeting_dir = Path(meeting_dir)
        if (meeting_dir / "meta.json").is_file():
            meeting_meta = _load_json(meeting_dir / "meta.json")
        if (meeting_dir / "minutes.md").is_file():
            minutes_md = (meeting_dir / "minutes.md").read_text(encoding="utf-8")
        if (meeting_dir / "turns.jsonl").is_file():
            n_turns = sum(
                1 for line in (meeting_dir / "turns.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            )

    scenes = scenario.get("scenes", []) or []
    nodes = [_scene_node(scenario, s) for s in scenes]
    scene_tokens = []
    for scene, node in zip(scenes, nodes):
        acc: list[str] = [str(scene.get("name", "")), str(scene.get("narration", ""))]
        _strings(node, acc)
        scene_tokens.append(_tokens(" ".join(acc)))

    evidence = _collect_evidence(norm, fragments)
    buckets = _assign_evidence(evidence, scene_tokens)

    pages = [_report_cover_page(norm, scenario, meeting_meta, len(scenes), len(evidence), n_turns)]
    pending: list[dict] = []
    for i, (scene, node) in enumerate(zip(scenes, nodes), start=1):
        stills = _still_files(stills_dir, i, str(scene.get("name", "")))
        page, waiting = _report_section_page(i, scene, node, buckets[i - 1], stills)
        pages.append(page)
        pending.extend(waiting)
    pages.append(_report_appendix_page(minutes_md, evidence, meeting_meta))

    closed_at = (meeting_meta or {}).get("closed_at", "")
    report_date = closed_at[:10] if closed_at else datetime.date.today().isoformat()
    return {
        "_type": DRAFT_TYPE,
        "title": f"{norm.get('title', '')} (심의 정리본)",
        "report_date": report_date,
        "tags": ["webdesignagents", "심의정리본"],
        "pages": pages,
        "pending_assets": pending,
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
