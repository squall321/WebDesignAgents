# P1 fragmentize — 정규화 보고서를 위젯 타입별 규칙으로 Claim/Evidence/Case/Metric/CTA 조각으로 1차 분해
from __future__ import annotations

from .ingest import block_text

# PLAN §4 P1 위젯 타입별 기본 매핑 표 (규칙 기반 1차 — LLM 정제는 prompts/fragmentize.md 어댑터 몫)
#   heading/rich_text/bulleted_list        → Claim · Case
#   table/comparison/key_value/chart 계열  → Metric · Evidence
#   flowchart/tree/network/mind_map        → 절차/구조 Evidence
#   milestone/raci_matrix/fmea             → Evidence
#   image/video/cad_3d                     → 시각 자산 (텍스트 조각 없음 — 스킵)
_CLAIM_SECTIONS = {"purpose", "background", "problem", "goal", "decision"}
_CASE_SECTIONS = {"reference", "current_state", "analysis"}
_CHART_TYPES = {"chart", "scatter", "progress_bar", "gauge", "histogram"}
_VISUAL_TYPES = {"image", "video", "cad_3d"}

# 조각 최대 텍스트 길이 — 씬 데이터/회의 인용에 쓰이므로 문장 단위로 짧게 유지
_MAX_TEXT = 200


def _clip(text: str, limit: int = _MAX_TEXT) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _classify(block_type: str, section: str | None) -> str | None:
    """위젯 타입(+block_sections 태그 힌트) → 조각 타입. None 이면 조각 생성 안 함."""
    if block_type in _VISUAL_TYPES:
        return None
    if block_type == "heading":
        return "claim"
    if block_type in ("rich_text", "bulleted_list"):
        if section in _CASE_SECTIONS:
            return "case"
        return "claim"
    if block_type in _CHART_TYPES:
        return "metric"
    if block_type in ("table", "comparison", "key_value"):
        # 수치 성격 섹션이면 metric, 그 외 evidence
        return "metric" if section == "schedule" else "evidence"
    if block_type in ("flowchart", "tree", "network", "mind_map"):
        return "evidence"  # 절차/구조 Evidence
    if block_type in ("milestone", "raci_matrix", "fmea"):
        return "evidence"
    return "claim"  # 미지 타입 폴백 — 텍스트가 있으면 주장 후보


def _item_texts(block_type: str, content: dict | None) -> list[str]:
    """항목형 위젯은 항목당 1조각으로 쪼갠다 (씬 배치 단위와 일치). 그 외는 통짜 1조각."""
    if not isinstance(content, dict):
        return []
    if block_type == "bulleted_list":
        return [str(x).strip() for x in content.get("items", []) if str(x).strip()]
    if block_type in ("flowchart", "milestone", "progress_bar"):
        out = []
        for item in content.get("items", []):
            label = str(item.get("label", "")).strip()
            desc = str(item.get("description", "") or item.get("note", "")).strip()
            val = item.get("value")
            seg = label
            if val is not None:
                seg = f"{seg} — {val}%".strip(" —")
            if desc:
                seg = f"{seg} — {desc}" if seg else desc
            if seg:
                out.append(seg)
        return out
    if block_type == "key_value":
        out = []
        for item in content.get("items", []):
            key = item.get("key", "")
            label = item.get("label", key)
            val = content.get(key, "")
            if val:
                out.append(f"{label}: {val}")
        return out
    if block_type == "comparison":
        out = []
        for row in content.get("rows", []):
            label = row.get("label", "")
            vals = row.get("values", {})
            body = " / ".join(f"{k}: {v}" for k, v in vals.items())
            if body:
                out.append(f"{label} — {body}" if label else body)
        return out
    if block_type == "table":
        out = []
        for row in content.get("rows", []):
            if isinstance(row, dict):
                cells = " · ".join(str(v) for v in row.values() if str(v).strip())
                if cells:
                    out.append(cells)
        return out
    whole = block_text(block_type, content)
    return [whole] if whole else []


# 규칙 기반 신뢰도 — 타입 매핑이 명확한 위젯일수록 높다 (LLM 정제 전 기준)
_CONFIDENCE = {
    "heading": 0.6,
    "rich_text": 0.55,
    "bulleted_list": 0.7,
    "key_value": 0.75,
    "table": 0.75,
    "comparison": 0.75,
    "flowchart": 0.8,
    "tree": 0.7,
    "raci_matrix": 0.7,
    "progress_bar": 0.8,
    "milestone": 0.75,
}


def fragmentize(norm: dict) -> list[dict]:
    """정규화 보고서 → 조각 목록 (모듈 간 계약).

    반환 조각: {frag_id: "RA-{doc_id}-{seq:03d}", type, text, source:{page, block_id},
                confidence} + 보조 키 widget/section (씬 배치 휴리스틱용).
    frag_id 목록은 P2 회의의 초기 known_refs 화이트리스트가 된다.
    """
    doc_id = norm["doc_id"]
    frags: list[dict] = []
    seq = 1
    for page in norm.get("pages", []):
        pname = page.get("name", "")
        for block in page.get("blocks", []):
            btype = block.get("type", "")
            ftype = _classify(btype, block.get("section"))
            if ftype is None:
                continue
            for text in _item_texts(btype, block.get("content")):
                frags.append(
                    {
                        "frag_id": f"RA-{doc_id}-{seq:03d}",
                        "type": ftype,
                        "text": _clip(text),
                        "source": {"page": pname, "block_id": block.get("id")},
                        "confidence": _CONFIDENCE.get(btype, 0.5),
                        "widget": btype,
                        "section": block.get("section"),
                    }
                )
                seq += 1
    return frags
