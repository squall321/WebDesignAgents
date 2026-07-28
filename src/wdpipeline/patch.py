# 씬 단위 핀포인트 수정의 정본 — 원자 연산 적용 + 전량 검증(실패 시 전체 취소) + 사람이 읽는 diff 요약
"""patch_scenario(scenario, ops) 가 유일한 수정 경로다 (PLAN §5.9).

웹 PATCH /api/runs/{id}/scenario, MCP scenario_patch, 콘솔 챗 액션이 모두 이 모듈을
소비한다. 연산 8종: set_data / set_narration / set_dur / set_tpl / set_stills /
reorder / remove_scene / insert_scene. 어떤 연산이든 하나라도 거부되거나 적용 후
validate_scenario 를 통과하지 못하면 PatchError 로 전체 취소한다 (원본 무손상).
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

OPS = (
    "set_data", "set_narration", "set_dur", "set_tpl",
    "set_stills", "reorder", "remove_scene", "insert_scene",
)

_TPL_REF_RE = re.compile(r"^([a-z][a-z0-9_.-]*)@(\d+)$")
# diff 요약에 넣는 값 표기의 절단 길이
_DIFF_VAL_LEN = 42
# insert_scene 의 content 키로 쓸 수 없는 문자 (data_ref 가 점 경로라 '.' 금지)
_KEY_BAD_RE = re.compile(r"[^0-9A-Za-z가-힣_-]+")


class PatchError(ValueError):
    """패치 전체 취소 — errors 에 연산 거부 사유 또는 검증 오류 목록을 담는다."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = list(errors)


# ── 공용 헬퍼 ────────────────────────────────────────────────────────────────


def _resolve_ref(doc: dict, ref: str) -> Any:
    node: Any = doc
    for seg in ref.split("."):
        if isinstance(node, dict) and seg in node:
            node = node[seg]
        else:
            return None
    return node


def find_scene(scenario: dict, name: Any) -> dict | None:
    """씬 이름 정확 일치 우선 — 소형 모델 대비 tpl 기본명(process 등)도 허용."""
    for s in scenario.get("scenes", []):
        if s.get("name") == name:
            return s
    for s in scenario.get("scenes", []):
        if isinstance(name, str) and str(s.get("tpl", "")).startswith(f"{name}@"):
            return s
    return None


def _fmt_num(v: Any) -> str:
    try:
        f = float(v)
        return str(int(f)) if f.is_integer() else str(f)
    except (TypeError, ValueError):
        return str(v)


def _fmt_val(v: Any) -> str:
    """diff 요약용 값 표기 — 문자열은 따옴표, 구조는 압축 JSON, 길면 절단."""
    if isinstance(v, str):
        s = f"'{v}'"
    else:
        s = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
    if len(s) > _DIFF_VAL_LEN:
        s = s[:_DIFF_VAL_LEN] + "…"
    return s


def _norm_path(path: str) -> list[str]:
    """점 경로 분해 — "steps[2].name" 대괄호 표기도 "steps.2.name" 으로 정규화."""
    return [seg for seg in re.sub(r"\[(\d+)\]", r".\1", path).split(".") if seg]


def normalize_tpl_ref(tpl: Any) -> str:
    """"process" 처럼 major 없는 참조를 레지스트리 버전으로 보정한다."""
    tpl = str(tpl).strip()
    if "@" in tpl:
        return tpl
    from .format import load_module_registry, tpl_short

    for mid, entry in load_module_registry().items():
        if entry.get("type") == "scene-template" and tpl_short(mid) == tpl:
            major = str(entry.get("version", "1.0.0")).split(".")[0]
            return f"{tpl}@{major}"
    return tpl


def _tpl_module_yaml(tpl_ref: str) -> dict | None:
    """tpl 참조 → module.yaml (레지스트리 부재·형식 오류면 None)."""
    if not _TPL_REF_RE.match(str(tpl_ref)):
        return None
    from .format import load_module_yaml, resolve_tpl_module_id

    return load_module_yaml(resolve_tpl_module_id(tpl_ref))


def _load_tpl_schema(tpl_ref: str) -> dict | None:
    if not _TPL_REF_RE.match(str(tpl_ref)):
        return None
    from .format import module_dir, resolve_tpl_module_id

    path = module_dir(resolve_tpl_module_id(tpl_ref)) / "schema.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_at(schema: dict, segs: list[str]) -> dict | None:
    """schema.json 을 점 경로로 내려가 해당 필드의 부분 스키마를 찾는다 (못 찾으면 None)."""
    node = schema
    for seg in segs:
        if not isinstance(node, dict):
            return None
        props = node.get("properties")
        if isinstance(props, dict) and seg in props:
            node = props[seg]
        elif seg.isdigit() and isinstance(node.get("items"), dict):
            node = node["items"]
        else:
            return None
    return node


def _format_allows(scenario: dict, tpl_ref: str) -> str | None:
    """포맷 template_pool 검증 — 위반 사유 문자열, 통과·판정불능이면 None."""
    from .format import FormatError, load_format

    fmt = str(scenario.get("format") or "wide-16x9")
    try:
        spec = load_format(fmt)
    except (FormatError, Exception):  # noqa: BLE001 — 포맷 로드 불능은 최종 검증 몫
        return None
    if not spec.allows_tpl(tpl_ref):
        return f"템플릿 {tpl_ref!r} 가 포맷 {spec.id} 의 template_pool 에 없다 (허용: {spec.tpl_ids()})"
    return None


# ── 연산 1건 적용 (챗 액션 루프가 직접 소비) ─────────────────────────────────


def apply_op(scenario: dict, op: dict) -> tuple[str | None, str | None]:
    """연산 1건을 scenario(호출자가 만든 사본)에 제자리 적용한다.

    반환: (diff 요약, 거부 사유) — 정확히 하나만 채워진다. scenario 자체를 검증하지는
    않는다 (전량 검증은 patch_scenario 몫).
    """
    kind = op.get("op") or op.get("type")
    if kind not in OPS:
        return None, f"허용되지 않는 연산: {kind!r} (허용: {', '.join(OPS)})"

    if kind == "reorder":
        return _op_reorder(scenario, op)
    if kind == "insert_scene":
        return _op_insert_scene(scenario, op)

    scene = find_scene(scenario, op.get("scene"))
    if scene is None:
        return None, f"{kind}: 씬 {op.get('scene')!r} 을 찾을 수 없다"

    if kind == "set_data":
        return _op_set_data(scenario, scene, op)
    if kind == "set_narration":
        return _op_set_narration(scene, op)
    if kind == "set_dur":
        return _op_set_dur(scene, op)
    if kind == "set_tpl":
        return _op_set_tpl(scenario, scene, op)
    if kind == "set_stills":
        return _op_set_stills(scene, op)
    # remove_scene
    scenario["scenes"] = [s for s in scenario["scenes"] if s is not scene]
    return f"{scene['name']} 씬 제거", None


def _op_set_data(scenario: dict, scene: dict, op: dict) -> tuple[str | None, str | None]:
    path = str(op.get("path") or "").strip()
    if not path:
        return None, "set_data: path 가 비었다"
    data = _resolve_ref(scenario, scene.get("data_ref") or "")
    if not isinstance(data, dict):
        return None, f"set_data: 씬 {scene['name']!r} 의 data_ref 를 해석할 수 없다"
    segs = _norm_path(path)
    value = op.get("value")
    # 스키마 maxLength 사전 검증 (전체 스키마 검증은 적용 후 validate_scenario 가 한 번 더)
    schema = _load_tpl_schema(scene.get("tpl", ""))
    if schema is not None:
        sub = _schema_at(schema, segs)
        if sub is not None and isinstance(value, str):
            max_len = sub.get("maxLength")
            if max_len is not None and len(value) > max_len:
                return None, f"set_data: {path} 값이 maxLength {max_len} 초과 ({len(value)}자)"
    node: Any = data
    for seg in segs[:-1]:
        if isinstance(node, dict) and seg in node:
            node = node[seg]
        elif isinstance(node, list) and seg.isdigit() and int(seg) < len(node):
            node = node[int(seg)]
        else:
            return None, f"set_data: 경로 {path!r} 가 씬 data 에 없다"
    last = segs[-1]
    if isinstance(node, dict):
        old = node.get(last)
        node[last] = value
    elif isinstance(node, list) and last.isdigit() and int(last) < len(node):
        old = node[int(last)]
        node[int(last)] = value
    else:
        return None, f"set_data: 경로 {path!r} 가 씬 data 에 없다"
    return f"{scene['name']}.{path}: {_fmt_val(old)}→{_fmt_val(value)}", None


def _op_set_narration(scene: dict, op: dict) -> tuple[str | None, str | None]:
    text = op.get("text")
    if not isinstance(text, str) or not text.strip():
        return None, "set_narration: text 가 비었다"
    old = scene.get("narration") or ""
    scene["narration"] = text.strip()
    return f"{scene['name']} narration: {_fmt_val(old)}→{_fmt_val(text.strip())}", None


def _op_set_dur(scene: dict, op: dict) -> tuple[str | None, str | None]:
    try:
        dur = float(op.get("dur"))
    except (TypeError, ValueError):
        return None, f"set_dur: dur 가 숫자가 아니다 ({op.get('dur')!r})"
    old = scene.get("dur")
    scene["dur"] = dur
    # 파이프라인 stills 공식(dur-1.0, 하한 dur/2)으로 초과 시각을 재클램프
    still_cap = round(max(dur - 1.0, dur * 0.5), 2)
    scene["stills"] = [s if s <= dur else still_cap for s in scene.get("stills", [])]
    return f"{scene['name']} dur: {_fmt_num(old)}→{_fmt_num(dur)}", None


def _op_set_tpl(scenario: dict, scene: dict, op: dict) -> tuple[str | None, str | None]:
    tpl = normalize_tpl_ref(op.get("tpl") or "")
    if _tpl_module_yaml(tpl) is None:
        return None, f"set_tpl: 레지스트리에 없는 템플릿 {op.get('tpl')!r}"
    pool_err = _format_allows(scenario, tpl)
    if pool_err:
        return None, f"set_tpl: {pool_err}"
    old = scene.get("tpl")
    scene["tpl"] = tpl
    return f"{scene['name']} tpl: {old}→{tpl}", None


def _op_set_stills(scene: dict, op: dict) -> tuple[str | None, str | None]:
    stills = op.get("stills")
    if not isinstance(stills, list):
        return None, "set_stills: stills 는 시각(초) 목록이어야 한다"
    try:
        times = [round(float(s), 3) for s in stills]
    except (TypeError, ValueError):
        return None, f"set_stills: 숫자가 아닌 시각이 있다 ({stills!r})"
    dur = float(scene.get("dur") or 0)
    bad = [t for t in times if not 0 <= t <= dur]
    if bad:
        return None, f"set_stills: 시각 {bad} 가 [0, dur={_fmt_num(dur)}] 범위를 벗어났다"
    old = scene.get("stills", [])
    scene["stills"] = times
    return f"{scene['name']} stills: {_fmt_val(old)}→{_fmt_val(times)}", None


def _op_reorder(scenario: dict, op: dict) -> tuple[str | None, str | None]:
    names = op.get("names")
    current = [s["name"] for s in scenario.get("scenes", [])]
    if not isinstance(names, list) or sorted(map(str, names)) != sorted(current):
        return None, f"reorder: names 가 현재 씬 이름 순열이 아니다 (현재: {current})"
    by_name = {s["name"]: s for s in scenario["scenes"]}
    scenario["scenes"] = [by_name[str(n)] for n in names]
    return "씬 순서 변경: " + " → ".join(map(str, names)), None


def _unique(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    i = 2
    while f"{base}-{i}" in taken:
        i += 1
    return f"{base}-{i}"


def _op_insert_scene(scenario: dict, op: dict) -> tuple[str | None, str | None]:
    """insert_scene {after, tpl, data, name?, dur?, narration?, stills?}.

    after: 씬 이름 = 그 뒤에 삽입, null = 맨 앞, 생략 = 맨 끝.
    dur 생략 시 module.yaml nat_default. data 는 템플릿 스키마 대상 데이터(dict) 필수 —
    스키마 적합성은 최종 validate_scenario 가 판정한다 (부적합이면 전체 취소).
    """
    tpl = normalize_tpl_ref(op.get("tpl") or "")
    module = _tpl_module_yaml(tpl)
    if module is None:
        return None, f"insert_scene: 레지스트리에 없는 템플릿 {op.get('tpl')!r}"
    pool_err = _format_allows(scenario, tpl)
    if pool_err:
        return None, f"insert_scene: {pool_err}"
    data = op.get("data")
    if not isinstance(data, dict):
        return None, "insert_scene: data 는 템플릿 데이터 객체여야 한다"

    short = tpl.split("@", 1)[0].rsplit(".", 1)[-1]
    scenes = scenario.setdefault("scenes", [])
    taken_names = {s.get("name") for s in scenes}
    name = str(op.get("name") or "").strip() or short
    if name in taken_names:
        return None, f"insert_scene: 씬 이름 {name!r} 이 이미 있다"

    content = scenario.setdefault("content", {})
    key = _unique(_KEY_BAD_RE.sub("-", name).strip("-") or short, set(content))
    content[key] = data

    try:
        dur = float(op["dur"]) if op.get("dur") is not None else float(module.get("nat_default") or 8.0)
    except (TypeError, ValueError):
        return None, f"insert_scene: dur 가 숫자가 아니다 ({op.get('dur')!r})"

    entry = {
        "name": name,
        "dur": dur,
        "nat": float(module.get("nat_default")) if module.get("nat_default") else None,
        "tpl": tpl,
        "stills": list(op.get("stills") or []),
        "data_ref": f"content.{key}",
        "narration": str(op.get("narration") or ""),
        "transition": "cut",
    }

    if "after" not in op:
        scenes.append(entry)
        pos = "맨 끝"
    elif op.get("after") is None:
        scenes.insert(0, entry)
        pos = "맨 앞"
    else:
        anchor = find_scene(scenario, op.get("after"))
        if anchor is None:
            content.pop(key, None)
            return None, f"insert_scene: after 씬 {op.get('after')!r} 을 찾을 수 없다"
        scenes.insert(scenes.index(anchor) + 1, entry)
        pos = f"{anchor['name']} 뒤"
    return f"{name} 씬 삽입 (tpl={tpl}, dur={_fmt_num(dur)}, 위치={pos})", None


# ── 전량 검증 ────────────────────────────────────────────────────────────────


def validate_scenario_dict(work: dict, modules_root: Path | None = None) -> tuple[Any, list[str]]:
    """dict → ScenarioDoc 파싱 + 확장 검증. (doc | None, 오류 목록)을 반환한다."""
    from pydantic import ValidationError

    from wdcore.models.scenario import ScenarioDoc

    from .scenario import validate_scenario

    try:
        doc = ScenarioDoc.model_validate(work)
    except ValidationError as exc:
        msgs = [
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:5]
        ]
        return None, msgs
    if modules_root is not None:
        return doc, validate_scenario(doc, modules_root)
    return doc, validate_scenario(doc)


# ── 정본 진입점 ──────────────────────────────────────────────────────────────


def patch_scenario(scenario: dict, ops: list[dict]) -> tuple[dict, list[str]]:
    """원자 연산 목록을 사본에 적용하고 전량 검증한다.

    반환: (검증 통과한 수정본 model_dump, diff 요약 목록).
    실패: PatchError(errors) — 원본 scenario 는 어떤 경우에도 변형되지 않는다.
    """
    if not isinstance(ops, list) or not ops:
        raise PatchError(["ops 는 비어있지 않은 연산 목록이어야 한다"])
    work = copy.deepcopy(scenario)
    diffs: list[str] = []
    errors: list[str] = []
    for i, op in enumerate(ops):
        if not isinstance(op, dict):
            errors.append(f"ops[{i}]: 연산은 객체여야 한다 ({str(op)[:60]})")
            continue
        diff, err = apply_op(work, op)
        if err:
            errors.append(f"ops[{i}] {err}")
        else:
            diffs.append(diff)  # type: ignore[arg-type]
    if errors:
        raise PatchError(errors)
    doc, verrors = validate_scenario_dict(work)
    if verrors:
        raise PatchError(verrors)
    return doc.model_dump(), diffs
