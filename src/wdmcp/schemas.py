# wdmcp 툴 11종의 입출력 pydantic 스키마 — PLAN §3 툴 부록의 실체 (봉투 data 페이로드 정본)
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

# ── 공통 ──────────────────────────────────────────────────────────────


class ToolModel(BaseModel):
    """모든 툴 스키마의 베이스. 오타 필드를 조기에 잡기 위해 extra 금지."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ErrorInfo(ToolModel):
    """봉투 error 필드 — 항상 구조화해 반환한다 (MCP 예외 전파 금지)."""

    code: str
    message: str
    hint: str = ""


class MeetingLedgerSummary(ToolModel):
    """봉투 session 필드의 회의 1건 원장 요약."""

    run_id: str | None = None
    delivered_personas: list[str] = Field(default_factory=list)
    delivered_cards: int = 0
    delivered_fragments: int = 0
    modules_delivered: bool = False
    known_refs_count: int = 0
    fact_counter: int = 0


class SessionSummary(ToolModel):
    """봉투 session 필드 — stdio 프로세스 수명 동안의 전달 원장 요약."""

    session_id: str
    started_at: str
    meetings: dict[str, MeetingLedgerSummary] = Field(default_factory=dict)


class Envelope(ToolModel):
    """모든 툴이 공유하는 반환 봉투 {ok, data, session, claude_instructions, error}."""

    ok: bool
    data: dict | None
    session: SessionSummary
    claude_instructions: str
    error: ErrorInfo | None


# ── 회의 툴 5종 ───────────────────────────────────────────────────────


class RoundInfo(ToolModel):
    round_no: int
    name: str
    speaker_order: str
    cycles: int
    citation_required: bool


class NextSpeakerInfo(ToolModel):
    role: str
    expert_id: str | None = None
    round_no: int
    round_name: str


class MeetingStartOut(ToolModel):
    """meeting_start 성공 페이로드."""

    status: Literal["created"] = "created"
    meeting_id: str
    type: str
    topic: str
    participants: list[str]
    run_id: str | None = None
    fragments_loaded: int = 0
    rounds: list[RoundInfo]
    next_speaker: NextSpeakerInfo | None


class BriefingRound(ToolModel):
    round_no: int
    name: str
    instruction: str
    citation_required: bool


class BriefingSpeaker(ToolModel):
    role: str
    expert_id: str | None = None
    name_ko: str | None = None


class PersonaDelivery(ToolModel):
    """페르소나 델타 전달 — 회의당 최초 1회만 full, 이후 recall (토큰 최소화)."""

    delivery: Literal["full", "recall", "none"]
    system_prompt: str | None = None
    recall: str | None = None
    note: str | None = None


class BriefingCard(ToolModel):
    """지식카드 전달 1건. card_id가 known_refs에 등재되어 인용 가능해진다."""

    card_id: str
    title: str
    confidence: str
    body_md: str


class BriefingFact(ToolModel):
    """보고서 조각(fragment) 근거 1건. ref(frag_id)가 known_refs에 등재된다."""

    marker: str = Field(description="[F#] 회의 전역 연번 마커")
    ref: str = Field(description="frag_id — citations.ref로 쓸 수 있는 유일 키")
    type: str = ""
    text: str
    source: str = ""
    confidence: float | str | None = None


class ModuleIndexEntry(ToolModel):
    """모듈 축약 인덱스 1행 — id·용도 한 줄·props 요약·in_scope (PLAN §6.3 재사용 모드)."""

    id: str
    type: str = "scene-template"
    status: str = "draft"
    version: str = ""
    nat_default: float | None = None
    summary: str = ""
    props: str = ""
    in_scope_hint: str = ""


class ModulesDelivery(ToolModel):
    """모듈 축약 인덱스 델타 전달 — 회의당 최초 1회만 full, 이후 ID recall."""

    delivery: Literal["full", "recall"]
    index: list[ModuleIndexEntry] | None = None
    module_ids: list[str] = Field(default_factory=list)
    recall: str | None = None


class TurnGist(ToolModel):
    turn_no: int
    speaker: str
    stance: str | None = None
    gist: str


class SpeakingRules(ToolModel):
    """meeting_submit_turn 필드 작성 규약."""

    round_no: int
    round_name: str
    citation_required: bool
    stance_enum: list[str]
    artifact_types: list[str]
    length_hint: str
    citation_note: str


class BriefingOut(ToolModel):
    """meeting_get_briefing 성공 페이로드."""

    meeting_id: str
    topic: str
    meeting_type: str
    round: BriefingRound
    speaker: BriefingSpeaker
    persona: PersonaDelivery
    cards: list[BriefingCard] = Field(default_factory=list)
    already_delivered_cards: list[str] = Field(default_factory=list)
    facts: list[BriefingFact] = Field(default_factory=list)
    modules: ModulesDelivery
    recent_turns: list[TurnGist] = Field(default_factory=list)
    speaking_rules: SpeakingRules


class CitationIn(ToolModel):
    """meeting_submit_turn citations 원소."""

    ref: str = Field(min_length=1)
    quote: str = ""


class ArtifactIn(ToolModel):
    """meeting_submit_turn artifacts 원소."""

    type: str
    content: str = Field(min_length=1)
    owner_expert_id: str | None = None


class SubmitTurnOut(ToolModel):
    accepted: Literal[True] = True
    turn_no: int
    status: str
    round_no: int
    next_speaker: NextSpeakerInfo | None


class MeetingStatusOut(ToolModel):
    meeting_id: str
    topic: str
    type: str
    status: str
    participants: list[str]
    round_index: int
    total_rounds: int
    current_round: str | None
    turns_total: int
    recent_turns: list[TurnGist]
    next_speaker: NextSpeakerInfo | None
    delivered_personas: list[str]
    known_refs_count: int
    modules_delivered: bool


class MeetingCloseOut(ToolModel):
    meeting_id: str
    status: str
    closed_at: str | None
    turns_total: int
    decisions: int
    action_items: int
    open_issues: int
    minutes_path: str


# ── 파이프라인 툴 4종 ─────────────────────────────────────────────────


class ReportIngestOut(ToolModel):
    """report_ingest 성공 페이로드 — report.norm.json 저장 결과."""

    run_id: str
    doc_id: str | int | None = None
    title: str = ""
    pages: int = 0
    norm_path: str


class FragmentPreview(ToolModel):
    frag_id: str
    type: str = ""
    text: str = ""


class FragmentizeOut(ToolModel):
    """report_fragmentize 성공 페이로드 — fragments.json 저장 결과."""

    run_id: str
    fragments_total: int
    by_type: dict[str, int] = Field(default_factory=dict)
    preview: list[FragmentPreview] = Field(default_factory=list)
    fragments_path: str


class SceneBrief(ToolModel):
    name: str
    dur: float
    tpl: str


class ScenarioBuildOut(ToolModel):
    """scenario_build 성공 페이로드 — 회의 산출물 집계 + ScenarioDoc 조립·검증 결과."""

    meeting_id: str
    run_id: str
    scenario_path: str
    core_message: str
    duration_sec: float
    scene_count: int
    scenes: list[SceneBrief] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    meeting_decisions: list[str] = Field(default_factory=list)
    scenario_patches: int = 0


# ── 렌더 툴 2종 ───────────────────────────────────────────────────────

RENDER_TARGETS = ("video", "pptx")

JobStatus = Literal["queued", "building", "rendering", "done", "failed"]


class RenderJob(ToolModel):
    """렌더 잡 원장 1건 — data/render_jobs/{job_id}.json의 파이썬 표현 (파일이 진실)."""

    job_id: str
    status: JobStatus = "queued"
    targets: list[str]
    scenario_path: str | None = None
    build_dir: str | None = None
    entry: str | None = None
    fps: int | None = None
    outputs: dict[str, str] = Field(default_factory=dict)
    detail: dict = Field(default_factory=dict)
    error: str | None = None
    created_at: str
    updated_at: str


class RenderSubmitOut(ToolModel):
    job_id: str
    status: JobStatus
    targets: list[str]
    job_path: str


# ── QA 툴 1종 ────────────────────────────────────────────────────────


class QaGateResult(BaseModel):
    """게이트 위반 1건 — wdqa 계약 {gate, rule, scene, severity, detail}. 여분 필드 허용."""

    model_config = ConfigDict(extra="allow")

    gate: str | int | None = None
    rule: str | None = None
    scene: str | None = None
    severity: str | None = None
    detail: str | None = None


class QaRunOut(ToolModel):
    """qa_run 성공 페이로드 — 리포트는 심의 인용 근거(지식카드 후보)가 된다."""

    build_path: str
    gates: list[str] | None = None
    passed: bool
    results: list[QaGateResult] = Field(default_factory=list)
