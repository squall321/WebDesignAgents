# 수치 표현 템플릿 2종 preview 실렌더 검증 — svg 마운트·콘솔 에러 0·씬 DOM·최소 폰트 24px·오버플로 0·수치 정확성(도넛 360°·라인 비례) + 게이트 1~7
from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"

STAGE_W, STAGE_H = 1920, 1080
MIN_FONT_PX = 24.0          # wdqa.config.QAConfig.min_font_px
STAGE_TOL_PX = 2.0
FPS = 24
FRAME_DIFF_CHANNEL_TOL = 8
FRAME_MATCH_MAX_RATIO = 0.02

LAYOUTS = {"c-ratio": "tpl.c-ratio", "c-trend": "tpl.c-trend"}
SCENE_NAME = {"c-ratio": "비율", "c-trend": "추세"}
FIXTURES = ["min", "typical", "max"]
CASES = [(n, f) for n in LAYOUTS for f in FIXTURES]

# 스테이지 내부 HTML 요소 실측 — 누적 opacity·computed fontSize·글리프 rect(Range)
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
    let op = 1, iconOk = false, clipOk = false;
    let node = el;
    while (node && node instanceof HTMLElement) {
      const ncs = node === el ? cs : getComputedStyle(node);
      op *= parseFloat(ncs.opacity || '1');
      if (node.hasAttribute('data-qa-icon')) iconOk = true;
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
      iconOk, clipOk,
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

# 수치 정확성 실측 — 도넛 조각 각도/지분, 라인 점 좌표, 축 절단 표기
_NUM_JS = """
() => {
  const slices = [...document.querySelectorAll('[data-c-slice]')].map((e) => ({
    i: +e.getAttribute('data-c-slice'),
    deg: +e.getAttribute('data-c-slice-deg'),
    share: +e.getAttribute('data-c-slice-share'),
  }));
  const waffle = document.querySelectorAll('[data-c-waffle]').length;
  const plotEl = document.querySelector('[data-c-plot]');
  const plot = plotEl ? JSON.parse(plotEl.getAttribute('data-c-plot')) : null;
  const points = [...document.querySelectorAll('[data-c-point]')].map((e) => ({
    id: e.getAttribute('data-c-point'),
    x: +e.getAttribute('data-c-point-x'),
    y: +e.getAttribute('data-c-point-y'),
    v: +e.getAttribute('data-c-point-value'),
  }));
  const trunc = document.querySelector('[data-c-truncated]');
  return {
    slices, waffle, plot, points,
    truncated: !!trunc,
    truncText: trunc ? (trunc.textContent || '').trim() : '',
    legends: document.querySelectorAll('[data-c-legend]').length,
  };
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


def measure_previews(write_snapshots: bool = True) -> dict:
    """2종 preview × (min, typical, max) 를 1920×1080 원척으로 실렌더하고 측정치를 모은다."""
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
            num = page.evaluate(_NUM_JS)
            snap = page.screenshot(clip=clip)
            if write_snapshots and fixture == "typical":
                (TPL_DIR / name / "fixtures" / "snapshots").mkdir(parents=True, exist_ok=True)
                (TPL_DIR / name / "fixtures" / "snapshots" / "typical.png").write_bytes(snap)

            head_diff = tail_diff = 0.0
            if fixture == "typical":   # frame-match 는 대표 구성 1회 (모션은 데이터 무관)
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
                "errors": errors, "duration": duration, "still": still, "meta": meta,
                "box": {"w": box["width"], "h": box["height"]},
                "layer": layer, "scan": scan, "num": num,
                "head_diff": head_diff, "tail_diff": tail_diff,
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
    assert r["meta"] and r["meta"]["tpl"] == LAYOUTS[name]
    assert r["meta"]["format"] == "wide-16x9"
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
def test_min_font_24px(rendered, name, fixture):
    scan = rendered[f"{name}:{fixture}"]["scan"]
    assert "error" not in scan, scan
    bad = [
        (it["text"][:20], it["fontSize"])
        for it in scan["items"]
        if it["hasText"] and not it["iconOk"] and it["fontSize"] + 1e-6 < MIN_FONT_PX
    ]
    assert not bad, f"{name}/{fixture}: 최소 폰트 {MIN_FONT_PX:.0f}px 미만 텍스트 — {bad}"


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


@pytest.mark.parametrize("name,fixture", CASES)
def test_nothing_exits_stage(rendered, name, fixture):
    scan = rendered[f"{name}:{fixture}"]["scan"]
    bad = []
    for it in scan["items"]:
        if it["clipOk"]:
            continue
        geo = it.get("textRect") if it["hasText"] else it["rect"]
        if not geo:
            continue
        if (geo["x"] < -STAGE_TOL_PX or geo["y"] < -STAGE_TOL_PX
                or geo["x"] + geo["w"] > STAGE_W + STAGE_TOL_PX
                or geo["y"] + geo["h"] > STAGE_H + STAGE_TOL_PX):
            bad.append((it["text"][:20] or f"<{it['tag']}>", round(geo["x"]), round(geo["y"]),
                        round(geo["x"] + geo["w"]), round(geo["y"] + geo["h"])))
    assert not bad, f"{name}/{fixture}: 스테이지 이탈 — {bad}"


# ── 수치 정확성 자기 검증 ────────────────────────────────────────────────

@pytest.mark.parametrize("fixture", FIXTURES)
def test_ratio_angles_sum_to_360(rendered, fixture):
    """도넛 조각 각도 합 = 360°±0.5 · 지분 합 = 100%±0.5 (파생 계산의 실측 증명)."""
    num = rendered[f"c-ratio:{fixture}"]["num"]
    if fixture == "min":       # 와플 스타일 — 조각 대신 100칸
        assert num["waffle"] == 100, f"와플 칸이 {num['waffle']}개 (100칸이어야 한다)"
        assert num["slices"] == []
        return
    slices = num["slices"]
    assert len(slices) >= 4, f"조각이 {len(slices)}개뿐"
    total_deg = sum(s["deg"] for s in slices)
    total_share = sum(s["share"] for s in slices)
    assert abs(total_deg - 360.0) <= 0.5, f"c-ratio/{fixture}: 각도 합 {total_deg}"
    assert abs(total_share - 100.0) <= 0.5, f"c-ratio/{fixture}: 지분 합 {total_share}"
    # 각도와 지분이 같은 파생식에서 나왔는지 — deg = share × 3.6
    for s in slices:
        assert abs(s["deg"] - s["share"] * 3.6) <= 0.01, f"조각 {s['i']} 각도/지분 불일치 — {s}"
    # 큰 것부터 시계 방향 (렌더러 정렬)
    degs = [s["deg"] for s in sorted(slices, key=lambda x: x["i"])]
    assert degs == sorted(degs, reverse=True) or degs[:-1] == sorted(degs[:-1], reverse=True), (
        f"c-ratio/{fixture}: 조각이 큰 것부터 정렬되지 않았다 — {degs}"
    )
    assert num["legends"] == len(slices), "범례 행과 조각 수가 다르다"


@pytest.mark.parametrize("fixture", FIXTURES)
def test_trend_point_coordinates_are_proportional(rendered, fixture):
    """라인 점 좌표가 값에 비례 — y = plotH − (v − min)/(max − min) × plotH 를 전 점 검산."""
    num = rendered[f"c-trend:{fixture}"]["num"]
    plot = num["plot"]
    assert plot, "플롯 기하 메타(data-c-plot)가 없다"
    pts = num["points"]
    assert len(pts) >= 3, f"검산할 점이 {len(pts)}개뿐"
    span = plot["max"] - plot["min"]
    for p in pts:
        expect = plot["h"] - (p["v"] - plot["min"]) / span * plot["h"]
        assert abs(expect - p["y"]) <= 0.01, (
            f"c-trend/{fixture}: 점 {p['id']} v={p['v']} y={p['y']} ≠ 기대 {expect:.3f}"
        )
        assert -0.01 <= p["y"] <= plot["h"] + 0.01, f"점 {p['id']} 이 플롯 밖 — y={p['y']}"
        assert -0.01 <= p["x"] <= plot["w"] + 0.01, f"점 {p['id']} 이 플롯 밖 — x={p['x']}"


@pytest.mark.parametrize("fixture", FIXTURES)
def test_trend_axis_truncation_is_shown_when_baseline_is_not_zero(rendered, fixture):
    """축 하한이 0 이 아니면 절단 표기가 실제로 화면에 뜬다 (0 이면 뜨지 않는다)."""
    r = rendered[f"c-trend:{fixture}"]
    num = r["num"]
    plot = num["plot"]
    if plot["min"] == 0:
        assert not num["truncated"], f"c-trend/{fixture}: 0 기준선인데 절단 표기가 떴다"
        assert not plot["truncated"]
        return
    assert num["truncated"], f"c-trend/{fixture}: 하한 {plot['min']} 인데 절단 표기가 없다"
    assert "축 절단" in num["truncText"], num["truncText"]
    assert str(int(plot["min"])) in num["truncText"], num["truncText"]
    # 절단 칩은 실제로 보이는 텍스트여야 한다 (스캔에 잡히는지)
    texts = [it["text"] for it in r["scan"]["items"] if it["hasText"]]
    assert any("축 절단" in t for t in texts), "절단 칩이 스틸 스캔에 잡히지 않는다"


def test_trend_uneven_spacing_is_value_proportional(rendered):
    """points[].at 이 전부 있으면 x 를 값 비례 배치한다 (max 픽스처가 등간격 at=1..12)."""
    num = rendered["c-trend:max"]["num"]
    assert num["plot"]["proportional"] is True
    xs = sorted({p["x"] for p in num["points"]})
    assert len(xs) == 12
    gaps = [round(b - a, 3) for a, b in zip(xs, xs[1:])]
    assert max(gaps) - min(gaps) <= 0.01, f"등간격 at 인데 x 간격이 흔들린다 — {gaps}"


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
def test_snapshot_committed(rendered, name):
    p = TPL_DIR / name / "fixtures" / "snapshots" / "typical.png"
    assert p.exists() and p.stat().st_size > 10_000, f"{name}: typical.png 스냅샷이 없다"


# ── 품질 게이트 1~7 ──────────────────────────────────────────────────────

def _scenario_for(name: str) -> dict:
    fixture = json.loads(
        (TPL_DIR / name / "fixtures" / "typical.json").read_text(encoding="utf-8")
    )
    nat = {"c-ratio": 12, "c-trend": 13}[name]
    return {
        "tokens_theme": "hwax-blue",
        "scenes": [{"name": SCENE_NAME[name], "dur": nat, "nat": nat,
                    "tpl": LAYOUTS[name], "data_ref": f"content.{name}"}],
        "content": {name: fixture},
    }


@pytest.fixture(scope="module")
def gate_results() -> dict:
    from wdqa.gates import run_gates

    return {
        name: run_gates(TPL_DIR / name / "preview.html", scenario=_scenario_for(name))
        for name in LAYOUTS
    }


@pytest.mark.parametrize("name", LAYOUTS)
def test_gates_have_no_errors(gate_results, name):
    res = gate_results[name]
    errors = [r for r in res["results"] if r["severity"] == "error"]
    assert not errors, f"{name}: 게이트 error {len(errors)}건 — " + json.dumps(
        errors, ensure_ascii=False
    )


@pytest.mark.parametrize("name", LAYOUTS)
def test_all_seven_gates_ran(gate_results, name):
    res = gate_results[name]
    assert res["passed"], res["summary"]
    report = json.loads(Path(res["report_path"]).read_text(encoding="utf-8"))
    assert set(report["gates_run"]) == {"mapping", "length", "contrast", "font",
                                        "overflow", "determinism", "frame_match"}
    # 단계 생략(phase-skipped)이 있으면 뒤 게이트가 실제로 돌지 않은 것이다
    assert not [r for r in res["results"] if r["rule"] in ("phase-skipped", "harness-failure")], (
        res["results"]
    )
