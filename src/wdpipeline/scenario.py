# P3 scenario — 조각을 씬 템플릿 7종에 규칙 기반 배치(assemble_demo_scenario)하고 ScenarioDoc 를 검증(validate_scenario)
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from wdcore.models.scenario import ScenarioDoc, check_om_scenes_budget

from .format import (
    DEFAULT_FORMAT_ID,
    DEFAULT_MODULES_ROOT,
    FormatError,
    FormatSpec,
    load_format,
    module_dir,
    resolve_modules_root,
    resolve_tpl_module_id,
    tpl_short,
)

# repo 루트 기준 모듈 레지스트리 (src/wdpipeline/scenario.py → 두 단계 위가 repo)
_REPO_ROOT = Path(__file__).resolve().parents[2]

__all__ = [
    "DEFAULT_MODULES_ROOT",
    "TEMPLATE_ORDER",
    "assemble_demo_scenario",
    "narration_from_x_read",
    "resolve_modules_root",
    "slot_fit_report",
    "validate_scenario",
]

# 씬 타입 7종 — 설득 골격 순서 (PLAN §6.1). wide-16x9 포맷의 skeleton 과 같은 순서다.
TEMPLATE_ORDER = [
    "opening", "problem", "concept", "process", "differentiator", "proof", "closing",
]

# tpl 참조: "opening@1" 또는 모듈 id 를 그대로 쓴 "vtpl.hook@1"
_TPL_REF_RE = re.compile(r"^([a-z][a-z0-9_.-]*)@(\d+)$")


# ── 모듈 레지스트리 접근 ────────────────────────────────────────────────


def _load_module(module_id: str, modules_root: Path) -> dict:
    """모듈 id → module.yaml 을 로드한다 (디렉터리는 format.module_dir 이 해석)."""
    path = module_dir(module_id, modules_root) / "module.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_schema(module_id: str, modules_root: Path) -> dict:
    """모듈 id → schema.json 을 로드한다 (디렉터리는 format.module_dir 이 해석)."""
    path = module_dir(module_id, modules_root) / "schema.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ── 텍스트 유틸 ─────────────────────────────────────────────────────────


def _truncate(text: str, limit: int) -> str:
    """maxLength 절단 — 앞뒤 공백은 보존한다 (pre/accent/post 이어붙임 공백 유지).

    절단 지점이 어절 중간이면 마지막 공백까지 물러나 '개인 공…' 류의 어색한
    중간 절단을 피한다 (경계가 절반 이전이면 정보 손실이 커서 그대로 자른다).
    """
    if len(text) <= limit:
        return text
    cut = text[: max(limit - 1, 0)]
    sp = cut.rfind(" ")
    if sp >= max((limit - 1) // 2, 1):
        cut = cut[:sp].rstrip()
    return cut + "…"


def _clip(text: str, limit: int) -> str:
    """정리 + 절단 — 조립 휴리스틱용 (앞뒤 공백 제거 후 말줄임 절단)."""
    return _truncate(str(text).strip(), limit)


def _split_title(title: str, pre_max: int = 14, accent_max: int = 12, post_max: int = 14) -> dict:
    """제목을 pre/accent/post 3분할한다 (opening/closing title 스키마).

    AccentText 는 pre+accent+post 를 그대로 이어붙이므로 pre 끝·post 앞에 공백을 넣는다.
    """
    tokens = title.split()
    if not tokens:
        return {"accent": "제목 없음"}
    if len(tokens) == 1:
        return {"accent": _clip(tokens[0], accent_max)}
    out: dict[str, str] = {"pre": _clip(tokens[0], pre_max - 1) + " ",
                           "accent": _clip(tokens[1], accent_max)}
    rest = " ".join(tokens[2:])
    if rest:
        out["post"] = " " + _clip(rest, post_max - 1)
    return out


# ── 조각/블록 선택 헬퍼 ─────────────────────────────────────────────────


def _frags(fragments: list[dict], *, type: str | None = None,
           section: str | None = None, widget: str | None = None) -> list[dict]:
    out = []
    for f in fragments:
        if type is not None and f.get("type") != type:
            continue
        if section is not None and f.get("section") != section:
            continue
        if widget is not None and f.get("widget") != widget:
            continue
        out.append(f)
    return out


def _texts(fragments: list[dict], n: int, **kw) -> list[str]:
    return [f["text"] for f in _frags(fragments, **kw)[:n]]


def _first_text(fragments: list[dict], fallback: str, **kw) -> str:
    xs = _texts(fragments, 1, **kw)
    return xs[0] if xs else fallback


def _blocks_of_type(norm: dict, btype: str) -> list[dict]:
    """norm 페이지 순서대로 해당 타입 블록을 (페이지 이름 포함) 나열한다."""
    out = []
    for page in norm.get("pages", []):
        for b in page.get("blocks", []):
            if b.get("type") == btype:
                out.append({"page": page.get("name", ""), **b})
    return out


def _clean_page_name(name: str) -> str:
    """"1. 플랫폼 개요" → "플랫폼 개요" (선두 번호 제거)."""
    return re.sub(r"^\s*\d+\s*[.)]\s*", "", name).strip()


# ── 슬롯 용량 조회 — schema.json 이 단일 정본 ────────────────────────────
#
# 용량 상수를 코드에 박으면 스키마가 바뀔 때 조용히 어긋난다. 카탈로그 수용 실측
# (docs/analysis/widget-coverage.md §8)이 schema.json 을 직접 읽는 것과 같은 이유로
# 조립기도 maxItems/maxLength 를 스키마에서 읽는다.

_SCHEMA_CACHE: dict[tuple[str, str], dict] = {}


def _slot_cap(short: str, prop: str, label_key: str | None = None) -> tuple[int | None, int | None]:
    """템플릿 슬롯의 (maxItems, 라벨 maxLength). 스키마를 못 읽으면 (None, None)."""
    root = str(resolve_modules_root())
    key = (root, short)
    schema = _SCHEMA_CACHE.get(key)
    if schema is None:
        try:
            schema = _load_schema(f"tpl.{short}", Path(root))
        except Exception:  # noqa: BLE001 — 용량 조회 실패가 조립을 막지 않는다
            schema = {}
        _SCHEMA_CACHE[key] = schema
    node = (schema.get("properties") or {}).get(prop) or {}
    item_props = (node.get("items") or {}).get("properties") or {}
    lmax = ((item_props.get(label_key) or {}) if label_key else {}).get("maxLength")
    return node.get("maxItems"), lmax


# ── 용량 초과 대응 (§8 — 33행 표를 4행 슬롯에 넣는 문제) ──────────────────
#
# 앞 N개 절단이 왜 답이 아닌가: 33행 표에서 앞 4행만 남기면 화면의 표는 원문과 다른
# 표가 된다. 심의가 [F#] 로 인용한 근거와 화면이 어긋나면 영상이 근거를 잃는다.
# 그래서 넘칠 때는 네 가지를 순서대로 쓴다.
#   ① 그룹 요약  — 카테고리 열이 있으면 그룹별 건수로 **전 행을 대표**한다 (_group_rows)
#   ② 대표 선별  — 수치군은 값 극단 + 중앙값 (_extreme_indices),
#                  순서군은 첫·끝 고정 + 균등 표본 (_span_indices),
#                  계층은 얕은 레벨 우선 (_level_indices)
#   ③ 라벨 축약  — maxLength 초과는 어절 경계 축약(_truncate), 원문은 structured 에 남는다
#   ④ 분할 제안  — 한 슬롯으로 부족하면 씬 분할 힌트를 낸다 (slot_fit_report 의 split)
# 어느 경우든 생략 건수를 "외 N건"으로 화면에 명시한다 — 무언의 절단 금지.


def _omit_note(n: int, unit: str = "건") -> str:
    """생략 건수 명시 문구. 0 이면 빈 문자열(꼬리표를 붙이지 않는다)."""
    return f"외 {n}{unit}" if n > 0 else ""


def _span_indices(n: int, cap: int | None) -> list[int]:
    """순서가 의미인 목록(절차 단계·마일스톤)의 대표 표본 인덱스.

    앞 N개 절단은 '끝'을 지워 절차의 결말을 없앤다. 첫·마지막은 서사의 시작과 착지라
    반드시 남기고 중간을 균등 간격으로 건너뛴다. 반환은 오름차순(원 순서 유지).
    """
    if cap is None or cap >= n:
        return list(range(n))
    if cap <= 0:
        return []
    if cap == 1:
        return [0]
    picked = {round(i * (n - 1) / (cap - 1)) for i in range(cap)}
    for i in range(1, n - 1):  # 반올림 충돌로 개수가 모자라면 내부 인덱스로 채운다
        if len(picked) >= cap:
            break
        picked.add(i)
    return sorted(picked)


def _extreme_indices(values: list[float | None], cap: int | None) -> list[int]:
    """수치 계열의 대표 인덱스 — 최대 · 최소 · 중앙값 우선.

    앞 N개 절단은 원본 정렬 순서에 종속돼 최댓값이 통째로 빠질 수 있다. 최대·최소는
    주장의 양 끝이고 중앙값은 분포의 대표라, 이 셋이 남으면 독자가 '가장 높은 것 /
    가장 낮은 것 / 전형'을 잃지 않는다. 반환은 오름차순 — 원 순서(= 서사 순서)는 유지한다.
    """
    n = len(values)
    if cap is None or cap >= n:
        return list(range(n))
    if cap <= 0:
        return []
    order = sorted(range(n), key=lambda i: (values[i] is None, values[i] or 0.0, i))
    picked: list[int] = []
    for i in [order[-1], order[0], order[n // 2], *order]:
        if i not in picked:
            picked.append(i)
        if len(picked) == cap:
            break
    return sorted(picked)


def _level_indices(nodes: list[dict], cap: int | None) -> list[int]:
    """계층 그래프의 대표 인덱스 — 얕은 레벨 우선.

    concept.nodes 는 방사형 배치라 계층 자체를 못 그린다. 그렇다면 남길 가치가 큰 건
    상위 노드(루트·1단)다 — 잎 8개를 임의로 남기면 전체 구조를 오해한다.
    """
    n = len(nodes)
    if cap is None or cap >= n:
        return list(range(n))
    order = sorted(range(n), key=lambda i: (int(nodes[i].get("level") or 0), i))
    return sorted(order[:cap])


def _category_column(payload: dict) -> dict | None:
    """표에서 그룹 요약의 축이 될 카테고리 열 — **첫 열만** 본다 (없으면 None).

    기준 두 가지. ① 값 종류가 2종 이상, 행 수의 절반 이하 (33행 표의 카테고리 열은
    8종, 위젯명 열은 33종이라 축이 못 된다). ② 위치는 첫 열 — 표의 분류 축은 관례상
    맨 왼쪽이다. '종류가 가장 적은 열'을 고르면 RACI 매트릭스가 '부서 멤버 열의 I/R
    분포'로 요약되는 식의 엉뚱한 축이 잡힌다. 축이 아닌 표는 요약하지 않고 미수용으로
    남기는 편이 낫다 — 잘못 요약한 표는 틀린 근거가 된다.
    """
    rows = payload.get("rows") or []
    cols = payload.get("columns") or []
    if len(rows) < 4 or not cols:
        return None
    col = cols[0]
    uniq = {str(r.get(col["key"], "")).strip() for r in rows}
    uniq.discard("")
    return col if 2 <= len(uniq) <= max(2, len(rows) // 2) else None


def _group_rows(payload: dict) -> list[tuple[str, int]]:
    """카테고리 열 기준 (그룹 라벨, 건수) 목록 — 등장 순서 유지. 축이 없으면 빈 목록."""
    col = _category_column(payload)
    if col is None:
        return []
    counts: dict[str, int] = {}
    for r in payload.get("rows") or []:
        label = str(r.get(col["key"], "")).strip()
        if label:
            counts[label] = counts.get(label, 0) + 1
    return list(counts.items())


# ── 구조 payload 색인 (fragment["structured"]) ───────────────────────────


def _structured(
    fragments: list[dict], *, kind: str | None = None, shape: str | None = None
) -> list[tuple[dict, dict]]:
    """구조 payload 를 실은 조각만 (조각, payload) 쌍으로 (원 순서 유지)."""
    out: list[tuple[dict, dict]] = []
    for f in fragments:
        p = f.get("structured")
        if not isinstance(p, dict):
            continue
        if kind is not None and p.get("kind") != kind:
            continue
        if shape is not None and p.get("shape") != shape:
            continue
        out.append((f, p))
    return out


def _single_series(payload: dict) -> bool:
    """dataviz.bars / closing.stats 가 받을 수 있는 단일 계열인가.

    다계열(group)·분포형(values/n)은 가로 막대 하나로 환원하면 수치를 지어내는 셈이라
    받지 않는다 — 격자·분포 슬롯은 카탈로그에 아직 없다(§9 #4, #7).
    """
    entries = payload.get("series") or []
    if len(entries) < 2 or any(e.get("group") for e in entries):
        return False
    return all(e.get("value") is not None for e in entries)


def _candidates(fragments: list[dict]) -> dict:
    """구조 payload → 슬롯 후보 색인 (조립기와 slot_fit_report 의 공용 1차 정본).

    같은 종류가 여럿이면 정보량이 가장 많은 것(흐름도=노드 수, 표=행 수)을 대표로 뽑고
    동수면 먼저 등장한 것을 남긴다 — 기존 `_flow_items` 의 선택 규칙과 같다.
    """
    def most(xs: list[tuple[dict, dict]], size) -> tuple[dict, dict] | None:
        return max(xs, key=lambda x: size(x[1]), default=None)

    tables = _structured(fragments, kind="table")
    # 2안 비교는 comparison 위젯이 정본 — 3열(항목+A+B) 일반 표는 차선
    three = [x for x in tables
             if len(x[1].get("columns") or []) == 3 and len(x[1].get("rows") or []) >= 2]
    comp = [x for x in three if x[0].get("widget") == "comparison"]
    compare_table = (comp or three or [None])[0]
    rest = [x for x in tables if x is not compare_table]
    grouped = [x for x in rest if _category_column(x[1])]

    return {
        "flow": most(_structured(fragments, kind="graph", shape="flow"),
                     lambda p: len(p.get("nodes") or [])),
        "graph": most([x for x in _structured(fragments, kind="graph")
                       if x[1].get("shape") in ("tree", "network")],
                      lambda p: len(p.get("nodes") or [])),
        "timeline": next((x for x in _structured(fragments, kind="timeline")
                          if len(x[1].get("milestones") or []) >= 3), None),
        "series": next((x for x in _structured(fragments, kind="series")
                        if _single_series(x[1])), None),
        "pairs": _structured(fragments, kind="pairs"),
        "compare_table": compare_table,
        "summary_tables": sorted(grouped, key=lambda x: -len(x[1].get("rows") or [])),
    }


def _assign(cand: dict, shorts: set[str]) -> dict:
    """후보 → 실제 슬롯 소유자 배정. 같은 payload 가 두 씬에 중복 등장하지 않게 한다.

    소유자는 이번 조립이 실제로 쓰는 템플릿(shorts)에 따라 달라진다 — 예를 들어
    tpl.dataviz 가 뽑히면 단일 계열은 dataviz.bars 가 가져가고 closing.stats 는
    키값 payload 로 채운다.
    """
    plan = dict(cand)
    owner: dict[str, str] = {}

    def own(entry: tuple[dict, dict] | None, slot: str | None) -> None:
        if entry is not None and slot:
            owner.setdefault(str(entry[0].get("frag_id", "")), slot)

    plan["series_slot"] = None
    if cand["series"] is not None:
        if "dataviz" in shorts:
            plan["series_slot"] = "dataviz.bars"
        elif "closing" in shorts:
            plan["series_slot"] = "closing.stats"

    proof_cap = _slot_cap("proof", "cases")[0] or 3
    pairs_for_proof = cand["pairs"][:proof_cap] if "proof" in shorts else []
    table_for_proof = None
    if "proof" in shorts and len(pairs_for_proof) < proof_cap and cand["summary_tables"]:
        table_for_proof = cand["summary_tables"][0]
    remaining_pairs = [x for x in cand["pairs"] if x not in pairs_for_proof]
    pairs_for_closing = (
        (remaining_pairs or cand["pairs"])[:1]
        if "closing" in shorts and plan["series_slot"] != "closing.stats" else []
    )

    compare_slot = ("compare.rows" if "compare" in shorts
                    else "differentiator.flow" if "differentiator" in shorts else None)

    plan.update(
        {
            "pairs_for_proof": pairs_for_proof,
            "pairs_for_closing": pairs_for_closing,
            "table_for_proof": table_for_proof,
            "compare_slot": compare_slot,
            "timeline_slot": "timeline.milestones" if "timeline" in shorts else None,
        }
    )

    own(cand["flow"], "process.steps" if "process" in shorts else None)
    own(cand["graph"], "concept.nodes" if "concept" in shorts else None)
    own(cand["series"], plan["series_slot"])
    own(cand["timeline"], plan["timeline_slot"])
    own(cand["compare_table"], compare_slot)
    own(table_for_proof, "proof.cases")
    for x in pairs_for_proof:
        own(x, "proof.cases")
    for x in pairs_for_closing:
        own(x, "closing.stats")
    plan["owner"] = owner
    return plan


# ── 스키마 준수 강제 (절단·클램프) ──────────────────────────────────────


def _conform(data: Any, schema: dict) -> Any:
    """데이터를 스키마의 maxLength/maxItems/min·maximum/properties 에 맞게 절단·정리한다.

    minItems 충족은 조립 휴리스틱의 책임 — 여기서는 항목을 만들어내지 않는다.
    """
    stype = schema.get("type")
    if stype == "string" or (stype is None and isinstance(data, str)):
        s = str(data)
        max_len = schema.get("maxLength")
        return _truncate(s, max_len) if max_len is not None else s
    if stype == "integer" and isinstance(data, (int, float)):
        v = int(data)
        if "minimum" in schema:
            v = max(v, int(schema["minimum"]))
        if "maximum" in schema:
            v = min(v, int(schema["maximum"]))
        return v
    if stype == "array" and isinstance(data, list):
        items_schema = schema.get("items", {})
        out = [_conform(x, items_schema) for x in data]
        max_items = schema.get("maxItems")
        return out[:max_items] if max_items is not None else out
    if stype == "object" and isinstance(data, dict):
        props = schema.get("properties", {})
        out = {}
        for k, v in data.items():
            if k in props:
                out[k] = _conform(v, props[k])
            elif schema.get("additionalProperties", True) is not False:
                out[k] = v
        return out
    return data


# ── narration — x-read 필드 연결 ───────────────────────────────────────


def _read_strings(value: Any) -> list[str]:
    """x-read 로 표시된 값에서 낭독 문자열을 뽑는다 (pre/accent/post 는 이어붙임)."""
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        if any(k in value for k in ("pre", "accent", "post")):
            joined = "".join(str(value.get(k, "")) for k in ("pre", "accent", "post"))
            return [joined] if joined.strip() else []
        out = []
        for v in value.values():
            out.extend(_read_strings(v))
        return out
    if isinstance(value, list):
        out = []
        for v in value:
            out.extend(_read_strings(v))
        return out
    return []


def _collect_x_read(data: Any, schema: dict) -> list[str]:
    """스키마 선언 순서대로 x-read 필드 값을 수집한다 — narration 연결의 원천."""
    out: list[str] = []
    if schema.get("x-read"):
        out.extend(_read_strings(data))
        return out
    if schema.get("type") == "object" and isinstance(data, dict):
        for key, sub in schema.get("properties", {}).items():
            if key in data:
                out.extend(_collect_x_read(data[key], sub))
    elif schema.get("type") == "array" and isinstance(data, list):
        items_schema = schema.get("items", {})
        for item in data:
            out.extend(_collect_x_read(item, items_schema))
    return out


def narration_from_x_read(data: dict, schema: dict, dur: float | None = None, rate: float = 5.5) -> str:
    """x-read 문자열을 문장으로 이어 TTS 내레이션 대본을 만든다.

    dur 가 주어지면 낭독 예산(dur × rate 자, 공백 제외)을 넘지 않도록 문장 단위로
    앞에서부터 채운다 — 게이트 2(narration-rate)와 같은 기준. 첫 문장은 예산을
    넘어도 남긴다(빈 내레이션 방지, 게이트가 dur 재조정을 제안하게 둔다).
    """
    parts = _collect_x_read(data, schema)
    sents = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if p[-1] not in ".!?…":
            p += "."
        sents.append(p)
    if dur is None:
        return " ".join(sents)
    budget = int(dur * rate)
    picked: list[str] = []
    used = 0
    for s in sents:
        n = len(s.replace(" ", ""))
        if picked and used + n > budget:
            break
        picked.append(s)
        used += n
    return " ".join(picked)


# ── 씬별 데이터 조립 휴리스틱 (규칙 기반 — LLM 무호출) ───────────────────


def _frame(norm: dict, idx: int) -> dict:
    return {
        "brand": _clip(norm["title"], 24),
        "total": f"{len(TEMPLATE_ORDER):02d}",
        "idx": f"{idx:02d}",
    }


def _build_opening(norm: dict, fragments: list[dict]) -> dict:
    tags = norm.get("tags", [])
    subtitle = _first_text(
        fragments, f"{norm.get('report_date', '')} 보고서", type="claim", widget="rich_text"
    )
    return {
        "badge": _clip(tags[0] if tags else "REPORT", 30),
        "title": _split_title(norm["title"]),
        "subtitle": _clip(subtitle, 40),
        "footnote": _clip(norm.get("report_date", ""), 30),
        "dotCount": max(3, min(8, len(norm.get("pages", [])) + 1)),
    }


def _build_problem(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    purpose = _texts(fragments, 6, type="claim", section="purpose")
    claims = _texts(fragments, 6, type="claim")
    pool = purpose or claims or ["보고 내용 정리가 필요합니다"]
    tags = norm.get("tags", [])
    failures = [_clip(t, 20) for t in (purpose or claims)[:4]]
    while len(failures) < 2:
        failures.append("정리된 근거 부재")
    accent = tags[1] if len(tags) > 1 else norm["title"].split()[0]
    return {
        "kicker": "문제 인식",
        "title": _clip(pool[0], 30),
        "chat": {
            "windowLabel": _clip("기존 방식 — 문서 검색", 24),
            "question": _clip(pool[0], 40),
            "barWidths": [500, 560, 460, 320],
            "verdict": _clip(pool[1] if len(pool) > 1 else "정리되지 않은 답", 40),
        },
        "claim": {
            "lead": _clip(norm["title"] + " —", 30),
            "strong": {"pre": "핵심은 ", "accent": _clip(accent, 8), "post": " 입니다"},
            "tail": " 확인하세요.",
        },
        "failures": failures,
        "conclusion": _clip(pool[-1], 40),
        "frame": _frame(norm, idx),
    }


def _concept_nodes(norm: dict) -> list[dict]:
    names = [_clean_page_name(p.get("name", "")) for p in norm.get("pages", [])]
    names = [n for n in names if n] + [t for t in norm.get("tags", [])]
    nodes = []
    seen = set()
    for n in names:
        key = n[:12]
        if key in seen:
            continue
        seen.add(key)
        nodes.append({"ini": n[0], "name": _clip(n, 12)})
        if len(nodes) == 8:
            break
    i = 1
    while len(nodes) < 4:
        nodes.append({"ini": str(i), "name": f"항목 {i}"})
        i += 1
    return nodes


def _flow_items(norm: dict) -> list[dict]:
    """가장 항목이 많은 flowchart 블록의 items (절차 씬의 원천)."""
    best: list[dict] = []
    for b in _blocks_of_type(norm, "flowchart"):
        items = (b.get("content") or {}).get("items", [])
        if len(items) > len(best):
            best = items
    return best


def _graph_nodes(payload: dict) -> tuple[list[dict], int]:
    """graph payload(tree/network) → concept.nodes 항목 + 생략 건수.

    §3 network/tree → tpl.concept.nodes. 계층·엣지는 방사형 배치가 표현하지 못하므로
    얕은 레벨 우선으로 남기고(_level_indices), 라벨은 어절 경계로 축약한다.
    원문 라벨은 fragments[].structured 에 그대로 남아 심의가 다시 읽을 수 있다.
    """
    cap, name_max = _slot_cap("concept", "nodes", "name")
    nodes = payload.get("nodes") or []
    out: list[dict] = []
    seen: set[str] = set()
    for i in _level_indices(nodes, cap):
        label = str(nodes[i].get("label") or "").strip()
        if not label:
            continue
        name = _clip(label, name_max or 12)
        if name in seen:
            continue
        seen.add(name)
        out.append({"ini": label[0], "name": name})
    return out, max(len(nodes) - len(out), 0)


def _build_concept(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    tags = norm.get("tags", [])
    title = _first_text(fragments, norm["title"], type="claim", widget="heading")

    # 노드 — graph payload(tree/network) 우선, 없으면 기존 페이지 이름 경로로 폴백
    nodes, omitted = ([], 0)
    if plan.get("graph") is not None:
        nodes, omitted = _graph_nodes(plan["graph"][1])
    if len(nodes) < 4:
        nodes, omitted = _concept_nodes(norm), 0

    # 라운드 — 흐름도 앞 3단계 (기존 동작: _flow_items 의 label/description)
    flow_nodes = (plan["flow"][1].get("nodes") or []) if plan.get("flow") else []
    items = [{"label": n.get("label", ""), "description": n.get("note", "")} for n in flow_nodes]
    items = items or _flow_items(norm)
    rounds = [
        {
            "chip": f"S{i + 1}",
            "name": _clip(item.get("label", f"단계 {i + 1}"), 14),
            "desc": _clip(item.get("description", "") or item.get("label", ""), 40),
        }
        for i, item in enumerate(items[:3])
    ]
    while len(rounds) < 2:
        n = len(rounds) + 1
        rounds.append({"chip": f"S{n}", "name": f"단계 {n}", "desc": "보고서 내용 정리"})

    summary = norm.get("ai_summary") or _first_text(fragments, norm["title"], type="claim")
    # 생략은 화면에 밝힌다 — concept 에는 푸터가 없어 outcome.desc 꼬리에 붙인다
    note = _omit_note(omitted, "개 노드")
    desc = f"{_clip(summary, 40 - len(note) - 3)} · {note}" if note else _clip(summary, 40)
    return {
        "kicker": _clip(tags[1] if len(tags) > 1 else "접근", 16),
        "title": _clip(title, 40),
        "center": _clip(tags[0] if tags else "핵심", 6),
        "nodes": nodes,
        "rounds": rounds,
        "outcome": {"title": "한눈 요약", "desc": desc},
        "frame": _frame(norm, idx),
    }


def _build_process(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§3 flowchart(graph/flow) → tpl.process.steps — items 순서·label→name·description→desc."""
    cap, name_max = _slot_cap("process", "steps", "name")
    nodes = (plan["flow"][1].get("nodes") or []) if plan.get("flow") else []
    omitted = 0
    if nodes:
        keep = _span_indices(len(nodes), cap)
        omitted = len(nodes) - len(keep)
        # n 은 **원문 단계 번호**다 — 표본이면 번호가 건너뛰어 생략이 눈에 보인다
        steps = [
            {
                "n": f"{i + 1:02d}",
                "name": _clip(nodes[i].get("label") or f"단계 {i + 1}", name_max or 12),
                "desc": _clip(nodes[i].get("note") or nodes[i].get("label") or "", 40),
            }
            for i in keep
        ]
    else:  # structured 없음 → 기존 텍스트 경로
        items = _flow_items(norm) or [
            {"label": t} for t in _texts(fragments, cap or 6, type="evidence")
        ]
        steps = [
            {
                "n": f"{i + 1:02d}",
                "name": _clip(item.get("label", f"단계 {i + 1}"), name_max or 12),
                "desc": _clip(item.get("description", "") or item.get("label", ""), 40),
            }
            for i, item in enumerate(items[: cap or 6])
        ]
    while len(steps) < 3:
        n = len(steps) + 1
        steps.append({"n": f"{n:02d}", "name": f"단계 {n}", "desc": "보고서 참조"})
    title = _first_text(fragments, "진행 절차", type="evidence", widget="flowchart")
    footnote = {"pre": _clip(f"출처: {norm['title']}", 30)}
    if omitted:
        footnote["post"] = _clip(_omit_note(omitted, "단계는 원문 참조"), 40)
    return {
        "kicker": "절차",
        "title": _clip(f"{_clean_page_name(norm['title'])} — 진행 흐름", 40)
        if nodes or _flow_items(norm) else _clip(title, 40),
        "steps": steps,
        "footnote": footnote,
        "frame": _frame(norm, idx),
    }


def _build_differentiator(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    cap, _ = _slot_cap("differentiator", "flow", "label")
    omitted = 0
    flow = []
    entry = plan.get("compare_table")
    if entry is not None and plan.get("compare_slot") == "differentiator.flow":
        # 2안 비교 표(항목 + A + B)를 반박 카드로 — 행 순서가 의미이므로 첫·끝 표본
        payload = entry[1]
        cols, rows_p = payload["columns"], payload["rows"]
        keep = _span_indices(len(rows_p), cap)
        omitted = len(rows_p) - len(keep)
        for j, i in enumerate(keep):
            row = rows_p[i]
            flow.append(
                {
                    "chip": f"C{j + 1}",
                    "label": _clip(row.get(cols[0]["key"]) or f"관점 {j + 1}", 16),
                    "quote": _clip(row.get(cols[1]["key"]) or "", 40),
                    "tag": _clip(row.get(cols[2]["key"]) if len(cols) > 2 else "비교 항목", 24),
                    "tagTone": "info",
                }
            )
        flow = [f for f in flow if f["quote"]]
    from_structured = bool(flow)
    if not flow:  # structured 없음 → 기존 raw comparison 경로
        rows: list[dict] = []
        for b in _blocks_of_type(norm, "comparison"):
            rows = (b.get("content") or {}).get("rows", [])
            if rows:
                break
        for i, row in enumerate(rows[: cap or 2]):
            vals = list((row.get("values") or {}).values())
            flow.append(
                {
                    "chip": f"C{i + 1}",
                    "label": _clip(row.get("label", f"관점 {i + 1}"), 16),
                    "quote": _clip(str(vals[0]) if vals else row.get("label", ""), 40),
                    "tag": _clip(str(vals[1]) if len(vals) > 1 else "비교 항목", 24),
                    "tagTone": "info",
                }
            )
    if not flow:
        ev = _texts(fragments, 2, type="evidence") or ["보고서 근거"]
        flow = [
            {"chip": f"C{i + 1}", "label": _clip(f"근거 {i + 1}", 16),
             "quote": _clip(t, 40), "tag": "보고서 발췌", "tagTone": "info"}
            for i, t in enumerate(ev[:2])
        ]
    members = [{"ini": n["ini"]} for n in _concept_nodes(norm)[:8]]
    while len(members) < 3:
        members.append({"ini": str(len(members) + 1)})
    # 판정 문구는 실제로 실린 표의 캡션 — 다른 표의 요약을 붙이면 화면과 근거가 어긋난다
    verdict = (entry[1].get("caption") if from_structured else "") or \
        _first_text(fragments, "보고서 근거로 정리", type="evidence", widget="comparison")
    return {
        "kicker": "차별점",
        "title": _clip(_first_text(fragments, "무엇이 다른가", type="claim", widget="heading"), 40),
        "flow": flow,
        "converge": {
            "chip": "정리",
            "label": _clip("종합", 12),
            "members": members,
            "verdict": _clip(verdict, 30),
        },
        "footnote": (
            {"pre": _clip(f"출처: {norm['title']}", 30),
             "post": _clip(_omit_note(omitted, "행은 원문 참조"), 40)}
            if omitted else {"pre": _clip(f"출처: {norm['title']}", 30)}
        ),
        "frame": _frame(norm, idx),
    }


def _pairs_line(pairs: list[dict], limit: int) -> tuple[str, int]:
    """키값 쌍을 "라벨: 값 · 라벨: 값" 한 줄로 — (문자열, 실린 쌍 수).

    값은 28자로 먼저 축약한다. 한 쌍이 desc 를 통째로 먹으면 카드 하나에 한 쌍만
    남아 '스펙 목록'이 되지 않는다 — 여러 쌍이 보이는 편이 스펙표의 성격에 맞다.
    """
    parts: list[str] = []
    for p in pairs:
        seg = f"{p.get('label') or p.get('key')}: {_clip(str(p.get('value', '')), 28)}".strip()
        if not seg or seg.endswith(":"):
            continue
        if parts and len(" · ".join([*parts, seg])) > limit:
            break
        parts.append(seg)
    return _clip(" · ".join(parts), limit), len(parts)


def _pairs_case(entry: tuple[dict, dict], i: int) -> dict:
    """§3 key_value(pairs) → proof.cases 근거 카드 (closing.stats 3칸을 넘는 스펙 목록)."""
    payload = entry[1]
    pairs = payload.get("pairs") or []
    desc, carried = _pairs_line(pairs, 70)
    left = len(pairs) - carried
    return {
        "rpt": _clip(f"스펙 {i + 1}", 12),
        "meta": _clip(f"{len(pairs)}쌍 중 {carried}쌍", 16),
        "title": _clip(payload.get("caption") or "주요 사양", 24),
        "desc": desc or "값 미기재",
        "badge": _clip(_omit_note(left, "쌍 원문 수록") or "원문 그대로", 24),
        "badgeTone": "info",
    }


def _table_case(entry: tuple[dict, dict]) -> dict | None:
    """표 payload → proof.cases 그룹 요약 카드.

    33행 표를 4행 슬롯에 앞 4행만 넣으면 나머지 29행이 조용히 사라진다. 카테고리 열이
    있으면 그룹별 건수가 **전 행을 대표**하므로 정보가 왜곡되지 않는다 — 대신 개별 행은
    화면에서 잃는다(격자 표 씬이 생기기 전까지의 차선책, §9 #1).
    """
    payload = entry[1]
    groups = _group_rows(payload)
    if not groups:
        return None
    rows = payload.get("rows") or []
    cols = payload.get("columns") or []
    desc, shown = "", 0
    for label, n in groups:
        seg = f"{label} {n}"
        if desc and len(f"{desc} · {seg}") > 70:
            break
        desc = f"{desc} · {seg}" if desc else seg
        shown += 1
    return {
        "rpt": _clip("표 집계", 12),
        "meta": _clip(f"{len(cols)}열×{len(rows)}행", 16),
        "title": _clip(payload.get("caption") or "표 요약", 24),
        "desc": _clip(desc, 70) or "집계 없음",
        "badge": _clip(_omit_note(len(groups) - shown, "군 원문 수록")
                       or f"{len(groups)}군 전수 집계", 24),
        "badgeTone": "info",
    }


def _build_proof(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    cap = _slot_cap("proof", "cases")[0] or 3
    cases: list[dict] = []
    # 구조 payload 우선 — 키값(스펙 목록) → 표(그룹 요약) → 페이지 근거 순으로 칸을 채운다
    for i, entry in enumerate(plan.get("pairs_for_proof") or []):
        cases.append(_pairs_case(entry, i))
    if plan.get("table_for_proof") is not None and len(cases) < cap:
        card = _table_case(plan["table_for_proof"])
        if card:
            cases.append(card)
    for pi, page in enumerate(norm.get("pages", []), start=1):
        if len(cases) >= cap:
            break
        pname = page.get("name", "")
        page_ev = [f for f in fragments
                   if f.get("source", {}).get("page") == pname and f["type"] in ("evidence", "metric")]
        if not page_ev:
            continue
        cases.append(
            {
                "rpt": _clip(f"페이지 {pi}", 12),
                "meta": _clip(f"근거 {len(page_ev)}건", 16),
                "title": _clip(_clean_page_name(pname), 24),
                "desc": _clip(page_ev[0]["text"], 70),
                "badge": _clip(f"✓ {page_ev[0].get('section') or '근거'} 수록", 24),
                "badgeTone": "info",
            }
        )
    while len(cases) < 2:
        n = len(cases) + 1
        cases.append(
            {"rpt": f"페이지 {n}", "meta": "요약", "title": _clip(norm["title"], 24),
             "desc": _clip(norm.get("search_text", norm["title"]), 70),
             "badge": "보고서 요약", "badgeTone": "info"}
        )
    return {
        "kicker": "실증",
        "title": _clip(f"{norm['title']} — 근거 하이라이트", 40),
        "cases": cases,
        "footnote": {"pre": _clip(f"전체 근거는 원문 {len(norm.get('pages', []))}페이지 참조", 30)},
        "frame": _frame(norm, idx),
    }


def _fmt_num(v: float) -> str:
    return f"{v:g}"


def _build_closing(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§3 key_value/단일계열 series → closing.stats (수치는 값 극단 + 중앙값 대표)."""
    cap, d_max = _slot_cap("closing", "stats", "d")
    stats: list[dict] = []
    omitted, unit_word = 0, "건"

    if plan.get("series_slot") == "closing.stats" and plan.get("series") is not None:
        payload = plan["series"][1]
        entries = [e for e in payload.get("series") or [] if e.get("value") is not None]
        keep = _extreme_indices([e.get("value") for e in entries], cap)
        omitted, unit_word = len(entries) - len(keep), "계열"
        unit = payload.get("unit") or ""
        stats = [
            {"v": _clip(f"{_fmt_num(entries[i]['value'])}{unit}", 14),
             "d": _clip(entries[i].get("label", ""), d_max or 24)}
            for i in keep
        ]
    elif plan.get("pairs_for_closing"):
        payload = plan["pairs_for_closing"][0][1]
        pairs = payload.get("pairs") or []
        keep = _span_indices(len(pairs), cap)
        omitted, unit_word = len(pairs) - len(keep), "쌍"
        stats = [
            {"v": _clip(str(pairs[i].get("value", "")) or "-", 14),
             "d": _clip(pairs[i].get("label") or pairs[i].get("key", ""), d_max or 24)}
            for i in keep
        ]

    if len(stats) < 2:  # structured 없음 → 기존 raw progress_bar / 조각 수 경로
        stats = []
        for b in _blocks_of_type(norm, "progress_bar"):
            for item in (b.get("content") or {}).get("items", []):
                if "value" in item:
                    stats.append(
                        {"v": _clip(f"{item['value']}%", 14),
                         "d": _clip(item.get("label", ""), 24)}
                    )
                if len(stats) == 3:
                    break
            if len(stats) == 3:
                break
        omitted = 0
    if len(stats) < 2:
        stats = [
            {"v": f"{len(norm.get('pages', []))}페이지", "d": "보고서 구성"},
            {"v": f"{len(fragments)}건", "d": "추출된 근거 조각"},
        ][: max(2, len(stats))]

    tags = norm.get("tags", [])
    ctas = [{"text": _clip(t, 18)} for t in tags[:3]] or [{"text": "보고서 전문 확인"}]
    note = _omit_note(omitted, unit_word)
    if note:
        footnote = f"{_clip('원문: ' + norm['title'], 30)} · {note}"
    else:
        footnote = f"원문: {norm['title']} ({norm.get('report_date', '')})"
    return {
        "stats": stats[: cap or 3],
        "title": _split_title(norm["title"]),
        "subtitle": _clip(" · ".join(tags) if tags else "보고서 요약", 30),
        "ctas": ctas,
        "footnote": _clip(footnote, 40),
    }


# ── 대체 템플릿 빌더 (구조 payload 와 정확 대응하는 씬 3종) ────────────────


def _build_compare(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§3 comparison 2안(table) → tpl.compare — cases→a/b 패널, rows→행 짝."""
    entry = plan.get("compare_table")
    payload = entry[1]
    cols, rows_p = payload["columns"], payload["rows"]
    cap, aspect_max = _slot_cap("compare", "rows", "aspect")
    keep = _span_indices(len(rows_p), cap)
    omitted = len(rows_p) - len(keep)
    rows = []
    for j, i in enumerate(keep):
        r = rows_p[i]
        rows.append(
            {
                "aspect": _clip(r.get(cols[0]["key"]) or f"{j + 1}", aspect_max or 4),
                "a": _clip(r.get(cols[1]["key"]) or "-", 44),
                "b": _clip(r.get(cols[2]["key"]) or "-", 44),
            }
        )
    concl = payload.get("caption") or f"{cols[1]['label']} vs {cols[2]['label']}"
    if omitted:
        concl = f"{_clip(concl, 26 - len(_omit_note(omitted, '행')) - 3)} · {_omit_note(omitted, '행')}"
    return {
        "kicker": "대비",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 비교", 40),
        "panels": {
            "a": {"tag": "A", "label": _clip(cols[1]["label"], 20)},
            "b": {"tag": "B", "label": _clip(cols[2]["label"], 20)},
        },
        "rows": rows,
        "conclusion": {"text": _clip(concl, 26)},
        "frame": _frame(norm, idx),
    }


def _build_dataviz(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§3 progress_bar/chart 단일계열(series) → tpl.dataviz.bars — value/axisMax 비례."""
    payload = plan["series"][1]
    cap, label_max = _slot_cap("dataviz", "bars", "label")
    entries = [e for e in payload.get("series") or [] if e.get("value") is not None]
    keep = _extreme_indices([e.get("value") for e in entries], cap)
    omitted = len(entries) - len(keep)
    unit = payload.get("unit") or ""
    bars = [
        {
            "label": _clip(entries[i].get("label", ""), label_max or 9),
            "value": max(float(entries[i]["value"]), 0.0),   # 0 기준선 강제 — 음수 금지
            "display": _clip(f"{_fmt_num(entries[i]['value'])}{unit}", 7),
        }
        for i in keep
    ]
    # 강조 막대는 정확히 1개(스키마 contains 강제) — 값이 가장 큰 막대를 주장으로 세운다
    top = max(range(len(bars)), key=lambda i: bars[i]["value"])
    bars[top]["emphasis"] = True
    axis_max = (payload.get("axis") or {}).get("max")
    data = {
        "kicker": "수치",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 수치", 40),
        "bars": bars,
        "headline": {"value": _clip(bars[top]["display"], 5),
                     "desc": _clip(bars[top]["label"], 16)},
        "claim": {"text": _clip(payload.get("caption") or "보고서 수치 근거", 28)},
        "frame": _frame(norm, idx),
    }
    if unit:
        data["unit"] = _clip(unit, 8)
    if isinstance(axis_max, (int, float)) and axis_max > 0:
        data["axisMax"] = float(axis_max)
    if omitted:  # 생략은 근거 줄에 명시 — 5칸 막대가 전부인 척하지 않는다
        data["insights"] = [{"text": _clip(_omit_note(omitted, "계열은 원문 참조"), 26)}]
    return data


# 원문 status 표기 → 스키마 3태
_STATUS_MAP = {
    "done": "done", "completed": "done", "complete": "done", "완료": "done",
    "current": "current", "in_progress": "current", "진행": "current", "진행 중": "current",
    "planned": "planned", "todo": "planned", "예정": "planned", "계획": "planned",
}


def _build_timeline(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§3 milestone(timeline) → tpl.timeline.milestones — status done/current/planned 그대로."""
    payload = plan["timeline"][1]
    ms = payload.get("milestones") or []
    cap, name_max = _slot_cap("timeline", "milestones", "name")
    keep = _span_indices(len(ms), cap)
    omitted = len(ms) - len(keep)
    items = []
    for i in keep:
        m = ms[i]
        raw = str(m.get("status") or "").strip()
        item = {
            "date": _clip(str(m.get("date") or "-"), 10),
            "name": _clip(m.get("label", ""), name_max or 14),
            "status": _STATUS_MAP.get(raw, _STATUS_MAP.get(raw.lower(), "planned")),
        }
        if m.get("note"):
            item["desc"] = _clip(str(m["note"]), 34)
        items.append(item)
    # current 는 정확히 1개(스키마 contains 강제). 원문에 여럿/없으면 시간 순서로 정리한다.
    cur = [j for j, it in enumerate(items) if it["status"] == "current"]
    if len(cur) > 1:
        for j in cur[1:]:
            items[j]["status"] = "done" if j < cur[0] else "planned"
    elif not cur:
        done = [j for j, it in enumerate(items) if it["status"] == "done"]
        items[done[-1] if done else 0]["status"] = "current"
    data = {
        "kicker": "로드맵",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 일정", 40),
        "milestones": items,
        "frame": _frame(norm, idx),
    }
    rng = payload.get("range") or {}
    foot = " ~ ".join(x for x in (rng.get("start"), rng.get("end")) if x)
    note = _omit_note(omitted, "개 이정표는 원문 참조")
    if foot or note:
        data["footnote"] = {"pre": _clip(" · ".join(x for x in (foot, note) if x), 30)}
    return data


_BUILDERS = {
    "opening": lambda norm, frags, idx, plan: _build_opening(norm, frags),
    "problem": _build_problem,
    "concept": _build_concept,
    "process": _build_process,
    "differentiator": _build_differentiator,
    "proof": _build_proof,
    "closing": _build_closing,
    "compare": _build_compare,
    "dataviz": _build_dataviz,
    "timeline": _build_timeline,
}

# 구조 payload 와 **정확 대응**하는 템플릿 (§3). structured_templates=True 일 때
# 역할 1순위가 정확 대응을 갖지 않으면 이 조건을 만족하는 대체 템플릿이 자리를 가져간다.
_EXACT_MATCH = {
    "process": lambda c: c["flow"] is not None,
    "concept": lambda c: c["graph"] is not None,
    "timeline": lambda c: c["timeline"] is not None,
    "compare": lambda c: c["compare_table"] is not None,
    "dataviz": lambda c: c["series"] is not None,
}


def _pick_module(spec: FormatSpec, role: str, cand: dict, structured_templates: bool) -> str:
    """역할 → 템플릿 모듈 id. 기본은 풀 1순위(기존 동작 그대로)."""
    ids = spec.template_pool[role]
    if structured_templates and not _EXACT_MATCH.get(tpl_short(ids[0]), lambda _c: False)(cand):
        for tid in ids[1:]:
            if _EXACT_MATCH.get(tpl_short(tid), lambda _c: False)(cand):
                return tid
    return ids[0]


# ── 공개 API (모듈 간 계약) ─────────────────────────────────────────────


def _stretch_to_target(nats: list[float], target: float) -> list[float]:
    """자연 길이 목록을 포맷의 duration.target 에 맞게 균일 스케일한다.

    배율이 1 이면 원본을 그대로 돌려준다 — 기존(wide-16x9, Σnat=target) 결과를 바이트 단위로 보존.
    반올림 잔차는 마지막 씬이 흡수한다.
    """
    total = sum(nats)
    if total <= 0 or abs(total - target) < 1e-9:
        return list(nats)
    scaled = [round(n * target / total, 2) for n in nats[:-1]]
    scaled.append(round(target - sum(scaled), 2))
    return scaled


def assemble_demo_scenario(
    norm: dict,
    fragments: list[dict],
    format: str = DEFAULT_FORMAT_ID,
    *,
    structured_templates: bool = False,
) -> ScenarioDoc:
    """규칙 기반(LLM 무호출) 데모 시나리오 조립.

    ai_summary(없으면 제목)를 core_message 로, 조각을 포맷 skeleton 의 역할별 템플릿에
    휴리스틱 배치한다. 씬 길이는 템플릿 nat_default 를 포맷 duration.target 에 맞춰 균일
    스케일하고, 각 씬 data 는 템플릿 schema.json 의 maxLength 에 맞게 절단하며,
    narration 은 x-read 필드를 포맷 narration.rate 예산 안에서 문장으로 연결한다.

    빌더는 `fragment["structured"]` 를 먼저 소비하고(§3 매핑), 없으면 기존 텍스트 경로로
    폴백한다. 슬롯 용량을 넘치면 그룹 요약·대표 선별로 압축하고 생략 건수를 화면에 밝힌다.

    structured_templates=True 면 역할의 1순위 템플릿이 구조 payload 와 정확 대응하지
    않을 때 같은 역할 풀의 대체 템플릿(tpl.compare · tpl.dataviz · tpl.timeline)이
    자리를 가져간다. 기본값 False 는 기존 7종 골격을 그대로 유지한다 — 씬 구성이 바뀌면
    이미 만들어진 시나리오·빌드 산출물과 어긋나므로 명시적 선택으로만 켠다.
    """
    modules_root = resolve_modules_root()
    spec = load_format(format, modules_root=modules_root)
    cand = _candidates(fragments)

    # 1) 역할 → 템플릿 → 모듈/스키마 해석. 조립 휴리스틱이 없는 역할은 즉시 거절한다.
    picks: list[tuple[dict, dict, str]] = []  # (module.yaml, schema.json, 템플릿 짧은 이름)
    for role in spec.skeleton:
        module_id = _pick_module(spec, role, cand, structured_templates)
        short = tpl_short(module_id)
        if short not in _BUILDERS:
            raise NotImplementedError(
                f"포맷 {spec.id!r} 역할 {role!r}(템플릿 {module_id!r})의 규칙 기반 조립 규칙이 없다 — "
                f"현재 데모 조립이 지원하는 템플릿은 {sorted(_BUILDERS)} 다"
            )
        picks.append((_load_module(module_id, modules_root),
                      _load_schema(module_id, modules_root), short))
    plan = _assign(cand, {short for _, _, short in picks})

    durs = _stretch_to_target(
        [float(m.get("nat_default", 10)) for m, _, _ in picks], spec.duration.target
    )

    content: dict[str, dict] = {}
    scenes: list[dict] = []
    used_names: set[str] = set()
    for idx, (role, (module, schema, short), dur) in enumerate(zip(spec.skeleton, picks, durs), 1):
        data = _conform(_BUILDERS[short](norm, fragments, idx, plan), schema)
        # content/씬 이름 키는 **역할**이다 — 한 템플릿을 두 역할이 쓰는 포맷(예: short-9x16 의
        # problem/solution → vtpl.stack)에서 데이터가 서로를 덮어쓰지 않게 한다.
        content[role] = data
        name = module.get("scene_name_default", role)
        if name in used_names:
            name = role if role not in used_names else f"{name}-{idx}"
        used_names.add(name)
        nat = float(module.get("nat_default", 10))
        major = str(module.get("version", "1.0.0")).split(".")[0]
        narration = (
            narration_from_x_read(data, schema, dur=dur, rate=spec.narration.rate)
            if spec.narration.enabled else ""
        )
        scenes.append(
            {
                "name": name,
                "dur": dur,
                "nat": nat,
                "tpl": f"{short}@{major}",
                # 등장 완료 후·퇴장 전 안정 화면 — dur-1.0s (진행률 방식(0.9×dur)은 긴 씬에서
                # 마지막 요소 페이드 도중을 캡처했다: QA 게이트 3 실측). 하한은 dur 절반.
                "stills": [round(max(dur - 1.0, dur * 0.5), 2)],
                "data_ref": f"content.{role}",
                "narration": narration,
                "transition": "cut",
            }
        )
    core_message = norm.get("ai_summary") or norm["title"]
    return ScenarioDoc.model_validate(
        {
            "version": "1.0",
            "format": spec.id,
            "meta": {
                "core_message": core_message,
                "audience": "사내 청중",
                "duration_sec": sum(s["dur"] for s in scenes),
                "tone": "정보 전달",
                "meeting_id": None,
                "source_report_id": None,
            },
            "content": content,
            "scenes": scenes,
            "tokens_theme": "hwax-blue",
            "playback": {"mode": "times", "count": 1},
        }
    )


def _fit_record(frag: dict, payload: dict, cand: dict, shorts: set[str]) -> dict:
    """구조 payload 하나의 슬롯 수용 판정 — slot_fit_report 의 행 1건.

    반환의 fit 5단계.
      ok         — 항목 수·라벨 모두 슬롯에 그대로 들어간다
      trim       — 개수는 맞고 라벨만 maxLength 초과 → 어절 경계 축약
      summarized — 그룹 요약 또는 대표 선별로 압축해 실었다 (생략 건수 화면 명시)
      split      — 한 슬롯 용량의 2배를 넘는다 → 씬 분할 권고 (요약본만 실린다)
      none       — 받을 슬롯 자체가 카탈로그에 없다
    """
    kind = payload.get("kind")
    slot = capacity = label_max = None
    labels: list[str] = []
    items = carried = 0
    strategy = reason = ""

    def cap_of(short: str, prop: str, label_key: str | None) -> None:
        nonlocal slot, capacity, label_max
        slot = f"{short}.{prop}"
        capacity, label_max = _slot_cap(short, prop, label_key)

    if kind == "graph":
        nodes = payload.get("nodes") or []
        labels = [str(n.get("label", "")) for n in nodes]
        items = len(nodes)
        if payload.get("shape") == "flow" and "process" in shorts:
            cap_of("process", "steps", "name")
            carried = len(_span_indices(items, capacity))
            strategy, reason = "span", "흐름도 → process.steps (순서 표본)"
        elif payload.get("shape") in ("tree", "network") and "concept" in shorts:
            cap_of("concept", "nodes", "name")
            carried = len(_level_indices(nodes, capacity))
            strategy, reason = "level", "tree/network → concept.nodes (얕은 레벨 우선, 엣지 손실)"
        else:
            reason = f"{payload.get('shape')} 를 받을 슬롯이 이번 조립 템플릿에 없다"

    elif kind == "timeline":
        ms = payload.get("milestones") or []
        labels, items = [str(m.get("label", "")) for m in ms], len(ms)
        if "timeline" in shorts:
            cap_of("timeline", "milestones", "name")
            carried = len(_span_indices(items, capacity))
            strategy, reason = "span", "milestone → timeline.milestones"
        else:
            reason = "tpl.timeline 이 이번 조립에 뽑히지 않았다 (structured_templates=False)"

    elif kind == "series":
        entries = payload.get("series") or []
        labels, items = [str(e.get("label", "")) for e in entries], len(entries)
        if not _single_series(payload):
            reason = "다계열(group)·분포형(values) — 단일 계열 막대로 환원 불가 (§9 #4)"
        elif "dataviz" in shorts:
            cap_of("dataviz", "bars", "label")
            carried = len(_extreme_indices([e.get("value") for e in entries], capacity))
            strategy, reason = "extreme", "단일 계열 → dataviz.bars (값 극단+중앙값)"
        elif "closing" in shorts:
            cap_of("closing", "stats", "d")
            carried = len(_extreme_indices([e.get("value") for e in entries], capacity))
            strategy, reason = "extreme", "단일 계열 → closing.stats (값 극단+중앙값)"
        else:
            reason = "수치 슬롯이 이번 조립 템플릿에 없다"

    elif kind == "table":
        rows, cols = payload.get("rows") or [], payload.get("columns") or []
        key0 = cols[0]["key"] if cols else ""
        labels, items = [str(r.get(key0, "")) for r in rows], len(rows)
        if cand.get("compare_table") is not None and payload is cand["compare_table"][1]:
            if "compare" in shorts:
                cap_of("compare", "rows", "aspect")
            elif "differentiator" in shorts:
                cap_of("differentiator", "flow", "label")
            if slot:
                carried = len(_span_indices(items, capacity))
                strategy, reason = "span", f"2안 비교 → {slot} (첫·끝 표본)"
            else:
                reason = "2안 비교 슬롯이 없다"
        elif _group_rows(payload) and "proof" in shorts:
            groups = _group_rows(payload)
            cap_of("proof", "cases", "title")
            capacity, labels = len(groups), [g[0] for g in groups]
            carried = sum(n for _, n in groups)   # 그룹 집계는 전 행을 대표한다
            strategy = "group"
            reason = f"카테고리 열 그룹 요약 {len(groups)}군 → proof.cases 1칸 (개별 행 손실)"
        else:
            reason = f"{len(cols)}열 격자 — 격자 표 씬이 카탈로그에 없다 (§9 #1)"

    elif kind == "pairs":
        pairs = payload.get("pairs") or []
        labels, items = [str(p.get("label", "")) for p in pairs], len(pairs)
        if cand.get("pairs") and "proof" in shorts:
            cap_of("proof", "cases", "title")
            carried = _pairs_line(pairs, 70)[1]
            capacity = carried or 1        # 카드 1장이 담는 쌍 수는 desc 70자에 종속
            strategy, reason = "text", "키값 → proof.cases 근거 카드 (desc 70자만큼)"
        elif "closing" in shorts:
            cap_of("closing", "stats", "d")
            carried = len(_span_indices(items, capacity))
            strategy, reason = "span", "키값 → closing.stats"
        else:
            reason = "스펙 목록 슬롯이 없다 (§9 #3)"

    elif kind == "media":
        reason = "이미지/영상 슬롯이 카탈로그에 하나도 없다 (§9 #2)"
    else:
        reason = f"미지 kind={kind}"

    trimmed = [x for x in labels if label_max and len(x) > label_max]
    if slot is None:
        fit = "none"
    elif strategy == "group":
        fit = "summarized"
    elif carried >= items:
        fit = "trim" if trimmed else "ok"
    elif items > 2 * max(carried, 1):
        fit = "split"
    else:
        fit = "summarized"

    rec = {
        "frag_id": frag.get("frag_id"),
        "widget": frag.get("widget"),
        "kind": kind,
        "shape": payload.get("shape"),
        "slot": slot,
        "capacity": capacity,
        "items": items,
        "carried": carried,
        "omitted": max(items - carried, 0),
        "labels_over_limit": len(trimmed),
        "label_max": label_max,
        "strategy": strategy,
        "fit": fit,
        "reason": reason,
    }
    if fit == "split":
        n = -(-items // max(carried, 1))
        rec["split_hint"] = {
            "scenes": n,
            "detail": f"{slot} 은 {carried}칸 — {items}항목을 온전히 보이려면 씬 {n}개로 나눠라",
        }
    return rec


def slot_fit_report(
    norm: dict,
    fragments: list[dict],
    *,
    format: str = DEFAULT_FORMAT_ID,
    structured_templates: bool = False,
) -> dict:
    """어떤 위젯이 어느 씬 슬롯에 ok/trim/summarized/split/none 으로 들어갔는지 보고한다.

    §8 재실측의 입력. 판정(fit)은 '이 payload 를 대상 슬롯이 담을 수 있는가'이고,
    placed 는 '이번 조립 문서에 실제로 들어갔는가'다 — 같은 종류가 여럿이면 슬롯 하나를
    두고 경쟁하므로 두 수치는 다르다(예: 흐름도 3건 중 process.steps 에 실리는 건 1건).
    """
    spec = load_format(format, modules_root=resolve_modules_root())
    cand = _candidates(fragments)
    shorts = {tpl_short(_pick_module(spec, role, cand, structured_templates))
              for role in spec.skeleton}
    plan = _assign(cand, shorts)
    owner = plan["owner"]

    rows = [_fit_record(f, p, cand, shorts) for f, p in _structured(fragments)]
    for r in rows:
        r["placed"] = r["frag_id"] in owner
        r["placed_slot"] = owner.get(r["frag_id"])

    tally = {k: 0 for k in ("ok", "trim", "summarized", "split", "none")}
    for r in rows:
        tally[r["fit"]] += 1
    total = len(rows)
    reached = total - tally["none"]
    return {
        "format": spec.id,
        "structured_templates": structured_templates,
        "templates": sorted(shorts),
        "structured_blocks": total,
        "tally": tally,
        "reach_pct": round(100 * reached / total, 1) if total else 0.0,
        "placed_pct": round(100 * sum(1 for r in rows if r["placed"]) / total, 1) if total else 0.0,
        "strict_reach_pct": (                      # §8 기존 기준(ok+trim 만) — 비교용
            round(100 * (tally["ok"] + tally["trim"]) / total, 1) if total else 0.0
        ),
        "split_hints": [r["split_hint"] | {"frag_id": r["frag_id"], "widget": r["widget"]}
                        for r in rows if "split_hint" in r],
        "rows": rows,
    }


def validate_scenario(
    doc: ScenarioDoc,
    modules_root: Path | None = None,
    formats_root: Path | None = None,
) -> list[str]:
    """ScenarioDoc 확장 검증 — 오류 문자열 목록을 반환한다 (빈 리스트 = 통과).

    검사: 포맷 스펙 로드·총 러닝타임 허용대·씬 tpl 이 포맷 template_pool 소속인지,
    OM_SCENES 16KB 예산, 씬 이름 중복(children 맵 키 충돌), tpl 레지스트리
    존재·status≠deprecated·메이저 버전 일치, data_ref 실경로, 템플릿 데이터 스키마.
    """
    modules_root = Path(modules_root) if modules_root is not None else resolve_modules_root()
    errors: list[str] = []

    spec: FormatSpec | None = None
    try:
        spec = load_format(doc.format, formats_root=formats_root, modules_root=modules_root)
    except FormatError as e:
        errors.append(f"포맷 {doc.format!r} 로드 실패 — {e}")

    if spec is not None:
        total = round(sum(s.dur for s in doc.scenes), 3)
        if not (spec.duration.min <= total <= spec.duration.max):
            errors.append(
                f"총 러닝타임 {total}s 가 포맷 {spec.id} 허용대 "
                f"{spec.duration.min}~{spec.duration.max}s 를 벗어났다 — 씬 dur 를 조정하라"
            )

    try:
        check_om_scenes_budget(doc)
    except ValueError as e:
        errors.append(str(e))

    names = [s.name for s in doc.scenes]
    for name in sorted({n for n in names if names.count(n) > 1}):
        errors.append(f"씬 이름 중복: {name!r} — children 맵 키가 충돌한다")

    doc_dump = doc.model_dump()
    for s in doc.scenes:
        m = _TPL_REF_RE.match(s.tpl)
        if not m:
            errors.append(f"씬 {s.name!r}: tpl 참조 형식 오류 {s.tpl!r} (기대: 'name@major')")
            continue
        major = m.group(2)
        if spec is not None and not spec.allows_tpl(s.tpl):
            errors.append(
                f"씬 {s.name!r}: 템플릿 {s.tpl!r} 가 포맷 {spec.id} 의 template_pool 에 없다 — "
                f"허용 템플릿은 {spec.tpl_ids()} 다"
            )
        module_id = resolve_tpl_module_id(s.tpl, spec=spec, modules_root=modules_root)
        module_path = module_dir(module_id, modules_root) / "module.yaml"
        if not module_path.is_file():
            errors.append(f"씬 {s.name!r}: 레지스트리에 없는 템플릿 {s.tpl!r} ({module_path})")
            continue
        try:
            module = yaml.safe_load(module_path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001 — 검증기는 수집만 한다
            errors.append(f"씬 {s.name!r}: module.yaml 로드 실패 ({e})")
            continue
        status = str(module.get("status", ""))
        if status == "deprecated":
            errors.append(f"씬 {s.name!r}: 템플릿 {s.tpl!r} 는 deprecated 상태")
        mod_major = str(module.get("version", "0")).split(".")[0]
        if mod_major != major:
            errors.append(
                f"씬 {s.name!r}: tpl 메이저 {major} ≠ 레지스트리 버전 {module.get('version')}"
            )

        # data_ref 실경로 해석
        if not s.data_ref:
            errors.append(f"씬 {s.name!r}: data_ref 가 비어 있다")
            continue
        node: Any = doc_dump
        ok = True
        for seg in s.data_ref.split("."):
            if isinstance(node, dict) and seg in node:
                node = node[seg]
            else:
                errors.append(f"씬 {s.name!r}: data_ref {s.data_ref!r} 경로가 문서에 없다")
                ok = False
                break
        if not ok:
            continue
        if not isinstance(node, dict):
            errors.append(f"씬 {s.name!r}: data_ref {s.data_ref!r} 가 객체가 아니다")
            continue

        # 템플릿 데이터 스키마 검증
        try:
            schema = _load_schema(module_id, modules_root)
        except Exception as e:  # noqa: BLE001
            errors.append(f"씬 {s.name!r}: schema.json 로드 실패 ({e})")
            continue
        validator = Draft202012Validator(schema)
        for err in sorted(validator.iter_errors(node), key=lambda e: list(e.absolute_path)):
            loc = "/".join(str(p) for p in err.absolute_path) or "(루트)"
            errors.append(f"씬 {s.name!r}: 데이터 스키마 위반 [{loc}] {err.message}")

    return errors
