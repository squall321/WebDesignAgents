// 창작 모드 위젯 수용 씬 템플릿 3종 — tpl.d-matrix(격자 표)·tpl.d-media(도판 쇼케이스)·tpl.d-multi(다계열 그룹 막대). 실물 규모(§8: raci 6열×8행·이미지 3장·다계열 7항목)를 담는 그릇.
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
  function niceCeil(v) {
    if (!(v > 0)) return 1;
    var pow = Math.pow(10, Math.floor(Math.log(v) / Math.LN10));
    var m = v / pow;
    var steps = [1, 1.2, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10];
    for (var i = 0; i < steps.length; i++) if (m <= steps[i] + 1e-9) return steps[i] * pow;
    return 10 * pow;
  }
  function fmtNum(v) {
    var r = Math.round(v * 10) / 10;
    return Math.abs(r - Math.round(r)) < 1e-9 ? String(Math.round(r)) : r.toFixed(1);
  }
  // 하단 중앙 풋노트 — {pre, strong, post}
  function DataNote(props) {
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

  /* ══ tpl.d-matrix — 격자 표 (은유: 대장(臺帳) 펼치기 — 헤더가 먼저 서고 행이 읽는 순서로 쌓인다) ══
     등장 순서 = 읽는 순서: ① 패널 → ② 헤더 행(열 이름 좌→우) → ③ 데이터 행이
     위→아래 순차 등장(행 안에서는 라벨→셀 좌→우 스윕) → ④ '외 N행' → ⑤ 풋노트.
     코드값(R/A 등)은 칩으로, 강조 셀(em)은 활성 칩/청색 강조. 초과분은 스키마가 자르고 omitted 로 표기. */

  function mxGeo(theme, C) {
    var L = theme.layout;
    var w = L.stageW - 2 * L.marginX;                       // 1640
    var pad = 24, firstColW = 430;
    return {
      x: L.marginX, y: L.contentTop, w: w, h: 592,
      pad: pad, firstColW: firstColW,
      colW: (w - 2 * pad - firstColW) / Math.max(1, C - 1), // 8열 시 166px
      headerH: 68, rowsTop: 76,
      rowsH: 592 - 76 - 4,
    };
  }
  function mxPlan(d) {
    var C = (d.columns || []).length;
    var n = (d.rows || []).length;
    var rowAt = function (i) { return 2.2 + i * 0.5; };
    var lastSettle = rowAt(Math.max(0, n - 1)) + 0.55 + Math.max(0, C - 2) * 0.06;
    return {
      cols: C, count: n, rowAt: rowAt, rowDur: 0.55, cellStagger: 0.06,
      panel: { at: 0.9, dur: 0.7 },
      header: { at: 1.5, dur: 0.5, stagger: 0.08 },
      rule: { at: 1.75, dur: 0.6 },
      omitted: { at: lastSettle + 0.45, dur: 0.5 },
      note: { at: lastSettle + 1.0, dur: 0.7 },
    };
  }
  function MatrixScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var cols = d.columns || [];
    var rows = d.rows || [];
    var C = cols.length;
    var p = mxPlan(d);
    var g = mxGeo(theme, C);
    var rowH = g.rowsH / Math.max(1, rows.length);
    var card = theme.component.card;
    var chip = theme.component.chip;
    function colLeft(j) { return g.firstColW + (j - 1) * g.colW; } // 패널 pad 기준 (j>=1)
    function headerCell(c, j) {
      var at = p.header.at + j * p.header.stagger;
      return (
        <div key={'h' + j} style={{
          position: 'absolute', top: 0, height: g.headerH,
          left: j === 0 ? g.pad + 12 : g.pad + colLeft(j),
          width: j === 0 ? g.firstColW - 24 : g.colW,
          display: 'flex', alignItems: 'center',
          justifyContent: j === 0 ? 'flex-start' : 'center',
          textAlign: j === 0 ? 'left' : 'center',
          fontSize: theme.type.caption, fontWeight: 800, color: theme.color.sub,
          lineHeight: 1.2, overflowWrap: 'anywhere',
          opacity: seg(t, at, p.header.dur, 0, 1),
          transform: 'translateY(' + seg(t, at, p.header.dur, -8, 0) + 'px)',
        }}>{c.label}</div>
      );
    }
    function cellNode(cell, j, at0) {
      var op = seg(t, at0 + 0.1 + j * p.cellStagger, 0.4, 0, 1);
      var base = {
        position: 'absolute', left: colLeft(j), top: 0, width: g.colW, height: '100%',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      };
      if (cell.chip) {
        var tone = cell.em
          ? { bg: chip.activeBg, fg: chip.activeFg }
          : { bg: chip.accentBg, fg: chip.accentFg };
        return (
          <div key={'c' + j} style={base}>
            <div style={{
              background: tone.bg, color: tone.fg, fontSize: theme.type.caption,
              fontWeight: 800, lineHeight: 1, padding: '8px 16px',
              borderRadius: theme.radius.pill, whiteSpace: 'nowrap',
              boxShadow: cell.em ? theme.shadow.blueSoft : 'none',
              opacity: op,
            }}>{cell.v}</div>
          </div>
        );
      }
      return (
        <div key={'c' + j} style={Object.assign({}, base, {
          fontSize: theme.type.caption, lineHeight: 1.25, textAlign: 'center',
          overflowWrap: 'anywhere', padding: '0 8px', boxSizing: 'border-box',
          fontWeight: cell.em ? 800 : 600,
          color: cell.em ? theme.color.blue : theme.color.ink,
          opacity: op,
        })}>{cell.v}</div>
      );
    }
    return (
      <FrameChrome label="격자" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {/* ── 표 패널 ── */}
        <div style={Object.assign({
          position: 'absolute', left: g.x, top: g.y, width: g.w, height: g.h,
          background: card.bg, border: '1px solid ' + card.border,
          borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
        }, enter(theme, t, p.panel.at, p.panel.dur))}>
          {/* 헤더 행 (고정) */}
          {cols.map(headerCell)}
          {/* 헤더 밑줄 — 표의 등뼈 */}
          <div style={{
            position: 'absolute', left: g.pad, top: g.headerH, height: 2,
            background: theme.color.sub, opacity: 0.55,
            width: seg(t, p.rule.at, p.rule.dur, 0, g.w - 2 * g.pad),
          }}></div>
          {/* 열 가이드 (비텍스트 장식) */}
          {cols.slice(1).map(function (_, k) {
            return (
              <div key={'g' + k} style={{
                position: 'absolute', left: g.pad + colLeft(k + 1), top: 14,
                width: 1, height: g.h - 28, background: theme.color.line,
                transformOrigin: '50% 0%',
                transform: 'scaleY(' + seg(t, p.header.at + k * 0.05, 0.6, 0, 1) + ')',
              }}></div>
            );
          })}
          {/* 데이터 행 — 위→아래 순차, 행 안은 라벨→셀 스윕 */}
          {rows.map(function (r, i) {
            var at0 = p.rowAt(i);
            return (
              <div key={'r' + i} style={Object.assign({
                position: 'absolute', left: g.pad, top: g.rowsTop + i * rowH,
                width: g.w - 2 * g.pad, height: rowH, boxSizing: 'border-box',
                background: i % 2 === 1 ? theme.color.bg : 'transparent',
                borderRadius: 10,
                borderTop: i > 0 ? '1px solid ' + theme.color.line : 'none',
              }, enter(theme, t, at0, p.rowDur, 14))}>
                <div style={{
                  position: 'absolute', left: 12, top: 0, height: '100%',
                  width: g.firstColW - 24, display: 'flex', alignItems: 'center',
                  fontSize: theme.type.caption, fontWeight: 700, color: theme.color.ink,
                  lineHeight: 1.25, overflowWrap: 'anywhere',
                }}>{r.label}</div>
                {(r.cells || []).slice(0, Math.max(0, C - 1)).map(function (cell, k) {
                  return cellNode(cell, k + 1, at0);
                })}
              </div>
            );
          })}
        </div>
        {/* '외 N행' — 스키마가 자른 잔여 행 표기 */}
        {d.omitted != null && (
          <div style={{
            position: 'absolute', left: g.x, top: g.y + g.h + 12, width: g.w,
            textAlign: 'right', fontSize: theme.type.caption, fontWeight: 600,
            color: theme.color.faint,
            opacity: seg(t, p.omitted.at, p.omitted.dur, 0, 1),
          }}>…외 {d.omitted}행</div>
        )}
        <DataNote t={t} theme={theme} data={d.note} top={theme.component.processNote.top} at={p.note.at} />
      </FrameChrome>
    );
  }
  MatrixScene.nat = 12;
  MatrixScene.schedule = function (d) {
    var p = mxPlan(d);
    var out = FRAME_SCHED.concat([
      { id: 'panel', kind: 'enter', at: p.panel.at, dur: p.panel.dur },
      { id: 'header', kind: 'enter', at: p.header.at, dur: p.header.dur, stagger: p.header.stagger, count: p.cols, path: '/columns' },
      { id: 'rule', kind: 'enter', at: p.rule.at, dur: p.rule.dur },
    ]);
    for (var i = 0; i < p.count; i++) {
      out.push({
        id: 'row-' + i, kind: 'enter', at: p.rowAt(i), dur: p.rowDur,
        stagger: p.cellStagger, count: Math.max(1, p.cols - 1), path: '/rows/' + i,
      });
    }
    if (d.omitted != null) {
      out.push({ id: 'omitted', kind: 'enter', at: p.omitted.at, dur: p.omitted.dur, path: '/omitted' });
    }
    if (d.note) {
      out.push({ id: 'note', kind: 'enter', at: p.note.at, dur: p.note.dur, path: '/note' });
    }
    return out;
  };

  /* ══ tpl.d-media — 도판 쇼케이스 (은유: 전시대 조명 — 액자가 페이드로 걸리고 초점이 서서히 맞는다) ══
     1장=전면 · 2장=대비 · 3장=그리드. 등장은 스케일+페이드(카드 페이드 + 이미지 1.06→1 정착).
     종횡비는 object-fit: cover 로 보존(레터박스 금지 — 잘림은 카드 안전 영역 안에서만). */

  function mdGeo(theme, n) {
    var L = theme.layout;
    var w = L.stageW - 2 * L.marginX;                        // 1640
    var gap = 40;
    return {
      x: L.marginX, y: L.contentTop, gap: gap,
      cardW: (w - Math.max(0, n - 1) * gap) / Math.max(1, n), // 1장 1640 · 2장 800 · 3장 520
      cardH: 560, imgH: 464, capH: 96,
    };
  }
  function mdPlan(d) {
    var n = (d.files || []).length;
    var at = function (i) { return 1.0 + i * 0.75; };
    var last = at(Math.max(0, n - 1));
    return {
      count: n, at: at, dur: 0.7,
      capDelay: 0.35, capDur: 0.5, badgeDelay: 0.5,
      note: { at: last + 1.2, dur: 0.7 },
    };
  }
  function MediaScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var files = d.files || [];
    var p = mdPlan(d);
    var g = mdGeo(theme, files.length);
    var card = theme.component.card;
    var chip = theme.component.chip;
    return (
      <FrameChrome label="도판" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {files.map(function (f, i) {
          var at = p.at(i);
          var scale = seg(t, at, 1.1, 1.06, 1);
          return (
            <div key={'f' + i} style={{
              position: 'absolute', left: g.x + i * (g.cardW + g.gap), top: g.y,
              width: g.cardW, height: g.cardH, boxSizing: 'border-box',
              background: card.bg, border: '1px solid ' + card.border,
              borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
              overflow: 'hidden',
              opacity: seg(t, at, p.dur, 0, 1),
            }}>
              <img src={f.src} alt={f.alt} style={{
                position: 'absolute', left: 0, top: 0, width: '100%', height: g.imgH,
                objectFit: 'cover', display: 'block',
                transform: 'scale(' + scale + ')',
              }} />
              {f.badge && (
                <div style={Object.assign({
                  position: 'absolute', left: 18, top: 18,
                  background: chip.activeBg, color: chip.activeFg,
                  fontSize: theme.type.caption, fontWeight: 800, lineHeight: 1,
                  padding: '8px 16px', borderRadius: theme.radius.pill, whiteSpace: 'nowrap',
                  boxShadow: theme.shadow.blueSoft,
                }, popIn(theme, t, at + p.badgeDelay))}>{f.badge}</div>
              )}
              {/* 캡션 스트립 — 캡션(잉크) + 출처(페인트) */}
              <div style={{
                position: 'absolute', left: 0, right: 0, bottom: 0, height: g.capH,
                background: card.bg, borderTop: '1px solid ' + theme.color.line,
                boxSizing: 'border-box', padding: '0 22px',
                display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 4,
              }}>
                <div style={Object.assign({
                  fontSize: theme.type.note, fontWeight: 800, color: theme.color.ink,
                  whiteSpace: 'nowrap',
                }, enter(theme, t, at + p.capDelay, p.capDur, 10))}>{f.caption}</div>
                {f.source && (
                  <div style={{
                    fontSize: theme.type.caption, fontWeight: 600, color: theme.color.faint,
                    whiteSpace: 'nowrap',
                    opacity: seg(t, at + p.capDelay + 0.15, p.capDur, 0, 1),
                  }}>출처 · {f.source}</div>
                )}
              </div>
            </div>
          );
        })}
        <DataNote t={t} theme={theme} data={d.note} top={theme.component.processNote.top} at={p.note.at} />
      </FrameChrome>
    );
  }
  MediaScene.nat = 10;
  MediaScene.schedule = function (d) {
    var p = mdPlan(d);
    var out = FRAME_SCHED.slice();
    for (var i = 0; i < p.count; i++) {
      out.push({ id: 'media-' + i, kind: 'enter', at: p.at(i), dur: 1.1, path: '/files/' + i });
      out.push({ id: 'media-' + i + '-caption', kind: 'enter', at: p.at(i) + p.capDelay, dur: p.capDur, path: '/files/' + i + '/caption' });
    }
    if (d.note) {
      out.push({ id: 'note', kind: 'enter', at: p.note.at, dur: p.note.dur, path: '/note' });
    }
    return out;
  };

  /* ══ tpl.d-multi — 다계열 그룹 막대 (은유: 겹겹의 논증 — 계열 하나가 논지 한 겹) ══
     등장 순서 = 논증 순서: ① 축(0 기준선 + 그리드) → ② 항목 라벨 → ③ 계열이 하나씩
     입장(범례 칩 점등 → 막대 좌→우 스윕 성장 → 계열 최대값 라벨) → ④ 풋노트.
     0 기준선 고정(음수 금지·axisMin 부재), 축 상한은 데이터 최댓값 이상으로 자동 승격. */

  var MS_TONE_ORDER = ['primary', 'secondary', 'positive', 'caution'];
  function msTone(theme, tone, idx) {
    var key = tone || MS_TONE_ORDER[idx % MS_TONE_ORDER.length];
    if (key === 'secondary') return { bar: theme.color.blue2, border: null };
    if (key === 'positive') return { bar: theme.color.green, border: null };
    if (key === 'caution') return { bar: theme.color.red, border: null };
    if (key === 'muted') return { bar: theme.color.blueSoft, border: theme.color.blueBorder };
    return { bar: theme.color.blue, border: null }; // primary
  }
  function msGeo(theme, N, S) {
    var L = theme.layout;
    var w = L.stageW - 2 * L.marginX;                       // 1640
    var padL = 96, padR = 44, padT = 96, padB = 78;
    var plotW = w - padL - padR;                             // 1500
    var plotH = 592 - padT - padB;                           // 418
    var catW = plotW / Math.max(1, N);
    var barW = Math.min(48, (catW - 44 - (S - 1) * 6) / Math.max(1, S));
    return {
      x: L.marginX, y: L.contentTop, w: w, h: 592, pad: 28,
      plotX0: padL, plotW: plotW, plotTop: padT, plotH: plotH,
      baseY: padT + plotH, catW: catW, barW: barW, barGap: 6,
      groupW: S * barW + (S - 1) * 6,
    };
  }
  function msPlan(d) {
    var S = (d.series || []).length;
    var N = (d.categories || []).length;
    var sAt = function (s) { return 2.4 + s * 1.4; };
    var lastSettle = sAt(Math.max(0, S - 1)) + 1.0 + 0.5;
    return {
      S: S, N: N, sAt: sAt,
      panel: { at: 0.9, dur: 0.7 },
      axis: { at: 1.3, dur: 0.6 },
      cats: { at: 1.75, dur: 0.5, stagger: 0.08 },
      barDur: 0.8, barStagger: 0.07, valDelay: 1.0,
      note: { at: lastSettle + 0.4, dur: 0.7 },
    };
  }
  function MultiScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var cats = d.categories || [];
    var series = d.series || [];
    var N = cats.length, S = series.length;
    var p = msPlan(d);
    var g = msGeo(theme, N, S);
    var card = theme.component.card;
    var dataMax = 0;
    series.forEach(function (s) {
      (s.values || []).forEach(function (v) { if (v > dataMax) dataMax = v; });
    });
    // 수치 왜곡 방지 — 축 상한은 항상 데이터 최댓값 이상(막대 절단 금지), 하한은 항상 0
    var effMax = d.axisMax != null ? Math.max(d.axisMax, dataMax) : niceCeil(dataMax);
    if (!(effMax > 0)) effMax = 1;
    var axisOp = seg(t, p.axis.at + 0.15, p.axis.dur, 0, 1);
    function barX(s, i) {
      return g.plotX0 + i * g.catW + (g.catW - g.groupW) / 2 + s * (g.barW + g.barGap);
    }
    return (
      <FrameChrome label="계열" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        <div style={Object.assign({
          position: 'absolute', left: g.x, top: g.y, width: g.w, height: g.h,
          background: card.bg, border: '1px solid ' + card.border,
          borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
        }, enter(theme, t, p.panel.at, p.panel.dur))}>
          {d.unit && (
            <div style={{
              position: 'absolute', left: g.pad, top: 30,
              fontSize: theme.type.caption, color: theme.color.faint, fontWeight: 600,
              opacity: axisOp,
            }}>단위 · {d.unit}</div>
          )}
          {/* 범례 — 계열 입장과 함께 점등 */}
          <div style={{
            position: 'absolute', right: g.pad, top: 26,
            display: 'flex', gap: 28, alignItems: 'center',
          }}>
            {series.map(function (s, si) {
              var tone = msTone(theme, s.tone, si);
              return (
                <div key={'lg' + si} style={{
                  display: 'flex', gap: 10, alignItems: 'center',
                  opacity: seg(t, p.sAt(si) - 0.15, 0.4, 0, 1),
                }}>
                  <div style={{
                    width: 16, height: 16, borderRadius: 5, background: tone.bar,
                    boxSizing: 'border-box',
                    border: tone.border ? '1px solid ' + tone.border : 'none',
                  }}></div>
                  <div style={{
                    fontSize: theme.type.caption, color: theme.color.sub,
                    fontWeight: 700, whiteSpace: 'nowrap',
                  }}>{s.name}</div>
                </div>
              );
            })}
          </div>
          {/* 축 — 0 기준선(진하게) + ¼ 그리드 + 눈금 라벨 */}
          {[0, 1, 2, 3, 4].map(function (k) {
            var y = g.baseY - (g.plotH / 4) * k;
            return (
              <React.Fragment key={'tk' + k}>
                <div style={{
                  position: 'absolute', left: g.plotX0, top: y - (k === 0 ? 1 : 0.5),
                  width: g.plotW, height: k === 0 ? 2 : 1,
                  background: k === 0 ? theme.color.sub : theme.color.line,
                  transformOrigin: '0% 50%',
                  transform: 'scaleX(' + seg(t, p.axis.at + k * 0.05, p.axis.dur, 0, 1) + ')',
                }}></div>
                <div style={{
                  position: 'absolute', left: 0, top: y - 15, width: g.plotX0 - 14,
                  textAlign: 'right', fontSize: theme.type.caption,
                  color: theme.color.faint, fontWeight: 600, opacity: axisOp,
                }}>{fmtNum((effMax / 4) * k)}</div>
              </React.Fragment>
            );
          })}
          {/* 항목 라벨 */}
          {cats.map(function (c, i) {
            return (
              <div key={'cat' + i} style={Object.assign({
                position: 'absolute', left: g.plotX0 + i * g.catW, top: g.baseY + 16,
                width: g.catW, textAlign: 'center',
                fontSize: theme.type.caption, color: theme.color.sub, fontWeight: 700,
                whiteSpace: 'nowrap',
              }, enter(theme, t, p.cats.at + i * p.cats.stagger, p.cats.dur, 10))}>{c.label}</div>
            );
          })}
          {/* 계열 막대 — 계열 순차 입장, 계열 안은 좌→우 스윕 */}
          {series.map(function (s, si) {
            var tone = msTone(theme, s.tone, si);
            var vals = (s.values || []).slice(0, N);
            var maxIdx = 0;
            vals.forEach(function (v, i) { if (v > vals[maxIdx]) maxIdx = i; });
            return (
              <React.Fragment key={'s' + si}>
                {vals.map(function (v0, i) {
                  var v = Math.max(0, Number(v0) || 0);
                  var full = (v / effMax) * g.plotH;
                  var h = seg(t, p.sAt(si) + i * p.barStagger, p.barDur, 0, full);
                  return (
                    <div key={'b' + i} style={{
                      position: 'absolute', left: barX(si, i), top: g.baseY - h,
                      width: g.barW, height: h, boxSizing: 'border-box',
                      background: tone.bar,
                      border: tone.border ? '1px solid ' + tone.border : 'none',
                      borderRadius: '8px 8px 0 0',
                    }}></div>
                  );
                })}
                {/* 값 라벨은 계열 최대치 1개만 — 과밀 방지 */}
                {vals.length > 0 && (
                  <div style={{
                    position: 'absolute',
                    left: barX(si, maxIdx) + g.barW / 2,
                    top: g.baseY - (Math.max(0, Number(vals[maxIdx]) || 0) / effMax) * g.plotH - 40,
                    fontSize: theme.type.caption, fontWeight: 800, color: theme.color.ink,
                    whiteSpace: 'nowrap',
                    opacity: seg(t, p.sAt(si) + p.valDelay, 0.5, 0, 1),
                    transform: 'translate(-50%,' + seg(t, p.sAt(si) + p.valDelay, 0.5, 8, 0) + 'px)',
                  }}>{fmtNum(Math.max(0, Number(vals[maxIdx]) || 0))}</div>
                )}
              </React.Fragment>
            );
          })}
        </div>
        <DataNote t={t} theme={theme} data={d.note} top={theme.component.processNote.top} at={p.note.at} />
      </FrameChrome>
    );
  }
  MultiScene.nat = 13;
  MultiScene.schedule = function (d) {
    var p = msPlan(d);
    var out = FRAME_SCHED.concat([
      { id: 'panel', kind: 'enter', at: p.panel.at, dur: p.panel.dur },
      { id: 'axis', kind: 'enter', at: p.axis.at, dur: p.axis.dur + 0.2 },
      { id: 'cats', kind: 'enter', at: p.cats.at, dur: p.cats.dur, stagger: p.cats.stagger, count: p.N, path: '/categories' },
    ]);
    for (var s = 0; s < p.S; s++) {
      out.push({ id: 'legend-' + s, kind: 'enter', at: p.sAt(s) - 0.15, dur: 0.4, path: '/series/' + s + '/name' });
      out.push({ id: 'series-' + s, kind: 'enter', at: p.sAt(s), dur: p.barDur, stagger: p.barStagger, count: p.N, path: '/series/' + s });
      out.push({ id: 'series-' + s + '-max', kind: 'enter', at: p.sAt(s) + p.valDelay, dur: 0.5 });
    }
    if (d.note) {
      out.push({ id: 'note', kind: 'enter', at: p.note.at, dur: p.note.dur, path: '/note' });
    }
    return out;
  };

  OMX.templates = Object.assign(OMX.templates || {}, {
    MatrixScene: MatrixScene,
    MediaScene: MediaScene,
    MultiScene: MultiScene,
  });
  OMX.templateIndex = Object.assign(OMX.templateIndex || {}, {
    'tpl.d-matrix': MatrixScene,
    'tpl.d-media': MediaScene,
    'tpl.d-multi': MultiScene,
  });
})();
