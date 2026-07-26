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
RENDER_TARGETS = ("video", "pptx")

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


def _run_pipeline(run_id: str, raw_path: Path, slug: str, droot: Path) -> None:
    """워커 본체 — 단계별 상태를 원장에 기록하며 순차 실행. 예외는 해당 단계 failed 로 남긴다."""
    pipe_dir = droot / "pipeline" / run_id
    stage = STAGES[0]
    try:
        update_run(run_id, status="running")

        # P0 ingest
        stage = "ingest"
        _update_stage(run_id, stage, status="running")
        from wdpipeline.ingest import ingest_report_file

        norm = ingest_report_file(raw_path)
        norm_path = pipe_dir / "report.norm.json"
        norm_path.write_text(json.dumps(norm, ensure_ascii=False, indent=2), encoding="utf-8")
        _update_stage(run_id, stage, status="done", output=str(norm_path))

        # P1 fragmentize
        stage = "fragmentize"
        _update_stage(run_id, stage, status="running")
        from wdpipeline.fragmentize import fragmentize

        fragments = fragmentize(norm)
        frag_path = pipe_dir / "fragments.json"
        frag_path.write_text(json.dumps(fragments, ensure_ascii=False, indent=2), encoding="utf-8")
        _update_stage(run_id, stage, status="done", output=str(frag_path))

        # P3 scenario (규칙 기반 데모 조립 — LLM 무호출)
        stage = "scenario"
        _update_stage(run_id, stage, status="running")
        from wdpipeline.scenario import assemble_demo_scenario, validate_scenario

        doc = assemble_demo_scenario(norm, fragments)
        errors = validate_scenario(doc)
        if errors:
            raise ValueError("시나리오 검증 실패: " + "; ".join(errors))
        scen_path = pipe_dir / "scenario.json"
        scen_path.write_text(
            json.dumps(doc.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary = {
            "scene_count": len(doc.scenes),
            "total_dur": round(sum(s.dur for s in doc.scenes), 3),
            "core_message": doc.meta.core_message,
        }
        _update_stage(run_id, stage, status="done", output=str(scen_path))
        update_run(run_id, scenario_summary=summary)

        # P4 build
        stage = "build"
        _update_stage(run_id, stage, status="running")
        from wdpipeline.build import build_render_package

        entry = Path(build_render_package(doc, droot / "build" / slug))
        _update_stage(run_id, stage, status="done", output=str(entry))
        update_run(run_id, status="done", build_dir=str(entry.parent), entry=entry.name)
    except Exception as exc:  # 워커 스레드 — 어떤 실패든 원장에 남긴다
        msg = f"{type(exc).__name__}: {exc}"
        try:
            _update_stage(run_id, stage, status="failed", error=msg)
            update_run(run_id, status="failed", error=msg)
        except Exception:
            pass


# ── 렌더 실행 (POST /api/runs/{id}/render) ───────────────────────────────────


def submit_render(run_id: str, targets: list[str], fps: int | None = None) -> dict:
    """빌드 완료된 실행에 wdrender exporter 를 백그라운드로 돌린다. 상태는 run.render 에 기록."""
    run = read_run(run_id)
    assert run is not None
    _update_render(
        run_id, status="queued", targets=targets, outputs={}, error=None,
        started_at=_now_iso(),
    )
    t = threading.Thread(
        target=_run_render, args=(run_id, targets, fps, data_dir()), daemon=True,
        name=f"wdweb-render-{run_id}",
    )
    t.start()
    return read_run(run_id)  # type: ignore[return-value]


def _run_render(run_id: str, targets: list[str], fps: int | None, droot: Path) -> None:
    """렌더 워커 — wdmcp/jobs.py 의 exporter 실행부 동형. 실패는 render.status=failed 로 기록."""
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

        # scene-data.json 이 있으면 stills/내레이션을 PPTX 캡처 시각·발표자 노트로 쓴다
        stills: dict[str, list[float]] | None = None
        notes: dict[str, str] | None = None
        scene_data = root / "scene-data.json"
        if scene_data.is_file():
            doc = json.loads(scene_data.read_text(encoding="utf-8"))
            scenes = doc.get("scenes") or []
            stills = {s["name"]: s["stills"] for s in scenes if s.get("stills")} or None
            notes = {s["name"]: s["narration"] for s in scenes if s.get("narration")} or None

        out_dir = droot / "renders" / root.name
        out_dir.mkdir(parents=True, exist_ok=True)

        _update_render(run_id, status="rendering")
        outputs: dict[str, str] = {}
        detail: dict = {}
        if "video" in targets:
            out = out_dir / "video.mp4"
            detail["video"] = export_video(
                root, rel, out, config=cfg, resources=resources, log=lambda m: None,
            )
            outputs["video"] = str(out)
        if "pptx" in targets:
            out = out_dir / "slides.pptx"
            detail["pptx"] = export_pptx(
                root, rel, out, config=cfg, resources=resources,
                stills=stills, notes=notes, log=lambda m: None,
            )
            outputs["pptx"] = str(out)
        _update_render(run_id, status="done", outputs=outputs, detail=detail,
                       finished_at=_now_iso())
    except Exception as exc:  # 워커 스레드 — 어떤 실패든 원장에 남긴다
        try:
            _update_render(run_id, status="failed", error=f"{type(exc).__name__}: {exc}",
                           finished_at=_now_iso())
        except Exception:
            pass


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
    """실행 1건의 mp4/pptx/qa.json/scenario.json 경로를 계산한다 (존재 보장 없음)."""
    out: dict[str, Path | None] = {"mp4": None, "pptx": None, "qa": None, "scenario": None}
    if run.get("build_dir"):
        renders = data_dir() / "renders" / Path(run["build_dir"]).name
        out["mp4"] = renders / "video.mp4"
        out["pptx"] = renders / "slides.pptx"
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
