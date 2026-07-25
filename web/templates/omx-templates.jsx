// 씬 템플릿 7종 — hwax-scenes.jsx S1~S7 일반화 (window.OMX.templates). 각 템플릿은 엔진 props + data + theme 를 받고 schedule(data)/nat 정적 속성을 가진다.
// 진입/퇴장은 progress 0과 1에서 0 (frame-match). 모든 모션은 t(localTime)의 순수 함수.
(function () {
  'use strict';
  var OMX = (window.OMX = window.OMX || {});
  var M = OMX.metaphors;
  var A = OMX.motion.A;
  var rise = OMX.motion.rise;
  var toneOf = OMX.motion.toneOf;
  var easeOf = OMX.motion.easeOf;
  var Easing = window.Easing;

  var FrameChrome = M['frame-chrome'];
  var ChatbotMockup = M['chatbot-mockup'];
  var RadialNetwork = M['radial-network'];
  var StepCardGrid = M['step-card-grid'];
  var RebuttalFlow = M['rebuttal-flow'];
  var CheckmarkConverge = M['checkmark-converge'];
  var StatTrio = M['stat-trio'];
  var CtaPill = M['cta-pill'];

  // ── 공용 렌더 조각 ───────────────────────────────────────────────────
  // {pre, accent, post} 강조 텍스트
  function AccentText(props) {
    var d = props.data || {};
    return (
      <React.Fragment>
        {d.pre}{d.accent && <span style={{ color: props.accentColor }}>{d.accent}</span>}{d.post}
      </React.Fragment>
    );
  }
  // {pre, strong, post} 풋노트 (strong 은 잉크색 800)
  function NoteLine(props) {
    var t = props.t, theme = props.theme, d = props.data;
    if (!d) return null;
    return (
      <div style={Object.assign({
        position: 'absolute', left: 0, right: 0, top: props.top, textAlign: 'center',
        fontSize: theme.type.body, color: theme.color.sub,
      }, rise(theme, t, props.at, 0.7, 16))}>
        {d.pre}{d.strong && <span style={{ fontWeight: 800, color: theme.color.ink }}>{d.strong}</span>}{d.post}
      </div>
    );
  }

  // ── 스케줄 유틸 — settle(정착 시각)과 기본 still 시각 산출 ───────────
  function settleOf(e) {
    if (e.settle != null) return e.settle;
    return e.at + (e.dur || 0) + (((e.count || 1) - 1) * (e.stagger || 0));
  }
  function stillOf(schedule, nat) {
    var last = 0;
    for (var i = 0; i < schedule.length; i++) {
      if (schedule[i].kind === 'exit') continue;
      var s = settleOf(schedule[i]);
      if (s > last) last = s;
    }
    return Math.min(nat - 0.15, last + 0.8);
  }
  OMX.scheduleUtil = Object.assign(OMX.scheduleUtil || {}, { settleOf: settleOf, stillOf: stillOf });

  var FRAME_SCHED = [
    { id: 'kicker', kind: 'enter', at: 0.15, dur: 0.7, path: '/kicker' },
    { id: 'title', kind: 'enter', at: 0.35, dur: 0.7, path: '/title' },
  ];

  /* ══ tpl.opening — 배지 + 대형 타이틀 (S1 일반화) ════════════════════ */
  function openingPlan(d) {
    var n = d.dotCount || 6;
    return {
      badge: { at: 0.4, dur: 0.7 },
      title: { at: 1.0, dur: 0.9 },
      subtitle: { at: 1.9, dur: 0.7 },
      line: { at: 2.7, dur: 0.9 },
      dots: { at: 3.0, dur: 0.45, stagger: 0.16, count: n },
      footnote: { at: 3.8, dur: 0.8 },
    };
  }
  function OpeningScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = openingPlan(d);
    var n = p.dots.count;
    var lineW = A(t, p.line.at, p.line.dur, 0, 620);
    var dotStep = n > 1 ? (620 - 96) / (n - 1) : 0;
    var badge = theme.component.badge;
    var popE = easeOf(theme.motion.pop.ease);
    var dots = [];
    for (var i = 0; i < n; i++) dots.push(i);
    return (
      <FrameChrome label="오프닝" t={t} theme={theme} hideFooter>
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 38 }}>
          <div style={Object.assign({ display: 'flex' }, rise(theme, t, p.badge.at))}>
            <div style={{
              border: '1.5px solid ' + badge.border, background: badge.bg, color: badge.fg,
              fontSize: theme.type.body, fontWeight: 700, letterSpacing: '0.1em',
              padding: '14px 32px', borderRadius: theme.radius.pill,
            }}>{d.badge}</div>
          </div>
          <div style={Object.assign({
            fontSize: theme.type.hero, fontWeight: 800, letterSpacing: '-0.03em',
            lineHeight: 1.1, textAlign: 'center',
          }, rise(theme, t, p.title.at, p.title.dur, 34))}>
            <AccentText data={d.title} accentColor={theme.color.blue} />
          </div>
          <div style={Object.assign({
            fontSize: theme.type.subtitle, color: theme.color.sub, fontWeight: 500,
          }, rise(theme, t, p.subtitle.at))}>{d.subtitle}</div>
          <div style={{ position: 'relative', width: 620, height: 40, marginTop: 12 }}>
            <div style={{ position: 'absolute', left: (620 - lineW) / 2, top: 19, width: lineW, height: 2, background: theme.color.blueBorder }}></div>
            {dots.map(function (i) {
              var pop = A(t, p.dots.at + i * p.dots.stagger, p.dots.dur, 0, 1, popE);
              var pulse = 1 + 0.09 * Math.sin(t * 2.2 + i * 1.1);
              return (
                <div key={i} style={{
                  position: 'absolute', top: 12, left: 40 + i * dotStep, width: 16, height: 16,
                  borderRadius: theme.radius.pill,
                  background: i % 2 ? theme.color.blue2 : theme.color.blue,
                  opacity: pop, transform: 'scale(' + (pop * pulse) + ')',
                }}></div>
              );
            })}
          </div>
        </div>
        {d.footnote && (
          <div style={{
            position: 'absolute', bottom: 72, left: 0, right: 0, textAlign: 'center',
            fontSize: theme.type.caption, color: theme.color.faint,
            opacity: A(t, p.footnote.at, p.footnote.dur, 0, 1),
          }}>{d.footnote}</div>
        )}
      </FrameChrome>
    );
  }
  OpeningScene.nat = 8;
  OpeningScene.schedule = function (d) {
    var p = openingPlan(d);
    return [
      { id: 'badge', kind: 'enter', at: p.badge.at, dur: p.badge.dur, path: '/badge' },
      { id: 'title', kind: 'enter', at: p.title.at, dur: p.title.dur, path: '/title' },
      { id: 'subtitle', kind: 'enter', at: p.subtitle.at, dur: p.subtitle.dur, path: '/subtitle' },
      { id: 'line', kind: 'enter', at: p.line.at, dur: p.line.dur },
      { id: 'dots', kind: 'enter', at: p.dots.at, dur: p.dots.dur, stagger: p.dots.stagger, count: p.dots.count },
      { id: 'footnote', kind: 'enter', at: p.footnote.at, dur: p.footnote.dur, path: '/footnote' },
    ];
  };

  /* ══ tpl.problem — 챗봇 목업 + ✕ 목록 (S2 일반화) ═══════════════════ */
  function problemPlan(d) {
    var nf = (d.failures || []).length;
    var failStart = 7.7;
    return {
      chat: { panel: 0.9, question: 1.3, answer: 2.7, bars: 3.0, verdict: 4.8 },
      claim: { at: 5.9, dur: 0.7 },
      failures: { at: failStart, dur: 0.6, stagger: 1.1, count: nf },
      conclusion: { at: failStart + nf * 1.1 + 0.2, dur: 0.6 },
    };
  }
  function ProblemScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = problemPlan(d);
    var x = theme.component.xList;
    var claim = d.claim || {};
    return (
      <FrameChrome label="문제" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        <ChatbotMockup t={t} theme={theme}
          windowLabel={d.chat.windowLabel} question={d.chat.question}
          barWidths={d.chat.barWidths} verdict={d.chat.verdict} at={p.chat} />
        <div style={{ position: 'absolute', left: 1050, top: 372, width: 730 }}>
          <div style={Object.assign({
            fontSize: theme.type.claim, lineHeight: 1.55, fontWeight: 500, color: theme.color.ink,
          }, rise(theme, t, p.claim.at))}>
            {claim.lead}<br />
            <span style={{ fontWeight: 800 }}><AccentText data={claim.strong} accentColor={theme.color.blue} /></span>{claim.tail}
          </div>
          <div style={{ marginTop: 44, display: 'flex', flexDirection: 'column', gap: 24 }}>
            {(d.failures || []).map(function (s, i) {
              return (
                <div key={i} style={Object.assign({
                  display: 'flex', alignItems: 'center', gap: 20,
                }, rise(theme, t, p.failures.at + i * p.failures.stagger, p.failures.dur, 18))}>
                  <div style={{
                    width: x.iconSize, height: x.iconSize, borderRadius: theme.radius.tag,
                    background: x.iconBg, color: x.iconFg,
                    fontSize: theme.type.emphasis, fontWeight: 800,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>✕</div>
                  <div style={{ fontSize: theme.type.item, fontWeight: 700 }}>{s}</div>
                </div>
              );
            })}
          </div>
          {d.conclusion && (
            <div style={Object.assign({
              marginTop: 42, fontSize: theme.type.emphasis, color: theme.color.sub,
            }, rise(theme, t, p.conclusion.at, p.conclusion.dur, 14))}>{d.conclusion}</div>
          )}
        </div>
      </FrameChrome>
    );
  }
  ProblemScene.nat = 13;
  ProblemScene.schedule = function (d) {
    var p = problemPlan(d);
    var nb = ((d.chat || {}).barWidths || [500, 560, 460, 320]).length;
    return FRAME_SCHED.concat([
      { id: 'chat-panel', kind: 'enter', at: p.chat.panel, dur: 0.7 },
      { id: 'chat-question', kind: 'enter', at: p.chat.question, dur: 0.6, path: '/chat/question' },
      { id: 'chat-answer', kind: 'enter', at: p.chat.answer, dur: 0.6 },
      { id: 'chat-bars', kind: 'enter', at: p.chat.bars, dur: 0.5, stagger: 0.35, count: nb },
      { id: 'chat-verdict', kind: 'enter', at: p.chat.verdict, dur: 0.6, path: '/chat/verdict' },
      { id: 'claim', kind: 'enter', at: p.claim.at, dur: p.claim.dur, path: '/claim' },
      { id: 'failures', kind: 'enter', at: p.failures.at, dur: p.failures.dur, stagger: p.failures.stagger, count: p.failures.count, path: '/failures' },
      { id: 'conclusion', kind: 'enter', at: p.conclusion.at, dur: p.conclusion.dur, path: '/conclusion' },
    ]);
  };

  /* ══ tpl.concept — 방사형 네트워크 + 라운드 목록 (S3 일반화) ════════ */
  function conceptPlan(d) {
    var m = (d.rounds || []).length;
    return {
      center: { at: 0.6, dur: 0.6 },
      nodes: { at: 1.0, dur: 0.55, stagger: 0.18, count: (d.nodes || []).length },
      lines: { at: 2.6, dur: 0.6, stagger: 0.1, count: (d.nodes || []).length },
      dots: { at: 3.4, dur: 0.6 },
      rounds: { at: 5.4, dur: 0.6, stagger: 1.3, count: m },
      outcome: { at: 5.4 + m * 1.3, dur: 0.7 },
    };
  }
  function ConceptScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = conceptPlan(d);
    var dec = theme.component.decision;
    var chip = theme.component.chip;
    return (
      <FrameChrome label="개념" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        <RadialNetwork t={t} theme={theme} center={d.center} nodes={d.nodes}
          at={{ center: p.center.at, nodes: p.nodes.at, nodeStagger: p.nodes.stagger, lines: p.lines.at, lineStagger: p.lines.stagger, dots: p.dots.at }} />
        <div style={{ position: 'absolute', left: 1150, top: 350, width: 640, display: 'flex', flexDirection: 'column', gap: 26 }}>
          {(d.rounds || []).map(function (rd, i) {
            return (
              <div key={i} style={Object.assign({
                display: 'flex', gap: 22, alignItems: 'flex-start',
              }, rise(theme, t, p.rounds.at + i * p.rounds.stagger, p.rounds.dur, 20))}>
                <div style={{
                  width: 62, height: 62, borderRadius: theme.radius.chip,
                  background: chip.accentBg, color: chip.accentFg,
                  fontSize: theme.type.emphasis, fontWeight: 800,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
                }}>{rd.chip}</div>
                <div>
                  <div style={{ fontSize: theme.type.item, fontWeight: 800 }}>{rd.name}</div>
                  <div style={{ fontSize: theme.type.note, color: theme.color.sub, marginTop: 6, lineHeight: 1.4 }}>{rd.desc}</div>
                </div>
              </div>
            );
          })}
          {d.outcome && (
            <div style={Object.assign({
              display: 'flex', gap: 22, alignItems: 'center', marginTop: 6,
            }, rise(theme, t, p.outcome.at, p.outcome.dur, 20))}>
              <div style={{ width: 62, textAlign: 'center', fontSize: theme.type.chipLg, color: theme.color.faint, flexShrink: 0 }}>↓</div>
              <div style={{ flex: 1, background: dec.bg, color: dec.fg, borderRadius: 18, padding: '22px 28px', boxShadow: dec.shadow }}>
                <div style={{ fontSize: theme.type.lead, fontWeight: 800 }}>{d.outcome.title}</div>
                <div style={{ fontSize: theme.type.caption, opacity: 0.85, marginTop: 6 }}>{d.outcome.desc}</div>
              </div>
            </div>
          )}
        </div>
      </FrameChrome>
    );
  }
  ConceptScene.nat = 11;
  ConceptScene.schedule = function (d) {
    var p = conceptPlan(d);
    return FRAME_SCHED.concat([
      { id: 'center', kind: 'enter', at: p.center.at, dur: p.center.dur, path: '/center' },
      { id: 'nodes', kind: 'enter', at: p.nodes.at, dur: p.nodes.dur, stagger: p.nodes.stagger, count: p.nodes.count, path: '/nodes' },
      { id: 'lines', kind: 'enter', at: p.lines.at, dur: p.lines.dur, stagger: p.lines.stagger, count: p.lines.count },
      { id: 'link-dots', kind: 'enter', at: p.dots.at, dur: p.dots.dur },
      { id: 'rounds', kind: 'enter', at: p.rounds.at, dur: p.rounds.dur, stagger: p.rounds.stagger, count: p.rounds.count, path: '/rounds' },
      { id: 'outcome', kind: 'enter', at: p.outcome.at, dur: p.outcome.dur, path: '/outcome' },
    ]);
  };

  /* ══ tpl.process — 순차 점등 스텝 카드 그리드 (S4 일반화) ═══════════ */
  function processPlan(d) {
    var n = (d.steps || []).length;
    var lightStagger = 2.35;
    var lightAt = 2.0;
    return {
      appear: { at: 1.0, dur: 0.6, stagger: 0.1, count: n },
      rail: { at: lightAt, dur: (n - 1) * lightStagger + 1.75 },
      light: { at: lightAt, dur: 0.55, stagger: lightStagger, count: n },
      footnote: { at: lightAt + (n - 1) * lightStagger + 2.25, dur: 0.7 },
    };
  }
  function ProcessScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = processPlan(d);
    return (
      <FrameChrome label="절차" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        <StepCardGrid t={t} theme={theme} steps={d.steps}
          at={{ appear: p.appear.at, appearStagger: p.appear.stagger, light: p.light.at, lightStagger: p.light.stagger, railDur: p.rail.dur }} />
        <NoteLine t={t} theme={theme} data={d.footnote} top={theme.component.processNote.top} at={p.footnote.at} />
      </FrameChrome>
    );
  }
  ProcessScene.nat = 18;
  ProcessScene.schedule = function (d) {
    var p = processPlan(d);
    return FRAME_SCHED.concat([
      { id: 'cards', kind: 'enter', at: p.appear.at, dur: p.appear.dur, stagger: p.appear.stagger, count: p.appear.count, path: '/steps' },
      { id: 'rail', kind: 'enter', at: p.rail.at, dur: p.rail.dur },
      { id: 'step-light', kind: 'enter', at: p.light.at, dur: p.light.dur, stagger: p.light.stagger, count: p.light.count },
      { id: 'footnote', kind: 'enter', at: p.footnote.at, dur: p.footnote.dur, path: '/footnote' },
    ]);
  };

  /* ══ tpl.differentiator — 반박 흐름 + 체크마크 수렴 (S5 일반화) ═════ */
  function diffPlan(d) {
    var n = (d.flow || []).length;
    var m = ((d.converge || {}).members || []).length;
    var cardAt = function (i) { return 1.1 + i * 3.2; };
    var convergeAt = cardAt(n) + 0.2;
    var ckAt = convergeAt + 0.9;
    var verdictAt = ckAt + m * 0.18 + 0.5;
    return {
      cardAt: cardAt,
      tagAt: function (i) { return cardAt(i) + 1.6; },
      arrowAt: function (i) { return cardAt(i) + 2.4; },
      converge: { at: convergeAt, checks: ckAt, checkStagger: 0.18, verdict: verdictAt },
      footnote: { at: verdictAt + 0.9, dur: 0.7 },
      flowCount: n, memberCount: m,
    };
  }
  function DifferentiatorScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = diffPlan(d);
    var cards = (d.flow || []).map(function (c, i) {
      return Object.assign({}, c, { at: p.cardAt(i), tagAt: p.tagAt(i) });
    });
    var arrowAts = [];
    for (var i = 0; i < cards.length; i++) arrowAts.push(p.arrowAt(i));
    var cv = d.converge || {};
    return (
      <FrameChrome label="차별점" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        <RebuttalFlow t={t} theme={theme} cards={cards} extraArrow arrowAt={arrowAts} />
        <CheckmarkConverge t={t} theme={theme}
          chip={cv.chip} label={cv.label} members={cv.members} verdict={cv.verdict}
          left={theme.layout.marginX + cards.length * theme.component.flow.colPitch}
          at={{ card: p.converge.at, checks: p.converge.checks, checkStagger: p.converge.checkStagger, verdict: p.converge.verdict }} />
        <NoteLine t={t} theme={theme} data={d.footnote} top={theme.component.flow.noteTop} at={p.footnote.at} />
      </FrameChrome>
    );
  }
  DifferentiatorScene.nat = 13;
  DifferentiatorScene.schedule = function (d) {
    var p = diffPlan(d);
    var out = FRAME_SCHED.slice();
    for (var i = 0; i < p.flowCount; i++) {
      out.push({ id: 'flow-' + i, kind: 'enter', at: p.cardAt(i), dur: 0.7, path: '/flow/' + i });
      out.push({ id: 'flow-' + i + '-tag', kind: 'enter', at: p.tagAt(i), dur: 0.5, path: '/flow/' + i + '/tag' });
    }
    out.push({ id: 'converge', kind: 'enter', at: p.converge.at, dur: 0.7, path: '/converge' });
    out.push({ id: 'checks', kind: 'enter', at: p.converge.checks, dur: 0.4, stagger: p.converge.checkStagger, count: p.memberCount });
    out.push({ id: 'verdict', kind: 'enter', at: p.converge.verdict, dur: 0.5, path: '/converge/verdict' });
    out.push({ id: 'footnote', kind: 'enter', at: p.footnote.at, dur: p.footnote.dur, path: '/footnote' });
    return out;
  };

  /* ══ tpl.proof — 3열 사례 카드 + 배지 (S6 일반화) ═══════════════════ */
  function proofPlan(d) {
    var n = (d.cases || []).length;
    var caseAt = function (i) { return 1.1 + i * 3.6; };
    return {
      caseAt: caseAt,
      footnote: { at: caseAt(n - 1) + 4.0, dur: 0.7 },
      count: n,
    };
  }
  function ProofScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = proofPlan(d);
    var g = theme.component.caseTrio;
    var chip = theme.component.chip;
    return (
      <FrameChrome label="실증" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {(d.cases || []).map(function (c, i) {
          var at = p.caseAt(i);
          var bTone = toneOf(theme.component.tag, c.badgeTone === 'success' ? 'success' : 'info', 'info');
          if (c.badgeTone === 'success') bTone = { bg: chip.successBg, fg: chip.successFg };
          return (
            <div key={i} style={Object.assign({
              position: 'absolute', left: theme.layout.marginX + i * g.colPitch, top: g.top,
              width: g.cardW, height: g.cardH,
              background: theme.component.card.bg, border: '1px solid ' + theme.component.card.border,
              borderRadius: theme.radius.card, boxShadow: theme.component.card.shadow,
              padding: '34px 36px', boxSizing: 'border-box', display: 'flex', flexDirection: 'column',
            }, rise(theme, t, at, 0.7, 30))}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{
                  background: chip.accentBg, color: chip.accentFg,
                  fontSize: theme.type.caption, fontWeight: 800, padding: '8px 18px',
                  borderRadius: theme.radius.pill,
                }}>{c.rpt}</div>
                <div style={{ fontSize: theme.type.caption, color: theme.color.faint, fontWeight: 600 }}>{c.meta}</div>
              </div>
              <div style={Object.assign({
                marginTop: 30, fontSize: theme.type.caseTitle, fontWeight: 800,
                lineHeight: 1.3, whiteSpace: 'pre-line',
              }, rise(theme, t, at + 0.2, 0.6, 14))}>{c.title}</div>
              <div style={Object.assign({
                marginTop: 22, fontSize: theme.type.body, color: theme.color.sub, lineHeight: 1.55,
              }, rise(theme, t, at + 0.35, 0.6, 14))}>{c.desc}</div>
              <div style={{
                marginTop: 'auto', alignSelf: 'flex-start', background: bTone.bg, color: bTone.fg,
                fontSize: theme.type.caption, fontWeight: 800, padding: '12px 22px',
                borderRadius: theme.radius.pill,
                opacity: A(t, at + 0.9, 0.5, 0, 1),
                transform: 'translateY(' + A(t, at + 0.9, 0.5, 10, 0) + 'px)',
              }}>{c.badge}</div>
            </div>
          );
        })}
        <NoteLine t={t} theme={theme} data={d.footnote} top={g.noteTop} at={p.footnote.at} />
      </FrameChrome>
    );
  }
  ProofScene.nat = 15;
  ProofScene.schedule = function (d) {
    var p = proofPlan(d);
    var out = FRAME_SCHED.slice();
    for (var i = 0; i < p.count; i++) {
      var at = p.caseAt(i);
      out.push({ id: 'case-' + i, kind: 'enter', at: at, dur: 0.7, path: '/cases/' + i });
      out.push({ id: 'case-' + i + '-badge', kind: 'enter', at: at + 0.9, dur: 0.5, path: '/cases/' + i + '/badge' });
    }
    out.push({ id: 'footnote', kind: 'enter', at: p.footnote.at, dur: p.footnote.dur, path: '/footnote' });
    return out;
  };

  /* ══ tpl.closing — 통계 트리오 → 타이틀 + CTA 필 (S7 일반화) ════════ */
  function closingPlan(d) {
    return {
      stats: { at: 0.7, dur: 0.7, stagger: 0.8, count: (d.stats || []).length },
      statsExit: { at: 5.7, dur: 0.7 },
      line: { at: 6.7, dur: 0.8 },
      title: { at: 7.0, dur: 0.9 },
      subtitle: { at: 7.9, dur: 0.7 },
      ctas: { at: 8.9, dur: 0.7 },
      footnote: { at: 9.8, dur: 0.7 },
    };
  }
  function ClosingScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = closingPlan(d);
    return (
      <FrameChrome label="클로징" t={t} theme={theme} hideFooter>
        <StatTrio t={t} theme={theme} stats={d.stats}
          at={{ start: p.stats.at, stagger: p.stats.stagger }} exit={{ at: p.statsExit.at, dur: p.statsExit.dur }} />
        <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 34 }}>
          <div style={{ width: A(t, p.line.at, p.line.dur, 0, 120), height: 5, background: theme.color.blue, borderRadius: 3 }}></div>
          <div style={Object.assign({
            fontSize: theme.type.display, fontWeight: 800, letterSpacing: '-0.03em',
          }, rise(theme, t, p.title.at, p.title.dur, 30))}>
            <AccentText data={d.title} accentColor={theme.color.blue} />
          </div>
          <div style={Object.assign({
            fontSize: theme.type.subtitle, color: theme.color.sub, fontWeight: 500,
          }, rise(theme, t, p.subtitle.at))}>{d.subtitle}</div>
          <div style={Object.assign({ display: 'flex', gap: 24, marginTop: 14 }, rise(theme, t, p.ctas.at))}>
            {(d.ctas || []).map(function (c, i) {
              return <CtaPill key={i} theme={theme} text={c.text} accent={c.accent} />;
            })}
          </div>
          {d.footnote && (
            <div style={{
              fontSize: theme.type.caption, color: theme.color.faint, marginTop: 20,
              opacity: A(t, p.footnote.at, p.footnote.dur, 0, 1),
            }}>{d.footnote}</div>
          )}
        </div>
      </FrameChrome>
    );
  }
  ClosingScene.nat = 12;
  ClosingScene.schedule = function (d) {
    var p = closingPlan(d);
    return [
      { id: 'stats', kind: 'enter', at: p.stats.at, dur: p.stats.dur, stagger: p.stats.stagger, count: p.stats.count, path: '/stats' },
      { id: 'stats-exit', kind: 'exit', at: p.statsExit.at, dur: p.statsExit.dur },
      { id: 'line', kind: 'enter', at: p.line.at, dur: p.line.dur },
      { id: 'title', kind: 'enter', at: p.title.at, dur: p.title.dur, path: '/title' },
      { id: 'subtitle', kind: 'enter', at: p.subtitle.at, dur: p.subtitle.dur, path: '/subtitle' },
      { id: 'ctas', kind: 'enter', at: p.ctas.at, dur: p.ctas.dur, path: '/ctas' },
      { id: 'footnote', kind: 'enter', at: p.footnote.at, dur: p.footnote.dur, path: '/footnote' },
    ];
  };

  OMX.templates = Object.assign(OMX.templates || {}, {
    OpeningScene: OpeningScene,
    ProblemScene: ProblemScene,
    ConceptScene: ConceptScene,
    ProcessScene: ProcessScene,
    DifferentiatorScene: DifferentiatorScene,
    ProofScene: ProofScene,
    ClosingScene: ClosingScene,
  });
  // tpl.* id → 컴포넌트 매핑 (레지스트리 소비자용)
  OMX.templateIndex = Object.assign(OMX.templateIndex || {}, {
    'tpl.opening': OpeningScene,
    'tpl.problem': ProblemScene,
    'tpl.concept': ConceptScene,
    'tpl.process': ProcessScene,
    'tpl.differentiator': DifferentiatorScene,
    'tpl.proof': ProofScene,
    'tpl.closing': ClosingScene,
  });
})();
