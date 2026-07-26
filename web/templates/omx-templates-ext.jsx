// 창작 모드 신규 씬 템플릿 3종 — tpl.dataviz(증거의 저울)·tpl.timeline(이정표의 길)·tpl.compare(거울 대면). 외부 샘플 미참조, 엔진 원자+토큰+frame-chrome 만으로 저작해 window.OMX.templates 에 병합.
// 계약: 엔진 props(localTime 등) + data + theme, 정적 .schedule(data)/.nat, frame-match(첫/끝 프레임 안정), 모든 모션은 t(localTime)의 순수 함수.
(function () {
  'use strict';
  var OMX = (window.OMX = window.OMX || {});
  var Easing = window.Easing;
  var animate = window.animate;
  var interpolate = window.interpolate;
  var FrameChrome = OMX.metaphors['frame-chrome']; // 허용된 공통 크롬 (dot-grid 내장)

  // ── 마이크로 헬퍼 — 엔진 원자 animate/interpolate 로만 재구성 ─────────
  function easeOf(name) { return (name && Easing[name]) || Easing.easeOutCubic; }
  function seg(t, at, dur, from, to, ease) {
    return animate({ from: from, to: to, start: at, end: at + dur, ease: ease || Easing.easeOutCubic })(t);
  }
  // 토큰 rise 프리셋 기반 등장 — dy 부호로 진입 방향(위/아래) 선택
  function enter(theme, t, at, dur, dy) {
    var m = theme.motion.rise;
    var d = dur == null ? m.dur : dur;
    var y = dy == null ? m.dy : dy;
    var e = easeOf(m.ease);
    return { opacity: seg(t, at, d, 0, 1, e), transform: 'translateY(' + seg(t, at, d, y, 0, e) + 'px)' };
  }
  // 토큰 pop 프리셋 — 배율 등장 (opacity 는 1 로 클램프)
  function popIn(theme, t, at, dur) {
    var m = theme.motion.pop;
    var d = dur == null ? m.dur : dur;
    var v = seg(t, at, d, 0, 1, easeOf(m.ease));
    return { opacity: Math.min(1, v), transform: 'scale(' + v + ')' };
  }
  // 하단 중앙 풋노트 — {pre, strong, post}
  function ExtNote(props) {
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

  /* ══ tpl.dataviz — 수치 논증 (은유: 증거의 저울 — 0 기준선 위에서 자로 잰 막대) ══
     등장 순서 = 논증 순서: ① 축(측정 기준) → ② 항목 라벨(비교 대상 호명) →
     ③ 비교군 막대(맥락) → ④ 강조 막대(주인공, 마지막 입장) → ⑤ 판독 수치 → ⑥ 결론 상자. */

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
  function dvGeo(theme) {
    var L = theme.layout;
    var panelW = 1120, gap = 40;
    var pad = 36, labelW = 230, plotGap = 18, valueW = 140;
    var plotX0 = pad + labelW + plotGap;                    // 패널 내 0 기준선 x = 284
    var plotW = panelW - plotX0 - pad;                      // 800
    return {
      panel: { x: L.marginX, y: L.contentTop, w: panelW, h: 590 },
      read: { x: L.marginX + panelW + gap, y: L.contentTop, w: L.stageW - 2 * L.marginX - panelW - gap },
      pad: pad, labelW: labelW, plotX0: plotX0,
      usableW: plotW - valueW,                              // 660 — axisMax 가 사상되는 폭
      rowTop: 96, rowsH: 424, barH: 36, tickY: 532,
    };
  }
  function datavizPlan(d) {
    var bars = d.bars || [];
    var n = bars.length;
    var ranks = [], r = 0, emIdx = 0;
    for (var i = 0; i < n; i++) {
      if (bars[i].emphasis) { emIdx = i; ranks.push(-1); }
      else { ranks.push(r); r++; }
    }
    var ctxAt = 2.3, ctxStagger = 0.35, ctxDur = 0.9;
    var emAt = ctxAt + Math.max(0, r - 1) * ctxStagger + 1.0;
    var m = (d.insights || []).length;
    var headlineAt = emAt + 1.3;
    var insightsAt = headlineAt + 0.5, insightStagger = 0.85;
    return {
      count: n, ctxCount: r, emIdx: emIdx,
      panel: { at: 0.9, dur: 0.7 },
      axis: { at: 1.3, dur: 0.6 },
      labels: { at: 1.7, dur: 0.5, stagger: 0.12 },
      barAt: function (i) { return bars[i].emphasis ? emAt : ctxAt + ranks[i] * ctxStagger; },
      barDur: function (i) { return bars[i].emphasis ? 1.1 : ctxDur; },
      emAt: emAt,
      headline: { at: headlineAt, dur: 0.7 },
      insights: { at: insightsAt, dur: 0.6, stagger: insightStagger, count: m },
      claim: { at: insightsAt + m * insightStagger + 0.3, dur: 0.7 },
    };
  }
  function DatavizScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = datavizPlan(d);
    var g = dvGeo(theme);
    var bars = d.bars || [];
    var dataMax = 0;
    for (var i = 0; i < bars.length; i++) if (bars[i].value > dataMax) dataMax = bars[i].value;
    // 수치 왜곡 방지 — 축 상한은 항상 데이터 최댓값 이상(막대 절단 금지), 하한은 항상 0
    var effMax = d.axisMax != null ? Math.max(d.axisMax, dataMax) : niceCeil(dataMax);
    if (!(effMax > 0)) effMax = 1;
    var rowH = g.rowsH / Math.max(1, bars.length);
    var card = theme.component.card;
    var dec = theme.component.decision;
    var ticks = [0, 1, 2, 3, 4];
    var axisOp = seg(t, p.axis.at + 0.15, p.axis.dur, 0, 1);
    var hl = d.headline || {};
    return (
      <FrameChrome label="수치" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {/* ── 차트 패널 ── */}
        <div style={Object.assign({
          position: 'absolute', left: g.panel.x, top: g.panel.y, width: g.panel.w, height: g.panel.h,
          background: card.bg, border: '1px solid ' + card.border,
          borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
        }, enter(theme, t, p.panel.at, p.panel.dur))}>
          {d.unit && (
            <div style={{
              position: 'absolute', right: g.pad, top: 30,
              fontSize: theme.type.caption, color: theme.color.faint, fontWeight: 600,
              opacity: axisOp,
            }}>단위 · {d.unit}</div>
          )}
          {/* 축 — 0 기준선(진하게) + ¼ 간격 그리드 + 눈금 라벨 */}
          {ticks.map(function (k) {
            var x = g.plotX0 + (g.usableW / 4) * k;
            return (
              <React.Fragment key={'tk' + k}>
                <div style={{
                  position: 'absolute', left: x - (k === 0 ? 1 : 0.5), top: g.rowTop - 8,
                  width: k === 0 ? 2 : 1, height: g.rowsH + 16,
                  background: k === 0 ? theme.color.sub : theme.color.line,
                  transformOrigin: '50% 0%',
                  transform: 'scaleY(' + seg(t, p.axis.at + k * 0.05, p.axis.dur, 0, 1) + ')',
                }}></div>
                <div style={{
                  position: 'absolute', left: x - 60, top: g.tickY, width: 120, textAlign: 'center',
                  fontSize: theme.type.caption, color: theme.color.faint, fontWeight: 600,
                  opacity: axisOp,
                }}>{fmtNum((effMax / 4) * k)}</div>
              </React.Fragment>
            );
          })}
          {/* 항목 행 — 라벨 → 막대 성장 → 값 라벨 */}
          {bars.map(function (b, i) {
            var y0 = g.rowTop + i * rowH;
            var at = p.barAt(i);
            var barW = seg(t, at, p.barDur(i), 0, (b.value / effMax) * g.usableW);
            var em = !!b.emphasis;
            return (
              <React.Fragment key={'b' + i}>
                <div style={Object.assign({
                  position: 'absolute', left: g.pad, top: y0, width: g.labelW, height: rowH,
                  display: 'flex', alignItems: 'center', justifyContent: 'flex-end',
                  fontSize: theme.type.note, fontWeight: em ? 800 : 700,
                  color: em ? theme.color.ink : theme.color.sub, whiteSpace: 'nowrap',
                }, enter(theme, t, p.labels.at + i * p.labels.stagger, p.labels.dur, 12))}>{b.label}</div>
                <div style={{
                  position: 'absolute', left: g.plotX0, top: y0 + (rowH - g.barH) / 2,
                  width: barW, height: g.barH,
                  borderRadius: '0 ' + theme.radius.bar + 'px ' + theme.radius.bar + 'px 0',
                  background: em ? theme.color.blue : theme.color.blueSoft,
                  border: em ? 'none' : '1px solid ' + theme.color.blueBorder,
                  boxSizing: 'border-box',
                  boxShadow: em ? theme.shadow.blueSoft : 'none',
                }}></div>
                <div style={{
                  position: 'absolute', left: g.plotX0 + barW + 14, top: y0,
                  height: rowH, display: 'flex', alignItems: 'center',
                  fontSize: theme.type.note, fontWeight: 800, whiteSpace: 'nowrap',
                  color: em ? theme.color.blue : theme.color.ink,
                  opacity: seg(t, at + p.barDur(i) - 0.15, 0.5, 0, 1),
                }}>{b.display}</div>
              </React.Fragment>
            );
          })}
        </div>
        {/* ── 판독 칼럼 — 헤드라인 수치 → 근거 → 결론 상자 ── */}
        <div style={{ position: 'absolute', left: g.read.x, top: g.read.y, width: g.read.w }}>
          <div style={Object.assign({
            fontSize: theme.type.display, fontWeight: 800, letterSpacing: '-0.02em',
            color: theme.color.blue, lineHeight: 1.15, whiteSpace: 'nowrap',
          }, enter(theme, t, p.headline.at, p.headline.dur, 24))}>{hl.value}</div>
          <div style={Object.assign({
            marginTop: 10, fontSize: theme.type.emphasis, color: theme.color.sub, fontWeight: 600,
          }, enter(theme, t, p.headline.at + 0.15, p.headline.dur, 14))}>{hl.desc}</div>
          <div style={{
            marginTop: 26, height: 1, background: theme.color.line,
            opacity: seg(t, p.headline.at + 0.4, 0.6, 0, 1),
          }}></div>
          <div style={{ marginTop: 26, display: 'flex', flexDirection: 'column', gap: 18 }}>
            {(d.insights || []).map(function (s, i) {
              return (
                <div key={i} style={Object.assign({
                  display: 'flex', gap: 14, alignItems: 'flex-start',
                }, enter(theme, t, p.insights.at + i * p.insights.stagger, p.insights.dur, 14))}>
                  <div style={{
                    width: 12, height: 12, borderRadius: 4, background: theme.color.blue2,
                    marginTop: 12, flexShrink: 0,
                  }}></div>
                  <div style={{
                    fontSize: theme.type.note, color: theme.color.ink, lineHeight: 1.5, fontWeight: 600,
                  }}>{s.text}</div>
                </div>
              );
            })}
          </div>
          {d.claim && (
            <div style={Object.assign({
              marginTop: 30, background: dec.bg, color: dec.fg, boxShadow: dec.shadow,
              borderRadius: 18, padding: '22px 26px',
              fontSize: theme.type.lead, fontWeight: 800, lineHeight: 1.4,
            }, enter(theme, t, p.claim.at, p.claim.dur, 18))}>{d.claim.text}</div>
          )}
        </div>
      </FrameChrome>
    );
  }
  DatavizScene.nat = 13;
  DatavizScene.schedule = function (d) {
    var p = datavizPlan(d);
    var out = FRAME_SCHED.concat([
      { id: 'panel', kind: 'enter', at: p.panel.at, dur: p.panel.dur },
      { id: 'axis', kind: 'enter', at: p.axis.at, dur: p.axis.dur + 0.2 },
      { id: 'labels', kind: 'enter', at: p.labels.at, dur: p.labels.dur, stagger: p.labels.stagger, count: p.count, path: '/bars' },
    ]);
    for (var i = 0; i < p.count; i++) {
      out.push({ id: 'bar-' + i, kind: 'enter', at: p.barAt(i), dur: p.barDur(i), path: '/bars/' + i });
      out.push({ id: 'bar-' + i + '-value', kind: 'enter', at: p.barAt(i) + p.barDur(i) - 0.15, dur: 0.5, path: '/bars/' + i + '/display' });
    }
    out.push({ id: 'headline', kind: 'enter', at: p.headline.at, dur: p.headline.dur + 0.15, path: '/headline' });
    if (p.insights.count > 0) {
      out.push({ id: 'insights', kind: 'enter', at: p.insights.at, dur: p.insights.dur, stagger: p.insights.stagger, count: p.insights.count, path: '/insights' });
    }
    out.push({ id: 'claim', kind: 'enter', at: p.claim.at, dur: p.claim.dur, path: '/claim' });
    return out;
  };

  /* ══ tpl.timeline — 시간 축 로드맵 (은유: 이정표의 길 — 채워진 길과 남은 길) ══
     등장 순서 = 시간 순서: 레일(길) → 마일스톤(이정표)이 좌→우 순차 점등,
     완료 구간은 파랗게 채워지고(걸어온 길) 현재 지점에 세로 현재선이 꽂히며 예정은 점선 카드. */

  function tlGeo(theme, n) {
    var L = theme.layout;
    var railW = L.stageW - 2 * L.marginX;
    var pitch = railW / Math.max(1, n);
    return {
      railW: railW, pitch: pitch,
      cardW: Math.min(2 * pitch - 60, 500), cardH: 204,
      railY: 604, railH: 6, stem: 34,
      aboveBottom: 570, belowTop: 650,
      nodeX: function (i) { return L.marginX + pitch * (i + 0.5); },
    };
  }
  function timelinePlan(d) {
    var ms = d.milestones || [];
    var n = ms.length;
    var c = 0;
    for (var i = 0; i < n; i++) if (ms[i].status === 'current') c = i;
    var T = function (i) { return 1.9 + i * 1.55; };
    return {
      count: n, current: c, T: T,
      rail: { at: 0.9, dur: 0.8 },
      nowLine: { at: T(c) + 0.7, dur: 0.8 },
      nowChip: { at: T(c) + 1.1, dur: 0.5 },
      footnote: { at: T(n - 1) + 1.7, dur: 0.7 },
    };
  }
  var TL_STATUS_LABEL = { done: '완료', current: '진행 중', planned: '예정' };
  function TimelineScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var ms = d.milestones || [];
    var p = timelinePlan(d);
    var g = tlGeo(theme, ms.length);
    var L = theme.layout;
    var chip = theme.component.chip;
    var sg = theme.component.stepGrid;
    var card = theme.component.card;
    // 완료→현재 구간 채움 폭 — 마일스톤 점등 시각을 키프레임으로 한 조각 보간
    var ins = [p.rail.at + 0.5], outs = [0];
    for (var k = 0; k <= p.current; k++) {
      ins.push(p.T(k));
      outs.push(g.nodeX(k) - L.marginX);
    }
    var fillW = interpolate(ins, outs, easeOf(theme.motion.fill.ease))(t);
    var nowX = g.nodeX(p.current);
    return (
      <FrameChrome label="로드맵" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {/* 현재선 — 지금 여기를 세로로 꽂는 점선 (카드 뒤) */}
        <div style={{
          position: 'absolute', left: nowX - 1, top: 358, width: 0, height: 512,
          borderLeft: '2px dashed ' + theme.color.blue2, opacity: 0.45 * seg(t, p.nowLine.at, p.nowLine.dur, 0, 1),
          transformOrigin: '50% 0%',
          transform: 'scaleY(' + seg(t, p.nowLine.at, p.nowLine.dur, 0, 1) + ')',
        }}></div>
        <div style={{ position: 'absolute', left: nowX, top: 322, transform: 'translateX(-50%)' }}>
          <div style={Object.assign({
            background: chip.activeBg, color: chip.activeFg,
            fontSize: theme.type.caption, fontWeight: 800, lineHeight: 1,
            padding: '10px 20px', borderRadius: theme.radius.pill, whiteSpace: 'nowrap',
            boxShadow: theme.shadow.blueSoft,
          }, enter(theme, t, p.nowChip.at, p.nowChip.dur, -12))}>{d.nowLabel || '현재'}</div>
        </div>
        {/* 시간 레일 — 길 그리기 → 걸어온 만큼 채움 */}
        <div style={{
          position: 'absolute', left: L.marginX, top: g.railY,
          width: seg(t, p.rail.at, p.rail.dur, 0, g.railW), height: g.railH,
          background: sg.railBase, borderRadius: 3,
        }}>
          <div style={{
            position: 'absolute', left: 0, top: 0, width: fillW, height: g.railH,
            background: sg.railFill, borderRadius: 3,
          }}></div>
        </div>
        {ms.map(function (m, i) {
          var at = p.T(i);
          var above = i % 2 === 0;
          var x = g.nodeX(i);
          var st = m.status;
          var cTone = st === 'current' ? { bg: chip.activeBg, fg: chip.activeFg }
            : st === 'done' ? { bg: chip.accentBg, fg: chip.accentFg }
            : { bg: theme.color.typingBg, fg: theme.color.sub };
          var cardTop = above ? g.aboveBottom - g.cardH : g.belowTop;
          var stemTop = above ? g.aboveBottom : g.railY + g.railH + 6;
          var isCur = st === 'current';
          var nodeSize = isCur ? 30 : 20;
          return (
            <React.Fragment key={i}>
              {/* 이정표 노드 */}
              <div style={Object.assign({
                position: 'absolute', left: x - nodeSize / 2, top: g.railY + g.railH / 2 - nodeSize / 2,
                width: nodeSize, height: nodeSize, borderRadius: theme.radius.pill, boxSizing: 'border-box',
                background: st === 'planned' ? card.bg : theme.color.blue,
                border: isCur ? '5px solid ' + card.bg
                  : st === 'planned' ? '3px solid ' + theme.color.blueBorder : 'none',
                boxShadow: isCur ? theme.shadow.blue : 'none',
              }, popIn(theme, t, at, 0.5))}></div>
              {/* 카드-레일 연결 스템 */}
              <div style={{
                position: 'absolute', left: x - 1, top: stemTop, width: 2, height: g.stem,
                background: theme.color.blueBorder,
                transformOrigin: above ? '50% 0%' : '50% 100%',
                transform: 'scaleY(' + seg(t, at + 0.1, 0.4, 0, 1) + ')',
              }}></div>
              {/* 이정표 카드 — 상태 칩 + 시점 + 이름 + 설명 */}
              <div style={Object.assign({
                position: 'absolute', left: x - g.cardW / 2, top: cardTop,
                width: g.cardW, height: g.cardH, boxSizing: 'border-box',
                background: card.bg, borderRadius: theme.radius.panel, padding: '22px 22px',
                border: isCur ? '2px solid ' + sg.activeBorder
                  : st === 'planned' ? '2px dashed ' + theme.color.blueBorder
                  : '1px solid ' + card.border,
                boxShadow: isCur ? sg.activeShadow : st === 'planned' ? 'none' : card.shadowSoft,
              }, enter(theme, t, at + 0.25, 0.6, above ? -18 : 18))}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    background: cTone.bg, color: cTone.fg, fontSize: theme.type.caption,
                    fontWeight: 800, lineHeight: 1, padding: '6px 14px',
                    borderRadius: theme.radius.pill, whiteSpace: 'nowrap',
                  }}>{m.tag || TL_STATUS_LABEL[st]}</div>
                  <div style={{
                    fontSize: theme.type.caption, color: theme.color.faint, fontWeight: 700,
                    whiteSpace: 'nowrap',
                  }}>{m.date}</div>
                </div>
                <div style={{
                  marginTop: 12, fontSize: theme.type.emphasis, fontWeight: 800,
                  color: theme.color.ink, whiteSpace: 'nowrap', lineHeight: 1.3,
                }}>{m.name}</div>
                {m.desc && (
                  <div style={{
                    marginTop: 8, fontSize: theme.type.caption,
                    color: theme.color.sub, lineHeight: 1.42,
                  }}>{m.desc}</div>
                )}
              </div>
            </React.Fragment>
          );
        })}
        <ExtNote t={t} theme={theme} data={d.footnote} top={theme.component.processNote.top} at={p.footnote.at} />
      </FrameChrome>
    );
  }
  TimelineScene.nat = 14;
  TimelineScene.schedule = function (d) {
    var p = timelinePlan(d);
    var out = FRAME_SCHED.concat([
      { id: 'rail', kind: 'enter', at: p.rail.at, dur: p.rail.dur },
    ]);
    for (var i = 0; i < p.count; i++) {
      out.push({ id: 'node-' + i, kind: 'enter', at: p.T(i), dur: 0.5, path: '/milestones/' + i });
      out.push({ id: 'card-' + i, kind: 'enter', at: p.T(i) + 0.25, dur: 0.6, path: '/milestones/' + i });
    }
    out.push({ id: 'now-line', kind: 'enter', at: p.nowLine.at, dur: p.nowLine.dur });
    out.push({ id: 'now-chip', kind: 'enter', at: p.nowChip.at, dur: p.nowChip.dur, path: '/nowLabel' });
    out.push({ id: 'footnote', kind: 'enter', at: p.footnote.at, dur: p.footnote.dur, path: '/footnote' });
    return out;
  };

  /* ══ tpl.compare — A/B 대비 (은유: 거울 대면 — 좌우 대칭 패널의 행 단위 짝 대결) ══
     등장 순서 = 대비 논리: 두 패널 동시 등장(대칭 선언) → 행마다 AS-IS(문제 제기)
     → 축 태그(쟁점 명명) → 화살표(넘겨주기) → TO-BE(응답) → 하단 결론 배지로 수렴. */

  function cpGeo(theme) {
    var L = theme.layout;
    var gap = 140;
    var panelW = (L.stageW - 2 * L.marginX - gap) / 2;
    return {
      panelW: panelW, gap: gap,
      leftX: L.marginX, rightX: L.marginX + panelW + gap,
      y: L.contentTop, h: 560, pad: 30,
      rowTop: 150, rowsH: 390, badgeTop: 912,
    };
  }
  function comparePlan(d) {
    var n = (d.rows || []).length;
    var T = function (i) { return 2.2 + i * 2.0; };
    return {
      count: n, T: T,
      panels: { at: 0.9, dur: 0.7 },
      chips: { at: 1.35, dur: 0.5 },
      labels: { at: 1.5, dur: 0.6 },
      aAt: function (i) { return T(i); },
      aspectAt: function (i) { return T(i) + 0.55; },
      arrowAt: function (i) { return T(i) + 0.95; },
      bAt: function (i) { return T(i) + 1.3; },
      badge: { at: T(Math.max(0, n - 1)) + 2.3, dur: 0.6 },
    };
  }
  function CompareScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = comparePlan(d);
    var g = cpGeo(theme);
    var rows = d.rows || [];
    var rowH = g.rowsH / Math.max(1, rows.length);
    var card = theme.component.card;
    var chip = theme.component.chip;
    var tag = theme.component.tag;
    var panels = d.panels || {};
    var pa = panels.a || {}, pb = panels.b || {};
    function panelShell(x, emph) {
      return {
        position: 'absolute', left: x, top: g.y, width: g.panelW, height: g.h,
        background: card.bg, borderRadius: theme.radius.card, boxSizing: 'border-box',
        border: emph ? '1.5px solid ' + theme.color.blueBorder : '1px solid ' + card.border,
        boxShadow: emph ? theme.component.stepGrid.activeShadow : card.shadowSoft,
      };
    }
    function header(meta, tone) {
      return (
        <React.Fragment>
          <div style={Object.assign({
            position: 'absolute', left: g.pad, top: 30, display: 'flex',
          }, popIn(theme, t, p.chips.at))}>
            <div style={{
              background: tone.bg, color: tone.fg, fontSize: theme.type.caption,
              fontWeight: 800, letterSpacing: '0.08em', lineHeight: 1,
              padding: '10px 20px', borderRadius: theme.radius.pill, whiteSpace: 'nowrap',
            }}>{meta.tag}</div>
          </div>
          <div style={Object.assign({
            position: 'absolute', left: g.pad, top: 80, right: g.pad,
            fontSize: theme.type.item, fontWeight: 800, color: theme.color.ink, whiteSpace: 'nowrap',
          }, enter(theme, t, p.labels.at, p.labels.dur, 14))}>{meta.label}</div>
          <div style={{
            position: 'absolute', left: g.pad, right: g.pad, top: 134, height: 1,
            background: theme.color.line, opacity: seg(t, p.labels.at + 0.3, 0.5, 0, 1),
          }}></div>
        </React.Fragment>
      );
    }
    function cell(row, i, side) {
      var at = side === 'a' ? p.aAt(i) : p.bAt(i);
      var mk = side === 'a'
        ? { g: '–', bg: theme.color.typingBg, fg: theme.color.sub }
        : { g: '✓', bg: theme.color.greenSoft, fg: theme.color.green };
      return (
        <div key={side + i} style={Object.assign({
          position: 'absolute', left: g.pad, right: g.pad, top: g.rowTop + i * rowH, height: rowH,
          display: 'flex', alignItems: 'center', gap: 16, boxSizing: 'border-box',
          borderTop: i > 0 ? '1px solid ' + theme.color.line : 'none',
        }, enter(theme, t, at, 0.6, 14))}>
          <div style={{
            width: 36, height: 36, borderRadius: 10, flexShrink: 0,
            background: mk.bg, color: mk.fg, fontSize: theme.type.caption, fontWeight: 800,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>{mk.g}</div>
          <div style={{
            fontSize: theme.type.note, lineHeight: 1.45,
            color: side === 'a' ? theme.color.sub : theme.color.ink,
            fontWeight: side === 'a' ? 500 : 700,
          }}>{side === 'a' ? row.a : row.b}</div>
        </div>
      );
    }
    return (
      <FrameChrome label="대비" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        <div style={Object.assign(panelShell(g.leftX, false), enter(theme, t, p.panels.at, p.panels.dur))}>
          {header(pa, { bg: theme.color.typingBg, fg: theme.color.sub })}
          {rows.map(function (row, i) { return cell(row, i, 'a'); })}
        </div>
        <div style={Object.assign(panelShell(g.rightX, true), enter(theme, t, p.panels.at, p.panels.dur))}>
          {header(pb, { bg: chip.activeBg, fg: chip.activeFg })}
          {rows.map(function (row, i) { return cell(row, i, 'b'); })}
        </div>
        {/* 중앙 축 — 쟁점 태그 + 넘겨주기 화살표 */}
        {rows.map(function (row, i) {
          return (
            <div key={'ax' + i} style={{
              position: 'absolute', left: g.leftX + g.panelW, width: g.gap,
              top: g.y + g.rowTop + i * rowH, height: rowH,
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'center', gap: 4,
            }}>
              <div style={Object.assign({
                background: chip.accentBg, color: chip.accentFg,
                fontSize: theme.type.caption, fontWeight: 700, lineHeight: 1,
                padding: '8px 14px', borderRadius: theme.radius.pill, whiteSpace: 'nowrap',
              }, popIn(theme, t, p.aspectAt(i)))}>{row.aspect}</div>
              <div style={{
                fontSize: theme.type.arrow, color: theme.color.faint, lineHeight: 1.2,
                opacity: seg(t, p.arrowAt(i), 0.5, 0, 1),
                transform: 'translateX(' + seg(t, p.arrowAt(i), 0.5, -14, 0) + 'px)',
              }}>→</div>
            </div>
          );
        })}
        {d.conclusion && (
          <div style={{
            position: 'absolute', left: 0, right: 0, top: g.badgeTop,
            display: 'flex', justifyContent: 'center',
          }}>
            <div style={Object.assign({
              background: tag.successBg, color: tag.successFg,
              fontSize: theme.type.emphasis, fontWeight: 800,
              padding: '14px 34px', borderRadius: theme.radius.pill, whiteSpace: 'nowrap',
              boxShadow: theme.shadow.cardSoft,
            }, popIn(theme, t, p.badge.at, p.badge.dur))}>✓ {d.conclusion.text}</div>
          </div>
        )}
      </FrameChrome>
    );
  }
  CompareScene.nat = 13;
  CompareScene.schedule = function (d) {
    var p = comparePlan(d);
    var out = FRAME_SCHED.concat([
      { id: 'panels', kind: 'enter', at: p.panels.at, dur: p.panels.dur, path: '/panels' },
      { id: 'panel-chips', kind: 'enter', at: p.chips.at, dur: p.chips.dur },
      { id: 'panel-labels', kind: 'enter', at: p.labels.at, dur: p.labels.dur },
    ]);
    for (var i = 0; i < p.count; i++) {
      out.push({ id: 'row-' + i + '-a', kind: 'enter', at: p.aAt(i), dur: 0.6, path: '/rows/' + i + '/a' });
      out.push({ id: 'row-' + i + '-aspect', kind: 'enter', at: p.aspectAt(i), dur: 0.45, path: '/rows/' + i + '/aspect' });
      out.push({ id: 'row-' + i + '-arrow', kind: 'enter', at: p.arrowAt(i), dur: 0.5 });
      out.push({ id: 'row-' + i + '-b', kind: 'enter', at: p.bAt(i), dur: 0.6, path: '/rows/' + i + '/b' });
    }
    out.push({ id: 'conclusion', kind: 'enter', at: p.badge.at, dur: p.badge.dur, path: '/conclusion' });
    return out;
  };

  OMX.templates = Object.assign(OMX.templates || {}, {
    DatavizScene: DatavizScene,
    TimelineScene: TimelineScene,
    CompareScene: CompareScene,
  });
  OMX.templateIndex = Object.assign(OMX.templateIndex || {}, {
    'tpl.dataviz': DatavizScene,
    'tpl.timeline': TimelineScene,
    'tpl.compare': CompareScene,
  });
})();
