# P3 scenario — 조각을 씬 템플릿 7종에 규칙 기반 배치(assemble_demo_scenario)하고 ScenarioDoc 를 검증(validate_scenario)
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from wdcore.models.scenario import ScenarioDoc, check_om_scenes_budget

# repo 루트 기준 모듈 레지스트리 (src/wdpipeline/scenario.py → 두 단계 위가 repo)
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODULES_ROOT = _REPO_ROOT / "modules"


def resolve_modules_root() -> Path:
    """WDA_MODULES_ROOT 환경변수 우선 — wdmcp 의 modules_root() 와 같은 규칙."""
    env = os.environ.get("WDA_MODULES_ROOT")
    return Path(env) if env else DEFAULT_MODULES_ROOT

# 씬 타입 7종 — 설득 골격 순서 (PLAN §6.1)
TEMPLATE_ORDER = [
    "opening", "problem", "concept", "process", "differentiator", "proof", "closing",
]

_TPL_REF_RE = re.compile(r"^([a-z][a-z0-9_-]*)@(\d+)$")


# ── 모듈 레지스트리 접근 ────────────────────────────────────────────────


def _load_module(name: str, modules_root: Path) -> dict:
    """modules/scene-templates/{name}/module.yaml 을 로드한다."""
    path = modules_root / "scene-templates" / name / "module.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_schema(name: str, modules_root: Path) -> dict:
    """modules/scene-templates/{name}/schema.json 을 로드한다."""
    path = modules_root / "scene-templates" / name / "schema.json"
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


def narration_from_x_read(data: dict, schema: dict) -> str:
    """x-read 문자열을 문장으로 이어 TTS 내레이션 대본을 만든다."""
    parts = _collect_x_read(data, schema)
    sents = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if p[-1] not in ".!?…":
            p += "."
        sents.append(p)
    return " ".join(sents)


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


def _build_problem(norm: dict, fragments: list[dict], idx: int) -> dict:
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


def _build_concept(norm: dict, fragments: list[dict], idx: int) -> dict:
    tags = norm.get("tags", [])
    title = _first_text(fragments, norm["title"], type="claim", widget="heading")
    items = _flow_items(norm)
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
    return {
        "kicker": _clip(tags[1] if len(tags) > 1 else "접근", 16),
        "title": _clip(title, 40),
        "center": _clip(tags[0] if tags else "핵심", 6),
        "nodes": _concept_nodes(norm),
        "rounds": rounds,
        "outcome": {"title": "한눈 요약", "desc": _clip(summary, 40)},
        "frame": _frame(norm, idx),
    }


def _build_process(norm: dict, fragments: list[dict], idx: int) -> dict:
    items = _flow_items(norm)
    if not items:
        items = [{"label": t} for t in _texts(fragments, 6, type="evidence")]
    steps = [
        {
            "n": f"{i + 1:02d}",
            "name": _clip(item.get("label", f"단계 {i + 1}"), 12),
            "desc": _clip(item.get("description", "") or item.get("label", ""), 40),
        }
        for i, item in enumerate(items[:6])
    ]
    while len(steps) < 3:
        n = len(steps) + 1
        steps.append({"n": f"{n:02d}", "name": f"단계 {n}", "desc": "보고서 참조"})
    title = _first_text(fragments, "진행 절차", type="evidence", widget="flowchart")
    return {
        "kicker": "절차",
        "title": _clip(f"{_clean_page_name(norm['title'])} — 진행 흐름", 40)
        if items else _clip(title, 40),
        "steps": steps,
        "footnote": {"pre": _clip(f"출처: {norm['title']}", 30)},
        "frame": _frame(norm, idx),
    }


def _build_differentiator(norm: dict, fragments: list[dict], idx: int) -> dict:
    rows: list[dict] = []
    for b in _blocks_of_type(norm, "comparison"):
        rows = (b.get("content") or {}).get("rows", [])
        if rows:
            break
    flow = []
    for i, row in enumerate(rows[:2]):
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
    verdict = _first_text(fragments, "보고서 근거로 정리", type="evidence", widget="comparison")
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
        "footnote": {"pre": _clip(f"출처: {norm['title']}", 30)},
        "frame": _frame(norm, idx),
    }


def _build_proof(norm: dict, fragments: list[dict], idx: int) -> dict:
    cases = []
    for pi, page in enumerate(norm.get("pages", []), start=1):
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
        if len(cases) == 3:
            break
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


def _build_closing(norm: dict, fragments: list[dict]) -> dict:
    stats = []
    for b in _blocks_of_type(norm, "progress_bar"):
        for item in (b.get("content") or {}).get("items", []):
            if "value" in item:
                stats.append(
                    {"v": _clip(f"{item['value']}%", 14), "d": _clip(item.get("label", ""), 24)}
                )
            if len(stats) == 3:
                break
        if len(stats) == 3:
            break
    if len(stats) < 2:
        stats = [
            {"v": f"{len(norm.get('pages', []))}페이지", "d": "보고서 구성"},
            {"v": f"{len(fragments)}건", "d": "추출된 근거 조각"},
        ][: max(2, len(stats))]
    tags = norm.get("tags", [])
    ctas = [{"text": _clip(t, 18)} for t in tags[:3]] or [{"text": "보고서 전문 확인"}]
    return {
        "stats": stats[:3],
        "title": _split_title(norm["title"]),
        "subtitle": _clip(" · ".join(tags) if tags else "보고서 요약", 30),
        "ctas": ctas,
        "footnote": _clip(f"원문: {norm['title']} ({norm.get('report_date', '')})", 40),
    }


_BUILDERS = {
    "opening": lambda norm, frags, idx: _build_opening(norm, frags),
    "problem": _build_problem,
    "concept": _build_concept,
    "process": _build_process,
    "differentiator": _build_differentiator,
    "proof": _build_proof,
    "closing": lambda norm, frags, idx: _build_closing(norm, frags),
}


# ── 공개 API (모듈 간 계약) ─────────────────────────────────────────────


def assemble_demo_scenario(norm: dict, fragments: list[dict]) -> ScenarioDoc:
    """규칙 기반(LLM 무호출) 데모 시나리오 조립.

    ai_summary(없으면 제목)를 core_message 로, 조각을 씬 타입 7종에 휴리스틱 배치.
    각 씬 data 는 템플릿 schema.json 의 maxLength 에 맞게 절단하고,
    narration 은 x-read 필드를 문장으로 연결한다.
    """
    modules_root = resolve_modules_root()
    content: dict[str, dict] = {}
    scenes: list[dict] = []
    for idx, name in enumerate(TEMPLATE_ORDER, start=1):
        module = _load_module(name, modules_root)
        schema = _load_schema(name, modules_root)
        data = _BUILDERS[name](norm, fragments, idx)
        data = _conform(data, schema)
        content[name] = data
        dur = float(module.get("nat_default", 10))
        major = str(module.get("version", "1.0.0")).split(".")[0]
        scenes.append(
            {
                "name": module.get("scene_name_default", name),
                "dur": dur,
                "nat": dur,
                "tpl": f"{name}@{major}",
                # 등장 완료 후·퇴장 전 안정 화면 — dur-1.0s (진행률 방식(0.9×dur)은 긴 씬에서
                # 마지막 요소 페이드 도중을 캡처했다: QA 게이트 3 실측). 하한은 dur 절반.
                "stills": [round(max(dur - 1.0, dur * 0.5), 2)],
                "data_ref": f"content.{name}",
                "narration": narration_from_x_read(data, schema),
                "transition": "cut",
            }
        )
    core_message = norm.get("ai_summary") or norm["title"]
    return ScenarioDoc.model_validate(
        {
            "version": "1.0",
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


def validate_scenario(doc: ScenarioDoc, modules_root: Path | None = None) -> list[str]:
    """ScenarioDoc 확장 검증 — 오류 문자열 목록을 반환한다 (빈 리스트 = 통과).

    검사: OM_SCENES 16KB 예산, 씬 이름 중복(children 맵 키 충돌), tpl 레지스트리
    존재·status≠deprecated·메이저 버전 일치, data_ref 실경로, 템플릿 데이터 스키마.
    """
    modules_root = Path(modules_root) if modules_root is not None else resolve_modules_root()
    errors: list[str] = []

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
        tpl_name, major = m.group(1), m.group(2)
        module_path = modules_root / "scene-templates" / tpl_name / "module.yaml"
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
            schema = _load_schema(tpl_name, modules_root)
        except Exception as e:  # noqa: BLE001
            errors.append(f"씬 {s.name!r}: schema.json 로드 실패 ({e})")
            continue
        validator = Draft202012Validator(schema)
        for err in sorted(validator.iter_errors(node), key=lambda e: list(e.absolute_path)):
            loc = "/".join(str(p) for p in err.absolute_path) or "(루트)"
            errors.append(f"씬 {s.name!r}: 데이터 스키마 위반 [{loc}] {err.message}")

    return errors
