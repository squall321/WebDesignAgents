# wdweb FastAPI 앱 — /api/* 라우트를 먼저 선언하고 frontend/dist 를 "/" 에 마운트 (HEAXHub fastapi_react 규약)
# 순서가 뒤집히면 API 가 전부 SPA 로 먹힌다 (VoiceRecorder backend/app/main.py 실물 규약 준수).
from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

import yaml
from fastapi import Body, FastAPI, HTTPException, Request, status
from fastapi.responses import PlainTextResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.routing import Route
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from wdcore.config import get_settings
from wdmcp.server import mcp as _wdmcp

from . import runs as runledger
from wdmcp.schemas import DOC_STYLES, PPTX_MODES

from .runs import REPO_ROOT, RENDER_TARGETS, data_dir

# wdmcp(경로 A stdio 어댑터)와 동일한 FastMCP 서버를 /mcp 로도 서빙 — heax 매니페스트
# mcp:{path:/mcp, transport:streamable_http} 선언과 실체를 일치시켜 게이트웨이 자동연동
# (ThermalShockMCP app/main.py 규약)을 성립시킨다. 도구 정의는 한 곳(wdmcp)뿐이다.
_mcp_app = _wdmcp.streamable_http_app()  # 내부 라우트 = settings.streamable_http_path("/mcp")


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    # 서브앱의 lifespan 은 자동 실행되지 않으므로 세션 매니저를 직접 구동한다.
    async with _wdmcp.session_manager.run():
        yield


app = FastAPI(
    title="WebDesignAgents",
    description="전문가 심의 기반 발표자료(영상/PPT) 자동 생성 플랫폼 — 웹 콘솔",
    version="0.1.0",
    lifespan=_lifespan,
)

# ⚠ app.mount("/mcp", ...) 를 쓰면 안 된다. Starlette Mount 의 경로 정규식은
# "/mcp/{path:path}" 라 뒤 슬래시 없는 정확 경로 "/mcp" 를 매칭하지 못하고, 이 앱은
# 파일 끝에서 SPA(StaticFiles)를 "/" 에 캐치올로 마운트하므로 그 캐치올이 "/mcp" 를
# 대신 먹어 GET/HEAD 전용 405 를 돌려준다(redirect_slashes 도 캐치올이 먼저 매칭돼
# 발동하지 않는다). 게이트웨이·표준 MCP 클라이언트는 뒤 슬래시 없이 호출하므로
# ASGI 앱을 정확 경로 Route 로 위임한다. methods 를 주지 않으면 메서드 필터가 없어
# POST(메시지)·GET(SSE)·DELETE(세션 종료)가 그대로 MCP 앱에 전달된다.
app.router.routes.append(Route("/mcp", endpoint=_mcp_app))

_MODULES_REGISTRY = REPO_ROOT / "modules" / "registry.yaml"
_WEB_ROOT = REPO_ROOT / "web"
_FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


# ── 응답 봉투 (VoiceRecorder responses 패턴) ────────────────────────────────


def envelope(data=None, message: str = "", success: bool = True) -> dict:
    return {"success": success, "data": data, "message": message}


@app.exception_handler(StarletteHTTPException)
async def _route_miss_handler(request: Request, exc: StarletteHTTPException):
    # 라우트 매칭 실패(404 등)도 /api/* 는 봉투로 — 프런트가 사유를 표시할 수 있게
    if request.url.path.startswith("/api/"):
        return JSONResponse(
            status_code=exc.status_code,
            content=envelope(None, message=str(exc.detail), success=False),
        )
    return PlainTextResponse(str(exc.detail), status_code=exc.status_code)


@app.exception_handler(HTTPException)
async def _http_exc_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=envelope(None, message=str(exc.detail), success=False),
    )


@app.exception_handler(RequestValidationError)
async def _validation_exc_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=envelope(None, message=f"요청 형식 오류: {exc.errors()}", success=False),
    )


# ── 공통 헬퍼 ────────────────────────────────────────────────────────────────


def _run_or_404(run_id: str) -> dict:
    run = runledger.read_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"실행을 찾을 수 없습니다: {run_id}")
    return run


def _serve_safe(root: Path, rel_path: str) -> FileResponse:
    """root 하위 파일만 서빙한다 — resolve 후 경계 검사로 경로 탈출(../, 절대경로)을 차단."""
    root_r = root.resolve()
    if not root_r.is_dir():
        raise HTTPException(status_code=404, detail="서빙 루트가 없습니다")
    try:
        target = (root_r / rel_path).resolve()
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="잘못된 경로입니다") from exc
    if target != root_r and not target.is_relative_to(root_r):
        raise HTTPException(status_code=403, detail="경로 탈출이 차단되었습니다")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"파일이 없습니다: {rel_path}")
    return FileResponse(target)


# ── 상태 ────────────────────────────────────────────────────────────────────


@app.get("/api/health")
def health() -> dict:
    """HEAXHub health_check 계약 — 봉투 없이 원형 그대로."""
    return {"status": "ok"}


# ── 실행 (파이프라인) ────────────────────────────────────────────────────────


@app.post("/api/runs", status_code=status.HTTP_202_ACCEPTED)
async def create_run(request: Request) -> JSONResponse:
    """보고서 JSON(body.report_json) 또는 multipart 파일을 받아 파이프라인 실행을 시작한다."""
    content_type = request.headers.get("content-type", "")
    slug: str | None = None
    if content_type.startswith("multipart/form-data"):
        form = await request.form()
        upload = form.get("file")
        if upload is None or isinstance(upload, str):
            raise HTTPException(status_code=400, detail="multipart 요청에 file 필드가 필요합니다")
        raw = await upload.read()
        try:
            report = json.loads(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"파일이 JSON 이 아닙니다: {exc}") from exc
        slug_field = form.get("slug")
        slug = slug_field if isinstance(slug_field, str) else None
    else:
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"본문이 JSON 이 아닙니다: {exc}") from exc
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="본문은 JSON 객체여야 합니다")
        report = body.get("report_json")
        slug = body.get("slug")
    if not isinstance(report, dict):
        raise HTTPException(status_code=400, detail="report_json 은 report_archive_draft_v1 객체여야 합니다")

    run = runledger.submit_run(report, slug=slug)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=envelope({"run_id": run["run_id"], "slug": run["slug"]},
                         message="파이프라인 실행을 시작했습니다"),
    )


@app.get("/api/runs")
def get_runs() -> dict:
    return envelope({"runs": runledger.list_runs()})


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    return envelope(_run_or_404(run_id))


@app.post("/api/runs/{run_id}/render", status_code=status.HTTP_202_ACCEPTED)
async def render_run(run_id: str, request: Request) -> JSONResponse:
    """wdrender exporter 를 백그라운드로 실행한다. body: {targets?, fps?, doc_style?, pptx_mode?}."""
    run = _run_or_404(run_id)
    if not run.get("build_dir") or not run.get("entry"):
        raise HTTPException(status_code=409, detail="빌드가 완료된 실행만 렌더할 수 있습니다")
    render = run.get("render") or {}
    if render.get("status") in ("queued", "rendering"):
        raise HTTPException(status_code=409, detail="이미 렌더가 진행 중입니다")

    body: dict = {}
    if (await request.body()):
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"본문이 JSON 이 아닙니다: {exc}") from exc
    # 기본값은 영상·PPT 다. 문서 3형식까지 기본에 넣으면 영상 한 번 뽑자고 5종을 다 굽는다.
    targets = body.get("targets") or ["video", "pptx"]
    if not isinstance(targets, list) or not targets or any(t not in RENDER_TARGETS for t in targets):
        raise HTTPException(status_code=400, detail=f"targets 는 {list(RENDER_TARGETS)} 의 부분집합이어야 합니다")
    fps = body.get("fps")
    if fps is not None and (not isinstance(fps, int) or fps <= 0):
        raise HTTPException(status_code=400, detail="fps 는 양의 정수여야 합니다")
    doc_style = body.get("doc_style") or "report"
    if doc_style not in DOC_STYLES:
        raise HTTPException(status_code=400,
                            detail=f"doc_style 은 {list(DOC_STYLES)} 중 하나여야 합니다")

    pptx_mode = body.get("pptx_mode") or "hybrid"
    if pptx_mode not in PPTX_MODES:
        raise HTTPException(status_code=400,
                            detail=f"pptx_mode 는 {list(PPTX_MODES)} 중 하나여야 합니다")

    updated = runledger.submit_render(run_id, targets=targets, fps=fps,
                                      doc_style=doc_style, pptx_mode=pptx_mode)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=envelope({"run_id": run_id, "render": updated["render"]},
                         message="렌더를 시작했습니다"),
    )


@app.post("/api/runs/{run_id}/qa")
def qa_run(run_id: str, body: dict | None = Body(default=None)) -> dict:
    """wdqa.gates.run_gates 를 실행하고 리포트를 저장·반환한다. body: {gates?}.

    동기 def — FastAPI 가 스레드풀에서 돌리므로 sync Playwright 하네스가
    이벤트 루프와 충돌하지 않고, QA 가 도는 동안 다른 요청도 막히지 않는다.
    """
    run = _run_or_404(run_id)
    if not run.get("build_dir"):
        raise HTTPException(status_code=409, detail="빌드가 완료된 실행만 QA 할 수 있습니다")
    gates = (body or {}).get("gates")
    if gates is not None and not isinstance(gates, list):
        raise HTTPException(status_code=400, detail="gates 는 문자열 목록이어야 합니다")
    try:
        result = runledger.run_qa(run_id, gates=gates)
    except ValueError as exc:  # 알 수 없는 게이트 이름 등
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return envelope(result, message="QA 게이트 실행 완료")


# ── 대화형 제작 (chat) ───────────────────────────────────────────────────────


@app.post("/api/runs/{run_id}/chat")
def chat_run(run_id: str, body: dict | None = Body(default=None)) -> dict:
    """대화 1턴 — LLM 이 제안한 액션을 시나리오에 적용·검증·재빌드한다. body: {message}.

    동기 def — LLM 호출·재빌드가 블로킹이므로 FastAPI 스레드풀에서 돌린다.
    """
    run = _run_or_404(run_id)
    message = (body or {}).get("message")
    if not isinstance(message, str) or not message.strip():
        raise HTTPException(status_code=400, detail="message 는 비어있지 않은 문자열이어야 합니다")
    from . import chat as chatops

    data = chatops.handle_chat(run, message.strip())
    return envelope(data, message="대화 처리 완료")


@app.get("/api/runs/{run_id}/chat")
def chat_history(run_id: str) -> dict:
    """대화 이력 반환 — run 재방문 시 프런트가 복원한다."""
    run = _run_or_404(run_id)
    return envelope({"chat": run.get("chat") or []})


# ── 씬 단위 HTML 출력 · 스틸 · 핀포인트 패치 (PLAN §5.9) ────────────────────


def _built_run_or_409(run_id: str) -> dict:
    run = _run_or_404(run_id)
    if not run.get("build_dir") or not Path(run["build_dir"]).is_dir():
        raise HTTPException(status_code=409, detail="빌드가 완료된 실행만 씬 API 를 쓸 수 있습니다")
    return run


@app.get("/api/runs/{run_id}/scenes")
def run_scenes(run_id: str) -> dict:
    """씬 목록 — name/tpl/dur/내레이션 요약/데이터 요약 (씬 스트립·chat 탐색용)."""
    run = _built_run_or_409(run_id)
    from . import scenes as sceneops

    try:
        scenes = sceneops.list_scenes(Path(run["build_dir"]))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return envelope({"run_id": run_id, "scenes": scenes, "count": len(scenes)})


@app.get("/api/runs/{run_id}/scenes/{scene_name}/html")
def run_scene_html(
    run_id: str, scene_name: str, mode: str = "light", still: float | None = None
) -> PlainTextResponse:
    """씬 하나만 도는 엔트리 HTML — light(상대 자원 참조)·self(전부 인라인, 다운로드 겸용)."""
    run = _built_run_or_409(run_id)
    if mode not in ("light", "self"):
        raise HTTPException(status_code=400, detail="mode 는 light|self 입니다")
    from . import scenes as sceneops

    try:
        html = sceneops.scene_entry_html(
            Path(run["build_dir"]), scene_name, still=still, mode=mode,
            # light 는 이 라우트 URL(…/scenes/{name}/html) 기준 상대 참조를
            # 프리뷰 서빙 루트(…/preview/)로 보정해 iframe 재생을 가능케 한다.
            base_href="../../preview/" if mode == "light" else None,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    headers = {}
    if mode == "self":
        from urllib.parse import quote

        fname = f"{run['slug']}-{sceneops.safe_name(scene_name)}.html"
        headers["Content-Disposition"] = (
            f"attachment; filename=\"scene.html\"; filename*=UTF-8''{quote(fname)}"
        )
    return PlainTextResponse(html, media_type="text/html; charset=utf-8", headers=headers)


@app.get("/api/runs/{run_id}/scenes/{scene_name}/still.png")
def run_scene_still(run_id: str, scene_name: str, t: float | None = None) -> FileResponse:
    """씬 스틸 PNG — RenderSession seek 캡처 (포맷 stage 원척, scene-data 기준 캐시).

    동기 def — sync Playwright 캡처가 FastAPI 스레드풀에서 돌며 이벤트 루프를 막지 않는다.
    """
    run = _built_run_or_409(run_id)
    from . import scenes as sceneops

    try:
        path = sceneops.scene_still_png(
            Path(run["build_dir"]), scene_name, t=t, entry=run.get("entry") or "index.html",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=exc.args[0]) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="image/png")


@app.patch("/api/runs/{run_id}/scenario")
def patch_run_scenario(run_id: str, body: dict = Body(...)) -> dict:
    """핀포인트 패치 — {ops:[...]} 를 patch_scenario 정본으로 적용·검증·재빌드한다.

    동기 def — 재빌드가 블로킹이므로 FastAPI 스레드풀에서 돌린다.
    실패(연산 거부·검증 위반)는 422 + 오류 목록으로 전체 취소된다 (원본 무손상).
    """
    run = _built_run_or_409(run_id)
    ops = (body or {}).get("ops")
    if not isinstance(ops, list) or not ops:
        raise HTTPException(status_code=400, detail="ops 는 비어있지 않은 연산 목록이어야 합니다")
    from wdpipeline.patch import PatchError

    from . import scenes as sceneops

    try:
        result = sceneops.apply_patch_to_run(run, ops)
    except PatchError as exc:
        raise HTTPException(
            status_code=422, detail="패치 적용 취소: " + "; ".join(exc.errors[:8])
        ) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return envelope(result, message="시나리오 패치 적용 완료")


@app.get("/api/runs/{run_id}/artifacts")
def run_artifacts(run_id: str) -> dict:
    run = _run_or_404(run_id)
    return envelope(runledger.artifacts_status(run))


_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_DOWNLOAD_META = {
    "mp4": ("video/mp4", "video.mp4"),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "slides.pptx"),
    "scenario": ("application/json", "scenario.json"),
    "html": ("text/html; charset=utf-8", "report.html"),
    "pdf": ("application/pdf", "report.pdf"),
    "docx": (_DOCX_MIME, "report.docx"),
}


@app.get("/api/runs/{run_id}/download/{kind}")
def download_artifact(run_id: str, kind: str) -> FileResponse:
    run = _run_or_404(run_id)
    if kind not in _DOWNLOAD_META:
        raise HTTPException(status_code=404, detail=f"kind 는 {sorted(_DOWNLOAD_META)} 중 하나입니다")
    path = runledger.artifact_paths(run).get(kind)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail=f"산출물이 아직 없습니다: {kind}")
    media_type, base_name = _DOWNLOAD_META[kind]
    return FileResponse(path, media_type=media_type, filename=f"{run['slug']}-{base_name}")


@app.get("/api/runs/{run_id}/preview/{path:path}")
def run_preview(run_id: str, path: str) -> FileResponse:
    """해당 실행의 build 패키지 파일 서빙 — 영상 엔트리를 iframe 으로 재생하는 용도."""
    run = _run_or_404(run_id)
    if not run.get("build_dir"):
        raise HTTPException(status_code=404, detail="빌드 산출물이 아직 없습니다")
    return _serve_safe(Path(run["build_dir"]), path)


# ── MCP 렌더 잡 산출물 ───────────────────────────────────────────────────────
# 웹 콘솔 원장(data/web_runs, run_id 키)과 MCP 렌더 잡 원장(data/render_jobs, job_id 키)은
# 서로 다른 원장이라, MCP 로 렌더한 영상은 위 /api/runs/... 라우트로 받을 수 없었다. 그래서
# render_status 가 돌려주는 건 컨테이너 파일 경로뿐이었고 챗에서 볼 방법이 없었다.
# 잡 원장 기준 라우트를 두어 job_id 만으로 재생·다운로드가 되게 한다.
# (media_type, 기본 파일명, Content-Disposition) — 영상은 inline 이어야 새 탭에서 다운로드가
# 아니라 재생으로 열린다. PPTX 는 브라우저가 표시할 수 없으니 attachment 가 맞다.
# 문서 3형식이 빠져 있으면 render_status 가 알려준 열람 URL 이 그대로 404 가 된다.
# html·pdf 는 inline(브라우저·chat 임베드로 바로 보게), docx 는 attachment.
_JOB_DOWNLOAD_META = {
    "video": ("video/mp4", "video.mp4", "inline"),
    "pptx": (_DOWNLOAD_META["pptx"][0], "slides.pptx", "attachment"),
    "html": (_DOWNLOAD_META["html"][0], "report.html", "inline"),
    "pdf": (_DOWNLOAD_META["pdf"][0], "report.pdf", "inline"),
    "docx": (_DOCX_MIME, "report.docx", "attachment"),
}


@app.get("/api/render_jobs/{job_id}/download/{kind}")
def download_render_job(job_id: str, kind: str) -> FileResponse:
    """render_submit 산출물 서빙 — 잡 원장의 경로가 데이터 루트 안인지 검증한 뒤 스트리밍."""
    if kind not in _JOB_DOWNLOAD_META:
        raise HTTPException(
            status_code=404, detail=f"kind 는 {sorted(_JOB_DOWNLOAD_META)} 중 하나입니다"
        )
    from wdmcp import jobs as mcp_jobs  # 지연 import — wdmcp ↔ wdweb 순환 회피

    job = mcp_jobs.read_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"렌더 잡 없음: {job_id}")
    raw = (job.outputs or {}).get(kind)
    if not raw:
        raise HTTPException(status_code=404, detail=f"산출물이 아직 없습니다: {kind}")
    # 원장 값이라도 경계 검사는 한다 — 데이터 루트 밖 파일이 URL 하나로 노출되지 않게.
    target = Path(raw).resolve()
    if not target.is_relative_to(data_dir().resolve()):
        raise HTTPException(status_code=403, detail="데이터 루트 밖 경로가 차단되었습니다")
    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"파일이 없습니다: {kind}")
    media_type, base_name, disposition = _JOB_DOWNLOAD_META[kind]
    return FileResponse(
        target, media_type=media_type, filename=f"{job_id}-{base_name}",
        content_disposition_type=disposition,
    )


# ── 회의록 ──────────────────────────────────────────────────────────────────


def _meeting_store():
    from wdcore.meetings.store import MeetingStore

    return MeetingStore(root=data_dir() / "meetings")


@app.get("/api/meetings")
def get_meetings() -> dict:
    metas = _meeting_store().list_meetings()
    items = [json.loads(m.model_dump_json()) for m in metas]
    items.sort(key=lambda m: m.get("created_at") or "", reverse=True)
    return envelope({"meetings": items})


@app.get("/api/meetings/{meeting_id}/minutes")
def get_minutes(meeting_id: str) -> dict:
    try:
        d = _meeting_store().find_dir(meeting_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    minutes = d / "minutes.md"
    if not minutes.is_file():
        raise HTTPException(status_code=404, detail="minutes.md 가 아직 없습니다")
    return envelope({"meeting_id": meeting_id, "markdown": minutes.read_text(encoding="utf-8")})


# ── 심의 창구 (MCP meeting_* 도구의 REST 사영) ───────────────────────────────
#
# 웹에도 심의가 있어야 한다. 없으면 웹은 규칙기반 데모 조립밖에 못 하고, 같은 플랫폼의
# 두 창구가 서로 다른 품질의 자료를 낸다. 구현은 wdweb/deliberation.call_tool 이
# MCP 도구 **본체를 그대로** 호출한다 — 검증 규칙을 복제하지 않기 위해서다.


def _tool(name: str, *, meeting_id: str | None = None, **kwargs) -> dict:
    """도구 호출 후 MCP 봉투를 웹 봉투로 바꾼다. ok=false 는 400 으로 올린다."""
    from wdweb.deliberation import call_tool

    try:
        out = call_tool(name, meeting_id=meeting_id, **kwargs)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not out.get("ok", True):
        err = out.get("error") or {}
        detail = err.get("message") or "요청을 처리하지 못했습니다"
        hint = err.get("hint")
        raise HTTPException(status_code=400, detail=f"{detail} — {hint}" if hint else detail)
    # claude_instructions 는 MCP 클라이언트(연기자)용 지시문이다. 웹 UI 도 자율 실행 대신
    # 사람이 턴을 쓸 수 있으므로 같이 싣는다 — 무엇을 써야 하는지가 거기 적혀 있다.
    data = dict(out.get("data") or {})
    if out.get("claude_instructions"):
        data["instructions"] = out["claude_instructions"]
    return envelope(data)


@app.get("/api/personas/roster")
def get_persona_roster() -> dict:
    """페르소나 로스터 (meeting_personas 사영) — 참가자를 고를 때 쓴다."""
    return _tool("meeting_personas")


@app.post("/api/meetings", status_code=status.HTTP_201_CREATED)
def post_meeting(body: dict = Body(...)) -> dict:
    """심의 개회. body: {topic, type, participants[], run_id?, format_id?}"""
    for key in ("topic", "type", "participants"):
        if not body.get(key):
            raise HTTPException(status_code=400, detail=f"{key} 는 필수입니다")
    return _tool(
        "meeting_start", topic=body["topic"], type=body["type"],
        participants=list(body["participants"]), run_id=body.get("run_id"),
        format_id=body.get("format_id"),
    )


@app.get("/api/meetings/{meeting_id}")
def get_meeting(meeting_id: str) -> dict:
    """심의 진행 현황 (meeting_status 사영)."""
    return _tool("meeting_status", meeting_id=meeting_id)


@app.get("/api/meetings/{meeting_id}/briefing")
def get_briefing(meeting_id: str) -> dict:
    """다음 발언자 브리핑 (meeting_get_briefing 사영). 전달한 ref 는 원장에 축적된다."""
    return _tool("meeting_get_briefing", meeting_id=meeting_id)


@app.post("/api/meetings/{meeting_id}/turns")
def post_turn(meeting_id: str, body: dict = Body(...)) -> dict:
    """발언 턴 제출 (meeting_submit_turn 사영). 엔진 검증 거부는 400 이다."""
    if body.get("round_no") is None or not body.get("role") or not body.get("content_md"):
        raise HTTPException(status_code=400, detail="round_no·role·content_md 는 필수입니다")
    return _tool(
        "meeting_submit_turn", meeting_id=meeting_id,
        round_no=int(body["round_no"]), role=body["role"], content_md=body["content_md"],
        expert_id=body.get("expert_id"), stance=body.get("stance"),
        citations=body.get("citations"), artifacts=body.get("artifacts"),
    )


@app.post("/api/meetings/{meeting_id}/close")
def post_close(meeting_id: str) -> dict:
    """폐회 — 회의록(minutes.md)을 굽고 미해결 쟁점을 뽑는다."""
    return _tool("meeting_close", meeting_id=meeting_id)


@app.post("/api/meetings/{meeting_id}/scenario")
def post_scenario(meeting_id: str, body: dict | None = Body(default=None)) -> dict:
    """심의 산출물 → 시나리오 (scenario_build 사영) + 그 실행의 렌더 패키지 재빌드.

    body: {run_id?, format?}. 재빌드까지 해야 루프가 닫힌다 — scenario.json 만 갈아두면
    실행의 build 는 옛 시나리오 그대로라 렌더·문서에 심의 결과가 반영되지 않는다.
    """
    body = body or {}
    kwargs: dict = {}
    for key in ("run_id", "format"):
        if body.get(key):
            kwargs[key] = body[key]
    out = _tool("scenario_build", meeting_id=meeting_id, **kwargs)
    rid = (out.get("data") or {}).get("run_id")
    run = runledger.read_run(rid) if rid else None
    if run is not None:
        from . import scenes as sceneops

        try:
            out["data"]["rebuild"] = sceneops.rebuild_run(run)
        except (FileNotFoundError, ValueError) as exc:
            out["data"]["rebuild"] = {"rebuilt": False, "error": f"{type(exc).__name__}: {exc}"}
    else:
        out["data"]["rebuild"] = {
            "rebuilt": False,
            "note": "웹 실행 원장에 없는 run 이다 — 콘솔에서 만든 실행에 연결하면 재빌드된다.",
        }
    return out


@app.post("/api/meetings/{meeting_id}/autorun", status_code=status.HTTP_202_ACCEPTED)
def post_autorun(meeting_id: str, body: dict | None = Body(default=None)) -> JSONResponse:
    """vLLM(GLM) 무인 완주를 백그라운드로 시작한다. body: {max_turns?, run_id?}

    브라우저에는 페르소나를 연기할 주체가 없다 — MCP 는 클라이언트가 연기하지만
    웹은 이 경로(PLAN 경로 B)로 같은 엔진 위에서 심의를 돌린다.
    전 라운드 완주는 LLM 턴이 수십 번이라 동기 요청으로는 프록시 타임아웃에 걸린다.
    """
    from wdweb.deliberation import start_autorun

    body = body or {}
    try:
        state = start_autorun(meeting_id, max_turns=body.get("max_turns"),
                              run_id=body.get("run_id"))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:  # 이미 진행 중
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return JSONResponse(status_code=status.HTTP_202_ACCEPTED,
                        content=envelope(state, message="심의를 시작했습니다"))


@app.get("/api/meetings/{meeting_id}/autorun")
def get_autorun(meeting_id: str) -> dict:
    """자율 심의 진행 상태 — 콘솔이 폴링한다."""
    from wdweb.deliberation import autorun_state

    state = autorun_state(meeting_id)
    if state is None:
        raise HTTPException(status_code=404, detail="이 심의에는 자율 실행 기록이 없습니다")
    return envelope(state)


@app.get("/api/approvals")
def get_approvals(point: str = "") -> dict:
    """승인 원장 (MCP approval_status 와 같은 원장)."""
    from wdcore.approvals import HITL_POINTS, ApprovalStore, unattended_mode

    if point and point not in HITL_POINTS:
        raise HTTPException(status_code=400, detail=f"알 수 없는 지점: {point}")
    store = ApprovalStore(data_dir() / "approvals")
    return envelope({
        "unattended": unattended_mode(),
        "points": {k: {"why": v, "records": len(list((store.root / k).glob("*.json")))}
                   for k, v in HITL_POINTS.items()},
        "blocked": store.pending(point or None),
    })


@app.post("/api/approvals", status_code=status.HTTP_201_CREATED)
def post_approval(body: dict = Body(...)) -> dict:
    """승인·거절 기록. body: {point, subject, reason, by?, decision?}"""
    from wdcore.approvals import Approval, ApprovalStore

    try:
        a = Approval(point=str(body.get("point") or ""), subject=str(body.get("subject") or ""),
                     reason=str(body.get("reason") or ""), by=str(body.get("by") or ""),
                     decision=str(body.get("decision") or "approve"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    ApprovalStore(data_dir() / "approvals").record(a)
    return envelope({"point": a.point, "subject": a.subject,
                     "decision": a.decision, "at": a.at}, message="기록했습니다")


@app.get("/api/metrics")
def get_metrics() -> dict:
    """성장 지표 (MCP metrics_report 와 같은 계산)."""
    from wdqa.metrics import collect_metrics

    try:
        return envelope(collect_metrics(data_dir()))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}") from exc


# ── 모듈 갤러리 ──────────────────────────────────────────────────────────────


def _load_modules_registry() -> dict:
    if not _MODULES_REGISTRY.is_file():
        raise HTTPException(status_code=404, detail="modules/registry.yaml 이 없습니다")
    return yaml.safe_load(_MODULES_REGISTRY.read_text(encoding="utf-8")) or {}


@app.get("/api/modules")
def get_modules() -> dict:
    return envelope(_load_modules_registry())


@app.get("/api/modules/{module_id}/preview/{path:path}")
def module_preview(module_id: str, path: str) -> FileResponse:
    """모듈 preview 파일 서빙. preview.html 의 ../../../web/* 상대참조는 브라우저 정규화로
    /api/web/* 에 닿는다 (아래 web 라우트가 받는다) — 이 라우트 자체는 모듈 디렉터리 밖을 불허."""
    registry = _load_modules_registry()
    entry = next((m for m in registry.get("modules", []) if m.get("id") == module_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"모듈을 찾을 수 없습니다: {module_id}")
    return _serve_safe(REPO_ROOT / entry["path"], path)


@app.get("/api/web/{path:path}")
def web_asset(path: str) -> FileResponse:
    """web/ 정적 자산 서빙 — 모듈 preview 의 ../../../web/* 참조와 프런트 테마 토큰 fetch 용."""
    return _serve_safe(_WEB_ROOT, path)


# ── 페르소나 ────────────────────────────────────────────────────────────────


@app.get("/api/personas")
def get_personas() -> dict:
    from wdcore.registry.registry import load_registry

    settings = get_settings()
    root = settings.personas_root
    if not root.is_absolute():
        root = REPO_ROOT / root
    reg = load_registry(root)
    personas = [
        {
            "id": p.id,
            "abbr": p.abbr,
            "name_ko": p.name_ko,
            "name_en": p.name_en,
            "category": p.category,
            "role": p.persona.title,
            "status": p.status.value,
        }
        for p in reg.list_personas()
    ]
    return envelope({"personas": personas, "count": len(personas)})


# ── 정적 프런트엔드 마운트 (반드시 /api/* 라우트 뒤) ─────────────────────────

if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")


# ── 엔트리포인트 ────────────────────────────────────────────────────────────


def main() -> None:
    """uvicorn 기동 — HEAXHub 3계약(127.0.0.1 바인드, $PORT, --root-path $ROOT_PATH) 존중."""
    import uvicorn

    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("WDWEB_PORT") or os.environ.get("PORT") or "8340")
    root_path = os.environ.get("ROOT_PATH", "")
    uvicorn.run(app, host=host, port=port, root_path=root_path)


if __name__ == "__main__":
    main()
