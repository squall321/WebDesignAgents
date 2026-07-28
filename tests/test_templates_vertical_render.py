# 세로 템플릿 4종 preview 실렌더 검증 — svg 마운트·콘솔 에러 0·씬 DOM 실존·최소 폰트 32px·안전 여백 72px·frame-match 실측
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"

# 세로 포맷 계약 (formats/short-9x16/format.yaml 과 동일 값 — 템플릿 쪽 자기 검증용 상수)
STAGE_W, STAGE_H = 1080, 1920
MIN_FONT_PX = 32.0
SAFE_MARGIN_PX = 72.0
FPS = 24
FRAME_DIFF_CHANNEL_TOL = 8
FRAME_MATCH_MAX_RATIO = 0.02

VERTICAL = ["v-hook", "v-stack", "v-metric", "v-cta"]
# typical 은 대표 구성, max 는 스키마 maxLength 상한 — 상한이 세로 폭/존 안에 드는지가 실측 역산의 증명
FIXTURES = ["typical", "max"]
CASES = [(n, f) for n in VERTICAL for f in FIXTURES]

# 스테이지 내부 요소 실측 — 누적 opacity·computed fontSize·글리프 rect(Range) 수집
_SCAN_JS = """
(args) => {
  const [svgSel, opacityMin] = args;
  const svg = document.querySelector(svgSel);
  if (!svg) return { error: 'no-svg' };
  const fo = svg.querySelector('foreignObject');
  if (!fo) return { error: 'no-foreignobject' };
  const stageRect = svg.getBoundingClientRect();
  const items = [];
  for (const el of fo.querySelectorAll('*')) {
    if (!(el instanceof HTMLElement)) continue;
    const cs = getComputedStyle(el);
    if (cs.display === 'none' || cs.visibility === 'hidden') continue;
    const rect = el.getBoundingClientRect();
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
      text: direct.slice(0, 60),
      hasText: direct.length > 0,
      fontSize: parseFloat(cs.fontSize),
      opacity: op,
      clipOk,
      scrollW: el.scrollWidth, scrollH: el.scrollHeight,
      clientW: el.clientWidth, clientH: el.clientHeight,
      rect: { x: rect.x - stageRect.x, y: rect.y - stageRect.y, w: rect.width, h: rect.height },
      textRect: textRect === null ? null
        : { x: textRect.l - stageRect.x, y: textRect.t - stageRect.y,
            w: textRect.r - textRect.l, h: textRect.b - textRect.t },
    });
  }
  return { stage: { w: stageRect.width, h: stageRect.height }, items };
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

# vtpl.stack 카드 실측 — 정착 시각의 카드 상자(스테이지 좌표)와 내용 넘침 여부
_CARDS_JS = """
(svgSel) => {
  const svg = document.querySelector(svgSel);
  const base = svg.getBoundingClientRect();
  return [...svg.querySelectorAll('[data-v-card]')].map((el) => {
    const b = el.getBoundingClientRect();
    return { i: +el.getAttribute('data-v-card'), y: b.y - base.y, h: b.height,
             scrollH: el.scrollHeight, clientH: el.clientHeight };
  });
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


def measure_previews(write_snapshots: bool = False) -> dict:
    """4종 preview × (typical, max) 를 1080×1920 원척으로 실렌더하고 측정치를 모은다.

    반환 키는 "{모듈}:{픽스처}". write_snapshots=True 면 typical 스냅샷을 갱신한다.
    """
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
        for name, fixture in CASES:
            rel = f"modules/scene-templates/{name}/preview.html"
            page = browser.new_page(viewport={"width": STAGE_W + 60, "height": STAGE_H + 60})
            errors: list[str] = []
            page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.add_init_script(
                f"window.__resources = {json.dumps(vendor_resources('/web/vendor'))};"
            )
            page.goto(f"{srv.url_for(rel)}?fixture={fixture}", wait_until="load", timeout=60_000)
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

            def seek(t: float) -> None:
                page.eval_on_selector(
                    EXPORTABLE_SVG,
                    "(el, t) => { el.dispatchEvent(new CustomEvent("
                    "'data-om-seek-to-time-frame', {detail: {time: t, sync: true}})); }",
                    t,
                )

            still = float(meta["still"]) if meta and meta.get("still") else duration * 0.9
            seek(still)
            layer = page.evaluate(_LAYER_JS, EXPORTABLE_SVG)
            scan = page.evaluate(_SCAN_JS, [EXPORTABLE_SVG, 0.1])
            cards = page.evaluate(_CARDS_JS, EXPORTABLE_SVG)
            snap = page.screenshot(clip=clip)
            if write_snapshots and fixture == "typical":
                (TPL_DIR / name / "fixtures" / "snapshots").mkdir(parents=True, exist_ok=True)
                (TPL_DIR / name / "fixtures" / "snapshots" / "typical.png").write_bytes(snap)

            head_diff = tail_diff = 0.0
            if fixture == "typical":  # frame-match 는 대표 구성 1회로 충분 (모션은 데이터 무관)
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

            out[f"{name}:{fixture}"] = {
                "errors": errors,
                "duration": duration,
                "still": still,
                "meta": meta,
                "box": {"w": box["width"], "h": box["height"]},
                "layer": layer,
                "scan": scan,
                "cards": cards,
                "head_diff": head_diff,
                "tail_diff": tail_diff,
                "snapshot_bytes": len(snap),
            }
            page.close()
        browser.close()
    return out


@pytest.fixture(scope="module")
def rendered() -> dict:
    return measure_previews()


@pytest.mark.parametrize("name,fixture", CASES)
def test_stage_is_vertical_and_mounted(rendered, name, fixture):
    r = rendered[f"{name}:{fixture}"]
    assert abs(r["box"]["w"] - STAGE_W) <= 1 and abs(r["box"]["h"] - STAGE_H) <= 1, (
        f"{name}/{fixture}: 스테이지 원척이 {STAGE_W}x{STAGE_H} 가 아니다 — {r['box']}"
    )
    assert r["meta"] and r["meta"]["format"] == "short-9x16"
    assert r["meta"]["stage"] == {"w": STAGE_W, "h": STAGE_H}
    assert r["meta"]["fixture"] == fixture, "프리뷰가 요청한 픽스처를 바인딩하지 않았다"
    assert r["duration"] > 0


@pytest.mark.parametrize("name,fixture", CASES)
def test_no_console_errors(rendered, name, fixture):
    r = rendered[f"{name}:{fixture}"]
    assert r["errors"] == [], f"{name}/{fixture}: 콘솔/페이지 오류 — {r['errors']}"


@pytest.mark.parametrize("name,fixture", CASES)
def test_scene_dom_exists(rendered, name, fixture):
    layer = rendered[f"{name}:{fixture}"]["layer"]
    assert layer["ok"], f"{name}/{fixture}: 씬 레이어 비정상 — {layer}"
    assert layer["nodes"] >= 10, f"{name}/{fixture}: 씬 DOM 노드가 {layer['nodes']}개뿐"


@pytest.mark.parametrize("name,fixture", CASES)
def test_min_font_32px(rendered, name, fixture):
    scan = rendered[f"{name}:{fixture}"]["scan"]
    assert "error" not in scan, scan
    bad = [
        (it["text"][:20], it["fontSize"])
        for it in scan["items"]
        if it["hasText"] and it["fontSize"] + 1e-6 < MIN_FONT_PX
    ]
    assert not bad, f"{name}/{fixture}: 최소 폰트 {MIN_FONT_PX:.0f}px 미만 텍스트 — {bad}"


@pytest.mark.parametrize("name,fixture", CASES)
def test_safe_margin_72px(rendered, name, fixture):
    scan = rendered[f"{name}:{fixture}"]["scan"]
    bad = []
    for it in scan["items"]:
        if not it["hasText"] or it["clipOk"] or not it["textRect"]:
            continue
        g = it["textRect"]
        if (g["x"] < SAFE_MARGIN_PX - 0.5 or g["y"] < SAFE_MARGIN_PX - 0.5
                or g["x"] + g["w"] > STAGE_W - SAFE_MARGIN_PX + 0.5
                or g["y"] + g["h"] > STAGE_H - SAFE_MARGIN_PX + 0.5):
            bad.append((it["text"][:20], round(g["x"]), round(g["y"]),
                        round(g["x"] + g["w"]), round(g["y"] + g["h"])))
    assert not bad, f"{name}/{fixture}: 안전 여백 {SAFE_MARGIN_PX:.0f}px 침범 — {bad}"


@pytest.mark.parametrize("name,fixture", CASES)
def test_no_text_overflow(rendered, name, fixture):
    """텍스트가 컨테이너를 넘치지 않는다 (maxLength 실측 역산의 사후 검증)."""
    scan = rendered[f"{name}:{fixture}"]["scan"]
    bad = []
    for it in scan["items"]:
        if not it["hasText"] or it["clipOk"]:
            continue
        if it["clientW"] <= 0 and it["clientH"] <= 0:
            continue
        if it["scrollW"] - it["clientW"] > 2 or it["scrollH"] - it["clientH"] > 2:
            bad.append((it["text"][:20], it["scrollW"], it["clientW"], it["scrollH"], it["clientH"]))
    assert not bad, f"{name}/{fixture}: 텍스트 오버플로 — {bad}"


@pytest.mark.parametrize("fixture", FIXTURES)
def test_stack_cards_do_not_collide(rendered, fixture):
    """적층 카드는 정착 후 겹치지 않고 내용도 카드 높이를 넘지 않는다 (pitch 역산 검증)."""
    cards = rendered[f"v-stack:{fixture}"]["cards"]
    assert len(cards) >= 3, f"카드가 {len(cards)}장뿐"
    cards = sorted(cards, key=lambda c: c["i"])
    for a, b in zip(cards, cards[1:]):
        gap = b["y"] - (a["y"] + a["h"])
        assert gap >= 20, f"v-stack/{fixture}: 카드 {a['i']}↔{b['i']} 간격 {gap:.0f}px"
    over = [(c["i"], c["scrollH"], c["clientH"]) for c in cards if c["scrollH"] - c["clientH"] > 2]
    assert not over, f"v-stack/{fixture}: 카드 내용이 높이를 넘침 — {over}"
    last = cards[-1]
    assert last["y"] + last["h"] <= STAGE_H - SAFE_MARGIN_PX, "마지막 카드가 하단 안전 여백을 침범"


@pytest.mark.parametrize("name", VERTICAL)
def test_frame_match(rendered, name):
    r = rendered[f"{name}:typical"]
    assert r["head_diff"] <= FRAME_MATCH_MAX_RATIO, (
        f"{name}: 첫 프레임 diff {r['head_diff']:.5f} > {FRAME_MATCH_MAX_RATIO}"
    )
    assert r["tail_diff"] <= FRAME_MATCH_MAX_RATIO, (
        f"{name}: 끝 프레임 diff {r['tail_diff']:.5f} > {FRAME_MATCH_MAX_RATIO}"
    )


@pytest.mark.parametrize("name", VERTICAL)
def test_snapshot_committed(name):
    p = TPL_DIR / name / "fixtures" / "snapshots" / "typical.png"
    assert p.exists() and p.stat().st_size > 10_000, f"{name}: typical.png 스냅샷이 없다"
