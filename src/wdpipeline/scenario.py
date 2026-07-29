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
    "DOC_TEMPLATE_SHORTS",
    "TEMPLATE_ORDER",
    "assemble_demo_scenario",
    "assemble_doc_scenario",
    "is_doc_format",
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
    받지 않는다 — 다계열은 tpl.d-multi 가 받는다(§9 #4 해소, 분포형은 §9 #7 잔존).
    """
    entries = payload.get("series") or []
    if len(entries) < 2 or any(e.get("group") for e in entries):
        return False
    return all(e.get("value") is not None for e in entries)


def _multi_grid(payload: dict) -> tuple[list[str], list[str], dict] | None:
    """다계열 series payload → (계열 이름들, 공통 항목들, 값맵). d-multi 부적격이면 None.

    d-multi 는 그룹 막대라 모든 계열이 같은 항목 축을 공유해야 한다 — 값이 빠진 항목을
    0 으로 지어내지 않고 **모든 계열에 값이 있는 항목만** 공통 축으로 남긴다.
    음수는 스키마(0 기준선)가 금지하므로 하나라도 있으면 부적격.
    """
    entries = [e for e in payload.get("series") or [] if e.get("group")]
    if not entries:
        return None
    groups: list[str] = []
    cats: list[str] = []
    val: dict[tuple[str, str], float] = {}
    for e in entries:
        g, lb, v = str(e["group"]), str(e.get("label") or ""), e.get("value")
        if not lb or v is None:
            continue
        if float(v) < 0:
            return None                      # 음수 — 0 기준선 스키마로 못 싣는다
        if g not in groups:
            groups.append(g)
        if lb not in cats:
            cats.append(lb)
        val.setdefault((g, lb), float(v))
    common = [c for c in cats if all((g, c) in val for g in groups)]
    if len(groups) < 2 or len(common) < 3:
        return None                          # 계열 2·항목 3 미만 — d-multi 스키마 하한
    return groups, common, val


# ── 발표 레이아웃(l-*) 후보 판정 — 배치 다양성 라운드 ─────────────────────
#
# 신규 8종은 새 데이터 종류를 요구하지 않는다. 이미 있는 구조 payload 가 **더 정확히
# 들어맞는 그릇**을 찾는 일이다 — 위계는 트리로, 다지표는 계기판으로, 표+수치는 혼합판
# 으로. 그래서 판정은 전부 "이 payload 가 저 슬롯의 하한을 채우는가"만 본다.
# 상한/하한은 코드 상수가 아니라 schema.json 이 정본이다(_cap/_floor/_lim).


def _kpi_metrics(payload: dict) -> list[dict] | None:
    """l-kpi.metrics 후보 — 값 있는 단일 계열 4개 이상 (closing.stats 3칸이 못 담는 다지표).

    좌표 계열(x 동반)은 제외한다 — 산점도의 y 는 지표가 아니라 위치다. 계기판에 올리면
    "자동 리포트 90" 처럼 축 하나를 지운 수치가 된다(그 payload 는 l-quad 소관).
    """
    if not _single_series(payload) or _quad_points(payload):
        return None
    entries = [e for e in payload.get("series") or [] if e.get("value") is not None]
    return entries if len(entries) >= _floor("l-kpi", "metrics", default=4) else None


def _quad_points(payload: dict) -> list[dict] | None:
    """l-quad.items 후보 — 가로(x)와 세로(value)를 둘 다 가진 좌표 항목 4개 이상.

    x 를 싣는 위젯은 quadrant·scatter·matrix 뿐이다(widgets._x_quadrant/_x_scatter).
    """
    pts = [
        e for e in payload.get("series") or []
        if isinstance(e.get("x"), (int, float)) and isinstance(e.get("value"), (int, float))
    ]
    return pts if len(pts) >= _floor("l-quad", "items", default=4) else None


def _tree_levels(payload: dict) -> tuple[list[dict], list[dict], list[dict]] | None:
    """graph(tree) → (루트, 중간, 리프). 루트 1개·중간 2개 이상이 아니면 l-tree 부적격.

    루트가 여럿인 숲이나 중간층 없는 2단은 이 템플릿의 그림(루트→버스→가지)이 성립하지
    않는다 — 억지로 담지 않고 기존 concept 방사형에 맡긴다.
    """
    nodes = payload.get("nodes") or []
    roots = [n for n in nodes if int(n.get("level") or 0) == 0]
    mids = [n for n in nodes if int(n.get("level") or 0) == 1]
    leaves = [n for n in nodes if int(n.get("level") or 0) == 2]
    if len(roots) != 1 or len(mids) < 2:
        return None
    return roots, mids, leaves


def _mix_table(payload: dict) -> tuple[list[dict], list[dict]] | None:
    """l-mix.table 후보 → (쓸 열, 행). 셀이 6자 상한이라 **짧은 값 열만** 데이터 열로 쓴다.

    문장 표를 넣으면 전 셀이 잘려 표가 거짓이 되므로, 셀 자수 상한을 그대로 통과하는
    열이 2개 이상일 때만 후보다(수치·코드값 표 — 진척률·RACI 류).
    """
    cols, rows = payload.get("columns") or [], payload.get("rows") or []
    if not cols or len(rows) < _floor("l-mix", "table", "rows", default=3):
        return None
    v_max = _lim("l-mix", "table", "rows", "[]", "cells", "[]", "v", default=6)
    cell_cap = _cap("l-mix", "table", "rows", "[]", "cells", default=3)
    cell_min = _floor("l-mix", "table", "rows", "[]", "cells", default=2)
    short = [
        c for c in cols[1:]
        if all(0 < len(str(r.get(c["key"], "") or "").strip()) <= v_max for r in rows)
    ]
    if len(short) < cell_min:
        return None
    return [cols[0], *short[:cell_cap]], rows


def _split_table(payload: dict) -> bool:
    """l-split.visual.table 후보 — 2열 이상·3행 이상이면 간이표로 요약해 실을 수 있다."""
    return (
        len(payload.get("columns") or []) >= _floor("l-split", "visual", "table", "columns",
                                                    default=2)
        and len(payload.get("rows") or []) >= _floor("l-split", "visual", "table", "rows",
                                                     default=3)
    )


# ── 커버리지 1순위 4종 판별 (tpl.c-ratio·c-trend·c-branch·c-grid) ─────────
#
# 어떤 신호로 무엇을 가르는가 — 같은 kind 안에서 그릇이 갈리므로 판별 규칙이 곧 계약이다.
#
#   series → c-ratio  : ① chart_type 이 비율 계열(pie·doughnut·waffle·treemap·packing)
#                        — 원천 위젯이 이미 '전체를 나눠 갖는 값'이다. 또는
#                       ② 값의 합이 100 근사(±0.5) — 백분율로 적힌 단일 계열.
#   series → c-trend  : ① chart_type 이 line·area, 또는 ② 항목 라벨의 2/3 이상이 시점
#                        표기(25.12 · 2026-01 · 3월 · 4주 · Q1 · 2026)다.
#   비율 vs 시계열     : **비율을 먼저 본다.** 파이·도넛에는 시점 축이 없고, 반대로 월별
#                       실적의 합이 우연히 100 이 되는 경우는 ②의 시점 라벨 신호가 잡아
#                       c-trend 로 되돌린다(_trend_series 가 비율 적격을 먼저 배제한다).
#                       두 신호가 동시에 서는 유일한 경우는 '월별 구성비(%)'인데, 이때는
#                       시점 축이 있으므로 추세가 맞다 — 그래서 비율 판정에서 시점 라벨을
#                       추가로 배제한다.
#   graph  → c-branch : 엣지 라벨이 있거나(판정 코드값) 한 노드에서 자식이 2개 이상 —
#                       tpl.process(선형 6단계)로는 갈림을 못 그린다. 레벨 4단 초과는
#                       부적격(축소·폰트 감소 금지 계약).
#   table/pairs → c-grid : 키값 6쌍 이상, 또는 2열 표 6행 이상. 3열 이상 표는 격자
#                       (d-matrix)가 정본이라 건드리지 않는다 — 2열 표는 d-matrix 하한
#                       (3열) 미달로 지금까지 미수용이던 몫이다.
#
# 네 그릇 모두 **포맷 template_pool 에 선언된 역할에서만** 발동한다(d-* 와 같은 옵트인
# 경계). 현행 formats/wide-16x9/format.yaml 풀에는 없어 기본 경로 동작은 불변이다.

_RATIO_CHART_TYPES = frozenset({"pie", "doughnut", "waffle", "treemap", "packing"})
_TREND_CHART_TYPES = frozenset({"line", "area"})

# 시점 라벨 — 25.12 · 2026-01-05 · 3월 · 4주 · 1분기 · Q1 · 2026
_TIME_LABEL_RE = re.compile(
    r"^\s*(?:"
    r"\d{2,4}[.\-/]\d{1,2}(?:[.\-/]\d{1,2})?"
    r"|\d{1,4}\s*(?:년|월|일|주|주차|분기|회차)"
    r"|[QqHh]\d"
    r"|\d{4}"
    r")\s*$"
)


def _time_axis(labels: list[str], chart_type: str) -> bool:
    """항목 라벨이 시점 축인가 — chart_type 선언이 없으면 라벨 2/3 이상이 시점 표기여야 한다."""
    if chart_type in _TREND_CHART_TYPES:
        return True
    hits = sum(1 for x in labels if _TIME_LABEL_RE.match(x))
    return len(labels) >= 4 and hits * 3 >= len(labels) * 2


def _ratio_series(payload: dict) -> list[dict] | None:
    """series payload → 비율·구성비 항목 4개 이상. 부적격이면 None.

    다계열(group)·분포형(values)·음수·0 합계는 조각 하나로 환원할 수 없어 제외한다.
    시점 축 라벨이면 구성비가 아니라 추세다(월별 구성비는 c-trend 가 맞다).
    """
    entries = payload.get("series") or []
    if not entries or any(e.get("group") or e.get("values") is not None for e in entries):
        return None
    items: list[dict] = []
    for e in entries:
        label, v = str(e.get("label") or "").strip(), e.get("value")
        if not label or v is None or float(v) < 0:
            return None
        items.append({"label": label, "value": float(v)})
    if len(items) < 4:                       # c-ratio 스키마 minItems 4
        return None
    labels = [x["label"] for x in items]
    ctype = str(payload.get("chart_type") or "")
    if _time_axis(labels, ctype):
        return None
    total = sum(x["value"] for x in items)
    if total <= 0:
        return None
    return items if (ctype in _RATIO_CHART_TYPES or abs(total - 100.0) <= 0.5) else None


def _trend_series(payload: dict) -> tuple[list[str], list[str], dict] | None:
    """series payload → (계열 이름들, 시점 라벨들, 값맵). 부적격이면 None.

    d-multi 의 `_multi_grid` 와 같은 '공통 축만' 규칙을 쓴다 — 빠진 값을 0 으로 지어내지
    않는다. 단일 계열도 받는다(계열 이름은 빈 문자열).
    """
    if _ratio_series(payload) is not None:
        return None                          # 비율이 먼저다
    entries = payload.get("series") or []
    if not entries or any(e.get("values") is not None for e in entries):
        return None                          # 분포형은 궤적이 아니다
    lines: list[str] = []
    points: list[str] = []
    val: dict[tuple[str, str], float] = {}
    for e in entries:
        label, v = str(e.get("label") or "").strip(), e.get("value")
        if not label or v is None or float(v) < 0:
            return None                      # c-trend values minimum 0
        group = str(e.get("group") or "")
        if group not in lines:
            lines.append(group)
        if label not in points:
            points.append(label)
        val.setdefault((group, label), float(v))
    if not (1 <= len(lines) <= 3):            # c-trend lines 1~3
        return None
    common = [p for p in points if all((g, p) in val for g in lines)]
    if len(common) < 4:                       # c-trend points minItems 4
        return None
    if not _time_axis(common, str(payload.get("chart_type") or "")):
        return None
    return lines, common, val


def _branch_graph(payload: dict) -> tuple[list[dict], list[dict]] | None:
    """graph payload → (노드, 엣지) 분기 흐름도용. 분기 신호가 없거나 5레벨이면 None.

    ① 레벨을 0..3 으로 압축(구간이 5개 이상이면 부적격 — 축소·폰트 감소 금지 계약)
    ② 레벨당 3개까지만 남긴다(2026-07-29 심의 tpl.c-branch F2 — 스키마가 레벨당 상한을
       강제하지 않아 과밀 시 노드 상자가 24px 글리프보다 작아진다. 조립기가 막는다)
    ③ 전진 엣지만 남기고, 남은 그래프에 판단 노드(자식 2개 이상)가 없으면 부적격
    """
    nodes = [n for n in (payload.get("nodes") or []) if str(n.get("id") or "")]
    edges = [e for e in (payload.get("edges") or [])
             if str(e.get("from") or "") and str(e.get("to") or "")]
    if len(nodes) < 3 or len(edges) < 2:
        return None
    lv_of = {str(n["id"]): int(n.get("level") or 0) for n in nodes}
    steps = sorted({lv_of[str(n["id"])] for n in nodes})
    if len(steps) > 4:
        return None                          # c-branch level 0~3
    rank = {v: i for i, v in enumerate(steps)}

    out_deg: dict[str, int] = {}
    for e in edges:
        src, dst = str(e["from"]), str(e["to"])
        if src in lv_of and dst in lv_of and rank[lv_of[dst]] > rank[lv_of[src]]:
            out_deg[src] = out_deg.get(src, 0) + 1
    branching = any(v >= 2 for v in out_deg.values()) or any(_s_label(e) for e in edges)
    if not branching:
        return None                          # 선형 절차는 tpl.process 로

    kept: list[dict] = []
    for step in steps:
        same = [(i, n) for i, n in enumerate(nodes) if lv_of[str(n["id"])] == step]
        # 판단 노드를 우선 남긴다 — 판단이 빠지면 분기 흐름도가 아니게 된다
        same.sort(key=lambda x: (0 if out_deg.get(str(x[1]["id"]), 0) >= 2 else 1, x[0]))
        for i, n in sorted(same[:3], key=lambda x: x[0]):
            kept.append({**n, "level": rank[step]})
    kept = kept[:12]                          # c-branch nodes maxItems 12
    ids = {str(n["id"]) for n in kept}
    fwd = [e for e in edges
           if str(e["from"]) in ids and str(e["to"]) in ids
           and int(next(n["level"] for n in kept if str(n["id"]) == str(e["to"])))
           > int(next(n["level"] for n in kept if str(n["id"]) == str(e["from"])))]
    fwd = fwd[:14]                            # c-branch edges maxItems 14
    deg: dict[str, int] = {}
    for e in fwd:
        deg[str(e["from"])] = deg.get(str(e["from"]), 0) + 1
    if len(kept) < 3 or len(fwd) < 2 or not any(v >= 2 for v in deg.values()):
        return None
    return kept, fwd


def _s_label(edge: dict) -> str:
    return str(edge.get("label") or "").strip()


def _grid_cards(payload: dict) -> list[dict] | None:
    """pairs(6쌍 이상) 또는 2열 표(6행 이상) → 카드 원자료. 부적격이면 None.

    3열 이상 표는 tpl.d-matrix 가 정본이라 건드리지 않는다 — 겹치는 슬롯을 만들지 않는다.
    """
    kind = payload.get("kind")
    if kind == "pairs":
        pairs = payload.get("pairs") or []
        if len(pairs) < 6:
            return None
        return [{"label": str(p.get("label") or p.get("key") or ""),
                 "desc": str(p.get("value") or "")} for p in pairs
                if str(p.get("label") or p.get("key") or "")]
    if kind == "table":
        cols, rows = payload.get("columns") or [], payload.get("rows") or []
        if len(cols) > 2 or len(cols) < 1 or len(rows) < 6:
            return None
        k0 = cols[0]["key"]
        k1 = cols[1]["key"] if len(cols) > 1 else None
        return [{"label": str(r.get(k0) or ""),
                 "desc": str(r.get(k1) or "") if k1 else ""} for r in rows
                if str(r.get(k0) or "")]
    return None


def _media_records(norm: dict | None) -> list[dict]:
    """d-media 후보 — 해결된 이미지 자산만 (file_id 중복 제거, 등장 순서 유지).

    미디어군은 텍스트 조각을 만들지 않으므로(fragmentize 정책) 후보의 원천은
    fragments 가 아니라 norm 의 collect_media 채널이다. 미해결·비이미지 자산은
    화면에 실을 파일이 없어 제외한다(collect_media 가 사유와 함께 계상한다).
    """
    if not norm:
        return []
    from .widgets import collect_media

    out: list[dict] = []
    seen: set[str] = set()
    for m in collect_media(norm):
        asset = m.get("asset") or {}
        if asset.get("status") != "resolved" or asset.get("media_type") != "image":
            continue
        if m["file_id"] in seen:
            continue
        seen.add(m["file_id"])
        out.append(m)
    return out


def _candidates(fragments: list[dict], norm: dict | None = None) -> dict:
    """구조 payload → 슬롯 후보 색인 (조립기와 slot_fit_report 의 공용 1차 정본).

    같은 종류가 여럿이면 정보량이 가장 많은 것(흐름도=노드 수, 표=행 수)을 대표로 뽑고
    동수면 먼저 등장한 것을 남긴다 — 기존 `_flow_items` 의 선택 규칙과 같다.

    d-* 후보 3종(§9 #1·#2·#4 해소분).
      matrix_table — **달리 갈 곳 없는 격자**(비교 표도 그룹 요약도 못 되는 3열 이상 표)
                     중 셀 수 최대. 다른 표는 기존 경로(compare/proof)가 우선이다.
      multi        — 다계열 공통 축 격자로 정리되는 series (음수·축 불일치는 부적격)
      media        — 해결된 이미지 자산 (원천은 fragments 가 아니라 norm — _media_records)
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
    homeless = [x for x in rest
                if x not in grouped
                and len(x[1].get("columns") or []) >= 3
                and len(x[1].get("rows") or []) >= 2]

    # l-* 후보 — 기존 후보를 뺏지 않는다. 소유권은 _assign 이 shorts 를 보고 정한다.
    least = [x for x in tables if _split_table(x[1])]
    least.sort(key=lambda x: len(x[1].get("columns") or []) * len(x[1].get("rows") or []))

    series_all = _structured(fragments, kind="series")
    graph_all = _structured(fragments, kind="graph")
    grid_all = [x for x in _structured(fragments) if _grid_cards(x[1])]

    return {
        "flow": most(_structured(fragments, kind="graph", shape="flow"),
                     lambda p: len(p.get("nodes") or [])),
        "graph": most([x for x in _structured(fragments, kind="graph")
                       if x[1].get("shape") in ("tree", "network")],
                      lambda p: len(p.get("nodes") or [])),
        "tree": most([x for x in _structured(fragments, kind="graph", shape="tree")
                      if _tree_levels(x[1]) is not None],
                     lambda p: len(p.get("nodes") or [])),
        "kpi": next((x for x in _structured(fragments, kind="series")
                     if _kpi_metrics(x[1])), None),
        "quadrant": next((x for x in _structured(fragments, kind="series")
                          if _quad_points(x[1])), None),
        "mix_table": most([x for x in tables if _mix_table(x[1])],
                          lambda p: len(p.get("columns") or []) * len(p.get("rows") or [])),
        # 간이표는 **가장 작은 표**가 제자리다 — 큰 격자는 d-matrix/l-mix 가 통째로 받는다
        "split_tables": least,
        "list_pairs": next((x for x in _structured(fragments, kind="pairs")
                            if len(x[1].get("pairs") or []) >= _floor("l-list", "rows",
                                                                      default=5)), None),
        "timeline": next((x for x in _structured(fragments, kind="timeline")
                          if len(x[1].get("milestones") or []) >= 3), None),
        "series": next((x for x in _structured(fragments, kind="series")
                        if _single_series(x[1])), None),
        "pairs": _structured(fragments, kind="pairs"),
        "compare_table": compare_table,
        "summary_tables": sorted(grouped, key=lambda x: -len(x[1].get("rows") or [])),
        "matrix_table": most(homeless, lambda p: len(p.get("columns") or [])
                             * len(p.get("rows") or [])),
        "multi": next((x for x in _structured(fragments, kind="series")
                       if _multi_grid(x[1]) is not None), None),
        "media": _media_records(norm),
        # 커버리지 1순위 4종 — 판별 규칙은 위 §"커버리지 1순위 4종 판별" 주석이 정본
        "ratio": next((x for x in series_all if _ratio_series(x[1]) is not None), None),
        "trend": next((x for x in series_all if _trend_series(x[1]) is not None), None),
        "branch": most([x for x in graph_all if _branch_graph(x[1]) is not None],
                       lambda p: len(p.get("nodes") or [])),
        "grid": most(grid_all, lambda p: len(_grid_cards(p) or [])),
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

    # 커버리지 1순위 4종 — 구조와 정확 대응이라 기존 슬롯보다 먼저 소유권을 가져간다.
    # 풀에 열리지 않으면(기본) 전부 no-op 이라 기존 배정은 바이트 단위로 그대로다.
    c_claim: set[int] = set()
    for key, slot in (("ratio", "c-ratio.series"), ("trend", "c-trend.lines"),
                      ("branch", "c-branch.nodes"), ("grid", "c-grid.cards")):
        entry = cand.get(key)
        if entry is not None and slot.split(".", 1)[0] in shorts:
            own(entry, slot)
            c_claim.add(id(entry))

    # 수치 계열의 첫 임자 — 다지표 계기판(l-kpi)과 혼합판(l-mix)은 3칸짜리 closing.stats
    # 보다 정확한 그릇이라 먼저 가져간다. 둘 다 없으면 기존 순서(dataviz → closing) 그대로.
    series_owner = None
    if id(cand["series"]) in c_claim:
        pass                                  # c-ratio/c-trend 가 이미 가져갔다
    elif cand["series"] is not None or cand.get("kpi") is not None:
        if "l-kpi" in shorts and cand.get("kpi") is not None:
            series_owner = "l-kpi.metrics"
        elif "l-mix" in shorts and cand.get("mix_table") is not None \
                and cand["series"] is not None:
            series_owner = "l-mix.chart"
    plan["series_slot"] = None
    if cand["series"] is not None and series_owner is None and id(cand["series"]) not in c_claim:
        if "dataviz" in shorts:
            plan["series_slot"] = "dataviz.bars"
        elif "closing" in shorts:
            plan["series_slot"] = "closing.stats"

    # 목록형 상세는 키값군의 정확 대응(9쌍 → 8행)이라 proof.cases 2줄 압축보다 먼저다
    list_pairs = cand.get("list_pairs") if "l-list" in shorts else None
    pairs_pool = [x for x in cand["pairs"] if x is not list_pairs and id(x) not in c_claim]

    proof_cap = _slot_cap("proof", "cases")[0] or 3
    pairs_for_proof = pairs_pool[:proof_cap] if "proof" in shorts else []
    table_for_proof = None
    if "proof" in shorts and len(pairs_for_proof) < proof_cap and cand["summary_tables"]:
        table_for_proof = cand["summary_tables"][0]
    remaining_pairs = [x for x in pairs_pool if x not in pairs_for_proof]
    pairs_for_closing = (
        (remaining_pairs or pairs_pool)[:1]
        if "closing" in shorts and plan["series_slot"] != "closing.stats" else []
    )

    compare_slot = ("compare.rows" if "compare" in shorts
                    else "differentiator.flow" if "differentiator" in shorts
                    else "l-ba.items" if "l-ba" in shorts else None)

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
    # d-* 씬 (포맷 template_pool 이 열어줬을 때만 shorts 에 들어온다 — 옵트인 경계)
    own(cand.get("matrix_table"), "d-matrix.rows" if "d-matrix" in shorts else None)
    own(cand.get("multi"), "d-multi.series" if "d-multi" in shorts else None)

    # ── 발표 레이아웃 l-* (같은 옵트인 경계 — 풀에 선언된 역할에서만 shorts 에 든다) ──
    plan["mix"] = (
        (cand["mix_table"], cand["series"])
        if "l-mix" in shorts and cand.get("mix_table") is not None
        and cand.get("series") is not None else None
    )
    plan["list_pairs_owned"] = list_pairs
    own(cand.get("tree"), "l-tree.nodes" if "l-tree" in shorts else None)
    own(cand.get("kpi") or cand.get("series"), series_owner)
    own(cand.get("quadrant"), "l-quad.items" if "l-quad" in shorts else None)
    own(list_pairs, "l-list.rows" if list_pairs is not None else None)
    if plan["mix"] is not None:
        own(plan["mix"][0], "l-mix.table")
    # 간이표는 아직 임자 없는 표 중 가장 작은 것 — 이미 다른 씬이 통째로 싣는 표를
    # 요약본으로 한 번 더 보이면 같은 근거가 두 화면에 다르게 남는다.
    split_entry = None
    if "l-split" in shorts:
        split_entry = next(
            (x for x in cand.get("split_tables") or []
             if str(x[0].get("frag_id", "")) not in owner), None
        )
        own(split_entry, "l-split.visual.table")
    plan["split_table"] = split_entry
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


def _frame(norm: dict, idx: int, total: int | None = None) -> dict:
    """푸터 메타. total 미지정은 기존 7씬 골격 — 골격이 길어진 포맷은 씬 수를 넘겨받는다."""
    return {
        "brand": _clip(norm["title"], 24),
        "total": f"{total or len(TEMPLATE_ORDER):02d}",
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


# ── d-* 데이터 씬 빌더 (격자 표 · 도판 · 다계열 — §9 #1·#2·#4 해소) ────────


# 코드값 배지 매핑 — 미디어 타입 → d-media badge 칩 (이미지는 배지 없음)
_MEDIA_BADGE = {"video": "영상", "cad_3d": "3D", "doc_viewer": "문서",
                "attachment": "첨부", "html_embed": "웹"}


def _build_d_matrix(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§9 #1 격자 표 → tpl.d-matrix — 행은 첫·끝 표본, 초과분은 omitted 로 정직 표기.

    코드값 칩: 한 열의 값이 전부 4자 이하면(RACI 의 R/A/C/I 류) chip 으로 세운다.
    """
    payload = plan["matrix_table"][1]
    cols_p, rows_p = payload["columns"], payload["rows"]
    col_cap = _slot_cap("d-matrix", "columns", "label")[0] or 8
    row_cap, label_max = _slot_cap("d-matrix", "rows", "label")
    cols = cols_p[:col_cap]
    col_omit = len(cols_p) - len(cols)
    keep = _span_indices(len(rows_p), row_cap)
    omitted = len(rows_p) - len(keep)

    def cell_val(i: int, col: dict) -> str:
        return str(rows_p[i].get(col["key"], "") or "").strip()

    # 열 단위 칩 판정 — 값 종류가 아니라 길이가 기준 (코드값은 nowrap 4자 상한)
    chip_cols = {
        c["key"] for c in cols[1:]
        if all(0 < len(cell_val(i, c)) <= 4 for i in keep)
    }
    rows = []
    for i in keep:
        cells = []
        for c in cols[1:]:
            v = cell_val(i, c) or "-"
            cell: dict = {"v": _clip(v, 4 if c["key"] in chip_cols else 12)}
            if c["key"] in chip_cols:
                cell["chip"] = True
            cells.append(cell)
        rows.append(
            {"label": _clip(cell_val(i, cols[0]) or f"행 {i + 1}", label_max or 24),
             "cells": cells}
        )
    data = {
        "kicker": "격자",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 표", 26),
        "columns": [{"label": _clip(c["label"] or c["key"], 10)} for c in cols],
        "rows": rows,
        "note": {"pre": _clip(f"{len(cols_p)}열×{len(rows_p)}행 원문 수록", 18)},
        "frame": _frame(norm, idx),
    }
    if omitted:
        data["omitted"] = omitted
    if col_omit:  # 열 생략도 무언 금지 — 풋노트에 밝힌다
        data["note"]["post"] = _clip(_omit_note(col_omit, "열은 원문 참조"), 18)
    return data


def _build_d_media(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§9 #2 이미지/도판 → tpl.d-media — 해결된 자산 최대 3장, src 는 assets/{파일명}.

    src 계약: 빌드 디렉터리의 `assets/` 아래에 해결 자산 사본이 있어야 한다
    (엔트리 기준 상대경로). 사본 복사는 빌드 단계 몫 — build_render_package 에는
    아직 자산 복사 단계가 없어 호출측이 복사한다(known issue 로 보고).
    """
    media = plan["media"]
    files = []
    for m in media[:3]:
        fname = Path(m["asset"]["local_path"]).name
        f = {
            "src": f"assets/{fname}",
            "caption": _clip(m.get("caption") or _clean_page_name(m.get("page", ""))
                             or "도판", 18),
            "alt": _clip(m.get("alt") or m.get("caption") or "보고서 도판", 80),
        }
        src_page = _clean_page_name(m.get("page", ""))
        if src_page:
            f["source"] = _clip(src_page, 14)
        badge = _MEDIA_BADGE.get(str(m.get("media_type") or ""))
        if badge:
            f["badge"] = badge
        files.append(f)
    left = len(media) - len(files)
    note = {"pre": _clip(_omit_note(left, "장은 원문 참조") or "원문 도판 그대로", 18)}
    return {
        "kicker": "도판",
        "title": _clip(f"{norm['title']} — 도판", 26),
        "files": files,
        "note": note,
        "frame": _frame(norm, idx),
    }


def _build_d_multi(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§9 #4 다계열 series → tpl.d-multi — 공통 축만, 값을 지어내지 않는다."""
    payload = plan["multi"][1]
    groups, cats, val = _multi_grid(payload)
    g_cap = _slot_cap("d-multi", "series", "name")[0] or 4
    c_cap, cat_max = _slot_cap("d-multi", "categories", "label")
    keep_g = groups[:g_cap]
    keep_c = [cats[i] for i in _span_indices(len(cats), c_cap)]
    omitted = (len(groups) - len(keep_g)) * len(cats) \
        + (len(cats) - len(keep_c)) * len(keep_g)
    data = {
        "kicker": "계열",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 계열 비교", 26),
        "categories": [{"label": _clip(c, cat_max or 8)} for c in keep_c],
        "series": [
            {"name": _clip(g, 10), "values": [val[(g, c)] for c in keep_c]}
            for g in keep_g
        ],
        "frame": _frame(norm, idx),
    }
    unit = payload.get("unit")
    if unit:
        data["unit"] = _clip(str(unit), 8)
    axis_max = (payload.get("axis") or {}).get("max")
    if isinstance(axis_max, (int, float)) and axis_max > 0:
        data["axisMax"] = float(axis_max)
    if omitted:
        data["note"] = {"pre": _clip(_omit_note(omitted, "값은 원문 참조"), 18)}
    return data


# ── 발표 레이아웃 빌더 8종 (l-* — 같은 데이터를 어떻게 배치하는가) ─────────
#
# 이 8종은 새 payload 종류를 요구하지 않는다. 빌더의 일도 그래서 옮겨 담기가 아니라
# **슬롯 상한 안에서 무엇을 남길지 고르고 생략을 화면에 밝히는 것**이다(§8 규칙 그대로).
# 상한은 전부 schema.json 에서 읽는다 — 상수를 코드에 박으면 스키마가 바뀔 때 조용히
# 어긋나고, 이번 라운드의 상한은 1920×1080 실측 역산이라 특히 그렇다.


def _num_text(v: float, limit: int) -> str:
    """수치 문자열 — value 패턴(^-?[0-9][0-9.,]*$)과 자수 상한을 함께 지킨다.

    지수 표기(1e+06)는 패턴 밖이라 반올림 정수로 떨어뜨리고, 그래도 길면 잘라낸 뒤
    끝의 구분자를 턴다("1,234," → "1,234").
    """
    s = _fmt_num(v)
    if "e" in s or "E" in s:
        s = f"{round(v):d}"
    if len(s) > limit:
        s = f"{round(v):d}"
    return s[:limit].rstrip(".,") or "0"


def _head_label(text: object, limit: int) -> str:
    """"Phase 0/1 — 작성자 owner check" → "Phase 0/1". 좁은 슬롯에서 말줄임보다 낫다.

    원문 라벨은 "이름 — 설명" 꼴이 흔하다. 그대로 자르면 이름까지 잘려("Phase 0/1 —…")
    무엇의 수치인지 사라지므로, 앞머리가 슬롯에 들어가면 앞머리만 남긴다.
    """
    s = " ".join(str(text).split())
    head = re.split(r"\s+[—–-]\s+", s, maxsplit=1)[0].strip()
    return _clip(head if head and len(head) <= limit else s, limit)


def _bullet_pool(norm: dict, fragments: list[dict], n: int) -> list[str]:
    """설명 문장 후보 — 주장 조각 우선, 모자라면 페이지 이름으로 채운다(지어내지 않는다)."""
    pool = [t for t in _texts(fragments, n * 2, type="claim") if t.strip()]
    for p in norm.get("pages", []):
        if len(pool) >= n:
            break
        name = _clean_page_name(p.get("name", ""))
        if name and name not in pool:
            pool.append(name)
    return pool


# ── tpl.l-split — 좌 설명 + 우 근거 2단 ──────────────────────────────────


def _split_visual(plan: dict, norm: dict) -> tuple[dict, str, str]:
    """근거 슬롯 하나를 고른다 → (visual, 생략 문구, 근거 캡션). 표 → 막대 → 강조 박스 순."""
    entry = plan.get("split_table")
    if entry is not None:
        payload = entry[1]
        cols_p, rows_p = payload["columns"], payload["rows"]
        col_cap = _cap("l-split", "visual", "table", "columns", default=3)
        row_cap = _cap("l-split", "visual", "table", "rows", default=6)
        lbl_max = _lim("l-split", "visual", "table", "rows", "[]", "label", default=20)
        v_max = _lim("l-split", "visual", "table", "rows", "[]", "cells", "[]", "v", default=14)
        head_max = _lim("l-split", "visual", "table", "columns", "[]", "label", default=12)
        cols = cols_p[:col_cap]
        keep = _span_indices(len(rows_p), row_cap)
        rows = [
            {
                "label": _clip(str(rows_p[i].get(cols[0]["key"], "") or f"행 {i + 1}"), lbl_max),
                "cells": [{"v": _clip(str(rows_p[i].get(c["key"], "") or "-"), v_max)}
                          for c in cols[1:]],
            }
            for i in keep
        ]
        omit = _omit_note(len(cols_p) - len(cols), "열") or \
            _omit_note(len(rows_p) - len(keep), "행")
        visual = {
            "kind": "table",
            "table": {
                "columns": [{"label": _clip(c.get("label") or c["key"], head_max)} for c in cols],
                "rows": rows,
            },
        }
        return visual, omit, str(payload.get("caption") or "")
    if plan.get("series") is not None:
        payload = plan["series"][1]
        cap = _cap("l-split", "visual", "bars", "items", default=6)
        lbl_max = _lim("l-split", "visual", "bars", "items", "[]", "label", default=20)
        entries = [e for e in payload.get("series") or [] if e.get("value") is not None]
        keep = _extreme_indices([e.get("value") for e in entries], cap)
        bars = {
            "items": [{"label": _clip(entries[i].get("label", ""), lbl_max),
                       "value": max(float(entries[i]["value"]), 0.0)} for i in keep]
        }
        unit = str(payload.get("unit") or "")
        if unit:
            bars["unit"] = _clip(unit, _lim("l-split", "visual", "bars", "unit", default=4))
        return ({"kind": "bars", "bars": bars},
                _omit_note(len(entries) - len(keep), "계열"),
                str(payload.get("caption") or ""))
    head_max = _lim("l-split", "visual", "note", "headline", default=34)
    return ({"kind": "note",
             "note": {"headline": _clip(norm["title"], head_max), "tone": "info"}}, "", "")


def _build_l_split(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§배치 표/계열 → tpl.l-split — 좌 설명이 서고 우 근거가 뒤따르는 2단 씬.

    불릿 개수는 세로 예산에 묶여 있다(스키마 조건부: 5개면 22자, 4개 이하면 40자).
    그래서 자수 상한을 개수에서 역산해 고른다 — 밀도를 올리면 문장이 짧아지는 교환이
    화면 뒤가 아니라 조립 규칙에 드러나 있어야 한다.
    """
    n_cap = _cap("l-split", "bullets", default=5)
    n_min = _floor("l-split", "bullets", default=3)
    pool = _bullet_pool(norm, fragments, n_cap + 2)
    lead_text = pool[0] if pool else norm["title"]
    pool = pool[1:] or pool          # 리드가 가져간 문장을 불릿에서 다시 세지 않는다
    n = max(n_min, min(n_cap, len(pool)))
    wide = _lim("l-split", "bullets", "[]", "text", default=40)
    tight = ((((_doc_schema("l-split").get("allOf") or [{}])[0].get("then") or {})
              .get("properties") or {}).get("bullets") or {}).get("items", {}) \
        .get("properties", {}).get("text", {}).get("maxLength", 22)
    limit = tight if n >= n_cap else wide
    bullets = [{"text": _clip(t, limit)} for t in (pool + ["원문 참조"] * n_min)[:n]]
    bullets[0]["em"] = True

    visual, omit, caption = _split_visual(plan, norm)
    lead = _clip(lead_text, _lim("l-split", "lead", default=30))
    # 소결론 자리는 12+10+12자다 — 문장을 잘라 넣으면 뜻이 깨진다("엔지니어 → 임원…").
    # 자동 조립은 대신 근거의 출처를 적는다(주장 문장은 저작 시나리오가 채우는 자리다).
    conclusion = {
        "pre": "근거는 원문 ",
        "strong": {"table": "표 그대로", "bars": "수치 그대로"}.get(visual["kind"], "본문"),
    }
    if omit:  # 무언의 절단 금지 — 간이표가 원문 전부인 척하지 않는다
        # _clip 이 아니라 _truncate — 앞 공백이 살아야 "표 그대로 · 외 1열" 로 붙는다
        conclusion["post"] = _truncate(" · " + omit,
                                       _lim("l-split", "conclusion", "post", default=12))
    return {
        "kicker": "설명과 근거",
        "title": _clip(caption or norm["title"], _lim("l-split", "title", default=26)),
        "ratio": "6:4",
        "lead": lead,
        "bullets": bullets,
        "conclusion": conclusion,
        "visual": visual,
        "frame": _frame(norm, idx, plan.get("_skeleton_len")),
    }


# ── tpl.l-list — 목록형 상세 5~8행 ───────────────────────────────────────


def _build_l_list(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§배치 pairs(키값) → tpl.l-list — 9쌍을 2줄로 뭉개던 proof.cases 대신 8행 그대로.

    l-list 에는 omitted 필드가 없다(스키마). 생략을 화면에서 지울 수는 없으므로 타이틀
    꼬리에 "(외 N건)" 으로 남긴다 — 필드 신설은 템플릿 소유자 몫이라 심의 안건으로 올렸다.
    """
    cap = _cap("l-list", "rows", default=8)
    floor = _floor("l-list", "rows", default=5)
    t_max = _lim("l-list", "rows", "[]", "title", default=30)
    d_wide = _lim("l-list", "rows", "[]", "desc", default=100)
    d_tight = ((((_doc_schema("l-list").get("allOf") or [{}])[0].get("then") or {})
                .get("properties") or {}).get("rows") or {}).get("items", {}) \
        .get("properties", {}).get("desc", {}).get("maxLength", 50)

    src: list[tuple[str, str]] = []
    entry = plan.get("list_pairs_owned") or plan.get("list_pairs")
    if entry is not None:
        src = [(str(p.get("label") or p.get("key") or ""), str(p.get("value") or ""))
               for p in entry[1].get("pairs") or []]
    if len(src) < floor:  # 키값이 없으면 주장 조각 목록으로 (제목만, 설명 없음)
        src = [(t, "") for t in _bullet_pool(norm, fragments, cap)]
    rows_src = src[:cap]
    omitted = max(len(src) - len(rows_src), 0)
    d_max = d_tight if len(rows_src) >= 6 else d_wide
    rows = []
    for i, (title, desc) in enumerate(rows_src, 1):
        row: dict = {"num": f"{i:02d}"[-2:], "title": _clip(title or f"항목 {i}", t_max)}
        if desc.strip():
            row["desc"] = _clip(desc, d_max)
        rows.append(row)
    while len(rows) < floor:  # 하한 미달은 스키마 위반 — 페이지 이름으로 채운다
        rows.append({"num": f"{len(rows) + 1:02d}", "title": f"항목 {len(rows) + 1}"})

    t_lim = _lim("l-list", "title", default=26)
    title = _clip(entry[1].get("caption") if entry else norm["title"], t_lim) \
        if (entry and entry[1].get("caption")) else _clip(norm["title"], t_lim)
    note = _omit_note(omitted, "건")
    if note:
        title = f"{_clip(title, t_lim - len(note) - 3)} ({note})"
    return {
        "kicker": "목록",
        "title": title,
        "rows": rows,
        "frame": _frame(norm, idx, plan.get("_skeleton_len")),
    }


# ── tpl.l-tree — 계층 구조도 ─────────────────────────────────────────────


def _tree_label_caps() -> dict[int, int]:
    """레벨별 라벨 자수 상한 — schema 의 조건부 allOf 가 정본 (기본 14/18/22)."""
    base = _lim("l-tree", "nodes", "[]", "label", default=22)
    caps = {0: base, 1: base, 2: base}
    for rule in _node("l-tree", "nodes", "[]").get("allOf") or []:
        lv = (((rule.get("if") or {}).get("properties") or {}).get("level") or {}).get("const")
        mx = (((rule.get("then") or {}).get("properties") or {}).get("label") or {}).get("maxLength")
        if isinstance(lv, int) and isinstance(mx, int):
            caps[lv] = mx
    return caps


def _tree_level_caps() -> dict[int, int]:
    """레벨별 노드 개수 상한 — schema 루트 allOf 의 contains/maxContains (기본 1/4/8)."""
    caps = {0: 1, 1: 4, 2: 8}
    for rule in _doc_schema("l-tree").get("allOf") or []:
        node = (rule.get("properties") or {}).get("nodes") or {}
        lv = (((node.get("contains") or {}).get("properties") or {}).get("level") or {}).get("const")
        mx = node.get("maxContains")
        if isinstance(lv, int) and isinstance(mx, int):
            caps[lv] = mx
    return caps


def _tree_pick(payload: dict) -> tuple[list[dict], list[dict], int]:
    """graph(tree) → 용량에 맞춘 (nodes, edges, 생략 수).

    가지를 통째로 버리면 구조 자체가 거짓이 되므로 리프는 **가지별 라운드로빈**으로
    남긴다 — 남은 가지마다 최소 1개는 보이고 총합이 상한을 넘지 않는다.
    """
    roots, mids, leaves = _tree_levels(payload) or ([], [], [])
    lv_cap, lb_cap = _tree_level_caps(), _tree_label_caps()
    keep_mid = mids[:lv_cap.get(1, 4)]
    leaf_cap = lv_cap.get(2, 8)
    # 가지당 상한은 세로 예산이다 — 총 상한을 가지 수로 올림 배분하면 3가지면 3·3·2 가 된다
    per_branch = -(-leaf_cap // max(len(keep_mid), 1))

    parent: dict[str, str] = {}
    for e in payload.get("edges") or []:
        parent.setdefault(str(e.get("to")), str(e.get("from")))
    branch: dict[str, list[dict]] = {str(m.get("id")): [] for m in keep_mid}
    for lf in leaves:
        p = parent.get(str(lf.get("id")))
        if p in branch:
            branch[p].append(lf)

    keep_leaf: list[dict] = []
    for r in range(per_branch):
        for lst in branch.values():
            if r < len(lst) and len(keep_leaf) < leaf_cap:
                keep_leaf.append(lst[r])

    kept = roots[:1] + keep_mid + keep_leaf
    ids = {str(n.get("id")) for n in kept}
    nodes = []
    for n in kept:
        level = int(n.get("level") or 0)
        out = {"id": str(n.get("id")), "label": _clip(str(n.get("label") or n.get("id")),
                                                     lb_cap.get(level, 22)), "level": level}
        if level == 1 and str(n.get("note") or "").strip():
            out["note"] = _clip(str(n["note"]), _lim("l-tree", "nodes", "[]", "note", default=13))
        nodes.append(out)
    e_cap = _cap("l-tree", "edges", default=12)
    edges = [{"from": str(e["from"]), "to": str(e["to"])}
             for e in payload.get("edges") or []
             if str(e.get("from")) in ids and str(e.get("to")) in ids][:e_cap]
    return nodes, edges, max(len(payload.get("nodes") or []) - len(nodes), 0)


def _build_l_tree(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§배치 graph(shape=tree) → tpl.l-tree — nodes/edges 를 개명 없이 그대로 받는다.

    concept 의 방사형은 레벨을 지우지만(얕은 레벨 우선 8개) 여기서는 레벨이 곧 그림이다.
    """
    payload = plan["tree"][1]
    nodes, edges, omitted = _tree_pick(payload)
    data = {
        "kicker": "계층",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 구조",
                       _lim("l-tree", "title", default=26)),
        "nodes": nodes,
        "edges": edges,
        "frame": _frame(norm, idx, plan.get("_skeleton_len")),
    }
    if omitted:
        data["omitted"] = omitted
    return data


# ── tpl.l-quote — 핵심 문장 강조 ─────────────────────────────────────────


def _build_l_quote(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """보고서의 결론 문장 하나를 각인한다 — 구조 payload 무대응(문장은 편집 판단이다).

    지어낸 선언이 아니라 원문에서 온 문장만 쓴다: ai_summary → 첫 주장 조각 → 제목 순.
    """
    q_max = _lim("l-quote", "quote", default=70)
    # 제목·소제목이 아니라 **문장**을 고른다 — 종결어미로 끝나고 슬롯에 들어가는 것 중 가장 긴 것
    claims = [t.strip() for t in _texts(fragments, 30, type="claim") if t.strip()]

    def pick(xs: list[str]) -> list[str]:
        return [t for t in xs if len(t) <= q_max and re.search(r"[다요\.\!\?]$", t)]

    # 도입/목적 절의 문장이 결론 각인에 가장 가깝다 — 없으면 전체에서 고른다
    sentences = pick([t.strip() for t in _texts(fragments, 30, type="claim", section="purpose")
                      if t.strip()]) or pick(claims)
    quote = str(norm.get("ai_summary") or "").strip() or (
        max(sentences, key=len) if sentences else (claims[0] if claims else norm["title"])
    )
    data = {
        "kicker": "결론",
        "quote": _clip(quote, q_max),
        "speaker": _clip(norm["title"], _lim("l-quote", "speaker", default=20)),
        "texture": "rule",
        "frame": _frame(norm, idx, plan.get("_skeleton_len")),
    }
    role = " · ".join(x for x in (norm.get("report_date", ""), *norm.get("tags", [])[:1]) if x)
    if role:
        data["role"] = _clip(role, _lim("l-quote", "role", default=26))
    return data


# ── tpl.l-kpi — 다지표 계기판 ────────────────────────────────────────────


def _build_l_kpi(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§배치 단일 계열 series(4개 이상) → tpl.l-kpi — closing.stats 3칸 상한을 넘긴다.

    증감(delta)·스파크바는 **비교 시점이 있어야** 만들 수 있는 값이다. 구조 payload 에
    이전 값이 없으므로 자동 조립은 싣지 않는다 — 방향과 평가를 지어내는 것이 가장 나쁘다.
    """
    entry = plan.get("kpi") or plan.get("series")
    payload = entry[1]
    entries = _kpi_metrics(payload) or [
        e for e in payload.get("series") or [] if e.get("value") is not None
    ]
    cap = _cap("l-kpi", "metrics", default=6)
    floor = _floor("l-kpi", "metrics", default=4)
    lbl_max = _lim("l-kpi", "metrics", "[]", "label", default=14)
    v_max = _lim("l-kpi", "metrics", "[]", "value", default=6)
    u_max = _lim("l-kpi", "metrics", "[]", "unit", default=3)
    keep = _extreme_indices([e.get("value") for e in entries], cap)
    unit = str(payload.get("unit") or "")
    metrics = []
    for i in keep:
        e = entries[i]
        m = {"label": _head_label(e.get("label", ""), lbl_max),
             "value": _num_text(float(e["value"]), v_max)}
        u = str(e.get("unit") or unit or "").strip()
        if u:
            m["unit"] = _clip(u, u_max)
        metrics.append(m)
    while len(metrics) < floor:   # 하한 미달은 스키마 위반 — 조각 수로 채우지 않고 거절 대신 표기
        metrics.append({"label": f"지표 {len(metrics) + 1}", "value": "0"})
    data = {
        "kicker": "지표판",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 지표",
                       _lim("l-kpi", "title", default=26)),
        "metrics": metrics,
        "frame": _frame(norm, idx, plan.get("_skeleton_len")),
    }
    omitted = len(entries) - len(keep)
    if omitted:
        data["omitted"] = omitted
    return data


# ── tpl.l-quad — 4분면 포지셔닝 ──────────────────────────────────────────


def _norm01(v: float, lo: float, hi: float) -> float:
    return 0.5 if hi <= lo else round(min(max((v - lo) / (hi - lo), 0.0), 1.0), 3)


def _build_l_quad(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§배치 series(quadrant/scatter — x·y) → tpl.l-quad — 0~1 정규화 배치.

    **알려진 손실**: 축 이름(props.x_axis_title/y_axis_title)과 가로 범위(x_range)는
    widgets._x_quadrant 가 payload 에 싣지 않는다. 그래서 축 이름은 자리표시자가 되고
    정규화 기준은 데이터 범위로 떨어진다 — 사분면 경계(0.5)가 원 위젯의 경계와 어긋날
    수 있으므로 그 사실을 note 로 화면에 밝힌다(심의 안건으로 올렸다).
    """
    payload = plan["quadrant"][1]
    pts = _quad_points(payload) or []
    cap = _cap("l-quad", "items", default=10)
    lbl_max = _lim("l-quad", "items", "[]", "label", default=18)
    keep = _extreme_indices([p.get("value") for p in pts], cap)
    xs = [float(p["x"]) for p in pts]
    ys = [float(p["value"]) for p in pts]
    axis = payload.get("axis") or {}
    y_lo = float(axis["min"]) if isinstance(axis.get("min"), (int, float)) else min(ys)
    y_hi = float(axis["max"]) if isinstance(axis.get("max"), (int, float)) else max(ys)
    x_lo, x_hi = min(xs), max(xs)
    items = [
        {
            "label": _clip(str(pts[i].get("label", "")), lbl_max),
            "x": _norm01(float(pts[i]["x"]), x_lo, x_hi),
            "y": _norm01(float(pts[i]["value"]), y_lo, y_hi),
        }
        for i in keep
    ]
    ax_lim = _lim("l-quad", "xAxis", "low", default=6)
    ay_lim = _lim("l-quad", "yAxis", "low", default=4)
    n_lim = _lim("l-quad", "xAxis", "name", default=14)
    # 축 이름은 payload 에 없다(아래 docstring). 캡션이 "A × B" 꼴이면 그 관례를 읽고,
    # 아니면 지어내지 않고 축의 정체를 그대로 적는다.
    m = re.match(r"^\s*(.+?)\s*[×xX✕]\s*(.+?)\s*$", str(payload.get("caption") or ""))
    x_name = _clip(m.group(1), n_lim) if m else "가로 축"
    y_name = _clip(re.sub(r"\(.*?\)", "", m.group(2)).strip(), n_lim) if m else "세로 축"
    return {
        "kicker": "포지셔닝",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 사분면",
                       _lim("l-quad", "title", default=26)),
        "xAxis": {"name": x_name, "low": _num_text(x_lo, ax_lim),
                  "high": _num_text(x_hi, ax_lim)},
        "yAxis": {"name": y_name or "세로 축", "low": _num_text(y_lo, ay_lim),
                  "high": _num_text(y_hi, ay_lim)},
        "quadrants": {"tl": "좌상", "tr": "우상", "bl": "좌하", "br": "우하"},
        "items": items,
        "note": {"pre": "축 이름은 원문 위젯 ", "strong": "속성 미전달",
                 "post": " · 범위는 데이터 기준"},
        "frame": _frame(norm, idx, plan.get("_skeleton_len")),
    }


# ── tpl.l-ba — Before/After 반반 ─────────────────────────────────────────


_NUMERIC_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def _ba_side(label: str, col: dict, rows: list[dict], key0: str, caption: str) -> dict:
    """비교 표의 한 열 → 한쪽 상태. 수치 행이 있으면 대표 수치로 올린다."""
    i_max = _cap("l-ba", "before", "items", default=5)
    i_min = _floor("l-ba", "before", "items", default=3)
    t_max = _lim("l-ba", "before", "items", "[]", "text", default=22)
    keep = _span_indices(len(rows), i_max)
    items = [{"text": _clip(str(rows[i].get(col["key"], "") or "-"), t_max)} for i in keep]
    while len(items) < i_min:
        items.append({"text": "원문 참조"})
    # 대표 수치 — 양쪽이 모두 수치인 행이 있으면 그 값, 없으면 비교 관점 수(메타값)
    value, desc = str(len(rows)), "개 관점"
    for r in rows:
        m = _NUMERIC_RE.search(str(r.get(col["key"], "")))
        if m:
            value = m.group(0)
            desc = str(r.get(key0, "") or "관점")
            break
    return {
        "label": _clip(label, _lim("l-ba", "before", "label", default=10)),
        "title": _clip(str(col.get("label") or col["key"]) + " 상태",
                       _lim("l-ba", "before", "title", default=30)),
        "items": items,
        "summary": {"value": _num_text(float(value.replace(",", "")),
                                       _lim("l-ba", "before", "summary", "value", default=6)),
                    "desc": _clip(desc, _lim("l-ba", "before", "summary", "desc", default=10))},
    }


def _build_l_ba(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§배치 comparison 2안(table) → tpl.l-ba — 두 열을 두 상태로 세운다.

    **자동 조립의 한계**: l-ba 는 상태마다 대표 수치를 요구하는데 comparison payload 에는
    수치가 없다. 수치가 든 행이 있으면 그것을 올리고, 없으면 비교 관점 수(메타값)로
    채운다 — 후자는 심의가 손으로 채워야 하는 자리이지 데이터가 아니다.
    """
    entry = plan.get("compare_table")
    payload = entry[1]
    cols, rows = payload["columns"], payload["rows"]
    key0 = cols[0]["key"]
    return {
        "kicker": "전환",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 대비",
                       _lim("l-ba", "title", default=26)),
        "before": _ba_side("AS-IS", cols[1], rows, key0, payload.get("caption") or ""),
        "after": _ba_side("TO-BE", cols[2], rows, key0, payload.get("caption") or ""),
        "note": {"pre": "대표 수치는 원문 표의 ", "strong": "수치 행", "post": " 에서 왔다"},
        "frame": _frame(norm, idx, plan.get("_skeleton_len")),
    }


# ── tpl.l-mix — 표 + 차트 혼합 ───────────────────────────────────────────


def _build_l_mix(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """§배치 table + series 동시 → tpl.l-mix — 위 한 줄 결론, 아래 좌 간이표 · 우 막대.

    stats(요약 수치)와 lead(한 줄 결론)는 스키마가 배타(oneOf)로 못박았다. 자동 조립은
    lead 를 쓴다 — 요약 수치는 원문에 없는 집계를 만들어야 나오기 때문이다.
    """
    t_entry, s_entry = plan["mix"]
    t_payload, s_payload = t_entry[1], s_entry[1]
    cols, rows_p = _mix_table(t_payload)
    row_cap = _cap("l-mix", "table", "rows", default=5)
    lbl_max = _lim("l-mix", "table", "rows", "[]", "label", default=13)
    v_max = _lim("l-mix", "table", "rows", "[]", "cells", "[]", "v", default=6)
    head_max = _lim("l-mix", "table", "columns", "[]", "label", default=10)
    keep = _span_indices(len(rows_p), row_cap)
    rows = [
        {
            "label": _clip(str(rows_p[i].get(cols[0]["key"], "") or f"행 {i + 1}"), lbl_max),
            "cells": [{"v": _clip(str(rows_p[i].get(c["key"], "") or "-"), v_max)}
                      for c in cols[1:]],
        }
        for i in keep
    ]
    b_cap = _cap("l-mix", "chart", "bars", default=4)
    b_lbl = _lim("l-mix", "chart", "bars", "[]", "label", default=18)
    b_disp = _lim("l-mix", "chart", "bars", "[]", "display", default=6)
    entries = [e for e in s_payload.get("series") or [] if e.get("value") is not None]
    b_keep = _extreme_indices([e.get("value") for e in entries], b_cap)
    unit = str(s_payload.get("unit") or "")
    bars = [
        {
            "label": _head_label(entries[i].get("label", ""), b_lbl),
            "value": max(float(entries[i]["value"]), 0.0),
            "display": _clip(f"{_fmt_num(float(entries[i]['value']))}{unit}", b_disp),
        }
        for i in b_keep
    ]
    bars[max(range(len(bars)), key=lambda j: bars[j]["value"])]["em"] = True
    chart: dict = {"bars": bars}
    axis_max = (s_payload.get("axis") or {}).get("max")
    if isinstance(axis_max, (int, float)) and axis_max > 0:
        chart["axisMax"] = float(axis_max)

    # 상단 띠 — 요약 수치와 한 줄 결론은 배타(oneOf)다. 계열 전체를 집계한 수치 3개가
    # 한 줄 캡션 반복보다 정보가 많아 stats 를 쓴다(전부 원 계열의 산술 집계 — 라벨로 밝힌다).
    vals = [float(e["value"]) for e in entries]
    top = max(range(len(entries)), key=lambda j: vals[j])
    s_v = _lim("l-mix", "stats", "[]", "value", default=6)
    s_l = _lim("l-mix", "stats", "[]", "label", default=14)
    stats = [
        {"value": _num_text(len(entries), s_v), "unit": "개", "label": "전체 항목"},
        {"value": _num_text(vals[top], s_v), "unit": _clip(unit or "", 3) or "pt",
         "label": _head_label(entries[top].get("label", ""), s_l)},
        {"value": _num_text(sum(vals) / len(vals), s_v), "unit": _clip(unit or "", 3) or "pt",
         "label": "평균"},
    ][:_cap("l-mix", "stats", default=3)]

    # 생략 표기는 18자 슬롯이라 "외 N행 · 외 N열 · 외 N계열" 이 들어가지 않는다 — 한 줄로 줄인다
    bits = [f"{n}{u}" for n, u in (
        (len(rows_p) - len(keep), "행"),
        (len(t_payload["columns"]) - len(cols), "열"),
        (len(entries) - len(b_keep), "계열"),
    ) if n > 0]
    omit = ("생략 " + "·".join(bits)) if bits else ""
    return {
        "kicker": "표와 막대",
        "title": _clip(t_payload.get("caption") or f"{norm['title']} — 표와 막대",
                       _lim("l-mix", "title", default=26)),
        "stats": stats,
        "table": {"columns": [{"label": _clip(c.get("label") or c["key"], head_max)}
                              for c in cols], "rows": rows},
        "chart": chart,
        "note": {"pre": _clip(omit or "원문 표와 계열 그대로",
                              _lim("l-mix", "note", "pre", default=18))},
        "frame": _frame(norm, idx, plan.get("_skeleton_len")),
    }


# ── 커버리지 1순위 4종 빌더 (c-ratio · c-trend · c-branch · c-grid) ───────


def _ratio_display(v: float, limit: int = 6) -> str:
    """범례 값 표기 — c-ratio series[].display 의 6자 계약 안에 들어가는 수치 표기.

    display 를 **생략하면** 렌더가 `fmtNum(value)+unit` 을 쓰는데 그 문자열에는 상한이
    없어 값존 150px 를 넘는다(2026-07-29 tpl.c-ratio 심의 F1, 실측 +47px). 조립기는
    항상 채운다. 자릿수를 잘라 값을 바꾸지 않고 만·억 자릿수로 접으며, 단위는 붙이지
    않는다 — '123.5만억원' 같은 자릿수·단위 혼선을 막기 위해 단위는 각주에 한 번만 쓴다.
    """
    plain = f"{v:,.0f}" if abs(v) >= 1000 else _fmt_num(v)
    if len(plain) <= limit:
        return plain
    for div, suffix in ((1e8, "억"), (1e4, "만")):
        if abs(v) >= div:
            folded = f"{v / div:.1f}".rstrip("0").rstrip(".") + suffix
            if len(folded) <= limit:
                return folded
            return f"{v / div:.0f}"[:limit - 1] + suffix
    return plain[:limit]


def _build_c_ratio(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """비율형 series → tpl.c-ratio — 상한 초과분은 total 로 넘겨 '기타(미표기)'로 자동 편입.

    상위 N개만 남기고 나머지를 버리면 화면의 100% 가 원문의 100% 와 달라진다. 그래서
    잘라내는 대신 total.value 에 전체 합을 선언한다 — 렌더러가 차액을 '기타(미표기)'
    조각으로 편입하고 편입량을 각주에 쓴다(스키마가 보장하는 경로).
    """
    payload = plan["ratio"][1]
    items = _ratio_series(payload) or []
    cap, label_max = _slot_cap("c-ratio", "series", "label")
    cap = cap or 7
    unit = _clip(str(payload.get("unit") or ""), 6)
    ordered = sorted(items, key=lambda x: -x["value"])
    keep = ordered[: max(4, cap - 1)] if len(ordered) > cap else ordered
    total = sum(x["value"] for x in items)
    data: dict = {
        "kicker": "구성비",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 구성비", 26),
        "series": [
            {"label": _clip(x["label"], label_max or 20),
             "value": x["value"],
             "display": _ratio_display(x["value"])}
            for x in keep
        ],
        "total": {"value": total, "label": _clip("전체", 10)},
        "center": {"value": _ratio_display(total, 5), "label": _clip("전체", 10)},
        "frame": _frame(norm, idx),
    }
    if unit:
        data["unit"] = unit
    left = len(items) - len(keep)
    # 단위는 각주에 한 번만 쓴다 (display 가 단위를 달지 않는 이유는 _ratio_display 주석)
    note = " · ".join(x for x in (f"단위 {unit}" if unit else "",
                                  _omit_note(left, "항목은 기타로 편입")) if x)
    if note:
        data["footnote"] = {"text": _clip(note, 30)}
    return data


def _build_c_trend(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """시계열 series → tpl.c-trend — 시점은 첫·끝 고정 표본, 축 하한은 데이터 아래로만.

    axis.min 을 데이터 최솟값보다 위로 올리면 라인이 기준선 아래로 잘린다
    (2026-07-29 tpl.c-trend 심의 F1, 실측 409.2px 플롯 밖). 조립기는 원문 축 선언이
    있어도 데이터 최솟값을 넘는 하한은 싣지 않는다.
    """
    payload = plan["trend"][1]
    lines, points, val = _trend_series(payload)
    p_cap, p_max = _slot_cap("c-trend", "points", "label")
    l_cap, l_max = _slot_cap("c-trend", "lines", "label")
    keep_p = [points[i] for i in _span_indices(len(points), p_cap or 12)]
    keep_l = lines[: l_cap or 3]
    unit = _clip(str(payload.get("unit") or ""), 6)
    values = {g: [val[(g, p)] for p in keep_p] for g in keep_l}
    flat = [v for vs in values.values() for v in vs]
    lo, hi = (min(flat), max(flat)) if flat else (0.0, 1.0)

    axis: dict = {}
    src_axis = payload.get("axis") or {}
    a_min, a_max = src_axis.get("min"), src_axis.get("max")
    if isinstance(a_min, (int, float)) and 0 <= float(a_min) <= lo:
        axis["min"] = float(a_min)            # 데이터 아래로만 — 하단 절단 금지
    if isinstance(a_max, (int, float)) and float(a_max) >= hi > 0:
        axis["max"] = float(a_max)

    first, last = (flat and values[keep_l[0]][0]), (flat and values[keep_l[0]][-1])
    delta_pct = ((last - first) / first * 100) if first else 0.0
    direction = "up" if last > first else "down" if last < first else "flat"
    data: dict = {
        "kicker": "추세",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 추세", 26),
        "points": [{"label": _clip(p, p_max or 5)} for p in keep_p],
        "lines": [
            {"label": _clip(g or (payload.get("caption") or "계열"), l_max or 8),
             "values": values[g], "fill": i == 0 and len(keep_l) == 1}
            for i, g in enumerate(keep_l)
        ],
        "readout": {
            "value": _clip(f"{_fmt_num(last)}{unit}", 6),
            "desc": _clip(f"{keep_p[-1]} 시점 값", 20),
            # polarity 는 언제나 neutral — 좋고 나쁨은 심의가 정한다(방향=평가 혼동 차단)
            "delta": {"text": _clip(f"{delta_pct:+.1f}%", 10),
                      "direction": direction, "polarity": "neutral"},
        },
        "frame": _frame(norm, idx),
    }
    if unit:
        data["unit"] = unit
    if axis:
        data["axis"] = axis
    omitted = len(points) - len(keep_p)
    src = _omit_note(omitted, "시점은 원문 참조") or _clean_page_name(
        str((plan["trend"][0].get("source") or {}).get("page") or ""))
    if src:
        data["source"] = {"text": _clip(src, 28)}
    return data


_BRANCH_KIND_NOTE = {"start": "시작", "end": "종료"}


def _build_c_branch(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """분기 graph → tpl.c-branch — kind 는 그래프 위상에서 파생한다(저작 필드가 아니다).

    시작 = 들어오는 엣지가 없는 최소 레벨 노드, 판단 = 나가는 엣지 2개 이상,
    끝 = 나가는 엣지가 없는 노드. 나머지는 처리. 스키마가 decision 1개를 요구하므로
    `_branch_graph` 가 이미 그 존재를 보장한 뒤에 온다.
    """
    nodes, edges = _branch_graph(plan["branch"][1])
    label_max = _slot_cap("c-branch", "nodes", "label")[1] or 22
    note_max = 20
    out_deg: dict[str, int] = {}
    in_deg: dict[str, int] = {}
    for e in edges:
        out_deg[str(e["from"])] = out_deg.get(str(e["from"]), 0) + 1
        in_deg[str(e["to"])] = in_deg.get(str(e["to"]), 0) + 1

    def kind_of(n: dict) -> str:
        nid = str(n["id"])
        if out_deg.get(nid, 0) >= 2:
            return "decision"
        if in_deg.get(nid, 0) == 0:
            return "start"
        if out_deg.get(nid, 0) == 0:
            return "end"
        return "process"

    out_nodes = []
    for n in nodes:
        kind = kind_of(n)
        # 판단 노드는 마름모 내접 사각이라 12자로 조인다 (스키마 if/then 계약)
        cap = 12 if kind == "decision" else label_max
        item: dict = {"id": _clip(str(n["id"]), 40),
                      "label": _clip(str(n.get("label") or n["id"]), cap),
                      "level": int(n["level"]), "kind": kind}
        note = str(n.get("note") or "").strip()
        if note and kind != "decision":
            item["note"] = _clip(note, note_max)
        if kind == "end":
            item["tone"] = "neutral"
        out_nodes.append(item)
    ids = {n["id"] for n in out_nodes}
    out_edges = []
    for e in edges:
        src, dst = _clip(str(e["from"]), 40), _clip(str(e["to"]), 40)
        if src not in ids or dst not in ids:
            continue
        edge: dict = {"from": src, "to": dst}
        label = _s_label(e)
        if label:
            edge["label"] = _clip(label, 3)   # 판정 코드값 전용 (조건 서술은 note 로)
        out_edges.append(edge)
    payload = plan["branch"][1]
    data: dict = {
        "kicker": "분기",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 분기 절차", 26),
        "nodes": out_nodes,
        "edges": out_edges,
        "frame": _frame(norm, idx),
    }
    total = len(payload.get("nodes") or [])
    left = total - len(out_nodes)
    data["note"] = {
        "pre": _clip(f"판단 {sum(1 for n in out_nodes if n['kind'] == 'decision')}곳 · ", 18),
        "strong": _clip(f"노드 {len(out_nodes)}", 12),
        "post": _clip(" " + (_omit_note(left, "개는 원문 참조") or "전수 수록"), 18),
    }
    return data


def _build_c_grid(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """키값 6쌍 이상 / 2열 표 6행 이상 → tpl.c-grid — 상한 초과는 omitted 로 정직 계상.

    배치(열·행·폰트)는 렌더가 개수에서 정한다 — 조립기는 개수만 넘긴다.
    """
    payload = plan["grid"][1]
    cards_src = _grid_cards(payload) or []
    cap, label_max = _slot_cap("c-grid", "cards", "label")
    cap = cap or 9
    keep = cards_src[:cap]
    cards = []
    for c in keep:
        card: dict = {"label": _clip(c["label"], label_max or 16)}
        desc = c.get("desc", "").strip()
        if desc:
            card["desc"] = _clip(desc, 36)
        cards.append(card)
    data: dict = {
        "kicker": "목록",
        "title": _clip(payload.get("caption") or f"{norm['title']} — 항목", 26),
        "cards": cards,
        "frame": _frame(norm, idx),
    }
    left = len(cards_src) - len(keep)
    if left > 0:
        data["omitted"] = left
    data["note"] = {
        "pre": _clip(f"{'키값' if payload.get('kind') == 'pairs' else '표'} ", 18),
        "strong": _clip(f"{len(cards_src)}건", 12),
        "post": _clip(" 중 " + (f"{len(keep)}건 수록" if left else "전수 수록"), 18),
    }
    return data


# ── 세로 숏폼 빌더 4종 (short-9x16 — vtpl.hook/stack/metric/cta) ──────────


def _v_frame(norm: dict, idx: int, plan: dict) -> dict:
    """세로 프레임 — 가로(_frame)와 달리 idx/total 이 정수(스키마 계약)."""
    return {
        "brand": _clip(norm["title"], 20),
        "idx": idx,
        "total": int(plan.get("_skeleton_len") or 5),
    }


def _build_vhook(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """vtpl.hook — 제목 3분할 후킹 문구 + 핵심 키워드 블록 + 구간 예고 레일."""
    tags = norm.get("tags", [])
    word = _clip(tags[0] if tags else norm["title"].split()[0], 8) or "핵심"
    caption = _first_text(
        fragments, f"{norm.get('report_date', '')} 보고서", type="claim", widget="rich_text"
    )
    return {
        "kicker": "핵심 브리핑",
        "line": _split_title(norm["title"], 10, 10, 10),
        "focus": {
            "label": _clip(norm["title"], 14),
            "word": word,
            "caption": _clip(caption, 22),
        },
        "hint": {"text": "핵심만 빠르게 정리합니다",
                 "beats": ["문제", "해법", "근거", "행동"]},
    }


def _build_vstack(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """vtpl.stack — 논지 적층 카드. 첫 호출은 problem, 두 번째부터 solution.

    short-9x16 skeleton 은 problem→solution 순서로 vtpl.stack 을 두 번 쓴다 —
    호출 순서가 곧 역할 순서다 (빌더는 역할명을 받지 않는다).
    """
    seq = int(plan.get("_stack_seq", 0))
    plan["_stack_seq"] = seq + 1
    tone = "problem" if seq == 0 else "solution"
    purpose = _texts(fragments, 6, type="claim", section="purpose")
    claims = _texts(fragments, 6, type="claim")
    pool = purpose or claims or ["보고 내용 정리가 필요합니다"]

    if tone == "problem":
        kicker, title = "문제", _clip(pool[0], 22)
        cards = [{"title": _clip(t, 30)} for t in pool[:4]]
        conclusion = _clip(pool[-1], 20)
    else:
        kicker = "해법"
        title = _clip(norm.get("ai_summary") or norm["title"], 22)
        flow_nodes = (plan["flow"][1].get("nodes") or []) if plan.get("flow") else []
        items = [{"label": n.get("label", ""), "desc": n.get("note", "")}
                 for n in flow_nodes if n.get("label")]
        if not items:
            items = [{"label": t} for t in _texts(fragments, 4, type="evidence")]
        cards = [
            {"title": _clip(it["label"], 30),
             **({"desc": _clip(it["desc"], 20)} if it.get("desc") else {})}
            for it in items[:4]
        ]
        conclusion = _clip(norm.get("ai_summary") or norm["title"], 20)
    while len(cards) < 3:
        n = len(cards) + 1
        cards.append({"title": f"논지 {n} — 보고서 참조"})
    return {
        "kicker": kicker,
        "title": title,
        "tone": tone,
        "cards": cards[:4],
        "conclusion": conclusion,
        "frame": _v_frame(norm, idx, plan),
    }


def _build_vmetric(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """vtpl.metric — 단일 계열의 최댓값 하나로 승부 (없으면 보고서 규모 폴백)."""
    data: dict = {"kicker": "핵심 수치", "title": _clip(norm["title"], 22)}
    if plan.get("series") is not None:
        payload = plan["series"][1]
        entries = [e for e in payload.get("series") or [] if e.get("value") is not None]
        top = max(entries, key=lambda e: float(e["value"]))
        data.update(
            {
                "label": _clip(top.get("label") or payload.get("caption") or "대표 수치", 20),
                "value": _clip(_fmt_num(float(top["value"])), 7),
                "evidence": _clip(payload.get("caption")
                                  or _first_text(fragments, "보고서 수치 근거", type="metric"), 34),
            }
        )
        unit = _clip(str(payload.get("unit") or ""), 2)
        if unit:
            data["unit"] = unit
    else:
        data.update(
            {
                "label": "추출된 근거 조각",
                "value": str(len(fragments)),
                "unit": "건",
                "evidence": _clip(norm.get("ai_summary") or norm["title"], 34),
            }
        )
    data["source"] = _clip(f"{norm['title']} {norm.get('report_date', '')}".strip(), 26)
    data["frame"] = _v_frame(norm, idx, plan)
    return data


def _build_vcta(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """vtpl.cta — 제목 3분할 헤드라인 + 태그 기반 진입점 필 1~3개."""
    tags = [t for t in norm.get("tags", []) if str(t).strip()]
    entries = [
        {"text": _clip(t, 16), "kind": "primary" if i == 0 else "secondary"}
        for i, t in enumerate(tags[:3])
    ] or [{"text": "보고서 전문 확인", "kind": "primary"}]
    return {
        "kicker": "다음 행동",
        "headline": _split_title(norm["title"], 10, 10, 10),
        "sub": _clip(norm.get("ai_summary") or "자세한 내용은 원문에서 확인하십시오", 38),
        "entries": entries,
        "footnote": _clip(f"원문: {norm['title']}", 26),
    }


# ── 문서형 조립 (읽는 자료 — doc-cover/toc/section/body/summary) ──────────
#
# 영상은 조각을 skeleton 7역할에 배치한다 — 씬 수가 골격 길이로 **고정**된다.
# 문서형은 반대다. 원 보고서의 페이지가 곧 섹션이고, 페이지 안의 heading 이 소절
# 경계이며, 소절의 구조 블록(표·수치·도식)이 본문 슬라이드 1장을 연다. 즉
# **슬라이드 수를 보고서 분량이 정한다** — cover → toc → (section → body×1~3)×페이지 → summary.
#
# 배치 논리도 반대다. 영상은 표·수치가 7역할의 좁은 슬롯 하나를 두고 **경쟁**해
# 대부분이 화면에 못 올랐지만(§8 도달률), 문서형은 근거 payload 마다 본문 슬라이드가
# 생기므로 경쟁이 없다. 슬롯 용량(표 3열×5행 등)은 코드가 아니라 doc-body schema.json 이
# 정한다 — 여기서는 maxItems/maxLength 를 읽어 쓴다(_cap/_lim).

DOC_TEMPLATE_SHORTS = ("doc-cover", "doc-toc", "doc-section", "doc-body", "doc-summary")
_DOC_SHORTS = frozenset(DOC_TEMPLATE_SHORTS)

# 페이지당 본문 슬라이드 상한 — 근거가 더 많으면 잘라내고 생략 건수를 화면에 밝힌다
DOC_MAX_BODIES_PER_SECTION = 3
# ScenarioDoc.scenes 상한(50). 넘칠 것 같으면 페이지당 본문 수부터 줄인다.
_DOC_MAX_SLIDES = 50


def _doc_schema(short: str) -> dict:
    """문서형 템플릿 schema.json — 못 읽으면 빈 dict (용량은 코드 기본값으로 떨어진다)."""
    root = str(resolve_modules_root())
    key = (root, short)
    schema = _SCHEMA_CACHE.get(key)
    if schema is None:
        try:
            schema = _load_schema(f"tpl.{short}", Path(root))
        except Exception:  # noqa: BLE001 — 용량 조회 실패가 조립을 막지 않는다
            schema = {}
        _SCHEMA_CACHE[key] = schema
    return schema


def _deref(root: dict, node: dict) -> dict:
    """로컬 $ref("#/$defs/side") 한 단계 해석 — 정의를 따로 둔 스키마도 상한을 읽히게 한다.

    l-ba 처럼 좌·우가 같은 정의를 참조하는 스키마에서 이게 없으면 조회가 조용히 빈
    노드를 돌려주고 조립기가 코드 기본값으로 떨어진다(= 스키마가 정본이 아니게 된다).
    """
    ref = node.get("$ref") if isinstance(node, dict) else None
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return node
    cur: Any = root
    for seg in ref[2:].split("/"):
        cur = (cur or {}).get(seg) or {}
    return cur or node


def _node(short: str, *path: str) -> dict:
    """스키마 노드 조회 — "[]" 는 items 로 내려간다 (evidence.table.rows 처럼 중첩된 슬롯용)."""
    schema = _doc_schema(short)
    node = schema
    for seg in path:
        node = (node.get("items") or {}) if seg == "[]" \
            else ((node.get("properties") or {}).get(seg) or {})
        node = _deref(schema, node)
    return node


def _cap(short: str, *path: str, default: int) -> int:
    v = _node(short, *path).get("maxItems")
    return int(v) if isinstance(v, int) else default


def _floor(short: str, *path: str, default: int) -> int:
    v = _node(short, *path).get("minItems")
    return int(v) if isinstance(v, int) else default


def _lim(short: str, *path: str, default: int) -> int:
    v = _node(short, *path).get("maxLength")
    return int(v) if isinstance(v, int) else default


def _line(text: object, limit: int) -> str:
    """공백을 하나로 접고 자른다 — 원문 마크다운의 줄바꿈이 슬라이드 문안에 새지 않게."""
    return _clip(" ".join(str(text).split()), limit)


def _doc_footer(norm: dict, right: str = "") -> dict:
    """꼬리말 — 좌: 문서명, 우: 날짜·배포 구분 (doc-toc/section/body/summary 공용)."""
    return {"left": _line(norm.get("title", ""), _lim("doc-body", "footer", "left", default=40)),
            "right": _line(right or norm.get("report_date", ""),
                           _lim("doc-body", "footer", "right", default=14))}


def _doc_pageno(idx: int, total: int) -> dict:
    return {"no": str(idx)[:4], "total": str(total)[:4]}


# ── 근거 슬롯 (구조 payload → doc-body.evidence: table | chart | image) ───
#
# tpl.doc-body 계약은 근거 종류를 3종으로 못박았고(kind 와 블록이 어긋나면 검증 실패)
# 표는 3열×5행, 막대는 5개가 상한이다. 그래서 흐름도·계층·키값·이정표는 전부 **표로
# 환원**된다 — 형태는 잃지만 원문 규모(N열×M행 / N단계 중 5)는 source 줄에 남긴다.


def _ev_table_caps() -> tuple[int, int, int, int, int]:
    """표 근거 슬롯 용량 — (열 상한, 행 상한, 머리행 자수, 셀 자수, 행 하한)."""
    return (
        _cap("doc-body", "evidence", "table", "headers", default=3),
        _cap("doc-body", "evidence", "table", "rows", default=5),
        _lim("doc-body", "evidence", "table", "headers", "[]", default=6),
        _lim("doc-body", "evidence", "table", "rows", "[]", "cells", "[]", default=10),
        _floor("doc-body", "evidence", "table", "rows", default=2),
    )


def _ev_table(headers: list[str], rows: list[list[str]], *, source: str = "") -> dict | None:
    """(머리행, 행 목록) → evidence(table). 행은 첫·끝 표본, 초과 규모는 source 에 명시."""
    h_cap, r_cap, h_max, c_max, r_min = _ev_table_caps()
    heads = [h for h in headers[:h_cap] if str(h).strip()]
    if len(heads) < 2 or len(rows) < r_min:
        return None
    keep = _span_indices(len(rows), r_cap)
    out_rows = [
        {"cells": [_line(rows[i][j] if j < len(rows[i]) else "", c_max) or "-"
                   for j in range(len(heads))]}
        for i in keep
    ]
    ev: dict = {
        "kind": "table",
        "table": {"headers": [_line(h, h_max) for h in heads], "rows": out_rows},
    }
    if source:
        ev["source"] = _line(source, _lim("doc-body", "evidence", "source", default=30))
    return ev


def _ev_from_table(payload: dict) -> dict | None:
    """표 payload → evidence(table). 3열 상한이라 첫 열(분류 축) + 뒤 2열을 남긴다."""
    cols_p = payload.get("columns") or []
    rows_p = payload.get("rows") or []
    if len(cols_p) < 2 or len(rows_p) < 2:
        return None
    h_cap, r_cap = _ev_table_caps()[:2]
    cols = cols_p[:h_cap]
    rows = [[str(r.get(c["key"], "") or "") for c in cols] for r in rows_p]
    return _ev_table(
        [str(c.get("label") or c["key"]) for c in cols], rows,
        source=f"원문 {len(cols_p)}열×{len(rows_p)}행 중 {len(cols)}열×{min(len(rows_p), r_cap)}행",
    )


def _ev_from_series(payload: dict) -> dict | None:
    """단일 계열 series → evidence(chart). 값 극단 + 중앙값이 남는다(앞 N개 절단 금지)."""
    entries = [e for e in payload.get("series") or [] if e.get("value") is not None]
    cap = _cap("doc-body", "evidence", "chart", "bars", default=5)
    if len(entries) < _floor("doc-body", "evidence", "chart", "bars", default=2):
        return None
    lab_max = _lim("doc-body", "evidence", "chart", "bars", "[]", "label", default=14)
    keep = _extreme_indices([e.get("value") for e in entries], cap)
    bars = [
        {"label": _line(entries[i].get("label") or f"항목 {i + 1}", lab_max),
         "value": max(float(entries[i]["value"]), 0.0)}   # 0 기준선 강제
        for i in keep
    ]
    bars[max(range(len(bars)), key=lambda i: bars[i]["value"])]["emphasis"] = True
    chart: dict = {"bars": bars}
    unit = _line(payload.get("unit") or "", _lim("doc-body", "evidence", "chart", "unit", default=3))
    if unit:
        chart["unit"] = unit
    ev: dict = {"kind": "chart", "chart": chart}
    omitted = len(entries) - len(keep)
    if omitted:
        ev["source"] = _line(f"{len(entries)}계열 중 {len(keep)} · {_omit_note(omitted, '계열 원문')}",
                             _lim("doc-body", "evidence", "source", default=30))
    return ev


def _ev_from_multi(payload: dict) -> dict | None:
    """다계열 series → evidence(table) — 계열×항목 격자. 빠진 값을 0 으로 지어내지 않는다."""
    grid = _multi_grid(payload)
    if grid is None:
        return None
    groups, cats, val = grid
    h_cap = _ev_table_caps()[0]
    keep_c = cats[: max(h_cap - 1, 1)]
    rows = [[g] + [_fmt_num(val[(g, c)]) for c in keep_c] for g in groups]
    return _ev_table(
        ["계열", *keep_c], rows,
        source=f"{len(groups)}계열×{len(cats)}항목 중 {min(len(groups), 5)}×{len(keep_c)}",
    )


def _ev_from_graph(payload: dict) -> dict | None:
    """흐름도·계층 → evidence(table). 도식의 형태는 잃지만 단계·계층은 행으로 남는다."""
    nodes = payload.get("nodes") or []
    if len(nodes) < 2:
        return None
    r_cap = _ev_table_caps()[1]
    flow = payload.get("shape") == "flow"
    keep = _span_indices(len(nodes), r_cap) if flow else _level_indices(nodes, r_cap)
    if flow:
        has_note = any(nodes[i].get("note") for i in keep)
        headers = ["#", "단계", "비고"] if has_note else ["#", "단계"]
        rows = [[str(i + 1), str(nodes[i].get("label") or ""), str(nodes[i].get("note") or "")][
            : len(headers)] for i in keep]
        kindword = "단계"
    else:
        headers = ["항목", "층"]
        rows = [[str(nodes[i].get("label") or ""), f"L{int(nodes[i].get('level') or 0)}"]
                for i in keep]
        kindword = "노드"
    return _ev_table(headers, rows,
                     source=f"{len(nodes)}{kindword} 중 {len(keep)} · 원문 도식 참조")


def _ev_from_pairs(payload: dict) -> dict | None:
    """key_value → evidence(table) — 항목·값 2열. 한 줄로 뭉개지 않는다."""
    pairs = payload.get("pairs") or []
    if len(pairs) < 2:
        return None
    r_cap = _ev_table_caps()[1]
    keep = _span_indices(len(pairs), r_cap)
    rows = [[str(pairs[i].get("label") or pairs[i].get("key") or ""),
             str(pairs[i].get("value", ""))] for i in keep]
    return _ev_table(["항목", "값"], rows,
                     source=f"{len(pairs)}쌍 중 {len(keep)} · 원문 전수 수록")


def _ev_from_timeline(payload: dict) -> dict | None:
    """milestone → evidence(table) — 일자·항목·상태 3열."""
    ms = payload.get("milestones") or []
    if len(ms) < 2:
        return None
    r_cap = _ev_table_caps()[1]
    keep = _span_indices(len(ms), r_cap)
    rows = []
    for i in keep:
        raw = str(ms[i].get("status") or "").strip()
        rows.append([str(ms[i].get("date") or "-"), str(ms[i].get("label") or ""),
                     _STATUS_MAP.get(raw, _STATUS_MAP.get(raw.lower(), "planned"))])
    return _ev_table(["일자", "항목", "상태"], rows,
                     source=f"{len(ms)}이정표 중 {len(keep)}")


# kind 별 기본 캡션 — 원문에 caption 이 없을 때만 쓴다 (evidence.caption 은 필수 필드)
_EV_CAPTION = {"table": "표", "series": "수치", "graph": "도식", "pairs": "주요 항목",
               "timeline": "일정"}

_EV_BUILDERS = {
    "table": _ev_from_table,
    "graph": _ev_from_graph,
    "pairs": _ev_from_pairs,
    "timeline": _ev_from_timeline,
}


def _doc_evidence(payload: dict) -> dict | None:
    """구조 payload → doc-body.evidence (받을 형태가 없으면 None)."""
    kind = str(payload.get("kind") or "")
    if kind == "series":
        ev = _ev_from_series(payload) if _single_series(payload) else _ev_from_multi(payload)
    else:
        ev = (_EV_BUILDERS.get(kind) or (lambda _p: None))(payload)
    if ev is None:
        return None
    ev["caption"] = _line(payload.get("caption") or _EV_CAPTION.get(kind, "근거"),
                          _lim("doc-body", "evidence", "caption", default=26))
    return ev


def _outline_evidence(sec: dict) -> dict:
    """구조 payload 가 없는 페이지의 근거 슬롯 — 그 페이지의 소절 구성.

    doc-body 는 evidence 를 **필수**로 요구한다. 없는 데이터를 지어내는 대신, 원문의
    소절 이름과 항목 수라는 실재하는 사실을 싣는다(수치 조작이 아니라 목차 발췌다).
    """
    rows = [[h, f"{n}건"] for h, n in sec["outline"]]
    ev = _ev_table(["소절", "항목"], rows, source=f"원문 {sec['page']}")
    if ev is None:      # 소절이 2개 미만 — 페이지 자체를 한 행으로
        ev = _ev_table(
            ["구분", "값"],
            [["출처", sec["name"]], ["항목", f"{sec['items']}건"]],
            source=f"원문 {sec['page']}",
        )
    if ev is not None:
        ev["caption"] = _line(f"{sec['name']} 구성",
                              _lim("doc-body", "evidence", "caption", default=26))
    return ev or {"kind": "table", "caption": "구성",
                  "table": {"headers": ["구분", "값"],
                            "rows": [{"cells": ["출처", "원문"]},
                                     {"cells": ["항목", "-"]}]}}


# ── 보고서 구조 → 슬라이드 계획 ─────────────────────────────────────────


def _frags_by_block(fragments: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for f in fragments:
        bid = (f.get("source") or {}).get("block_id")
        if bid:
            out.setdefault(str(bid), []).append(f)
    return out


def _page_segments(page: dict) -> list[dict]:
    """페이지 블록을 heading 경계로 소절 분해한다 — 원 보고서의 목차 구조가 곧 슬라이드 경계."""
    segs: list[dict] = []
    cur: dict = {"heading": "", "blocks": []}
    for b in page.get("blocks", []) or []:
        if b.get("type") == "heading":
            if cur["heading"] or cur["blocks"]:
                segs.append(cur)
            cur = {"heading": str((b.get("content") or {}).get("text") or "").strip(),
                   "blocks": []}
        else:
            cur["blocks"].append(b)
    if cur["heading"] or cur["blocks"]:
        segs.append(cur)
    return segs


def _segment_content(seg: dict, by_block: dict[str, list[dict]]) -> tuple[str, list[str], tuple | None]:
    """소절 → (리드문, 본문 텍스트 목록, 근거 조각). 구조 블록은 근거 슬롯으로 간다."""
    lead = ""
    texts: list[str] = []
    evidence: tuple[dict, dict] | None = None
    for b in seg["blocks"]:
        fl = by_block.get(str(b.get("id") or ""), [])
        st = next((f for f in fl if isinstance(f.get("structured"), dict)), None)
        if st is not None:
            if evidence is None:
                evidence = (st, st["structured"])
            continue
        for f in fl:
            t = " ".join(str(f.get("text") or "").split())
            if not t:
                continue
            if not lead and f.get("widget") == "rich_text":
                lead = t
                continue
            texts.append(t)
    return lead, texts, evidence


def _doc_units(segs: list[dict], by_block: dict[str, list[dict]], *,
               max_bodies: int) -> tuple[list[dict], int]:
    """소절 목록 → 본문 슬라이드 단위. **근거 하나가 슬라이드 하나**를 연다.

    doc-body 는 evidence 가 필수라 근거 없는 소절은 독립 슬라이드가 될 수 없다. 그런
    소절의 문안은 앞 슬라이드(없으면 첫 슬라이드)의 불릿으로 흡수된다 — 버리지 않는다.
    페이지에 근거가 아예 없으면 소절 구성 표를 근거로 세운 슬라이드 1장을 만든다.
    """
    units: list[dict] = []
    pending: list[str] = []
    dropped_ev = 0
    for seg in segs:
        lead, texts, ev = _segment_content(seg, by_block)
        head = str(seg.get("heading") or "").strip()
        chunk = ([f"{head} — {lead}"] if head and lead else
                 [head] if head else [lead] if lead else [])
        chunk += texts
        if ev is not None and len(units) < max_bodies:
            units.append({"title": head, "lead": lead, "texts": texts, "evidence": ev})
            continue
        if ev is not None:
            dropped_ev += 1
        if units:
            units[-1]["texts"].extend(chunk)
        else:
            pending.extend(chunk)
    if pending:
        if units:
            units[0]["texts"] = pending + units[0]["texts"]
        else:
            units.append({"title": "", "lead": "", "texts": pending, "evidence": None})
    for j, u in enumerate(units, 1):
        u["n"] = j
    return units, dropped_ev


def _doc_plan(norm: dict, fragments: list[dict], *,
              max_bodies: int = DOC_MAX_BODIES_PER_SECTION) -> dict:
    """보고서 → 문서형 슬라이드 계획 (조립기와 slot_fit_report 의 공용 1차 정본)."""
    by_block = _frags_by_block(fragments)
    sections: list[dict] = []
    placed: dict[str, str] = {}
    for pi, page in enumerate(norm.get("pages", []) or [], 1):
        segs = _page_segments(page)
        units, drop_e = _doc_units(segs, by_block, max_bodies=max_bodies)
        if not units:
            continue
        for u in units:
            if u["evidence"] is not None:
                placed[str(u["evidence"][0].get("frag_id"))] = "doc-body.evidence"
        outline = []
        for s in segs:
            if not s["heading"]:
                continue
            _l, ts, ev = _segment_content(s, by_block)
            outline.append((_clean_page_name(s["heading"]), len(ts) + (1 if ev else 0)))
        sections.append(
            {
                "n": len(sections) + 1,
                "page": str(page.get("name") or f"페이지 {pi}"),
                "name": _clean_page_name(str(page.get("name") or "")) or f"섹션 {pi}",
                "lead": next((u["lead"] for u in units if u["lead"]), ""),
                "headings": [s["heading"] for s in segs if s["heading"]],
                "outline": outline,
                "items": sum(len(u["texts"]) for u in units),
                "units": units,
                "evidence_omitted": drop_e,
            }
        )
    return {"sections": sections, "placed": placed, "evidence_total": len(placed),
            "sections_omitted": 0, "total": 0, "max_bodies": max_bodies}


def _doc_slides(doc: dict, by_short: dict[str, tuple[str, str]]) -> list[tuple[str, str, dict]]:
    """계획 → (템플릿 짧은 이름, content 키, 슬롯) 슬라이드 목록. 슬라이드 번호도 여기서 확정."""
    slides: list[tuple[str, str, dict]] = []
    if "doc-cover" in by_short:
        slides.append(("doc-cover", "cover", {}))
    if "doc-toc" in by_short:
        slides.append(("doc-toc", "toc", {}))
    for sec in doc["sections"]:
        if "doc-section" in by_short:
            slides.append(("doc-section", f"section-{sec['n']}", {"section": sec}))
        for u in sec["units"]:
            slides.append(("doc-body", f"body-{sec['n']}-{u['n']}",
                           {"section": sec, "unit": u}))
    if "doc-summary" in by_short:
        slides.append(("doc-summary", "summary", {}))
    seen: set[int] = set()
    for i, (_short, _key, slot) in enumerate(slides, 1):
        sec = slot.get("section")
        if sec is not None and id(sec) not in seen:
            seen.add(id(sec))
            sec["slide_no"] = i
        unit = slot.get("unit")
        if unit is not None:
            unit["slide_no"] = i
    doc["total"] = len(slides)
    return slides


# ── 문서형 씬 빌더 5종 ──────────────────────────────────────────────────


def _build_doc_cover(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """tpl.doc-cover — 읽는 자료의 표지는 서지사항이 본체다 (제목·날짜·분류·구성)."""
    doc = plan["_doc"]
    tags = [str(t) for t in norm.get("tags", []) if str(t).strip()]
    subtitle = (norm.get("ai_summary")
                or _first_text(fragments, "", type="claim", widget="rich_text")
                or norm["title"])
    lab = _lim("doc-cover", "meta", "[]", "label", default=8)
    val = _lim("doc-cover", "meta", "[]", "value", default=26)
    meta = [
        {"label": _line("작성일", lab), "value": _line(norm.get("report_date") or "-", val)},
        {"label": _line("분류", lab), "value": _line(" · ".join(tags) or "일반", val)},
        {"label": _line("구성", lab),
         "value": _line(f"{len(doc['sections'])}개 절 · {doc['total']}장", val)},
        {"label": _line("근거", lab), "value": _line(f"표·수치 {doc['evidence_total']}건", val)},
    ][: _cap("doc-cover", "meta", default=5)]
    data: dict = {
        "title": _line(norm["title"], _lim("doc-cover", "title", default=34)),
        "subtitle": _line(subtitle, _lim("doc-cover", "subtitle", default=54)),
        "meta": meta,
        "footer": _line(f"원문 {len(norm.get('pages', []) or [])}페이지 · 내부 참고용",
                        _lim("doc-cover", "footer", default=44)),
    }
    if tags:
        data["badge"] = _line(tags[0], _lim("doc-cover", "badge", default=12))
    return data


def _build_doc_toc(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """tpl.doc-toc — 목차는 섹션 목록에서 자동 유도한다 (원 보고서 페이지 이름이 정본).

    항목 하한(4)을 섹션 수가 못 채우면 본문 슬라이드 단위로 내려가 group(섹션명)으로 묶는다.
    """
    doc = plan["_doc"]
    cap = _cap("doc-toc", "items", default=10)
    low = _floor("doc-toc", "items", default=4)
    txt = _lim("doc-toc", "items", "[]", "text", default=26)
    note_max = _lim("doc-toc", "items", "[]", "note", default=18)
    grp = _lim("doc-toc", "items", "[]", "group", default=12)

    def sec_items() -> list[dict]:
        out = []
        for s in doc["sections"]:
            it: dict = {"no": f"{s['n']}."[:4], "text": _line(s["name"], txt),
                        "page": str(s.get("slide_no") or 1)[:4]}
            if s["lead"]:
                it["note"] = _line(s["lead"], note_max)
            out.append(it)
        return out

    def body_items() -> list[dict]:
        out = []
        for s in doc["sections"]:
            for u in s["units"]:
                out.append({
                    "no": f"{s['n']}.{u['n']}"[:4],
                    "group": _line(s["name"], grp),
                    "text": _line(u["title"] or s["name"], txt),
                    "page": str(u.get("slide_no") or 1)[:4],
                })
        return out

    items = sec_items()
    if len(items) < low:
        items = body_items() or items
    while len(items) < low:      # 극소형 보고서 — 실재하는 슬라이드로만 채운다
        items.append({"no": f"{len(items) + 1}.", "text": _line("요약", txt),
                      "page": str(doc["total"])[:4]})
    left = max(len(items) - cap, 0) + doc.get("sections_omitted", 0)
    note = f"전 {doc['total']}장 · 섹션 {len(doc['sections'])}개"
    if left:
        note += f" · {_omit_note(left, '개 항목은 원문 참조')}"
    return {
        "kicker": _line("목차", _lim("doc-toc", "kicker", default=12)),
        "title": _line("목차", _lim("doc-toc", "title", default=16)),
        "items": items[:cap],
        "note": _line(note, _lim("doc-toc", "note", default=46)),
        "page": _doc_pageno(idx, doc["total"]),
        "footer": _doc_footer(norm),
    }


def _build_doc_section(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """tpl.doc-section — 섹션 간지. 원 보고서 페이지 이름 + 그 페이지의 소제목 예고 칩."""
    doc = plan["_doc"]
    sec = plan["_slot"]["section"]
    cap = _cap("doc-section", "points", default=4)
    chip = _lim("doc-section", "points", "[]", default=16)
    points = [_line(_clean_page_name(h), chip) for h in sec["headings"][:cap]]
    data: dict = {
        "no": f"{sec['n']:02d}"[:_lim("doc-section", "no", default=3)],
        "name": _line(sec["name"], _lim("doc-section", "name", default=20)),
        "lead": _line(sec["lead"] or f"{sec['name']} — 원문 {sec['page']}",
                      _lim("doc-section", "lead", default=54)),
        "footer": _doc_footer(norm),
    }
    if points:
        data["points"] = points
    return data


def _build_doc_body(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """tpl.doc-body — 좌측 불릿 + 우측 근거 슬롯(표·막대). 근거 1개가 슬라이드 1장을 연다."""
    doc = plan["_doc"]
    sec, u = plan["_slot"]["section"], plan["_slot"]["unit"]
    b_cap = _cap("doc-body", "bullets", default=6)
    b_low = _floor("doc-body", "bullets", default=3)
    b_max = _lim("doc-body", "bullets", "[]", "text", default=42)

    texts = [t for t in u["texts"] if t.strip()]
    bullets = [{"text": _line(t, b_max)} for t in texts[:b_cap]]
    # 불릿 하한 — 원문에서 더 끌어온다(리드문 → 소절 제목 → 출처 표기 순, 창작 금지)
    filler = ([u["lead"]] if u["lead"] else []) + [
        _clean_page_name(h) for h in sec["headings"]] + [sec["lead"], f"원문 {sec['page']} 참조"]
    seen = {b["text"] for b in bullets}
    for t in filler:
        if len(bullets) >= b_low:
            break
        line = _line(t, b_max)
        if line and line not in seen:
            seen.add(line)
            bullets.append({"text": line})

    ev = _doc_evidence(u["evidence"][1]) if u["evidence"] is not None else _outline_evidence(sec)
    data: dict = {
        "kicker": _line(sec["name"], _lim("doc-body", "kicker", default=12)),
        "title": _line(_clean_page_name(u["title"]) or (
            f"{sec['name']} ({u['n']}/{len(sec['units'])})" if len(sec["units"]) > 1
            else sec["name"]), _lim("doc-body", "title", default=30)),
        "bullets": bullets[:b_cap],
        "evidence": ev,
        "page": _doc_pageno(idx, doc["total"]),
        "footer": _doc_footer(norm),
    }
    if u["lead"]:
        data["lead"] = _line(u["lead"], _lim("doc-body", "lead", default=42))
    over = max(len(texts) - len(data["bullets"]), 0)
    tail = _omit_note(over, "항목은 원문 참조")
    if u["n"] == len(sec["units"]) and sec["evidence_omitted"]:
        tail = " · ".join(x for x in (tail, _omit_note(sec["evidence_omitted"], "건 근거는 원문 참조")) if x)
    if tail:
        data["takeaway"] = _line(tail, _lim("doc-body", "takeaway", default=44))
    return data


def _build_doc_summary(norm: dict, fragments: list[dict], idx: int, plan: dict) -> dict:
    """tpl.doc-summary — ai_summary 가 있으면 그것, 없으면 상위 claim 조각으로 결론을 세운다."""
    doc = plan["_doc"]
    cap = _cap("doc-summary", "points", default=5)
    low = _floor("doc-summary", "points", default=3)
    t_max = _lim("doc-summary", "points", "[]", "text", default=40)
    n_max = _lim("doc-summary", "points", "[]", "note", default=24)

    # note 는 '보조 근거 한 줄'이다 — 잘린 뒷말이 아니라 **그 결론이 어느 절에서 왔는지**를 적는다.
    # 뽑는 순서는 **절마다 하나씩 먼저** — confidence 만으로 고르면 5줄이 1절에서만 나온다.
    ranked = sorted(_frags(fragments, type="claim"),
                    key=lambda f: -float(f.get("confidence") or 0.0))
    per_page: dict[str, dict] = {}
    for f in ranked:
        per_page.setdefault(str((f.get("source") or {}).get("page") or ""), f)
    order = [per_page[k] for k in per_page] + ranked

    picked: list[tuple[str, str]] = []
    seen: set[str] = set()
    summary = norm.get("ai_summary") or ""
    if summary.strip():
        picked.append((summary, ""))
        seen.add(summary[:12])
    for f in order:
        if len(picked) >= cap:
            break
        t = " ".join(str(f.get("text") or "").split())
        if not t or t[:12] in seen:
            continue
        seen.add(t[:12])
        picked.append((t, _clean_page_name(str((f.get("source") or {}).get("page") or ""))))
    while len(picked) < low:
        picked.append((f"원문 {norm['title']} 참조", ""))
    points = [
        {"text": _line(t, t_max), **({"note": _line(src, n_max)} if src else {})}
        for t, src in picked[:cap]
    ]

    a_cap = _cap("doc-summary", "actions", default=4)
    a_max = _lim("doc-summary", "actions", "[]", "text", default=34)
    missing = sum(s["evidence_omitted"] for s in doc["sections"])
    actions = [{"text": _line(f"원문 {len(norm.get('pages', []) or [])}페이지 전문 확인", a_max)}]
    if missing:
        actions.append({"text": _line(f"미수록 근거 {missing}건 원문 대조", a_max)})
    if doc.get("sections_omitted"):
        actions.append({"text": _line(f"미수록 {doc['sections_omitted']}개 절 확인", a_max)})
    return {
        "kicker": _line("요약", _lim("doc-summary", "kicker", default=12)),
        "title": _line(f"{norm['title']} 요약", _lim("doc-summary", "title", default=26)),
        "points": points,
        "actions_title": _line("다음 단계", _lim("doc-summary", "actions_title", default=10)),
        "actions": actions[:a_cap],
        "note": _line(f"원문: {norm['title']} ({norm.get('report_date', '')})",
                      _lim("doc-summary", "note", default=40)),
        "page": _doc_pageno(idx, doc["total"]),
        "footer": _doc_footer(norm),
    }


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
    "d-matrix": _build_d_matrix,
    "d-media": _build_d_media,
    "d-multi": _build_d_multi,
    "c-ratio": _build_c_ratio,
    "c-trend": _build_c_trend,
    "c-branch": _build_c_branch,
    "c-grid": _build_c_grid,
    "l-split": _build_l_split,
    "l-list": _build_l_list,
    "l-tree": _build_l_tree,
    "l-quote": _build_l_quote,
    "l-kpi": _build_l_kpi,
    "l-quad": _build_l_quad,
    "l-ba": _build_l_ba,
    "l-mix": _build_l_mix,
    "hook": _build_vhook,
    "stack": _build_vstack,
    "metric": _build_vmetric,
    "cta": _build_vcta,
    "doc-cover": _build_doc_cover,
    "doc-toc": _build_doc_toc,
    "doc-section": _build_doc_section,
    "doc-body": _build_doc_body,
    "doc-summary": _build_doc_summary,
}

# 구조 payload 와 **정확 대응**하는 템플릿 (§3). structured_templates=True 일 때
# 역할 1순위가 정확 대응을 갖지 않으면 이 조건을 만족하는 대체 템플릿이 자리를 가져간다.
_EXACT_MATCH = {
    "process": lambda c: c["flow"] is not None,
    "concept": lambda c: c["graph"] is not None,
    "timeline": lambda c: c["timeline"] is not None,
    "compare": lambda c: c["compare_table"] is not None,
    "dataviz": lambda c: c["series"] is not None,
    # d-* 3종 — 포맷 template_pool 에 선언된 역할에서만 발동한다 (옵트인 경계).
    # 현행 formats/wide-16x9/format.yaml 풀에는 아직 없어 기본 경로 동작은 불변이다.
    "d-matrix": lambda c: c.get("matrix_table") is not None,
    "d-media": lambda c: bool(c.get("media")),
    "d-multi": lambda c: c.get("multi") is not None,
    # 커버리지 1순위 4종 — 같은 옵트인 경계. 판별 신호는 _ratio_series/_trend_series/
    # _branch_graph/_grid_cards 가 정본이고 그 근거는 §"커버리지 1순위 4종 판별" 주석에 있다.
    "c-ratio": lambda c: c.get("ratio") is not None,
    "c-trend": lambda c: c.get("trend") is not None,
    "c-branch": lambda c: c.get("branch") is not None,
    "c-grid": lambda c: c.get("grid") is not None,
    # 발표 레이아웃 l-* — 같은 옵트인 경계. l-quote 는 정확 대응이 없다(문장은 편집
    # 판단이지 payload 가 아니다) — 풀 1순위로 명시했을 때만 자리를 지킨다.
    "l-tree": lambda c: c.get("tree") is not None,
    "l-kpi": lambda c: c.get("kpi") is not None,
    "l-quad": lambda c: c.get("quadrant") is not None,
    "l-mix": lambda c: c.get("mix_table") is not None and c.get("series") is not None,
    "l-split": lambda c: bool(c.get("split_tables")) or c.get("series") is not None,
    "l-list": lambda c: c.get("list_pairs") is not None,
    "l-ba": lambda c: c.get("compare_table") is not None,
}


# 대응 payload 없이는 화면을 만들 수 없는 템플릿 — 텍스트 폴백 경로가 없다.
# 이런 템플릿이 역할의 1순위인데 payload 가 없으면 자리를 폴백 가능한 템플릿에 비켜준다
# (기존 포맷의 1순위는 전부 폴백 경로를 가진 템플릿이라 동작이 달라지지 않는다).
_NEEDS_PAYLOAD = frozenset({
    "dataviz", "timeline", "compare", "d-matrix", "d-media", "d-multi",
    "l-tree", "l-kpi", "l-quad", "l-mix", "l-ba",
    "c-ratio", "c-trend", "c-branch", "c-grid",
})


def _pick_module(spec: FormatSpec, role: str, cand: dict, structured_templates: bool) -> str:
    """역할 → 템플릿 모듈 id. 기본은 풀 1순위(기존 동작 그대로)."""
    ids = spec.template_pool[role]
    if structured_templates and not _EXACT_MATCH.get(tpl_short(ids[0]), lambda _c: False)(cand):
        for tid in ids[1:]:
            if _EXACT_MATCH.get(tpl_short(tid), lambda _c: False)(cand):
                return tid
        if tpl_short(ids[0]) in _NEEDS_PAYLOAD:
            for tid in ids[1:]:
                if tpl_short(tid) not in _NEEDS_PAYLOAD:
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


def is_doc_format(spec: FormatSpec) -> bool:
    """문서형 포맷인가 — skeleton 전 역할의 1순위 템플릿이 doc-* 인 포맷.

    `all` 인 것이 중요하다. 영상 포맷이 풀에 doc-* 를 하나 얹었다고 조립 경로가
    통째로 바뀌면 안 된다 — 문서형 골격은 씬 수 계산 규칙 자체가 다르기 때문이다.
    """
    return all(tpl_short(spec.primary_tpl(r)) in _DOC_SHORTS for r in spec.skeleton)


def _doc_by_short(spec: FormatSpec) -> dict[str, tuple[str, str]]:
    """포맷 골격 → {템플릿 짧은 이름: (역할, 모듈 id)} (골격 등장 순서)."""
    out: dict[str, tuple[str, str]] = {}
    for role in spec.skeleton:
        for tid in spec.template_pool[role]:
            short = tpl_short(tid)
            if short in _DOC_SHORTS:
                out.setdefault(short, (role, tid))
                break
    return out


def assemble_doc_scenario(
    norm: dict,
    fragments: list[dict],
    format: str,
) -> ScenarioDoc:
    """문서형(읽는 자료) 골격 조립 — cover → toc → (section → body×1~3)×페이지 → summary.

    영상 조립(`assemble_demo_scenario`)과 달리 **씬 수를 보고서가 정한다**. 원 보고서의
    페이지가 섹션이 되고, 페이지 안의 heading 이 소절 경계가 되며, 소절의 블록이 본문
    슬라이드가 된다. 구조 payload(표·수치·다이어그램)는 요약하지 않고 doc-body 의 근거
    슬롯에 그대로 실린다 — 문서형은 밀도가 높아 영상 슬롯보다 훨씬 많이 담는다.

    길이는 템플릿 nat_default 합이 포맷 허용대 안이면 그대로 두고, 벗어나면 target 으로
    균일 스케일한다(슬라이드 수가 가변이라 항상 target 에 맞추면 장수마다 씬이 짧아진다).
    """
    modules_root = resolve_modules_root()
    spec = load_format(format, modules_root=modules_root)
    if not is_doc_format(spec):
        raise NotImplementedError(
            f"포맷 {spec.id!r} 는 문서형이 아니다 — skeleton 역할의 1순위 템플릿이 "
            f"{sorted(_DOC_SHORTS)} 여야 문서형 골격으로 조립한다"
        )
    return _assemble_doc(norm, fragments, spec, modules_root)


def _assemble_doc(
    norm: dict, fragments: list[dict], spec: FormatSpec, modules_root: Path
) -> ScenarioDoc:
    by_short = _doc_by_short(spec)
    missing = [s for s in ("doc-cover", "doc-body") if s not in by_short]
    if missing:
        raise NotImplementedError(
            f"포맷 {spec.id!r} 문서형 골격에 필수 템플릿 {missing} 이 없다 — "
            f"template_pool 에 tpl.doc-cover · tpl.doc-body 를 선언하라"
        )

    # 슬라이드 수 상한(50) 방어 — 페이지당 본문 수부터 줄이고, 그래도 넘으면 뒤 섹션을 뺀다
    max_bodies = DOC_MAX_BODIES_PER_SECTION
    doc = _doc_plan(norm, fragments, max_bodies=max_bodies)
    slides = _doc_slides(doc, by_short)
    while len(slides) > _DOC_MAX_SLIDES and max_bodies > 1:
        max_bodies -= 1
        doc = _doc_plan(norm, fragments, max_bodies=max_bodies)
        slides = _doc_slides(doc, by_short)
    while len(slides) > _DOC_MAX_SLIDES and doc["sections"]:
        dropped = doc["sections"].pop()
        doc["sections_omitted"] += 1
        for u in dropped["units"]:
            if u["evidence"] is not None:
                doc["placed"].pop(str(u["evidence"][0].get("frag_id")), None)
        doc["evidence_total"] = len(doc["placed"])
        slides = _doc_slides(doc, by_short)

    modules = {s: _load_module(tid, modules_root) for s, (_r, tid) in by_short.items()}
    schemas = {s: _load_schema(tid, modules_root) for s, (_r, tid) in by_short.items()}
    nats = [float(modules[s].get("nat_default", 10)) for s, _k, _slot in slides]
    total_nat = round(sum(nats), 3)
    durs = (list(nats) if spec.duration.min <= total_nat <= spec.duration.max
            else _stretch_to_target(nats, spec.duration.target))

    plan: dict = {"_doc": doc}
    content: dict[str, dict] = {}
    scenes: list[dict] = []
    used: set[str] = set()
    for idx, ((short, key, slot), dur, nat) in enumerate(zip(slides, durs, nats), 1):
        plan["_slot"] = slot
        schema = schemas[short]
        data = _conform(_BUILDERS[short](norm, fragments, idx, plan), schema)
        content[key] = data
        base = str(modules[short].get("scene_name_default", short))
        name, k = base, 1
        while name in used:
            k += 1
            name = f"{base} {k}"
        used.add(name)
        major = str(modules[short].get("version", "1.0.0")).split(".")[0]
        scenes.append(
            {
                "name": name,
                "dur": dur,
                "nat": nat,
                "tpl": f"{short}@{major}",
                "stills": [round(max(dur - 1.0, dur * 0.5), 2)],
                "data_ref": f"content.{key}",
                "narration": (
                    narration_from_x_read(data, schema, dur=dur, rate=spec.narration.rate)
                    if spec.narration.enabled else ""
                ),
                "transition": "cut",
            }
        )
    return ScenarioDoc.model_validate(
        {
            "version": "1.0",
            "format": spec.id,
            "meta": {
                "core_message": norm.get("ai_summary") or norm["title"],
                "audience": "보고서 독자",
                "duration_sec": round(sum(s["dur"] for s in scenes), 3),
                "tone": "정보 전달",
                "meeting_id": None,
                "source_report_id": None,
            },
            "content": content,
            "scenes": scenes,
            "tokens_theme": spec.theme,
            "playback": {"mode": "times", "count": 1},
        }
    )


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
    않을 때 같은 역할 풀의 대체 템플릿(tpl.compare · tpl.dataviz · tpl.timeline ·
    tpl.d-matrix · tpl.d-media · tpl.d-multi)이 자리를 가져간다. d-* 는 포맷
    template_pool 에 선언된 역할에서만 발동한다(옵트인 경계 — 현행 wide-16x9 풀 미선언).
    기본값 False 는 기존 7종 골격을 그대로 유지한다 — 씬 구성이 바뀌면
    이미 만들어진 시나리오·빌드 산출물과 어긋나므로 명시적 선택으로만 켠다.
    """
    modules_root = resolve_modules_root()
    spec = load_format(format, modules_root=modules_root)
    if is_doc_format(spec):   # 문서형은 씬 수를 보고서가 정한다 — 골격 고정 경로를 타지 않는다
        return _assemble_doc(norm, fragments, spec, modules_root)
    cand = _candidates(fragments, norm)

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
    plan["_skeleton_len"] = len(spec.skeleton)  # 세로 프레임 total (vtpl frame 은 정수 계약)

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

    def cap_at(name: str, cap: int, lmax: int | None = None) -> None:
        """중첩 슬롯(l-mix.table.rows 처럼 properties 두 겹 아래)의 용량 설정."""
        nonlocal slot, capacity, label_max
        slot, capacity, label_max = name, cap, lmax

    if kind == "graph":
        nodes = payload.get("nodes") or []
        labels = [str(n.get("label", "")) for n in nodes]
        items = len(nodes)
        branch = _branch_graph(payload) if "c-branch" in shorts else None
        if branch is not None:
            cap_of("c-branch", "nodes", "label")
            carried = len(branch[0])
            strategy = "level"
            reason = "분기 그래프 → c-branch.nodes (레벨당 3개·판단 노드 보존)"
        elif payload.get("shape") == "tree" and "l-tree" in shorts \
                and _tree_levels(payload) is not None:
            kept, _e, _o = _tree_pick(payload)
            cap_at("l-tree.nodes", _cap("l-tree", "nodes", default=13),
                   _lim("l-tree", "nodes", "[]", "label", default=22))
            carried = len(kept)
            strategy, reason = "level", "tree → l-tree.nodes (루트 1·중간 ≤4·리프 ≤8, 위계 보존)"
        elif payload.get("shape") == "flow" and "process" in shorts:
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
        ratio = _ratio_series(payload) if "c-ratio" in shorts else None
        trend = _trend_series(payload) if "c-trend" in shorts else None
        grid = _multi_grid(payload) if not _single_series(payload) else None
        if ratio is not None:
            cap_of("c-ratio", "series", "label")
            # 상한 초과분은 잘리지 않고 total 로 넘어가 '기타(미표기)' 조각이 된다
            carried = items
            strategy, reason = "ratio", "비율형 → c-ratio.series (초과분은 기타로 자동 편입)"
        elif trend is not None:
            lines, points, _v = trend
            cap_of("c-trend", "points", "label")
            labels, items = points, len(points)
            carried = len(_span_indices(items, capacity))
            strategy, reason = "span", f"시계열 → c-trend (계열 {len(lines)} · 시점 표본)"
        elif "l-quad" in shorts and _quad_points(payload):
            pts = _quad_points(payload)
            cap_at("l-quad.items", _cap("l-quad", "items", default=10),
                   _lim("l-quad", "items", "[]", "label", default=18))
            labels, items = [str(p.get("label", "")) for p in pts], len(pts)
            carried = len(_extreme_indices([p.get("value") for p in pts], capacity))
            strategy, reason = "extreme", "좌표 계열 → l-quad.items (0~1 정규화 배치)"
        elif "l-kpi" in shorts and _kpi_metrics(payload):
            cap_at("l-kpi.metrics", _cap("l-kpi", "metrics", default=6),
                   _lim("l-kpi", "metrics", "[]", "label", default=14))
            carried = len(_extreme_indices([e.get("value") for e in entries], capacity))
            strategy, reason = "extreme", "다지표 → l-kpi.metrics (타일 4~6, 3칸 상한 해소)"
        elif "l-mix" in shorts and _single_series(payload) and cand.get("mix_table") is not None:
            cap_at("l-mix.chart.bars", _cap("l-mix", "chart", "bars", default=4),
                   _lim("l-mix", "chart", "bars", "[]", "label", default=18))
            carried = len(_extreme_indices([e.get("value") for e in entries], capacity))
            strategy, reason = "extreme", "단일 계열 → l-mix.chart.bars (표와 같은 화면)"
        elif grid is not None and "d-multi" in shorts:
            groups, cats, _ = grid
            cap_of("d-multi", "series", "name")
            g_cap = capacity or 4
            c_cap = _slot_cap("d-multi", "categories", "label")[0] or 7
            labels = groups
            carried = min(len(groups), g_cap) * min(len(cats), c_cap)
            capacity = g_cap * c_cap        # 계열×항목 격자 용량 (포인트 기준)
            strategy, reason = "grid", "다계열 → d-multi.series (공통 축 격자)"
        elif not _single_series(payload):
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
            elif "l-ba" in shorts:
                cap_at("l-ba.items", _cap("l-ba", "before", "items", default=5),
                       _lim("l-ba", "before", "items", "[]", "text", default=22))
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
        elif "l-mix" in shorts and cand.get("mix_table") is not None \
                and payload is cand["mix_table"][1]:
            keep_cols, _r = _mix_table(payload)
            cap_at("l-mix.table.rows", _cap("l-mix", "table", "rows", default=5),
                   _lim("l-mix", "table", "rows", "[]", "label", default=13))
            carried = len(_span_indices(items, capacity))
            strategy = "span"
            reason = "수치·코드값 표 → l-mix.table (막대와 같은 화면)" + (
                f" · 열 {len(cols) - len(keep_cols)}개는 원문 참조"
                if len(cols) > len(keep_cols) else ""
            )
        elif "d-matrix" in shorts and len(cols) >= 3 and len(rows) >= 2:
            cap_of("d-matrix", "rows", "label")
            carried = len(_span_indices(items, capacity))
            col_cap = _slot_cap("d-matrix", "columns", "label")[0] or 8
            strategy = "span"
            reason = "격자 → d-matrix.rows (첫·끝 표본, 외 N행 표기)" + (
                f" · 열 {len(cols) - col_cap}개 초과는 원문 참조" if len(cols) > col_cap else ""
            )
        elif "c-grid" in shorts and _grid_cards(payload):
            cap_of("c-grid", "cards", "label")
            carried = min(items, capacity or 9)
            strategy = "head"
            reason = "2열 표 → c-grid.cards (d-matrix 하한 3열 미달분, 초과는 외 N건)"
        elif "l-split" in shorts and _split_table(payload):
            col_cap = _cap("l-split", "visual", "table", "columns", default=3)
            cap_at("l-split.visual.table.rows",
                   _cap("l-split", "visual", "table", "rows", default=6),
                   _lim("l-split", "visual", "table", "rows", "[]", "label", default=20))
            carried = len(_span_indices(items, capacity))
            strategy = "span"
            reason = "표 → l-split.visual.table (좌 설명의 근거 간이표)" + (
                f" · 열 {len(cols) - col_cap}개는 원문 참조" if len(cols) > col_cap else ""
            )
        else:
            reason = (f"{len(cols)}열 격자 — 격자 표 씬이 이번 조립 템플릿에 없다 "
                      f"(3열+ 는 d-matrix · 2열 6행+ 는 c-grid)")

    elif kind == "pairs":
        pairs = payload.get("pairs") or []
        labels, items = [str(p.get("label", "")) for p in pairs], len(pairs)
        if "l-list" in shorts and cand.get("list_pairs") is not None \
                and payload is cand["list_pairs"][1]:
            cap_at("l-list.rows", _cap("l-list", "rows", default=8),
                   _lim("l-list", "rows", "[]", "title", default=30))
            carried = min(items, capacity)
            strategy, reason = "head", "키값 → l-list.rows (쌍 하나가 행 하나 — 뭉개지 않는다)"
        elif "c-grid" in shorts and _grid_cards(payload):
            cap_of("c-grid", "cards", "label")
            carried = min(items, capacity or 9)
            strategy = "head"
            reason = "키값 6쌍+ → c-grid.cards (쌍 하나가 카드 하나 — 뭉개지 않는다)"
        elif cand.get("pairs") and "proof" in shorts:
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
        # 미디어는 fragments 가 아니라 자산 채널(collect_media)로 흐른다 — d-media 가 소비
        reason = ("자산 채널 소관 — d-media 가 collect_media 로 받는다 (§9 #2)"
                  if "d-media" in shorts
                  else "이미지/영상 슬롯이 조립 템플릿에 없다 (§9 #2 — d-media 미편성)")
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


def _doc_fit_record(frag: dict, payload: dict) -> dict:
    """문서형 근거 슬롯의 수용 판정 — slot_fit_report 의 행 1건 (doc-body.evidence 기준).

    영상(`_fit_record`)과 판정 축이 다르다. 영상은 7역할의 슬롯 하나를 여러 payload 가
    **경쟁**해 같은 종류 중 하나만 실렸지만, 문서형은 payload 마다 본문 슬라이드가 열리므로
    경쟁이 없다 — 미배치는 페이지당 본문 상한(3장)에 걸린 것뿐이다. 대신 슬롯 자체는 좁다
    (표 3열×5행 · 막대 5개) — 도달(fit)과 배치(placed)를 따로 읽어야 하는 이유다.
    """
    kind = payload.get("kind")
    row_cap = _cap("doc-body", "evidence", "table", "rows", default=5)
    col_cap = _cap("doc-body", "evidence", "table", "headers", default=3)
    cell_max = _lim("doc-body", "evidence", "table", "rows", "[]", "cells", "[]", default=10)
    slot = capacity = label_max = None
    labels: list[str] = []
    items = carried = 0
    strategy = reason = ""

    def table_slot(kept: int, why: str, *, strat: str = "span") -> None:
        nonlocal slot, capacity, label_max, carried, strategy, reason
        slot, capacity, label_max = "doc-body.evidence.table.rows", row_cap, cell_max
        carried, strategy, reason = kept, strat, why

    if kind == "table":
        rows, cols = payload.get("rows") or [], payload.get("columns") or []
        key0 = cols[0]["key"] if cols else ""
        labels, items = [str(r.get(key0, "")) for r in rows], len(rows)
        table_slot(len(_span_indices(items, row_cap)),
                   "표 → doc-body.evidence.table (첫·끝 표본)" + (
            f" · 열 {len(cols) - col_cap}개는 원문 참조" if len(cols) > col_cap else ""))
    elif kind == "series":
        entries = payload.get("series") or []
        labels, items = [str(e.get("label", "")) for e in entries], len(entries)
        if _single_series(payload):
            slot = "doc-body.evidence.chart.bars"
            capacity = _cap("doc-body", "evidence", "chart", "bars", default=5)
            label_max = _lim("doc-body", "evidence", "chart", "bars", "[]", "label", default=14)
            carried = len(_extreme_indices([e.get("value") for e in entries], capacity))
            strategy, reason = "extreme", "단일 계열 → evidence.chart.bars (값 극단+중앙값)"
        elif _multi_grid(payload) is not None:
            groups, cats, _ = _multi_grid(payload)
            labels, items = groups, len(groups) * len(cats)
            keep_c = max(col_cap - 1, 1)
            slot, label_max = "doc-body.evidence.table.rows", cell_max
            capacity = row_cap * keep_c
            carried = min(len(groups), row_cap) * min(len(cats), keep_c)
            strategy, reason = "grid", "다계열 → evidence.table (계열×항목 격자)"
        else:
            reason = "분포형(values/n) — 문서형 근거 슬롯도 값 목록을 지어내지 않는다 (§9 #7)"
    elif kind == "graph":
        nodes = payload.get("nodes") or []
        labels, items = [str(n.get("label", "")) for n in nodes], len(nodes)
        flow = payload.get("shape") == "flow"
        table_slot(
            len(_span_indices(items, row_cap) if flow else _level_indices(nodes, row_cap)),
            ("흐름도 → evidence.table (#·단계·비고, 순서 표본)" if flow
             else "tree/network → evidence.table (항목·층, 얕은 레벨 우선 · 엣지 손실)"),
            strat="span" if flow else "level",
        )
    elif kind == "pairs":
        pairs = payload.get("pairs") or []
        labels, items = [str(p.get("label", "")) for p in pairs], len(pairs)
        table_slot(len(_span_indices(items, row_cap)),
                   "키값 → evidence.table (항목·값 2열, 한 줄 뭉개기 없음)")
    elif kind == "timeline":
        ms = payload.get("milestones") or []
        labels, items = [str(m.get("label", "")) for m in ms], len(ms)
        table_slot(len(_span_indices(items, row_cap)),
                   "milestone → evidence.table (일자·항목·상태 3열)")
    elif kind == "media":
        reason = "자산 채널 소관 — evidence.image 배선은 미구현 (§9 #2)"
    else:
        reason = f"미지 kind={kind}"

    trimmed = [x for x in labels if label_max and len(x) > label_max]
    if slot is None:
        fit = "none"
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
            "detail": f"{slot} 은 {carried}칸 — {items}항목을 온전히 보이려면 본문 슬라이드 {n}장으로 나눠라",
        }
    return rec


def _tally_rows(rows: list[dict]) -> dict:
    tally = {k: 0 for k in ("ok", "trim", "summarized", "split", "none")}
    for r in rows:
        tally[r["fit"]] += 1
    return tally


def _doc_slot_fit_report(norm: dict, fragments: list[dict], spec: FormatSpec) -> dict:
    """문서형 도달률 — 판정 축은 doc-body.evidence, placed 는 본문 슬라이드 배치 여부."""
    doc = _doc_plan(norm, fragments)
    placed = doc["placed"]
    rows = [_doc_fit_record(f, p) for f, p in _structured(fragments)]
    for r in rows:
        r["placed"] = r["frag_id"] in placed
        r["placed_slot"] = placed.get(r["frag_id"])
    tally = _tally_rows(rows)
    total = len(rows)
    reached = total - tally["none"]
    return {
        "format": spec.id,
        "structured_templates": False,
        "templates": sorted(_doc_by_short(spec)),
        "structured_blocks": total,
        "tally": tally,
        "reach_pct": round(100 * reached / total, 1) if total else 0.0,
        "placed_pct": round(100 * sum(1 for r in rows if r["placed"]) / total, 1) if total else 0.0,
        "strict_reach_pct": (
            round(100 * (tally["ok"] + tally["trim"]) / total, 1) if total else 0.0
        ),
        "split_hints": [r["split_hint"] | {"frag_id": r["frag_id"], "widget": r["widget"]}
                        for r in rows if "split_hint" in r],
        "sections": len(doc["sections"]),
        "bodies": sum(len(s["units"]) for s in doc["sections"]),
        "rows": rows,
    }


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
    if is_doc_format(spec):
        return _doc_slot_fit_report(norm, fragments, spec)
    cand = _candidates(fragments, norm)
    shorts = {tpl_short(_pick_module(spec, role, cand, structured_templates))
              for role in spec.skeleton}
    plan = _assign(cand, shorts)
    owner = plan["owner"]

    rows = [_fit_record(f, p, cand, shorts) for f, p in _structured(fragments)]
    for r in rows:
        r["placed"] = r["frag_id"] in owner
        r["placed_slot"] = owner.get(r["frag_id"])

    tally = _tally_rows(rows)
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
