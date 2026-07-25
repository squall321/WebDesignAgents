# P0 ingest — ReportArchive 복붙 JSON(report_archive_draft_v1)을 블록 구조 보존 정규화(report.norm.json)로 변환
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

SUPPORTED_TYPE = "report_archive_draft_v1"

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


def _resolve_asset(assets_dir: Path, file_id: str) -> str | None:
    """assets_dir 에서 file_id 로 시작하는 로컬 파일을 찾는다. 없으면 None(스킵 기록)."""
    exact = assets_dir / file_id
    if exact.is_file():
        return str(exact)
    matches = sorted(assets_dir.glob(f"{file_id}.*"))
    return str(matches[0]) if matches else None


def normalize_report(raw: dict, assets_dir: Path | None = None) -> dict:
    """report_archive_draft_v1 dict → report.norm.json dict (블록 구조 보존)."""
    if raw.get("_type") != SUPPORTED_TYPE:
        raise ValueError(
            f"지원하지 않는 입력 포맷: _type={raw.get('_type')!r} (기대: {SUPPORTED_TYPE!r})"
        )
    title = str(raw.get("title", "")).strip()
    if not title:
        raise ValueError("title 이 비어 있다 — report_archive_draft_v1 필수 필드")
    report_date = str(raw.get("report_date", ""))
    # 복붙 모드에는 보고서 id 가 없다 — title|report_date 해시로 안정적 doc_id 파생
    doc_id = hashlib.sha1(f"{title}|{report_date}".encode("utf-8")).hexdigest()[:8]

    pages_out: list[dict] = []
    file_ids: set[str] = set()
    search_parts: list[str] = [title]

    for page in raw.get("pages", []):
        name = str(page.get("name", ""))
        content_map: dict = page.get("content", {}) or {}
        extra_blocks: list[dict] = page.get("extra_blocks", []) or []
        sections: dict = page.get("block_sections", {}) or {}
        defs = {b["id"]: b for b in extra_blocks if "id" in b}

        # blocks_order 순 정렬 — 비어 있으면 extra_blocks 선언 순서 폴백
        order = [bid for bid in (page.get("blocks_order") or []) if bid in defs]
        if not order:
            order = [b["id"] for b in extra_blocks if "id" in b]

        blocks_out = []
        search_parts.append(name)
        for bid in order:
            bdef = defs[bid]
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

    assets = []
    for fid in sorted(file_ids):
        local = _resolve_asset(assets_dir, fid) if assets_dir else None
        assets.append({"file_id": fid, "local_path": local})  # local_path=None → 스킵 기록

    return {
        "doc_id": doc_id,
        "title": title,
        "report_date": report_date,
        "tags": list(raw.get("tags", [])),
        "pages": pages_out,
        "assets": assets,
        "ai_summary": raw.get("ai_summary"),  # 복붙 모드에는 보통 없다 → None
        "search_text": " ".join(search_parts),  # 위젯 텍스트 평탄화로 자체 생성
    }


def ingest_report_file(path: Path, assets_dir: Path | None = None) -> dict:
    """P0 모드 1(파일 복붙) 진입점 — 파일을 읽어 정규화 dict 를 반환한다 (모듈 간 계약)."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"입력 파일이 JSON 객체가 아니다: {path}")
    return normalize_report(raw, assets_dir=assets_dir)
