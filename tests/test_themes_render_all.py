# 템플릿 전수 × 테마 전수 실렌더 — 역동 리포팅의 전제(테마별 대응)를 실측으로 지킨다
#
# 왜 따로 두는가 — tests/test_themes_render.py 는 테마 **다양성**(면 분리·강조색 거리)을
# 템플릿 3종으로 깊게 본다. 여기는 반대로 **넓게** 본다: 40종이 5테마에서 모두
# 콘솔 에러 없이 원척으로 서는가. 200 조합 중 15 만 보고 있었다(2026-11-01 실측).
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "web" / "tokens"

# 초기 7+3 종은 module.yaml 에 stage 선언이 없다 — 가로 1920×1080 이 암묵 기본이었다.
DEFAULT_STAGE = (1920, 1080)


def _templates() -> list[dict]:
    reg = yaml.safe_load((ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    out = []
    for m in reg["modules"]:
        if m["type"] != "scene-template":
            continue
        stage = m.get("stage")
        if not stage:
            doc = yaml.safe_load((ROOT / m["path"] / "module.yaml").read_text(encoding="utf-8"))
            stage = doc.get("stage")
        w, h = (stage["w"], stage["h"]) if stage else DEFAULT_STAGE
        out.append({"id": m["id"], "dir": Path(m["path"]).name, "w": w, "h": h})
    return out


def _theme_ids() -> list[str]:
    reg = yaml.safe_load((ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    return [m["id"].split(".", 1)[1] for m in reg["modules"] if m["type"] == "theme"]


TEMPLATES = _templates()
THEMES = _theme_ids()
CASES = [(t["id"], th) for t in TEMPLATES for th in THEMES]


@pytest.fixture(scope="module")
def rendered() -> dict:
    """전 조합을 원척으로 렌더해 콘솔 에러·무대 크기·평균색을 모은다."""
    from playwright.sync_api import sync_playwright

    from wdrender.page_session import EXPORTABLE_SVG
    from wdrender.server import StaticServer

    # 프리뷰는 무대를 축소해 보여준다 — 원척으로 재려면 크롬을 숨기고 transform 을 끈다
    # (tests/test_themes_render.py 와 같은 규약). 이걸 빠뜨리면 200 조합이 전부
    # "크기가 다르다" 로 잘못 실패한다(실측).
    export_css = (
        "[data-omelette-chrome]{display:none !important;}\n"
        "%s{transform:none !important; box-shadow:none !important;}"
    )
    by_id = {t["id"]: t for t in TEMPLATES}
    theme_json = {t: json.dumps((TOKENS / f"{t}.json").read_text(encoding="utf-8"))
                  for t in THEMES}
    out: dict = {}
    with StaticServer(ROOT) as srv, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for tpl_id, theme in CASES:
            t = by_id[tpl_id]
            page = browser.new_page(viewport={"width": t["w"] + 60, "height": t["h"] + 60})
            errors: list[str] = []
            page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.add_init_script(
                f"window.OM_THEME = JSON.parse({theme_json[theme]});")
            try:
                page.goto(srv.url_for(f"modules/scene-templates/{t['dir']}/preview.html"),
                          wait_until="networkidle", timeout=60_000)
                page.wait_for_selector(EXPORTABLE_SVG, state="attached", timeout=60_000)
                page.evaluate("() => document.fonts.ready.then(() => true)")
                page.add_style_tag(content=export_css % EXPORTABLE_SVG)
                svg = page.query_selector(EXPORTABLE_SVG)
                box = svg.bounding_box() if svg else None
            except Exception as exc:  # noqa: BLE001 — 실패도 결과로 남긴다
                errors.append(f"render: {type(exc).__name__}: {exc}")
                box = None
            out[f"{theme}:{tpl_id}"] = {"errors": errors, "box": box,
                                        "want": (t["w"], t["h"])}
            page.close()
        browser.close()
    return out


def test_every_combination_was_attempted():
    assert len(CASES) == len(TEMPLATES) * len(THEMES)
    assert len(TEMPLATES) >= 40 and len(THEMES) >= 5, (
        f"커버리지가 줄었다 — 템플릿 {len(TEMPLATES)} · 테마 {len(THEMES)}")


@pytest.mark.parametrize("tpl_id,theme", CASES, ids=[f"{t}-{th}" for t, th in CASES])
def test_no_console_errors(rendered, tpl_id: str, theme: str):
    """어떤 테마에서든 콘솔 에러 0 — 토큰 하나가 없으면 여기서 터진다."""
    r = rendered[f"{theme}:{tpl_id}"]
    assert not r["errors"], f"{tpl_id} @ {theme}: {r['errors'][:2]}"


@pytest.mark.parametrize("tpl_id,theme", CASES, ids=[f"{t}-{th}" for t, th in CASES])
def test_stage_mounted_at_full_scale(rendered, tpl_id: str, theme: str):
    """무대가 원척으로 선다 — 세로 템플릿을 가로 크기로 재면 조용히 어긋난다."""
    r = rendered[f"{theme}:{tpl_id}"]
    assert r["box"] is not None, f"{tpl_id} @ {theme}: 무대를 찾지 못했다"
    w, h = r["want"]
    assert round(r["box"]["width"]) == w and round(r["box"]["height"]) == h, (
        f"{tpl_id} @ {theme}: {round(r['box']['width'])}×{round(r['box']['height'])} ≠ {w}×{h}")
