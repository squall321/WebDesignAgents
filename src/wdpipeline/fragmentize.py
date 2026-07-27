# P1 fragmentize — 정규화 보고서를 위젯 타입별 규칙으로 Claim/Evidence/Case/Metric/CTA 조각으로 1차 분해
from __future__ import annotations

from .ingest import block_text
from .widgets import GROUP_BY_TYPE, extract_structured, structured_summary

# PLAN §4 P1 위젯 타입별 기본 매핑 표 (규칙 기반 1차 — LLM 정제는 prompts/fragmentize.md 어댑터 몫)
#   heading/rich_text/bulleted_list        → Claim · Case
#   table/comparison/key_value/chart 계열  → Metric · Evidence
#   flowchart/tree/network/mind_map        → 절차/구조 Evidence
#   milestone/raci_matrix/fmea             → Evidence
#   image/video/cad_3d 등 미디어군          → 시각 자산 (텍스트 조각 없음 — assets 채널)
_CLAIM_SECTIONS = {"purpose", "background", "problem", "goal", "decision"}
_CASE_SECTIONS = {"reference", "current_state", "analysis"}
_CHART_TYPES = {"chart", "scatter", "progress_bar", "gauge", "histogram"}
# 미디어군은 텍스트 조각을 만들지 않는다 — 파일 자산은 wdpipeline.assets 가 담당한다.
_VISUAL_TYPES = {t for t, g in GROUP_BY_TYPE.items() if g == "media"}

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


def _representative_text(btype: str, block: dict, summary: str) -> str:
    """구조 조각의 텍스트 — 한 줄 요약 뒤에 평탄화 본문을 붙여 _MAX_TEXT 로 자른다.

    구조 자체는 structured 로 온전히 실리므로 여기 텍스트는 심의 브리핑([F#] 인용)의
    가독용 요약이다. 행 단위 중복 조각을 만들지 않아 브리핑 top_k 를 표 하나가
    독점하던 문제(표 35행=조각 35건)를 없앤다.
    """
    body = block_text(btype, block.get("content"))
    return _clip(f"{summary} — {body}" if body else summary)


def fragmentize(norm: dict) -> list[dict]:
    """정규화 보고서 → 조각 목록 (모듈 간 계약).

    반환 조각: {frag_id: "RA-{doc_id}-{seq:03d}", type, text, source:{page, block_id},
                confidence} + 보조 키 widget/widget_type/section (씬 배치 휴리스틱용)
                + structured(구조 payload — 있는 블록에만).

    구조가 있는 위젯(표/다이어그램/수치/일정/키값군)은 **대표 조각 1건 + structured**
    로 압축한다. 항목 단위 텍스트 조각은 structured.rows/nodes/series 의 열화 사본이라
    같은 정보를 두 번 싣게 되고, 표 1개가 브리핑 조각 top_k 를 독점한다.
    텍스트군(heading/rich_text/bulleted_list)은 기존대로 항목당 1조각을 유지한다.

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
            payload = extract_structured(block)
            if payload is not None:
                summary = structured_summary(payload)
                texts = [_representative_text(btype, block, summary)]
            else:
                texts = [_clip(t) for t in _item_texts(btype, block.get("content"))]
            for text in texts:
                frag = {
                    "frag_id": f"RA-{doc_id}-{seq:03d}",
                    "type": ftype,
                    "text": text,
                    "source": {"page": pname, "block_id": block.get("id")},
                    "confidence": _CONFIDENCE.get(btype, 0.5),
                    "widget": btype,        # 하위 호환 (scenario._frags 가 이 키로 필터)
                    "widget_type": btype,
                    "section": block.get("section"),
                }
                if payload is not None:
                    frag["structured"] = payload
                frags.append(frag)
                seq += 1
    return frags
