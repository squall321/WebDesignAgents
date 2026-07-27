# P0 ingest — ReportArchive 복붙/REST/조각/마크다운 입력을 블록 구조 보존 정규화(report.norm.json)로 변환
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SUPPORTED_TYPE = "report_archive_draft_v1"

# 관용 입력 형태 — 판별은 _type 이 아니라 형태 스니핑으로 한다
FORM_DRAFT = "report_archive_draft_v1"
FORM_REST = "reportarchive_rest"
FORM_PAGES = "pages_only"
FORM_MARKDOWN = "markdown"

_EXPECTED_INPUTS = (
    "입력 형태를 인식하지 못했다. 받아들이는 형태는 4가지다. "
    "① report_archive_draft_v1 복붙 JSON — {_type, title, report_date, tags, pages[]}. "
    "② ReportArchive REST 응답 — {success, data:{...}} 봉투 또는 GET /api/reports/{id} 의 "
    "ReportRead(pages[].content/extra_blocks). "
    "③ pages 배열만 있는 조각 JSON — [{name, extra_blocks, content}] 또는 {pages:[...]}. "
    "④ 마크다운 텍스트 — # 헤딩 · - 불릿 · | 표."
)

# 마크다운 문법 제거용 (rich_text 평탄화 — search_text 자체 생성)
_MD_STRIP_RES = [
    re.compile(r"```[^`]*```", re.S),          # 코드 블록
    re.compile(r"`([^`]*)`"),                   # 인라인 코드 → 내용만
    re.compile(r"!\[[^\]]*\]\([^)]*\)"),        # 이미지
    re.compile(r"\[([^\]]*)\]\([^)]*\)"),       # 링크 → 라벨만
    re.compile(r"[*_]{1,3}([^*_]+)[*_]{1,3}"),  # 강조 → 내용만
    re.compile(r"^#{1,6}\s*", re.M),            # 헤딩 마커
    re.compile(r"^[-*+]\s+", re.M),             # 리스트 마커
]


def _strip_markdown(md: str) -> str:
    """마크다운 문법 기호를 제거하고 평문만 남긴다."""
    out = md
    for pat in _MD_STRIP_RES:
        if pat.groups:
            out = pat.sub(r"\1", out)
        else:
            out = pat.sub("", out)
    return re.sub(r"\s+", " ", out).strip()


def _collect_strings(node: Any, acc: list[str]) -> None:
    """알 수 없는 위젯 content 폴백 — 재귀로 문자열 값을 전부 수집한다."""
    if isinstance(node, str):
        s = node.strip()
        if s:
            acc.append(s)
    elif isinstance(node, dict):
        for v in node.values():
            _collect_strings(v, acc)
    elif isinstance(node, list):
        for v in node:
            _collect_strings(v, acc)


def block_text(block_type: str, content: dict | None) -> str:
    """위젯 타입별 텍스트 평탄화 — search_text 자체 생성의 핵심 (PLAN §4 P0).

    heading/rich_text/bulleted_list/key_value/table/comparison/flowchart/tree/
    raci_matrix/progress_bar 를 타입별로 추출하고, 그 외 타입은 문자열 재귀 수집 폴백.
    """
    if not isinstance(content, dict):
        return ""
    c = content
    if block_type == "heading":
        return str(c.get("text", "")).strip()
    if block_type == "rich_text":
        return _strip_markdown(str(c.get("markdown", "")))
    if block_type == "bulleted_list":
        return " ".join(str(x).strip() for x in c.get("items", []) if str(x).strip())
    if block_type == "key_value":
        parts = []
        for item in c.get("items", []):
            key = item.get("key", "")
            label = item.get("label", key)
            val = c.get(key, "")
            if label or val:
                parts.append(f"{label}: {val}".strip(": "))
        return " ".join(parts)
    if block_type == "table":
        parts = []
        for row in c.get("rows", []):
            if isinstance(row, dict):
                parts.append(" ".join(str(v) for v in row.values() if str(v).strip()))
        return " ".join(parts)
    if block_type == "comparison":
        parts = []
        for row in c.get("rows", []):
            label = row.get("label", "")
            vals = row.get("values", {})
            body = " / ".join(f"{k}: {v}" for k, v in vals.items())
            parts.append(f"{label} — {body}" if label else body)
        return " ".join(parts)
    if block_type in ("flowchart", "milestone", "progress_bar"):
        parts = []
        for item in c.get("items", []):
            label = str(item.get("label", "")).strip()
            desc = str(item.get("description", "") or item.get("note", "")).strip()
            val = item.get("value")
            seg = label
            if val is not None:
                seg = f"{seg} {val}%".strip()
            if desc:
                seg = f"{seg} — {desc}" if seg else desc
            if seg:
                parts.append(seg)
        return " ".join(parts)
    if block_type in ("tree", "network", "mind_map"):
        parts = []
        for row in c.get("rows", c.get("nodes", [])):
            label = str(row.get("label", "")).strip()
            sub = str(row.get("subtitle", "")).strip()
            if label:
                parts.append(f"{label} ({sub})" if sub else label)
        return " ".join(parts)
    if block_type == "raci_matrix":
        parts = [str(r.get("label", "")).strip() for r in c.get("roles", [])]
        for row in c.get("rows", []):
            label = str(row.get("label", "")).strip()
            if label:
                parts.append(label)
        return " ".join(p for p in parts if p)
    if block_type in ("image", "video", "cad_3d"):
        return str(c.get("caption", "") or c.get("alt", "")).strip()
    acc: list[str] = []
    _collect_strings(c, acc)
    return " ".join(acc)


def _collect_file_ids(node: Any, acc: set[str]) -> None:
    """블록 props/content 안의 file_id 참조를 재귀 수집한다."""
    if isinstance(node, dict):
        fid = node.get("file_id")
        if isinstance(fid, (str, int)) and str(fid).strip():
            acc.add(str(fid))
        for v in node.values():
            _collect_file_ids(v, acc)
    elif isinstance(node, list):
        for v in node:
            _collect_file_ids(v, acc)


# ---------------------------------------------------------------------------
# 관용 입력 어댑터 — 어떤 형태로 들어와도 draft 형태(pages[])로 맞춘 뒤 같은 정규화기를 태운다
# ---------------------------------------------------------------------------

_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_MD_BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.*\S)\s*$")
_MD_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]*-{2,}[\s:|-]*\|?\s*$")
_MD_FENCE_RE = re.compile(r"^\s*```")

_BLOCK_CODE = {"heading": "h", "rich_text": "rt", "bulleted_list": "bl", "table": "tbl"}


def _md_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|"):
        s = s[:-1]
    return [c.strip() for c in s.split("|")]


def _md_is_table_row(line: str) -> bool:
    return line.strip().startswith("|") and line.count("|") >= 2


def _md_block(kind: str, payload: Any) -> tuple[str, dict, dict]:
    """(type, props, content) 3튜플 — draft 페이지 조립 직전 중간 표현."""
    if kind == "heading":
        level, text = payload
        return "heading", {"level": level, "default_text": text}, {"text": text}
    if kind == "rich_text":
        return "rich_text", {}, {"markdown": payload}
    if kind == "bulleted_list":
        return "bulleted_list", {}, {"items": list(payload)}
    header, rows = payload
    columns = [{"key": f"c{i + 1}", "label": h, "type": "text"} for i, h in enumerate(header)]
    out_rows = [
        {f"c{i + 1}": cell for i, cell in enumerate(r[: len(header)])} for r in rows
    ]
    return "table", {"columns": columns}, {"rows": out_rows}


def markdown_to_draft(md: str, *, title: str | None = None, report_date: str = "") -> dict:
    """④ 사람이 구두 정리한 마크다운 → report_archive_draft_v1 형태 dict (PLAN §4 P0 어댑터).

    heading(#) · 불릿(-/*/+/1.) · 파이프 표 · 코드펜스를 블록으로 변환하고,
    H1 을 만나면 새 페이지를 연다. 순서·구조는 그대로 보존한다(평탄화 금지).
    """
    pages: list[dict] = []
    blocks: list[tuple[str, dict, dict]] = []
    page_name = ""

    def close_page() -> None:
        if blocks:
            pages.append({"name": page_name or f"{len(pages) + 1}페이지", "blocks": list(blocks)})
        blocks.clear()

    para: list[str] = []
    bullets: list[str] = []

    def flush_para() -> None:
        text = "\n".join(para).strip()
        para.clear()
        if text:
            blocks.append(_md_block("rich_text", text))

    def flush_bullets() -> None:
        if bullets:
            blocks.append(_md_block("bulleted_list", bullets))
            bullets.clear()

    lines = md.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if _MD_FENCE_RE.match(line):  # 코드펜스는 통째로 rich_text 로 보존
            flush_bullets()
            flush_para()
            fence = [line]
            i += 1
            while i < len(lines) and not _MD_FENCE_RE.match(lines[i]):
                fence.append(lines[i])
                i += 1
            if i < len(lines):
                fence.append(lines[i])
                i += 1
            blocks.append(_md_block("rich_text", "\n".join(fence)))
            continue

        heading = _MD_HEADING_RE.match(line)
        if heading:
            flush_bullets()
            flush_para()
            level, text = len(heading.group(1)), heading.group(2).strip()
            if level == 1:
                close_page()
                page_name = text
            blocks.append(_md_block("heading", (level, text)))
            i += 1
            continue

        if _md_is_table_row(line) and i + 1 < len(lines) and _MD_TABLE_SEP_RE.match(lines[i + 1]):
            flush_bullets()
            flush_para()
            header = _md_cells(line)
            i += 2
            rows = []
            while i < len(lines) and _md_is_table_row(lines[i]):
                rows.append(_md_cells(lines[i]))
                i += 1
            blocks.append(_md_block("table", (header, rows)))
            continue

        bullet = _MD_BULLET_RE.match(line)
        if bullet:
            flush_para()
            bullets.append(bullet.group(1).strip())
            i += 1
            continue

        if not line.strip():
            flush_bullets()
            flush_para()
        else:
            flush_bullets()
            para.append(line)
        i += 1

    flush_bullets()
    flush_para()
    close_page()

    if not pages:
        raise ValueError("마크다운에서 블록을 만들지 못했다 — 헤딩·불릿·표·문단이 모두 비었다.")

    if not title:
        for page in pages:
            for btype, _props, content in page["blocks"]:
                if btype == "heading" and content.get("text"):
                    title = str(content["text"])
                    break
            if title:
                break
    if not title:
        first = _strip_markdown(pages[0]["blocks"][0][2].get("markdown", ""))
        title = first[:80]
    if not title:
        raise ValueError("마크다운에서 제목을 찾지 못했다 — 첫 줄에 '# 제목' 을 넣어라.")

    out_pages = []
    for pi, page in enumerate(pages, start=1):
        extra_blocks, content, order = [], {}, []
        for bi, (btype, props, bcontent) in enumerate(page["blocks"], start=1):
            bid = f"p{pi}_{bi:02d}_{_BLOCK_CODE.get(btype, 'b')}"
            extra_blocks.append({"id": bid, "type": btype, "props": props})
            content[bid] = bcontent
            order.append(bid)
        out_pages.append({
            "name": page["name"],
            "extra_blocks": extra_blocks,
            "content": content,
            "blocks_order": order,
            "block_sections": {},
        })

    return {
        "_type": SUPPORTED_TYPE,
        "title": str(title).strip(),
        "report_date": report_date,
        "tags": [],
        "pages": out_pages,
    }


def _looks_like_page(node: Any) -> bool:
    return isinstance(node, dict) and any(
        k in node for k in ("extra_blocks", "content", "blocks", "blocks_order")
    )


def _norm_tags(raw_tags: Any) -> list[str]:
    """tags 표기 흔들림 흡수 — ["a"] / [{"name": "a"}] / "a,b" 를 모두 받는다."""
    if isinstance(raw_tags, str):
        return [t.strip() for t in raw_tags.split(",") if t.strip()]
    out = []
    for t in raw_tags or []:
        if isinstance(t, str):
            t = t.strip()
        elif isinstance(t, dict):
            t = str(t.get("name") or t.get("label") or t.get("tag") or "").strip()
        else:
            t = str(t).strip()
        if t:
            out.append(t)
    return out


def sniff_input(raw: Any) -> tuple[dict, str]:
    """어떤 입력이든 (draft 유사 dict, 형태 이름) 으로 정규화한다. 못 알아보면 ValueError."""
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        return markdown_to_draft(raw), FORM_MARKDOWN

    if isinstance(raw, list):
        if raw and all(_looks_like_page(p) for p in raw):
            return {"pages": raw}, FORM_PAGES
        raise ValueError(
            f"{_EXPECTED_INPUTS} 받은 것 — 길이 {len(raw)} 의 리스트인데 페이지 형태가 아니다."
        )

    if not isinstance(raw, dict):
        raise ValueError(f"{_EXPECTED_INPUTS} 받은 것 — {type(raw).__name__}.")

    # ② REST 봉투 {success, data:{...}} 언래핑 (중첩 대비 최대 3회)
    form = None
    node = raw
    for _ in range(3):
        if isinstance(node.get("pages"), list) or _looks_like_page(node):
            break
        inner = node.get("data") or node.get("report") or node.get("result")
        if not isinstance(inner, dict):
            break
        node, form = inner, FORM_REST

    if isinstance(node.get("pages"), list):
        if form is None:
            form = FORM_DRAFT if node.get("_type") == SUPPORTED_TYPE else (
                FORM_REST if any(k in node for k in ("id", "report_id", "created_at", "search_text"))
                else FORM_PAGES
            )
        return node, form
    if _looks_like_page(node):  # 페이지 없는 단일 보고서 — 통째로 한 페이지 취급
        page = dict(node)
        page.setdefault("name", str(node.get("title") or node.get("name") or ""))
        return {**node, "pages": [page]}, form or FORM_PAGES

    keys = ", ".join(sorted(str(k) for k in raw)[:12]) or "(빈 객체)"
    raise ValueError(f"{_EXPECTED_INPUTS} 받은 것 — 최상위 키 [{keys}] 에 pages 가 없다.")


def _infer_block_type(content: Any) -> str:
    """def 없이 content 만 있는 블록(REST blocks 슬롯)의 타입 추정 — 내용 유실 방지."""
    if not isinstance(content, dict):
        return "unknown"
    if "markdown" in content:
        return "rich_text"
    if "text" in content:
        return "heading"
    if "items" in content and isinstance(content.get("items"), list):
        return "bulleted_list"
    if "rows" in content:
        return "table"
    return "unknown"


def _page_blocks(page: dict) -> tuple[list[dict], dict]:
    """페이지 하나에서 (블록 정의 목록, 순서) 를 뽑는다.

    extra_blocks 의 인라인 content(ai-draft 형태)와 별도 content 맵을 모두 받고,
    blocks_order 에 빠진 블록도 뒤에 이어 붙여 조용한 유실을 막는다.
    """
    extra_blocks = page.get("extra_blocks") or []
    content_map = dict(page.get("content") or {})
    defs: dict[str, dict] = {}
    declared: list[str] = []
    for b in extra_blocks:
        if not isinstance(b, dict) or "id" not in b:
            continue
        bid = str(b["id"])
        defs[bid] = b
        declared.append(bid)
        if "content" in b and bid not in content_map:
            content_map[bid] = b["content"]

    # 템플릿 슬롯(blocks) — 정의 없이 content 만 있는 경우 타입을 추정해 살린다
    slots = page.get("blocks")
    if isinstance(slots, dict):
        for bid, c in slots.items():
            bid = str(bid)
            if bid not in content_map:
                content_map[bid] = c
            if bid not in defs:
                defs[bid] = {"id": bid, "type": _infer_block_type(content_map[bid]), "props": {}}

    order = [str(b) for b in (page.get("blocks_order") or []) if str(b) in defs]
    seen = set(order)
    for bid in declared + [b for b in content_map if b in defs]:
        if bid not in seen:
            order.append(bid)
            seen.add(bid)
    return [defs[bid] for bid in order], content_map


def normalize_report(raw: Any, assets_dir: Path | None = None, *, base_url: str | None = None) -> dict:
    """관용 입력(draft/REST/pages/마크다운) → report.norm.json dict (블록 구조 보존)."""
    doc, form = sniff_input(raw)

    title = str(doc.get("title") or doc.get("name") or "").strip()
    report_date = str(doc.get("report_date") or doc.get("date") or "")
    if not report_date:
        stamp = str(doc.get("created_at") or doc.get("updated_at") or "")
        report_date = stamp[:10] if len(stamp) >= 10 else ""

    pages_in = doc.get("pages") or []
    pages_out: list[dict] = []
    file_ids: set[str] = set()
    search_parts: list[str] = []

    for page in pages_in:
        if not isinstance(page, dict):
            continue
        name = str(page.get("name", ""))
        sections: dict = page.get("block_sections", {}) or {}
        block_defs, content_map = _page_blocks(page)

        blocks_out = []
        search_parts.append(name)
        for bdef in block_defs:
            bid = str(bdef["id"])
            btype = str(bdef.get("type", ""))
            props = bdef.get("props", {}) or {}
            content = content_map.get(bid)
            _collect_file_ids(props, file_ids)
            _collect_file_ids(content, file_ids)
            blocks_out.append(
                {
                    "id": bid,
                    "type": btype,
                    "props": props,
                    "content": content,
                    "section": sections.get(bid),  # block_sections 태그 보존 (설득 골격 힌트)
                }
            )
            txt = block_text(btype, content)
            if txt:
                search_parts.append(txt)
        pages_out.append({"name": name, "blocks": blocks_out})

    if not title:  # 메타에 제목이 없는 조각 입력 — 첫 heading 에서 승격
        for page in pages_out:
            for b in page["blocks"]:
                if b["type"] == "heading" and block_text("heading", b["content"]):
                    title = block_text("heading", b["content"])
                    break
            if title:
                break
    if not title:
        raise ValueError(
            "title 을 찾지 못했다 — 최상위 title/name 이나 heading 블록 중 하나는 있어야 한다."
        )
    search_parts.insert(0, title)

    # 보고서 id 가 있으면(REST) 그대로, 없으면(복붙) title|report_date 해시로 안정적 doc_id 파생
    raw_id = doc.get("id") or doc.get("report_id") or doc.get("doc_id")
    doc_id = re.sub(r"[^A-Za-z0-9]", "", str(raw_id))[:12] if raw_id else ""
    if not doc_id:
        doc_id = hashlib.sha1(f"{title}|{report_date}".encode("utf-8")).hexdigest()[:8]

    # 쓰레기 입력이 그럴듯한 납품물로 위장되는 것을 막는다 — 빈 보고서는 여기서 거부
    if not pages_out:
        raise ValueError("pages 가 비어 있다 — 변환할 내용이 없는 보고서")
    total_blocks = sum(len(p["blocks"]) for p in pages_out)
    blocks_with_text = sum(
        1 for p in pages_out for b in p["blocks"] if block_text(b["type"], b["content"])
    )
    if total_blocks == 0 or blocks_with_text == 0:
        raise ValueError(
            f"텍스트를 가진 블록이 없다 (블록 {total_blocks}개, 텍스트 0개) — "
            "content 가 채워진 보고서인지 확인하라"
        )

    from .assets import resolve_assets

    records = resolve_assets(sorted(file_ids), assets_dir=assets_dir, base_url=base_url)
    # assets 는 기존 계약 그대로 2키 유지, 해결 사유·이미지 메타는 assets_meta 로 덧붙인다
    assets = [{"file_id": r["file_id"], "local_path": r["local_path"]} for r in records]

    provided_search = doc.get("search_text")
    search_text = (
        provided_search.strip()
        if isinstance(provided_search, str) and provided_search.strip()
        else " ".join(search_parts)  # 위젯 텍스트 평탄화로 자체 생성
    )

    return {
        "doc_id": doc_id,
        "title": title,
        "report_date": report_date,
        "tags": _norm_tags(doc.get("tags")),
        "pages": pages_out,
        "assets": assets,
        "assets_meta": records,  # 해결 경로·미해결 사유·width/height/aspect
        "ai_summary": doc.get("ai_summary"),  # 복붙 모드에는 보통 없다 → None
        "search_text": search_text,
        "source_format": form,  # draft / rest / pages_only / markdown
    }


def ingest_report_file(
    path: Path, assets_dir: Path | None = None, base_url: str | None = None
) -> dict:
    """P0 진입점 — 파일을 읽어 정규화 dict 를 반환한다 (모듈 간 계약).

    JSON(복붙 draft·REST 응답·pages 조각)과 마크다운을 모두 받는다. 확장자가
    .md/.markdown/.txt 이거나 JSON 파싱이 실패하면 마크다운으로 해석한다.
    """
    text = Path(path).read_text(encoding="utf-8")
    raw: Any
    if Path(path).suffix.lower() in (".md", ".markdown", ".txt"):
        raw = text
    else:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError:
            raw = text  # JSON 이 아니면 마크다운으로 재시도(스니핑이 최종 판단)
    return normalize_report(raw, assets_dir=assets_dir, base_url=base_url)
