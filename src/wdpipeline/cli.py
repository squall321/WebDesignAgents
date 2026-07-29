# wda CLI — 파이프라인 P0~P5 실행 진입점 (typer): ingest/fragmentize/scenario/build/render/run/validate
from __future__ import annotations

import json
from pathlib import Path

import typer

from wdcore.config import get_settings
from wdpipeline.format import DEFAULT_FORMAT_ID

app = typer.Typer(help="WebDesignAgents 파이프라인 CLI", no_args_is_help=True)

# repo 루트 (src/wdpipeline/cli.py → 두 단계 위) — 상대 경로 설정의 앵커
_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULES_ROOT = _REPO_ROOT / "modules"

NORM_FILE = "report.norm.json"
FRAGMENTS_FILE = "fragments.json"
SCENARIO_FILE = "scenario.json"


def _data_dir() -> Path:
    d = get_settings().data_dir
    return d if d.is_absolute() else _REPO_ROOT / d


def _run_dir(run_id: str) -> Path:
    return _data_dir() / "pipeline" / run_id


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path):
    if not path.is_file():
        typer.echo(f"[오류] 파일 없음: {path} — 앞 단계를 먼저 실행하라", err=True)
        raise typer.Exit(code=1)
    return json.loads(path.read_text(encoding="utf-8"))


@app.command()
def version() -> None:
    """설치 확인용."""
    typer.echo("webdesignagents 0.1.0")


@app.command()
def ingest(
    file: Path = typer.Option(..., "--file", exists=True, help="ReportArchive 복붙 JSON"),
    run_id: str = typer.Option("", "--run-id", help="파이프라인 run id (기본: doc_id)"),
    assets_dir: Path | None = typer.Option(None, "--assets-dir", help="file_id → 로컬 자산 매핑 디렉터리"),
) -> None:
    """P0 — 복붙 JSON 을 정규화해 data/pipeline/{run_id}/report.norm.json 으로 저장한다."""
    from wdpipeline.ingest import ingest_report_file

    norm = ingest_report_file(file, assets_dir=assets_dir)
    rid = run_id or norm["doc_id"]
    out = _run_dir(rid) / NORM_FILE
    _write_json(out, norm)
    skipped = [a["file_id"] for a in norm["assets"] if a["local_path"] is None]
    typer.echo(f"[ingest] doc_id={norm['doc_id']} pages={len(norm['pages'])} → {out}")
    if skipped:
        typer.echo(f"[ingest] 자산 스킵 {len(skipped)}건: {', '.join(skipped)}")


@app.command()
def fragmentize(
    run_id: str = typer.Option(..., "--run-id", help="ingest 를 마친 run id"),
) -> None:
    """P1 — report.norm.json 을 규칙 기반으로 조각 분해해 fragments.json 으로 저장한다."""
    from wdpipeline.fragmentize import fragmentize as _fragmentize

    norm = _read_json(_run_dir(run_id) / NORM_FILE)
    frags = _fragmentize(norm)
    out = _run_dir(run_id) / FRAGMENTS_FILE
    _write_json(out, frags)
    by_type: dict[str, int] = {}
    for f in frags:
        by_type[f["type"]] = by_type.get(f["type"], 0) + 1
    typer.echo(f"[fragmentize] {len(frags)}조각 {by_type} → {out}")


@app.command()
def formats() -> None:
    """사용 가능한 포맷(formats/{id}/format.yaml) 목록을 보여준다."""
    from wdpipeline.format import FormatError, list_formats, load_format

    ids = list_formats()
    if not ids:
        typer.echo("[formats] 등록된 포맷이 없다 — formats/{id}/format.yaml 을 작성하라", err=True)
        raise typer.Exit(code=1)
    for fid in ids:
        try:
            spec = load_format(fid)
        except FormatError as e:
            typer.echo(f"  {fid}: [로드 실패] {str(e).splitlines()[0]}")
            continue
        # 분량은 산출에 따라 자가 다르다 — 영상은 초, PPT 전용은 슬라이드 수.
        if spec.slides is not None and not spec.wants("video"):
            budget = f"{spec.slides.target}장(허용 {spec.slides.min}~{spec.slides.max})"
        else:
            budget = f"{spec.duration.target}s(허용 {spec.duration.min}~{spec.duration.max})"
        typer.echo(
            f"  {fid}: {spec.name_ko} — 무대 {spec.stage.w}x{spec.stage.h} · {budget} · "
            f"산출 {'+'.join(spec.outputs)} · 골격 {'→'.join(spec.skeleton)}"
        )


@app.command()
def scenario(
    run_id: str = typer.Option(..., "--run-id", help="fragmentize 를 마친 run id"),
    format: str = typer.Option(
        DEFAULT_FORMAT_ID, "--format", help="포맷 id (wda formats 로 목록 확인)"
    ),
) -> None:
    """P3 — 규칙 기반 데모 시나리오를 조립·검증해 scenario.json 으로 저장한다."""
    from wdpipeline.format import FormatError
    from wdpipeline.scenario import assemble_demo_scenario, validate_scenario

    norm = _read_json(_run_dir(run_id) / NORM_FILE)
    frags = _read_json(_run_dir(run_id) / FRAGMENTS_FILE)
    try:
        doc = assemble_demo_scenario(norm, frags, format=format)
    except (FormatError, NotImplementedError) as e:
        for line in str(e).splitlines():
            typer.echo(f"[포맷 오류] {line}", err=True)
        raise typer.Exit(code=1) from None
    errors = validate_scenario(doc, modules_root=_MODULES_ROOT)
    if errors:
        for e in errors:
            typer.echo(f"[검증 실패] {e}", err=True)
        raise typer.Exit(code=1)
    out = _run_dir(run_id) / SCENARIO_FILE
    _write_json(out, doc.model_dump())
    total = sum(s.dur for s in doc.scenes)
    typer.echo(
        f"[scenario] 포맷 {doc.format} 씬 {len(doc.scenes)}개 Σdur={total}s 검증 통과 → {out}"
    )


@app.command()
def build(
    run_id: str = typer.Option(..., "--run-id", help="scenario 를 마친 run id"),
    slug: str = typer.Option("", "--slug", help="빌드 슬러그 (기본: run_id)"),
) -> None:
    """P4 — scenario.json 을 렌더 패키지 data/build/{slug}/ 로 조립한다."""
    from wdcore.models.scenario import ScenarioDoc
    from wdpipeline.build import build_render_package
    from wdpipeline.format import FormatError
    from wdpipeline.scenario import validate_scenario

    try:
        doc = ScenarioDoc.model_validate(_read_json(_run_dir(run_id) / SCENARIO_FILE))
    except Exception as e:  # pydantic ValidationError 포함 — 원시 트레이스백 대신 정제 출력
        for line in str(e).splitlines():
            typer.echo(f"[검증 실패] {line}", err=True)
        raise typer.Exit(code=1) from None
    errors = validate_scenario(doc, modules_root=_MODULES_ROOT)
    if errors:
        for e in errors:
            typer.echo(f"[검증 실패] {e}", err=True)
        raise typer.Exit(code=1)
    s = slug or run_id
    try:
        entry = build_render_package(doc, _data_dir() / "build" / s, modules_root=_MODULES_ROOT)
    except (FormatError, FileNotFoundError) as e:
        for line in str(e).splitlines():
            typer.echo(f"[포맷 오류] {line}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"[build] 포맷 {doc.format} 엔트리 생성 → {entry}")


@app.command()
def render(
    slug: str = typer.Option(..., "--slug", help="build 를 마친 슬러그"),
    fps: int = typer.Option(0, "--fps", help="프레임레이트 오버라이드 (기본: configs/render.toml)"),
    skip_video: bool = typer.Option(False, "--skip-video", help="mp4 생략 (pptx 만)"),
    format: str = typer.Option("", "--format", help="포맷 오버라이드 (기본: scene-data.json 의 format)"),
) -> None:
    """P5 — data/build/{slug}/ 를 mp4 + pptx 로 export 한다 (wdrender 호출)."""
    from wdrender.config import load_config
    from wdrender.exporter_pptx import export_pptx
    from wdrender.exporter_video import export_video
    from wdpipeline.build import ENTRY_NAME
    from wdpipeline.format import render_targets

    build_dir = _data_dir() / "build" / slug
    if not (build_dir / ENTRY_NAME).is_file():
        typer.echo(f"[오류] 빌드 없음: {build_dir / ENTRY_NAME} — wda build 먼저", err=True)
        raise typer.Exit(code=1)
    scene_data = _read_json(build_dir / "scene-data.json")
    stills = {s["name"]: s["stills"] for s in scene_data["scenes"] if s.get("stills")}
    notes = {s["name"]: s["narration"] for s in scene_data["scenes"] if s.get("narration")}
    # 무대·슬라이드 규격은 빌드된 시나리오의 포맷이 지배한다 (--format 은 명시 오버라이드)
    fid = format or scene_data.get("format") or DEFAULT_FORMAT_ID

    # 무엇을 뽑을지는 포맷의 outputs 가 정한다 — PPT 전용 포맷(outputs: [pptx])은 mp4 를
    # 아예 시도하지 않는다. --skip-video 는 그 위에 얹는 사용자 오버라이드다.
    targets = render_targets(fid, skip_video=skip_video)
    if not targets:
        typer.echo(f"[오류] 포맷 {fid} 에 실행할 렌더 타깃이 없다 (--skip-video 와 outputs 확인)", err=True)
        raise typer.Exit(code=1)

    cfg = load_config()
    if fps > 0:
        cfg.fps = fps
    out_dir = _data_dir() / "renders" / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    if "video" in targets:
        info = export_video(
            build_dir, ENTRY_NAME, out_dir / f"{slug}.mp4", config=cfg, format_id=fid
        )
        typer.echo(
            f"[render] mp4 포맷={fid} duration={info['duration']}s fps={info['fps']} "
            f"frames={info['frames']} → {info['out']}"
        )
    else:
        typer.echo(f"[render] mp4 생략 — 포맷 {fid} 산출 {'+'.join(targets) or '(없음)'}")
    if "pptx" in targets:
        pinfo = export_pptx(
            build_dir, ENTRY_NAME, out_dir / f"{slug}.pptx",
            config=cfg, format_id=fid, stills=stills, notes=notes,
        )
        typer.echo(f"[render] pptx {pinfo['slides']}장/{pinfo['scenes']}씬 → {pinfo['out']}")


@app.command()
def run(
    file: Path = typer.Option(..., "--file", exists=True, help="ReportArchive 복붙 JSON"),
    slug: str = typer.Option(..., "--slug", help="run id 겸 빌드/렌더 슬러그"),
    assets_dir: Path | None = typer.Option(None, "--assets-dir"),
    fps: int = typer.Option(0, "--fps", help="프레임레이트 오버라이드"),
    format: str = typer.Option(
        DEFAULT_FORMAT_ID, "--format", help="포맷 id (wda formats 로 목록 확인)"
    ),
) -> None:
    """P0→P1→P3→P4→P5 전 단계 일괄 실행 (규칙 기반 데모 파이프라인)."""
    ingest(file=file, run_id=slug, assets_dir=assets_dir)
    fragmentize(run_id=slug)
    scenario(run_id=slug, format=format)
    build(run_id=slug, slug=slug)
    render(slug=slug, fps=fps, skip_video=False, format="")
    typer.echo(f"[run] 완료 — data/renders/{slug}/")


@app.command()
def repro(
    module: str = typer.Option("", "--module", help="모듈 id 하나만 검증 (기본: 레지스트리 전 씬 템플릿 모듈)"),
    runs: int = typer.Option(2, "--runs", help="독립 세션 렌더 횟수"),
    update_golden: bool = typer.Option(
        False, "--update-golden", help="typical 골든 스냅샷 재생성 (기존과의 diff 는 리포트에 기록)"
    ),
    build_slug: str = typer.Option(
        "", "--build", help="빌드 슬러그 — 같은 시나리오 2회 빌드 바이트 동일성 검사 추가"
    ),
) -> None:
    """QA — 템플릿 재현력 검증 (세션 간·골든 대비·빌드 간). 리포트는 data/qa_reports 에 저장."""
    from datetime import datetime

    from wdqa.repro import record_quality, template_modules, verify_all, verify_build

    fixtures_by_module = None
    if module:
        ids = {m["id"] for m in template_modules(_MODULES_ROOT)}
        dirs = {m["dir"]: m["id"] for m in template_modules(_MODULES_ROOT)}
        mid = module if module in ids else dirs.get(module, "")
        if not mid:
            typer.echo(f"[오류] 레지스트리에 없는 모듈: {module}", err=True)
            raise typer.Exit(code=1)
        # 전 모듈 순회 대신 대상 1종만 3픽스처, 나머지는 생략
        fixtures_by_module = {i: () for i in ids}
        fixtures_by_module[mid] = ("min", "typical", "max")

    report = verify_all(
        _MODULES_ROOT, runs=runs, fixtures_by_module=fixtures_by_module,
        update_golden=update_golden, progress=lambda s: typer.echo(f"[repro] {s}"),
    )

    if build_slug:
        report["build"] = verify_build(_data_dir() / "build" / build_slug)
        b = report["build"]
        typer.echo(f"[repro] build {build_slug}: {'PASS' if b['passed'] else 'FAIL'} — "
                   + ", ".join(f"{k}={'=' if v['identical'] else '≠'}"
                               for k, v in b.get("files", {}).items()))
        report["passed"] = report["passed"] and b["passed"]

    out_dir = _data_dir() / "qa_reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"repro-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    _write_json(out, report)

    typer.echo(f"[repro] {'통과' if report['passed'] else '실패'} — 모듈 {report['modules']}종 → {out}")
    typer.echo(f"  {'모듈':<22} {'판정':<6} {'max_diff_ratio':<16} golden_diff")
    mods_by_id = {m["id"]: m for m in template_modules(_MODULES_ROOT)}
    for r in report["results"]:
        g = r["fixtures"].get("typical", {}).get("golden_diff_ratio")
        typer.echo(
            f"  {r['module']:<22} {'PASS' if r['passed'] else 'FAIL':<6} "
            f"{r['max_diff_ratio']:<16.8f} {'-' if g is None else f'{g:.8f}'}"
        )
        record_quality(mods_by_id[r["module"]]["mod_dir"], r,
                       checked_at=report["checked_at"])
    if not report["passed"]:
        raise typer.Exit(code=1)


@app.command()
def validate() -> None:
    """페르소나 레지스트리 + 씬 템플릿 모듈 레지스트리 정합성 검사."""
    from jsonschema import Draft202012Validator
    from wdcore.registry.registry import load_registry
    import yaml

    n_errors = 0

    reg = load_registry(root=_REPO_ROOT / "personas")
    typer.echo(f"[validate] 페르소나 {len(reg.personas)}인 · 지식카드 {len(reg.all_cards())}장")
    for issue in reg.issues:
        typer.echo(f"  [{issue.level}] {issue.where}: {issue.message}")
        if issue.level == "error":
            n_errors += 1

    tpl_root = _MODULES_ROOT / "scene-templates"
    for mod_dir in sorted(p for p in tpl_root.iterdir() if p.is_dir()):
        name = mod_dir.name
        try:
            module = yaml.safe_load((mod_dir / "module.yaml").read_text(encoding="utf-8"))
            schema = json.loads((mod_dir / "schema.json").read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
        except Exception as e:  # noqa: BLE001 — 검증 결과 수집
            typer.echo(f"  [error] {name}: 모듈 로드 실패 — {e}")
            n_errors += 1
            continue
        for fx in ("min", "typical", "max"):
            fx_path = mod_dir / "fixtures" / f"{fx}.json"
            if not fx_path.is_file():
                typer.echo(f"  [error] {name}: fixture 누락 — {fx}.json")
                n_errors += 1
                continue
            errs = list(validator.iter_errors(json.loads(fx_path.read_text(encoding="utf-8"))))
            for err in errs:
                typer.echo(f"  [error] {name}/fixtures/{fx}.json: {err.message}")
                n_errors += 1
        typer.echo(f"[validate] {module.get('id', name)} status={module.get('status', '?')}")

    if n_errors:
        typer.echo(f"[validate] 오류 {n_errors}건", err=True)
        raise typer.Exit(code=1)
    typer.echo("[validate] 통과")


if __name__ == "__main__":
    app()
