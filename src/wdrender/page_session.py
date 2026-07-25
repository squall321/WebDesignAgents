# Playwright 렌더 세션 — 페이지 로드, 3단계 대기, seek 프로토콜, 프레임 캡처의 공통 계층
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

# 엔진(animations-v2.jsx)이 광고하는 export 계약 셀렉터
EXPORTABLE_SVG = "svg[data-om-exportable-video-with-duration-secs]"

# 편집 크롬 제거 + 스테이지 자동 축척(scale) 해제 — 원척 1920×1080 픽셀 캡처의 전제.
# 인라인 style 의 transform 은 stylesheet !important 로만 이길 수 있다.
_EXPORT_CSS = (
    "[data-omelette-chrome]{display:none !important;}\n"
    f"{EXPORTABLE_SVG}{{transform:none !important; box-shadow:none !important;}}"
)

# support.js 가 SRI 와 함께 요청하는 CDN URL (오프라인 폴백 매핑의 키)
REACT_URL = "https://unpkg.com/react@18.3.1/umd/react.production.min.js"
REACT_DOM_URL = "https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js"
BABEL_URL = "https://unpkg.com/@babel/standalone@7.29.0/babel.min.js"


def vendor_resources(vendor_url_base: str) -> dict[str, str]:
    """CDN 실패 대비 window.__resources 폴백 매핑을 만든다.

    vendor_url_base: 서빙 트리 안의 vendor 디렉터리 URL 경로 (예: "/web/vendor").
    """
    base = vendor_url_base.rstrip("/")
    return {
        REACT_URL: f"{base}/react.production.min.js",
        REACT_DOM_URL: f"{base}/react-dom.production.min.js",
        BABEL_URL: f"{base}/babel.min.js",
    }


class RenderSession:
    """헤드리스 크로미엄에서 엔트리를 열고 export 준비 상태까지 끌어올린 세션.

    진입 시 수행 순서.
      1) (선택) window.__resources 주입 — CDN 오프라인 폴백
      2) 페이지 로드 → svg[data-om-exportable-video-with-duration-secs] 마운트 대기
      3) document.fonts.ready 대기
      4) svg[data-om-fonts-inlined="true"] 대기
      5) [data-omelette-chrome] 숨김 + transform:none CSS 주입
      6) duration/sync-seek 능력/캡처 클립 확정
    """

    def __init__(
        self,
        url: str,
        *,
        width: int = 1920,
        height: int = 1080,
        viewport_margin: int = 60,
        resources: dict[str, str] | None = None,
        timeout_ms: int = 60_000,
        headless: bool = True,
    ):
        self.url = url
        self.width = width
        self.height = height
        self.viewport_margin = viewport_margin
        self.resources = resources
        self.timeout_ms = timeout_ms
        self.headless = headless
        self.duration: float = 0.0
        self.sync_seek: bool = False
        self._pw = None
        self._browser = None
        self.page = None
        self._clip: dict[str, int] | None = None

    def __enter__(self) -> "RenderSession":
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=self.headless)
        self.page = self._browser.new_page(
            viewport={
                "width": self.width + self.viewport_margin,
                "height": self.height + self.viewport_margin,
            }
        )
        if self.resources:
            self.page.add_init_script(
                f"window.__resources = {json.dumps(self.resources)};"
            )
        self.page.goto(self.url, wait_until="load", timeout=self.timeout_ms)
        # 1단계 — exportable svg 마운트 (x-import 폴링 완료의 신호)
        self.page.wait_for_selector(
            EXPORTABLE_SVG, state="attached", timeout=self.timeout_ms
        )
        # 2단계 — 문서 폰트 로드 완료
        self.page.evaluate("() => document.fonts.ready.then(() => true)")
        # 3단계 — 엔진의 @font-face 인라인 완료 신호
        self.page.wait_for_selector(
            f'{EXPORTABLE_SVG}[data-om-fonts-inlined="true"]',
            state="attached",
            timeout=self.timeout_ms,
        )
        # 크롬 숨김 + 원척 고정
        self.page.add_style_tag(content=_EXPORT_CSS)
        svg = self.page.query_selector(EXPORTABLE_SVG)
        self.duration = float(
            svg.get_attribute("data-om-exportable-video-with-duration-secs")
        )
        self.sync_seek = svg.get_attribute("data-om-sync-seek") == "true"
        box = svg.bounding_box()
        if box is None or abs(box["width"] - self.width) > 1 or abs(box["height"] - self.height) > 1:
            raise RuntimeError(
                f"스테이지 원척 고정 실패 — 기대 {self.width}x{self.height}, 실측 {box}"
            )
        self._clip = {
            "x": round(box["x"]),
            "y": round(box["y"]),
            "width": self.width,
            "height": self.height,
        }
        return self

    def __exit__(self, *exc) -> None:
        if self._browser is not None:
            self._browser.close()
        if self._pw is not None:
            self._pw.stop()
        self._browser = None
        self._pw = None
        self.page = None

    def seek(self, t: float) -> None:
        """t(초)로 프레임 seek. sync 광고 시 dispatch 반환 즉시 DOM이 해당 프레임 상태."""
        self.page.eval_on_selector(
            EXPORTABLE_SVG,
            "(el, t) => { el.dispatchEvent(new CustomEvent("
            "'data-om-seek-to-time-frame', {detail: {time: t, sync: true}})); }",
            t,
        )
        if not self.sync_seek:
            # sync-seek 미광고 엔진 폴백 — rAF 2회로 비동기 커밋 안착 대기
            self.page.evaluate(
                "() => new Promise(r => requestAnimationFrame("
                "() => requestAnimationFrame(() => r())))"
            )

    def capture(self, path: str | Path | None = None) -> bytes:
        """스테이지 svg 영역을 원척 PNG로 캡처한다."""
        return self.page.screenshot(
            path=str(path) if path is not None else None, clip=self._clip
        )

    def scenes(self) -> list[dict[str, Any]] | None:
        """엔트리의 window.OM_SCENES(JSON 문자열 리터럴)를 파싱해 반환한다."""
        raw = self.page.evaluate("() => window.OM_SCENES")
        if not isinstance(raw, str):
            return None
        return json.loads(raw)
