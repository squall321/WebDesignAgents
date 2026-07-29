# 오프닝 변주 3종(tpl.o-statement/o-metric/o-question) preview 실렌더 검증 — 콘솔 오류 0·최소 폰트 24px·
# 오버플로 0·안전 여백·frame-match + 카운트업 결정성(같은 시각 두 번 seek = 같은 픽셀) + 기존 tpl.opening
# 대비 각인 전략 차이(지문 실측·나란히 스냅샷) + 게이트 1~7 클린
from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
JSX_REL = "templates/omx-openings.jsx"

STAGE_W, STAGE_H = 1920, 1080
MIN_FONT_PX = 24.0
SAFE_MARGIN_PX = 16.0
FPS = 24
FRAME_DIFF_CHANNEL_TOL = 8
FRAME_MATCH_MAX_RATIO = 0.02
FIRST_IMPRESSION_T = 0.6  # "첫 인상" 표본 시각 — 이 시점 화면이 4종 서로 달라야 한다

MODULES = ["o-statement", "o-metric", "o-question"]
FIXTURES = ["min", "typical", "max"]
CASES = [(n, f) for n in MODULES for f in FIXTURES]
BASELINE = "opening"  # 기존 오프닝 1종 — 각인 전략 비교 기준선
COUNTUP_PROBES = (0.7, 1.2, 1.8)  # o-metric 카운트업 구간(0.45~2.20s) 안 표본

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
      fontWeight: parseInt(cs.fontWeight, 10) || 400,
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


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _side_by_side(left: bytes, right: bytes) -> bytes:
    """기존 tpl.opening(좌)과 신규 오프닝(우)을 반 척도로 나란히 붙인 비교 스냅샷."""
    from PIL import Image

    a = Image.open(io.BytesIO(left)).convert("RGB").resize((STAGE_W // 2, STAGE_H // 2))
    b = Image.open(io.BytesIO(right)).convert("RGB").resize((STAGE_W // 2, STAGE_H // 2))
    canvas = Image.new("RGB", (STAGE_W, STAGE_H // 2), (233, 235, 241))
    canvas.paste(a, (0, 0))
    canvas.paste(b, (STAGE_W // 2, 0))
    buf = io.BytesIO()
    canvas.save(buf, format="PNG")
    return buf.getvalue()


def measure_previews(write_snapshots: bool = False) -> dict:
    """3종 preview × (min, typical, max) + 기준선 tpl.opening 을 1920×1080 원척으로 실렌더한다."""
    from playwright.sync_api import sync_playwright
    from wdrender.page_session import EXPORTABLE_SVG, vendor_resources
    from wdrender.server import StaticServer

    export_css = (
        "[data-omelette-chrome]{display:none !important;}\n"
        f"{EXPORTABLE_SVG}{{transform:none !important; box-shadow:none !important;}}"
    )
    out: dict = {}
    all_cases = CASES + [(BASELINE, "typical")]
    with StaticServer(ROOT) as srv, sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        for name, fixture in all_cases:
            rel = f"modules/scene-templates/{name}/preview.html"
            url = srv.url_for(rel)
            if name != BASELINE:  # 기존 tpl.opening 프리뷰는 ?fixture= 를 모른다 (typical 고정)
                url = f"{url}?fixture={fixture}"
            page = browser.new_page(viewport={"width": STAGE_W + 60, "height": STAGE_H + 60})
            errors: list[str] = []
            page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
                    if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            page.add_init_script(
                f"window.__resources = {json.dumps(vendor_resources('/web/vendor'))};"
            )
            page.goto(url, wait_until="load", timeout=60_000)
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

            seek(FIRST_IMPRESSION_T)
            first_scan = page.evaluate(_SCAN_JS, [EXPORTABLE_SVG, 0.1])
            first_snap = page.screenshot(clip=clip)

            # 카운트업 결정성 — 같은 시각으로 두 번 seek(사이에 다른 시각 경유)해 픽셀 해시 비교
            countup: list[dict] = []
            if name == "o-metric":
                for t in COUNTUP_PROBES:
                    seek(t)
                    h1 = _sha(page.screenshot(clip=clip))
                    n1 = page.evaluate(_SCAN_JS, [EXPORTABLE_SVG, 0.1])
                    seek(duration - 0.05)   # 멀리 이탈
                    seek(0.0)               # 반대편으로 한 번 더
                    seek(t)                 # 같은 시각으로 복귀
                    h2 = _sha(page.screenshot(clip=clip))
                    big = [it["text"] for it in n1["items"]
                           if it["hasText"] and it["fontSize"] >= 200]
                    countup.append({"t": t, "hash1": h1, "hash2": h2,
                                    "number": big[0] if big else None})

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

            if write_snapshots and fixture == "typical" and name != BASELINE:
                (TPL_DIR / name / "fixtures" / "snapshots").mkdir(parents=True, exist_ok=True)
                (TPL_DIR / name / "fixtures" / "snapshots" / "typical.png").write_bytes(snap)

            out[f"{name}:{fixture}"] = {
                "errors": errors,
                "duration": duration,
                "still": still,
                "meta": meta,
                "box": {"w": box["width"], "h": box["height"]},
                "layer": layer,
                "scan": scan,
                "first_scan": first_scan,
                "first_hash": _sha(first_snap),
                "still_hash": _sha(snap),
                "countup": countup,
                "head_diff": head_diff,
                "tail_diff": tail_diff,
                "snapshot": snap,
                "snapshot_bytes": len(snap),
            }
            page.close()
        browser.close()

    if write_snapshots:  # 기준선과 나란히 둔 각인 전략 비교 스냅샷
        base = out[f"{BASELINE}:typical"]["snapshot"]
        for name in MODULES:
            path = TPL_DIR / name / "fixtures" / "snapshots" / "vs-tpl-opening.png"
            path.write_bytes(_side_by_side(base, out[f"{name}:typical"]["snapshot"]))
    return out


@pytest.fixture(scope="module")
def rendered() -> dict:
    return measure_previews()


def texts(scan: dict, min_font: float = 0.0) -> list[str]:
    return [it["text"] for it in scan["items"]
            if it["hasText"] and it["fontSize"] >= min_font]


# ── 공통 렌더 건전성 ──────────────────────────────────────────────────────


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
    assert layer["nodes"] >= 8, f"{name}/{fixture}: 씬 DOM 노드가 {layer['nodes']}개뿐"


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


@pytest.mark.parametrize("name", MODULES)
def test_frame_match(rendered, name):
    r = rendered[f"{name}:typical"]
    assert r["head_diff"] <= FRAME_MATCH_MAX_RATIO, (
        f"{name}: 첫 프레임 diff {r['head_diff']:.5f} > {FRAME_MATCH_MAX_RATIO}"
    )
    assert r["tail_diff"] <= FRAME_MATCH_MAX_RATIO, (
        f"{name}: 끝 프레임 diff {r['tail_diff']:.5f} > {FRAME_MATCH_MAX_RATIO}"
    )


@pytest.mark.parametrize("name", MODULES)
def test_snapshot_committed(name):
    p = TPL_DIR / name / "fixtures" / "snapshots" / "typical.png"
    assert p.exists() and p.stat().st_size > 10_000, f"{name}: typical.png 스냅샷이 없다"


@pytest.mark.parametrize("name", MODULES)
def test_side_by_side_snapshot_committed(name):
    """기존 tpl.opening 과 나란히 둔 비교 스냅샷 — 각인 전략 차이를 눈으로 확인하는 근거."""
    p = TPL_DIR / name / "fixtures" / "snapshots" / "vs-tpl-opening.png"
    assert p.exists() and p.stat().st_size > 10_000, f"{name}: vs-tpl-opening.png 가 없다"


# ── 카운트업 결정성 — localTime 순수성 실증 ────────────────────────────────


def test_countup_is_deterministic_on_reseek(rendered):
    """같은 시각으로 두 번 seek 하면(사이에 끝·처음을 경유해도) 픽셀 해시가 같다."""
    probes = rendered["o-metric:typical"]["countup"]
    assert len(probes) == len(COUNTUP_PROBES), f"카운트업 표본이 없다 — {probes}"
    bad = [p for p in probes if p["hash1"] != p["hash2"]]
    assert not bad, (
        "재-seek 픽셀 해시 불일치 — "
        + ", ".join(f"t={p['t']}s {p['hash1'][:10]}… ≠ {p['hash2'][:10]}…" for p in bad)
    )


def test_countup_actually_counts(rendered):
    """표본 시각마다 수치가 실제로 다르다 — 정적 숫자를 결정적이라고 우기지 않는다."""
    probes = rendered["o-metric:typical"]["countup"]
    numbers = [p["number"] for p in probes]
    assert all(n and re.fullmatch(r"[\d,]+", n) for n in numbers), f"수치 텍스트 미검출 — {numbers}"
    assert len(set(numbers)) == len(numbers), f"카운트업이 멈춰 있다 — {numbers}"
    values = [int(n.replace(",", "")) for n in numbers]
    assert values == sorted(values), f"카운트업이 단조 증가가 아니다 — {values}"
    target = rendered["o-metric:typical"]["meta"]["layout"]["formatted"]
    assert values[-1] < int(target.replace(",", "")), "표본 시각이 이미 목표값에 도달했다"
    final = [it["text"] for it in rendered["o-metric:typical"]["scan"]["items"]
             if it["hasText"] and it["fontSize"] >= 200]
    assert final and final[0] == target, f"스틸 수치가 목표값이 아니다 — {final} vs {target}"


# ── 각인 전략이 실제로 다른가 — 렌더 실측 층위 ────────────────────────────


def _largest_text(scan: dict) -> dict:
    return max((it for it in scan["items"] if it["hasText"] and it["textRect"]),
               key=lambda it: it["fontSize"])


def imprint(scan: dict) -> tuple:
    """각인 지문 — (최대 폰트, 그 텍스트의 종류, 좌측 여백 고정 여부).

    화면의 주인공이 무엇이고 어디에 박혀 있는지가 곧 각인 전략이다:
    타이틀(tpl.opening) / 문장(o-statement, 좌측 고정) / 숫자(o-metric) / 물음표(o-question).
    """
    big = _largest_text(scan)
    text = big["text"]
    kind = "number" if re.fullmatch(r"[\d,.]+", text) else ("mark" if text == "?" else "text")
    return (round(big["fontSize"]), kind, big["textRect"]["x"] <= 120)


def test_imprint_fingerprints_are_pairwise_distinct(rendered):
    """기존 tpl.opening 포함 4종의 지문이 서로 다르다 — '같은 시리즈'로 보이지 않는다는 실측."""
    prints = {n: imprint(rendered[f"{n}:typical"]["scan"]) for n in [BASELINE] + MODULES}
    assert prints[BASELINE] == (112, "text", False), f"기준선 전제가 변했다 — {prints[BASELINE]}"
    assert prints["o-statement"] == (108, "text", True), prints["o-statement"]
    assert prints["o-metric"] == (220, "number", False), prints["o-metric"]
    assert prints["o-question"] == (168, "mark", False), prints["o-question"]
    values = list(prints.values())
    assert len(set(values)) == len(values), f"지문이 겹친다 — {prints}"
    # 주인공 폰트 크기만으로도 4종이 갈린다 (스케일 위계가 서로 다르다)
    assert len({p[0] for p in values}) == 4, f"주인공 크기가 겹친다 — {prints}"


def test_first_impression_differs_from_legacy_opening(rendered):
    """첫 0.6초에 화면에 있는 것이 4종 모두 다르다 (픽셀 해시·가시 텍스트 양쪽)."""
    hashes = {n: rendered[f"{n}:typical"]["first_hash"] for n in [BASELINE] + MODULES}
    assert len(set(hashes.values())) == 4, f"첫 인상 프레임이 겹친다 — {hashes}"

    # tpl.opening: 0.6s 에는 배지만 (타이틀 등장 at=1.0)
    base_texts = texts(rendered[f"{BASELINE}:typical"]["first_scan"], 60.0)
    assert not base_texts, f"기준선 전제가 변했다 — 0.6s 에 대형 텍스트 {base_texts}"

    # o-statement: 0.6s 에 문장 전체가 이미 실루엣으로 존재한다 (읽히는 순서대로 밝아진다)
    st = rendered["o-statement:typical"]
    lines = [ln["text"] for ln in
             json.loads((TPL_DIR / "o-statement" / "fixtures" / "typical.json").read_text("utf-8"))["lines"]]
    shown = " ".join(texts(st["first_scan"]))
    for ln in lines:
        for word in ln.split():
            assert word in shown, f"o-statement: 0.6s 에 '{word}' 가 없다 — 실루엣 각인 실패"

    # o-metric: 0.6s 에 초대형 수치만, 제목(26px)은 아직 없다
    mt_first = rendered["o-metric:typical"]["first_scan"]
    assert texts(mt_first, 200.0), "o-metric: 0.6s 에 초대형 수치가 없다"
    mt_data = json.loads((TPL_DIR / "o-metric" / "fixtures" / "typical.json").read_text("utf-8"))
    assert mt_data["title"] not in " ".join(texts(mt_first)), (
        "o-metric: 제목이 수치보다 먼저 등장한다 — 위계 역전이 이 템플릿의 존재 이유"
    )

    # o-question: 0.6s 에 질문 1행만, 물음표/칩은 아직 없다
    qs_first = rendered["o-question:typical"]["first_scan"]
    qs_texts = " ".join(texts(qs_first))
    assert "?" not in qs_texts, "o-question: 물음표가 질문보다 먼저 나왔다"
    qs_data = json.loads((TPL_DIR / "o-question" / "fixtures" / "typical.json").read_text("utf-8"))
    for topic in qs_data["topics"]:
        assert topic not in qs_texts, f"o-question: 항목 칩 '{topic}' 이 0.6s 에 이미 보인다"


def test_statement_has_no_badge_no_dots_and_is_left_aligned(rendered):
    """선언형은 장식이 없다 — 배지 필도 도트도 없고 문장은 좌측 정렬 100px 에서 시작한다."""
    r = rendered["o-statement:typical"]
    lay = r["meta"]["layout"]
    assert lay["fontSize"] == 108 and lay["maxChars"] == 16, lay
    size = lay["fontSize"]
    lines = [it for it in r["scan"]["items"]
             if it["hasText"] and abs(it["fontSize"] - size) < 0.5 and it["textRect"]]
    assert len(lines) >= 2, f"문장 행을 찾지 못했다 — {len(lines)}"
    left = min(it["textRect"]["x"] for it in lines)
    assert abs(left - lay["consts"]["stMargin"]) <= 12, f"문장 좌측 시작점 {left:.0f}px"
    # 배지·도트 부재 — 16×16 도트나 pill 배지 크기의 요소가 없다
    dots = [it for it in r["scan"]["items"]
            if abs(it["rect"]["w"] - 16) < 2 and abs(it["rect"]["h"] - 16) < 2]
    assert not dots, f"도트 장식이 남아 있다 — {len(dots)}개"
    for it in r["scan"]["items"]:
        if it["hasText"] and it["textRect"] and it["textRect"]["y"] < 300:
            assert it["fontSize"] >= size - 0.5, (
                f"상단에 배지성 소형 텍스트 — {it['text'][:20]!r} {it['fontSize']}px"
            )


@pytest.mark.parametrize("fixture,size", [("min", 120), ("typical", 108), ("max", 96)])
def test_statement_font_follows_line_length(rendered, fixture, size):
    """행 최대 자수가 폰트를 정한다 — DOM 실측으로 96~120px 대역이 실제로 움직인다."""
    r = rendered[f"o-statement:{fixture}"]
    lay = r["meta"]["layout"]
    assert lay["fontSize"] == size, lay
    hits = [it for it in r["scan"]["items"]
            if it["hasText"] and abs(it["fontSize"] - size) < 0.5 and it["textRect"]]
    assert len(hits) == sum(lay["tokens"]), (
        f"o-statement/{fixture}: {size}px 점등 토큰 {len(hits)}개 (기대 {sum(lay['tokens'])})"
    )
    # 토큰의 세로 위치를 묶으면 행 수가 나온다 (행 높이 = fontSize × 1.24)
    rows = sorted({round(it["textRect"]["y"] / lay["lineH"]) for it in hits})
    assert len(rows) == len(lay["tokens"]), (
        f"o-statement/{fixture}: 행 {len(rows)}개 (기대 {len(lay['tokens'])})"
    )


def test_metric_number_dwarfs_the_title(rendered):
    """수치 220px : 제목 26px — 크기 위계가 뒤집혀 있다 (제목이 조연)."""
    r = rendered["o-metric:typical"]
    lay = r["meta"]["layout"]
    assert lay["valueSize"] == 220 and lay["suffixSize"] == 110
    data = json.loads((TPL_DIR / "o-metric" / "fixtures" / "typical.json").read_text("utf-8"))
    number = [it for it in r["scan"]["items"]
              if it["hasText"] and it["text"] == lay["formatted"]]
    title = [it for it in r["scan"]["items"] if it["hasText"] and it["text"] == data["title"]]
    suffix = [it for it in r["scan"]["items"] if it["hasText"] and it["text"] == data["suffix"]]
    assert number and title and suffix, "수치/단위/제목 요소를 찾지 못했다"
    assert number[0]["fontSize"] >= 180, number[0]["fontSize"]
    assert number[0]["fontSize"] / title[0]["fontSize"] >= 6.0, (
        f"수치/제목 비 {number[0]['fontSize'] / title[0]['fontSize']:.1f} — 충격이 부족하다"
    )
    assert title[0]["textRect"]["y"] > number[0]["textRect"]["y"], "제목이 수치 위에 있다"


@pytest.mark.parametrize("fixture", FIXTURES)
def test_metric_number_row_fits_the_stage(rendered, fixture):
    """스키마 상한(6자리·소수 1·단위 3자)에서도 220px 수치 행이 무대 안에 남는다 — 글리프 실측."""
    r = rendered[f"o-metric:{fixture}"]
    lay = r["meta"]["layout"]
    rows = [it for it in r["scan"]["items"]
            if it["hasText"] and it["text"] == lay["formatted"] and it["textRect"]]
    assert rows, f"o-metric/{fixture}: 수치 텍스트를 찾지 못했다 ({lay['formatted']})"
    box = rows[0]["textRect"]
    right = box["x"] + box["w"]
    suffix = [it for it in r["scan"]["items"]
              if it["hasText"] and abs(it["fontSize"] - lay["suffixSize"]) < 0.5 and it["textRect"]]
    if suffix:
        right = max(right, suffix[0]["textRect"]["x"] + suffix[0]["textRect"]["w"])
    measured = right - box["x"]
    assert measured <= 1720, f"o-metric/{fixture}: 수치 행 실측 폭 {measured:.0f}px > 1720px"
    # 추정식(mtWidthEm)이 실측보다 보수적이어야 스키마 상한이 안전판 구실을 한다
    estimated = lay["widthEm"] * lay["valueSize"]
    assert estimated >= measured - 1.0, (
        f"o-metric/{fixture}: 추정 {estimated:.0f}px < 실측 {measured:.0f}px — 추정식이 낙관적이다"
    )


def test_question_keeps_the_answer_slot_empty(rendered):
    """중앙 빈 자리(Ø300 원 + 물음표) + 항목 칩 3개 — 답을 비워 두는 구조."""
    r = rendered["o-question:typical"]
    lay = r["meta"]["layout"]
    assert lay["ring"] == 300 and lay["topics"] == 3
    marks = [it for it in r["scan"]["items"] if it["hasText"] and it["text"] == "?"]
    assert marks and marks[0]["fontSize"] >= 150, f"물음표 — {marks}"
    ring = [it for it in r["scan"]["items"]
            if abs(it["rect"]["w"] - 300) < 8 and abs(it["rect"]["h"] - 300) < 8]
    assert ring, "Ø300 빈 자리 원을 찾지 못했다"
    data = json.loads((TPL_DIR / "o-question" / "fixtures" / "typical.json").read_text("utf-8"))
    chips = [it for it in r["scan"]["items"]
             if it["hasText"] and it["text"] in data["topics"] and it["textRect"]]
    assert len(chips) == 3, f"항목 칩 {len(chips)}개"
    assert all(c["textRect"]["y"] > marks[0]["textRect"]["y"] for c in chips), "칩이 물음표 위에 있다"


# ── 게이트 1~7 — 빌드 패키지에 실제로 물려 돌린다 ──────────────────────────


def _build_with_openings(out_dir: Path) -> tuple[Path, dict]:
    """오프닝 3종을 3씬으로 빌드한 뒤 omx-openings.jsx 를 엔트리에 물린다.

    registry.yaml 의 load_order_contract 는 병렬 작업자 소유라 아직 이 파일을 모른다
    (modules/_pending/openings.registry.yaml 이 병합 대기 중). 병합 전에도 게이트를 돌리려고
    빌드 산출물에만 스크립트를 덧댄다 — 병합 후에는 이 보정이 no-op 이 된다.
    """
    from wdcore.models.scenario import ScenarioDoc
    from wdpipeline.build import ENTRY_NAME, build_render_package

    def fx(name: str) -> dict:
        return json.loads((TPL_DIR / name / "fixtures" / "typical.json").read_text("utf-8"))

    doc = ScenarioDoc(
        meta={"core_message": "오프닝 변주 3종 게이트 검증", "duration_sec": 25},
        content={"statement": fx("o-statement"), "metric": fx("o-metric"),
                 "question": fx("o-question")},
        scenes=[
            {"name": "선언", "dur": 8, "nat": 8, "tpl": "o-statement@1",
             "data_ref": "content.statement",
             "narration": "가장 위험한 결정은 아무도 반박하지 않은 결정입니다."},
            {"name": "수치", "dur": 8, "nat": 8, "tpl": "o-metric@1",
             "data_ref": "content.metric",
             "narration": "지난 한 달 동안 천이백사십 건의 안건이 심의를 거쳤습니다."},
            {"name": "질문", "dur": 9, "nat": 9, "tpl": "o-question@1",
             "data_ref": "content.question",
             "narration": "우리는 무엇을 근거로 결정한다고 말할 수 있는지 묻습니다."},
        ],
    )
    entry = build_render_package(doc, out_dir)
    shutil.copy2(ROOT / "web" / "templates" / "omx-openings.jsx", out_dir / JSX_REL)
    html = entry.read_text(encoding="utf-8")
    tag = f'<script type="text/babel" data-presets="react" src="./{JSX_REL}"></script>'
    if tag not in html:
        marker = '<script type="text/babel" data-presets="react" src="./scenes.jsx"></script>'
        assert marker in html, "엔트리에서 scenes.jsx 스크립트 태그를 찾지 못했다"
        entry.write_text(html.replace(marker, tag + "\n" + marker), encoding="utf-8")
    assert (out_dir / ENTRY_NAME).exists()
    return entry, doc.model_dump(mode="json")


def test_gates_1_to_7_clean(tmp_path):
    from wdqa.gates import run_gates

    build_dir = tmp_path / "build"
    _, scenario = _build_with_openings(build_dir)
    res = run_gates(build_dir, scenario=scenario)
    errors = [r for r in res["results"] if r["severity"] == "error"]
    warnings = [r for r in res["results"] if r["severity"] == "warning"]
    assert not errors, f"게이트 error {len(errors)}건 — {errors[:5]}"
    assert res["passed"], f"게이트 미통과 — {res['summary']}"
    print(f"gates: error 0 · warning {len(warnings)} · report {res['report_path']}")


if __name__ == "__main__":
    # 스냅샷 갱신 진입점 — uv run python tests/test_openings_render.py
    res = measure_previews(write_snapshots=True)
    for k, v in res.items():
        print(k, "errors:", len(v["errors"]), "dur:", v["duration"], "still:", round(v["still"], 2),
              "imprint:", imprint(v["scan"]))
