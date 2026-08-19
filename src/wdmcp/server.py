# wdmcp 서버 — 경로 A FastMCP stdio 어댑터. 심의·파이프라인·렌더 툴 11종을 봉투로 노출 (LLM 무호출)
from __future__ import annotations

import importlib
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

import structlog
import yaml
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import ValidationError

from wdcore.config import get_settings
from wdcore.errors import WebDesignAgentsError
from wdcore.meetings import MEETING_TEMPLATES, MeetingEngine, MeetingStore
from wdcore.models import (
    Artifact,
    ArtifactType,
    Citation,
    MeetingMeta,
    MeetingTurn,
    MeetingType,
    RoundSpec,
    SpeakerRole,
    Stance,
)
from wdcore.registry.registry import Registry, load_registry

from . import jobs
from .envelope import (
    INSTR_FRAGMENTIZED,
    INSTR_INGESTED,
    INSTR_STATUS,
    briefing_instructions,
    error_envelope,
    meeting_closed_instructions,
    meeting_started_instructions,
    ok_envelope,
    qa_instructions,
    render_status_instructions,
    render_submitted_instructions,
    scenario_built_instructions,
    turn_accepted_instructions,
)
from .schemas import (
    RENDER_TARGETS,
    BriefingCard,
    BriefingFact,
    BriefingOut,
    BriefingRound,
    BriefingSpeaker,
    FragmentizeOut,
    FragmentPreview,
    MeetingCloseOut,
    MeetingStartOut,
    MeetingStatusOut,
    ModuleIndexEntry,
    ModulesDelivery,
    NextSpeakerInfo,
    PersonaDelivery,
    QaGateResult,
    QaRunOut,
    RenderSubmitOut,
    ReportIngestOut,
    RoundInfo,
    ScenarioBuildOut,
    ScenarioPatchOut,
    SceneBrief,
    SceneHtmlOut,
    SceneInfo,
    SceneListOut,
    SceneStillOut,
    SpeakingRules,
    SubmitTurnOut,
    TurnGist,
)
from .session import MeetingLedger, get_session, split_fact_structure

log = structlog.get_logger("wdmcp.server")

REPO_ROOT = Path(__file__).resolve().parents[2]

# HTTP(streamable) 모드는 wdweb 이 loopback 바인드 + Caddy 프록시 뒤에서 서빙하므로
# Host 검증(DNS rebinding 보호)은 끈다 — ThermalShockMCP·LaminateAnalyzerMCP 와 동일 전제.
# stdio 모드(경로 A)에는 이 설정이 영향을 주지 않는다.
mcp = FastMCP(
    name="webdesignagents",
    instructions=(
        "전문가 심의 기반 발표자료(영상/PPT) 자동 생성 플랫폼. 이 서버는 발언을 생성하지 않는다. "
        "일반 흐름: report_ingest → report_fragmentize → meeting_start(참가자 명시)로 심의를 열고 → "
        "클라이언트(당신)가 브리핑의 페르소나를 연기해 턴을 제출하며 → 폐회 후 scenario_build → "
        "render_submit/render_status → qa_run으로 산출물을 검증한다. "
        "각 응답의 claude_instructions를 반드시 따르라."
    ),
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

# ── 코어 서비스 (지연 조립 + 테스트 리셋) ────────────────────────────

_registry: Registry | None = None


def get_registry() -> Registry:
    """페르소나 레지스트리를 지연 로드해 캐시한다. 회의 상태의 진실은 파일이므로 캐시와 무관하다."""
    global _registry
    if _registry is None:
        _registry = load_registry()
    return _registry


def reset_services() -> None:
    """캐시된 레지스트리를 비운다 (테스트에서 WDA_* 환경 변경 후 호출)."""
    global _registry
    _registry = None


def _engine() -> MeetingEngine:
    """호출 시점 설정으로 조립하는 회의 엔진. 회의 상태의 진실은 항상 파일에 있다."""
    return MeetingEngine(MeetingStore(get_settings().meetings_dir), get_registry())


def modules_root() -> Path:
    return Path(os.environ.get("WDA_MODULES_ROOT", str(REPO_ROOT / "modules")))


def _load_module_index() -> list[ModuleIndexEntry]:
    """modules/registry.yaml에서 모듈 축약 인덱스를 만든다 (id·용도 한 줄·props·in_scope)."""
    path = modules_root() / "registry.yaml"
    if not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: list[ModuleIndexEntry] = []
    for m in raw.get("modules", []):
        try:
            out.append(
                ModuleIndexEntry(
                    id=str(m.get("id", "")),
                    type=str(m.get("type", "scene-template")),
                    status=str(m.get("status", "draft")),
                    version=str(m.get("version", "")),
                    nat_default=m.get("nat_default"),
                    summary=str(m.get("summary", "")),
                    props=str(m.get("props", "")),
                    in_scope_hint=str(m.get("in_scope_hint", "")),
                )
            )
        except ValidationError:  # 인덱스 1행 오류가 브리핑 전체를 막지 않는다
            continue
    return out


# ── 파이프라인 run 파일 (파일이 진실) ─────────────────────────────────


def _run_dir(run_id: str) -> Path:
    return get_settings().pipeline_dir / run_id


def _new_run_id() -> str:
    return f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def _load_fragments(run_id: str) -> list[dict]:
    """data/pipeline/{run_id}/fragments.json을 로드한다. 없으면 FileNotFoundError."""
    path = _run_dir(run_id) / "fragments.json"
    if not path.is_file():
        raise FileNotFoundError(f"fragments.json 없음: {path}")
    frags = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(frags, list):
        raise ValueError(f"fragments.json 형식 오류(리스트 아님): {path}")
    return frags


def _lazy_import(module: str):
    """병렬 개발 중인 모듈의 지연 import. (module | None, 오류 문자열 | None)을 반환한다."""
    try:
        return importlib.import_module(module), None
    except Exception as exc:  # ImportError 포함 — 미완성/문법 오류 모두 봉투로 강등
        return None, f"{type(exc).__name__}: {exc}"


# ── 회의 헬퍼 ────────────────────────────────────────────────────────

_TOKEN_RE = re.compile(r"[0-9A-Za-z가-힣]{2,}")


def _score_fragment(frag_text: str, query_tokens: set[str]) -> int:
    return len(set(_TOKEN_RE.findall(frag_text)) & query_tokens)


def _recent_turns(turns: list[MeetingTurn], n: int = 3) -> list[TurnGist]:
    """최근 n턴의 요지 (브리핑·현황 표시용)."""
    out: list[TurnGist] = []
    for t in turns[-n:]:
        first_line = (t.content_md.strip().splitlines() or [""])[0]
        out.append(
            TurnGist(
                turn_no=t.turn_no,
                speaker=t.expert_id or t.role.value,
                stance=t.stance,
                gist=first_line[:150],
            )
        )
    return out


def _next_speaker_info(
    engine: MeetingEngine, meta: MeetingMeta, turns: list[MeetingTurn]
) -> NextSpeakerInfo | None:
    """다음 발언자 요약. 폐회됐거나 전 라운드 종료면 None."""
    try:
        role, expert_id, spec, _ = engine.next_speaker(meta, turns)
    except ValueError:
        return None
    return NextSpeakerInfo(
        role=role.value, expert_id=expert_id, round_no=meta.round_index, round_name=spec.name,
    )


def _speaking_rules(spec: RoundSpec, round_no: int) -> SpeakingRules:
    return SpeakingRules(
        round_no=round_no,
        round_name=spec.name,
        citation_required=spec.citation_required,
        stance_enum=list(get_args(Stance)),
        artifact_types=[a.value for a in ArtifactType],
        length_hint="200~1500자, 1인칭, 자기 도메인 관점 유지",
        citation_note="citations의 ref에는 이 회의 브리핑으로 전달된 카드 ID 또는 조각(frag) ID만 쓸 수 있다.",
    )


_TIER_ORDER = {"core": 0, "checklist": 1, "failure_mode": 2, "deep": 3}


def _cards_for_briefing(persona_id: str, ledger: MeetingLedger, top_k: int = 3):
    """발언 페르소나의 지식카드 top_k — 신규는 본문 full, 기전달은 ID recall."""
    cards = get_registry().cards_for(persona_id)
    cards = sorted(cards, key=lambda c: (_TIER_ORDER.get(c.tier.value, 9), c.id))[:top_k]
    new_cards = [c for c in cards if c.id not in ledger.delivered_cards]
    already = sorted(c.id for c in cards if c.id in ledger.delivered_cards)
    return new_cards, already


def _facts_for_briefing(
    ledger: MeetingLedger, query: str, top_k: int = 5
) -> list[BriefingFact]:
    """run 조각 중 미전달분을 단순 키워드 겹침으로 top_k 선별해 [F#] 마커로 전달한다."""
    if not ledger.run_id:
        return []
    try:
        frags = _load_fragments(ledger.run_id)
    except (FileNotFoundError, ValueError):
        return []
    qtokens = set(_TOKEN_RE.findall(query))
    fresh = [f for f in frags if str(f.get("frag_id", "")) not in ledger.delivered_fragments]
    ranked = sorted(
        fresh,
        key=lambda f: (-_score_fragment(str(f.get("text", "")), qtokens), str(f.get("frag_id"))),
    )[:top_k]
    markers = ledger.next_fact_markers(len(ranked))
    facts: list[BriefingFact] = []
    for m, f in zip(markers, ranked):
        frag_id = str(f.get("frag_id", ""))
        src = f.get("source") or {}
        source = (
            f"p.{src.get('page')} {src.get('block_id', '')}".strip()
            if isinstance(src, dict)
            else str(src)
        )
        # 구조 조각은 요약 한 줄을 structured 로 분리한다 (text 는 요약을 뗀 본문)
        summary, body = split_fact_structure(f)
        facts.append(
            BriefingFact(
                marker=m,
                ref=frag_id,
                type=str(f.get("type", "")),
                text=body,
                source=source,
                confidence=f.get("confidence"),
                widget=str(f.get("widget") or f.get("widget_type") or ""),
                structured=summary,
            )
        )
    return facts


# ── 회의 툴 5종 ───────────────────────────────────────────────────────


def _roster_line() -> str:
    """로스터 한 줄. 힌트를 만드는 모든 자리가 이걸 쓴다.

    ⚠ 예전에는 participants 가 빈 배열일 때만 로스터를 알려 줬다. 유효하지 않은 id 를
    넣으면 PERSONA_NOT_FOUND 의 hint 가 빈 문자열이라, 클라이언트는 무엇이 유효한지
    알 방법이 없었다 — 두 분기 위에 로스터가 있는데도. 실제로 외부 Claude 가 그럴듯한
    id 를 여덟 개 시도하다 "페르소나 등록이 안 돼 있다"고 결론내고 포기했다.
    """
    return ", ".join(f"{x.id}({x.abbr})" for x in get_registry().summaries())


@mcp.tool()
def meeting_personas() -> dict:
    """회의에 넣을 수 있는 페르소나 로스터. meeting_start 의 participants 에 쓸 id 목록이다.

    회의를 열기 전에 이걸 먼저 부르면 된다. 종전에는 유효한 id 를 알아내는 방법이
    'participants 를 빈 배열로 보내 오류를 유발하는 것' 뿐이었다.
    """
    state = get_session()
    rows = [
        {
            "id": x.id,
            "abbr": x.abbr,
            "category": x.category,
            "name_ko": x.name_ko,
            "name_en": x.name_en,
            "status": x.status.value if hasattr(x.status, "value") else str(x.status),
            "boundary_statement": x.boundary_statement,
        }
        for x in get_registry().summaries()
    ]
    return ok_envelope(
        state,
        {"count": len(rows), "personas": rows,
         "meeting_types": [t.value for t in MeetingType]},
        "이 중 5~8인을 골라 meeting_start(participants=[id,...]) 로 회의를 연다. "
        "확정한 순서가 곧 발언 순서다.",
    )


@mcp.tool()
def meeting_start(
    topic: str, type: str, participants: list[str], run_id: str | None = None
) -> dict:
    """회의를 생성한다. participants(페르소나 id 배열)는 명시 필수 — 확정 순서가 곧 발언 순서다.

    run_id를 주면 data/pipeline/{run_id}/fragments.json의 frag_id들이 브리핑 [F#] 근거이자
    인용 화이트리스트(known_refs)의 원천이 된다.
    """
    state = get_session()
    try:
        mtype = MeetingType(type)
    except ValueError:
        return error_envelope(
            state,
            "INVALID_TYPE",
            f"지원하지 않는 회의 유형: {type!r}",
            f"type은 {'/'.join(t.value for t in MeetingType)} 중 하나다.",
        )
    if not participants:
        return error_envelope(
            state,
            "PARTICIPANTS_REQUIRED",
            "participants가 비어 있다. 참가 페르소나를 명시해야 회의를 생성할 수 있다.",
            f"meeting_personas 로 목록을 받을 수 있다. 로스터: {_roster_line()}",
        )
    fragments_loaded = 0
    if run_id:
        try:
            fragments_loaded = len(_load_fragments(run_id))
        except (FileNotFoundError, ValueError) as exc:
            return error_envelope(
                state, "RUN_NOT_FOUND", str(exc),
                "report_ingest → report_fragmentize로 run을 먼저 만들거나 run_id를 빼고 호출하라.",
            )
    engine = _engine()
    try:
        meta = engine.create(mtype, topic, participants)
    except WebDesignAgentsError as exc:
        # 힌트 없이 코드만 돌려주면 클라이언트는 무엇을 고쳐야 하는지 모른다.
        return error_envelope(
            state, exc.error_code.upper(), exc.message,
            f"유효한 id 는 이것뿐이다(meeting_personas 로도 받을 수 있다). "
            f"로스터: {_roster_line()}",
        )
    except ValueError as exc:
        return error_envelope(
            state, "INVALID_PARTICIPANTS", str(exc),
            f"meeting_personas 로 목록을 확인하라. 로스터: {_roster_line()}",
        )
    ledger = state.ledger(meta.id)
    ledger.run_id = run_id
    data = MeetingStartOut(
        meeting_id=meta.id,
        type=meta.type.value,
        topic=meta.topic,
        participants=list(meta.participants),
        run_id=run_id,
        fragments_loaded=fragments_loaded,
        rounds=[
            RoundInfo(
                round_no=i,
                name=s.name,
                speaker_order=s.speaker_order,
                cycles=s.cycles,
                citation_required=s.citation_required,
            )
            for i, s in enumerate(MEETING_TEMPLATES[meta.type])
        ],
        next_speaker=_next_speaker_info(engine, meta, []),
    )
    return ok_envelope(
        state, data.model_dump(mode="json"), meeting_started_instructions(meta.type.value)
        , meta.id
    )


@mcp.tool()
def meeting_get_briefing(meeting_id: str) -> dict:
    """다음 발언자를 결정하고 그 발언자용 브리핑을 반환한다.

    브리핑 = 라운드 지시 + 페르소나 델타(최초 full → 이후 recall) + 지식카드 + 조각 [F#] +
    모듈 축약 인덱스(회의당 최초 1회 full → 이후 ID recall) + 최근 턴 요지.
    전달된 카드/조각 ID는 인용 화이트리스트(known_refs)에 축적된다.
    """
    state = get_session()
    engine = _engine()
    try:
        meta, turns = engine.store.load(meeting_id)
    except FileNotFoundError as exc:
        return error_envelope(
            state, "NOT_FOUND", str(exc), "meeting_start가 반환한 meeting_id를 사용하라."
        )
    try:
        role, expert_id, spec, instruction = engine.next_speaker(meta, turns)
    except ValueError as exc:
        return error_envelope(
            state, "NO_NEXT_SPEAKER", str(exc), "meeting_close를 호출해 회의록을 생성하라."
        )

    ledger = state.ledger(meeting_id)
    recent = _recent_turns(turns)

    # 모듈 축약 인덱스 — 회의당 최초 1회만 full, 이후 ID recall (PLAN §6.3 토큰 최소화)
    index = _load_module_index()
    if not ledger.modules_delivered:
        ledger.modules_delivered = True
        modules = ModulesDelivery(
            delivery="full", index=index, module_ids=[m.id for m in index]
        )
    else:
        modules = ModulesDelivery(
            delivery="recall",
            module_ids=[m.id for m in index],
            recall="모듈 축약 인덱스는 이 회의에서 이미 전달되었다. ID로 참조하라.",
        )

    common = dict(
        meeting_id=meeting_id,
        topic=meta.topic,
        meeting_type=meta.type.value,
        round=BriefingRound(
            round_no=meta.round_index,
            name=spec.name,
            instruction=instruction,
            citation_required=spec.citation_required,
        ),
        modules=modules,
        recent_turns=recent,
        speaking_rules=_speaking_rules(spec, meta.round_index),
    )

    if role is SpeakerRole.moderator:
        data = BriefingOut(
            **common,
            speaker=BriefingSpeaker(role=role.value),
            persona=PersonaDelivery(
                delivery="none",
                note="모더레이터는 고정 역할이다. 참가자 발언의 요약·군집화·중재만 하고 새 기술 주장을 만들지 않는다.",
            ),
        )
        return ok_envelope(
            state,
            data.model_dump(mode="json"),
            briefing_instructions(
                "moderator", None, None, meta.round_index, False,
                meta.type.value, spec.citation_required,
            ),
        )

    persona = get_registry().get(expert_id)
    first_delivery = expert_id not in ledger.delivered_personas
    ledger.delivered_personas.add(expert_id)

    new_cards, already = _cards_for_briefing(expert_id, ledger)
    cards = [
        BriefingCard(
            card_id=c.id, title=c.title, confidence=c.confidence.value, body_md=c.body_md
        )
        for c in new_cards
    ]
    query = " ".join([meta.topic, instruction] + [r.gist for r in recent])
    facts = _facts_for_briefing(ledger, query)

    ledger.delivered_cards.update(c.card_id for c in cards)
    ledger.delivered_fragments.update(f.ref for f in facts)
    ledger.known_refs.update(c.card_id for c in cards)
    ledger.known_refs.update(f.ref for f in facts)

    if first_delivery:
        pd = PersonaDelivery(delivery="full", system_prompt=persona.persona.system_prompt)
    else:
        pd = PersonaDelivery(
            delivery="recall",
            recall=f"'{persona.name_ko}'({expert_id}) 페르소나는 이 회의에서 이미 전달되었다. 유지하라.",
        )
    data = BriefingOut(
        **common,
        speaker=BriefingSpeaker(role=role.value, expert_id=expert_id, name_ko=persona.name_ko),
        persona=pd,
        cards=cards,
        already_delivered_cards=already,
        facts=facts,
    )
    return ok_envelope(
        state,
        data.model_dump(mode="json"),
        briefing_instructions(
            "expert", persona.name_ko, expert_id, meta.round_index, first_delivery,
            meta.type.value, spec.citation_required,
        ),
    )


@mcp.tool()
def meeting_submit_turn(
    meeting_id: str,
    round_no: int,
    role: str,
    content_md: str,
    expert_id: str | None = None,
    stance: str | None = None,
    citations: list[dict] | None = None,
    artifacts: list[dict] | None = None,
) -> dict:
    """발언 턴을 엔진 검증(차례·라운드·인용 필수·known_refs 실존)을 거쳐 기록한다.

    거부되면 ok=false와 TURN_REJECTED 사유·hint를 반환한다. 통과하면 다음 발언자를 예고한다.
    citations 원소는 {"ref","quote"}, artifacts 원소는 {"type","content","owner_expert_id"?} 형식이다.
    """
    state = get_session()
    engine = _engine()
    try:
        meta, _ = engine.store.load(meeting_id)
    except FileNotFoundError as exc:
        return error_envelope(
            state, "NOT_FOUND", str(exc), "meeting_start가 반환한 meeting_id를 사용하라."
        )
    try:
        turn = MeetingTurn(
            round_no=round_no,
            role=SpeakerRole(role),
            expert_id=expert_id,
            stance=stance,
            content_md=content_md,
            citations=[Citation.model_validate(c) for c in citations or []],
            artifacts=[Artifact.model_validate(a) for a in artifacts or []],
        )
    except (ValidationError, ValueError) as exc:
        return error_envelope(
            state, "INVALID_TURN", str(exc), "브리핑 speaking_rules의 필드 규약에 맞춰 다시 제출하라."
        )
    ledger = state.ledger(meeting_id)
    try:
        accepted = engine.submit_turn(meta, turn, ledger.known_refs)
    except ValueError as exc:
        return error_envelope(
            state,
            "TURN_REJECTED",
            str(exc),
            "거부 사유를 반영해 수정 후 재제출하라. 인용은 브리핑으로 전달된 카드/조각 ref만 쓸 수 있다. "
            "차례가 불확실하면 meeting_get_briefing으로 현재 발언자를 다시 확인하라.",
        )
    _, turns = engine.store.load(meeting_id)
    next_info = _next_speaker_info(engine, meta, turns)
    data = SubmitTurnOut(
        turn_no=accepted.turn_no,
        status=meta.status.value,
        round_no=meta.round_index,
        next_speaker=next_info,
    )
    return ok_envelope(state, data.model_dump(mode="json"), turn_accepted_instructions(next_info), meeting_id)


@mcp.tool()
def meeting_status(meeting_id: str) -> dict:
    """회의 진행 현황(라운드·턴 수·최근 논점·다음 발언자·전달 원장)을 요약한다."""
    state = get_session()
    engine = _engine()
    try:
        meta, turns = engine.store.load(meeting_id)
    except FileNotFoundError as exc:
        return error_envelope(
            state, "NOT_FOUND", str(exc), "meeting_start가 반환한 meeting_id를 사용하라."
        )
    specs = MEETING_TEMPLATES[meta.type]
    ledger = state.ledger(meeting_id)
    data = MeetingStatusOut(
        meeting_id=meta.id,
        topic=meta.topic,
        type=meta.type.value,
        status=meta.status.value,
        participants=list(meta.participants),
        round_index=meta.round_index,
        total_rounds=len(specs),
        current_round=specs[meta.round_index].name if meta.round_index < len(specs) else None,
        turns_total=len(turns),
        recent_turns=_recent_turns(turns),
        next_speaker=_next_speaker_info(engine, meta, turns),
        delivered_personas=sorted(ledger.delivered_personas),
        known_refs_count=len(ledger.known_refs),
        modules_delivered=ledger.modules_delivered,
    )
    return ok_envelope(state, data.model_dump(mode="json"), INSTR_STATUS, meeting_id)


@mcp.tool()
def meeting_close(meeting_id: str) -> dict:
    """회의를 폐회하고 회의록(minutes.md)을 생성해 경로와 요약 통계를 반환한다."""
    state = get_session()
    engine = _engine()
    try:
        meta, turns = engine.store.load(meeting_id)
    except FileNotFoundError as exc:
        return error_envelope(
            state, "NOT_FOUND", str(exc), "meeting_start가 반환한 meeting_id를 사용하라."
        )
    try:
        path = engine.close(meta, turns)
    except ValueError as exc:
        return error_envelope(state, "ALREADY_CLOSED", str(exc))
    decisions = sum(1 for t in turns for a in t.artifacts if a.type is ArtifactType.decision)
    data = MeetingCloseOut(
        meeting_id=meta.id,
        status=meta.status.value,
        closed_at=meta.closed_at.isoformat() if meta.closed_at else None,
        turns_total=len(turns),
        decisions=decisions,
        action_items=sum(
            1 for t in turns for a in t.artifacts if a.type is ArtifactType.action_item
        ),
        open_issues=sum(
            1 for t in turns for a in t.artifacts if a.type is ArtifactType.open_issue
        ),
        minutes_path=str(path),
    )
    return ok_envelope(
        state, data.model_dump(mode="json"),
        meeting_closed_instructions(meta.type.value, decisions),
    )


# ── 파이프라인 툴 4종 (wdpipeline 지연 import — 병렬 개발 계약) ────────


@mcp.tool()
def report_ingest(file: str, assets_dir: str | None = None, run_id: str | None = None) -> dict:
    """ReportArchive 복붙 JSON 파일을 정규화해 data/pipeline/{run_id}/report.norm.json으로 저장한다."""
    state = get_session()
    mod, err = _lazy_import("wdpipeline.ingest")
    if mod is None:
        return error_envelope(
            state, "PIPELINE_UNAVAILABLE",
            f"wdpipeline.ingest를 불러올 수 없다: {err}",
            "wdpipeline 모듈이 아직 구현 중일 수 있다. 구현 완료 후 다시 호출하라.",
        )
    src = Path(file)
    if not src.is_file():
        return error_envelope(
            state, "FILE_NOT_FOUND", f"보고서 파일 없음: {src}",
            "ReportArchive에서 복사한 report_archive_draft_v1 JSON 파일 경로를 넘겨라.",
        )
    rid = run_id or _new_run_id()
    try:
        norm = mod.ingest_report_file(src, Path(assets_dir) if assets_dir else None)
    except Exception as exc:
        return error_envelope(state, "INGEST_FAILED", f"{type(exc).__name__}: {exc}")
    run_dir = _run_dir(rid)
    run_dir.mkdir(parents=True, exist_ok=True)
    norm_path = run_dir / "report.norm.json"
    norm_path.write_text(json.dumps(norm, ensure_ascii=False, indent=2), encoding="utf-8")
    data = ReportIngestOut(
        run_id=rid,
        doc_id=norm.get("doc_id"),
        title=str(norm.get("title", "")),
        pages=len(norm.get("pages", [])),
        norm_path=str(norm_path),
    )
    return ok_envelope(state, data.model_dump(mode="json"), INSTR_INGESTED)


@mcp.tool()
def report_fragmentize(run_id: str) -> dict:
    """정규화 보고서를 Claim/Evidence/Case/Metric/CTA 조각으로 분해해 fragments.json으로 저장한다.

    frag_id 목록은 이후 회의(meeting_start run_id=...)의 인용 화이트리스트가 된다.
    """
    state = get_session()
    mod, err = _lazy_import("wdpipeline.fragmentize")
    if mod is None:
        return error_envelope(
            state, "PIPELINE_UNAVAILABLE",
            f"wdpipeline.fragmentize를 불러올 수 없다: {err}",
            "wdpipeline 모듈이 아직 구현 중일 수 있다. 구현 완료 후 다시 호출하라.",
        )
    norm_path = _run_dir(run_id) / "report.norm.json"
    if not norm_path.is_file():
        return error_envelope(
            state, "RUN_NOT_FOUND", f"report.norm.json 없음: {norm_path}",
            "report_ingest를 먼저 호출해 run을 만들어라.",
        )
    norm = json.loads(norm_path.read_text(encoding="utf-8"))
    try:
        frags = mod.fragmentize(norm)
    except Exception as exc:
        return error_envelope(state, "FRAGMENTIZE_FAILED", f"{type(exc).__name__}: {exc}")
    frags_path = _run_dir(run_id) / "fragments.json"
    frags_path.write_text(json.dumps(frags, ensure_ascii=False, indent=2), encoding="utf-8")
    by_type: dict[str, int] = {}
    for f in frags:
        by_type[str(f.get("type", "?"))] = by_type.get(str(f.get("type", "?")), 0) + 1
    data = FragmentizeOut(
        run_id=run_id,
        fragments_total=len(frags),
        by_type=by_type,
        preview=[
            FragmentPreview(
                frag_id=str(f.get("frag_id", "")),
                type=str(f.get("type", "")),
                text=str(f.get("text", ""))[:120],
            )
            for f in frags[:5]
        ],
        fragments_path=str(frags_path),
    )
    return ok_envelope(state, data.model_dump(mode="json"), INSTR_FRAGMENTIZED)


@mcp.tool()
def scenario_build(meeting_id: str, run_id: str | None = None) -> dict:
    """회의 산출물(decision·scenario_patch)을 집계하고 규칙 기반 ScenarioDoc을 조립·검증·저장한다.

    run_id 미지정 시 meeting_start에 연결했던 run을 쓴다. 산출은 data/pipeline/{run_id}/scenario.json.
    """
    state = get_session()
    mod, err = _lazy_import("wdpipeline.scenario")
    if mod is None:
        return error_envelope(
            state, "PIPELINE_UNAVAILABLE",
            f"wdpipeline.scenario를 불러올 수 없다: {err}",
            "wdpipeline 모듈이 아직 구현 중일 수 있다. 구현 완료 후 다시 호출하라.",
        )
    engine = _engine()
    try:
        meta, turns = engine.store.load(meeting_id)
    except FileNotFoundError as exc:
        return error_envelope(
            state, "NOT_FOUND", str(exc), "meeting_start가 반환한 meeting_id를 사용하라."
        )
    rid = run_id or state.ledger(meeting_id).run_id
    if not rid:
        return error_envelope(
            state, "RUN_REQUIRED",
            "이 회의에 연결된 run이 없다. run_id를 명시하라.",
            "report_ingest → report_fragmentize로 만든 run_id를 넘겨라.",
        )
    run_dir = _run_dir(rid)
    norm_path = run_dir / "report.norm.json"
    if not norm_path.is_file():
        return error_envelope(
            state, "RUN_NOT_FOUND", f"report.norm.json 없음: {norm_path}",
            "report_ingest를 먼저 호출해 run을 만들어라.",
        )
    try:
        fragments = _load_fragments(rid)
    except (FileNotFoundError, ValueError) as exc:
        return error_envelope(
            state, "RUN_NOT_FOUND", str(exc), "report_fragmentize를 먼저 호출하라."
        )
    norm = json.loads(norm_path.read_text(encoding="utf-8"))

    decisions = [
        a.content for t in turns for a in t.artifacts if a.type is ArtifactType.decision
    ]
    patches = [
        a.content for t in turns for a in t.artifacts if a.type is ArtifactType.scenario_patch
    ]
    try:
        doc = mod.assemble_demo_scenario(norm, fragments)
        doc = doc.model_copy(
            update={"meta": doc.meta.model_copy(update={"meeting_id": meeting_id})}
        )
        errors = mod.validate_scenario(doc, modules_root())
    except Exception as exc:
        return error_envelope(state, "SCENARIO_FAILED", f"{type(exc).__name__}: {exc}")
    scenario_path = run_dir / "scenario.json"
    scenario_path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    data = ScenarioBuildOut(
        meeting_id=meeting_id,
        run_id=rid,
        scenario_path=str(scenario_path),
        core_message=doc.meta.core_message,
        duration_sec=doc.meta.duration_sec,
        scene_count=len(doc.scenes),
        scenes=[SceneBrief(name=s.name, dur=s.dur, tpl=s.tpl) for s in doc.scenes],
        validation_errors=list(errors),
        meeting_decisions=decisions,
        scenario_patches=len(patches),
    )
    return ok_envelope(state, data.model_dump(mode="json"), scenario_built_instructions(list(errors)))


# ── 렌더 툴 2종 ───────────────────────────────────────────────────────


@mcp.tool()
def render_submit(
    scenario_path: str | None = None,
    targets: list[str] | None = None,
    build_dir: str | None = None,
    entry: str | None = None,
    fps: int | None = None,
) -> dict:
    """렌더 잡을 등록한다 — 백그라운드 스레드가 (필요 시) 빌드 후 mp4/PPTX를 export 한다.

    scenario_path(ScenarioDoc JSON) 또는 build_dir(기성 렌더 패키지 + entry) 중 하나를 넘겨라.
    targets 기본 ["video"], 허용 값 video/pptx. 상태는 data/render_jobs/{job_id}.json에 기록되며
    render_status로 폴링한다.
    """
    state = get_session()
    targets = targets or ["video"]
    bad = [t for t in targets if t not in RENDER_TARGETS]
    if bad:
        return error_envelope(
            state, "INVALID_TARGETS", f"지원하지 않는 target: {bad}",
            f"targets는 {list(RENDER_TARGETS)}의 부분집합이다.",
        )
    if bool(scenario_path) == bool(build_dir):
        return error_envelope(
            state, "INVALID_INPUT",
            "scenario_path와 build_dir 중 정확히 하나를 지정해야 한다.",
            "시나리오에서 빌드하려면 scenario_path, 기성 빌드를 렌더하려면 build_dir+entry.",
        )
    if scenario_path:
        sp = Path(scenario_path)
        if not sp.is_file():
            return error_envelope(
                state, "FILE_NOT_FOUND", f"scenario 파일 없음: {sp}",
                "scenario_build가 반환한 scenario_path를 사용하라.",
            )
        # 잡 실패를 미루지 않는다 — 빌더 가용성과 문서 유효성을 접수 시점에 검사
        mod, err = _lazy_import("wdpipeline.build")
        if mod is None:
            return error_envelope(
                state, "PIPELINE_UNAVAILABLE",
                f"wdpipeline.build를 불러올 수 없다: {err}",
                "wdpipeline 모듈이 아직 구현 중일 수 있다. build_dir 경로로는 렌더가 가능하다.",
            )
        from wdcore.models.scenario import ScenarioDoc

        try:
            ScenarioDoc.model_validate_json(sp.read_text(encoding="utf-8"))
        except ValidationError as exc:
            return error_envelope(
                state, "INVALID_SCENARIO", str(exc), "scenario_build로 유효한 문서를 다시 만들어라."
            )
    else:
        bd = Path(build_dir)
        if not bd.is_dir():
            return error_envelope(state, "BUILD_DIR_NOT_FOUND", f"빌드 디렉터리 없음: {bd}")
        if entry is None:
            candidates = sorted(bd.glob("*.dc.html")) or [bd / "index.html"]
            if not candidates[0].is_file():
                return error_envelope(
                    state, "ENTRY_NOT_FOUND",
                    f"엔트리 HTML을 찾지 못했다: {bd}",
                    "entry에 빌드 디렉터리 기준 엔트리 파일명을 명시하라.",
                )
            entry = candidates[0].name
        elif not (bd / entry).is_file():
            return error_envelope(state, "ENTRY_NOT_FOUND", f"엔트리 없음: {bd / entry}")
    job = jobs.submit_render_job(
        targets=targets, scenario_path=scenario_path, build_dir=build_dir, entry=entry, fps=fps,
    )
    data = RenderSubmitOut(
        job_id=job.job_id,
        status=job.status,
        targets=job.targets,
        job_path=str(jobs.job_path(job.job_id)),
    )
    return ok_envelope(state, data.model_dump(mode="json"), render_submitted_instructions(job.job_id))


def _artifact_urls(job) -> dict[str, str]:
    """산출물별 열람 URL — 파일 경로만으로는 챗·브라우저에서 볼 수 없어 함께 돌려준다.

    앞에 붙는 $ROOT_PATH 는 런처가 주는 서브패스(예: /apps/web_design_agents)다. 그래서
    반환값을 그대로 마크다운 링크로 쓰면 포털 오리진에서 열리고(세션 쿠키 실림) 챗은
    영상 링크를 인라인 플레이어로 렌더한다. ROOT_PATH 가 없으면(로컬 직접 실행) 루트 기준.
    """
    root = (os.environ.get("ROOT_PATH") or "").rstrip("/")
    return {
        kind: f"{root}/api/render_jobs/{job.job_id}/download/{kind}"
        for kind in (job.outputs or {})
        if kind in ("video", "pptx")
    }


@mcp.tool()
def render_status(job_id: str) -> dict:
    """렌더 잡 상태·산출물 경로/열람 URL을 조회한다 (data/render_jobs/{job_id}.json이 진실)."""
    state = get_session()
    job = jobs.read_job(job_id)
    if job is None:
        return error_envelope(
            state, "NOT_FOUND", f"렌더 잡 없음: {job_id}",
            "render_submit이 반환한 job_id를 사용하라.",
        )
    data = {**job.model_dump(mode="json"), "urls": _artifact_urls(job)}
    return ok_envelope(state, data, render_status_instructions(job.status))


# ── QA 툴 1종 (wdqa 지연 import — 병렬 개발 계약) ─────────────────────


@mcp.tool()
def qa_run(build_path: str, gates: list[str] | None = None, scenario_path: str | None = None) -> dict:
    """빌드 디렉터리에 품질 게이트를 실행해 리포트를 반환한다.

    리포트는 지식카드로 등록되어 다음 심의의 인용 근거가 된다 (PLAN §7).
    """
    state = get_session()
    mod, err = _lazy_import("wdqa.gates")
    if mod is None:
        return error_envelope(
            state, "QA_UNAVAILABLE",
            f"wdqa.gates를 불러올 수 없다: {err}",
            "wdqa 모듈이 아직 구현 중일 수 있다. 구현 완료 후 다시 호출하라.",
        )
    bd = Path(build_path)
    if not bd.is_dir():
        return error_envelope(state, "BUILD_DIR_NOT_FOUND", f"빌드 디렉터리 없음: {bd}")
    scenario: dict | None = None
    if scenario_path:
        sp = Path(scenario_path)
        if not sp.is_file():
            return error_envelope(state, "FILE_NOT_FOUND", f"scenario 파일 없음: {sp}")
        scenario = json.loads(sp.read_text(encoding="utf-8"))
    try:
        report = mod.run_gates(bd, scenario=scenario, gates=gates)
    except Exception as exc:
        return error_envelope(state, "QA_FAILED", f"{type(exc).__name__}: {exc}")
    data = QaRunOut(
        build_path=str(bd),
        gates=gates,
        passed=bool(report.get("passed")),
        results=[QaGateResult.model_validate(r) for r in report.get("results", [])],
    )
    return ok_envelope(state, data.model_dump(mode="json"), qa_instructions(data.passed))


# ── 씬 툴 4종 (핀포인트 수정 — PLAN §5.9, wdweb.scenes/wdpipeline.patch 지연 import) ──


def _scene_run_paths(run_id: str) -> tuple[Path | None, Path | None, dict | None]:
    """run_id → (build_dir, scenario_path, 웹 원장 run|None).

    웹 콘솔 원장(data/web_runs)을 우선 조회하고, 없으면 MCP 파이프라인 run
    (data/pipeline/{run_id})으로 폴백한다 — 두 경로 모두 scenario.json 이 진실이다.
    """
    webruns, _err = _lazy_import("wdweb.runs")
    if webruns is not None:
        try:
            web_run = webruns.read_run(run_id)
        except Exception:  # noqa: BLE001 — 원장 조회 실패는 파이프라인 폴백으로
            web_run = None
        if web_run is not None:
            scen = webruns.data_dir() / "pipeline" / run_id / "scenario.json"
            bd = (
                Path(web_run["build_dir"])
                if web_run.get("build_dir")
                else webruns.data_dir() / "build" / web_run["slug"]
            )
            return bd, scen, web_run
    scen = _run_dir(run_id) / "scenario.json"
    if scen.is_file():
        return get_settings().data_dir / "build" / run_id, scen, None
    return None, None, None


def _ensure_scene_build(bd: Path, scen_path: Path) -> tuple[Path | None, str | None]:
    """빌드 산출물이 없거나 시나리오보다 낡았으면 재빌드한다. (엔트리 경로, 오류)."""
    entry = bd / "index.html"
    if entry.is_file() and entry.stat().st_mtime >= scen_path.stat().st_mtime:
        return entry, None
    mod, err = _lazy_import("wdpipeline.build")
    if mod is None:
        return None, f"wdpipeline.build 를 불러올 수 없다: {err}"
    from wdcore.models.scenario import ScenarioDoc

    try:
        doc = ScenarioDoc.model_validate_json(scen_path.read_text(encoding="utf-8"))
        return Path(mod.build_render_package(doc, bd)), None
    except Exception as exc:  # noqa: BLE001 — 빌드 실패는 봉투로 강등
        return None, f"{type(exc).__name__}: {exc}"


def _scene_ctx(state, run_id: str):
    """씬 툴 공용 전처리 — (build_dir, scenario_path, web_run, 오류 봉투|None)."""
    bd, scen, web_run = _scene_run_paths(run_id)
    if bd is None or scen is None or not scen.is_file():
        return None, None, None, error_envelope(
            state, "RUN_NOT_FOUND", f"run 을 찾지 못했다: {run_id}",
            "웹 콘솔 실행(wr-*) 또는 scenario_build 를 마친 파이프라인 run_id 를 넘겨라.",
        )
    mod, err = _lazy_import("wdweb.scenes")
    if mod is None:
        return None, None, None, error_envelope(
            state, "SCENES_UNAVAILABLE", f"wdweb.scenes 를 불러올 수 없다: {err}",
            "wdweb 모듈이 아직 구현 중일 수 있다. 구현 완료 후 다시 호출하라.",
        )
    _entry, berr = _ensure_scene_build(bd, scen)
    if berr:
        return None, None, None, error_envelope(state, "BUILD_FAILED", berr)
    return bd, scen, web_run, None


@mcp.tool()
def scene_list(run_id: str) -> dict:
    """씬 목록(name/tpl/dur/내레이션·데이터 요약)을 반환한다 — 핀포인트 수정의 탐색 진입점.

    잘못 만들어진 씬을 찾으면 scene_html/scene_still 로 확인하고 scenario_patch 로 고쳐라.
    """
    state = get_session()
    bd, _scen, _web, err = _scene_ctx(state, run_id)
    if err:
        return err
    scenes_mod, _ = _lazy_import("wdweb.scenes")
    try:
        rows = scenes_mod.list_scenes(bd)
    except Exception as exc:  # noqa: BLE001
        return error_envelope(state, "SCENE_LIST_FAILED", f"{type(exc).__name__}: {exc}")
    data = SceneListOut(
        run_id=run_id, build_dir=str(bd), count=len(rows),
        scenes=[SceneInfo.model_validate(r) for r in rows],
    )
    return ok_envelope(
        state, data.model_dump(mode="json"),
        "씬 목록이다. 수정 대상 씬을 특정했으면 scene_html(자립형)으로 화면을 확인하거나 "
        "scenario_patch 의 ops(set_data/set_narration/set_dur/set_tpl/set_stills/reorder/"
        "remove_scene/insert_scene)로 핀포인트 수정하라.",
    )


@mcp.tool()
def scene_html(run_id: str, scene: str, mode: str = "self", still: float | None = None) -> dict:
    """씬 하나만 도는 엔트리 HTML 을 파일로 저장하고 경로를 반환한다.

    mode="self"(기본)는 JS·토큰·데이터·폰트를 전부 인라인한 자립형 단일 html —
    http 서빙 없이 file:// 로도 열린다 (chat 임베드·파일 첨부용, 수 MB).
    mode="light"는 빌드 상대 자원 참조 경량판이다. still 지정 시 그 시각에서 정지한다.
    """
    state = get_session()
    if mode not in ("light", "self"):
        return error_envelope(state, "INVALID_MODE", f"mode 는 light|self 다: {mode!r}")
    bd, _scen, _web, err = _scene_ctx(state, run_id)
    if err:
        return err
    scenes_mod, _ = _lazy_import("wdweb.scenes")
    try:
        html = scenes_mod.scene_entry_html(bd, scene, still=still, mode=mode)
    except KeyError as exc:
        return error_envelope(state, "SCENE_NOT_FOUND", str(exc.args[0]),
                              "scene_list 로 씬 이름을 확인하라.")
    except Exception as exc:  # noqa: BLE001
        return error_envelope(state, "SCENE_HTML_FAILED", f"{type(exc).__name__}: {exc}")
    out = bd / f"scene-{scenes_mod.safe_name(scene)}.{mode}.html"
    out.write_text(html, encoding="utf-8")
    data = SceneHtmlOut(
        run_id=run_id, scene=scene, mode=mode, still=still,
        html_path=str(out), size_bytes=out.stat().st_size,
    )
    if mode == "self":
        instr = (
            "자립형 씬 html 을 저장했다. 필요하면 Read 로 열어 구조를 확인하고, 사용자에게는 "
            "html_path 를 전달하라 — http 서빙 없이 브라우저(file:// 포함)에서 바로 열린다."
        )
    else:
        instr = (
            "경량 씬 html 을 빌드 디렉터리에 저장했다. 빌드 상대 자원을 참조하므로 "
            "빌드 디렉터리를 http 로 서빙한 상태에서 열어야 한다 (file:// 불가)."
        )
    return ok_envelope(state, data.model_dump(mode="json"), instr)


@mcp.tool()
def scene_still(run_id: str, scene: str, t: float | None = None) -> dict:
    """씬 스틸 PNG 를 캡처해 저장 경로를 반환한다 (t 미지정 = 대표 스틸 시각).

    RenderSession seek 캡처 — 포맷 스펙 stage 원척이며 scene-data 기준으로 캐시된다.
    """
    state = get_session()
    bd, _scen, web_run, err = _scene_ctx(state, run_id)
    if err:
        return err
    scenes_mod, _ = _lazy_import("wdweb.scenes")
    entry = (web_run or {}).get("entry") or "index.html"
    try:
        path = scenes_mod.scene_still_png(bd, scene, t=t, entry=entry)
    except KeyError as exc:
        return error_envelope(state, "SCENE_NOT_FOUND", str(exc.args[0]),
                              "scene_list 로 씬 이름을 확인하라.")
    except Exception as exc:  # noqa: BLE001
        return error_envelope(state, "SCENE_STILL_FAILED", f"{type(exc).__name__}: {exc}")
    data = SceneStillOut(
        run_id=run_id, scene=scene, t=t, png_path=str(path), size_bytes=path.stat().st_size,
    )
    return ok_envelope(
        state, data.model_dump(mode="json"),
        "씬 스틸 PNG 를 저장했다. png_path 를 Read 로 열어 눈으로 확인하라 "
        "(Claude 는 이미지를 볼 수 있다). 문제가 보이면 scenario_patch 로 고쳐라.",
    )


@mcp.tool()
def scenario_patch(run_id: str, ops: list[dict]) -> dict:
    """핀포인트 패치 — 원자 연산 목록을 정본(patch_scenario)으로 적용·전량 검증·재빌드한다.

    연산: set_data{scene,path,value} / set_narration{scene,text} / set_dur{scene,dur} /
    set_tpl{scene,tpl} / set_stills{scene,stills} / reorder{names} / remove_scene{scene} /
    insert_scene{after,tpl,data,name?,dur?}. 하나라도 거부되거나 검증에 실패하면
    전체 취소된다 (원본 무손상). 성공 시 사람이 읽는 diff 요약을 반환한다.
    """
    state = get_session()
    patch_mod, err = _lazy_import("wdpipeline.patch")
    if patch_mod is None:
        return error_envelope(
            state, "PIPELINE_UNAVAILABLE", f"wdpipeline.patch 를 불러올 수 없다: {err}",
            "wdpipeline 모듈이 아직 구현 중일 수 있다. 구현 완료 후 다시 호출하라.",
        )
    bd, scen, web_run, ctx_err = _scene_ctx(state, run_id)
    if ctx_err:
        return ctx_err
    scenario = json.loads(scen.read_text(encoding="utf-8"))
    try:
        patched, diffs = patch_mod.patch_scenario(scenario, ops)
    except patch_mod.PatchError as exc:
        return error_envelope(
            state, "PATCH_REJECTED", "; ".join(exc.errors[:8]),
            "전체 취소되었다 (원본 무손상). 거부 사유를 반영해 ops 를 수정 후 재호출하라. "
            "씬 이름·경로는 scene_list 로 확인할 수 있다.",
        )
    scen.write_text(json.dumps(patched, ensure_ascii=False, indent=2), encoding="utf-8")
    entry, berr = _ensure_scene_build(bd, scen)
    if berr:
        return error_envelope(
            state, "BUILD_FAILED",
            f"패치는 저장됐지만 재빌드에 실패했다: {berr}",
            "scenario.json 은 갱신된 상태다. 빌드 오류를 해결한 뒤 다시 호출하라.",
        )
    total = round(sum(float(s["dur"]) for s in patched["scenes"]), 3)
    if web_run is not None:
        webruns, _ = _lazy_import("wdweb.runs")
        if webruns is not None:
            webruns.update_run(
                run_id, build_dir=str(entry.parent), entry=entry.name,
                scenario_summary={
                    "scene_count": len(patched["scenes"]), "total_dur": total,
                    "core_message": patched["meta"]["core_message"],
                },
            )
    data = ScenarioPatchOut(
        run_id=run_id, applied=diffs, scenario_path=str(scen),
        build_dir=str(entry.parent), entry=entry.name,
        scene_count=len(patched["scenes"]), total_dur=total,
    )
    return ok_envelope(
        state, data.model_dump(mode="json"),
        "패치가 적용되고 재빌드까지 끝났다. applied 의 diff 요약을 사용자에게 그대로 전하고, "
        "필요하면 scene_still/scene_html 로 수정 결과를 확인시켜라.",
    )


# ── 엔트리 ───────────────────────────────────────────────────────────


def main() -> None:
    """wdmcp 콘솔 엔트리 — stdio 트랜스포트로 기동한다 (stdout은 프로토콜 전용, 로그는 stderr)."""
    logging.basicConfig(stream=sys.stderr, level=get_settings().log_level)
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr))
    log.info("wdmcp_server_start", transport="stdio")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
