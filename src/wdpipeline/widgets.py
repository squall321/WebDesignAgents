# 위젯 content/props 를 씬 템플릿이 데이터로 소비할 구조 payload 로 변환하는 어댑터 (ReportArchive 38종 전수 커버리지 추적 포함)
"""ReportArchive 위젯 → 구조 payload 어댑터.

스키마 단일 소스는 `ReportArchive/backend/app/widgets/registry.py` 의
`WIDGET_REGISTRY`(38종) 이다. 이 모듈은 그 content/props 스키마를 읽어 만든
얇은 어댑터이며, 다음 6개 payload kind 로 정규화한다.

    table    — {kind, columns:[{key,label}], rows:[{col_key: str}], caption}
    graph    — {kind, nodes:[{id,label,level?}], edges:[{from,to,label?}], shape}
    series   — {kind, series:[{label,value?,...}], axis:{min,max}, chart_type}
    timeline — {kind, milestones:[{label,date,status}]}
    pairs    — {kind, pairs:[{key,label,value}]}
    media    — {kind, media_type, files:[{file_id,caption,alt}]}

중요 — 열 정의(table.columns)·비교 케이스(comparison.cases)·진행률 상한
(progress_bar.default_max) 등은 **content 가 아니라 props 에 저장**된다
(examples/reportarchive/report_sample.json 실물 확인). 그래서 이 어댑터는
블록 전체({type, props, content})를 받고 content → props 순으로 필드를 찾는다.
"""
from __future__ import annotations

from typing import Any

__all__ = [
    "GROUP_BY_TYPE",
    "KNOWN_TYPES",
    "STRUCTURED_TYPES",
    "collect_media",
    "coverage_stats",
    "extract_structured",
    "structured_summary",
]

# ── 위젯 38종 → 군(group) 분류 ────────────────────────────────────────────
# text 군은 payload 를 만들지 않는다(기존 텍스트 조각으로 충분). 나머지 6군은
# 구조 payload 를 만든다. registry.WIDGET_REGISTRY 키와 1:1 대응해야 한다.
GROUP_BY_TYPE: dict[str, str] = {
    # 표군
    "table": "table",
    "comparison": "table",
    "raci_matrix": "table",
    "fmea": "table",
    "record_table": "table",
    # 다이어그램군
    "flowchart": "graph",
    "tree": "graph",
    "network": "graph",
    "mind_map": "graph",
    "sankey": "graph",
    # 수치군
    "chart": "series",
    "scatter": "series",
    "scatter3d": "series",
    "heatmap": "series",
    "contour": "series",
    "treemap": "series",
    "packing": "series",
    "pie": "series",
    "waffle": "series",
    "box": "series",
    "density": "series",
    "radar": "series",
    "progress_bar": "series",
    "quadrant": "series",
    # 일정군
    "milestone": "timeline",
    # 키값군
    "key_value": "pairs",
    "record": "pairs",
    # 미디어군
    "image": "media",
    "video": "media",
    "attachment": "media",
    "cad_3d": "media",
    "doc_viewer": "media",
    "html_embed": "media",
    # 텍스트군 — 구조 없음
    "heading": "text",
    "rich_text": "text",
    "bulleted_list": "text",
    "card": "text",
    "equation": "text",
}

KNOWN_TYPES = frozenset(GROUP_BY_TYPE)
STRUCTURED_TYPES = frozenset(t for t, g in GROUP_BY_TYPE.items() if g != "text")

# 미디어 타입 → 한국어 표기 (요약 문자열용)
_MEDIA_LABEL = {
    "image": "이미지",
    "video": "영상",
    "attachment": "첨부",
    "cad_3d": "3D 모델",
    "doc_viewer": "문서",
    "html_embed": "임베드",
}

# 차트 타입 → 한국어 표기 (요약 문자열용)
_CHART_LABEL = {
    "progress_bar": "진행률",
    "bar": "막대",
    "line": "선",
    "pie": "파이",
    "doughnut": "도넛",
    "waffle": "와플",
    "radar": "레이더",
    "heatmap": "히트맵",
    "contour": "등고선",
    "treemap": "트리맵",
    "packing": "원형 패킹",
    "box": "박스플롯",
    "density": "밀도",
    "scatter": "산점도",
    "scatter3d": "3D 산점도",
    "quadrant": "2x2 매트릭스",
}

# FMEA 는 열이 고정 스키마다 (registry._fmea_content)
_FMEA_COLUMNS: list[tuple[str, str]] = [
    ("failure_mode", "고장 모드"),
    ("potential_effect", "영향"),
    ("potential_cause", "원인"),
    ("current_controls", "현 관리"),
    ("severity", "S"),
    ("occurrence", "O"),
    ("detection", "D"),
    ("rpn", "RPN"),
    ("recommended_action", "권고 조치"),
    ("responsible", "담당"),
    ("due_date", "기한"),
    ("status", "상태"),
]


# ── 저수준 유틸 ──────────────────────────────────────────────────────────


def _cp(block: dict) -> tuple[dict, dict]:
    """블록에서 (content, props) 를 딕셔너리로 꺼낸다 (None/비딕셔너리는 빈 dict)."""
    c = block.get("content")
    p = block.get("props")
    return (c if isinstance(c, dict) else {}), (p if isinstance(p, dict) else {})


def _pick(content: dict, props: dict, key: str, default: Any = None) -> Any:
    """content 우선, 없으면 props 에서 필드를 찾는다 (열 정의는 props 에 산다)."""
    v = content.get(key)
    if v is None:
        v = props.get(key)
    return default if v is None else v


def _s(v: Any) -> str:
    """셀/라벨 값을 문자열로 평탄화한다 (dict/list 는 대표값만)."""
    if v is None or isinstance(v, bool):
        return "" if v is None else ("예" if v else "아니오")
    if isinstance(v, (int, float)):
        return f"{v:g}" if isinstance(v, float) else str(v)
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        # 온톨로지 엔티티({name, entity_id}) · 이미지 셀({file_id, alt, caption})
        for k in ("name", "label", "alt", "caption", "text"):
            if v.get(k):
                return str(v[k]).strip()
        return ""
    if isinstance(v, list):
        return ", ".join(x for x in (_s(i) for i in v) if x)
    return str(v).strip()


def _num(v: Any) -> float | None:
    """숫자 또는 '12.3%' 같은 문자열을 float 로 (불가능하면 None)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(",", "").rstrip("%").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _caption(content: dict, props: dict) -> str:
    """캡션 — content.caption 우선, 없으면 props.label (편집기 라벨)."""
    return _s(content.get("caption")) or _s(props.get("label"))


def _cols(raw: Any) -> list[dict]:
    """[{key,label,...}] 선언을 {key,label} 만 남긴 열 목록으로."""
    out = []
    for x in raw if isinstance(raw, list) else []:
        if not isinstance(x, dict):
            continue
        key = _s(x.get("key"))
        if not key:
            continue
        out.append({"key": key, "label": _s(x.get("label")) or key})
    return out


def _rows(content: dict, key: str = "rows") -> list[dict]:
    return [r for r in (content.get(key) or []) if isinstance(r, dict)]


def _table(columns: list[dict], rows: list[dict], caption: str,
           files: list[dict] | None = None) -> dict | None:
    if not columns or not rows:
        return None
    payload: dict = {"kind": "table", "columns": columns, "rows": rows, "caption": caption}
    if files:
        payload["files"] = files
    return payload


# ── 표군 ─────────────────────────────────────────────────────────────────


def _x_table(block: dict) -> dict | None:
    c, p = _cp(block)
    columns = _cols(_pick(c, p, "columns"))
    rows_src = _rows(c)
    if not columns:
        # 열 선언이 없으면 행 키 합집합에서 유도한다 (등장 순서 보존)
        keys: list[str] = []
        for r in rows_src:
            for k in r:
                if k not in keys:
                    keys.append(str(k))
        columns = [{"key": k, "label": k} for k in keys]
    rows = [{col["key"]: _s(r.get(col["key"])) for col in columns} for r in rows_src]
    return _table(columns, rows, _caption(c, p))


def _x_comparison(block: dict) -> dict | None:
    c, p = _cp(block)
    columns = [{"key": "__aspect", "label": "항목"}] + _cols(_pick(c, p, "cases"))
    rows: list[dict] = []
    files: list[dict] = []
    for r in _rows(c):
        out = {"__aspect": _s(r.get("label")) or _s(r.get("key"))}
        values = r.get("values") if isinstance(r.get("values"), dict) else {}
        for col in columns[1:]:
            v = values.get(col["key"])
            if isinstance(v, dict) and v.get("file_id"):
                # 이미지 셀 — 텍스트는 alt/caption 으로 낮추고 file_id 는 files 로 승격
                files.append(
                    {
                        "file_id": _s(v.get("file_id")),
                        "caption": _s(v.get("caption")),
                        "alt": _s(v.get("alt")),
                    }
                )
            out[col["key"]] = _s(v)
        rows.append(out)
    return _table(columns, rows, _caption(c, p), files)


def _x_raci(block: dict) -> dict | None:
    c, p = _cp(block)
    roles = _cols(c.get("roles") if c.get("roles") else p.get("default_roles"))
    columns = [{"key": "__task", "label": "작업"}] + roles
    rows = []
    for r in _rows(c):
        out = {"__task": _s(r.get("label"))}
        assignments = r.get("assignments") if isinstance(r.get("assignments"), dict) else {}
        for col in roles:
            out[col["key"]] = _s(assignments.get(col["key"]))
        rows.append(out)
    return _table(columns, rows, _caption(c, p))


def _x_fmea(block: dict) -> dict | None:
    c, p = _cp(block)
    # content 는 저장 훅이 "fmea_items" 로 한 겹 감싼다 (registry._fmea_content 주석)
    inner = c.get("fmea_items") if isinstance(c.get("fmea_items"), dict) else c
    columns = [{"key": k, "label": lb} for k, lb in _FMEA_COLUMNS]
    rows = [{k: _s(r.get(k)) for k, _ in _FMEA_COLUMNS} for r in _rows(inner)]
    return _table(columns, rows, _caption(inner, p) or _caption(c, p))


def _x_record_table(block: dict) -> dict | None:
    c, p = _cp(block)
    rows_src = _rows(c)
    keys: list[str] = []
    for r in rows_src:
        props = r.get("properties") if isinstance(r.get("properties"), dict) else {}
        for k in props:
            if k not in keys:
                keys.append(str(k))
    columns = [{"key": "__name", "label": "이름"}] + [{"key": k, "label": k} for k in keys]
    rows = []
    for r in rows_src:
        props = r.get("properties") if isinstance(r.get("properties"), dict) else {}
        out = {"__name": _s(r.get("name"))}
        out.update({k: _s(props.get(k)) for k in keys})
        rows.append(out)
    return _table(columns, rows, _caption(c, p))


# ── 다이어그램군 ─────────────────────────────────────────────────────────


def _graph(nodes: list[dict], edges: list[dict], shape: str, caption: str,
           **extra: Any) -> dict | None:
    if not nodes:
        return None
    payload = {"kind": "graph", "nodes": nodes, "edges": edges,
               "shape": shape, "caption": caption}
    payload.update({k: v for k, v in extra.items() if v})
    return payload


def _parent_levels(nodes: list[dict], parent_of: dict[str, str | None]) -> None:
    """parent 체인 깊이를 level 로 채운다 (순환은 방문 집합으로 차단)."""
    for n in nodes:
        level, cur, seen = 0, parent_of.get(n["id"]), {n["id"]}
        while cur and cur not in seen and level < 64:
            seen.add(cur)
            level += 1
            cur = parent_of.get(cur)
        n["level"] = level


def _x_flowchart(block: dict) -> dict | None:
    c, p = _cp(block)
    nodes, edges = [], []
    for i, item in enumerate(c.get("items") or []):
        if not isinstance(item, dict):
            continue
        label = _s(item.get("label"))
        if not label:
            continue
        node = {"id": f"n{len(nodes) + 1}", "label": label, "level": len(nodes)}
        note = _s(item.get("description")) or _s(item.get("note"))
        if note:
            node["note"] = note
        nodes.append(node)
    for a, b in zip(nodes, nodes[1:]):
        edges.append({"from": a["id"], "to": b["id"]})
    return _graph(nodes, edges, "flow", _caption(c, p),
                  orientation=_s(_pick(c, p, "orientation")))


def _x_parent_rows(block: dict) -> dict | None:
    """tree · mind_map — rows[{label,parent,subtitle}] 의 parent 가 라벨을 가리킨다."""
    c, p = _cp(block)
    nodes: list[dict] = []
    used: set[str] = set()
    id_of: dict[str, str] = {}      # 라벨 → 최초 노드 id
    parent_label: dict[str, str] = {}
    for r in _rows(c):
        label = _s(r.get("label"))
        if not label:
            continue
        nid, n = label, 2
        while nid in used:
            nid, n = f"{label}#{n}", n + 1
        used.add(nid)
        id_of.setdefault(label, nid)
        node = {"id": nid, "label": label}
        sub = _s(r.get("subtitle"))
        if sub:
            node["note"] = sub
        nodes.append(node)
        par = _s(r.get("parent"))
        if par:
            parent_label[nid] = par
    parent_of = {nid: id_of.get(par) for nid, par in parent_label.items()}
    _parent_levels(nodes, parent_of)
    edges = [{"from": pid, "to": nid} for nid, pid in parent_of.items() if pid]
    return _graph(nodes, edges, "tree", _caption(c, p))


def _x_network(block: dict) -> dict | None:
    c, p = _cp(block)
    nodes = []
    for x in c.get("nodes") or []:
        if not isinstance(x, dict) or not _s(x.get("id")):
            continue
        node = {"id": _s(x["id"]), "label": _s(x.get("label")) or _s(x["id"])}
        if _s(x.get("group")):
            node["group"] = _s(x.get("group"))
        if _num(x.get("value")) is not None:
            node["value"] = _num(x.get("value"))
        nodes.append(node)
    edges = []
    for e in c.get("edges") or []:
        if not isinstance(e, dict):
            continue
        src, dst = _s(e.get("source")), _s(e.get("target"))
        if not src or not dst:
            continue
        edge = {"from": src, "to": dst}
        lb = _s(e.get("label"))
        if lb:
            edge["label"] = lb
        edges.append(edge)
    return _graph(nodes, edges, "network", _caption(c, p))


def _x_sankey(block: dict) -> dict | None:
    c, p = _cp(block)
    nodes, seen = [], set()
    for x in c.get("nodes") or []:
        label = _s(x.get("label")) if isinstance(x, dict) else _s(x)
        if not label or label in seen:
            continue
        seen.add(label)
        nodes.append({"id": label, "label": label})
    edges = []
    for link in c.get("links") or []:
        if not isinstance(link, dict):
            continue
        src, dst = _s(link.get("source")), _s(link.get("target"))
        if not src or not dst:
            continue
        edge = {"from": src, "to": dst}
        val = _num(link.get("value"))
        if val is not None:
            unit = _s(_pick(c, p, "unit"))
            edge["label"] = f"{val:g}{unit}"
            edge["value"] = val
        edges.append(edge)
    return _graph(nodes, edges, "network", _caption(c, p))


# ── 수치군 ───────────────────────────────────────────────────────────────


def _series(entries: list[dict], chart_type: str, caption: str,
            axis: dict | None = None, unit: str = "") -> dict | None:
    if not entries:
        return None
    payload: dict = {
        "kind": "series",
        "series": entries,
        "chart_type": chart_type,
        "caption": caption,
        "axis": axis or {},
    }
    if unit:
        payload["unit"] = unit
    return payload


def _axis(content: dict, props: dict, lo: str, hi: str) -> dict:
    out = {}
    for name, key in (("min", lo), ("max", hi)):
        v = _num(_pick(content, props, key))
        if v is not None:
            out[name] = v
    return out


def _x_progress_bar(block: dict) -> dict | None:
    c, p = _cp(block)
    unit = _s(_pick(c, p, "unit")) or "%"
    default_max = _num(_pick(c, p, "default_max"))
    entries = []
    for item in c.get("items") or []:
        if not isinstance(item, dict):
            continue
        label = _s(item.get("label"))
        if not label:
            continue
        e: dict = {"label": label, "value": _num(item.get("value")), "unit": unit}
        mx = _num(item.get("max"))
        if mx is None:
            mx = default_max
        if mx is not None:
            e["max"] = mx
        for k in ("note", "status"):
            if _s(item.get(k)):
                e[k] = _s(item.get(k))
        entries.append(e)
    axis = {"min": 0.0}
    if default_max is not None:
        axis["max"] = default_max
    return _series(entries, "progress_bar", _caption(c, p), axis, unit)


def _x_label_value_rows(block: dict, chart_type: str) -> dict | None:
    """pie · waffle · treemap · packing — rows[{label,value,parent?}]."""
    c, p = _cp(block)
    unit = _s(_pick(c, p, "unit"))
    entries = []
    for r in _rows(c):
        label = _s(r.get("label"))
        if not label:
            continue
        e: dict = {"label": label, "value": _num(r.get("value"))}
        if unit:
            e["unit"] = unit
        if _s(r.get("parent")):
            e["parent"] = _s(r.get("parent"))  # 계층(treemap/packing) 보존
        entries.append(e)
    ctype = _s(c.get("chart_type")) or chart_type
    return _series(entries, ctype, _caption(c, p), {}, unit)


def _numeric_columns(columns: list[dict], raw: Any, x_key: str) -> list[dict]:
    """columns 선언 중 x축을 뺀 수치 열만 (type 선언이 없으면 전부 후보)."""
    typed = {}
    for x in raw if isinstance(raw, list) else []:
        if isinstance(x, dict) and _s(x.get("key")):
            typed[_s(x["key"])] = _s(x.get("type"))
    out = []
    for col in columns:
        if col["key"] == x_key:
            continue
        if typed.get(col["key"], "number") == "number":
            out.append(col)
    return out


def _x_chart(block: dict) -> dict | None:
    c, p = _cp(block)
    raw_cols = _pick(c, p, "columns")
    columns = _cols(raw_cols)
    x_key = _s(_pick(c, p, "x_column_key")) or (columns[0]["key"] if columns else "")
    value_cols = _numeric_columns(columns, raw_cols, x_key)
    multi = len(value_cols) > 1
    entries = []
    for r in _rows(c):
        xlabel = _s(r.get(x_key))
        for col in value_cols:
            val = _num(r.get(col["key"]))
            if val is None:
                continue
            e: dict = {"label": xlabel or col["label"], "value": val}
            if multi:
                e["group"] = col["label"]
            entries.append(e)
    return _series(entries, _s(_pick(c, p, "chart_type")) or "bar",
                   _caption(c, p), _axis(c, p, "y_min", "y_max"))


def _x_scatter(block: dict) -> dict | None:
    c, p = _cp(block)
    entries = []
    rows = _rows(c)
    for sdef in c.get("series") or []:
        if not isinstance(sdef, dict):
            continue
        name = _s(sdef.get("label"))
        xk, yk, zk = _s(sdef.get("x_key")), _s(sdef.get("y_key")), _s(sdef.get("z_key"))
        for r in rows:
            y = _num(r.get(yk))
            if y is None:
                continue
            e: dict = {"label": name or _s(r.get(xk)), "value": y, "group": name}
            x = _num(r.get(xk))
            if x is not None:
                e["x"] = x
            z = _num(r.get(zk)) if zk else None
            if z is not None:
                e["z"] = z
            entries.append(e)
    return _series(entries, block.get("type") or "scatter",
                   _caption(c, p), _axis(c, p, "y_min", "y_max"))


def _x_matrix(block: dict) -> dict | None:
    """heatmap · contour — x_labels × y_labels 격자를 셀 단위 계열로 편다."""
    c, p = _cp(block)
    xs = [_s(x) for x in (c.get("x_labels") or [])]
    ys = [_s(y) for y in (c.get("y_labels") or [])]
    entries = []
    for yi, row in enumerate(c.get("matrix") or []):
        if not isinstance(row, list):
            continue
        for xi, cell in enumerate(row):
            val = _num(cell)
            if val is None:
                continue
            xl = xs[xi] if xi < len(xs) else str(xi)
            yl = ys[yi] if yi < len(ys) else str(yi)
            entries.append({"label": f"{yl} × {xl}", "value": val, "group": yl})
    if not entries:  # contour 의 long-form 모드 (rows: [{x,y,z}])
        for r in _rows(c):
            val = _num(r.get("z"))
            if val is None:
                continue
            entries.append({"label": f"{_s(r.get('y'))} × {_s(r.get('x'))}", "value": val})
    return _series(entries, block.get("type") or "heatmap",
                   _caption(c, p), _axis(c, p, "z_min", "z_max"))


def _x_radar(block: dict) -> dict | None:
    c, p = _cp(block)
    axes = [_s(a) for a in (c.get("axis_labels") or [])]
    defs = [d for d in (c.get("series") or []) if isinstance(d, dict)]
    values = c.get("values") or []
    multi = len(defs) > 1
    entries = []
    for si, sdef in enumerate(defs):
        name = _s(sdef.get("label")) or f"계열{si + 1}"
        row = values[si] if si < len(values) and isinstance(values[si], list) else []
        for ai, cell in enumerate(row):
            val = _num(cell)
            if val is None:
                continue
            axis_label = axes[ai] if ai < len(axes) else f"축{ai + 1}"
            e = {"label": f"{name} · {axis_label}" if multi else axis_label, "value": val}
            if multi:
                e["group"] = name
            entries.append(e)
    return _series(entries, "radar", _caption(c, p), _axis(c, p, "value_min", "value_max"))


def _x_distribution(block: dict) -> dict | None:
    """box · density — 그룹별 원시 분포. 통계 요약을 지어내지 않고 values 로 보존한다."""
    c, p = _cp(block)
    unit = _s(_pick(c, p, "unit"))
    buckets: dict[str, list[float]] = {}
    for g in c.get("groups") or []:  # density
        if not isinstance(g, dict):
            continue
        name = _s(g.get("name"))
        if not name:
            continue
        vals = [v for v in (_num(x) for x in (g.get("values") or [])) if v is not None]
        buckets.setdefault(name, []).extend(vals)
    for r in _rows(c):  # box (long-form)
        name = _s(r.get("group"))
        val = _num(r.get("value"))
        if name and val is not None:
            buckets.setdefault(name, []).append(val)
    entries = []
    for name, vals in buckets.items():
        e: dict = {"label": name, "group": name, "values": vals, "n": len(vals)}
        if unit:
            e["unit"] = unit
        entries.append(e)
    return _series(entries, block.get("type") or "box", _caption(c, p),
                   _axis(c, p, "y_min", "y_max"), unit)


def _x_quadrant(block: dict) -> dict | None:
    c, p = _cp(block)
    entries = []
    for it in c.get("plot_items") or []:
        if not isinstance(it, dict):
            continue
        y = _num(it.get("y"))
        e: dict = {"label": _s(it.get("label")) or _s(it.get("id")), "value": y}
        x = _num(it.get("x"))
        if x is not None:
            e["x"] = x
        if _s(it.get("group")):
            e["group"] = _s(it.get("group"))
        entries.append(e)
    for it in c.get("bucket_items") or []:
        if not isinstance(it, dict):
            continue
        entries.append(
            {
                "label": _s(it.get("text")) or _s(it.get("id")),
                "value": _num(it.get("weight")),
                "group": _s(it.get("quadrant")),
            }
        )
    # quadrant 축 범위는 [min, max] 2원소 배열이다 (props.y_range)
    yr = _pick(c, p, "y_range")
    axis = {}
    if isinstance(yr, list) and len(yr) == 2:
        axis = {"min": _num(yr[0]), "max": _num(yr[1])}
    return _series(entries, "quadrant", _caption(c, p), axis)


# ── 일정군 · 키값군 ──────────────────────────────────────────────────────


def _x_milestone(block: dict) -> dict | None:
    c, p = _cp(block)
    milestones = []
    for it in c.get("items") or []:
        if not isinstance(it, dict):
            continue
        label = _s(it.get("label"))
        if not label:
            continue
        m = {"label": label, "date": _s(it.get("date")), "status": _s(it.get("status"))}
        if _s(it.get("note")):
            m["note"] = _s(it.get("note"))
        milestones.append(m)
    if not milestones:
        return None
    payload: dict = {"kind": "timeline", "milestones": milestones, "caption": _caption(c, p)}
    rng = {k: _s(_pick(c, p, f"{k}_date")) for k in ("start", "end")}
    if any(rng.values()):
        payload["range"] = {k: v for k, v in rng.items() if v}
    return payload


def _x_key_value(block: dict) -> dict | None:
    c, p = _cp(block)
    pairs = []
    for it in _pick(c, p, "items") or []:
        if not isinstance(it, dict):
            continue
        key = _s(it.get("key"))
        if not key:
            continue
        pairs.append({"key": key, "label": _s(it.get("label")) or key, "value": _s(c.get(key))})
    if not pairs:
        return None
    return {"kind": "pairs", "pairs": pairs, "caption": _caption(c, p)}


def _x_record(block: dict) -> dict | None:
    c, p = _cp(block)
    props = c.get("properties") if isinstance(c.get("properties"), dict) else {}
    pairs = [{"key": str(k), "label": str(k), "value": _s(v)} for k, v in props.items()]
    if _s(c.get("name")):
        pairs.insert(0, {"key": "__name", "label": "이름", "value": _s(c.get("name"))})
    if not pairs:
        return None
    return {"kind": "pairs", "pairs": pairs, "caption": _caption(c, p)}


# ── 미디어군 ─────────────────────────────────────────────────────────────


def _x_media(block: dict) -> dict | None:
    c, p = _cp(block)
    mtype = _s(block.get("type"))
    caption = _caption(c, p)
    files: list[dict] = []
    for f in _pick(c, p, "files") or []:
        if not isinstance(f, dict) or not _s(f.get("file_id")):
            continue
        files.append(
            {
                "file_id": _s(f["file_id"]),
                "caption": _s(f.get("caption")) or caption,
                "alt": _s(f.get("alt")) or _s(f.get("filename")),
            }
        )
    # cad_3d · doc_viewer · html_embed 는 단일 file_id 를 content 최상위에 둔다.
    # 일부 실물/픽스처는 image 도 props.file_id 로 참조하므로 props 까지 훑는다.
    single = _s(_pick(c, p, "file_id"))
    if not files and single:
        files.append(
            {
                "file_id": single,
                "caption": caption or _s(c.get("title")),
                "alt": _s(_pick(c, p, "loaded_filename")) or _s(_pick(c, p, "filename")),
            }
        )
    if not files:
        return None
    return {"kind": "media", "media_type": mtype, "files": files, "caption": caption}


# ── 디스패치 ─────────────────────────────────────────────────────────────

_EXTRACTORS = {
    "table": _x_table,
    "comparison": _x_comparison,
    "raci_matrix": _x_raci,
    "fmea": _x_fmea,
    "record_table": _x_record_table,
    "flowchart": _x_flowchart,
    "tree": _x_parent_rows,
    "mind_map": _x_parent_rows,
    "network": _x_network,
    "sankey": _x_sankey,
    "progress_bar": _x_progress_bar,
    "pie": lambda b: _x_label_value_rows(b, "pie"),
    "waffle": lambda b: _x_label_value_rows(b, "waffle"),
    "treemap": lambda b: _x_label_value_rows(b, "treemap"),
    "packing": lambda b: _x_label_value_rows(b, "packing"),
    "chart": _x_chart,
    "scatter": _x_scatter,
    "scatter3d": _x_scatter,
    "heatmap": _x_matrix,
    "contour": _x_matrix,
    "radar": _x_radar,
    "box": _x_distribution,
    "density": _x_distribution,
    "quadrant": _x_quadrant,
    "milestone": _x_milestone,
    "key_value": _x_key_value,
    "record": _x_record,
    "image": _x_media,
    "video": _x_media,
    "attachment": _x_media,
    "cad_3d": _x_media,
    "doc_viewer": _x_media,
    "html_embed": _x_media,
}


def extract_structured(block: dict) -> dict | None:
    """블록({type, props, content}) → 구조 payload. 구조가 없거나 비면 None.

    텍스트군(heading/rich_text/bulleted_list/card/equation)과 미지 타입은 None 이다
    (미지 타입 추적은 coverage_stats 가 담당).
    """
    if not isinstance(block, dict):
        return None
    fn = _EXTRACTORS.get(str(block.get("type", "")))
    if fn is None:
        return None
    try:
        return fn(block)
    except (TypeError, ValueError, AttributeError, KeyError, IndexError):
        # 스키마를 벗어난 실물 데이터 하나가 파이프라인 전체를 막지 않는다
        return None


# ── 요약 문자열 (심의 브리핑 한 줄) ───────────────────────────────────────


def _fmt(v: Any, unit: str = "") -> str:
    n = _num(v)
    if n is None:
        return _s(v) or "-"
    return f"{n:g}{unit}"


def structured_summary(payload: dict | None) -> str:
    """payload → 심의 브리핑용 한 줄 요약. payload 가 없으면 빈 문자열."""
    if not isinstance(payload, dict):
        return ""
    kind = payload.get("kind")

    if kind == "table":
        cols = payload.get("columns") or []
        rows = payload.get("rows") or []
        heads = [c.get("label") or c.get("key") for c in cols[:4]]
        head = "/".join(h for h in heads if h)
        more = "…" if len(cols) > 4 else ""
        return f"표 {len(cols)}열×{len(rows)}행: {head}{more}" if head else \
            f"표 {len(cols)}열×{len(rows)}행"

    if kind == "graph":
        nodes = payload.get("nodes") or []
        edges = payload.get("edges") or []
        shape = payload.get("shape")
        if shape == "flow":
            return f"흐름도 {len(nodes)}노드 선형"
        if shape == "tree":
            depth = max((n.get("level", 0) for n in nodes), default=0) + 1
            return f"트리 {len(nodes)}노드 {depth}단"
        return f"네트워크 {len(nodes)}노드 {len(edges)}엣지"

    if kind == "series":
        entries = payload.get("series") or []
        ctype = payload.get("chart_type") or ""
        name = _CHART_LABEL.get(ctype, ctype or "수치")
        unit = payload.get("unit") or (entries[0].get("unit", "") if entries else "")
        vals = []
        for e in entries[:3]:
            if e.get("value") is not None:
                vals.append(_fmt(e.get("value"), unit))
            elif e.get("values"):
                vals.append(f"{e['label']} n={len(e['values'])}")
        tail = f": {'/'.join(vals)}" if vals else ""
        return f"{name} {len(entries)}계열{tail}"

    if kind == "timeline":
        ms = payload.get("milestones") or []
        dates = [m.get("date") for m in ms if m.get("date")]
        span = f": {dates[0]} ~ {dates[-1]}" if dates else ""
        return f"일정 {len(ms)}건{span}"

    if kind == "pairs":
        pairs = payload.get("pairs") or []
        head = "/".join(p.get("label") or p.get("key") for p in pairs[:4])
        more = "…" if len(pairs) > 4 else ""
        return f"키값 {len(pairs)}쌍: {head}{more}" if head else f"키값 {len(pairs)}쌍"

    if kind == "media":
        mtype = payload.get("media_type", "")
        return f"{_MEDIA_LABEL.get(mtype, mtype or '자산')} {len(payload.get('files') or [])}건"

    return ""


# ── 미디어 자산 문맥 ─────────────────────────────────────────────────────


def collect_media(norm: dict) -> list[dict]:
    """미디어 위젯의 파일 자산을 **블록 문맥과 함께** 모은다.

    ingest 의 `_collect_file_ids` 는 file_id 를 평평한 집합으로 모으므로 어느 블록·
    어느 페이지에서 쓰였는지가 사라진다(`norm["assets"]` 에는 file_id/local_path 뿐).
    씬에 이미지를 배치하려면 캡션·alt·출처 블록이 필요해서 여기서 되살린다.
    해결 경로·크기 메타는 `norm["assets_meta"]`(wdpipeline.assets.resolve_assets 산출)
    레코드를 file_id 로 조인해 `asset` 키에 그대로 붙인다.

    반환 항목: {file_id, media_type, page, block_id, section, caption, alt, asset}
    asset 이 None 이면 그 file_id 는 아직 해결되지 않은 것이다(렌더 스킵 대상).
    """
    meta_by_id: dict[str, dict] = {}
    for rec in norm.get("assets_meta") or norm.get("assets") or []:
        if isinstance(rec, dict) and rec.get("file_id"):
            meta_by_id[str(rec["file_id"])] = rec

    out: list[dict] = []
    for page in norm.get("pages", []):
        pname = page.get("name", "")
        for block in page.get("blocks", []):
            payload = extract_structured(block)
            # media 군 외에 comparison 의 이미지 셀도 files 를 싣는다 (_x_comparison)
            if not payload or not payload.get("files"):
                continue
            for f in payload.get("files", []):
                fid = _s(f.get("file_id"))
                if not fid:
                    continue
                out.append(
                    {
                        "file_id": fid,
                        "media_type": payload.get("media_type") or "image",
                        "page": pname,
                        "block_id": block.get("id"),
                        "section": block.get("section"),
                        "caption": f.get("caption") or payload.get("caption", ""),
                        "alt": f.get("alt", ""),
                        "asset": meta_by_id.get(fid),
                    }
                )
    return out


# ── 커버리지 통계 ────────────────────────────────────────────────────────


def coverage_stats(norm: dict) -> dict:
    """정규화 보고서 전체의 구조 추출 성공/실패/미지 타입 통계.

    반환: {total_blocks, structured, text_group, failed, unknown_types:{type: n},
           by_type:{type: {blocks, structured, group}}, by_kind:{kind: n}}
    - failed  : 구조군인데 payload 가 나오지 않은 블록(빈 content 등)
    - unknown : GROUP_BY_TYPE 에 없는 위젯 타입 (registry 신규 추가 감지용)
    """
    by_type: dict[str, dict] = {}
    by_kind: dict[str, int] = {}
    unknown: dict[str, int] = {}
    total = structured = text_group = failed = 0

    for page in norm.get("pages", []):
        for block in page.get("blocks", []):
            btype = str(block.get("type", ""))
            total += 1
            group = GROUP_BY_TYPE.get(btype)
            slot = by_type.setdefault(
                btype, {"blocks": 0, "structured": 0, "group": group or "unknown"}
            )
            slot["blocks"] += 1
            if group is None:
                unknown[btype] = unknown.get(btype, 0) + 1
                continue
            if group == "text":
                text_group += 1
                continue
            payload = extract_structured(block)
            if payload is None:
                failed += 1
                continue
            structured += 1
            slot["structured"] += 1
            kind = str(payload.get("kind"))
            by_kind[kind] = by_kind.get(kind, 0) + 1

    return {
        "total_blocks": total,
        "structured": structured,
        "text_group": text_group,
        "failed": failed,
        "unknown_types": unknown,
        "by_type": by_type,
        "by_kind": by_kind,
    }
