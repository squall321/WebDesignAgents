# 렌더 잡 원장·백그라운드 워커 — data/render_jobs/{id}.json이 진실, 스레드가 빌드→렌더 상태를 기록
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from wdcore.config import get_settings

from .schemas import RenderJob

_lock = threading.Lock()



def _format_of(build_dir: Path) -> str | None:
    """빌드 산출물의 scene-data.json 에서 포맷 id 를 읽는다 (없으면 render.toml 폴백)."""
    sd = Path(build_dir) / "scene-data.json"
    if not sd.is_file():
        return None
    try:
        return json.loads(sd.read_text(encoding="utf-8")).get("format")
    except ValueError:
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def jobs_dir() -> Path:
    d = get_settings().data_dir / "render_jobs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def job_path(job_id: str) -> Path:
    return jobs_dir() / f"{job_id}.json"


def new_job_id() -> str:
    return f"rj-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def write_job(job: RenderJob) -> Path:
    path = job_path(job.job_id)
    with _lock:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(job.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
    return path


def read_job(job_id: str) -> RenderJob | None:
    path = job_path(job_id)
    if not path.is_file():
        return None
    with _lock:
        return RenderJob.model_validate_json(path.read_text(encoding="utf-8"))


def _update_job(job_id: str, **updates) -> RenderJob:
    job = read_job(job_id)
    assert job is not None, f"잡 파일 유실: {job_id}"
    job = job.model_copy(update={**updates, "updated_at": _now_iso()})
    write_job(job)
    return job


def submit_render_job(
    *,
    targets: list[str],
    scenario_path: str | None = None,
    build_dir: str | None = None,
    entry: str | None = None,
    fps: int | None = None,
) -> RenderJob:
    """잡 파일을 queued로 기록하고 백그라운드 워커 스레드를 기동한다."""
    now = _now_iso()
    job = RenderJob(
        job_id=new_job_id(),
        status="queued",
        targets=targets,
        scenario_path=scenario_path,
        build_dir=build_dir,
        entry=entry,
        fps=fps,
        created_at=now,
        updated_at=now,
    )
    write_job(job)
    # 렌더 산출물 루트를 스레드 기동 전에 확정한다 (스레드에서 settings 재평가 방지)
    renders_root = get_settings().data_dir / "renders"
    build_root = get_settings().data_dir / "build"
    t = threading.Thread(
        target=_run_job, args=(job.job_id, renders_root, build_root), daemon=True,
        name=f"wdmcp-render-{job.job_id}",
    )
    t.start()
    return job


def _run_job(job_id: str, renders_root: Path, build_root: Path) -> None:
    """워커 본체 — (선택) wdpipeline.build 빌드 → wdrender exporter 실행. 예외는 failed로 기록."""
    try:
        job = read_job(job_id)
        assert job is not None
        stills: dict[str, list[float]] | None = None
        notes: dict[str, str] | None = None

        if job.scenario_path:
            _update_job(job_id, status="building")
            # 병렬 개발 계약(AGENT_BRIEF §모듈 간 계약) — 지연 import
            from wdpipeline.build import build_render_package

            from wdcore.models.scenario import ScenarioDoc

            doc = ScenarioDoc.model_validate_json(
                Path(job.scenario_path).read_text(encoding="utf-8")
            )
            # build_render_package 는 out_dir 직속에 쓴다 — {slug} 하위 디렉터리를 여기서 만든다
            slug = Path(job.scenario_path).parent.name or "scenario"
            entry_path = Path(build_render_package(doc, build_root / slug))
            root = entry_path.parent
            rel = entry_path.name
            stills = {s.name: s.stills for s in doc.scenes if s.stills} or None
            notes = {s.name: s.narration for s in doc.scenes if s.narration} or None
            job = _update_job(job_id, build_dir=str(root), entry=rel)
        else:
            root = Path(job.build_dir or "")
            rel = job.entry or ""

        from wdrender.config import RenderConfig, load_config
        from wdrender.exporter_pptx import export_pptx
        from wdrender.exporter_video import export_video
        from wdrender.page_session import vendor_resources

        cfg = load_config()
        if job.fps:
            cfg = RenderConfig(
                fps=job.fps, width=cfg.width, height=cfg.height,
                viewport_margin=cfg.viewport_margin, ffmpeg_args=cfg.ffmpeg_args,
                default_still_progress=cfg.default_still_progress, vendor_dir=cfg.vendor_dir,
            )
        resources = vendor_resources("/vendor") if (root / "vendor").is_dir() else None
        out_dir = renders_root / root.name
        out_dir.mkdir(parents=True, exist_ok=True)

        _update_job(job_id, status="rendering")
        outputs: dict[str, str] = {}
        detail: dict = {}
        if "video" in job.targets:
            out = out_dir / "video.mp4"
            detail["video"] = export_video(
                root, rel, out, config=cfg, resources=resources,
                format_id=_format_of(root), log=lambda m: None,
            )
            outputs["video"] = str(out)
        if "pptx" in job.targets:
            out = out_dir / "slides.pptx"
            detail["pptx"] = export_pptx(
                root, rel, out, config=cfg, resources=resources,
                format_id=_format_of(root), stills=stills, notes=notes, log=lambda m: None,
            )
            outputs["pptx"] = str(out)
        _update_job(job_id, status="done", outputs=outputs, detail=detail)
    except Exception as exc:  # 워커 스레드 — 어떤 실패든 잡 파일에 기록한다
        try:
            _update_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
