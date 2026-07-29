# 레이아웃 4종(tpl.l-kpi/l-quad/l-ba/l-mix) preview 실렌더 검증 — 콘솔 에러 0·씬 DOM·최소 폰트 24px·오버플로 0·frame-match·수치 규칙(클램프/증감색/표·차트 일관성) 실측
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"

# 가로 포맷 계약 (formats/wide-16x9/format.yaml stage + wdqa QAConfig 기본값과 동일 상수)
STAGE_W, STAGE_H = 1920, 1080
MIN_FONT_PX = 24.0
SAFE_MARGIN_PX = 16.0
FPS = 24
FRAME_DIFF_CHANNEL_TOL = 8
FRAME_MATCH_MAX_RATIO = 0.02

LAYOUTS = ["l-kpi", "l-quad", "l-ba", "l-mix"]
# min 은 최소 구조, typical 은 대표 구성(실물 유도), max 는 스키마 상한 — 상한이 배치 존 안에 드는지가 실측 역산의 증명
FIXTURES = ["min", "typical", "max"]
CASES = [(n, f) for n in LAYOUTS for f in FIXTURES]

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

# 순수 함수 규칙 실측 — 클램프(0~1 밖 값)와 증감 색 규칙(방향≠평가)을 페이지 안에서 직접 호출
_RULES_JS = """
() => {
  const L = window.OMX && window.OMX.layoutsB;
  if (!L) return { error: 'no-layoutsB' };
  return {
    clamp: [L.clamp01(-0.2), L.clamp01(0), L.clamp01(0.37), L.clamp01(1), L.clamp01(1.4),
            L.clamp01('nope')],
    // 같은 방향이라도 평가가 다르면 색이 다르고, 다른 방향이라도 평가가 같으면 색이 같다
    downGood: L.deltaToneKey({ dir: 'down', tone: 'good' }),
    downBad: L.deltaToneKey({ dir: 'down', tone: 'bad' }),
    upGood: L.deltaToneKey({ dir: 'up', tone: 'good' }),
    upBad: L.deltaToneKey({ dir: 'up', tone: 'bad' }),
    flatNeutral: L.deltaToneKey({ dir: 'flat', tone: 'neutral' }),
    noTone: L.deltaToneKey({ dir: 'down' }),
    glyphs: [L.deltaGlyph({ dir: 'up' }), L.deltaGlyph({ dir: 'down' }), L.deltaGlyph({ dir: 'flat' })],
  };
}
"""

# l-quad 점/범례 실측 — 판 안 좌표와 범례 번호가 짝을 이루는지
_QUAD_JS = """
(svgSel) => {
  const svg = document.querySelector(svgSel);
  const base = svg.getBoundingClientRect();
  const dots = [];
  for (const el of svg.querySelectorAll('foreignObject div')) {
    const cs = getComputedStyle(el);
    if (cs.borderRadius !== '999px' || cs.borderTopWidth !== '2px') continue;
    const b = el.getBoundingClientRect();
    dots.push({ text: (el.textContent || '').trim(),
                x: b.x - base.x, y: b.y - base.y, w: b.width, h: b.height });
  }
  return dots;
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
    """4종 preview × (min, typical, max) 를 1920×1080 원척으로 실렌더하고 측정치를 모은다.

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
            rules = page.evaluate(_RULES_JS)
            dots = page.evaluate(_QUAD_JS, EXPORTABLE_SVG) if name == "l-quad" else []
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
                "rules": rules,
                "dots": dots,
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
def test_stage_is_wide_and_mounted(rendered, name, fixture):
    r = rendered[f"{name}:{fixture}"]
    assert abs(r["box"]["w"] - STAGE_W) <= 1 and abs(r["box"]["h"] - STAGE_H) <= 1, (
        f"{name}/{fixture}: 스테이지 원척이 {STAGE_W}x{STAGE_H} 가 아니다 — {r['box']}"
    )
    assert r["meta"] and r["meta"]["format"] == "wide-16x9"
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
    assert layer["nodes"] >= 20, f"{name}/{fixture}: 씬 DOM 노드가 {layer['nodes']}개뿐 (밀도 미달)"


@pytest.mark.parametrize("name,fixture", CASES)
def test_min_font_24px(rendered, name, fixture):
    scan = rendered[f"{name}:{fixture}"]["scan"]
    assert "error" not in scan, scan
    bad = [
        (it["text"][:20], it["fontSize"])
        for it in scan["items"]
        if it["hasText"] and it["fontSize"] + 1e-6 < MIN_FONT_PX
    ]
    assert not bad, f"{name}/{fixture}: 최소 폰트 {MIN_FONT_PX:.0f}px 미만 텍스트 — {bad}"


@pytest.mark.parametrize("name,fixture", CASES)
def test_safe_margin_16px(rendered, name, fixture):
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


@pytest.mark.parametrize("name", LAYOUTS)
def test_frame_match(rendered, name):
    r = rendered[f"{name}:typical"]
    assert r["head_diff"] <= FRAME_MATCH_MAX_RATIO, (
        f"{name}: 첫 프레임 diff {r['head_diff']:.5f} > {FRAME_MATCH_MAX_RATIO}"
    )
    assert r["tail_diff"] <= FRAME_MATCH_MAX_RATIO, (
        f"{name}: 끝 프레임 diff {r['tail_diff']:.5f} > {FRAME_MATCH_MAX_RATIO}"
    )


@pytest.mark.parametrize("name", LAYOUTS)
def test_snapshot_committed(name):
    p = TPL_DIR / name / "fixtures" / "snapshots" / "typical.png"
    assert p.exists() and p.stat().st_size > 10_000, f"{name}: typical.png 스냅샷이 없다"


# ── 수치 정확성 자기 점검 — 브라우저 안에서 순수 함수를 직접 호출해 규칙을 증명 ──


def test_delta_color_rule_separates_direction_from_verdict(rendered):
    """증감 색은 **평가(tone)**가 정한다 — 방향(dir)이 같아도 평가가 다르면 색이 다르다."""
    r = rendered["l-kpi:typical"]["rules"]
    assert "error" not in r, r
    assert r["downGood"] == "success", "'오류율 ▼62%'(down+good)는 녹색이어야 한다"
    assert r["downBad"] == "error", "down+bad 는 적색"
    assert r["upGood"] == "success", "up+good 는 녹색"
    assert r["upBad"] == "error", "up+bad 는 적색"
    # 같은 방향 → 다른 색 / 다른 방향 → 같은 색 (방향과 색이 독립임의 증명)
    assert r["downGood"] != r["downBad"], "같은 down 인데 평가가 달라도 색이 같다면 규칙이 깨진 것"
    assert r["downGood"] == r["upGood"], "평가가 같으면 방향이 달라도 색은 같아야 한다"
    assert r["flatNeutral"] == "info" and r["noTone"] == "info"
    assert r["glyphs"] == ["▲", "▼", "■"], "글리프는 방향만 표현한다"


def test_quad_coordinates_are_clamped(rendered):
    """0~1 밖 좌표는 clamp01 이 판 안으로 가둔다 (NaN 은 0)."""
    r = rendered["l-quad:typical"]["rules"]
    assert "error" not in r, r
    assert r["clamp"] == [0, 0, 0.37, 1, 1, 0], f"clamp01 결과가 계약과 다르다 — {r['clamp']}"


@pytest.mark.parametrize("fixture", FIXTURES)
def test_quad_dots_stay_inside_board(rendered, fixture):
    """항목 점이 좌표판(1000×592) 안에 있고 번호가 판/범례에서 짝을 이룬다."""
    dots = rendered[f"l-quad:{fixture}"]["dots"]
    n = len(json.loads(
        (TPL_DIR / "l-quad" / "fixtures" / f"{fixture}.json").read_text(encoding="utf-8")
    )["items"])
    assert len(dots) == 2 * n, f"판 점 {n}개 + 범례 번호 {n}개 = {2 * n} 이어야 하는데 {len(dots)}개"
    board_right = 140 + 1000
    # 좌표 사각형 (무대 절대좌표) — marginX 140 + padL 110, contentTop 330 + padT 52
    rect = {"x": 250, "y": 382, "w": 858, "h": 488}
    plot = [d for d in dots if d["x"] < board_right]
    assert len(plot) == n, f"좌표판 안 점이 {len(plot)}개 (기대 {n})"
    for d in plot:
        assert d["x"] >= rect["x"] - 0.5 and d["y"] >= rect["y"] - 0.5, f"점이 좌표 사각형 밖 — {d}"
        assert d["x"] + d["w"] <= rect["x"] + rect["w"] + 0.5, f"점이 오른쪽 밖 — {d}"
        assert d["y"] + d["h"] <= rect["y"] + rect["h"] + 0.5, f"점이 아래 밖 — {d}"
    assert sorted(int(d["text"]) for d in plot) == list(range(1, n + 1))
    # 극단값(0/1)이 실제로 있고 그래도 사각형 안이라는 것이 정규화 배치의 증거다
    items = json.loads(
        (TPL_DIR / "l-quad" / "fixtures" / f"{fixture}.json").read_text(encoding="utf-8")
    )["items"]
    if any(it["y"] in (0, 1) or it["x"] in (0, 1) for it in items):
        assert min(d["y"] for d in plot) >= rect["y"] - 0.5


@pytest.mark.parametrize("fixture", FIXTURES)
def test_mix_table_and_chart_agree(rendered, fixture):
    """l-mix 표·차트 데이터 일관성 — 라벨이 겹치는 행과 막대는 같은 수치를 가리킨다."""
    data = json.loads(
        (TPL_DIR / "l-mix" / "fixtures" / f"{fixture}.json").read_text(encoding="utf-8")
    )
    rows = {r["label"]: [c["v"] for c in r["cells"]] for r in data["table"]["rows"]}
    bars = data["chart"]["bars"]
    shared = [b for b in bars if b["label"] in rows]
    if fixture in ("min", "typical"):
        assert len(shared) >= 3, f"{fixture}: 겹치는 라벨이 {len(shared)}건뿐 — 일관성 검사가 헛돈다"
    for b in shared:
        assert b["display"] in rows[b["label"]], (
            f"막대 {b['label']!r} 판독값 {b['display']!r} 가 같은 행의 셀에 없다 — {rows[b['label']]}"
        )
    # 화면에도 두 표현이 실제로 떠 있는지 (텍스트 실측)
    texts = {it["text"] for it in rendered[f"l-mix:{fixture}"]["scan"]["items"] if it["hasText"]}
    for b in shared:
        assert b["label"] in texts, f"막대 라벨 {b['label']!r} 이 화면에 없다"
        assert b["display"] in texts, f"판독값 {b['display']!r} 이 화면에 없다"


def test_ba_splits_stage_in_half(rendered):
    """l-ba 는 무대를 x=960 에서 정확히 반으로 가른다 — 좌/우 글자가 서로의 반쪽을 침범하지 않는다."""
    for fixture in FIXTURES:
        scan = rendered[f"l-ba:{fixture}"]["scan"]
        crossing = []
        for it in scan["items"]:
            if not it["hasText"] or not it["textRect"]:
                continue
            g = it["textRect"]
            if g["y"] < 330 or g["y"] > 922:      # 크롬(킥커/타이틀/풋노트)은 반반 규칙 밖
                continue
            if g["x"] < 960 - 0.5 and g["x"] + g["w"] > 960 + 0.5:
                crossing.append((it["text"][:20], round(g["x"]), round(g["x"] + g["w"])))
        # 중앙 화살표·개선폭 배지만 경계를 걸친다 (설계된 다리)
        allowed = {"→"}
        gain = json.loads(
            (TPL_DIR / "l-ba" / "fixtures" / f"{fixture}.json").read_text(encoding="utf-8")
        ).get("gain")
        if gain:
            allowed.add(gain)
        bad = [c for c in crossing if c[0] not in allowed]
        assert not bad, f"l-ba/{fixture}: 반반 경계를 넘은 글자 — {bad}"


if __name__ == "__main__":
    # 스냅샷 갱신 진입점 — uv run python tests/test_layouts_b_render.py
    res = measure_previews(write_snapshots=True)
    for k, v in res.items():
        print(k, "errors:", len(v["errors"]), "dur:", v["duration"], "still:", round(v["still"], 2),
              "nodes:", v["layer"].get("nodes"))
