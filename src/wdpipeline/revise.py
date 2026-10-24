# 사람이 고친 시나리오와 마지막 빌드를 대조해 무엇이 바뀌었는지 요약한다 (PLAN §11 사람 편집 왕복)
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

__all__ = ["diff_scenario", "change_summary_md", "SCENE_FIELDS"]

# 씬에서 변경을 추적할 필드. data_ref 는 값이 아니라 참조라 따로 본다(본문 교체는 여기서 안 잡힌다).
SCENE_FIELDS = ("tpl", "dur", "nat", "narration", "stills", "transition", "data_ref")

# 문서 수준 필드 — 이게 바뀌면 씬이 그대로여도 결과물이 달라진다.
DOC_FIELDS = ("format", "tokens_theme", "playback")


def _scenes_by_name(doc: dict) -> dict[str, dict]:
    return {str(s.get("name")): s for s in (doc.get("scenes") or [])}


def _order(doc: dict) -> list[str]:
    return [str(s.get("name")) for s in (doc.get("scenes") or [])]


def diff_scenario(current: dict, built: dict) -> dict:
    """현재 시나리오 vs 마지막 빌드(scene-data.json). 둘 다 ScenarioDoc 덤프다.

    빌드 산출물이 곧 기준선이라 별도 스냅샷을 두지 않는다 — 기록을 하나 더 두면
    그것이 어긋날 때 무엇이 진실인지 다시 다퉈야 한다.
    """
    cur_s, old_s = _scenes_by_name(current), _scenes_by_name(built)
    cur_o, old_o = _order(current), _order(built)

    added = [n for n in cur_o if n not in old_s]
    removed = [n for n in old_o if n not in cur_s]
    kept_cur = [n for n in cur_o if n in old_s]
    kept_old = [n for n in old_o if n in cur_s]

    fields: list[dict] = []
    for name in kept_cur:
        a, b = cur_s[name], old_s[name]
        for f in SCENE_FIELDS:
            before, after = b.get(f), a.get(f)
            if before != after:
                fields.append({"scene": name, "field": f, "before": before, "after": after})

    doc_fields: list[dict] = []
    for f in DOC_FIELDS:
        before, after = built.get(f), current.get(f)
        if before == after:
            continue
        # 빌드가 채워 넣은 값은 사람 편집이 아니다 — scenario.json 에 format 이 없어도
        # 빌드는 포맷을 해석해 scene-data.json 에 적는다. 이걸 변경으로 세면 모든 실행이
        # 매번 "format 이 사라졌다" 고 보고된다(실측).
        if after is None and before is not None:
            continue
        doc_fields.append({"field": f, "before": before, "after": after})

    # meta 는 중첩 dict 라 키 단위로 본다 — 통째로 비교하면 "meta 가 바뀜" 한 줄만 나온다
    meta_fields: list[dict] = []
    cm, bm = current.get("meta") or {}, built.get("meta") or {}
    for key in sorted(set(cm) | set(bm)):
        if cm.get(key) != bm.get(key):
            meta_fields.append({"field": key, "before": bm.get(key), "after": cm.get(key)})

    dur_cur = round(sum(float(s.get("dur") or 0) for s in cur_s.values()), 3)
    dur_old = round(sum(float(s.get("dur") or 0) for s in old_s.values()), 3)

    return {
        "changed": bool(added or removed or fields or doc_fields or meta_fields
                        or kept_cur != kept_old),
        "scenes": {
            "added": added, "removed": removed,
            "reordered": kept_cur != kept_old,
            "before_count": len(old_o), "after_count": len(cur_o),
        },
        "fields": fields,
        "doc_fields": doc_fields,
        "meta_fields": meta_fields,
        "duration": {"before": dur_old, "after": dur_cur,
                     "delta": round(dur_cur - dur_old, 3)},
    }


def _fmt(value: Any, limit: int = 60) -> str:
    text = "(없음)" if value is None else str(value)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def change_summary_md(diff: dict, *, run_id: str = "") -> str:
    """변경 요약 마크다운 — 재심의를 열 때 그대로 발제문이 된다.

    사람이 무엇을 고쳤는지 심의가 알아야 "왜 고쳤는가" 를 물을 수 있다.
    """
    if not diff["changed"]:
        return f"## 변경 없음\n\n{run_id or '이 실행'} 의 시나리오는 마지막 빌드와 같다."

    sc, dur = diff["scenes"], diff["duration"]
    lines = [f"## 사람 편집 요약{f' — {run_id}' if run_id else ''}", ""]
    lines.append(f"- 씬 {sc['before_count']} → {sc['after_count']}개 · "
                 f"총 길이 {dur['before']}s → {dur['after']}s ({dur['delta']:+.3f}s)")
    if sc["added"]:
        lines.append(f"- **추가된 씬** {', '.join(sc['added'])}")
    if sc["removed"]:
        lines.append(f"- **삭제된 씬** {', '.join(sc['removed'])}")
    if sc["reordered"]:
        lines.append("- **순서 변경** — 논증의 흐름이 바뀌었다")

    if diff["doc_fields"] or diff["meta_fields"]:
        lines += ["", "### 문서 수준"]
        for f in diff["doc_fields"] + diff["meta_fields"]:
            lines.append(f"- `{f['field']}` {_fmt(f['before'])} → {_fmt(f['after'])}")

    if diff["fields"]:
        lines += ["", "### 씬별 변경", "", "| 씬 | 항목 | 이전 | 이후 |", "| --- | --- | --- | --- |"]
        for f in diff["fields"]:
            lines.append(f"| {f['scene']} | {f['field']} | {_fmt(f['before'], 40)} "
                         f"| {_fmt(f['after'], 40)} |")

    lines += ["", "### 심의가 물어야 할 것", "",
              "- 이 편집이 core_message 를 더 강하게 만드는가, 아니면 흐릿하게 하는가.",
              "- 길이 변화가 내레이션 무음 예산과 맞는가.",
              "- 바뀐 씬의 템플릿이 그 데이터를 담기에 여전히 맞는가."]
    return "\n".join(lines)


def load_pair(scenario_path: Path, build_dir: Path) -> tuple[dict, dict]:
    """(현재 시나리오, 마지막 빌드) 를 읽는다. 없으면 FileNotFoundError."""
    s = Path(scenario_path)
    b = Path(build_dir) / "scene-data.json"
    if not s.is_file():
        raise FileNotFoundError(f"시나리오가 없다: {s}")
    if not b.is_file():
        raise FileNotFoundError(f"빌드 산출물이 없다: {b} — 먼저 wda build 를 돌려라")
    return (json.loads(s.read_text(encoding="utf-8")),
            json.loads(b.read_text(encoding="utf-8")))
