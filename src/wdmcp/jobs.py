# 렌더 잡 원장·백그라운드 워커 — data/render_jobs/{id}.json이 진실, 스레드가 빌드→렌더 상태를 기록
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from wdcore.config import get_settings

from .schemas import DOC_TARGETS, RenderJob

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


def _capture_doc_stills(build_dir: Path, entry_rel: str, out_dir: Path,
                        resources: dict | None) -> int:
    """문서 삽화용 씬 스틸을 document.py 파일명 규약(`{idx:02d}_{name}_{t:.1f}s.png`)으로 캡처한다.

    렌더 패키지에는 스틸이 없다(영상·PPT 는 캡처 후 버린다). 문서만 파일이 필요해서
    여기서 한 번 굽는다 — 이미 있으면 건너뛴다(재실행 비용 0).
    """
    import json as _json

    sd = build_dir / "scene-data.json"
    if not sd.is_file():
        return 0
    scenes = (_json.loads(sd.read_text(encoding="utf-8")) or {}).get("scenes") or []
    out_dir.mkdir(parents=True, exist_ok=True)

    from wdrender.config import apply_format, load_config
    from wdrender.page_session import RenderSession
    from wdrender.server import StaticServer

    cfg = apply_format(load_config(), _format_of(build_dir))
    wanted: list[tuple[int, str, float, float]] = []   # (idx, name, 전역시각, 로컬시각)
    elapsed = 0.0
    for i, sc in enumerate(scenes, start=1):
        dur = float(sc.get("dur") or 0)
        # 다단 페이즈 씬(예: 클로징)은 stills 가 복수다 — 전량 캡처해야 그림이 겹치지 않는다
        locals_ = [float(t) for t in (sc.get("stills") or [max(dur - 1.0, dur * 0.5)])]
        name = str(sc.get("name") or f"scene{i}")
        for local in locals_:
            wanted.append((i, name, elapsed + local, local))
        elapsed += dur

    # 파일명은 document.py 규약(_still_filename)과 같아야 한다 — **전역 시각** 기준이다.
    # 로컬 시각으로 쓰면 다단 페이즈 씬에서 두 그림이 같은 파일로 해석된다(실측 버그).
    todo = [w for w in wanted
            if not (out_dir / f"{w[0]:02d}_{w[1]}_{w[2]:.1f}s.png").is_file()]
    if not todo:
        return 0
    with StaticServer(build_dir) as srv:
        with RenderSession(srv.url_for(entry_rel), width=cfg.width, height=cfg.height,
                           resources=resources) as sess:
            for idx, name, gt, _local in todo:
                sess.seek(gt)
                sess.capture(out_dir / f"{idx:02d}_{name}_{gt:.1f}s.png")
    return len(todo)


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
    run_dir: str | None = None,
    doc_style: str = "report",
    pptx_mode: str = "hybrid",
    pptx_verify: bool = False,
    narration: bool = False,
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
        run_dir=run_dir,
        doc_style=doc_style,
        pptx_mode=pptx_mode,
        pptx_verify=pptx_verify,
        narration=narration,
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
    work: Path | None = None   # 내레이션 씬 음성 임시 보관 — 끝나면 지운다
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

        outputs: dict[str, str] = {}
        detail: dict = {}
        # 포맷의 outputs 가 실제 산출을 지배한다 — PPT 전용 포맷(outputs: [pptx])에서
        # mp4 를 굽다 실패하지 않게, wda render 와 같은 단일 판정점을 쓴다.
        from wdpipeline.format import render_targets

        # 문서 3형식은 무대 규격과 무관하다(심의 산출물에서 나온다) — 포맷 outputs 필터 면제.
        allowed = set(render_targets(_format_of(root))) | set(DOC_TARGETS)
        job_targets = [t for t in job.targets if t in allowed]

        # 내레이션 — 실측·재조정·재빌드는 빌드의 일부라 building 상태로 둔다 (결정 49~52)
        plan = None
        if job.narration and "video" in job_targets:
            import tempfile

            from wdpipeline.narration import prepare

            _update_job(job_id, status="building")
            work = Path(tempfile.mkdtemp(prefix="wda_narr_"))
            scen = Path(job.scenario_path) if job.scenario_path else (
                Path(job.run_dir) / "scenario.json" if job.run_dir else None
            )
            plan = prepare(root, work, scenario_path=scen, log=lambda m: None)
            if stills is not None:   # 재조정으로 dur 가 바뀌어 PPTX 캡처 시각도 옮겨졌다
                stills = {s.name: s.stills for s in plan.doc.scenes if s.stills} or None

        _update_job(job_id, status="rendering")
        if "video" in job_targets:
            out = out_dir / "video.mp4"
            detail["video"] = export_video(
                root, rel, out, config=cfg, resources=resources,
                format_id=_format_of(root), log=lambda m: None,
            )
            outputs["video"] = str(out)
            if plan is not None:
                from wdpipeline.narration import finish

                detail["narration"] = finish(plan, out, out_dir, log=lambda m: None)
        if "pptx" in job_targets:
            out = out_dir / "slides.pptx"
            detail["pptx"] = export_pptx(
                root, rel, out, config=cfg, resources=resources,
                format_id=_format_of(root), stills=stills, notes=notes,
                mode=job.pptx_mode, verify=job.pptx_verify, log=lambda m: None,
            )
            outputs["pptx"] = str(out)

        # ── 문서 3형식 — 심의 산출물을 읽는 글로 (본문=narration, 삽화=씬 스틸,
        #    표=structured, 부록=회의록). run_dir 이 있어야 조립할 수 있다.
        doc_targets = [t for t in job_targets if t in DOC_TARGETS]
        if doc_targets:
            from wdpipeline.document import assemble_document, validate_document
            from wdrender.exporter_doc import export_document

            # 절대경로로 정규화 — assemble_document 가 만드는 figure source_path 가
            # 그대로 절대경로가 되어, exporter 의 assets_root 조합에 좌우되지 않는다.
            run_dir = Path(job.run_dir) if job.run_dir else (
                Path(job.scenario_path).parent if job.scenario_path else None
            )
            if run_dir is not None:
                run_dir = run_dir.resolve()
            if run_dir is None or not run_dir.is_dir():
                raise ValueError(
                    "문서 산출에는 run_dir(data/pipeline/{run_id})가 필요하다 — "
                    "render_submit 에 run_dir 을 넘기거나 scenario_path 로 제출하라"
                )
            # 삽화 확보 — 렌더 패키지에는 스틸 PNG 가 없다. 문서가 그림을 실으려면
            # 씬 스틸을 run_dir/stills/ 규약 이름으로 먼저 구워야 한다.
            _capture_doc_stills(root, rel, run_dir / "stills", resources)
            ddoc = assemble_document(run_dir, build_dir=root, style=job.doc_style)
            errs = validate_document(ddoc)
            if errs:
                raise ValueError("문서 검증 실패: " + "; ".join(errs))
            res = export_document(
                ddoc, out_dir, stem="report",
                formats=tuple(doc_targets), assets_root=root, log=lambda m: None,
            )
            for kind, info in res.items():
                path = out_dir / f"report.{kind}"
                outputs[kind] = str(path)
                detail[kind] = info

        _update_job(job_id, status="done", outputs=outputs, detail=detail)
    except Exception as exc:  # 워커 스레드 — 어떤 실패든 잡 파일에 기록한다
        try:
            _update_job(job_id, status="failed", error=f"{type(exc).__name__}: {exc}")
        except Exception:
            pass
    finally:
        if work is not None:
            import shutil

            shutil.rmtree(work, ignore_errors=True)
