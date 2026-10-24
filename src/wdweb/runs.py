# 웹 콘솔 실행 원장 — data/web_runs/{run_id}.json 이 진실, 백그라운드 스레드가 파이프라인 4단계·렌더 상태를 기록
# (wdmcp/jobs.py 의 잡 패턴 동형 구현 — jobs.py 는 data_dir 를 cwd 상대로 해석해 웹 서버 기동 위치에
#  따라 경로가 어긋날 수 있어, 여기서는 repo 루트 앵커로 통일한다)
from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from wdcore.config import get_settings

# repo 루트 (src/wdweb/runs.py → 두 단계 위) — 상대 경로 설정의 앵커 (wdpipeline.cli 와 동일 규약)
REPO_ROOT = Path(__file__).resolve().parents[2]

STAGES = ("ingest", "fragmentize", "scenario", "build")
# 문서 3형식도 같은 잡 경로를 탄다 (wdmcp.schemas.RENDER_TARGETS 와 동일 계약)
RENDER_TARGETS = ("video", "pptx", "html", "pdf", "docx")

_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")
# RLock — 파일 I/O(write_run/read_run)와 그것을 품는 read-modify-write(update_*)가
# 같은 잠금을 중첩 획득한다. 파이프라인·렌더·QA 스레드의 갱신 유실 방지.
_lock = threading.RLock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def data_dir() -> Path:
    d = get_settings().data_dir
    return d if d.is_absolute() else REPO_ROOT / d


def runs_dir() -> Path:
    d = data_dir() / "web_runs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_file(run_id: str) -> Path:
    return runs_dir() / f"{run_id}.json"


def new_run_id() -> str:
    return f"wr-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:4]}"


def sanitize_slug(slug: str | None) -> str | None:
    """빌드 디렉터리명으로 안전한 슬러그만 남긴다. 비면 None."""
    if not slug:
        return None
    s = _SLUG_RE.sub("-", slug.strip()).strip("-.")[:60]
    return s or None


# ── 원장 입출력 (파일이 진실) ────────────────────────────────────────────────


def write_run(run: dict) -> Path:
    path = run_file(run["run_id"])
    with _lock:
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    return path


def read_run(run_id: str) -> dict | None:
    path = run_file(run_id)
    with _lock:
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


def update_run(run_id: str, **updates) -> dict:
    with _lock:
        run = read_run(run_id)
        assert run is not None, f"실행 원장 유실: {run_id}"
        run.update(updates)
        run["updated_at"] = _now_iso()
        write_run(run)
        return run


def _update_stage(run_id: str, stage: str, **fields) -> dict:
    with _lock:
        run = read_run(run_id)
        assert run is not None, f"실행 원장 유실: {run_id}"
        for row in run["stages"]:
            if row["stage"] == stage:
                row.update(fields)
                break
        run["updated_at"] = _now_iso()
        write_run(run)
        return run


def _update_render(run_id: str, **fields) -> dict:
    with _lock:
        run = read_run(run_id)
        assert run is not None, f"실행 원장 유실: {run_id}"
        render = run.get("render") or {}
        render.update(fields)
        run["render"] = render
        run["updated_at"] = _now_iso()
        write_run(run)
        return run


def list_runs() -> list[dict]:
    """전체 실행을 최신순으로 반환한다 (run_id 에 UTC 타임스탬프가 박혀 있어 이름 역순 = 최신순)."""
    out: list[dict] = []
    for p in sorted(runs_dir().glob("*.json"), reverse=True):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


# ── 파이프라인 실행 (POST /api/runs) ─────────────────────────────────────────



def _format_of(build_dir: Path) -> str | None:
    """빌드 산출물의 scene-data.json 에서 포맷 id 를 읽는다 (없으면 render.toml 폴백)."""
    sd = Path(build_dir) / "scene-data.json"
    if not sd.is_file():
        return None
    try:
        return json.loads(sd.read_text(encoding="utf-8")).get("format")
    except ValueError:
        return None


def submit_run(report: dict, slug: str | None = None) -> dict:
    """보고서 JSON을 임시 저장하고 백그라운드 스레드로 ingest→fragmentize→scenario→build 를 돌린다."""
    run_id = new_run_id()
    # slug 는 표시용 이름일 뿐 디렉터리 키가 아니다 — 같은 slug 두 실행이 build/renders
    # 를 공유해 서로 덮어쓰는 사고를 막기 위해 run_id 꼬리를 붙여 항상 유일하게 만든다.
    base = sanitize_slug(slug)
    slug_s = f"{base}-{run_id[-4:]}" if base else run_id
    droot = data_dir()

    pipe_dir = droot / "pipeline" / run_id
    pipe_dir.mkdir(parents=True, exist_ok=True)
    raw_path = pipe_dir / "report.raw.json"
    raw_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    now = _now_iso()
    run = {
        "run_id": run_id,
        "slug": slug_s,
        "status": "queued",
        "stages": [
            {"stage": s, "status": "pending", "error": None, "output": None} for s in STAGES
        ],
        "scenario_summary": None,
        "build_dir": None,
        "entry": None,
        "render": None,
        "qa": None,
        "error": None,
        "created_at": now,
        "updated_at": now,
    }
    write_run(run)
    t = threading.Thread(
        target=_run_pipeline, args=(run_id, raw_path, slug_s, droot), daemon=True,
        name=f"wdweb-pipeline-{run_id}",
    )
    t.start()
    return run


def _run_pipeline(run_id: str, raw_path: Path, slug: str, droot: Path,
                  start_from: str | None = None) -> None:
    """워커 본체 — 단계별 상태를 원장에 기록하며 순차 실행. 예외는 해당 단계 failed 로 남긴다.

    start_from 을 주면 그 단계부터 돈다(재개). 앞 단계 산출물은 디스크에서 읽어 잇는다 —
    원장은 쓰다 만 채로 죽을 수 있지만 산출물은 쓰였거나 안 쓰였거나 둘 중 하나다.
    """
    from wdpipeline.resume import stages_from

    pipe_dir = droot / "pipeline" / run_id
    todo = set(stages_from(start_from)) if start_from else set(STAGES)
    stage = start_from or STAGES[0]
    norm = fragments = doc = None
    try:
        update_run(run_id, status="running", error=None)

        # P0 ingest
        stage = "ingest"
        norm_path = pipe_dir / "report.norm.json"
        if stage in todo:
            _update_stage(run_id, stage, status="running")
            from wdpipeline.ingest import ingest_report_file

            norm = ingest_report_file(raw_path)
            norm_path.write_text(json.dumps(norm, ensure_ascii=False, indent=2), encoding="utf-8")
            _update_stage(run_id, stage, status="done", output=str(norm_path))
        else:
            norm = json.loads(norm_path.read_text(encoding="utf-8"))

        # P1 fragmentize
        stage = "fragmentize"
        frag_path = pipe_dir / "fragments.json"
        if stage in todo:
            _update_stage(run_id, stage, status="running")
            from wdpipeline.fragmentize import fragmentize

            fragments = fragmentize(norm)
            frag_path.write_text(json.dumps(fragments, ensure_ascii=False, indent=2), encoding="utf-8")
            _update_stage(run_id, stage, status="done", output=str(frag_path))
        else:
            fragments = json.loads(frag_path.read_text(encoding="utf-8"))

        # P3 scenario (규칙 기반 데모 조립 — LLM 무호출)
        stage = "scenario"
        scen_path = pipe_dir / "scenario.json"
        from wdcore.models.scenario import ScenarioDoc
        from wdpipeline.scenario import assemble_demo_scenario, validate_scenario

        if stage in todo:
            _update_stage(run_id, stage, status="running")
            doc = assemble_demo_scenario(norm, fragments)
            errors = validate_scenario(doc)
            if errors:
                raise ValueError("시나리오 검증 실패: " + "; ".join(errors))
            scen_path.write_text(
                json.dumps(doc.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
        else:
            # 재개 — 사람이 고쳐 둔 시나리오가 있을 수 있으므로 디스크를 읽는다
            doc = ScenarioDoc.model_validate(
                json.loads(scen_path.read_text(encoding="utf-8")))
        summary = {
            "scene_count": len(doc.scenes),
            "total_dur": round(sum(s.dur for s in doc.scenes), 3),
            "core_message": doc.meta.core_message,
        }
        if stage in todo:
            _update_stage(run_id, stage, status="done", output=str(scen_path))
        update_run(run_id, scenario_summary=summary)

        # P4 build — 재개여도 항상 다시 굽는다. 앞 단계가 바뀌었을 수 있고,
        # 빌드는 비용이 낮으면서 어긋나면 가장 눈에 안 띄는 자리다.
        stage = "build"
        _update_stage(run_id, stage, status="running")
        from wdpipeline.build import build_render_package

        entry = Path(build_render_package(doc, droot / "build" / slug))
        _update_stage(run_id, stage, status="done", output=str(entry))
        update_run(run_id, status="done", build_dir=str(entry.parent), entry=entry.name,
                   error=None)
    except Exception as exc:  # 워커 스레드 — 어떤 실패든 원장에 남긴다
        msg = f"{type(exc).__name__}: {exc}"
        try:
            _update_stage(run_id, stage, status="failed", error=msg)
            update_run(run_id, status="failed", error=msg)
        except Exception:
            pass


# ── 렌더 실행 (POST /api/runs/{id}/render) ───────────────────────────────────


def submit_render(run_id: str, targets: list[str], fps: int | None = None,
                  doc_style: str = "report", pptx_mode: str = "hybrid",
                  narration: bool = False) -> dict:
    """빌드 완료된 실행에 wdrender exporter 를 백그라운드로 돌린다. 상태는 run.render 에 기록."""
    run = read_run(run_id)
    assert run is not None
    _update_render(
        run_id, status="queued", targets=targets, doc_style=doc_style,
        pptx_mode=pptx_mode, narration=narration, outputs={}, error=None,
        started_at=_now_iso(),
    )
    t = threading.Thread(
        target=_run_render, args=(run_id, targets, fps, data_dir(), doc_style, pptx_mode, narration),
        daemon=True,
        name=f"wdweb-render-{run_id}",
    )
    t.start()
    return read_run(run_id)  # type: ignore[return-value]


def resume_run(run_id: str) -> dict:
    """실패한 실행을 끊긴 단계부터 다시 돌린다 (PLAN M3 ④).

    재개 지점은 **원장이 아니라 디스크**가 정한다 — 프로세스가 원장을 쓰다 죽으면
    원장은 'running' 인 채로 남지만, 산출물은 쓰였거나 안 쓰였거나 둘 중 하나다.
    """
    from wdpipeline.resume import resume_point

    run = read_run(run_id)
    if run is None:
        raise FileNotFoundError(f"실행 없음: {run_id}")
    if run.get("status") == "running":
        raise RuntimeError("이미 진행 중이다 — 끝나거나 실패한 뒤에 재개하라")

    droot = data_dir()
    pipe_dir = droot / "pipeline" / run_id
    build_dir = droot / "build" / run["slug"]
    start = resume_point(pipe_dir, build_dir)
    if start is None:
        return {"run_id": run_id, "resumed": False,
                "note": "모든 단계의 산출물이 이미 있다 — 다시 돌릴 것이 없다"}

    raw_path = pipe_dir / "report.raw.json"
    if not raw_path.is_file():
        raise FileNotFoundError(f"원본 보고서가 없다: {raw_path}")

    for row in run["stages"]:
        if row["stage"] == start or row["status"] == "failed":
            row["status"], row["error"] = "pending", None
    write_run(run)

    threading.Thread(
        target=_run_pipeline, args=(run_id, raw_path, run["slug"], droot, start),
        daemon=True, name=f"wdweb-resume-{run_id}",
    ).start()
    return {"run_id": run_id, "resumed": True, "start_from": start}


def _run_render(run_id: str, targets: list[str], fps: int | None, droot: Path,
                doc_style: str = "report", pptx_mode: str = "hybrid",
                narration: bool = False) -> None:
    """렌더 워커 — wdmcp/jobs.py 의 exporter 실행부 동형. 실패는 render.status=failed 로 기록."""
    work: Path | None = None   # 내레이션 씬 음성 임시 보관 — 끝나면 지운다
    try:
        run = read_run(run_id)
        assert run is not None
        root = Path(run["build_dir"] or "")
        rel = run["entry"] or ""

        from wdrender.config import RenderConfig, load_config
        from wdrender.exporter_pptx import export_pptx
        from wdrender.exporter_video import export_video
        from wdrender.page_session import vendor_resources

        cfg = load_config()
        if fps:
            cfg = RenderConfig(
                fps=fps, width=cfg.width, height=cfg.height,
                viewport_margin=cfg.viewport_margin, ffmpeg_args=cfg.ffmpeg_args,
                default_still_progress=cfg.default_still_progress, vendor_dir=cfg.vendor_dir,
            )
        resources = vendor_resources("/vendor") if (root / "vendor").is_dir() else None

        out_dir = droot / "renders" / root.name
        out_dir.mkdir(parents=True, exist_ok=True)

        _update_render(run_id, status="rendering")
        outputs: dict[str, str] = {}
        detail: dict = {}
        # 포맷의 outputs 가 실제 산출을 지배한다 — PPT 전용 포맷(outputs: [pptx])에서
        # mp4 를 굽다 실패하지 않게, wda render 와 같은 단일 판정점을 쓴다.
        from wdpipeline.format import render_targets

        # 문서 3형식은 무대 규격과 무관하다(심의 산출물에서 나온다) — 포맷 outputs 필터 면제.
        allowed = set(render_targets(_format_of(root))) | {"html", "pdf", "docx"}
        targets = [t for t in targets if t in allowed]

        # 내레이션 — 실측·재조정·재빌드를 영상 렌더 앞에 끝낸다 (결정 56~59)
        plan = None
        if narration and "video" in targets:
            import tempfile

            from wdpipeline.narration import prepare

            work = Path(tempfile.mkdtemp(prefix="wda_narr_"))
            plan = prepare(root, work, scenario_path=droot / "pipeline" / run_id / "scenario.json",
                           log=lambda m: None)

        # scene-data.json 이 있으면 stills/내레이션을 PPTX 캡처 시각·발표자 노트로 쓴다
        # (내레이션 재조정 뒤에 읽는다 — dur 가 바뀌면 캡처 시각도 옮겨진다)
        stills: dict[str, list[float]] | None = None
        notes: dict[str, str] | None = None
        scene_data = root / "scene-data.json"
        if scene_data.is_file():
            doc = json.loads(scene_data.read_text(encoding="utf-8"))
            scenes = doc.get("scenes") or []
            stills = {s["name"]: s["stills"] for s in scenes if s.get("stills")} or None
            notes = {s["name"]: s["narration"] for s in scenes if s.get("narration")} or None

        if "video" in targets:
            out = out_dir / "video.mp4"
            detail["video"] = export_video(
                root, rel, out, config=cfg, resources=resources,
                format_id=_format_of(root), log=lambda m: None,
            )
            outputs["video"] = str(out)
            if plan is not None:
                from wdpipeline.narration import finish

                detail["narration"] = finish(plan, out, out_dir, log=lambda m: None)
        if "pptx" in targets:
            out = out_dir / "slides.pptx"
            detail["pptx"] = export_pptx(
                root, rel, out, config=cfg, resources=resources,
                format_id=_format_of(root), stills=stills, notes=notes,
                mode=pptx_mode, log=lambda m: None,
            )
            outputs["pptx"] = str(out)

        # 문서 3형식 — 심의 산출물을 읽는 글로. wdmcp.jobs 와 같은 절차를 쓴다
        # (삽화용 씬 스틸을 run_dir/stills 규약 이름으로 먼저 굽고 조립·검증·export).
        doc_targets = [t for t in targets if t in ("html", "pdf", "docx")]
        if doc_targets:
            from wdmcp.jobs import _capture_doc_stills
            from wdpipeline.document import assemble_document, validate_document
            from wdrender.exporter_doc import export_document

            run_dir = (droot / "pipeline" / run_id).resolve()
            _capture_doc_stills(root, rel, run_dir / "stills", resources)
            ddoc = assemble_document(run_dir, build_dir=root, style=doc_style)
            errs = validate_document(ddoc)
            if errs:
                raise ValueError("문서 검증 실패: " + "; ".join(errs))
            res = export_document(ddoc, out_dir, stem="report",
                                  formats=tuple(doc_targets), assets_root=root,
                                  log=lambda m: None)
            for kind, info in res.items():
                outputs[kind] = str(out_dir / f"report.{kind}")
                detail[kind] = info

        _update_render(run_id, status="done", outputs=outputs, detail=detail,
                       finished_at=_now_iso())
    except Exception as exc:  # 워커 스레드 — 어떤 실패든 원장에 남긴다
        try:
            _update_render(run_id, status="failed", error=f"{type(exc).__name__}: {exc}",
                           finished_at=_now_iso())
        except Exception:
            pass
    finally:
        if work is not None:
            import shutil

            shutil.rmtree(work, ignore_errors=True)


# ── QA (POST /api/runs/{id}/qa) ─────────────────────────────────────────────


def run_qa(run_id: str, gates: list[str] | None = None) -> dict:
    """wdqa 게이트를 동기 실행하고 결과 요약을 원장에 기록한다."""
    run = read_run(run_id)
    assert run is not None and run.get("build_dir")
    build_dir = Path(run["build_dir"])

    scenario: dict | None = None
    scene_data = build_dir / "scene-data.json"
    if scene_data.is_file():
        scenario = json.loads(scene_data.read_text(encoding="utf-8"))

    from wdqa.gates import run_gates

    result = run_gates(build_dir, scenario=scenario, gates=gates)
    update_run(run_id, qa={
        "passed": result["passed"],
        "summary": result["summary"],
        "report_path": result["report_path"],
        "ran_at": _now_iso(),
    })
    return result


# ── 산출물 조회 ──────────────────────────────────────────────────────────────


def artifact_paths(run: dict) -> dict[str, Path | None]:
    """실행 1건의 mp4/pptx/문서3종/qa.json/scenario.json 경로를 계산한다 (존재 보장 없음)."""
    out: dict[str, Path | None] = {
        "mp4": None, "pptx": None, "html": None, "pdf": None, "docx": None,
        "qa": None, "scenario": None,
    }
    if run.get("build_dir"):
        renders = data_dir() / "renders" / Path(run["build_dir"]).name
        out["mp4"] = renders / "video.mp4"
        out["pptx"] = renders / "slides.pptx"
        for kind in ("html", "pdf", "docx"):  # exporter_doc 의 stem 은 "report"
            out[kind] = renders / f"report.{kind}"
    qa = run.get("qa") or {}
    if qa.get("report_path"):
        out["qa"] = Path(qa["report_path"])
    scen = data_dir() / "pipeline" / run["run_id"] / "scenario.json"
    out["scenario"] = scen
    return out


def artifacts_status(run: dict) -> dict:
    """산출물 존재 여부·크기 요약 (GET /api/runs/{id}/artifacts)."""
    status: dict = {}
    for kind, path in artifact_paths(run).items():
        exists = bool(path and path.is_file())
        status[kind] = {
            "exists": exists,
            "size": path.stat().st_size if exists else None,  # type: ignore[union-attr]
            "path": str(path) if path else None,
        }
    return status
