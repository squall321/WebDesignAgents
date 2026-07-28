# 대화형 제작 패널 백엔드 — LLM 이 제안한 허용 액션을 시나리오에 적용·검증·재빌드하는 왕복 루프
"""POST /api/runs/{run_id}/chat 의 본체.

흐름: 현재 scenario.json 요약 + 템플릿 인덱스 + 허용 액션 스키마를 시스템 프롬프트로
LLM(wdllm.client — GLM 5원칙)에 보내 {reply, actions} JSON 을 받고, 액션을 시나리오
수정본에 적용 → validate_scenario 통과 시에만 저장 + 재빌드(빌드 산출물이 시나리오를
내장하므로 어떤 수정이든 프리뷰 갱신에는 재빌드가 필요하다). 실패 시 전체 취소하고
사유를 reply 에 병합한다. LLM 호출 지점은 get_llm() 으로 분리 — 테스트가 monkeypatch 한다.
"""
from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

import yaml
from fastapi import HTTPException

from . import runs as runledger
from .runs import REPO_ROOT, data_dir

_MODULES_REGISTRY = REPO_ROOT / "modules" / "registry.yaml"

# LLM 컨텍스트에 넣는 직전 대화 이력 수 (user/assistant 합산)
_HISTORY_WINDOW = 8
# 씬 data 요약을 프롬프트에 넣을 때의 절단 길이
_DATA_BRIEF_LEN = 240

# "[씬이름] ..." 프리픽스 — 콘솔 씬 스트립의 "이 씬 수정" 타겟 지정 규약
_SCENE_TARGET_RE = re.compile(r"^\s*\[([^\[\]]{1,60})\]")

ALLOWED_ACTIONS = (
    "set_field", "set_narration", "set_dur", "set_tpl",
    "drop_scene", "reorder", "rebuild", "run_qa",
)


# ── LLM 호출 지점 (테스트 monkeypatch 대상) ─────────────────────────────────


def get_llm():
    """GLM 5원칙 클라이언트 — dev 기본은 로컬 vLLM(:8000, qwen2.5-7b-dev)."""
    from wdllm.client import GLMClient

    return GLMClient()


def ask_llm(llm, messages: list[dict]) -> dict:
    """{reply, actions} JSON 을 강제한다 — 파싱 실패 시 재시도(chat_json 규약)."""
    from wdllm.client import chat_json

    retries = getattr(getattr(llm, "config", None), "parse_retries", 2)
    obj, _results = chat_json(llm, messages, parse_retries=retries)
    return obj


# ── 프롬프트 조립 ────────────────────────────────────────────────────────────


def _tpl_index() -> list[dict]:
    """레지스트리의 scene-template 축약 인덱스 — {ref, nat_default, summary}."""
    if not _MODULES_REGISTRY.is_file():
        return []
    registry = yaml.safe_load(_MODULES_REGISTRY.read_text(encoding="utf-8")) or {}
    out = []
    for m in registry.get("modules", []):
        if m.get("type") != "scene-template":
            continue
        name = str(m.get("id", "")).removeprefix("tpl.")
        major = str(m.get("version", "1.0.0")).split(".")[0]
        out.append({
            "ref": f"{name}@{major}",
            "nat_default": m.get("nat_default"),
            "summary": m.get("summary", ""),
        })
    return out


def _resolve_ref(doc: dict, ref: str) -> Any:
    node: Any = doc
    for seg in ref.split("."):
        if isinstance(node, dict) and seg in node:
            node = node[seg]
        else:
            return None
    return node


def _scenario_brief(scenario: dict) -> str:
    lines = [f"core_message: {scenario['meta']['core_message']}", "scenes (순서대로):"]
    for i, s in enumerate(scenario.get("scenes", []), start=1):
        data = _resolve_ref(scenario, s.get("data_ref") or "")
        dj = json.dumps(data, ensure_ascii=False, separators=(",", ":")) if isinstance(data, dict) else "{}"
        if len(dj) > _DATA_BRIEF_LEN:
            dj = dj[:_DATA_BRIEF_LEN] + "…"
        nar = (s.get("narration") or "").replace("\n", " ")
        if len(nar) > 90:
            nar = nar[:90] + "…"
        lines.append(
            f"{i}. name={s['name']} tpl={s['tpl']} dur={s['dur']} narration={nar!r} data={dj}"
        )
    return "\n".join(lines)


def _system_prompt(scenario: dict) -> str:
    tpls = "\n".join(
        f"- {t['ref']}: {t['summary']} (기본 {t['nat_default']}초)" for t in _tpl_index()
    )
    return f"""너는 발표 영상 시나리오 편집 어시스턴트다. 사용자의 요청을 아래 허용 액션으로 변환한다.
허용 액션으로 표현할 수 없는 요청이면 actions 를 빈 배열로 두고 reply 로 사유를 설명한다.

[현재 시나리오]
{_scenario_brief(scenario)}

[사용 가능한 템플릿 (tpl)]
{tpls}

[허용 액션 — 이 8종만 유효하다]
- {{"type":"set_field","scene":"<씬 name>","path":"<씬 data 안의 점 경로. 예: title, steps.0.name>","value":<새 값>}}
- {{"type":"set_narration","scene":"<씬 name>","text":"<새 내레이션 대본>"}}
- {{"type":"set_dur","scene":"<씬 name>","dur":<재생 길이 초. 0 초과 300 이하>}}
- {{"type":"set_tpl","scene":"<씬 name>","tpl":"<템플릿 참조. 예: process@1>"}}
- {{"type":"drop_scene","scene":"<씬 name>"}}
- {{"type":"reorder","names":["<전체 씬 name 을 원하는 순서로 나열>", ...]}}
- {{"type":"rebuild"}}
- {{"type":"run_qa"}}  (선택 인자 "gates": ["2"] 등)

[응답 형식 — 설명·코드펜스 없이 JSON 객체 하나만]
{{"reply":"<사용자에게 할 말 (한국어)>","actions":[<액션 0개 이상>]}}"""


def _scene_target(scenario: dict, message: str) -> str | None:
    """"[씬이름] ..." 프리픽스가 실존 씬을 가리키면 그 이름을 반환한다."""
    m = _SCENE_TARGET_RE.match(message)
    if not m:
        return None
    name = m.group(1).strip()
    if any(s.get("name") == name for s in scenario.get("scenes", [])):
        return name
    return None


# ── 액션 적용 (정본은 wdpipeline.patch — 여기서는 액션명 변환 + 위임만) ─────

# 챗 액션명 → patch 연산명 (나머지는 이름 동일)
_ACTION_TO_OP = {"set_field": "set_data", "drop_scene": "remove_scene"}


def _apply_actions(
    scenario: dict, actions: list
) -> tuple[dict, list[str], list[str], bool, bool, dict | None]:
    """액션 목록을 시나리오 깊은 복사본에 적용한다 (연산 실체는 wdpipeline.patch.apply_op).

    반환: (수정본, applied 요약, rejected 사유, modified 여부, rebuild 요청 여부, qa 요청).
    """
    from wdpipeline import patch as patchops

    work = copy.deepcopy(scenario)
    applied: list[str] = []
    rejected: list[str] = []
    modified = False
    rebuild_requested = False
    qa_request: dict | None = None

    for action in actions if isinstance(actions, list) else []:
        if not isinstance(action, dict):
            rejected.append(f"액션 형식 오류: {str(action)[:60]}")
            continue
        atype = action.get("type")
        if atype not in ALLOWED_ACTIONS:
            rejected.append(f"허용되지 않는 액션: {atype!r}")
            continue

        if atype == "rebuild":
            rebuild_requested = True
            continue
        if atype == "run_qa":
            gates = action.get("gates")
            qa_request = {"gates": gates if isinstance(gates, list) else None}
            continue

        op = {k: v for k, v in action.items() if k != "type"}
        op["op"] = _ACTION_TO_OP.get(atype, atype)
        diff, err = patchops.apply_op(work, op)
        if err:
            rejected.append(err)
        else:
            applied.append(diff)  # type: ignore[arg-type]
            modified = True

    return work, applied, rejected, modified, rebuild_requested, qa_request


# ── 검증·저장·재빌드 ─────────────────────────────────────────────────────────


def _validate(work: dict) -> tuple[Any, list[str]]:
    """ScenarioDoc 파싱 + 확장 검증 — (doc | None, 오류 목록). 정본은 wdpipeline.patch."""
    from wdpipeline.patch import validate_scenario_dict

    return validate_scenario_dict(work)


def _rebuild(run: dict, doc) -> tuple[Path, str]:
    """새 scenario 로 빌드 패키지를 재생성한다 — 기존 build_dir 유지(프리뷰 URL 안정)."""
    from wdpipeline.build import build_render_package

    build_dir = Path(run["build_dir"]) if run.get("build_dir") else data_dir() / "build" / run["slug"]
    entry = Path(build_render_package(doc, build_dir))
    return entry.parent, entry.name


def _append_chat(run_id: str, entries: list[dict]) -> None:
    """chat 배열 read-modify-write — 원장 RLock 을 잡은 채 수행한다."""
    with runledger._lock:  # noqa: SLF001 — runs.py 잠금 규약 (원장 갱신 유실 방지)
        run = runledger.read_run(run_id)
        assert run is not None, f"실행 원장 유실: {run_id}"
        chat = list(run.get("chat") or [])
        chat.extend(entries)
        runledger.update_run(run_id, chat=chat)


def _qa_summary_text(run_id: str, qa_request: dict) -> str:
    """run_qa 액션 — 게이트 실행 결과를 reply 병합용 한 줄 요약으로."""
    run = runledger.read_run(run_id)
    if not (run and run.get("build_dir")):
        return "QA: 빌드가 없어 실행하지 못했다."
    try:
        result = runledger.run_qa(run_id, gates=qa_request.get("gates"))
    except ValueError as exc:
        return f"QA 실행 실패: {exc}"
    except Exception as exc:  # noqa: BLE001 — 게이트 실행 실패도 대화로 보고
        return f"QA 실행 실패: {type(exc).__name__}: {exc}"
    rows = [r for r in result.get("results", []) if r.get("severity") != "info"]
    head = "QA 통과" if result.get("passed") else f"QA 실패 — 지적 {len(rows)}건"
    detail = "; ".join(
        f"[{r.get('severity')}] gate{r.get('gate')} {r.get('rule')}"
        + (f" @{r['scene']}" if r.get("scene") else "")
        for r in rows[:5]
    )
    return head + (f" ({detail})" if detail else "")


# ── 공개 API (app.py 라우트가 호출) ──────────────────────────────────────────


def handle_chat(run: dict, message: str) -> dict:
    """대화 1턴 처리 — {reply, applied, rebuilt} 를 반환한다 (봉투는 라우트 몫)."""
    run_id = run["run_id"]
    scenario_done = any(
        s.get("stage") == "scenario" and s.get("status") == "done" for s in run.get("stages", [])
    )
    if not scenario_done:
        raise HTTPException(status_code=409, detail="scenario 단계가 완료된 실행만 대화할 수 있습니다")
    scen_path = data_dir() / "pipeline" / run_id / "scenario.json"
    if not scen_path.is_file():
        raise HTTPException(status_code=409, detail=f"scenario.json 이 없습니다: {scen_path}")
    scenario = json.loads(scen_path.read_text(encoding="utf-8"))

    # LLM 호출 — 시스템 프롬프트 + (씬 타겟 지정 시 그 씬 한정 지시) + 최근 이력 + 이번 발화
    system = _system_prompt(scenario)
    target = _scene_target(scenario, message)
    if target:
        system += (
            f"\n\n[씬 타겟] 사용자가 씬 {target!r} 를 지목했다. 액션의 scene 값은 반드시 "
            f"{target!r} 로 하고, 다른 씬은 언급하지도 수정하지도 마라."
        )
    messages: list[dict] = [{"role": "system", "content": system}]
    for m in (run.get("chat") or [])[-_HISTORY_WINDOW:]:
        if m.get("role") in ("user", "assistant") and m.get("content"):
            messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": message})

    from wdllm.client import LLMError

    try:
        obj = ask_llm(get_llm(), messages)
    except LLMError as exc:
        raise HTTPException(
            status_code=503, detail=f"LLM 호출 실패 — vLLM 상태를 확인하세요: {exc}"
        ) from exc

    reply = str(obj.get("reply") or "").strip()
    notes: list[str] = []  # 적용 결과·거부 사유를 reply 뒤에 병합한다
    work, applied, rejected, modified, rebuild_requested, qa_request = _apply_actions(
        scenario, obj.get("actions") or []
    )

    rebuilt = False
    if modified:
        doc, errors = _validate(work)
        if errors:
            # 전체 취소 — 원본 scenario.json 은 건드리지 않는다
            applied = []
            notes.append("적용 취소(시나리오 검증 실패): " + "; ".join(errors[:5]))
        else:
            scen_path.write_text(
                json.dumps(doc.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            # 빌드 산출물(scene-data.json·OM_SCENES)이 시나리오를 내장하므로
            # 프리뷰 갱신에는 어떤 수정이든 재빌드가 필요하다.
            build_dir, entry = _rebuild(run, doc)
            rebuilt = True
            runledger.update_run(
                run_id,
                build_dir=str(build_dir),
                entry=entry,
                scenario_summary={
                    "scene_count": len(doc.scenes),
                    "total_dur": round(sum(s.dur for s in doc.scenes), 3),
                    "core_message": doc.meta.core_message,
                },
            )
    elif rebuild_requested:
        doc, errors = _validate(scenario)
        if errors:
            notes.append("재빌드 취소(시나리오 검증 실패): " + "; ".join(errors[:5]))
        else:
            build_dir, entry = _rebuild(run, doc)
            rebuilt = True
            applied.append("재빌드")
            runledger.update_run(run_id, build_dir=str(build_dir), entry=entry)

    if qa_request is not None:
        notes.append(_qa_summary_text(run_id, qa_request))
        applied.append("QA 게이트 실행")

    if rejected:
        notes.append("반영하지 못한 액션: " + "; ".join(rejected))

    if not reply:
        # 소형 모델이 reply 를 생략하는 경우 — 적용 요약으로 대신한다 (실 스모크 실측)
        reply = "요청을 반영했습니다: " + " · ".join(applied) if applied else "(응답 없음)"
    reply = "\n\n".join([reply, *notes])

    now = runledger._now_iso()  # noqa: SLF001 — 원장 타임스탬프 규약 통일
    _append_chat(run_id, [
        {"role": "user", "content": message, "at": now},
        {"role": "assistant", "content": reply, "actions": applied, "rebuilt": rebuilt, "at": now},
    ])
    return {"reply": reply, "applied": applied, "rebuilt": rebuilt}
