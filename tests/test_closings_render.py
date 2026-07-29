# 클로징 변주 3종(tpl.x-summary/x-quote/x-next) preview 실렌더 검증 — 콘솔 오류 0·최소 폰트 24px·오버플로 0
# + frame-match(특히 tail — 클로징은 영상 마지막이라 마지막 프레임이 안정 화면이어야 한다) + 게이트 1~7 클린
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
JSX_REL = "templates/omx-closings.jsx"

STAGE_W, STAGE_H = 1920, 1080
MIN_FONT_PX = 24.0
SAFE_MARGIN_PX = 16.0
FPS = 24
FRAME_DIFF_CHANNEL_TOL = 8
FRAME_MATCH_MAX_RATIO = 0.02

MODULES = ["x-summary", "x-quote", "x-next"]
SCENE_NAMES = {"x-summary": "요약", "x-quote": "각인", "x-next": "다음 단계"}
NAT = {"x-summary": 14, "x-quote": 10, "x-next": 14}
FIXTURES = ["min", "typical", "max"]
CASES = [(n, f) for n in MODULES for f in FIXTURES]

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
    """3종 preview × (min, typical, max) 를 1920×1080 원척으로 실렌더하고 측정치를 모은다."""
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
            snap = page.screenshot(clip=clip)
            if write_snapshots and fixture == "typical":
                (TPL_DIR / name / "fixtures" / "snapshots").mkdir(parents=True, exist_ok=True)
                (TPL_DIR / name / "fixtures" / "snapshots" / "typical.png").write_bytes(snap)

            # frame-match 는 클로징의 핵심이라 3픽스처 전부 잰다 (마지막 프레임이 안정 화면인가)
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
            # 정지 화면 지속성 — still 시각과 마지막 프레임이 같은 화면인가 (질의응답 대기 전제)
            seek(still)
            still_png = page.screenshot(clip=clip)
            seek(duration - step)
            last_png = page.screenshot(clip=clip)
            settle_diff = _pixel_diff_ratio(still_png, last_png, FRAME_DIFF_CHANNEL_TOL)

            out[f"{name}:{fixture}"] = {
                "errors": errors,
                "duration": duration,
                "still": still,
                "meta": meta,
                "box": {"w": box["width"], "h": box["height"]},
                "layer": layer,
                "scan": scan,
                "head_diff": head_diff,
                "tail_diff": tail_diff,
                "settle_diff": settle_diff,
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
    assert r["meta"]["nat"] == NAT[name]
    assert r["duration"] > 0


@pytest.mark.parametrize("name,fixture", CASES)
def test_no_console_errors(rendered, name, fixture):
    r = rendered[f"{name}:{fixture}"]
    assert r["errors"] == [], f"{name}/{fixture}: 콘솔/페이지 오류 — {r['errors']}"


@pytest.mark.parametrize("name,fixture", CASES)
def test_scene_dom_exists(rendered, name, fixture):
    # x-quote 는 "배경을 비운다"가 설계 자체라 노드 수가 적다 (min: 규칙선·문장·밑줄·출처뿐)
    floor = 6 if name == "x-quote" else 10
    layer = rendered[f"{name}:{fixture}"]["layer"]
    assert layer["ok"], f"{name}/{fixture}: 씬 레이어 비정상 — {layer}"
    assert layer["nodes"] >= floor, f"{name}/{fixture}: 씬 DOM 노드가 {layer['nodes']}개뿐"


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


# ── frame-match — 클로징의 존재 이유 (마지막 프레임이 안정 화면인가) ────────


@pytest.mark.parametrize("name,fixture", CASES)
def test_frame_match(rendered, name, fixture):
    r = rendered[f"{name}:{fixture}"]
    assert r["head_diff"] <= FRAME_MATCH_MAX_RATIO, (
        f"{name}/{fixture}: 첫 프레임 diff {r['head_diff']:.5f} > {FRAME_MATCH_MAX_RATIO}"
    )
    assert r["tail_diff"] <= FRAME_MATCH_MAX_RATIO, (
        f"{name}/{fixture}: 끝 프레임 diff {r['tail_diff']:.5f} > {FRAME_MATCH_MAX_RATIO}"
    )


@pytest.mark.parametrize("name,fixture", CASES)
def test_last_frame_is_the_settled_screen(rendered, name, fixture):
    """still 시각 화면 == 마지막 프레임 화면.

    클로징은 퇴장 효과가 없어야 한다 — progress 1 에서 무언가 사라지고 있으면 컷이 지저분해지고
    정지 화면(질의응답 대기)으로 쓸 수 없다. 두 시각의 픽셀 diff 가 임계 이하면 그 구간 전체가
    정적이라는 뜻이다.

    실측 잔차 0.005~0.012 는 전부 공통 크롬의 dot-grid 텍스처 드리프트(translateY (t*2)%46)다 —
    still~끝 사이 5~10초 동안 점이 10~20px 흐르며 생기는 값이고 내용은 움직이지 않는다.
    인접 프레임 기준(head/tail_diff)은 같은 조건에서 0.000000 이다.
    """
    r = rendered[f"{name}:{fixture}"]
    assert r["settle_diff"] <= FRAME_MATCH_MAX_RATIO, (
        f"{name}/{fixture}: still({r['still']:.2f}s) 과 마지막 프레임이 다르다 "
        f"— diff {r['settle_diff']:.5f} > {FRAME_MATCH_MAX_RATIO} (퇴장 효과 잔존 의심)"
    )


@pytest.mark.parametrize("name,fixture", CASES)
def test_schedule_declares_no_exit(rendered, name, fixture):
    """schedule 에 kind:'exit' 이 하나도 없다 — tpl.closing 과 갈리는 지점(저쪽은 stats-exit 보유)."""
    meta = rendered[f"{name}:{fixture}"]["meta"]
    assert meta["exits"] == 0, f"{name}/{fixture}: 퇴장 이벤트 {meta['exits']}건 — 클로징 규율 위반"


@pytest.mark.parametrize("name", MODULES)
def test_snapshot_committed(name):
    p = TPL_DIR / name / "fixtures" / "snapshots" / "typical.png"
    assert p.exists() and p.stat().st_size > 10_000, f"{name}: typical.png 스냅샷이 없다"


# ── 레이아웃 역산 자기 검증 ────────────────────────────────────────────────


@pytest.mark.parametrize("fixture,count,rowH", [("min", 3, 166.667), ("typical", 4, 120.5),
                                                ("max", 5, 92.8)])
def test_summary_row_height_follows_count(rendered, fixture, count, rowH):
    """행 높이는 스키마가 아니라 렌더가 행 수로 계산한다 — DOM 실측으로 증명."""
    r = rendered[f"x-summary:{fixture}"]
    lay = r["meta"]["layout"]
    assert lay["count"] == count
    assert abs(lay["geo"]["rowH"] - rowH) < 0.05, f"rowH {lay['geo']['rowH']} (기대 {rowH})"
    hits = [
        it for it in r["scan"]["items"]
        if abs(it["rect"]["w"] - 1640) < 1.0 and abs(it["rect"]["h"] - rowH) < 1.0
    ]
    assert len(hits) == count, f"x-summary/{fixture}: 1640×{rowH} 행이 {len(hits)}개 (기대 {count})"
    # 밀집(5행)에서도 수치·문장 폰트는 24px 아래로 내려가지 않는다
    assert lay["geo"]["valueSize"] >= MIN_FONT_PX


def test_summary_dense_switches_metric_scale(rendered):
    """5행에서만 수치가 38px → 31px 로 내려간다 (밀도에 따른 단일 분기)."""
    geo = {f: rendered[f"x-summary:{f}"]["meta"]["layout"]["geo"] for f in FIXTURES}
    assert geo["min"]["valueSize"] == 38 and geo["typical"]["valueSize"] == 38
    assert geo["max"]["valueSize"] == 31 and geo["max"]["dense"] is True
    assert geo["typical"]["dense"] is False


@pytest.mark.parametrize("fixture", FIXTURES)
def test_quote_typography_is_display_scale(rendered, fixture):
    """문장은 언제나 92px — 길어져도 스케일이 줄지 않는다(오프닝 각인형과 같은 층위)."""
    r = rendered[f"x-quote:{fixture}"]
    assert r["meta"]["layout"]["geo"]["quoteSize"] == 92
    big = [it for it in r["scan"]["items"] if it["hasText"] and it["fontSize"] >= 80]
    assert big, f"x-quote/{fixture}: 80px 이상 텍스트가 없다"
    assert all(80 <= it["fontSize"] <= 100 for it in big), (
        f"x-quote/{fixture}: 각인 문장이 80~100px 대역을 벗어났다 — "
        f"{[it['fontSize'] for it in big]}"
    )
    widest = max(it["rect"]["w"] for it in big)
    assert widest <= 1560 + 1, f"x-quote/{fixture}: 문장 폭 {widest} > 1560"


@pytest.mark.parametrize("fixture,steps,cardH", [("min", 3, 172.0), ("typical", 4, 124.0),
                                                 ("max", 4, 124.0)])
def test_next_card_height_follows_step_count(rendered, fixture, steps, cardH):
    """단계 수가 카드 높이를 정하고 시점 필·담당 칩 폭(190px)은 고정이다."""
    r = rendered[f"x-next:{fixture}"]
    lay = r["meta"]["layout"]
    assert lay["steps"] == steps
    assert abs(lay["geo"]["cardH"] - cardH) < 0.05
    assert lay["geo"]["whenW"] == 190 and lay["geo"]["ownerW"] == 190
    hits = [
        it for it in r["scan"]["items"]
        if abs(it["rect"]["w"] - 1020) < 1.0 and abs(it["rect"]["h"] - cardH) < 1.0
    ]
    assert len(hits) == steps, f"x-next/{fixture}: 1020×{cardH} 카드가 {len(hits)}개 (기대 {steps})"


@pytest.mark.parametrize("fixture", FIXTURES)
def test_next_decision_panel_fits(rendered, fixture):
    """좌측 패널 내용(근거 목록 끝)이 확정 메타 자리를 침범하지 않는다."""
    lay = rendered[f"x-next:{fixture}"]["meta"]["layout"]
    g = lay["geo"]
    n = lay["decisionPoints"]
    bottom = g["rows"]["points"] + n * g["pointH"] + (n - 1) * g["pointGap"]
    assert bottom <= g["rows"]["metaTop"], (
        f"x-next/{fixture}: 근거 목록 끝 {bottom} > 메타 상단 {g['rows']['metaTop']}"
    )


# ── 게이트 1~7 — 빌드 패키지에 실제로 물려 돌린다 ──────────────────────────


def _build_with_closings(out_dir: Path) -> Path:
    """클로징 3종을 한 빌드에 물려 게이트를 돌린다.

    registry.yaml 의 load_order_contract 는 병렬 작업자 소유라 아직 omx-closings.jsx 를 모른다
    (modules/_pending/closings.registry.yaml 이 병합 대기 중). 병합 전에도 게이트를 돌리려고
    빌드 산출물에만 스크립트를 덧댄다 — 병합 후에는 이 보정이 no-op 이 된다.
    """
    from wdcore.models.scenario import ScenarioDoc
    from wdpipeline.build import ENTRY_NAME, build_render_package

    data = {
        n: json.loads((TPL_DIR / n / "fixtures" / "typical.json").read_text("utf-8"))
        for n in MODULES
    }
    doc = ScenarioDoc(
        meta={"core_message": "클로징 변주 3종 게이트 검증", "duration_sec": 38},
        content={"summary": data["x-summary"], "quote": data["x-quote"], "nxt": data["x-next"]},
        scenes=[
            {"name": "요약", "dur": 14, "nat": 14, "tpl": "x-summary@1",
             "data_ref": "content.summary",
             "narration": "오늘 심의가 남긴 것은 넷입니다. 근거 수치와 함께 되짚겠습니다."},
            {"name": "각인", "dur": 10, "nat": 10, "tpl": "x-quote@1",
             "data_ref": "content.quote",
             "narration": "결론을 가르는 건 반증 가능성 하나입니다."},
            {"name": "다음 단계", "dur": 14, "nat": 14, "tpl": "x-next@1",
             "data_ref": "content.nxt",
             "narration": "확정 사항과 다음 여섯 주의 일정입니다. 담당과 시점을 확인해 주십시오."},
        ],
    )
    entry = build_render_package(doc, out_dir)
    shutil.copy2(ROOT / "web" / "templates" / "omx-closings.jsx", out_dir / JSX_REL)
    html = entry.read_text(encoding="utf-8")
    tag = f'<script type="text/babel" data-presets="react" src="./{JSX_REL}"></script>'
    if tag not in html:
        marker = '<script type="text/babel" data-presets="react" src="./scenes.jsx"></script>'
        assert marker in html, "엔트리에서 scenes.jsx 스크립트 태그를 찾지 못했다"
        entry.write_text(html.replace(marker, tag + "\n" + marker), encoding="utf-8")
    assert (out_dir / ENTRY_NAME).exists()
    return entry


def test_gates_1_to_7_clean(tmp_path):
    from wdqa.gates import run_gates

    build_dir = tmp_path / "build"
    _build_with_closings(build_dir)
    res = run_gates(build_dir)
    errors = [r for r in res["results"] if r["severity"] == "error"]
    warnings = [r for r in res["results"] if r["severity"] == "warning"]
    assert not errors, f"게이트 error {len(errors)}건 — {errors[:5]}"
    assert res["passed"], f"게이트 미통과 — {res['summary']}"
    fm = [r for r in res["results"] if r["gate"] == 7]
    assert not fm, f"게이트 7(frame-match) 지적 — {fm}"
    print(f"gates: error 0 · warning {len(warnings)} · report {res['report_path']}")


if __name__ == "__main__":
    # 스냅샷 갱신 진입점 — uv run python tests/test_closings_render.py
    res = measure_previews(write_snapshots=True)
    for k, v in res.items():
        print(k, "errors:", len(v["errors"]), "dur:", v["duration"],
              "still:", round(v["still"], 2),
              "head:", f"{v['head_diff']:.6f}", "tail:", f"{v['tail_diff']:.6f}",
              "settle:", f"{v['settle_diff']:.6f}")
