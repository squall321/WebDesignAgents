# 구조·목록 레이아웃 2종(tpl.c-branch/c-grid) preview 실렌더 검증 — 콘솔 오류 0·최소 폰트 24px·오버플로 0·frame-match
# + 레이아웃 정확성(엣지 노드 관통 0·분기 라벨 겹침 0·개수별 카드 크기 자동 조정) + 게이트 1~7 클린
from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
JSX_REL = "templates/omx-layouts-d.jsx"

STAGE_W, STAGE_H = 1920, 1080
MIN_FONT_PX = 24.0
SAFE_MARGIN_PX = 16.0
FPS = 24
FRAME_DIFF_CHANNEL_TOL = 8
FRAME_MATCH_MAX_RATIO = 0.02

MODULES = ["c-branch", "c-grid"]
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
    assert layer["nodes"] >= 10, f"{name}/{fixture}: 씬 DOM 노드가 {layer['nodes']}개뿐"


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


# ── 레이아웃 정확성 자기 검증 — 이 라운드의 존재 이유 ──────────────────────


def _overlap(a: dict, b: dict, eps: float = 0.5) -> bool:
    return (a["x"] + a["w"] - b["x"] > eps and b["x"] + b["w"] - a["x"] > eps
            and a["y"] + a["h"] - b["y"] > eps and b["y"] + b["h"] - a["y"] > eps)


@pytest.mark.parametrize("fixture", FIXTURES)
def test_branch_edges_never_cross_nodes(rendered, fixture):
    """엣지 세로/가로 구간이 노드 상자를 관통하지 않는다 (거터·우회 레인 설계의 실측 증명)."""
    meta = rendered[f"c-branch:{fixture}"]["meta"]
    boxes = list(meta["layout"]["boxes"].values())
    routes = meta["layout"]["routes"]
    assert routes, f"c-branch/{fixture}: 경로가 하나도 없다"
    bad = []
    for r in routes:
        for k, s in enumerate(r["segs"]):
            for b in boxes:
                # 출발/도착 노드의 변에서 시작·끝나므로 접점(0폭 겹침)은 허용, 관통만 잡는다
                if _overlap({"x": s["x"], "y": s["y"], "w": s["w"], "h": s["h"]}, b):
                    bad.append((r["from"], r["to"], k, b["id"]))
    assert not bad, f"c-branch/{fixture}: 엣지가 노드를 관통한다 — {bad}"


@pytest.mark.parametrize("fixture", FIXTURES)
def test_branch_labels_do_not_collide(rendered, fixture):
    """분기 라벨끼리·라벨과 노드가 겹치지 않는다 (거터 120px 안 88×34 필 배치)."""
    meta = rendered[f"c-branch:{fixture}"]["meta"]
    boxes = list(meta["layout"]["boxes"].values())
    labels = [
        {"x": r["labelX"] - 44, "y": r["labelY"] - 17, "w": 88, "h": 34,
         "id": f"{r['from']}→{r['to']}:{r['label']}"}
        for r in meta["layout"]["routes"] if r.get("label")
    ]
    node_hit = [(lb["id"], b["id"]) for lb in labels for b in boxes if _overlap(lb, b)]
    assert not node_hit, f"c-branch/{fixture}: 분기 라벨이 노드를 덮는다 — {node_hit}"
    pair_hit = [
        (labels[i]["id"], labels[j]["id"])
        for i in range(len(labels)) for j in range(i + 1, len(labels))
        if _overlap(labels[i], labels[j])
    ]
    assert not pair_hit, f"c-branch/{fixture}: 분기 라벨끼리 겹친다 — {pair_hit}"


@pytest.mark.parametrize("fixture,count,cols,rows", [("min", 4, 2, 2), ("typical", 6, 3, 2),
                                                     ("max", 9, 3, 3)])
def test_grid_card_size_follows_count(rendered, fixture, count, cols, rows):
    """카드 크기는 스키마가 아니라 렌더가 개수로 계산한다 — DOM 실측으로 증명."""
    r = rendered[f"c-grid:{fixture}"]
    lay = r["meta"]["layout"]
    assert lay["count"] == count, f"c-grid/{fixture}: 카드 {lay['count']}장 (기대 {count})"
    assert lay["shape"] == {"cols": cols, "rows": rows, "dense": rows >= 3}
    gap = 24
    exp_w = (1640 - (cols - 1) * gap) / cols
    exp_h = (592 - (rows - 1) * gap) / rows
    assert abs(lay["geo"]["cardW"] - exp_w) < 0.5 and abs(lay["geo"]["cardH"] - exp_h) < 0.5
    hits = [
        it for it in r["scan"]["items"]
        if abs(it["rect"]["w"] - exp_w) < 1.0 and abs(it["rect"]["h"] - exp_h) < 1.0
    ]
    assert len(hits) == count, (
        f"c-grid/{fixture}: {exp_w:.1f}×{exp_h:.1f} 카드가 {len(hits)}개 (기대 {count})"
    )


def test_grid_card_size_actually_changes(rendered):
    """4 / 6 / 9 장이 서로 다른 카드 크기를 낳는다 (자동 조정이 실제로 작동)."""
    geo = {f: rendered[f"c-grid:{f}"]["meta"]["layout"]["geo"] for f in FIXTURES}
    assert geo["min"]["cardW"] > geo["typical"]["cardW"], "4장(2열)이 6장(3열)보다 넓어야 한다"
    assert geo["typical"]["cardH"] > geo["max"]["cardH"], "6장(2행)이 9장(3행)보다 높아야 한다"
    assert geo["max"]["dense"] and not geo["typical"]["dense"]
    # 밀집에서도 제목·설명 폰트는 24px 아래로 내려가지 않는다
    assert geo["max"]["titleSize"] >= MIN_FONT_PX


# ── 게이트 1~7 — 빌드 패키지에 실제로 물려 돌린다 ──────────────────────────


def _build_with_layouts_d(out_dir: Path) -> Path:
    """c-branch + c-grid 2씬 빌드 후 omx-layouts-d.jsx 를 엔트리에 물린다.

    registry.yaml 의 load_order_contract 는 병렬 작업자 소유라 아직 이 파일을 모른다
    (modules/_pending/layouts-d.registry.yaml 이 병합 대기 중). 병합 전에도 게이트를 돌리려고
    빌드 산출물에만 스크립트를 덧댄다 — 병합 후에는 이 보정이 no-op 이 된다.
    """
    from wdcore.models.scenario import ScenarioDoc
    from wdpipeline.build import ENTRY_NAME, build_render_package

    branch = json.loads((TPL_DIR / "c-branch" / "fixtures" / "typical.json").read_text("utf-8"))
    grid = json.loads((TPL_DIR / "c-grid" / "fixtures" / "typical.json").read_text("utf-8"))
    doc = ScenarioDoc(
        meta={"core_message": "구조·목록 레이아웃 게이트 검증", "duration_sec": 27},
        content={"branch": branch, "grid": grid},
        scenes=[
            {"name": "분기", "dur": 14, "nat": 14, "tpl": "c-branch@1",
             "data_ref": "content.branch", "narration": "편집 권한 판정은 잠금을 먼저 본다."},
            {"name": "목록", "dur": 13, "nat": 13, "tpl": "c-grid@1",
             "data_ref": "content.grid", "narration": "혼동하기 쉬운 위젯 여섯 쌍을 한 화면에 둔다."},
        ],
    )
    entry = build_render_package(doc, out_dir)
    shutil.copy2(ROOT / "web" / "templates" / "omx-layouts-d.jsx", out_dir / JSX_REL)
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
    _build_with_layouts_d(build_dir)
    res = run_gates(build_dir)
    errors = [r for r in res["results"] if r["severity"] == "error"]
    warnings = [r for r in res["results"] if r["severity"] == "warning"]
    assert not errors, f"게이트 error {len(errors)}건 — {errors[:5]}"
    assert res["passed"], f"게이트 미통과 — {res['summary']}"
    print(f"gates: error 0 · warning {len(warnings)} · report {res['report_path']}")


if __name__ == "__main__":
    # 스냅샷 갱신 진입점 — uv run python tests/test_layouts_d_render.py
    res = measure_previews(write_snapshots=True)
    for k, v in res.items():
        print(k, "errors:", len(v["errors"]), "dur:", v["duration"], "still:", round(v["still"], 2))
