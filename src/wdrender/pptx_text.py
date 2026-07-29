# 하이브리드 PPTX 텍스트층 — 렌더 페이지의 리프 텍스트 요소를 좌표·타이포와 함께 수집하고, 배경 캡처용으로 같은 요소를 숨긴다
from __future__ import annotations

import re
from typing import Any

# 스테이지 svg 셀렉터는 page_session 의 export 계약을 그대로 쓴다
from .page_session import EXPORTABLE_SVG

EMU_PER_POINT = 12700

# 누적 불투명도가 이 값 미만이면 "애니메이션 진행 중"으로 보고 네이티브 텍스트로 승격하지 않는다.
# (승격하지 않은 요소는 숨기지도 않으므로 배경 캡처에 원래의 반투명 모습 그대로 남는다)
MIN_OPACITY = 0.95

# ── 폰트 대체 매핑 ────────────────────────────────────────────────────────
# python-pptx 는 폰트 임베딩을 지원하지 않는다. PPTX 는 열람 PC 에 설치된 폰트로만
# 렌더되므로, 렌더 무대에서 쓰는 Pretendard 계열을 윈도우 기본 한글 폰트로 내린다.
DEFAULT_FALLBACK_FONT = "맑은 고딕"
FONT_FALLBACK: dict[str, str] = {
    "pretendard variable": "맑은 고딕",
    "pretendard": "맑은 고딕",
    "noto sans kr": "맑은 고딕",
    "malgun gothic": "맑은 고딕",
    "맑은 고딕": "맑은 고딕",
    "apple sd gothic neo": "맑은 고딕",
    "sans-serif": "맑은 고딕",
    "system-ui": "맑은 고딕",
    "-apple-system": "맑은 고딕",
    "serif": "바탕",
    "nanummyeongjo": "바탕",
    "monospace": "Consolas",
    "d2coding": "D2Coding",
    "consolas": "Consolas",
    "courier new": "Courier New",
    "arial": "Arial",
    "helvetica": "Arial",
}


def map_font_family(css_family: str) -> str:
    """CSS font-family 스택에서 첫 매핑 가능한 패밀리를 PPTX 용 폰트명으로 바꾼다."""
    for raw in (css_family or "").split(","):
        name = raw.strip().strip("'\"").lower()
        if name in FONT_FALLBACK:
            return FONT_FALLBACK[name]
    return DEFAULT_FALLBACK_FONT


_RGB_RE = re.compile(r"rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)")


def parse_css_color(css_color: str) -> tuple[int, int, int] | None:
    """computed color("rgb(a, b, c)")를 (r, g, b) 로. 파싱 실패 시 None."""
    m = _RGB_RE.match(css_color or "")
    if not m:
        return None
    return tuple(max(0, min(255, int(round(float(g))))) for g in m.groups())  # type: ignore[return-value]


# ── 역할 분류 ────────────────────────────────────────────────────────────
# 근거.
#  - 두 포맷(1920×1080 가로 / 1080×1920 세로)의 타입 스케일은 모두 **짧은 변 1080px**
#    기준으로 저작돼 있다(hwax-blue semantic.type). 그래서 폰트 크기를 짧은 변으로
#    정규화하면 가로/세로가 같은 자로 비교된다. rel = font_px / min(stage_w, stage_h).
#  - 실측 기준점: 가로 sectionTitle 56 → 0.052, hero 112 → 0.104 / 세로 title 72 → 0.067,
#    hero 96 → 0.089 / 본문 26·40 → 0.024·0.037 / 킥커 26·32(700 이상) / 푸터 24·32.
#  - 킥커(작지만 굵고 화면 상단)와 본문(같은 크기, 400)은 크기로 갈리지 않으므로
#    굵기와 y 위치가 결정한다. 푸터·주석은 화면 하단(y_rel ≥ 0.88)이 결정한다.
#  - 중간 밴드(0.031~0.050)에는 가로 subtitle 36/500 과 세로 body 40/400 이 함께 산다.
#    크기로는 갈리지 않아 굵기 500 이상을 subtitle 로 본다(상단 30% 는 굵기 무관 subtitle).
ROLE_TITLE_REL = 0.050  # 가로 56px / 세로 54px 이상
ROLE_SUB_REL = 0.031  # 가로 34px / 세로 34px 이상
ROLE_SUB_WEIGHT = 500  # 중간 밴드에서 subtitle 로 올릴 최소 굵기
ROLE_TOP_BAND = 0.20  # 킥커가 사는 상단 밴드
ROLE_SUB_TOP_BAND = 0.30  # 굵기와 무관하게 subtitle 로 보는 상단대
ROLE_BOTTOM_BAND = 0.88  # 푸터·각주가 사는 하단 밴드


def classify_role(box: dict[str, Any], stage: dict[str, float]) -> str:
    """텍스트 상자를 title/subtitle/body/caption/label 중 하나로 분류한다(휴리스틱)."""
    short_side = max(1.0, min(float(stage["w"]), float(stage["h"])))
    rel = float(box["font_size_px"]) / short_side
    y_rel = (float(box["y"]) + float(box["h"]) / 2.0) / max(1.0, float(stage["h"]))
    weight = int(box.get("font_weight") or 400)

    if rel >= ROLE_TITLE_REL:
        # 대형 지표값(예: 320px "100")도 여기 들어온다 — 크기만으로는 제목과 구분되지 않는다.
        return "title"
    if rel >= ROLE_SUB_REL:
        if weight >= ROLE_SUB_WEIGHT or y_rel < ROLE_SUB_TOP_BAND:
            return "subtitle"
        return "body"
    if weight >= 700 and y_rel <= ROLE_TOP_BAND:
        return "label"  # 킥커
    if y_rel >= ROLE_BOTTOM_BAND:
        return "caption"  # 푸터·출처·각주
    if weight >= 700:
        return "label"  # 카드 제목·칩·단계 번호
    return "body"


# ── 브라우저 측 수집기 ───────────────────────────────────────────────────
# 리프 텍스트 규칙: "직속 자식으로 공백 아닌 텍스트 노드를 가진 요소"만 채택하고,
# 채택된 조상의 자손은 건너뛴다(중복 방지). 강조 span 등은 부모의 run 으로 흡수된다.
_COLLECT_JS = r"""
(arg) => {
  const {sel, hide, minOpacity} = arg;
  const svg = document.querySelector(sel);
  if (!svg) return null;

  // 이전 호출에서 숨긴 요소 복원 — 추출 술어와 캡처 술어를 항상 일치시킨다
  document.querySelectorAll('[data-wda-pptx-hidden]').forEach((el) => {
    el.setAttribute('style', el.getAttribute('data-wda-pptx-s0') || '');
    el.removeAttribute('data-wda-pptx-hidden');
    el.removeAttribute('data-wda-pptx-s0');
  });

  const host = svg.querySelector('foreignObject > div') || svg;
  const sr = svg.getBoundingClientRect();
  const boxes = [];
  const skipped = [];
  const SKIP = {SCRIPT: 1, STYLE: 1, TITLE: 1, DEFS: 1, NOSCRIPT: 1};

  // 조상 사슬의 누적 불투명도·행렬. 도중에 display:none / visibility:hidden 이면 null.
  const accum = (el) => {
    let op = 1;
    let m = new DOMMatrix();
    for (let n = el; n && n !== svg; n = n.parentElement) {
      const cs = getComputedStyle(n);
      if (cs.display === 'none' || cs.visibility === 'hidden') return null;
      const o = parseFloat(cs.opacity);
      if (!isNaN(o)) op *= o;
      if (cs.transform && cs.transform !== 'none') {
        m = new DOMMatrix(cs.transform).multiply(m);
      }
    }
    return {op: op, m: m};
  };

  const num = (v) => { const x = parseFloat(v); return isNaN(x) ? 0 : x; };

  // 글자만 지운다 — visibility:hidden 은 요소의 배경·테두리·그림자(칩·필·카드)까지
  // 함께 지워 배경 캡처를 망가뜨린다. 색을 투명으로 내리면 장식은 그대로 남는다.
  // 테두리 색 기본값이 currentColor 이므로 실측값으로 먼저 고정한다.
  const hideGlyphs = (root) => {
    const stack = [root];
    while (stack.length) {
      const n = stack.pop();
      const cs = getComputedStyle(n);
      n.setAttribute('data-wda-pptx-s0', n.getAttribute('style') || '');
      n.setAttribute('data-wda-pptx-hidden', '1');
      n.style.setProperty('border-color', [cs.borderTopColor, cs.borderRightColor,
                                           cs.borderBottomColor, cs.borderLeftColor].join(' '),
                          'important');
      n.style.setProperty('color', 'transparent', 'important');
      n.style.setProperty('-webkit-text-fill-color', 'transparent', 'important');
      n.style.setProperty('text-shadow', 'none', 'important');
      for (const c of n.children) if (!SKIP[c.tagName]) stack.push(c);
    }
  };

  // 한 요소의 직속 자식들을 스타일 단위 run 으로 쪼갠다 (강조 span 색·굵기 보존).
  // <br> 과 pre 계열의 개행은 {br:true} 마커로 남겨 파워포인트 줄바꿈(a:br)으로 옮긴다.
  const WS_PRE = {'pre': 1, 'pre-wrap': 1, 'pre-line': 1, 'break-spaces': 1};
  const pushText = (runs, s, style, ws) => {
    if (WS_PRE[ws]) {
      const parts = s.split('\n');
      for (let i = 0; i < parts.length; i++) {
        if (i) runs.push({br: true});
        if (parts[i]) runs.push(Object.assign({text: parts[i]}, style));
      }
    } else {
      // white-space:normal 은 브라우저가 연속 공백을 하나로 접는다 — 같게 맞춘다
      const t = s.replace(/\s+/g, ' ');
      if (t) runs.push(Object.assign({text: t}, style));
    }
  };
  const runsOf = (el, cs) => {
    const runs = [];
    for (const n of el.childNodes) {
      if (n.nodeType === 3) {
        if (n.nodeValue) {
          pushText(runs, n.nodeValue,
                   {color: cs.color, weight: cs.fontWeight, italic: cs.fontStyle === 'italic'},
                   cs.whiteSpace);
        }
      } else if (n.nodeType === 1) {
        if (SKIP[n.tagName]) continue;
        if (n.tagName === 'BR') { runs.push({br: true}); continue; }
        const ccs = getComputedStyle(n);
        if (ccs.display === 'none' || ccs.visibility === 'hidden') continue;
        const txt = n.textContent;
        if (!txt) continue;
        pushText(runs, txt,
                 {color: ccs.color, weight: ccs.fontWeight, italic: ccs.fontStyle === 'italic'},
                 ccs.whiteSpace);
      }
    }
    // 양끝 공백은 브라우저도 버린다
    while (runs.length && (runs[0].br || !runs[0].text.trim())) runs.shift();
    while (runs.length && (runs[runs.length - 1].br || !runs[runs.length - 1].text.trim())) runs.pop();
    if (runs.length) {
      runs[0].text = runs[0].text.replace(/^\s+/, '');
      runs[runs.length - 1].text = runs[runs.length - 1].text.replace(/\s+$/, '');
    }
    return runs;
  };

  // 줄 수 — 내용 range 의 클라이언트 사각형을 top 기준(폰트 크기의 60% 허용오차)으로 묶는다
  const lineCount = (el, fs) => {
    const rng = document.createRange();
    rng.selectNodeContents(el);
    const rects = Array.from(rng.getClientRects()).filter((r) => r.width > 0 && r.height > 0);
    if (!rects.length) return 1;
    const tops = rects.map((r) => r.top).sort((a, b) => a - b);
    const tol = Math.max(2, fs * 0.6);
    let lines = 1;
    let last = tops[0];
    for (const t of tops) { if (t - last > tol) { lines += 1; last = t; } }
    return lines;
  };

  const walk = (el, ancestorPicked) => {
    let picked = false;
    if (!SKIP[el.tagName] && !ancestorPicked) {
      for (const n of el.childNodes) {
        if (n.nodeType === 3 && n.nodeValue.trim()) { picked = true; break; }
      }
    }
    if (picked) {
      const cs = getComputedStyle(el);
      const runs = runsOf(el, cs);
      const text = runs.map((r) => (r.br ? '\n' : r.text)).join('');
      const ac = accum(el);
      const r = el.getBoundingClientRect();
      const brief = text.trim().slice(0, 40);
      if (!text.trim()) {
        picked = false;                                  // 공백뿐 — 조용히 통과
      } else if (ac === null) {
        skipped.push({text: brief, reason: 'hidden'});
        picked = false;
      } else if (Math.abs(ac.m.b) > 1e-3 || Math.abs(ac.m.c) > 1e-3) {
        // 회전·기울임이 걸린 요소는 텍스트박스로 재현하면 위치가 어긋난다 — 배경에 남긴다
        skipped.push({text: brief, reason: 'rotate/skew',
                      matrix: [ac.m.a, ac.m.b, ac.m.c, ac.m.d]});
        picked = false;
      } else if (ac.op < minOpacity) {
        skipped.push({text: brief, reason: 'opacity', opacity: +ac.op.toFixed(3)});
        picked = false;
      } else if (r.width < 1 || r.height < 1) {
        skipped.push({text: brief, reason: 'zero-size'});
        picked = false;
      } else if (r.right <= sr.left || r.left >= sr.right ||
                 r.bottom <= sr.top || r.top >= sr.bottom) {
        skipped.push({text: brief, reason: 'offstage'});
        picked = false;
      } else {
        const sx = ac.m.a || 1;
        const sy = ac.m.d || 1;
        // 테두리+패딩을 뺀 콘텐츠 상자 — 배지처럼 패딩이 큰 요소도 글자 위치가 맞는다
        const insL = (num(cs.borderLeftWidth) + num(cs.paddingLeft)) * sx;
        const insR = (num(cs.borderRightWidth) + num(cs.paddingRight)) * sx;
        const insT = (num(cs.borderTopWidth) + num(cs.paddingTop)) * sy;
        const insB = (num(cs.borderBottomWidth) + num(cs.paddingBottom)) * sy;
        const fs = num(cs.fontSize) * sx;
        const lhRaw = cs.lineHeight;
        const lh = lhRaw === 'normal' ? null : num(lhRaw) * sy;
        boxes.push({
          text: text,
          runs: runs,
          tag: el.tagName,
          x: r.left - sr.left + insL,
          y: r.top - sr.top + insT,
          w: Math.max(1, r.width - insL - insR),
          h: Math.max(1, r.height - insT - insB),
          font_size_px: fs,
          font_weight: parseInt(cs.fontWeight, 10) || 400,
          font_family: cs.fontFamily,
          color: cs.color,
          text_align: cs.textAlign,
          line_height_px: lh,
          italic: cs.fontStyle === 'italic',
          opacity: +ac.op.toFixed(3),
          scale: +sx.toFixed(4),
          lines: lineCount(el, fs),
        });
        if (hide) hideGlyphs(el);
      }
    }
    for (const c of el.children) walk(c, ancestorPicked || picked);
  };

  walk(host, false);
  return {stage: {w: sr.width, h: sr.height}, boxes: boxes, skipped: skipped};
}
"""


def extract_text_boxes(
    session, t: float, *, hide: bool = False, min_opacity: float = MIN_OPACITY
) -> list[dict[str, Any]]:
    """t(초)로 seek 한 뒤 그 시각의 리프 텍스트 요소를 스테이지 좌표로 수집한다.

    hide=True 면 채택된 요소의 글자색을 투명으로 내려 곧바로 이어지는 capture()가
    텍스트 없는 배경이 되게 한다(숨김은 다음 호출 첫머리에 원복된다). 채택 술어와
    숨김 술어가 같은 통과에서 결정되므로 "뽑은 것만 정확히 사라진다".

    각 원소: text, runs, x/y/w/h(스테이지 px, 콘텐츠 상자), fx/fy/fw/fh(0~1 정규화),
    font_size_px, font_weight, font_family, color, text_align, line_height_px,
    lines, opacity, role. 부수적으로 session.last_text_skips 에 제외 사유가 남는다.
    """
    session.seek(t)
    res = session.page.evaluate(
        _COLLECT_JS,
        {"sel": EXPORTABLE_SVG, "hide": bool(hide), "minOpacity": float(min_opacity)},
    )
    if res is None:
        raise RuntimeError("스테이지 svg 를 찾지 못함 — export 계약 셀렉터 불일치")
    stage = res["stage"]
    sw = max(1.0, float(stage["w"]))
    sh = max(1.0, float(stage["h"]))
    boxes: list[dict[str, Any]] = []
    for b in res["boxes"]:
        b["fx"] = b["x"] / sw
        b["fy"] = b["y"] / sh
        b["fw"] = b["w"] / sw
        b["fh"] = b["h"] / sh
        b["role"] = classify_role(b, stage)
        boxes.append(b)
    session.last_text_stage = stage
    session.last_text_skips = res["skipped"]
    return boxes
