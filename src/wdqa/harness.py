# 런타임 게이트 공용 하네스 — wdrender StaticServer+RenderSession 재사용 + 스틸 시각 DOM 스캔
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from wdrender.page_session import EXPORTABLE_SVG, RenderSession, vendor_resources
from wdrender.server import StaticServer

from .config import QAConfig

# 스틸 시각의 스테이지 내 텍스트·컨테이너 요소 실측 스캔 (게이트 1R·3R·4·5 공용).
# foreignObject 내부 HTML 요소만 대상 — 누적 opacity·배경색 체인·rect·scroll 크기·QA 면제 속성 수집.
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
          textRect = textRect === null ? { l: rr.left, t: rr.top, r: rr.right, b: rr.bottom }
            : { l: Math.min(textRect.l, rr.left), t: Math.min(textRect.t, rr.top),
                r: Math.max(textRect.r, rr.right), b: Math.max(textRect.b, rr.bottom) };
        }
      }
    }
    direct = direct.replace(/\\s+/g, ' ').trim();
    let op = 1, iconOk = false, clipOk = false;
    const bgChain = [];
    let node = el;
    while (node && node instanceof HTMLElement) {
      const ncs = node === el ? cs : getComputedStyle(node);
      op *= parseFloat(ncs.opacity || '1');
      if (node.hasAttribute('data-qa-icon')) iconOk = true;
      if (node.hasAttribute('data-qa-clip-ok')) clipOk = true;
      const bc = ncs.backgroundColor;
      if (bc && bc !== 'transparent' && bc !== 'rgba(0, 0, 0, 0)') bgChain.push(bc);
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
      color: cs.color,
      opacity: op,
      bgChain,
      rect: { x: rect.x - stageRect.x, y: rect.y - stageRect.y,
              w: rect.width, h: rect.height },
      textRect: textRect === null ? null
        : { x: textRect.l - stageRect.x, y: textRect.t - stageRect.y,
            w: textRect.r - textRect.l, h: textRect.b - textRect.t },
      scrollW: el.scrollWidth, scrollH: el.scrollHeight,
      clientW: el.clientWidth, clientH: el.clientHeight,
      overflowX: cs.overflowX, overflowY: cs.overflowY,
      iconOk, clipOk,
    });
  }
  return { stage: { w: stageRect.width, h: stageRect.height }, items };
}
"""

# 게이트 1 런타임 — 활성 씬 레이어가 비어있지 않은지·unmapped 폴백이 아닌지 검사
_LAYER_JS = """
(args) => {
  const [svgSel, idx] = args;
  const svg = document.querySelector(svgSel);
  if (!svg) return { ok: false, reason: 'no-svg' };
  const layer = svg.querySelector('[data-om-scene-layer="' + idx + '"]');
  if (!layer) {
    const any = svg.querySelector('[data-om-scene-layer]');
    return { ok: false, reason: 'no-layer',
             active: any ? any.getAttribute('data-om-scene-layer') : null };
  }
  const nodes = layer.querySelectorAll('*').length;
  const text = (layer.textContent || '').trim();
  const unmapped = text.startsWith('unmapped scene:');
  return { ok: nodes > 0 && !unmapped, reason: unmapped ? 'unmapped' : (nodes === 0 ? 'empty' : ''),
           nodes, snippet: text.slice(0, 60) };
}
"""


class QASession:
    """RenderSession 위에 QA 스캔 편의를 얹은 래퍼 (엔진 계약은 wdrender 가 소유)."""

    def __init__(self, sess: RenderSession, cfg: QAConfig):
        self.sess = sess
        self.cfg = cfg

    @property
    def duration(self) -> float:
        return self.sess.duration

    def seek(self, t: float) -> None:
        self.sess.seek(max(0.0, min(t, self.sess.duration)))

    def capture(self) -> bytes:
        return self.sess.capture()

    def scenes(self) -> list[dict] | None:
        return self.sess.scenes()

    def preview_meta(self) -> dict | None:
        """프리뷰 엔트리의 window.__OMX_PREVIEW__ (있으면 stills 폴백에 사용)."""
        v = self.sess.page.evaluate("() => window.__OMX_PREVIEW__ || null")
        return v if isinstance(v, dict) else None

    def scan(self) -> dict[str, Any]:
        """현재 seek 상태의 스테이지 요소 실측 스캔."""
        return self.sess.page.evaluate(
            _SCAN_JS, [EXPORTABLE_SVG, self.cfg.min_visible_opacity]
        )

    def layer_check(self, idx: int) -> dict[str, Any]:
        return self.sess.page.evaluate(_LAYER_JS, [EXPORTABLE_SVG, idx])


@contextmanager
def open_session(
    serve_root: Path, entry_rel: str, cfg: QAConfig
) -> Iterator[QASession]:
    """StaticServer + RenderSession 을 열어 QASession 으로 감싼다."""
    resources = None
    for cand, base in ((serve_root / "web" / "vendor", "/web/vendor"),
                       (serve_root / "vendor", "/vendor")):
        if (cand / "react.production.min.js").exists():
            resources = vendor_resources(base)
            break
    with StaticServer(serve_root) as srv:
        with RenderSession(srv.url_for(entry_rel), resources=resources) as sess:
            yield QASession(sess, cfg)


def scene_starts(scenes: list[dict]) -> list[float]:
    """씬 전역 시작 시각 누적 리스트 (len = len(scenes)+1, 마지막 = 총 길이)."""
    starts = [0.0]
    for s in scenes:
        starts.append(starts[-1] + float(s["dur"]))
    return starts


def still_times_for_scene(
    scene: dict,
    scenario_scene: dict | None,
    preview_still: float | None,
    cfg: QAConfig,
) -> list[float]:
    """씬 로컬 스틸 시각 목록 — scenario stills → OM_SCENES stills → __OMX_PREVIEW__ → 기본 progress."""
    dur = float(scene["dur"])
    stills: list[float] = []
    if scenario_scene and scenario_scene.get("stills"):
        stills = [float(t) for t in scenario_scene["stills"]]
    elif scene.get("stills"):
        stills = [float(t) for t in scene["stills"]]
    elif preview_still is not None:
        stills = [float(preview_still)]
    else:
        try:
            from wdrender.config import load_config

            progress = load_config().default_still_progress
        except Exception:
            progress = 0.9
        stills = [dur * progress]
    fps = cfg.resolved_fps()
    lo, hi = 0.0, max(0.0, dur - 1.0 / fps)
    return [min(max(t, lo), hi) for t in stills]
