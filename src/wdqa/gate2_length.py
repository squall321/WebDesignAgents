# 게이트 2 — 글자수 대비 씬 길이 (x-read 합산 | 내레이션 길이 → 낭독 속도 대비 최소 dur 제안)
from __future__ import annotations

import json
import math
import re
from pathlib import Path

from .config import QAConfig
from .report import row

GATE = 2

_WS_RE = re.compile(r"\s+")


def _nonspace_len(s: str) -> int:
    return len(_WS_RE.sub("", s))


def _tpl_dir_name(tpl: str) -> str:
    """'tpl.process' | 'process@1' | 'process' → 'process'."""
    t = tpl.split("@", 1)[0]
    if t.startswith("tpl."):
        t = t[len("tpl."):]
    return t


def load_schema(modules_root: Path, tpl: str) -> dict | None:
    p = modules_root / "scene-templates" / _tpl_dir_name(tpl) / "schema.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _count_all_strings(data) -> int:
    """데이터 서브트리의 모든 문자열을 공백 제외 글자수로 합산한다."""
    if isinstance(data, str):
        return _nonspace_len(data)
    if isinstance(data, dict):
        return sum(_count_all_strings(v) for v in data.values())
    if isinstance(data, list):
        return sum(_count_all_strings(v) for v in data)
    return 0


def collect_read_chars(schema: dict, data) -> int:
    """스키마의 x-read: true 노드를 데이터와 병행 순회하며 공백 제외 글자수를 합산한다.

    x-read 는 문자열뿐 아니라 객체/배열 노드에도 선언된다(opening.title 세그먼트 배열 등,
    P4 스키마 계약) — 그 경우 서브트리 전체 문자열을 합산한다.
    """
    if not isinstance(schema, dict):
        return 0
    if schema.get("x-read") is True:
        return _count_all_strings(data)
    total = 0
    stype = schema.get("type")
    if stype == "object" and isinstance(data, dict):
        for key, sub in (schema.get("properties") or {}).items():
            if key in data:
                total += collect_read_chars(sub, data[key])
    elif stype == "array" and isinstance(data, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for v in data:
                total += collect_read_chars(items, v)
    return total


def _resolve_data(scenario: dict, scene: dict) -> dict | None:
    """data_ref 경로('content.process') 우선, 없으면 content[템플릿명]."""
    ref = scene.get("data_ref") or ""
    if ref:
        cur = scenario
        for seg in ref.split("."):
            if isinstance(cur, dict) and seg in cur:
                cur = cur[seg]
            else:
                return None
        return cur if isinstance(cur, dict) else None
    content = scenario.get("content") or {}
    return content.get(_tpl_dir_name(scene.get("tpl", "")))


def run_data(scenario: dict | None, cfg: QAConfig) -> list[dict]:
    """씬별 필요 낭독 시간(내레이션 5.5자/초, 자막 9자/초)과 dur 를 비교한다."""
    results: list[dict] = []
    if not scenario:
        results.append(
            row(GATE, "no-scenario", "info",
                "scenario 미제공 — 게이트 2(글자수 대비 길이)를 생략한다")
        )
        return results
    scenes = scenario.get("scenes") or []
    if not scenes:
        results.append(row(GATE, "no-scenes", "warning", "scenario.scenes 가 비어 있다"))
        return results

    for sc in scenes:
        name = sc.get("name", "?")
        dur = float(sc.get("dur", 0) or 0)
        if dur <= 0:
            results.append(
                row(GATE, "bad-dur", "error", f"dur={dur} 가 유효하지 않다", scene=name)
            )
            continue

        narration = (sc.get("narration") or "").strip()
        if narration:
            chars = _nonspace_len(narration)
            need = chars / cfg.narration_cps
            rule, rate = "narration-rate", cfg.narration_cps
        else:
            tpl = sc.get("tpl") or ""
            schema = load_schema(cfg.modules_root, tpl) if tpl else None
            if schema is None:
                results.append(
                    row(GATE, "schema-missing", "info",
                        f"tpl={tpl!r} 스키마를 찾지 못해 x-read 합산을 생략한다", scene=name)
                )
                continue
            data = _resolve_data(scenario, sc)
            if data is None:
                results.append(
                    row(GATE, "data-missing", "info",
                        f"씬 데이터(data_ref={sc.get('data_ref') or '-'})를 찾지 못했다", scene=name)
                )
                continue
            chars = collect_read_chars(schema, data)
            need = chars / cfg.caption_cps
            rule, rate = "caption-rate", cfg.caption_cps

        if need > dur + 1e-3:
            suggest = math.ceil(need * 10) / 10
            results.append(
                row(GATE, rule, "error",
                    f"글자수 {chars}자 ÷ {rate}자/초 = {need:.1f}s > dur {dur:.1f}s "
                    f"— 최소 dur 제안: {suggest:.1f}s", scene=name)
            )

        nat = sc.get("nat")
        if nat:
            stretch = abs(dur - float(nat)) / float(nat)
            if stretch > cfg.stretch_limit + 1e-9:
                results.append(
                    row(GATE, "stretch-limit", "warning",
                        f"타임 스트레치 {stretch:.0%} 가 한계 ±{cfg.stretch_limit:.0%} 를 초과 "
                        f"(dur={dur}, nat={nat})", scene=name)
                )
    return results
