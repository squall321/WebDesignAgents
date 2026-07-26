# wdweb FastAPI 앱 — /api/* 라우트를 먼저 선언하고 frontend/dist 를 "/" 에 마운트 (HEAXHub fastapi_react 규약)
# 순서가 뒤집히면 API 가 전부 SPA 로 먹힌다 (VoiceRecorder backend/app/main.py 실물 규약 준수).
from __future__ import annotations

import json
import os
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from wdcore.config import get_settings

from . import runs as runledger
from .runs import REPO_ROOT, RENDER_TARGETS, data_dir

app = FastAPI(
    title="WebDesignAgents",
    description="전문가 심의 기반 발표자료(영상/PPT) 자동 생성 플랫폼 — 웹 콘솔",
    version="0.1.0",
)

_MODULES_REGISTRY = REPO_ROOT / "modules" / "registry.yaml"
_WEB_ROOT = REPO_ROOT / "web"
_FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


# ── 응답 봉투 (VoiceRecorder responses 패턴) ────────────────────────────────


def envelope(data=None, message: str = "", success: bool = True) -> dict:
    return {"success": success, "data": data, "message": message}


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
    """wdrender exporter(mp4+pptx)를 백그라운드로 실행한다. body: {targets?, fps?}."""
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
    targets = body.get("targets") or list(RENDER_TARGETS)
    if not isinstance(targets, list) or not targets or any(t not in RENDER_TARGETS for t in targets):
        raise HTTPException(status_code=400, detail=f"targets 는 {list(RENDER_TARGETS)} 의 부분집합이어야 합니다")
    fps = body.get("fps")
    if fps is not None and (not isinstance(fps, int) or fps <= 0):
        raise HTTPException(status_code=400, detail="fps 는 양의 정수여야 합니다")

    updated = runledger.submit_render(run_id, targets=targets, fps=fps)
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=envelope({"run_id": run_id, "render": updated["render"]},
                         message="렌더를 시작했습니다"),
    )


@app.post("/api/runs/{run_id}/qa")
async def qa_run(run_id: str, request: Request) -> dict:
    """wdqa.gates.run_gates 를 동기 실행하고 리포트를 저장·반환한다. body: {gates?}."""
    run = _run_or_404(run_id)
    if not run.get("build_dir"):
        raise HTTPException(status_code=409, detail="빌드가 완료된 실행만 QA 할 수 있습니다")
    body: dict = {}
    if (await request.body()):
        try:
            body = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"본문이 JSON 이 아닙니다: {exc}") from exc
    gates = body.get("gates")
    if gates is not None and not isinstance(gates, list):
        raise HTTPException(status_code=400, detail="gates 는 문자열 목록이어야 합니다")
    try:
        result = runledger.run_qa(run_id, gates=gates)
    except ValueError as exc:  # 알 수 없는 게이트 이름 등
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return envelope(result, message="QA 게이트 실행 완료")


@app.get("/api/runs/{run_id}/artifacts")
def run_artifacts(run_id: str) -> dict:
    run = _run_or_404(run_id)
    return envelope(runledger.artifacts_status(run))


_DOWNLOAD_META = {
    "mp4": ("video/mp4", "video.mp4"),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "slides.pptx"),
    "scenario": ("application/json", "scenario.json"),
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
