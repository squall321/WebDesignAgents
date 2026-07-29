# 문서 HTML 산출물 브라우저 재열기 검증 — 콘솔 에러 0·목차 앵커 동작·이미지 로드·self 단독 실행
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from wdrender.exporter_doc import export_html

ROOT = Path(__file__).resolve().parents[1]
REAL_FIXTURE = ROOT / "data" / "doc_check" / "document.json"


def _make_still(path: Path) -> Path:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (960, 540), "#EBEEFA")
    ImageDraw.Draw(img).rectangle([40, 40, 920, 500], outline="#1428A0", width=6)
    img.save(path)
    return path


def _doc(still: Path) -> dict:
    return {
        "meta": {"title": "브라우저 재열기 검증본", "core_message": "같은 심의, 세 번째 표현.",
                 "date": "2026-07-29"},
        "sections": [
            {"title": "오프닝", "blocks": [
                {"type": "figure", "src": str(still), "caption": "오프닝 씬"},
                {"type": "paragraph", "text": "본문 문장이다.", "refs": ["RA-001"]},
            ]},
            {"title": "근거", "blocks": [
                {"type": "table", "caption": "비교", "columns": ["항목", "값"],
                 "rows": [["게시", "사본 아님"]]},
                {"type": "paragraph", "text": "두 번째 절의 문장이다."},
            ]},
            {"title": "클로징", "blocks": [
                {"type": "figure", "src": str(still), "caption": "클로징 씬"},
                {"type": "paragraph", "text": "마무리 문장이다."},
            ]},
        ],
        "footnotes": [{"id": "RA-001", "text": "플랫폼 개요",
                       "source": {"page": "1. 개요", "block_id": "h1"}}],
    }


def _inspect(page, url: str) -> dict:
    """페이지를 열고 콘솔·이미지·앵커·오버플로를 한 번에 측정한다."""
    errors: list[str] = []
    failed: list[str] = []
    page.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}")
            if m.type in ("error", "warning") else None)
    page.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
    page.on("requestfailed", lambda r: failed.append(f"{r.url[:80]} {r.failure}"))
    page.goto(url, wait_until="load", timeout=30_000)
    page.evaluate("() => document.fonts.ready.then(() => true)")
    data = page.evaluate("""() => ({
        images: Array.from(document.images).map(i => ({
            ok: i.complete && i.naturalWidth > 0, external: !i.currentSrc.startsWith('data:')
        })),
        anchors: Array.from(document.querySelectorAll('nav.toc a')).map(a => a.getAttribute('href')),
        resolved: Array.from(document.querySelectorAll('nav.toc a'))
            .every(a => !!document.getElementById(decodeURIComponent(a.getAttribute('href')).slice(1))),
        fnrefs: document.querySelectorAll('sup.fnref a').length,
        pretendard: document.fonts.check("16px 'Pretendard Variable'"),
        overflowX: document.documentElement.scrollWidth - window.innerWidth,
    })""")
    # 목차 마지막 항목을 눌러 실제로 이동하는지
    before = page.evaluate("() => window.scrollY")
    page.click("nav.toc a >> nth=-1")
    page.wait_for_timeout(300)
    data.update(errors=errors, failed=failed, scrolled=page.evaluate("() => window.scrollY") - before,
                hash=page.evaluate("() => location.hash"))
    return data


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        yield b
        b.close()


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("doc")
    still = _make_still(d / "scene.png")
    doc = _doc(still)
    light = d / "report_light.html"
    selfc = d / "report_self.html"
    export_html(doc, light, mode="light", log=lambda m: None)
    export_html(doc, selfc, mode="self", log=lambda m: None)
    return {"light": light, "self": selfc}


def test_light_html_은_에러_없이_열리고_목차가_동작한다(browser, built):
    page = browser.new_page(viewport={"width": 1000, "height": 900})
    try:
        r = _inspect(page, built["light"].as_uri())
    finally:
        page.close()
    assert r["errors"] == [], f"콘솔 에러/경고가 있다: {r['errors']}"
    assert r["failed"] == [], f"자원 로드 실패: {r['failed']}"
    assert len(r["images"]) == 2 and all(i["ok"] for i in r["images"])
    assert all(i["external"] for i in r["images"]), "light 모드는 외부 파일을 참조한다"
    assert len(r["anchors"]) == 3 and r["resolved"], f"앵커 미해소: {r['anchors']}"
    assert r["scrolled"] > 100, "목차 링크를 눌러도 이동하지 않는다"
    assert r["hash"], "앵커 이동 후 해시가 없다"
    assert r["fnrefs"] == 1
    assert r["pretendard"], "상대 경로 @font-face 가 로드되지 않았다"
    assert r["overflowX"] <= 1, f"가로 스크롤이 생겼다: {r['overflowX']}px"


def test_self_html_은_단독_복사해도_외부_자원_없이_열린다(browser, built, tmp_path):
    """다른 디렉터리로 파일 하나만 옮겨 file:// 로 연다 — 메일 첨부 상황의 실증."""
    alone = tmp_path / "옮긴자리" / "report.html"
    alone.parent.mkdir(parents=True)
    shutil.copy2(built["self"], alone)
    assert not any(p.name != alone.name for p in alone.parent.iterdir())

    page = browser.new_page(viewport={"width": 1000, "height": 900})
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url))
    try:
        r = _inspect(page, alone.as_uri())
    finally:
        page.close()
    assert r["errors"] == [] and r["failed"] == []
    assert len(r["images"]) == 2 and all(i["ok"] for i in r["images"])
    assert not any(i["external"] for i in r["images"]), "self 모드인데 외부 이미지 참조가 남았다"
    assert r["pretendard"], "인라인 폰트가 로드되지 않았다"
    assert r["resolved"] and r["scrolled"] > 100
    # 문서 자신 말고는 아무것도 요청하지 않아야 한다
    outside = [u for u in requests if u != alone.as_uri()]
    assert outside == [], f"외부 요청이 있다: {outside}"


@pytest.mark.skipif(not REAL_FIXTURE.exists(), reason="data/doc_check/document.json 없음")
def test_실데이터_self_문서도_단독으로_열린다(browser, tmp_path):
    doc = json.loads(REAL_FIXTURE.read_text(encoding="utf-8"))
    out = tmp_path / "solo" / "report.html"
    export_html(doc, out, mode="self", assets_root=ROOT, log=lambda m: None)
    page = browser.new_page(viewport={"width": 1000, "height": 900})
    requests: list[str] = []
    page.on("request", lambda r: requests.append(r.url))
    try:
        r = _inspect(page, out.as_uri())
    finally:
        page.close()
    assert r["errors"] == [] and r["failed"] == []
    assert len(r["images"]) == 7 and all(i["ok"] and not i["external"] for i in r["images"])
    assert r["resolved"] and r["overflowX"] <= 1
    assert [u for u in requests if u != out.as_uri()] == []
