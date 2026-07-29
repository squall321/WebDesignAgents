// 클로징 변주 3종 — tpl.x-summary(요약 회수) · tpl.x-quote(한 문장 각인) · tpl.x-next(다음 단계).
// tpl.closing(통계 트리오 퇴장 → 타이틀 + CTA 필) 1종뿐이던 마무리를 다변화한다.
// 공통 규율 — 클로징은 영상의 마지막이라 **퇴장(exit) 효과를 두지 않는다**. 등장만으로 쌓아
// 마지막 프레임이 곧 완성 화면이 되게 한다(게이트 7 tail diff 0 · 정지 화면으로 오래 버틸 수 있음).
// 계약: 엔진 props({localTime, progress, dur, index, count, scene}) + data(schema.json) + theme(토큰 트리),
// 정적 .schedule(data)/.nat, 모든 모션은 t(localTime)의 순수 함수(Math.random/Date/타이머 금지).
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
  // 하단 중앙 풋노트 — {pre, strong, post}
  function ClosingNote(props) {
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

  // 클로징 공통 내용 띠 — 킥커/타이틀 아래부터 하단 안내 자리까지.
  // 하단 안내(대기 문구 필·풋노트)는 프레임 푸터 구분선(y≈971) **위에서 끝난다** — 기존 씬들이
  // 쓰던 processNote.top(952)은 푸터가 켜지면 구분선과 겹친다. 클로징은 마지막 정지 화면이라
  // 그 겹침이 그대로 남으므로, 띠를 20~40px 줄여 안내가 구분선을 침범하지 않게 한다.
  var BAND_TOP_KEY = 'contentTop';   // theme.layout.contentTop (330)
  var FOOTER_RULE_Y = 971;           // FrameChrome 푸터 borderTop 실측 y (bottom 56 + padTop 22 + 24px 1줄)

  /* ══ tpl.x-summary — 요약 회수형 (은유: 회의록 — 다룬 것이 번호대로 되짚어지고 그대로 남는다) ══
     등장 순서 = 되짚는 순서: ① 킥커/타이틀 → ② 1행(번호칩 → 문장 → 근거 수치) → ③ 2행 → …
     → ④ 마지막 행 → ⑤ 대기 문구. 어느 행도 사라지지 않는다 — 전부 남는 것이 이 템플릿의 요점이다.
     tpl.closing 과의 차이: 저쪽은 통계가 **퇴장한 뒤** 타이틀이 들어오는 2페이즈 전환이라
     마지막에 남는 건 슬로건이다. 이쪽은 본문에서 다룬 근거가 한 화면에 누적돼 남는다 —
     발표 종료 후 질의응답 대기 화면으로 그대로 세워둘 수 있는 상태가 목표다.

     밀도 원칙 — 행 수(3~5)가 행 높이·수치 글자 크기를 정한다. 스키마에는 크기 필드가 없다. */

  var SM_GAP = 18;
  var SM_PAD = 30;
  var SM_METRIC_W = 320;
  var SM_CHIP_GAP = 26;
  var SM_BAND_BOTTOM = 866;
  var SM_STANDBY_TOP = 886;
  var SM_STANDBY_H = 56;                                  // 886+56=942 < 971 (푸터 구분선)

  function smGeo(theme, n) {
    var L = theme.layout;
    var W = L.stageW - 2 * L.marginX;                     // 1640
    var top = L[BAND_TOP_KEY];                            // 330
    var H = SM_BAND_BOTTOM - top;                         // 536
    var count = Math.max(1, n);
    var rowH = (H - (count - 1) * SM_GAP) / count;        // 3행 166.67 · 4행 120.5 · 5행 92.8
    var dense = count >= 5;
    var chip = Math.min(72, rowH - 32);
    var valueSize = dense ? theme.type.item : theme.type.caseTitle;   // 31 / 38
    var valueLineH = Math.round(valueSize * 1.2);                     // 37 / 46
    var labelLineH = Math.round(theme.type.caption * 1.25);           // 30
    return {
      x: L.marginX, y: top, w: W, h: H,
      count: count, rowH: rowH, dense: dense, pad: SM_PAD,
      chip: chip, chipGap: SM_CHIP_GAP,
      textLeft: SM_PAD + chip + SM_CHIP_GAP,
      textW: W - 2 * SM_PAD - chip - SM_CHIP_GAP - SM_METRIC_W - SM_CHIP_GAP,
      textLineH: Math.round(theme.type.item * 1.35),                  // 42
      metricW: SM_METRIC_W,
      valueSize: valueSize, valueLineH: valueLineH,
      labelLineH: labelLineH, metricH: valueLineH + 4 + labelLineH,
      standbyTop: SM_STANDBY_TOP, standbyH: SM_STANDBY_H,
      footerRuleY: FOOTER_RULE_Y,
    };
  }
  function smPlan(d) {
    var n = (d.points || []).length;
    var at = function (i) { return 1.0 + i * 1.4; };
    var last = at(Math.max(0, n - 1));
    return {
      count: n, at: at, dur: 0.6,
      chipDelay: 0.06, textDelay: 0.16, metricDelay: 0.34,
      standby: { at: last + 1.9, dur: 0.7 },
    };
  }
  function SummaryScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var points = d.points || [];
    var g = smGeo(theme, points.length);
    var p = smPlan(d);
    var card = theme.component.card;
    var chip = theme.component.chip;
    return (
      <FrameChrome label="요약" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {points.map(function (it, i) {
          var at = p.at(i);
          var top = g.y + i * (g.rowH + SM_GAP);
          return (
            <div key={'r' + i} style={Object.assign({
              position: 'absolute', left: g.x, top: top, width: g.w, height: g.rowH,
              boxSizing: 'border-box', background: card.bg,
              border: '1px solid ' + card.border, borderRadius: theme.radius.card,
              boxShadow: card.shadowSoft,
            }, enter(theme, t, at, p.dur, 22))}>
              {/* 번호 칩 — 되짚는 순서를 눈에 박는다 (본문 차례와 같은 번호) */}
              <div style={Object.assign({
                position: 'absolute', left: g.pad, top: (g.rowH - g.chip) / 2,
                width: g.chip, height: g.chip, boxSizing: 'border-box',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: chip.activeBg, color: chip.activeFg,
                borderRadius: theme.radius.chip,
                fontSize: theme.type.emphasis, fontWeight: 800, lineHeight: 1.2,
              }, popIn(theme, t, at + p.chipDelay))}>{i + 1}</div>
              {/* 회수 문장 — 본문 한 대목을 한 문장으로 (1줄 고정) */}
              <div style={Object.assign({
                position: 'absolute', left: g.textLeft, top: (g.rowH - g.textLineH) / 2,
                width: g.textW, height: g.textLineH,
                display: 'flex', alignItems: 'center',
                fontSize: theme.type.item, fontWeight: 700, color: theme.color.ink,
                letterSpacing: '-0.01em', lineHeight: 1.35, whiteSpace: 'nowrap',
              }, enter(theme, t, at + p.textDelay, 0.5, 12))}>{it.text}</div>
              {/* 근거 수치 — 문장이 주장이면 이쪽이 그 근거다 */}
              <div style={Object.assign({
                position: 'absolute', right: g.pad, top: (g.rowH - g.metricH) / 2,
                width: g.metricW, height: g.metricH, textAlign: 'right',
              }, enter(theme, t, at + p.metricDelay, 0.5, 12))}>
                <div style={{
                  height: g.valueLineH, lineHeight: g.valueLineH + 'px',
                  fontSize: g.valueSize, fontWeight: 800, color: theme.color.blue,
                  letterSpacing: '-0.02em', whiteSpace: 'nowrap',
                }}>{it.metric}</div>
                {it.metricLabel && (
                  <div style={{
                    height: g.labelLineH, lineHeight: g.labelLineH + 'px', marginTop: 4,
                    fontSize: theme.type.caption, fontWeight: 600, color: theme.color.sub,
                    whiteSpace: 'nowrap',
                  }}>{it.metricLabel}</div>
                )}
              </div>
            </div>
          );
        })}
        {/* 대기 문구 — 질의응답 동안 세워둘 마지막 상태 */}
        <div style={{
          position: 'absolute', left: 0, right: 0, top: g.standbyTop,
          display: 'flex', justifyContent: 'center',
        }}>
          <div style={Object.assign({
            display: 'flex', alignItems: 'center', height: g.standbyH, padding: '0 38px',
            boxSizing: 'border-box',
            background: chip.accentBg, color: chip.accentFg,
            border: '1.5px solid ' + theme.color.blueBorder,
            borderRadius: theme.radius.pill,
            fontSize: theme.type.body, fontWeight: 700, lineHeight: 1.2, whiteSpace: 'nowrap',
          }, enter(theme, t, p.standby.at, p.standby.dur, 16))}>{d.standby}</div>
        </div>
      </FrameChrome>
    );
  }
  SummaryScene.nat = 14;
  SummaryScene.schedule = function (d) {
    var p = smPlan(d);
    var points = d.points || [];
    var out = FRAME_SCHED.slice();
    for (var i = 0; i < p.count; i++) {
      var at = p.at(i);
      out.push({ id: 'point-' + i, kind: 'enter', at: at, dur: p.dur, path: '/points/' + i });
      out.push({ id: 'num-' + i, kind: 'enter', at: at + p.chipDelay, dur: 0.45 });
      out.push({ id: 'text-' + i, kind: 'enter', at: at + p.textDelay, dur: 0.5, path: '/points/' + i + '/text' });
      out.push({ id: 'metric-' + i, kind: 'enter', at: at + p.metricDelay, dur: 0.5, path: '/points/' + i + '/metric' });
    }
    out.push({ id: 'standby', kind: 'enter', at: p.standby.at, dur: p.standby.dur, path: '/standby' });
    return out;
  };

  /* ══ tpl.x-quote — 한 문장 각인형 (은유: 비문 — 다 지우고 한 문장만 새긴다) ══
     등장 순서 = 각인 절차: ① 상단 규칙선이 그어지고 → ② 문장이 올라와 앉고 →
     ③ 밑줄이 좌→우로 그어져 문장을 고정하고 → ④ 출처/일자가 조용히 붙는다.
     배경에는 아무것도 두지 않는다(킥커·타이틀·푸터 없음) — 남길 것이 하나뿐이라는 선언이다.

     타이포 스케일 — 문장은 theme.type.display(92px), 행간 1.24. 오프닝 선언형(tpl.o-statement)이
     자수에 따라 96~120px · 행간 1.24 를 쓰므로(2026-07-29 omx-openings.jsx 실측) 그 대역 바로
     아래 토큰값에 고정한다 — 여는 화면이 가장 크고 닫는 화면이 같은 층위에서 한 단계 낮게 앉아
     수미상관이 성립한다. 임의 px 대신 토큰을 쓰는 쪽을 택했다(UI 원칙 3 — 토큰 일치).
     강조부만 blue 로 갈라 읽힌다. */

  var QT_W = 1560;                     // 문장 폭 — 좌우 180px 여백 (safe margin 의 10배)
  var QT_LINE_H = 1.24;                // tpl.o-statement 의 ST_LINE_H 와 동일 (수미상관)
  var QT_RULE_W = 120;
  var QT_UNDERLINE_W = 560;

  function qtGeo(theme) {
    return {
      quoteW: QT_W, quoteSize: theme.type.display,        // 92 (요구 대역 80~100px)
      quoteLineH: QT_LINE_H, ruleW: QT_RULE_W, underlineW: QT_UNDERLINE_W,
      metaSize: theme.type.body,
    };
  }
  function qtPlan() {
    return {
      rule: { at: 0.5, dur: 0.8 },
      quote: { at: 1.1, dur: 1.0 },
      underline: { at: 2.6, dur: 0.9 },
      meta: { at: 3.5, dur: 0.7 },
    };
  }
  function QuoteScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var g = qtGeo(theme);
    var p = qtPlan();
    var q = d.quote || {};
    return (
      <FrameChrome label="각인" t={t} theme={theme} hideFooter>
        <div style={{
          position: 'absolute', inset: 0,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            width: seg(t, p.rule.at, p.rule.dur, 0, g.ruleW), height: 5,
            background: theme.color.blue, borderRadius: 3, marginBottom: 40,
          }}></div>
          <div style={Object.assign({
            width: g.quoteW, textAlign: 'center',
            fontSize: g.quoteSize, fontWeight: 800, color: theme.color.ink,
            letterSpacing: '-0.03em', lineHeight: g.quoteLineH,
          }, enter(theme, t, p.quote.at, p.quote.dur, 34))}>
            {q.pre}{q.accent && <span style={{ color: theme.color.blue }}>{q.accent}</span>}{q.post}
          </div>
          <div style={{
            width: seg(t, p.underline.at, p.underline.dur, 0, g.underlineW), height: 3,
            background: theme.color.blueBorder, borderRadius: 2, marginTop: 44,
          }}></div>
          <div style={Object.assign({
            marginTop: 34, display: 'flex', alignItems: 'center', gap: 16,
            fontSize: g.metaSize, lineHeight: 1.3,
          }, enter(theme, t, p.meta.at, p.meta.dur, 14))}>
            <span style={{ fontWeight: 700, color: theme.color.ink }}>{d.source}</span>
            {d.date && <span style={{ color: theme.color.faint }}>·</span>}
            {d.date && <span style={{ fontWeight: 500, color: theme.color.faint }}>{d.date}</span>}
          </div>
        </div>
      </FrameChrome>
    );
  }
  QuoteScene.nat = 10;
  QuoteScene.schedule = function (d) {
    var p = qtPlan();
    var out = [
      { id: 'rule', kind: 'enter', at: p.rule.at, dur: p.rule.dur },
      { id: 'quote', kind: 'enter', at: p.quote.at, dur: p.quote.dur, path: '/quote' },
      { id: 'underline', kind: 'enter', at: p.underline.at, dur: p.underline.dur },
      { id: 'source', kind: 'enter', at: p.meta.at, dur: p.meta.dur, path: '/source' },
    ];
    if (d && d.date) out.push({ id: 'date', kind: 'enter', at: p.meta.at, dur: p.meta.dur, path: '/date' });
    return out;
  };

  /* ══ tpl.x-next — 다음 단계형 (은유: 인수인계 — 왼쪽은 닫힌 것, 오른쪽은 열린 것) ══
     등장 순서 = 실무 보고서의 마무리 순서: ① 결정 패널(라벨 → 결정문 → 구분선 → 근거 목록 → 확정 메타)
     → ② 다음 단계 카드(시점 필 → 내용 → 담당 칩)를 위에서 아래로 → ③ 풋노트.
     tpl.closing 의 CTA 필과의 차이: 저쪽은 '무엇을 하라'는 권유(주체·시점 없음)다.
     이쪽은 **누가·언제·무엇을** 이 카드마다 박혀 있어 회의 종료 화면이 곧 액션아이템 표가 된다.

     밀도 원칙 — 단계 수(3~4)가 카드 높이를 정하고 시점 필·담당 칩은 고정 폭이다.
     내용 폭은 그 잔여로 역산되며, 스키마 maxLength 는 그 폭에서 뽑은 수치다. */

  var NX_LEFT_W = 580;
  var NX_COL_GAP = 40;
  var NX_CARD_GAP = 20;
  var NX_WHEN_W = 190;
  var NX_OWNER_W = 190;
  var NX_INNER_GAP = 20;
  var NX_BAND_BOTTOM = 886;
  var NX_NOTE_TOP = 906;                                   // 906+31=937 < 971 (푸터 구분선)

  function nxGeo(theme, n) {
    var L = theme.layout;
    var top = L[BAND_TOP_KEY];                             // 330
    var H = NX_BAND_BOTTOM - top;                          // 556
    var W = L.stageW - 2 * L.marginX;                      // 1640
    var rightW = W - NX_LEFT_W - NX_COL_GAP;               // 1020
    var count = Math.max(1, n);
    var cardH = (H - (count - 1) * NX_CARD_GAP) / count;   // 3장 172 · 4장 124
    var cardPad = 20;
    var innerW = rightW - 2 * cardPad;                     // 980
    var leftPad = 28;
    var leftInner = NX_LEFT_W - 2 * leftPad;               // 524
    var headLineH = Math.round(theme.type.caseTitle * 1.24);   // 47
    var pointLineH = Math.round(theme.type.body * 1.27);       // 33
    var whatLineH = Math.round(theme.type.item * 1.3);         // 40
    var labelH = 42;
    var metaH = 30;
    // 좌측 패널 세로 흐름 — 라벨 → 결정문(2줄 고정) → 구분선 → 근거 목록(각 2줄) → 확정 메타(하단 고정)
    var rows = { label: leftPad, head: leftPad + labelH + 18 };
    rows.rule = rows.head + headLineH * 2 + 22;
    rows.points = rows.rule + 23;
    rows.metaTop = H - leftPad - metaH;
    return {
      x: L.marginX, y: top, w: W, h: H,
      leftW: NX_LEFT_W, leftPad: leftPad, leftInner: leftInner,
      labelH: labelH, headLineH: headLineH, headH: headLineH * 2,
      pointLineH: pointLineH, pointH: pointLineH * 2, pointGap: 22,
      rows: rows, metaH: metaH,
      rightX: L.marginX + NX_LEFT_W + NX_COL_GAP, rightW: rightW,
      count: count, cardH: cardH, cardPad: cardPad, innerW: innerW,
      whenW: NX_WHEN_W, ownerW: NX_OWNER_W, pillH: 46,
      whatW: innerW - NX_WHEN_W - NX_INNER_GAP - NX_OWNER_W - NX_INNER_GAP,  // 560
      whatLineH: whatLineH, whatH: whatLineH * 2,
      noteTop: NX_NOTE_TOP, footerRuleY: FOOTER_RULE_Y,
    };
  }
  function nxPlan(d) {
    var np = ((d.decision || {}).points || []).length;
    var ns = (d.steps || []).length;
    var cardAt = function (i) { return 3.4 + i * 1.15; };
    var last = cardAt(Math.max(0, ns - 1)) + 0.4 + 0.5;
    return {
      panel: { at: 0.9, dur: 0.7 },
      label: { at: 1.15, dur: 0.45 },
      head: { at: 1.3, dur: 0.6 },
      rule: { at: 1.7, dur: 0.6 },
      points: { at: 2.0, dur: 0.5, stagger: 0.5, count: np },
      meta: { at: 2.0 + np * 0.5 + 0.4, dur: 0.5 },
      cardAt: cardAt, cardDur: 0.6, whenDelay: 0.1, whatDelay: 0.24, ownerDelay: 0.4,
      stepCount: ns,
      note: { at: last + 1.0, dur: 0.7 },
    };
  }
  function NextScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var dec = d.decision || {};
    var steps = d.steps || [];
    var g = nxGeo(theme, steps.length);
    var p = nxPlan(d);
    var card = theme.component.card;
    var chip = theme.component.chip;
    return (
      <FrameChrome label="다음 단계" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {/* ── 좌: 닫힌 것 — 이 자리에서 확정된 결정 ── */}
        <div style={Object.assign({
          position: 'absolute', left: g.x, top: g.y, width: g.leftW, height: g.h,
          boxSizing: 'border-box', background: card.bg,
          border: '1px solid ' + card.border, borderRadius: theme.radius.card,
          boxShadow: card.shadow,
        }, enter(theme, t, p.panel.at, p.panel.dur, 26))}>
          <div style={Object.assign({
            position: 'absolute', left: g.leftPad, top: g.rows.label, height: g.labelH,
            display: 'flex', alignItems: 'center', padding: '0 20px', boxSizing: 'border-box',
            background: chip.accentBg, color: chip.accentFg, borderRadius: theme.radius.pill,
            fontSize: theme.type.caption, fontWeight: 800, letterSpacing: '0.08em',
            lineHeight: 1.2, whiteSpace: 'nowrap',
          }, popIn(theme, t, p.label.at))}>{dec.label || '결정 사항'}</div>
          <div style={Object.assign({
            position: 'absolute', left: g.leftPad, top: g.rows.head,
            width: g.leftInner, height: g.headH,
            display: 'flex', alignItems: 'center',   // 1줄 결정문도 2줄 상자 안에서 균형을 잡는다
            fontSize: theme.type.caseTitle, fontWeight: 800, color: theme.color.ink,
            letterSpacing: '-0.02em', lineHeight: g.headLineH + 'px',
          }, enter(theme, t, p.head.at, p.head.dur, 16))}>{dec.headline}</div>
          <div style={{
            position: 'absolute', left: g.leftPad, top: g.rows.rule,
            width: g.leftInner, height: 1, background: theme.color.line,
            transform: 'scaleX(' + seg(t, p.rule.at, p.rule.dur, 0, 1) + ')',
            transformOrigin: '0% 50%',
          }}></div>
          {(dec.points || []).map(function (s, i) {
            var top = g.rows.points + i * (g.pointH + g.pointGap);
            return (
              <React.Fragment key={'dp' + i}>
                <div style={Object.assign({
                  position: 'absolute', left: g.leftPad, top: top + 12,
                  width: 10, height: 10, borderRadius: theme.radius.pill,
                  background: theme.color.blue,
                }, popIn(theme, t, p.points.at + i * p.points.stagger))}></div>
                <div style={Object.assign({
                  position: 'absolute', left: g.leftPad + 24, top: top,
                  width: g.leftInner - 24, height: g.pointH,
                  fontSize: theme.type.body, fontWeight: 500, color: theme.color.sub,
                  lineHeight: g.pointLineH + 'px', overflowWrap: 'anywhere',
                }, enter(theme, t, p.points.at + i * p.points.stagger, p.points.dur, 10))}>{s}</div>
              </React.Fragment>
            );
          })}
          {dec.meta && (
            <div style={Object.assign({
              position: 'absolute', left: g.leftPad, bottom: g.leftPad,
              width: g.leftInner, height: g.metaH,
              fontSize: theme.type.caption, fontWeight: 600, color: theme.color.faint,
              lineHeight: g.metaH + 'px', whiteSpace: 'nowrap',
            }, enter(theme, t, p.meta.at, p.meta.dur, 10))}>{dec.meta}</div>
          )}
        </div>
        {/* ── 우: 열린 것 — 누가 언제 무엇을 ── */}
        {steps.map(function (s, i) {
          var at = p.cardAt(i);
          var top = g.y + i * (g.cardH + NX_CARD_GAP);
          return (
            <div key={'s' + i} style={Object.assign({
              position: 'absolute', left: g.rightX, top: top, width: g.rightW, height: g.cardH,
              boxSizing: 'border-box', background: card.bg,
              border: '1px solid ' + card.border, borderRadius: theme.radius.card,
              boxShadow: card.shadowSoft,
            }, enter(theme, t, at, p.cardDur, 24))}>
              {/* 시점 — 채운 필 (일정) */}
              <div style={Object.assign({
                position: 'absolute', left: g.cardPad, top: (g.cardH - g.pillH) / 2,
                width: g.whenW, height: g.pillH, boxSizing: 'border-box',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: chip.activeBg, color: chip.activeFg, borderRadius: theme.radius.pill,
                fontSize: theme.type.caption, fontWeight: 800, lineHeight: 1.2, whiteSpace: 'nowrap',
              }, popIn(theme, t, at + p.whenDelay))}>{s.when}</div>
              {/* 내용 — 최대 2줄 (단계 수가 늘어도 글자는 줄지 않는다) */}
              <div style={Object.assign({
                position: 'absolute', left: g.cardPad + g.whenW + NX_INNER_GAP,
                top: (g.cardH - g.whatH) / 2, width: g.whatW, height: g.whatH,
                display: 'flex', alignItems: 'center',
                fontSize: theme.type.item, fontWeight: 700, color: theme.color.ink,
                letterSpacing: '-0.01em', lineHeight: g.whatLineH + 'px', overflowWrap: 'anywhere',
              }, enter(theme, t, at + p.whatDelay, 0.5, 12))}>{s.what}</div>
              {/* 담당 — 윤곽 칩 (책임) */}
              <div style={Object.assign({
                position: 'absolute', right: g.cardPad, top: (g.cardH - g.pillH) / 2,
                width: g.ownerW, height: g.pillH, boxSizing: 'border-box',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                border: '1.5px solid ' + theme.color.blueBorder, borderRadius: theme.radius.pill,
                fontSize: theme.type.caption, fontWeight: 700, color: theme.color.ink,
                lineHeight: 1.2, whiteSpace: 'nowrap',
              }, enter(theme, t, at + p.ownerDelay, 0.5, 10))}>{s.owner}</div>
            </div>
          );
        })}
        <ClosingNote t={t} theme={theme} data={d.note} top={g.noteTop} at={p.note.at} />
      </FrameChrome>
    );
  }
  NextScene.nat = 14;
  NextScene.schedule = function (d) {
    var p = nxPlan(d);
    var dec = d.decision || {};
    var out = FRAME_SCHED.slice();
    out.push({ id: 'panel', kind: 'enter', at: p.panel.at, dur: p.panel.dur });
    // label 은 미지정 시 렌더가 '결정 사항'으로 채운다 — 그때는 데이터 경로를 걸지 않는다
    out.push(dec.label
      ? { id: 'decision-label', kind: 'enter', at: p.label.at, dur: 0.45, path: '/decision/label' }
      : { id: 'decision-label', kind: 'enter', at: p.label.at, dur: 0.45 });
    out.push({ id: 'decision-headline', kind: 'enter', at: p.head.at, dur: p.head.dur, path: '/decision/headline' });
    out.push({ id: 'decision-rule', kind: 'enter', at: p.rule.at, dur: p.rule.dur });
    if (p.points.count) {
      out.push({
        id: 'decision-points', kind: 'enter', at: p.points.at, dur: p.points.dur,
        stagger: p.points.stagger, count: p.points.count, path: '/decision/points',
      });
    }
    if (dec.meta) out.push({ id: 'decision-meta', kind: 'enter', at: p.meta.at, dur: p.meta.dur, path: '/decision/meta' });
    for (var i = 0; i < p.stepCount; i++) {
      var at = p.cardAt(i);
      out.push({ id: 'step-' + i, kind: 'enter', at: at, dur: p.cardDur, path: '/steps/' + i });
      out.push({ id: 'when-' + i, kind: 'enter', at: at + p.whenDelay, dur: 0.45, path: '/steps/' + i + '/when' });
      out.push({ id: 'what-' + i, kind: 'enter', at: at + p.whatDelay, dur: 0.5, path: '/steps/' + i + '/what' });
      out.push({ id: 'owner-' + i, kind: 'enter', at: at + p.ownerDelay, dur: 0.5, path: '/steps/' + i + '/owner' });
    }
    if (d.note) out.push({ id: 'note', kind: 'enter', at: p.note.at, dur: p.note.dur, path: '/note' });
    return out;
  };

  OMX.templates = Object.assign(OMX.templates || {}, {
    SummaryScene: SummaryScene,
    QuoteScene: QuoteScene,
    NextScene: NextScene,
  });
  OMX.templateIndex = Object.assign(OMX.templateIndex || {}, {
    'tpl.x-summary': SummaryScene,
    'tpl.x-quote': QuoteScene,
    'tpl.x-next': NextScene,
  });
  // 레이아웃 역산 규칙의 시험 좌석 — 순수 함수라 브라우저에서 단독 검증한다
  OMX.closings = Object.assign(OMX.closings || {}, {
    smGeo: smGeo, qtGeo: qtGeo, nxGeo: nxGeo,
    smPlan: smPlan, qtPlan: qtPlan, nxPlan: nxPlan,
  });
})();
