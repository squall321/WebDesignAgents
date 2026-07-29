# 문서형 템플릿 5종 preview 실렌더 검증 — 3무대(16:9·4:3·A4) svg 마운트·콘솔 에러 0·씬 DOM·최소 폰트 24px·오버플로 0·frame-match 실측
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"

# 문서형 3무대 (module.yaml stages 와 같은 값 — 템플릿 쪽 자기 검증용 상수)
STAGES = {"16x9": (1920, 1080), "4x3": (1440, 1080), "a4": (1240, 1754)}
GOLDEN_STAGE = "16x9"
MIN_FONT_PX = 24.0          # wdqa QAConfig.min_font_px
SAFE_MARGIN_X = 72.0        # 좌우 여백 84px 에서 글리프 좌우 베어링 여유 12px
SAFE_MARGIN_Y = 36.0        # 위 48 / 아래 40 여백에서 글리프 상하 베어링 여유 4px
FPS = 24
FRAME_DIFF_CHANNEL_TOL = 8
FRAME_MATCH_MAX_RATIO = 0.02
FIT_TOL = 2.0

DOC = ["doc-cover", "doc-toc", "doc-section", "doc-body", "doc-summary"]
EXTRA_FIXTURES = {"doc-body": ["chart", "image"]}
# 16:9 는 전 픽스처, 좁고 낮은 두 무대는 대표·상한·상한포화(cap)만 — cap 은 스키마 maxLength 를
# 정확히 채운 합성 최악 구성이다(역산이 맞는지의 최종 증명).
CASES = [
    (mod, fx, stage)
    for mod in DOC
    for fx, stage in (
        [(f, "16x9") for f in ["min", "typical", "max"] + EXTRA_FIXTURES.get(mod, [])]
        + [(f, s) for s in ("4x3", "a4") for f in ("typical", "max", "cap")]
    )
]
FILL = "정보밀도점검문자열가나다라마바사아자차카타파하"

_SCAN_JS = """
(args) => {
  const [svgSel, opacityMin] = args;
  const svg = document.querySelector(svgSel);
  if (!svg) return { error: 'no-svg' };
  const fo = svg.querySelector('foreignObject');
  if (!fo) return { error: 'no-foreignobject' };
  const stageRect = svg.getBoundingClientRect();
  const items = [];
  const fits = [];
  for (const el of fo.querySelectorAll('*')) {
    if (!(el instanceof HTMLElement)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const rect = el.getBoundingClientRect();
    if (el.hasAttribute('data-doc-fit') || el.hasAttribute('data-doc-col')) {
      fits.push({ key: el.getAttribute('data-doc-fit') || ('col:' + el.getAttribute('data-doc-col')),
                  scrollH: el.scrollHeight, clientH: el.clientHeight,
                  scrollW: el.scrollWidth, clientW: el.clientWidth,
                  top: rect.y - stageRect.y, bottom: rect.bottom - stageRect.y });
    }
    if (rect.width === 0 && rect.height === 0) continue;
    let direct = '';
    let textRect = null;
    for (const n of el.childNodes) {
      if (n.nodeType !== 3) continue;
      direct += n.textContent;
      if (n.textContent.trim()) {
        const rg = document.createRange();
        rg.selectNodeContents(n);
        const rr = rg.getBoundingClientRect();
        if (rr.width > 0 || rr.height > 0) {
          textRect = textRect === null
            ? { l: rr.left, t: rr.top, r: rr.right, b: rr.bottom }
            : { l: Math.min(textRect.l, rr.left), t: Math.min(textRect.t, rr.top),
                r: Math.max(textRect.r, rr.right), b: Math.max(textRect.b, rr.bottom) };
        }
      }
    }
    direct = direct.replace(/\\s+/g, ' ').trim();
    let op = 1, clipOk = false;
    let node = el;
    while (node && node instanceof HTMLElement) {
      const ncs = node === el ? cs : getComputedStyle(node);
      op *= parseFloat(ncs.opacity || '1');
      if (node.hasAttribute('data-qa-clip-ok')) clipOk = true;
      if (node.parentElement === null || node.parentNode === fo) break;
      node = node.parentElement;
    }
    if (op < opacityMin) continue;
    items.push({
      tag: el.tagName.toLowerCase(),
      text: direct.slice(0, 40),
      hasText: direct.length > 0,
      fontSize: parseFloat(cs.fontSize),
      opacity: op, clipOk,
      scrollW: el.scrollWidth, scrollH: el.scrollHeight,
      clientW: el.clientWidth, clientH: el.clientHeight,
      rect: { x: rect.x - stageRect.x, y: rect.y - stageRect.y, w: rect.width, h: rect.height },
      textRect: textRect === null ? null
        : { x: textRect.l - stageRect.x, y: textRect.t - stageRect.y,
            w: textRect.r - textRect.l, h: textRect.b - textRect.t },
    });
  }
  return { stage: { w: stageRect.width, h: stageRect.height }, items, fits };
}
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


def _pixel_diff_ratio(png_a: bytes, png_b: bytes, tol: int) -> float:
    from PIL import Image, ImageChops

    a = Image.open(io.BytesIO(png_a)).convert("RGB")
    b = Image.open(io.BytesIO(png_b)).convert("RGB")
    if a.size != b.size:
        return 1.0
    diff = ImageChops.difference(a, b)
    r, g, bl = diff.split()
    m = ImageChops.lighter(ImageChops.lighter(r, g), bl)
    changed = sum(m.histogram()[tol + 1:])
    total = a.size[0] * a.size[1]
    return changed / total if total else 1.0


def pad_to_caps(schema: dict, data):
    """스키마 maxLength 를 정확히 채운 데이터 사본 — 자수 상한 역산의 최악 구성."""
    if not isinstance(schema, dict):
        return data
    t = schema.get("type")
    if t == "string" and isinstance(data, str):
        ml = schema.get("maxLength")
        if not ml or len(data) >= ml:
            return data
        need = ml - len(data)
        return data + (FILL * (need // len(FILL) + 1))[:need]
    if t == "object" and isinstance(data, dict):
        props = schema.get("properties") or {}
        return {k: (pad_to_caps(props[k], v) if k in props else v) for k, v in data.items()}
    if t == "array" and isinstance(data, list):
        items = schema.get("items")
        return [pad_to_caps(items, v) for v in data] if isinstance(items, dict) else data
    return data


def _fulfill_json(body: bytes):
    """라우트 핸들러 — 인자 1개여야 playwright 가 request 를 끼워 넣지 않는다."""

    def handler(route) -> None:
        route.fulfill(status=200, content_type="application/json", body=body)

    return handler


def measure() -> dict:
    """5종 preview × (픽스처, 무대)를 원척으로 실렌더하고 측정치를 모은다. 키는 "{모듈}:{픽스처}:{무대}"."""
    from playwright.sync_api import sync_playwright
    from wdrender.page_session import EXPORTABLE_SVG, vendor_resources
    from wdrender.server import StaticServer

    export_css = (
        "[data-omelette-chrome]{display:none !important;}\n"
        f"{EXPORTABLE_SVG}{{transform:none !important; box-shadow:none !important;}}"
    )
    out: dict = {}
    with StaticServer(ROOT) as srv, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for mod, fixture, stage_key in CASES:
            w, h = STAGES[stage_key]
            page = browser.new_page(viewport={"width": w + 60, "height": h + 60})
            errors: list[str] = []
            page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.add_init_script(
                f"window.__resources = {json.dumps(vendor_resources('/web/vendor'))};"
            )
            query = fixture
            if fixture == "cap":  # max 요청을 상한 포화 데이터로 가로채 응답한다 (프리뷰 무수정)
                schema = json.loads((TPL_DIR / mod / "schema.json").read_text(encoding="utf-8"))
                base = json.loads((TPL_DIR / mod / "fixtures" / "max.json").read_text(encoding="utf-8"))
                body = json.dumps(pad_to_caps(schema, base), ensure_ascii=False).encode("utf-8")
                page.route(f"**/scene-templates/{mod}/fixtures/*.json", _fulfill_json(body))
                query = "max"
            rel = f"modules/scene-templates/{mod}/preview.html"
            page.goto(f"{srv.url_for(rel)}?fixture={query}&stage={stage_key}",
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
            clip = {"x": round(box["x"]), "y": round(box["y"]), "width": w, "height": h}
            meta = page.evaluate("() => window.__OMX_PREVIEW__ || null")

            def seek(t: float) -> None:
                page.eval_on_selector(
                    EXPORTABLE_SVG,
                    "(el, t) => { el.dispatchEvent(new CustomEvent("
                    "'data-om-seek-to-time-frame', {detail: {time: t, sync: true}})); }",
                    t,
                )

            still = float(meta["still"]) if meta and meta.get("still") else duration * 0.9
            seek(still)
            page.wait_for_function("() => [...document.images].every((i) => i.complete)", timeout=30_000)
            layer = page.evaluate(_LAYER_JS, EXPORTABLE_SVG)
            scan = page.evaluate(_SCAN_JS, [EXPORTABLE_SVG, 0.1])

            head_diff = tail_diff = 0.0
            if fixture == "typical" and stage_key == GOLDEN_STAGE:  # 모션은 데이터·무대 무관
                step = 1.0 / FPS
                seek(0.0)
                head_a = page.screenshot(clip=clip)
                seek(step)
                head_b = page.screenshot(clip=clip)
                seek(duration - 2 * step)
                tail_a = page.screenshot(clip=clip)
                seek(duration - step)
                tail_b = page.screenshot(clip=clip)
                head_diff = _pixel_diff_ratio(head_a, head_b, FRAME_DIFF_CHANNEL_TOL)
                tail_diff = _pixel_diff_ratio(tail_a, tail_b, FRAME_DIFF_CHANNEL_TOL)

            out[f"{mod}:{fixture}:{stage_key}"] = {
                "errors": errors, "duration": duration, "still": still, "meta": meta,
                "stage_wh": (w, h), "box": {"w": box["width"], "h": box["height"]},
                "layer": layer, "scan": scan,
                "head_diff": head_diff, "tail_diff": tail_diff,
            }
            page.close()
        browser.close()
    return out


@pytest.fixture(scope="module")
def rendered() -> dict:
    return measure()


@pytest.mark.parametrize("mod,fixture,stage", CASES)
def test_stage_is_native_size(rendered, mod, fixture, stage):
    r = rendered[f"{mod}:{fixture}:{stage}"]
    w, h = STAGES[stage]
    assert abs(r["box"]["w"] - w) <= 1 and abs(r["box"]["h"] - h) <= 1, (
        f"{mod}/{fixture}@{stage}: 무대 원척이 {w}x{h} 가 아니다 — {r['box']}"
    )
    assert r["meta"]["stage"] == {"w": w, "h": h}
    assert r["meta"]["format"] in ("deck-doc-16x9", "deck-4x3", "print-a4")
    assert r["duration"] > 0


@pytest.mark.parametrize("mod,fixture,stage", CASES)
def test_no_console_errors(rendered, mod, fixture, stage):
    r = rendered[f"{mod}:{fixture}:{stage}"]
    assert r["errors"] == [], f"{mod}/{fixture}@{stage}: 콘솔/페이지 오류 — {r['errors']}"


@pytest.mark.parametrize("mod,fixture,stage", CASES)
def test_scene_dom_exists(rendered, mod, fixture, stage):
    layer = rendered[f"{mod}:{fixture}:{stage}"]["layer"]
    assert layer["ok"], f"{mod}/{fixture}@{stage}: 씬 레이어 비정상 — {layer}"
    assert layer["nodes"] >= 8, f"{mod}/{fixture}@{stage}: 씬 DOM 노드가 {layer['nodes']}개뿐"


@pytest.mark.parametrize("mod,fixture,stage", CASES)
def test_min_font_24px(rendered, mod, fixture, stage):
    scan = rendered[f"{mod}:{fixture}:{stage}"]["scan"]
    assert "error" not in scan, scan
    bad = [(it["text"][:20], it["fontSize"]) for it in scan["items"]
           if it["hasText"] and it["fontSize"] + 1e-6 < MIN_FONT_PX]
    assert not bad, f"{mod}/{fixture}@{stage}: 최소 폰트 {MIN_FONT_PX:.0f}px 미만 — {bad}"


@pytest.mark.parametrize("mod,fixture,stage", CASES)
def test_no_text_overflow(rendered, mod, fixture, stage):
    """텍스트가 컨테이너를 넘치지 않는다 (maxLength 실측 역산의 사후 검증)."""
    scan = rendered[f"{mod}:{fixture}:{stage}"]["scan"]
    bad = []
    for it in scan["items"]:
        if not it["hasText"] or it["clipOk"]:
            continue
        if it["clientW"] <= 0 and it["clientH"] <= 0:
            continue
        if it["scrollW"] - it["clientW"] > FIT_TOL or it["scrollH"] - it["clientH"] > FIT_TOL:
            bad.append((it["text"][:20], it["scrollW"], it["clientW"], it["scrollH"], it["clientH"]))
    assert not bad, f"{mod}/{fixture}@{stage}: 텍스트 오버플로 — {bad}"


@pytest.mark.parametrize("mod,fixture,stage", CASES)
def test_nothing_leaves_the_stage(rendered, mod, fixture, stage):
    r = rendered[f"{mod}:{fixture}:{stage}"]
    w, h = r["stage_wh"]
    bad = []
    for it in r["scan"]["items"]:
        if it["clipOk"]:
            continue
        g = it["textRect"] if it["hasText"] and it["textRect"] else it["rect"]
        if (g["x"] < -FIT_TOL or g["y"] < -FIT_TOL
                or g["x"] + g["w"] > w + FIT_TOL or g["y"] + g["h"] > h + FIT_TOL):
            bad.append((it["text"][:20] or it["tag"], round(g["x"]), round(g["y"]),
                        round(g["x"] + g["w"]), round(g["y"] + g["h"])))
    assert not bad, f"{mod}/{fixture}@{stage}: 무대 {w}x{h} 이탈 — {bad}"


@pytest.mark.parametrize("mod,fixture,stage", CASES)
def test_safe_margin(rendered, mod, fixture, stage):
    r = rendered[f"{mod}:{fixture}:{stage}"]
    w, h = r["stage_wh"]
    bad = []
    for it in r["scan"]["items"]:
        if not it["hasText"] or it["clipOk"] or not it["textRect"]:
            continue
        g = it["textRect"]
        if (g["x"] < SAFE_MARGIN_X - 0.5 or g["y"] < SAFE_MARGIN_Y - 0.5
                or g["x"] + g["w"] > w - SAFE_MARGIN_X + 0.5
                or g["y"] + g["h"] > h - SAFE_MARGIN_Y + 0.5):
            bad.append((it["text"][:16], round(g["x"]), round(g["y"]),
                        round(g["x"] + g["w"]), round(g["y"] + g["h"])))
    assert not bad, f"{mod}/{fixture}@{stage}: 안전 여백 침범 — {bad}"


@pytest.mark.parametrize("mod,fixture,stage", CASES)
def test_layout_fits_the_page(rendered, mod, fixture, stage):
    """본문 영역·2단 열이 지면 안에서 닫힌다 — 문서형은 스크롤이 없다."""
    fits = {f["key"]: f for f in rendered[f"{mod}:{fixture}:{stage}"]["scan"]["fits"]}
    assert "main" in fits, f"{mod}/{fixture}@{stage}: data-doc-fit=main 이 없다"
    over = [(k, f["scrollW"], f["clientW"], f["scrollH"], f["clientH"]) for k, f in fits.items()
            if f["scrollH"] - f["clientH"] > FIT_TOL or f["scrollW"] - f["clientW"] > FIT_TOL]
    assert not over, f"{mod}/{fixture}@{stage}: 레이아웃 넘침 — {over}"
    main = fits["main"]
    spill = [(k, round(f["bottom"]), round(main["bottom"])) for k, f in fits.items()
             if k.startswith("col:") and f["bottom"] > main["bottom"] + FIT_TOL]
    assert not spill, f"{mod}/{fixture}@{stage}: 열이 본문 영역 아래로 흘렀다 — {spill}"


@pytest.mark.parametrize("mod", DOC)
def test_frame_match(rendered, mod):
    """첫/끝 인접 프레임이 정지 — 문서형은 정지 화면이 최종형이다."""
    r = rendered[f"{mod}:typical:{GOLDEN_STAGE}"]
    assert r["head_diff"] <= FRAME_MATCH_MAX_RATIO, (
        f"{mod}: 첫 프레임 diff {r['head_diff']:.5f} > {FRAME_MATCH_MAX_RATIO}"
    )
    assert r["tail_diff"] <= FRAME_MATCH_MAX_RATIO, (
        f"{mod}: 끝 프레임 diff {r['tail_diff']:.5f} > {FRAME_MATCH_MAX_RATIO}"
    )


@pytest.mark.parametrize("mod", DOC)
def test_still_settles_before_nat(rendered, mod):
    """스케줄 정착 시각(still)이 nat 안에 있고, 그 뒤로는 움직임이 없다."""
    r = rendered[f"{mod}:typical:{GOLDEN_STAGE}"]
    nat = float(r["meta"]["nat"])
    assert 0 < r["still"] <= nat - 0.1, f"{mod}: still {r['still']} vs nat {nat}"


@pytest.mark.parametrize("mod", DOC)
def test_a4_portrait_layout_holds(rendered, mod):
    """A4 세로(1240×1754)에서도 레이아웃이 성립한다 — 가로 전용이 아니다."""
    r = rendered[f"{mod}:max:a4"]
    fits = {f["key"]: f for f in r["scan"]["fits"]}
    assert fits["main"]["clientH"] > 1000, f"{mod}: A4 본문 영역이 {fits['main']['clientH']}px 뿐"
    texts = [it for it in r["scan"]["items"] if it["hasText"]]
    assert len(texts) >= 5, f"{mod}: A4 에서 렌더된 텍스트가 {len(texts)}개뿐"


@pytest.mark.parametrize("mod", DOC)
def test_snapshot_committed(mod):
    from PIL import Image

    p = TPL_DIR / mod / "fixtures" / "snapshots" / "typical.png"
    assert p.exists() and p.stat().st_size > 10_000, f"{mod}: typical.png 스냅샷이 없다"
    assert Image.open(p).size == STAGES[GOLDEN_STAGE], f"{mod}: 골든이 기준 무대 크기가 아니다"
