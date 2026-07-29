# 테마 4종 실렌더 검증 — 기존 템플릿 3종(process·proof·closing) 프리뷰에 OM_THEME 를 주입해 스냅샷·콘솔 에러 0·테마 간 실제 차이를 실측
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "web" / "tokens"
PREVIEW_OUT = TOKENS / "_previews"

STAGE_W, STAGE_H = 1920, 1080
THEMES = ["neutral-slate", "warm-amber", "deep-dark", "fresh-teal"]
TEMPLATES = {"process": "tpl.process", "proof": "tpl.proof", "closing": "tpl.closing"}
CASES = [(t, n) for t in THEMES for n in TEMPLATES]

# 다양성 실측 두 축 — (1) 넓은 면의 색조 분리, (2) 강조색 정체성 분리.
# 넓은 평면에서는 채널 차 6 도 색조로 읽히므로 면 분리는 낮은 임계로, 대신 커버리지를 크게 요구한다.
FIELD_TOL = 6
MIN_FIELD_DIFF_RATIO = 0.50    # 화면의 절반 이상이 다른 색으로 칠해져야 '다른 테마'다
ACCENT_MIN_DISTANCE = 60.0     # 강조색(palette.blue) RGB 유클리드 거리
BLOCK_TOL = 24                 # 참고 수치 — 확실히 다른 픽셀(도형·텍스트 색 교체) 비율

# 프리뷰가 하드코딩한 hwax-blue 대신 주입 테마를 쓰게 하는 훅.
# loader.jsx 가 `window.OMX = window.OMX || {}` 로 기존 객체를 재사용하므로,
# themes 프로퍼티에 세터를 걸어 두면 노출 시점에 loadUrl 을 fromGlobal(OM_THEME) 로 감쌀 수 있다.
_INJECT_JS = """
(() => {
  window.OM_THEME = __THEME_JSON__;
  window.OMX = window.OMX || {};
  let held = null;
  Object.defineProperty(window.OMX, 'themes', {
    configurable: true,
    enumerable: true,
    get() { return held; },
    set(v) {
      const origLoadUrl = v.loadUrl;
      v.loadUrl = function (url) { return v.fromGlobal() || origLoadUrl.call(v, url); };
      held = v;
    },
  });
})();
"""

_LAYER_JS = """
(svgSel) => {
  const svg = document.querySelector(svgSel);
  const layer = svg && svg.querySelector('[data-om-scene-layer="0"]');
  if (!layer) return { ok: false, reason: 'no-layer' };
  const text = (layer.textContent || '').trim();
  return { ok: layer.querySelectorAll('*').length > 0 && !text.startsWith('unmapped scene:'),
           nodes: layer.querySelectorAll('*').length, snippet: text.slice(0, 60) };
}
"""

# 실제 소비된 테마가 주입본인지 확인 — 프레임 배경·킥커 색을 DOM 에서 되읽는다
_THEME_JS = """
(svgSel) => {
  const svg = document.querySelector(svgSel);
  const fo = svg && svg.querySelector('foreignObject');
  if (!fo) return null;
  const root = fo.firstElementChild;
  const cs = root ? getComputedStyle(root) : null;
  return { id: (window.OMX.themes.fromGlobal() || {}).id || null,
           rootBg: cs ? cs.backgroundColor : null };
}
"""


def _diff_ratio(png_a: bytes, png_b: bytes, tol: int) -> float:
    from PIL import Image, ImageChops

    a = Image.open(io.BytesIO(png_a)).convert("RGB")
    b = Image.open(io.BytesIO(png_b)).convert("RGB")
    if a.size != b.size:
        return 1.0
    r, g, bl = ImageChops.difference(a, b).split()
    m = ImageChops.lighter(ImageChops.lighter(r, g), bl)
    changed = sum(m.histogram()[tol + 1:])
    return changed / (a.size[0] * a.size[1])


def _mean_rgb(png: bytes) -> tuple[int, int, int]:
    from PIL import Image, ImageStat

    stat = ImageStat.Stat(Image.open(io.BytesIO(png)).convert("RGB"))
    return tuple(round(v) for v in stat.mean)


def render_all() -> dict:
    """4 테마 × 3 템플릿 프리뷰를 원척으로 실렌더하고 스냅샷·측정치를 모은다."""
    from playwright.sync_api import sync_playwright
    from wdrender.page_session import EXPORTABLE_SVG, vendor_resources
    from wdrender.server import StaticServer

    export_css = (
        "[data-omelette-chrome]{display:none !important;}\n"
        f"{EXPORTABLE_SVG}{{transform:none !important; box-shadow:none !important;}}"
    )
    theme_json = {
        t: json.dumps((TOKENS / f"{t}.json").read_text(encoding="utf-8")) for t in THEMES
    }
    out: dict = {}
    with StaticServer(ROOT) as srv, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for theme_id, name in CASES:
            page = browser.new_page(viewport={"width": STAGE_W + 60, "height": STAGE_H + 60})
            errors: list[str] = []
            page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.add_init_script(
                f"window.__resources = {json.dumps(vendor_resources('/web/vendor'))};"
            )
            page.add_init_script(_INJECT_JS.replace("__THEME_JSON__", theme_json[theme_id]))
            page.goto(srv.url_for(f"modules/scene-templates/{name}/preview.html"),
                      wait_until="load", timeout=60_000)
            page.wait_for_selector(EXPORTABLE_SVG, state="attached", timeout=60_000)
            page.evaluate("() => document.fonts.ready.then(() => true)")
            page.wait_for_selector(
                f'{EXPORTABLE_SVG}[data-om-fonts-inlined="true"]', state="attached", timeout=60_000
            )
            page.add_style_tag(content=export_css)

            svg = page.query_selector(EXPORTABLE_SVG)
            duration = float(svg.get_attribute("data-om-exportable-video-with-duration-secs"))
            box = svg.bounding_box()
            clip = {"x": round(box["x"]), "y": round(box["y"]), "width": STAGE_W, "height": STAGE_H}
            meta = page.evaluate("() => window.__OMX_PREVIEW__ || null")
            still = float(meta["still"]) if meta and meta.get("still") else duration * 0.9
            page.eval_on_selector(
                EXPORTABLE_SVG,
                "(el, t) => { el.dispatchEvent(new CustomEvent("
                "'data-om-seek-to-time-frame', {detail: {time: t, sync: true}})); }",
                still,
            )
            layer = page.evaluate(_LAYER_JS, EXPORTABLE_SVG)
            applied = page.evaluate(_THEME_JS, EXPORTABLE_SVG)
            snap = page.screenshot(clip=clip)

            dest = PREVIEW_OUT / theme_id / f"{name}.png"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(snap)

            out[f"{theme_id}:{name}"] = {
                "errors": errors, "duration": duration, "still": still, "meta": meta,
                "box": {"w": box["width"], "h": box["height"]},
                "layer": layer, "applied": applied, "png": snap,
                "mean": _mean_rgb(snap), "path": dest,
            }
            page.close()
        browser.close()
    return out


@pytest.fixture(scope="module")
def rendered() -> dict:
    return render_all()


@pytest.mark.parametrize("theme_id,name", CASES)
def test_no_console_errors(rendered, theme_id, name):
    r = rendered[f"{theme_id}:{name}"]
    assert r["errors"] == [], f"{theme_id}/{name}: 콘솔·페이지 오류 — {r['errors']}"


@pytest.mark.parametrize("theme_id,name", CASES)
def test_stage_mounted_at_full_scale(rendered, theme_id, name):
    r = rendered[f"{theme_id}:{name}"]
    assert abs(r["box"]["w"] - STAGE_W) <= 1 and abs(r["box"]["h"] - STAGE_H) <= 1, r["box"]
    assert r["meta"] and r["meta"]["tpl"] == TEMPLATES[name]
    assert r["duration"] > 0


@pytest.mark.parametrize("theme_id,name", CASES)
def test_scene_dom_rendered(rendered, theme_id, name):
    layer = rendered[f"{theme_id}:{name}"]["layer"]
    assert layer["ok"], f"{theme_id}/{name}: 씬 레이어 비정상 — {layer}"
    assert layer["nodes"] >= 10, f"{theme_id}/{name}: 씬 DOM 노드 {layer['nodes']}개뿐"


@pytest.mark.parametrize("theme_id,name", CASES)
def test_injected_theme_is_the_one_consumed(rendered, theme_id, name):
    """OM_THEME 주입이 실제로 소비됐는지 — 로더가 돌려준 id 를 페이지에서 되읽는다."""
    applied = rendered[f"{theme_id}:{name}"]["applied"]
    assert applied and applied["id"] == theme_id, (
        f"{theme_id}/{name}: 소비된 테마가 {applied} — 주입이 먹지 않았다"
    )


@pytest.mark.parametrize("theme_id,name", CASES)
def test_snapshot_written(rendered, theme_id, name):
    p = rendered[f"{theme_id}:{name}"]["path"]
    assert p.exists() and p.stat().st_size > 10_000, f"{p} 스냅샷이 비었다"


@pytest.mark.parametrize("name", TEMPLATES)
def test_themes_paint_different_fields(rendered, name):
    """4종이 실제로 달라 보이는가 (면) — 같은 템플릿·다른 테마 조합 전수 픽셀 차."""
    bad = []
    for i, a in enumerate(THEMES):
        for b in THEMES[i + 1:]:
            ratio = _diff_ratio(rendered[f"{a}:{name}"]["png"], rendered[f"{b}:{name}"]["png"],
                                FIELD_TOL)
            if ratio < MIN_FIELD_DIFF_RATIO:
                bad.append((a, b, round(ratio, 4)))
    assert not bad, f"{name}: 화면 면적의 색조 분리가 부족하다 — {bad}"


def test_accent_colors_are_far_apart():
    """강조색이 서로 멀어야 '같은 시리즈' 인상을 벗어난다 — 기준 테마까지 포함해 전수."""
    ids = ["hwax-blue"] + THEMES
    accents = {
        t: tuple(int(json.loads((TOKENS / f"{t}.json").read_text(encoding="utf-8"))
                     ["raw"]["palette"]["blue"].lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
        for t in ids
    }
    bad = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            d = sum((x - y) ** 2 for x, y in zip(accents[a], accents[b])) ** 0.5
            if d < ACCENT_MIN_DISTANCE:
                bad.append((a, b, round(d, 1)))
    assert not bad, f"강조색이 너무 가깝다 — {bad}"


def test_dark_theme_reads_dark_in_pixels(rendered):
    """deep-dark 스냅샷의 평균 휘도가 밝은 3종보다 확연히 낮아야 한다."""
    for name in TEMPLATES:
        dark = sum(rendered[f"deep-dark:{name}"]["mean"]) / 3
        lights = [sum(rendered[f"{t}:{name}"]["mean"]) / 3
                  for t in THEMES if t != "deep-dark"]
        assert dark < 80, f"{name}: deep-dark 평균 밝기 {dark:.1f} — 다크로 보이지 않는다"
        assert dark < min(lights) - 100, (
            f"{name}: deep-dark({dark:.1f}) 가 밝은 테마들({[round(v) for v in lights]}) 과 충분히 벌어지지 않았다"
        )


if __name__ == "__main__":
    res = render_all()
    for key, r in res.items():
        print(f"{key:28s} mean={r['mean']} errors={len(r['errors'])} "
              f"nodes={r['layer']['nodes']} still={r['still']:.2f} -> {r['path'].name}")
    print()
    for name in TEMPLATES:
        for i, a in enumerate(THEMES):
            for b in THEMES[i + 1:]:
                field = _diff_ratio(res[f"{a}:{name}"]["png"], res[f"{b}:{name}"]["png"], FIELD_TOL)
                block = _diff_ratio(res[f"{a}:{name}"]["png"], res[f"{b}:{name}"]["png"], BLOCK_TOL)
                print(f"{name:8s} {a:14s} vs {b:14s} "
                      f"field(tol{FIELD_TOL})={field * 100:6.2f}%  block(tol{BLOCK_TOL})={block * 100:6.2f}%")
