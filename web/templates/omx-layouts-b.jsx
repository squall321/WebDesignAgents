// 가로 16:9 데이터 배치 레이아웃 4종 — tpl.l-kpi(KPI 대시보드)·tpl.l-quad(4분면 매트릭스)·tpl.l-ba(Before/After 반반)·tpl.l-mix(표+차트 혼합). 실무 발표자료의 고밀도 배치 패턴.
// 계약: 엔진 props(localTime 등) + data + theme, 정적 .schedule(data)/.nat, frame-match(첫/끝 프레임 안정), 모든 모션은 t(localTime)의 순수 함수.
(function () {
  'use strict';
  var OMX = (window.OMX = window.OMX || {});
  var Easing = window.Easing;
  var animate = window.animate;
  var FrameChrome = OMX.metaphors['frame-chrome']; // 허용된 공통 크롬 (dot-grid 내장)

  // ── 마이크로 헬퍼 — 엔진 원자 animate 로만 재구성 ────────────────────
  function easeOf(name) { return (name && Easing[name]) || Easing.easeOutCubic; }
  function seg(t, at, dur, from, to, ease) {
    return animate({ from: from, to: to, start: at, end: at + dur, ease: ease || Easing.easeOutCubic })(t);
  }
  function enter(theme, t, at, dur, dy) {
    var m = theme.motion.rise;
    var d = dur == null ? m.dur : dur;
    var y = dy == null ? m.dy : dy;
    var e = easeOf(m.ease);
    return { opacity: seg(t, at, d, 0, 1, e), transform: 'translateY(' + seg(t, at, d, y, 0, e) + 'px)' };
  }
  function popIn(theme, t, at, dur) {
    var m = theme.motion.pop;
    var d = dur == null ? m.dur : dur;
    var v = seg(t, at, d, 0, 1, easeOf(m.ease));
    return { opacity: Math.min(1, v), transform: 'scale(' + v + ')' };
  }
  // 0~1 정규화 좌표 클램프 — 스키마 밖 경로(구 데이터·수기 편집)로 들어온 값도 무대 안에 가둔다
  function clamp01(v) {
    var n = Number(v);
    if (!(n === n)) return 0;      // NaN 방어 (isNaN 대체 — 순수 비교)
    return n < 0 ? 0 : (n > 1 ? 1 : n);
  }
  // 증감 색 규칙 — **방향(dir)은 글리프만 정하고 색은 평가(tone)가 정한다.**
  // "오류율 ▼ 62%" 는 감소(down)지만 평가는 good → 녹색이어야 한다. 방향으로 색을 정하면 틀린다.
  function deltaToneKey(delta) {
    var tone = delta && delta.tone;
    if (tone === 'good') return 'success';
    if (tone === 'bad') return 'error';
    return 'info';
  }
  function deltaGlyph(delta) {
    var dir = delta && delta.dir;
    if (dir === 'up') return '▲';
    if (dir === 'down') return '▼';
    return '■';
  }
  function chipTone(theme, key) {
    var c = theme.component.chip;
    if (key === 'success') return { bg: c.successBg, fg: c.successFg };
    if (key === 'error') return { bg: c.errorBg, fg: c.errorFg };
    if (key === 'accent') return { bg: c.accentBg, fg: c.accentFg };
    return { bg: c.infoBg, fg: c.infoFg };
  }
  // 항목 톤 — 점/막대의 채움(비텍스트)과 그 위 글자색을 같은 선언 페어로 묶는다
  function itemTone(theme, tone) {
    var c = theme.component.chip;
    if (tone === 'positive') return { bg: c.successBg, fg: c.successFg, line: theme.color.green };
    if (tone === 'caution') return { bg: c.errorBg, fg: c.errorFg, line: theme.color.red };
    if (tone === 'muted') return { bg: theme.color.typingBg, fg: theme.color.sub, line: theme.color.faint };
    return { bg: c.accentBg, fg: c.accentFg, line: theme.color.blue }; // primary
  }
  // 하단 중앙 풋노트 — {pre, strong, post}
  function LayoutNote(props) {
    var t = props.t, theme = props.theme, d = props.data;
    if (!d) return null;
    return (
      <div style={Object.assign({
        position: 'absolute', left: 0, right: 0, top: props.top, textAlign: 'center',
        fontSize: theme.type.body, color: theme.color.sub,
      }, enter(theme, t, props.at, 0.7, 16))}>
        {d.pre}{d.strong && <span style={{ fontWeight: 800, color: theme.color.ink }}>{d.strong}</span>}{d.post}
      </div>
    );
  }
  var FRAME_SCHED = [
    { id: 'kicker', kind: 'enter', at: 0.15, dur: 0.7, path: '/kicker' },
    { id: 'title', kind: 'enter', at: 0.35, dur: 0.7, path: '/title' },
  ];

  /* ══ tpl.l-kpi — KPI 대시보드 (은유: 계기판 점등 — 지표가 왼→오, 위→아래로 하나씩 불이 들어온다) ══
     등장 순서 = 읽는 순서: ① 타일 → ② 큰 수치 → ③ 증감 배지 → ④ 미니 스파크바 (지표별 반복) → ⑤ 풋노트.
     지표 4~6개를 2×2 / 3×2 그리드로. closing.stats 3개 상한이 못 담던 다지표 보고서를 위한 그릇.
     증감은 방향(▲▼)과 평가(good/bad/neutral)를 분리해 받는다 — 감소가 곧 나쁨이 아니다. */

  function kpiGeo(theme, n) {
    var L = theme.layout;
    var w = L.stageW - 2 * L.marginX;                 // 1640
    var gap = 32;
    var cols = n <= 4 ? 2 : 3;                        // 4개=2×2 · 5~6개=3×2
    return {
      x: L.marginX, y: L.contentTop, w: w, gap: gap, cols: cols,
      tileW: (w - (cols - 1) * gap) / cols,           // 3열 525.3 · 2열 804
      tileH: (592 - gap) / 2,                         // 280
      pad: 28,
    };
  }
  function kpiPlan(d) {
    var n = (d.metrics || []).length;
    var at = function (i) { return 1.1 + i * 0.45; };
    var last = at(Math.max(0, n - 1));
    return {
      count: n, at: at, dur: 0.6,
      valueDelay: 0.25, deltaDelay: 0.55, sparkDelay: 0.75, sparkStagger: 0.05,
      omitted: { at: last + 1.1, dur: 0.5 },
      note: { at: last + 1.5, dur: 0.7 },
    };
  }
  function KpiScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var metrics = d.metrics || [];
    var p = kpiPlan(d);
    var g = kpiGeo(theme, metrics.length);
    var card = theme.component.card;
    var innerW = g.tileW - 2 * g.pad;
    return (
      <FrameChrome label="지표" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {metrics.map(function (m, i) {
          var at = p.at(i);
          var col = i % g.cols, rowIdx = Math.floor(i / g.cols);
          var spark = m.spark || [];
          var sparkMax = 0;
          spark.forEach(function (v) { var n = Math.max(0, Number(v) || 0); if (n > sparkMax) sparkMax = n; });
          if (!(sparkMax > 0)) sparkMax = 1;
          var tone = chipTone(theme, deltaToneKey(m.delta));
          return (
            <div key={'m' + i} style={Object.assign({
              position: 'absolute',
              left: g.x + col * (g.tileW + g.gap),
              top: g.y + rowIdx * (g.tileH + g.gap),
              width: g.tileW, height: g.tileH, boxSizing: 'border-box',
              background: card.bg, border: '1px solid ' + card.border,
              borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
            }, enter(theme, t, at, p.dur, 20))}>
              {/* 라벨 — 무엇을 재는가 */}
              <div style={{
                position: 'absolute', left: g.pad, top: 28, width: innerW,
                fontSize: theme.type.body, fontWeight: 700, color: theme.color.sub,
                whiteSpace: 'nowrap', lineHeight: 1.2,
                opacity: seg(t, at + 0.1, 0.5, 0, 1),
              }}>{m.label}</div>
              {/* 큰 수치 + 단위 — 숫자와 단위를 분리해 폭 예산을 지킨다 */}
              <div style={Object.assign({
                position: 'absolute', left: g.pad, top: 70, width: innerW, height: 112,
                display: 'flex', alignItems: 'baseline', gap: 8,
              }, enter(theme, t, at + p.valueDelay, 0.6, 16))}>
                <div style={{
                  fontSize: theme.type.display, fontWeight: 800, color: theme.color.blue,
                  letterSpacing: '-0.03em', lineHeight: 1.2, whiteSpace: 'nowrap',
                }}>{m.value}</div>
                {m.unit && (
                  <div style={{
                    fontSize: theme.type.subtitle, fontWeight: 700, color: theme.color.sub,
                    lineHeight: 1.2, whiteSpace: 'nowrap',
                  }}>{m.unit}</div>
                )}
              </div>
              {/* 증감 배지 — 글리프는 방향, 색은 평가 */}
              {m.delta && (
                <div style={Object.assign({
                  position: 'absolute', left: g.pad, top: 186,
                  display: 'flex', alignItems: 'center', gap: 10,
                  background: tone.bg, color: tone.fg,
                  padding: '10px 18px', borderRadius: theme.radius.pill,
                  fontSize: theme.type.body, fontWeight: 800, lineHeight: 1.2, whiteSpace: 'nowrap',
                }, popIn(theme, t, at + p.deltaDelay))}>
                  <span>{deltaGlyph(m.delta)}</span>
                  <span>{m.delta.text}</span>
                </div>
              )}
              {/* 미니 스파크바 — 추세의 결(비텍스트 장식) */}
              {spark.length > 0 && (
                <div style={{
                  position: 'absolute', right: g.pad, top: 186, height: 48,
                  display: 'flex', alignItems: 'flex-end', gap: 6,
                }}>
                  {spark.map(function (v, k) {
                    var full = 12 + (Math.max(0, Number(v) || 0) / sparkMax) * 36;
                    var last = k === spark.length - 1;
                    return (
                      <div key={'s' + k} style={{
                        width: 10, borderRadius: 4, boxSizing: 'border-box',
                        height: seg(t, at + p.sparkDelay + k * p.sparkStagger, 0.45, 0, full),
                        background: last ? theme.color.blue : theme.color.blueSoft,
                        border: last ? 'none' : '1px solid ' + theme.color.blueBorder,
                      }}></div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
        {/* '외 N개' — 그리드 아래는 풋노트 자리라 타이틀 줄 오른쪽에 메타로 붙인다 */}
        {d.omitted != null && (
          <div style={{
            position: 'absolute', left: g.x, top: theme.layout.titleTop + 22, width: g.w,
            textAlign: 'right', fontSize: theme.type.body, fontWeight: 600,
            color: theme.color.faint,
            opacity: seg(t, p.omitted.at, p.omitted.dur, 0, 1),
          }}>…외 {d.omitted}개 지표</div>
        )}
        <LayoutNote t={t} theme={theme} data={d.note} top={theme.component.processNote.top} at={p.note.at} />
      </FrameChrome>
    );
  }
  KpiScene.nat = 11;
  KpiScene.schedule = function (d) {
    var p = kpiPlan(d);
    var metrics = d.metrics || [];
    var out = FRAME_SCHED.slice();
    for (var i = 0; i < p.count; i++) {
      out.push({ id: 'tile-' + i, kind: 'enter', at: p.at(i), dur: p.dur, path: '/metrics/' + i });
      out.push({ id: 'value-' + i, kind: 'enter', at: p.at(i) + p.valueDelay, dur: 0.6, path: '/metrics/' + i + '/value' });
      if (metrics[i] && metrics[i].delta) {
        out.push({ id: 'delta-' + i, kind: 'enter', at: p.at(i) + p.deltaDelay, dur: 0.45, path: '/metrics/' + i + '/delta' });
      }
      if (metrics[i] && (metrics[i].spark || []).length) {
        out.push({
          id: 'spark-' + i, kind: 'enter', at: p.at(i) + p.sparkDelay, dur: 0.45,
          stagger: p.sparkStagger, count: metrics[i].spark.length, path: '/metrics/' + i + '/spark',
        });
      }
    }
    if (d.omitted != null) out.push({ id: 'omitted', kind: 'enter', at: p.omitted.at, dur: p.omitted.dur, path: '/omitted' });
    if (d.note) out.push({ id: 'note', kind: 'enter', at: p.note.at, dur: p.note.dur, path: '/note' });
    return out;
  };

  /* ══ tpl.l-quad — 4분면 매트릭스 (은유: 좌표 위의 자리다툼 — 두 축이 그어지고 항목이 제 자리를 찾아 앉는다) ══
     등장 순서 = 논증 순서: ① 좌표판 → ② 두 축(끝 라벨) → ③ 사분면 이름 → ④ 항목이 번호순 착지
     (좌표판의 번호 점 ↔ 우측 범례의 같은 번호) → ⑤ 풋노트.
     좌표는 0~1 정규화, 범위 밖 값은 clamp01 로 판 안에 가둔다. 라벨 충돌을 피하려고 이름은 범례가 맡는다. */

  var QUAD_KEYS = ['tl', 'tr', 'bl', 'br'];
  function qdGeo(theme) {
    var L = theme.layout;
    var boardW = 1000, gap = 40;
    var padL = 110, padT = 52, padB = 52, padR = 32;
    return {
      board: { x: L.marginX, y: L.contentTop, w: boardW, h: 592 },
      legend: { x: L.marginX + boardW + gap, y: L.contentTop, w: L.stageW - 2 * L.marginX - boardW - gap, h: 592 },
      plotX: padL, plotY: padT,
      plotW: boardW - padL - padR,     // 858
      plotH: 592 - padT - padB,        // 488
      dot: 44, legendPad: 28,
    };
  }
  function qdPlan(d) {
    var n = (d.items || []).length;
    var at = function (i) { return 2.7 + i * 0.35; };
    var last = at(Math.max(0, n - 1)) + 0.5;
    return {
      count: n, at: at, dur: 0.5,
      board: { at: 0.9, dur: 0.7 },
      legendPanel: { at: 1.15, dur: 0.7 },
      axis: { at: 1.45, dur: 0.6 },
      quads: { at: 2.1, dur: 0.5, stagger: 0.12 },
      note: { at: last + 0.9, dur: 0.7 },
    };
  }
  function QuadScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var items = d.items || [];
    var q = d.quadrants || {};
    var ax = d.xAxis || {}, ay = d.yAxis || {};
    var p = qdPlan(d);
    var g = qdGeo(theme);
    var card = theme.component.card;
    var axisOp = seg(t, p.axis.at + 0.15, p.axis.dur, 0, 1);
    var legendPitch = Math.min(60, (g.legend.h - 2 * g.legendPad) / Math.max(1, items.length));
    var legendTop = (g.legend.h - legendPitch * items.length) / 2;
    // 사분면 사각형 (판 좌표계) — 강조 사분면 틴트와 라벨 앵커의 공통 원천
    function quadBox(key) {
      var halfW = g.plotW / 2, halfH = g.plotH / 2;
      return {
        x: g.plotX + (key === 'tr' || key === 'br' ? halfW : 0),
        y: g.plotY + (key === 'bl' || key === 'br' ? halfH : 0),
        w: halfW, h: halfH,
        right: key === 'tr' || key === 'br',
        bottom: key === 'bl' || key === 'br',
      };
    }
    return (
      <FrameChrome label="사분면" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {/* ── 좌표판 ── */}
        <div style={Object.assign({
          position: 'absolute', left: g.board.x, top: g.board.y, width: g.board.w, height: g.board.h,
          background: card.bg, border: '1px solid ' + card.border,
          borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
        }, enter(theme, t, p.board.at, p.board.dur))}>
          {/* 축 이름 — 가로/세로가 무엇을 재는지 한 줄로 */}
          <div style={{
            position: 'absolute', left: 24, top: 14,
            fontSize: theme.type.caption, fontWeight: 600, color: theme.color.faint,
            whiteSpace: 'nowrap', opacity: axisOp,
          }}>가로 · {ax.name}</div>
          <div style={{
            position: 'absolute', right: 24, top: 14,
            fontSize: theme.type.caption, fontWeight: 600, color: theme.color.faint,
            whiteSpace: 'nowrap', opacity: axisOp,
          }}>세로 · {ay.name}</div>
          {/* 강조 사분면 틴트 (비텍스트) */}
          {d.highlight && (function () {
            var b = quadBox(d.highlight);
            return (
              <div style={{
                position: 'absolute', left: b.x, top: b.y, width: b.w, height: b.h,
                background: theme.color.blueSoft, borderRadius: 12,
                opacity: seg(t, p.quads.at, 0.6, 0, 0.75),
              }}></div>
            );
          })()}
          {/* 축 — 바깥 테두리 + 중앙 십자 */}
          <div style={{
            position: 'absolute', left: g.plotX, top: g.plotY, width: g.plotW, height: g.plotH,
            border: '1px solid ' + theme.color.line, borderRadius: 12,
            opacity: axisOp,
          }}></div>
          <div style={{
            position: 'absolute', left: g.plotX, top: g.plotY + g.plotH / 2 - 1, height: 2,
            background: theme.color.blueBorder, transformOrigin: '0% 50%',
            width: g.plotW, transform: 'scaleX(' + seg(t, p.axis.at, p.axis.dur, 0, 1) + ')',
          }}></div>
          <div style={{
            position: 'absolute', left: g.plotX + g.plotW / 2 - 1, top: g.plotY, width: 2,
            background: theme.color.blueBorder, transformOrigin: '50% 0%',
            height: g.plotH, transform: 'scaleY(' + seg(t, p.axis.at + 0.1, p.axis.dur, 0, 1) + ')',
          }}></div>
          {/* 축 끝 라벨 — 세로(좌측 스트립) · 가로(하단 스트립) */}
          <div style={{
            position: 'absolute', left: 4, top: g.plotY - 2, width: 100, textAlign: 'right',
            fontSize: theme.type.caption, fontWeight: 700, color: theme.color.sub,
            whiteSpace: 'nowrap', opacity: axisOp,
          }}>{ay.high}</div>
          <div style={{
            position: 'absolute', left: 4, top: g.plotY + g.plotH - 28, width: 100, textAlign: 'right',
            fontSize: theme.type.caption, fontWeight: 700, color: theme.color.sub,
            whiteSpace: 'nowrap', opacity: axisOp,
          }}>{ay.low}</div>
          <div style={{
            position: 'absolute', left: g.plotX, top: g.plotY + g.plotH + 14, width: 200,
            fontSize: theme.type.caption, fontWeight: 700, color: theme.color.sub,
            whiteSpace: 'nowrap', opacity: axisOp,
          }}>{ax.low}</div>
          <div style={{
            position: 'absolute', left: g.plotX + g.plotW - 200, top: g.plotY + g.plotH + 14,
            width: 200, textAlign: 'right',
            fontSize: theme.type.caption, fontWeight: 700, color: theme.color.sub,
            whiteSpace: 'nowrap', opacity: axisOp,
          }}>{ax.high}</div>
          {/* 사분면 이름 — 네 모서리에 앵커 */}
          {QUAD_KEYS.map(function (key, k) {
            if (!q[key]) return null;
            var b = quadBox(key);
            var on = key === d.highlight;
            return (
              <div key={'q' + key} style={Object.assign({
                position: 'absolute', width: 260,
                left: b.right ? b.x + b.w - 274 : b.x + 14,
                top: b.bottom ? b.y + b.h - 44 : b.y + 14,
                textAlign: b.right ? 'right' : 'left',
                fontSize: theme.type.note, fontWeight: 800,
                color: on ? theme.color.blue : theme.color.faint,
                whiteSpace: 'nowrap',
              }, enter(theme, t, p.quads.at + k * p.quads.stagger, p.quads.dur, 10))}>{q[key]}</div>
            );
          })}
          {/* 항목 — 번호 점이 제 좌표에 착지 (0~1 밖 값은 clamp01 로 판 안에) */}
          {items.map(function (it, i) {
            var tone = itemTone(theme, it.tone);
            // 점 반지름만큼 안쪽으로 물려 배치 — 0/1 극단값도 판 테두리 안에 온전히 들어온다
            var inset = g.dot / 2 + 4;
            var cx = g.plotX + inset + clamp01(it.x) * (g.plotW - 2 * inset);
            var cy = g.plotY + inset + (1 - clamp01(it.y)) * (g.plotH - 2 * inset);
            return (
              <div key={'i' + i} style={Object.assign({
                position: 'absolute', left: cx - g.dot / 2, top: cy - g.dot / 2,
                width: g.dot, height: g.dot, boxSizing: 'border-box',
                borderRadius: theme.radius.pill,
                background: tone.bg, border: '2px solid ' + tone.line,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: theme.type.caption, fontWeight: 800, color: tone.fg, lineHeight: 1,
              }, popIn(theme, t, p.at(i), p.dur))}>{i + 1}</div>
            );
          })}
        </div>
        {/* ── 범례 — 번호 ↔ 이름 (좌표판의 라벨 충돌을 없앤다) ── */}
        <div style={Object.assign({
          position: 'absolute', left: g.legend.x, top: g.legend.y,
          width: g.legend.w, height: g.legend.h, boxSizing: 'border-box',
          background: card.bg, border: '1px solid ' + card.border,
          borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
        }, enter(theme, t, p.legendPanel.at, p.legendPanel.dur))}>
          {items.map(function (it, i) {
            var tone = itemTone(theme, it.tone);
            return (
              <div key={'l' + i} style={Object.assign({
                position: 'absolute', left: g.legendPad, top: legendTop + i * legendPitch,
                width: g.legend.w - 2 * g.legendPad, height: legendPitch,
                display: 'flex', alignItems: 'center', gap: 16,
              }, enter(theme, t, p.at(i) + 0.12, p.dur, 12))}>
                <div style={{
                  width: 40, height: 40, flexShrink: 0, boxSizing: 'border-box',
                  borderRadius: theme.radius.pill, background: tone.bg,
                  border: '2px solid ' + tone.line,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: theme.type.caption, fontWeight: 800, color: tone.fg, lineHeight: 1,
                }}>{i + 1}</div>
                <div style={{
                  fontSize: theme.type.note, fontWeight: 700, color: theme.color.ink,
                  whiteSpace: 'nowrap',
                }}>{it.label}</div>
              </div>
            );
          })}
        </div>
        <LayoutNote t={t} theme={theme} data={d.note} top={theme.component.processNote.top} at={p.note.at} />
      </FrameChrome>
    );
  }
  QuadScene.nat = 13;
  QuadScene.schedule = function (d) {
    var p = qdPlan(d);
    var out = FRAME_SCHED.concat([
      { id: 'board', kind: 'enter', at: p.board.at, dur: p.board.dur },
      { id: 'legend-panel', kind: 'enter', at: p.legendPanel.at, dur: p.legendPanel.dur },
      { id: 'axis', kind: 'enter', at: p.axis.at, dur: p.axis.dur + 0.2 },
      { id: 'quadrants', kind: 'enter', at: p.quads.at, dur: p.quads.dur, stagger: p.quads.stagger, count: 4, path: '/quadrants' },
    ]);
    for (var i = 0; i < p.count; i++) {
      out.push({ id: 'item-' + i, kind: 'enter', at: p.at(i), dur: p.dur, path: '/items/' + i });
      out.push({ id: 'legend-' + i, kind: 'enter', at: p.at(i) + 0.12, dur: p.dur, path: '/items/' + i + '/label' });
    }
    if (d.note) out.push({ id: 'note', kind: 'enter', at: p.note.at, dur: p.note.dur, path: '/note' });
    return out;
  };

  /* ══ tpl.l-ba — Before/After 반반 화면 (은유: 강을 건너기 — 왼 기슭에서 오른 기슭으로) ══
     등장 순서 = 전환의 서사: ① 좌(AS-IS) 패널·칩·제목·항목·요약 → ② 중앙 화살표 → ③ 개선폭 배지
     → ④ 우(TO-BE) 패널이 같은 순서로 → ⑤ 풋노트.
     tpl.compare(행 짝 비교)와 다르다 — 이건 **전체 상태 대비**다. 화면을 x=960 에서 정확히 반으로 가른다. */

  function baGeo(theme) {
    var L = theme.layout;
    var half = L.stageW / 2;                          // 960 — 화면의 정확한 절반
    var panelW = 740, band = 160;
    return {
      half: half, y: L.contentTop, h: 592, panelW: panelW, pad: 36,
      leftX: L.marginX,                               // 140 .. 880
      rightX: half + band / 2,                        // 1040 .. 1780
      chipTop: 32, titleTop: 96, titleH: 88, ruleTop: 200,
      itemsTop: 220, itemPitch: 40,
      sumTop: 444, sumH: 112,
      arrowY: L.contentTop + 300, badgeY: L.contentTop + 410,
    };
  }
  function baPlan(d) {
    var bn = ((d.before || {}).items || []).length;
    var an = ((d.after || {}).items || []).length;
    var side = function (base, n) {
      return {
        panel: base, chip: base + 0.4, title: base + 0.6,
        items: base + 1.0, stagger: 0.35, count: n,
        summary: base + 1.0 + Math.max(0, n - 1) * 0.35 + 0.55,
      };
    };
    var before = side(0.9, bn);
    var arrow = before.summary + 0.9;
    var badge = arrow + 0.5;
    var after = side(badge + 0.45, an);
    return {
      before: before, after: after, dur: 0.6,
      arrow: { at: arrow, dur: 0.6 }, badge: { at: badge, dur: 0.5 },
      note: { at: after.summary + 1.1, dur: 0.7 },
    };
  }
  function BaPanel(props) {
    var t = props.t, theme = props.theme, d = props.data || {}, s = props.plan, g = props.geo;
    var card = theme.component.card;
    var tone = chipTone(theme, props.toneKey);
    var innerW = g.panelW - 2 * g.pad;
    var sum = d.summary || {};
    return (
      <div style={Object.assign({
        position: 'absolute', left: props.x, top: g.y, width: g.panelW, height: g.h,
        boxSizing: 'border-box',
        background: card.bg, border: '1px solid ' + card.border,
        borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
      }, enter(theme, t, s.panel, props.dur))}>
        <div style={Object.assign({
          position: 'absolute', left: g.pad, top: g.chipTop,
          background: tone.bg, color: tone.fg,
          padding: '10px 20px', borderRadius: theme.radius.pill,
          fontSize: theme.type.body, fontWeight: 800, lineHeight: 1.2, whiteSpace: 'nowrap',
        }, popIn(theme, t, s.chip))}>{d.label}</div>
        <div style={Object.assign({
          position: 'absolute', left: g.pad, top: g.titleTop, width: innerW, height: g.titleH,
          fontSize: theme.type.cardTitle, fontWeight: 800, color: theme.color.ink,
          lineHeight: 1.28, letterSpacing: '-0.01em', overflowWrap: 'anywhere',
        }, enter(theme, t, s.title, props.dur, 14))}>{d.title}</div>
        <div style={{
          position: 'absolute', left: g.pad, top: g.ruleTop, height: 1,
          background: theme.color.line, transformOrigin: '0% 50%',
          width: innerW, transform: 'scaleX(' + seg(t, s.title + 0.2, 0.6, 0, 1) + ')',
        }}></div>
        {(d.items || []).map(function (it, i) {
          return (
            <div key={'it' + i} style={Object.assign({
              position: 'absolute', left: g.pad, top: g.itemsTop + i * g.itemPitch,
              width: innerW, height: g.itemPitch,
              display: 'flex', alignItems: 'center', gap: 14,
            }, enter(theme, t, s.items + i * s.stagger, props.dur, 12))}>
              <div style={{
                width: 10, height: 10, flexShrink: 0, borderRadius: 3, background: tone.fg,
              }}></div>
              <div style={{
                fontSize: theme.type.note, fontWeight: 600, color: theme.color.ink,
                whiteSpace: 'nowrap', lineHeight: 1.3,
              }}>{it.text}</div>
            </div>
          );
        })}
        <div style={Object.assign({
          position: 'absolute', left: g.pad, top: g.sumTop, width: innerW, height: g.sumH,
          display: 'flex', alignItems: 'baseline', gap: 20,
        }, enter(theme, t, s.summary, props.dur, 18))}>
          <div style={{
            fontSize: theme.type.display, fontWeight: 800, lineHeight: 1.2,
            letterSpacing: '-0.03em', whiteSpace: 'nowrap',
            color: props.accent ? theme.color.blue : theme.color.sub,
          }}>{sum.value}</div>
          <div style={{
            fontSize: theme.type.body, fontWeight: 700, color: theme.color.sub,
            whiteSpace: 'nowrap', lineHeight: 1.2,
          }}>{sum.desc}</div>
        </div>
      </div>
    );
  }
  function BaScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = baPlan(d);
    var g = baGeo(theme);
    var dec = theme.component.decision;
    return (
      <FrameChrome label="대비" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {/* 정확히 절반을 가르는 세로선 */}
        <div style={{
          position: 'absolute', left: g.half - 0.5, top: g.y, width: 1,
          background: theme.color.line, transformOrigin: '50% 0%',
          height: g.h, transform: 'scaleY(' + seg(t, p.before.panel, 0.8, 0, 1) + ')',
        }}></div>
        <BaPanel t={t} theme={theme} data={d.before} plan={p.before} geo={g}
                 x={g.leftX} toneKey="error" dur={p.dur} accent={false} />
        <BaPanel t={t} theme={theme} data={d.after} plan={p.after} geo={g}
                 x={g.rightX} toneKey="accent" dur={p.dur} accent={true} />
        {/* 전환 화살표 — 좌에서 우로 */}
        <div style={Object.assign({
          position: 'absolute', left: g.half - 40, top: g.arrowY, width: 80, textAlign: 'center',
          fontSize: theme.type.arrow, fontWeight: 800, color: theme.color.blue, lineHeight: 1.2,
        }, enter(theme, t, p.arrow.at, p.arrow.dur, 0))}>→</div>
        {/* 개선폭 배지 — 두 기슭을 잇는 다리 */}
        {d.gain && (
          <div style={Object.assign({
            position: 'absolute', left: 0, right: 0, top: g.badgeY,
            display: 'flex', justifyContent: 'center',
          }, popIn(theme, t, p.badge.at))}>
            <div style={{
              background: dec.bg, color: dec.fg, boxShadow: dec.shadow,
              padding: '12px 22px', borderRadius: theme.radius.pill,
              fontSize: theme.type.lead, fontWeight: 800, lineHeight: 1.2, whiteSpace: 'nowrap',
            }}>{d.gain}</div>
          </div>
        )}
        <LayoutNote t={t} theme={theme} data={d.note} top={theme.component.processNote.top} at={p.note.at} />
      </FrameChrome>
    );
  }
  BaScene.nat = 14;
  BaScene.schedule = function (d) {
    var p = baPlan(d);
    var out = FRAME_SCHED.slice();
    [['before', p.before], ['after', p.after]].forEach(function (pair) {
      var key = pair[0], s = pair[1];
      out.push({ id: key + '-panel', kind: 'enter', at: s.panel, dur: p.dur, path: '/' + key });
      out.push({ id: key + '-label', kind: 'enter', at: s.chip, dur: 0.45, path: '/' + key + '/label' });
      out.push({ id: key + '-title', kind: 'enter', at: s.title, dur: p.dur, path: '/' + key + '/title' });
      if (s.count > 0) {
        out.push({ id: key + '-items', kind: 'enter', at: s.items, dur: p.dur, stagger: s.stagger, count: s.count, path: '/' + key + '/items' });
      }
      out.push({ id: key + '-summary', kind: 'enter', at: s.summary, dur: p.dur, path: '/' + key + '/summary' });
      if (key === 'before') {
        out.push({ id: 'arrow', kind: 'enter', at: p.arrow.at, dur: p.arrow.dur });
        if (d.gain) out.push({ id: 'gain', kind: 'enter', at: p.badge.at, dur: p.badge.dur, path: '/gain' });
      }
    });
    if (d.note) out.push({ id: 'note', kind: 'enter', at: p.note.at, dur: p.note.dur, path: '/note' });
    return out;
  };

  /* ══ tpl.l-mix — 표 + 차트 혼합 (은유: 같은 사실의 두 얼굴 — 숫자로 읽고 길이로 본다) ══
     등장 순서 = 읽는 순서: ① 요약 띠(수치 3개 또는 한 줄 결론) → ② 표(헤더 → 행) → ③ 막대 → ④ 풋노트.
     상단 40% 요약 · 하단 60% 좌표(좌 간이표 4열×5행 / 우 막대 4개). structured table 과 series 를
     **동시에** 받는 유일한 템플릿 — 라벨이 겹치는 행과 막대는 같은 수치를 가리켜야 한다. */

  function mxGeo(theme) {
    var L = theme.layout;
    var w = L.stageW - 2 * L.marginX;                 // 1640
    var topH = 226, gap = 24, botH = 342;             // 226 + 24 + 342 = 592
    var tableW = 940, chartGap = 40;
    return {
      x: L.marginX, y: L.contentTop, w: w,
      top: { x: L.marginX, y: L.contentTop, w: w, h: topH },
      bot: { y: L.contentTop + topH + gap, h: botH },
      table: { x: L.marginX, w: tableW },
      chart: { x: L.marginX + tableW + chartGap, w: w - tableW - chartGap },  // 660
      pad: 24, firstColW: 380, headerH: 50, rowsTop: 66,
      barPitch: 73.5, barTrackH: 26,
    };
  }
  function mxPlan(d) {
    var stats = (d.stats || []);
    var rows = ((d.table || {}).rows || []);
    var bars = ((d.chart || {}).bars || []);
    var rowsAt = 3.0, rowStagger = 0.4;
    var rowsSettle = rowsAt + Math.max(0, rows.length - 1) * rowStagger + 0.55;
    var barsAt = rowsSettle + 0.5, barStagger = 0.4;
    var barsSettle = barsAt + Math.max(0, bars.length - 1) * barStagger + 0.8;
    return {
      statCount: stats.length, rowCount: rows.length, barCount: bars.length,
      topPanel: { at: 0.9, dur: 0.7 },
      stats: { at: 1.3, dur: 0.6, stagger: 0.3 },
      lead: { at: 1.3, dur: 0.7 },
      tablePanel: { at: 2.2, dur: 0.7 },
      header: { at: 2.6, dur: 0.5, stagger: 0.08 },
      rows: { at: rowsAt, dur: 0.55, stagger: rowStagger },
      chartPanel: { at: 2.45, dur: 0.7 },
      bars: { at: barsAt, dur: 0.8, stagger: barStagger },
      note: { at: barsSettle + 0.4, dur: 0.7 },
    };
  }
  function MixScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = mxPlan(d);
    var g = mxGeo(theme);
    var card = theme.component.card;
    var tbl = d.table || {};
    var cols = tbl.columns || [];
    var rows = tbl.rows || [];
    var chart = d.chart || {};
    var bars = chart.bars || [];
    var stats = d.stats || [];
    var dataColW = (g.table.w - 2 * g.pad - g.firstColW) / Math.max(1, cols.length - 1);
    var rowH = rows.length ? (g.bot.h - g.rowsTop - 16) / rows.length : 0;
    var barMax = 0;
    bars.forEach(function (b) { var v = Math.max(0, Number(b.value) || 0); if (v > barMax) barMax = v; });
    if (chart.axisMax != null) barMax = Math.max(barMax, Number(chart.axisMax) || 0);
    if (!(barMax > 0)) barMax = 1;
    var trackW = g.chart.w - 2 * g.pad;               // 612
    var statW = (g.top.w - 2 * g.pad) / Math.max(1, stats.length);
    return (
      <FrameChrome label="혼합" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {/* ── 상단 40% — 요약 수치 또는 한 줄 결론 ── */}
        <div style={Object.assign({
          position: 'absolute', left: g.top.x, top: g.top.y, width: g.top.w, height: g.top.h,
          boxSizing: 'border-box',
          background: card.bg, border: '1px solid ' + card.border,
          borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
        }, enter(theme, t, p.topPanel.at, p.topPanel.dur))}>
          {stats.map(function (s, i) {
            return (
              <div key={'st' + i} style={Object.assign({
                position: 'absolute', left: g.pad + i * statW, top: 38, width: statW,
                textAlign: 'center',
              }, enter(theme, t, p.stats.at + i * p.stats.stagger, p.stats.dur, 18))}>
                <div style={{
                  display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: 8,
                }}>
                  <div style={{
                    fontSize: theme.type.display, fontWeight: 800, color: theme.color.blue,
                    letterSpacing: '-0.03em', lineHeight: 1.2, whiteSpace: 'nowrap',
                  }}>{s.value}</div>
                  {s.unit && (
                    <div style={{
                      fontSize: theme.type.subtitle, fontWeight: 700, color: theme.color.sub,
                      lineHeight: 1.2, whiteSpace: 'nowrap',
                    }}>{s.unit}</div>
                  )}
                </div>
                <div style={{
                  marginTop: 10, fontSize: theme.type.body, fontWeight: 700, color: theme.color.sub,
                  whiteSpace: 'nowrap', lineHeight: 1.2,
                }}>{s.label}</div>
              </div>
            );
          })}
          {d.lead && (
            <div style={Object.assign({
              position: 'absolute', left: g.pad, top: 0, width: g.top.w - 2 * g.pad, height: g.top.h,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: theme.type.claim, fontWeight: 800, color: theme.color.ink,
              lineHeight: 1.35, textAlign: 'center', overflowWrap: 'anywhere',
            }, enter(theme, t, p.lead.at, p.lead.dur, 16))}>{d.lead}</div>
          )}
        </div>
        {/* ── 하단 좌 60% — 간이표 ── */}
        <div style={Object.assign({
          position: 'absolute', left: g.table.x, top: g.bot.y, width: g.table.w, height: g.bot.h,
          boxSizing: 'border-box',
          background: card.bg, border: '1px solid ' + card.border,
          borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
        }, enter(theme, t, p.tablePanel.at, p.tablePanel.dur))}>
          {cols.map(function (c, j) {
            return (
              <div key={'h' + j} style={{
                position: 'absolute', top: 16, height: g.headerH,
                left: j === 0 ? g.pad + 12 : g.pad + g.firstColW + (j - 1) * dataColW,
                width: j === 0 ? g.firstColW - 24 : dataColW,
                display: 'flex', alignItems: 'center',
                justifyContent: j === 0 ? 'flex-start' : 'center',
                fontSize: theme.type.caption, fontWeight: 800, color: theme.color.sub,
                whiteSpace: 'nowrap', lineHeight: 1.2,
                opacity: seg(t, p.header.at + j * p.header.stagger, p.header.dur, 0, 1),
              }}>{c.label}</div>
            );
          })}
          <div style={{
            position: 'absolute', left: g.pad, top: 16 + g.headerH, height: 2,
            background: theme.color.sub, opacity: 0.55, transformOrigin: '0% 50%',
            width: g.table.w - 2 * g.pad,
            transform: 'scaleX(' + seg(t, p.header.at + 0.2, 0.6, 0, 1) + ')',
          }}></div>
          {rows.map(function (r, i) {
            var at = p.rows.at + i * p.rows.stagger;
            return (
              <div key={'r' + i} style={Object.assign({
                position: 'absolute', left: g.pad, top: g.rowsTop + i * rowH,
                width: g.table.w - 2 * g.pad, height: rowH, boxSizing: 'border-box',
                background: i % 2 === 1 ? theme.color.bg : 'transparent', borderRadius: 10,
              }, enter(theme, t, at, p.rows.dur, 12))}>
                <div style={{
                  position: 'absolute', left: 12, top: 0, height: '100%', width: g.firstColW - 24,
                  display: 'flex', alignItems: 'center',
                  fontSize: theme.type.caption, fontWeight: 700, color: theme.color.ink,
                  whiteSpace: 'nowrap', lineHeight: 1.25,
                }}>{r.label}</div>
                {(r.cells || []).slice(0, Math.max(0, cols.length - 1)).map(function (cell, k) {
                  return (
                    <div key={'c' + k} style={{
                      position: 'absolute', left: g.firstColW + k * dataColW, top: 0,
                      width: dataColW, height: '100%',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      fontSize: theme.type.caption, lineHeight: 1.25, whiteSpace: 'nowrap',
                      fontWeight: cell.em ? 800 : 600,
                      color: cell.em ? theme.color.blue : theme.color.ink,
                      opacity: seg(t, at + 0.1 + k * 0.07, 0.4, 0, 1),
                    }}>{cell.v}</div>
                  );
                })}
              </div>
            );
          })}
        </div>
        {/* ── 하단 우 40% — 같은 데이터의 막대 표현 ── */}
        <div style={Object.assign({
          position: 'absolute', left: g.chart.x, top: g.bot.y, width: g.chart.w, height: g.bot.h,
          boxSizing: 'border-box',
          background: card.bg, border: '1px solid ' + card.border,
          borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
        }, enter(theme, t, p.chartPanel.at, p.chartPanel.dur))}>
          {bars.map(function (b, i) {
            var at = p.bars.at + i * p.bars.stagger;
            var full = (Math.max(0, Number(b.value) || 0) / barMax) * (trackW - 2); // 트랙 테두리 안쪽
            var em = !!b.em;
            return (
              <div key={'b' + i} style={Object.assign({
                position: 'absolute', left: g.pad, top: g.pad + i * g.barPitch,
                width: trackW, height: 66,
              }, enter(theme, t, at, 0.5, 12))}>
                {/* 라벨·판독값은 고정 폭 — flex 수축으로 글자가 잘리는 경로를 막는다 */}
                <div style={{
                  position: 'absolute', left: 0, top: 0, width: trackW - 166,
                  fontSize: theme.type.caption, fontWeight: 700, color: theme.color.ink,
                  whiteSpace: 'nowrap', lineHeight: 1.25,
                }}>{b.label}</div>
                <div style={{
                  position: 'absolute', right: 0, top: 0, width: 150, textAlign: 'right',
                  fontSize: theme.type.caption, fontWeight: 800, whiteSpace: 'nowrap',
                  lineHeight: 1.25, color: em ? theme.color.blue : theme.color.sub,
                }}>{b.display}</div>
                <div style={{
                  position: 'absolute', left: 0, top: 40, width: trackW, height: g.barTrackH,
                  background: theme.color.blueSoft, borderRadius: theme.radius.bar,
                  boxSizing: 'border-box', border: '1px solid ' + theme.color.blueBorder,
                }}>
                  <div style={{
                    position: 'absolute', left: 0, top: 0, height: '100%',
                    width: seg(t, at + 0.1, p.bars.dur, 0, full),
                    background: em ? theme.color.blue : theme.color.blue2,
                    borderRadius: theme.radius.bar,
                  }}></div>
                </div>
              </div>
            );
          })}
        </div>
        <LayoutNote t={t} theme={theme} data={d.note} top={theme.component.processNote.top} at={p.note.at} />
      </FrameChrome>
    );
  }
  MixScene.nat = 15;
  MixScene.schedule = function (d) {
    var p = mxPlan(d);
    var out = FRAME_SCHED.concat([
      { id: 'top-panel', kind: 'enter', at: p.topPanel.at, dur: p.topPanel.dur },
    ]);
    if (p.statCount > 0) {
      out.push({ id: 'stats', kind: 'enter', at: p.stats.at, dur: p.stats.dur, stagger: p.stats.stagger, count: p.statCount, path: '/stats' });
    }
    if (d.lead) out.push({ id: 'lead', kind: 'enter', at: p.lead.at, dur: p.lead.dur, path: '/lead' });
    out.push({ id: 'table-panel', kind: 'enter', at: p.tablePanel.at, dur: p.tablePanel.dur });
    out.push({ id: 'table-header', kind: 'enter', at: p.header.at, dur: p.header.dur, stagger: p.header.stagger, count: ((d.table || {}).columns || []).length, path: '/table/columns' });
    for (var i = 0; i < p.rowCount; i++) {
      out.push({ id: 'row-' + i, kind: 'enter', at: p.rows.at + i * p.rows.stagger, dur: p.rows.dur, path: '/table/rows/' + i });
    }
    out.push({ id: 'chart-panel', kind: 'enter', at: p.chartPanel.at, dur: p.chartPanel.dur });
    for (var k = 0; k < p.barCount; k++) {
      out.push({ id: 'bar-' + k, kind: 'enter', at: p.bars.at + k * p.bars.stagger, dur: p.bars.dur + 0.1, path: '/chart/bars/' + k });
    }
    if (d.note) out.push({ id: 'note', kind: 'enter', at: p.note.at, dur: p.note.dur, path: '/note' });
    return out;
  };

  OMX.templates = Object.assign(OMX.templates || {}, {
    KpiScene: KpiScene,
    QuadScene: QuadScene,
    BaScene: BaScene,
    MixScene: MixScene,
  });
  OMX.templateIndex = Object.assign(OMX.templateIndex || {}, {
    'tpl.l-kpi': KpiScene,
    'tpl.l-quad': QuadScene,
    'tpl.l-ba': BaScene,
    'tpl.l-mix': MixScene,
  });
  // 수치 정확성 규칙의 시험 좌석 — 클램프와 증감 색 규칙은 순수 함수라 단독으로 검증한다
  OMX.layoutsB = Object.assign(OMX.layoutsB || {}, {
    clamp01: clamp01,
    deltaToneKey: deltaToneKey,
    deltaGlyph: deltaGlyph,
  });
})();
