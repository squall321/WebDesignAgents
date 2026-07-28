# 템플릿 재현력 하네스 — 같은 데이터·같은 템플릿이 세션 간·골든 대비·빌드 간 3층에서 같은 화면인지 검증
from __future__ import annotations

import hashlib
import io
import json
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Callable, Iterator

import yaml

from wdrender.page_session import EXPORTABLE_SVG, vendor_resources
from wdrender.server import StaticServer

from .config import REPO_ROOT, QAConfig
from .gate7_framematch import pixel_diff_ratio

FIXTURES = ("min", "typical", "max")
GOLDEN_NAME = "typical.png"

# 편집 크롬 제거 + 무대 원척 고정 (wdrender.page_session 과 동일 규약 — 골든과 같은 조건)
_EXPORT_CSS = (
    "[data-omelette-chrome]{display:none !important;}\n"
    f"{EXPORTABLE_SVG}{{transform:none !important; box-shadow:none !important;}}"
)


# ---------------------------------------------------------------- 레지스트리

def template_modules(modules_root: Path | None = None) -> list[dict]:
    """registry.yaml 의 scene-template 모듈 목록 — {id, dir, mod_dir, stage}."""
    root = Path(modules_root) if modules_root is not None else REPO_ROOT / "modules"
    reg = yaml.safe_load((root / "registry.yaml").read_text(encoding="utf-8")) or {}
    out: list[dict] = []
    for m in reg.get("modules", []):
        if m.get("type") != "scene-template":
            continue
        rel = Path(m["path"])
        mod_dir = root / rel.relative_to("modules") if rel.parts[:1] == ("modules",) else root / rel
        out.append({
            "id": m["id"],
            "dir": mod_dir.name,
            "mod_dir": mod_dir,
            "stage": m.get("stage") or {"w": 1920, "h": 1080},
        })
    return out


def _find_module(module_id: str, modules_root: Path | None = None) -> dict:
    mods = template_modules(modules_root)
    for m in mods:
        if m["id"] == module_id or m["dir"] == module_id:
            return m
    known = ", ".join(m["id"] for m in mods)
    raise KeyError(f"레지스트리에 없는 모듈: {module_id} (등록: {known})")


# ---------------------------------------------------------------- 렌더 세션

@contextmanager
def _repro_env() -> Iterator[tuple]:
    """repo 루트 정적 서버 + 공유 크로미엄 (독립성은 run 별 새 브라우저 컨텍스트로 확보)."""
    from playwright.sync_api import sync_playwright

    with StaticServer(REPO_ROOT) as srv, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        try:
            yield browser, srv
        finally:
            browser.close()


def _render_once(browser, srv: StaticServer, mod: dict, fixture: str, cfg: QAConfig) -> dict:
    """preview 를 독립 컨텍스트로 1회 렌더 — 스틸 PNG·스케줄 시각(still/nat/duration)·오류 수집.

    구 프리뷰(가로 7+3종)는 ?fixture= 를 읽지 않으므로, fixtures/*.json 요청을 라우트
    인터셉트해 목표 픽스처 바이트로 응답한다 (프리뷰 파일 무수정 원칙).
    """
    entry_rel = str(mod["mod_dir"].resolve().relative_to(REPO_ROOT) / "preview.html")
    w, h = int(mod["stage"]["w"]), int(mod["stage"]["h"])
    fixture_path = mod["mod_dir"] / "fixtures" / f"{fixture}.json"
    if not fixture_path.is_file():
        return {"error": f"fixture 없음: {fixture_path}"}
    fixture_bytes = fixture_path.read_bytes()

    ctx = browser.new_context(viewport={"width": w + 60, "height": h + 60})
    try:
        page = ctx.new_page()
        errors: list[str] = []
        page.on("console", lambda m: errors.append(f"console.error: {m.text}")
                if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        page.add_init_script(
            f"window.__resources = {json.dumps(vendor_resources('/web/vendor'))};"
        )
        page.route(
            f"**/scene-templates/{mod['dir']}/fixtures/*.json",
            lambda route: route.fulfill(
                status=200, content_type="application/json", body=fixture_bytes
            ),
        )
        page.goto(f"{srv.url_for(entry_rel)}?fixture={fixture}",
                  wait_until="load", timeout=60_000)
        page.wait_for_selector(EXPORTABLE_SVG, state="attached", timeout=60_000)
        page.evaluate("() => document.fonts.ready.then(() => true)")
        page.wait_for_selector(
            f'{EXPORTABLE_SVG}[data-om-fonts-inlined="true"]',
            state="attached", timeout=60_000,
        )
        page.add_style_tag(content=_EXPORT_CSS)

        svg = page.query_selector(EXPORTABLE_SVG)
        duration = float(svg.get_attribute("data-om-exportable-video-with-duration-secs"))
        sync_seek = svg.get_attribute("data-om-sync-seek") == "true"
        box = svg.bounding_box()
        if box is None or abs(box["width"] - w) > 1 or abs(box["height"] - h) > 1:
            return {"error": f"무대 원척 고정 실패 — 기대 {w}x{h}, 실측 {box}", "errors": errors}
        clip = {"x": round(box["x"]), "y": round(box["y"]), "width": w, "height": h}
        meta = page.evaluate("() => window.__OMX_PREVIEW__ || null")

        fps = cfg.resolved_fps()
        raw_still = (float(meta["still"]) if isinstance(meta, dict)
                     and meta.get("still") is not None else duration * 0.9)
        still = min(max(raw_still, 0.0), max(0.0, duration - 1.0 / fps))
        page.eval_on_selector(
            EXPORTABLE_SVG,
            "(el, t) => { el.dispatchEvent(new CustomEvent("
            "'data-om-seek-to-time-frame', {detail: {time: t, sync: true}})); }",
            still,
        )
        if not sync_seek:
            page.evaluate("() => new Promise(r => requestAnimationFrame("
                          "() => requestAnimationFrame(() => r())))")
        # 이미지 자산(d-media 등) 로드 완주 대기 — 세션 간 로드 타이밍 차가 diff 로 오인되는 것 방지
        page.wait_for_function(
            "() => [...document.images].every((i) => i.complete)", timeout=30_000
        )
        png = page.screenshot(clip=clip)
        return {
            "errors": errors,
            "duration": duration,
            "nat": (meta or {}).get("nat"),
            "still": still,
            "fixture_channel": ("query" if isinstance(meta, dict)
                                and meta.get("fixture") == fixture else "route"),
            "png": png,
        }
    finally:
        ctx.close()


# ---------------------------------------------------------------- 1층+3층: 모듈 검증

def _verify_module_in_env(
    browser, srv: StaticServer, mod: dict, *,
    runs: int, fixtures: tuple[str, ...], cfg: QAConfig, update_golden: bool,
) -> dict:
    result: dict = {
        "module": mod["id"], "dir": mod["dir"],
        "stage": mod["stage"], "runs": runs,
        "fixtures": {}, "passed": True, "max_diff_ratio": 0.0,
    }
    golden_path = mod["mod_dir"] / "fixtures" / "snapshots" / GOLDEN_NAME
    for fx in fixtures:
        sessions = [_render_once(browser, srv, mod, fx, cfg) for _ in range(runs)]
        fr: dict = {"errors": [], "passed": True}
        bad = [s["error"] for s in sessions if s.get("error")]
        errs = [e for s in sessions for e in s.get("errors", [])]
        if bad or errs:
            fr.update({"passed": False, "errors": bad + errs})
            result["fixtures"][fx] = fr
            result["passed"] = False
            continue
        base = sessions[0]
        # 세션 간 스틸 perceptual diff — 기존 frame_match 임계 재사용
        diffs = [pixel_diff_ratio(base["png"], s["png"], cfg.frame_diff_channel_tol)
                 for s in sessions[1:]]
        session_max = max(diffs) if diffs else 0.0
        # 스케줄 시각 결정성 — schedule(data) 파생 still/nat 과 duration 이 세션 간 동일
        sched_ok = all(
            abs(s["still"] - base["still"]) < 1e-9
            and s["nat"] == base["nat"]
            and abs(s["duration"] - base["duration"]) < 1e-9
            for s in sessions[1:]
        )
        fr.update({
            "session_max_diff_ratio": session_max,
            "schedule_deterministic": sched_ok,
            "still": base["still"], "nat": base["nat"], "duration": base["duration"],
            "fixture_channel": base["fixture_channel"],
        })
        if session_max > cfg.frame_match_max_ratio or not sched_ok:
            fr["passed"] = False
        result["max_diff_ratio"] = max(result["max_diff_ratio"], session_max)

        # 골든 대비 (typical 만 골든 보유)
        if fx == "typical":
            if update_golden:
                prev = golden_path.read_bytes() if golden_path.is_file() else None
                if prev is not None:
                    from PIL import Image

                    fr["golden_prev_diff_ratio"] = pixel_diff_ratio(
                        prev, base["png"], cfg.frame_diff_channel_tol
                    )
                    fr["golden_prev_size"] = list(Image.open(io.BytesIO(prev)).size)
                golden_path.parent.mkdir(parents=True, exist_ok=True)
                golden_path.write_bytes(base["png"])
                fr["golden_updated"] = True
                fr["golden_diff_ratio"] = 0.0
            elif golden_path.is_file():
                gd = pixel_diff_ratio(
                    golden_path.read_bytes(), base["png"], cfg.frame_diff_channel_tol
                )
                fr["golden_diff_ratio"] = gd
                result["max_diff_ratio"] = max(result["max_diff_ratio"], gd)
                if gd > cfg.frame_match_max_ratio:
                    fr["passed"] = False
                    fr["errors"].append(
                        f"골든 스냅샷 diff {gd:.6f} > {cfg.frame_match_max_ratio}"
                    )
            else:
                fr["passed"] = False
                fr["errors"].append(f"골든 스냅샷 없음: {golden_path}")
        result["fixtures"][fx] = fr
        if not fr["passed"]:
            result["passed"] = False
    return result


def verify_template(
    module_id: str, *,
    runs: int = 2,
    fixtures: tuple[str, ...] = FIXTURES,
    cfg: QAConfig | None = None,
    modules_root: Path | None = None,
    update_golden: bool = False,
) -> dict:
    """모듈 하나의 재현력 검증 — 픽스처별 독립 세션 runs 회 렌더 + 골든 대비 diff."""
    cfg = cfg or QAConfig()
    mod = _find_module(module_id, modules_root)
    with _repro_env() as (browser, srv):
        return _verify_module_in_env(
            browser, srv, mod, runs=runs, fixtures=fixtures,
            cfg=cfg, update_golden=update_golden,
        )


def verify_all(
    modules_root: Path | None = None, *,
    runs: int = 2,
    fixtures: tuple[str, ...] = FIXTURES,
    fixtures_by_module: dict[str, tuple[str, ...]] | None = None,
    cfg: QAConfig | None = None,
    update_golden: bool = False,
    progress: Callable[[str], None] | None = None,
) -> dict:
    """레지스트리 전 scene-template 모듈 일괄 검증 + 요약 표.

    fixtures_by_module 로 모듈별 픽스처 계층화(대표 전체/나머지 typical)를 지정할 수 있다.
    """
    cfg = cfg or QAConfig()
    mods = template_modules(modules_root)
    results: list[dict] = []
    with _repro_env() as (browser, srv):
        for mod in mods:
            fx = (fixtures_by_module or {}).get(mod["id"], fixtures)
            if not fx:  # 계층화에서 명시적으로 비운 모듈은 검증 자체를 생략
                continue
            r = _verify_module_in_env(
                browser, srv, mod, runs=runs, fixtures=fx,
                cfg=cfg, update_golden=update_golden,
            )
            results.append(r)
            if progress:
                progress(
                    f"{mod['id']}: {'PASS' if r['passed'] else 'FAIL'} "
                    f"max_diff={r['max_diff_ratio']:.6f}"
                )
    summary = [
        {
            "module": r["module"], "passed": r["passed"],
            "max_diff_ratio": r["max_diff_ratio"],
            "golden_diff_ratio": r["fixtures"].get("typical", {}).get("golden_diff_ratio"),
        }
        for r in results
    ]
    return {
        "kind": "repro-templates",
        "checked_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "runs": runs,
        "config": {
            "frame_match_max_ratio": cfg.frame_match_max_ratio,
            "frame_diff_channel_tol": cfg.frame_diff_channel_tol,
        },
        "modules": len(results),
        "passed": all(r["passed"] for r in results),
        "summary": summary,
        "results": results,
    }


# ---------------------------------------------------------------- 2층: 빌드 간

_BUILD_FILES = ("scene-data.json", "scenes.jsx", "index.html")


def verify_build(build_dir: Path) -> dict:
    """같은 scenario(scene-data.json)로 build 를 2회 돌려 산출 파일 바이트 동일성을 검사한다."""
    from wdcore.models.scenario import ScenarioDoc
    from wdpipeline.build import build_render_package

    build_dir = Path(build_dir)
    sd = build_dir / "scene-data.json"
    if not sd.is_file():
        return {"build_dir": str(build_dir), "passed": False,
                "error": f"scene-data.json 없음: {sd}"}
    doc = ScenarioDoc.model_validate(json.loads(sd.read_text(encoding="utf-8")))

    hashes: list[dict[str, str]] = []
    for _ in range(2):
        with tempfile.TemporaryDirectory(prefix="wda_repro_build_") as td:
            out = Path(td) / "pkg"
            build_render_package(doc, out)
            hashes.append({
                f: hashlib.sha256((out / f).read_bytes()).hexdigest()
                for f in _BUILD_FILES
            })
    files = {
        f: {"sha_a": hashes[0][f][:16], "sha_b": hashes[1][f][:16],
            "identical": hashes[0][f] == hashes[1][f]}
        for f in _BUILD_FILES
    }
    # 정보성 — 기존 빌드 산출물과의 일치 여부 (구코드 빌드면 다를 수 있어 판정에는 미포함)
    matches_original = {
        f: (build_dir / f).is_file()
        and hashlib.sha256((build_dir / f).read_bytes()).hexdigest() == hashes[0][f]
        for f in _BUILD_FILES
    }
    return {
        "build_dir": str(build_dir),
        "files": files,
        "matches_original": matches_original,
        "passed": all(v["identical"] for v in files.values()),
    }


# ---------------------------------------------------------------- module.yaml 기록

_REPRO_BLOCK_RE = re.compile(r"^  reproducibility:\n(?:^    .*\n?)*", re.MULTILINE)


def record_quality(mod_dir: Path, result: dict, checked_at: str | None = None) -> None:
    """module.yaml 의 quality.reproducibility 에 최근 결과(판정·max_diff_ratio·일시)를 기록한다.

    주석·순서 보존을 위해 YAML 재직렬화 대신 서지컬 텍스트 편집만 한다.
    """
    path = Path(mod_dir) / "module.yaml"
    text = path.read_text(encoding="utf-8")
    checked_at = checked_at or datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    block = (
        "  reproducibility:\n"
        f"    verdict: {'pass' if result['passed'] else 'fail'}\n"
        f"    max_diff_ratio: {result['max_diff_ratio']:.8f}\n"
        f"    checked_at: \"{checked_at}\"\n"
    )
    if _REPRO_BLOCK_RE.search(text):
        text = _REPRO_BLOCK_RE.sub(block, text, count=1)
    elif re.search(r"^quality:[ \t]*$", text, re.MULTILINE):
        text = re.sub(r"^quality:[ \t]*\n", "quality:\n" + block, text,
                      count=1, flags=re.MULTILINE)
    else:
        if not text.endswith("\n"):
            text += "\n"
        text += "quality:\n" + block
    path.write_text(text, encoding="utf-8")
