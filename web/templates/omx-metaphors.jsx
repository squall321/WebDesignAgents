// 시각 은유 9종 — hwax-scenes.jsx 표현 코드를 데이터 props + theme 주입형으로 일반화한 컴포넌트 라이브러리 (window.OMX.metaphors)
// 모든 모션은 전달받은 t(localTime)의 순수 함수 — Math.random/Date/자체 타이머 금지.
(function () {
  'use strict';
  var Easing = window.Easing;
  var animate = window.animate;
  var OMX = (window.OMX = window.OMX || {});

  // ── 마이크로 헬퍼 ─────────────────────────────────────────────────────
  function easeOf(name) { return (name && Easing[name]) || Easing.easeOutCubic; }
  function A(t, start, dur, from, to, ease) {
    return animate({ from: from, to: to, start: start, end: start + dur, ease: ease || Easing.easeOutCubic })(t);
  }
  // theme.motion.rise 프리셋 기반 등장 스타일 — {opacity, transform}
  function rise(theme, t, at, dur, dy) {
    var m = theme.motion.rise;
    var d = dur == null ? m.dur : dur;
    var y = dy == null ? m.dy : dy;
    var e = easeOf(m.ease);
    return {
      opacity: A(t, at, d, 0, 1, e),
      transform: 'translateY(' + A(t, at, d, y, 0, e) + 'px)',
    };
  }
  function toneOf(map, tone, fallback) {
    var key = tone || fallback;
    return { bg: map[key + 'Bg'], fg: map[key + 'Fg'] };
  }

  // ── dot-grid — 움직이는 점 텍스처 배경 ───────────────────────────────
  function DotGrid(props) {
    var t = props.t, theme = props.theme;
    return (
      <div data-qa-clip-ok="true" style={{
        position: 'absolute', inset: -60, opacity: 0.55,
        backgroundImage: 'radial-gradient(' + theme.component.frame.dot + ' 1.6px, transparent 1.6px)',
        backgroundSize: '46px 46px',
        transform: 'translateY(' + ((t * 2) % 46) + 'px)',
      }}></div>
    );
  }

  // ── frame-chrome — 씬 공통 크롬(킥커/타이틀/푸터/도트 그리드) ────────
  // props: {t, theme, label, kicker, title, titleSize?, frame?{brand,idx,total}, hideFooter?, at?, children}
  function FrameChrome(props) {
    var t = props.t, theme = props.theme;
    var fr = theme.component.frame;
    var L = theme.layout;
    var at = props.at || {};
    var kickerAt = at.kicker != null ? at.kicker : 0.15;
    var titleAt = at.title != null ? at.title : 0.35;
    var footerAt = at.footer != null ? at.footer : 0.5;
    var meta = props.frame || {};
    var showFooter = !props.hideFooter && (meta.brand || meta.idx);
    return (
      <div data-screen-label={(props.label || '') + ' @' + Math.floor(t) + 's'} style={{
        position: 'absolute', inset: 0, background: fr.bg, fontFamily: theme.font.base,
        color: fr.ink, overflow: 'hidden', wordBreak: 'keep-all',
      }}>
        <DotGrid t={t} theme={theme} />
        <div style={{ position: 'absolute', inset: 0, background: fr.glow }}></div>
        {props.kicker && (
          <div style={Object.assign({
            position: 'absolute', left: L.marginX, top: L.kickerTop,
            display: 'flex', alignItems: 'center', gap: L.kickerGap,
          }, rise(theme, t, kickerAt))}>
            <div style={{ width: L.kickerRuleW, height: L.kickerRuleH, background: fr.rule, borderRadius: 3 }}></div>
            <div style={{ fontSize: theme.type.body, fontWeight: 700, letterSpacing: '0.18em', color: fr.kicker }}>{props.kicker}</div>
          </div>
        )}
        {props.title && (
          <div style={Object.assign({
            position: 'absolute', left: L.marginX, top: L.titleTop,
            fontSize: props.titleSize || theme.type.sectionTitle, fontWeight: 800,
            letterSpacing: '-0.02em', lineHeight: 1.18,
          }, rise(theme, t, titleAt))}>{props.title}</div>
        )}
        {props.children}
        {showFooter && (
          <div style={{
            position: 'absolute', left: L.marginX, right: L.marginX, bottom: L.footerBottom,
            borderTop: '1px solid ' + fr.line, paddingTop: L.footerPadTop,
            display: 'flex', justifyContent: 'space-between',
            fontSize: theme.type.caption, color: fr.footerInk,
            opacity: A(t, footerAt, 0.8, 0, 1),
          }}>
            <span>{meta.brand || ''}</span>
            <span>{meta.idx ? meta.idx + ' / ' + (meta.total || '') : ''}</span>
          </div>
        )}
      </div>
    );
  }

  // ── chatbot-mockup — 챗봇 목업 + 스켈레톤 답변 + 판정 필 ─────────────
  // props: {t, theme, windowLabel, question, barWidths(고정 배열 — 난수 금지), verdict,
  //         at:{panel,question,answer,bars,verdict}, left?, top?, width?, height?}
  function ChatbotMockup(props) {
    var t = props.t, theme = props.theme;
    var ch = theme.component.chat;
    var card = theme.component.card;
    var at = props.at || {};
    var atPanel = at.panel != null ? at.panel : 0.9;
    var atQ = at.question != null ? at.question : atPanel + 0.4;
    var atA = at.answer != null ? at.answer : atPanel + 1.8;
    var atBars = at.bars != null ? at.bars : atA + 0.3;
    var atV = at.verdict != null ? at.verdict : atBars + 1.8;
    var barStagger = at.barStagger != null ? at.barStagger : theme.motion.stagger.bar;
    var bars = props.barWidths || [500, 560, 460, 320];
    return (
      <div style={Object.assign({
        position: 'absolute', left: props.left != null ? props.left : theme.layout.marginX,
        top: props.top != null ? props.top : theme.layout.contentTop,
        width: props.width || 800, height: props.height || 490,
        background: ch.panelBg, border: '1px solid ' + ch.panelBorder,
        borderRadius: theme.radius.card, boxShadow: card.shadow,
      }, rise(theme, t, atPanel))}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '20px 28px', borderBottom: '1px solid ' + ch.panelBorder }}>
          {[0, 1, 2].map(function (i) {
            return <div key={i} style={{ width: 14, height: 14, borderRadius: theme.radius.pill, background: ch.headerDot }}></div>;
          })}
          <div style={{ marginLeft: 12, fontSize: theme.type.caption, color: ch.headerFg, fontWeight: 600 }}>{props.windowLabel}</div>
        </div>
        <div style={{ padding: '30px 34px', display: 'flex', flexDirection: 'column', gap: 26 }}>
          <div style={Object.assign({
            alignSelf: 'flex-end', maxWidth: 560, background: ch.questionBg, color: ch.questionFg,
            borderRadius: '20px 20px 4px 20px', padding: '20px 26px',
            fontSize: theme.type.chat, fontWeight: 600,
          }, rise(theme, t, atQ, 0.6, 18))}>{props.question}</div>
          <div style={Object.assign({
            alignSelf: 'flex-start', width: 620, background: ch.answerBg,
            borderRadius: '20px 20px 20px 4px', padding: '26px 28px',
          }, rise(theme, t, atA, 0.6, 18))}>
            {bars.map(function (w, i) {
              return (
                <div key={i} style={{
                  width: A(t, atBars + i * barStagger, 0.5, 0, w), height: 16,
                  borderRadius: theme.radius.bar, background: ch.skelBar,
                  marginBottom: i === bars.length - 1 ? 0 : 16,
                }}></div>
              );
            })}
          </div>
          {props.verdict && (
            <div style={Object.assign({
              alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 12,
              background: ch.verdictBg, border: '1px solid ' + ch.verdictBorder,
              borderRadius: theme.radius.pill, padding: '12px 24px',
            }, rise(theme, t, atV, 0.6, 14))}>
              <div style={{ width: 12, height: 12, borderRadius: theme.radius.pill, background: ch.verdictDot }}></div>
              <span style={{ fontSize: theme.type.note, color: ch.verdictFg, fontWeight: 600 }}>{props.verdict}</span>
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── radial-network — 중앙 질문 → 방사형 전문가 노드 네트워크 ─────────
  // props: {t, theme, center, nodes:[{ini,name}], left?, top?, cx?, cy?,
  //         at:{center,nodes,nodeStagger,lines,lineStagger,dots}}
  function RadialNetwork(props) {
    var t = props.t, theme = props.theme;
    var net = theme.component.network;
    var at = props.at || {};
    var atCenter = at.center != null ? at.center : 0.6;
    var atNodes = at.nodes != null ? at.nodes : 1.0;
    var nodeStagger = at.nodeStagger != null ? at.nodeStagger : theme.motion.stagger.icon;
    var atLines = at.lines != null ? at.lines : 2.6;
    var lineStagger = at.lineStagger != null ? at.lineStagger : 0.1;
    var atDots = at.dots != null ? at.dots : 3.4;
    var nodes = props.nodes || [];
    var n = nodes.length;
    var cx = props.cx != null ? props.cx : 480;
    var cy = props.cy != null ? props.cy : 330;
    var r = props.r != null ? props.r : net.r;
    var popEase = easeOf(theme.motion.pop.ease);
    return (
      <div style={{
        position: 'absolute', left: props.left != null ? props.left : 130,
        top: props.top != null ? props.top : theme.layout.contentTop,
        width: props.width || 960, height: props.height || 640,
      }}>
        {nodes.map(function (p, i) {
          var deg = (360 / n) * i - 90;
          var lw = r - net.lineTrim;
          return (
            <div key={'l' + i} style={{
              position: 'absolute', left: cx, top: cy, width: lw, height: 2, background: net.line,
              transformOrigin: 'left center',
              transform: 'rotate(' + deg + 'deg) translateX(64px) scaleX(' + A(t, atLines + i * lineStagger, 0.6, 0, 1) + ')',
            }}>
              <div style={{
                position: 'absolute', top: -5,
                left: (((Math.sin(t * 1.5 + i * 1.3) + 1) / 2) * 88) + '%',
                width: net.travelDotSize, height: net.travelDotSize,
                borderRadius: theme.radius.pill, background: net.travelDot,
                opacity: A(t, atDots, 0.6, 0, 0.9),
              }}></div>
            </div>
          );
        })}
        {nodes.map(function (p, i) {
          var ang = ((360 / n) * i - 90) * Math.PI / 180;
          var x = cx + Math.cos(ang) * r, y = cy + Math.sin(ang) * r;
          var pop = A(t, atNodes + i * nodeStagger, 0.55, 0, 1, popEase);
          var half = Math.round(net.nodeSize / 2) + 6;
          return (
            <div key={i} style={{ position: 'absolute', left: x - half, top: y - half, width: half * 2, textAlign: 'center', opacity: pop, transform: 'scale(' + pop + ')' }}>
              <div style={{
                width: net.nodeSize, height: net.nodeSize, margin: '0 auto',
                borderRadius: theme.radius.pill, background: net.nodeBg,
                border: '2px solid ' + net.nodeBorder, boxShadow: theme.component.card.shadow,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: theme.type.caseTitle, fontWeight: 800, color: net.nodeFg,
              }}>{p.ini}</div>
              <div style={{
                marginTop: 10, fontSize: theme.type.caption, fontWeight: 600, color: net.nameFg,
                whiteSpace: 'nowrap', textAlign: 'center',
                width: net.nodeSize + 92, marginLeft: -(92 / 2),
              }}>{p.name}</div>
            </div>
          );
        })}
        <div style={Object.assign({
          position: 'absolute', left: cx - net.centerW / 2, top: cy - net.centerH / 2,
          width: net.centerW, height: net.centerH, borderRadius: theme.radius.box,
          background: net.centerBg, color: net.centerFg,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: theme.type.chipLg, fontWeight: 800, boxShadow: net.centerShadow,
        }, rise(theme, t, atCenter, 0.6, 14))}>{props.center}</div>
      </div>
    );
  }

  // ── step-card-grid — 순차 점등 스텝 카드 그리드 (+진행 레일) ─────────
  // props: {t, theme, steps:[{n,name,desc}], cols?, at:{appear,appearStagger,light,lightStagger,railDur}}
  function StepCardGrid(props) {
    var t = props.t, theme = props.theme;
    var g = theme.component.stepGrid;
    var L = theme.layout;
    var at = props.at || {};
    var steps = props.steps || [];
    var n = steps.length;
    var cols = props.cols || 3;
    var atAppear = at.appear != null ? at.appear : 1.0;
    var appearStagger = at.appearStagger != null ? at.appearStagger : 0.1;
    var atLight = at.light != null ? at.light : 2.0;
    var lightStagger = at.lightStagger != null ? at.lightStagger : theme.motion.stagger.step;
    var railDur = at.railDur != null ? at.railDur : (n - 1) * lightStagger + 1.75;
    return (
      <React.Fragment>
        <div style={{ position: 'absolute', left: L.marginX, top: g.railTop, width: g.railW, height: g.railH, background: g.railBase, borderRadius: 3 }}>
          <div style={{ width: A(t, atLight, railDur, 0, g.railW, easeOf(theme.motion.fill.ease)), height: g.railH, background: g.railFill, borderRadius: 3 }}></div>
        </div>
        {steps.map(function (s, i) {
          var col = i % cols, row = Math.floor(i / cols);
          var app = rise(theme, t, atAppear + i * appearStagger, 0.6, 22);
          var on = A(t, atLight + i * lightStagger, 0.55, 0, 1);
          return (
            <div key={i} style={{
              position: 'absolute', left: L.marginX + col * g.colPitch, top: g.top + row * g.rowPitch,
              width: g.cardW, height: g.cardH,
              background: theme.component.card.bg, borderRadius: theme.radius.panel,
              padding: '30px 32px', boxSizing: 'border-box',
              border: '2px solid ' + (on > 0.5 ? g.activeBorder : g.idleBorder),
              boxShadow: on > 0.5 ? g.activeShadow : g.idleShadow,
              opacity: app.opacity * (0.45 + 0.55 * on),
              transform: app.transform + ' translateY(' + (-6 * on) + 'px)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
                <div style={{
                  width: 62, height: 62, borderRadius: theme.radius.chip,
                  fontSize: theme.type.emphasis, fontWeight: 800,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: on > 0.5 ? g.numActiveBg : g.numIdleBg,
                  color: on > 0.5 ? g.numActiveFg : g.numIdleFg,
                }}>{s.n}</div>
                <div style={{ fontSize: theme.type.cardTitle, fontWeight: 800 }}>{s.name}</div>
              </div>
              <div style={{ marginTop: 22, fontSize: theme.type.body, color: theme.color.sub, lineHeight: 1.5 }}>{s.desc}</div>
            </div>
          );
        })}
      </React.Fragment>
    );
  }

  // ── rebuttal-flow — R1→R2 반박 카드 흐름 (+열 사이 화살표) ───────────
  // props: {t, theme, cards:[{chip,chipTone,label,quote,tag,tagTone,at,tagAt}],
  //         extraArrow?, arrowAt:(i)=>sec 또는 배열}
  function RebuttalFlow(props) {
    var t = props.t, theme = props.theme;
    var f = theme.component.flow;
    var L = theme.layout;
    var cards = props.cards || [];
    var arrowCount = cards.length - 1 + (props.extraArrow ? 1 : 0);
    var arrowAts = props.arrowAt || [];
    var tagM = theme.motion.tag;
    var tagE = easeOf(tagM.ease);
    return (
      <React.Fragment>
        {cards.map(function (c, i) {
          var chipTone = toneOf(theme.component.chip, c.chipTone, 'accent');
          var tagTone = toneOf(theme.component.tag, c.tagTone, 'info');
          var cardAt = c.at != null ? c.at : 1.1 + i * 3.2;
          var tagAt = c.tagAt != null ? c.tagAt : cardAt + 1.6;
          return (
            <div key={i} style={{ position: 'absolute', left: L.marginX + i * f.colPitch, top: f.top, width: f.cardW }}>
              <div style={Object.assign({
                background: theme.component.card.bg, border: '1px solid ' + theme.component.card.border,
                borderRadius: theme.radius.panel, boxShadow: theme.component.card.shadow,
                padding: '30px 32px', minHeight: f.minH, boxSizing: 'border-box',
              }, rise(theme, t, cardAt))}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div style={{
                    width: 56, height: 56, borderRadius: theme.radius.tag,
                    background: chipTone.bg, color: chipTone.fg,
                    fontSize: theme.type.note, fontWeight: 800,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>{c.chip}</div>
                  <div style={{ fontSize: theme.type.note, color: theme.color.sub, fontWeight: 600 }}>{c.label}</div>
                </div>
                <div style={{ marginTop: 26, fontSize: theme.type.item, fontWeight: 700, lineHeight: 1.45 }}>{c.quote}</div>
                {c.tag && (
                  <div style={{
                    marginTop: 26, display: 'inline-block', background: tagTone.bg, color: tagTone.fg,
                    fontSize: theme.type.caption, fontWeight: 700, padding: '10px 20px',
                    borderRadius: theme.radius.pill,
                    opacity: A(t, tagAt, tagM.dur, 0, 1, tagE),
                    transform: 'translateY(' + A(t, tagAt, tagM.dur, tagM.dy, 0, tagE) + 'px)',
                  }}>{c.tag}</div>
                )}
              </div>
            </div>
          );
        })}
        {Array.apply(null, Array(Math.max(0, arrowCount))).map(function (_, i) {
          var aAt = arrowAts[i] != null ? arrowAts[i] : 3.5 + i * 3.3;
          return (
            <div key={'a' + i} style={{
              position: 'absolute', left: L.marginX + f.cardW + 14 + i * f.colPitch, top: f.arrowY,
              fontSize: theme.type.arrow, color: f.arrowFg, opacity: A(t, aAt, 0.5, 0, 1),
            }}>→</div>
          );
        })}
      </React.Fragment>
    );
  }

  // ── checkmark-converge — 아바타 체크마크 순차 점등 수렴 카드 ─────────
  // props: {t, theme, chip, chipTone, label, members:[{ini}], verdict, verdictTone,
  //         left?, at:{card,checks,checkStagger,verdict}}
  function CheckmarkConverge(props) {
    var t = props.t, theme = props.theme;
    var f = theme.component.flow;
    var cv = theme.component.converge;
    var at = props.at || {};
    var cardAt = at.card != null ? at.card : 7.6;
    var ckAt = at.checks != null ? at.checks : cardAt + 0.9;
    var ckStagger = at.checkStagger != null ? at.checkStagger : theme.motion.stagger.icon;
    var members = props.members || [];
    var verdictAt = at.verdict != null ? at.verdict : ckAt + members.length * ckStagger + 0.5;
    var chipTone = toneOf(theme.component.chip, props.chipTone, 'success');
    var verdictTone = toneOf(theme.component.tag, props.verdictTone, 'success');
    var popE = easeOf(theme.motion.pop.ease);
    var tagM = theme.motion.tag;
    return (
      <div style={{ position: 'absolute', left: props.left != null ? props.left : theme.layout.marginX + 2 * f.colPitch, top: f.top, width: f.cardW }}>
        <div style={Object.assign({
          background: theme.component.card.bg, border: '1px solid ' + theme.component.card.border,
          borderRadius: theme.radius.panel, boxShadow: theme.component.card.shadow,
          padding: '30px 32px', minHeight: f.minH, boxSizing: 'border-box',
        }, rise(theme, t, cardAt))}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{
              width: 56, height: 56, borderRadius: theme.radius.tag,
              background: chipTone.bg, color: chipTone.fg,
              fontSize: theme.type.note, fontWeight: 800,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>{props.chip}</div>
            <div style={{ fontSize: theme.type.note, color: theme.color.sub, fontWeight: 600 }}>{props.label}</div>
          </div>
          <div style={{ marginTop: 30, display: 'flex', gap: 18 }}>
            {members.map(function (p, i) {
              var ck = A(t, ckAt + i * ckStagger, 0.4, 0, 1, popE);
              return (
                <div key={i} data-qa-clip-ok="true" style={{
                  position: 'relative', width: cv.avatarSize, height: cv.avatarSize,
                  borderRadius: theme.radius.pill, background: cv.avatarBg,
                  border: '2px solid ' + cv.avatarBorder,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontSize: theme.type.caption, fontWeight: 800, color: cv.avatarFg,
                }}>
                  {p.ini}
                  <div data-qa-icon="true" style={{
                    position: 'absolute', right: -7, bottom: -7, width: cv.checkSize, height: cv.checkSize,
                    borderRadius: theme.radius.pill, background: cv.checkBg, color: cv.checkFg,
                    fontSize: theme.type.iconCheck, fontWeight: 800,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    opacity: ck, transform: 'scale(' + ck + ')',
                  }}>✓</div>
                </div>
              );
            })}
          </div>
          {props.verdict && (
            <div style={{
              marginTop: 32, display: 'inline-block', background: verdictTone.bg, color: verdictTone.fg,
              fontSize: theme.type.note, fontWeight: 800, padding: '12px 24px',
              borderRadius: theme.radius.pill,
              opacity: A(t, verdictAt, tagM.dur, 0, 1),
              transform: 'translateY(' + A(t, verdictAt, tagM.dur, tagM.dy, 0) + 'px)',
            }}>{props.verdict}</div>
          )}
        </div>
      </div>
    );
  }

  // ── stat-trio — 대형 통계 가로 나열 (선택적 페이드아웃 퇴장) ─────────
  // props: {t, theme, stats:[{v,d}], at:{start,stagger}, exit:{at,dur}?}
  function StatTrio(props) {
    var t = props.t, theme = props.theme;
    var st = theme.component.statTrio;
    var at = props.at || {};
    var start = at.start != null ? at.start : 0.7;
    var stagger = at.stagger != null ? at.stagger : 0.8;
    var stats = props.stats || [];
    var style = {
      position: 'absolute', inset: 0, display: 'flex',
      alignItems: 'center', justifyContent: 'center', gap: st.gap,
    };
    if (props.exit) {
      var exitM = theme.motion.exit;
      var eDur = props.exit.dur != null ? props.exit.dur : exitM.dur;
      var out = A(t, props.exit.at, eDur, 1, 0, easeOf(exitM.ease));
      style.opacity = out;
      style.transform = 'translateY(' + ((1 - out) * exitM.dy) + 'px)';
    }
    return (
      <div style={style}>
        {stats.map(function (s, i) {
          return (
            <div key={i} style={Object.assign({ width: st.itemW, textAlign: 'center' }, rise(theme, t, start + i * stagger, 0.7, 26))}>
              <div style={{ fontSize: theme.type.sectionTitle, fontWeight: 800, color: st.valueFg, letterSpacing: '-0.02em' }}>{s.v}</div>
              <div style={{ fontSize: theme.type.emphasis, color: st.descFg, marginTop: 16 }}>{s.d}</div>
            </div>
          );
        })}
      </div>
    );
  }

  // ── cta-pill — 행동유도 필 (정적 — 모션은 부모가 rise 래핑) ──────────
  // props: {theme, text, accent}
  function CtaPill(props) {
    var theme = props.theme;
    var c = theme.component.ctaPill;
    return (
      <div style={{
        background: c.bg, border: '1.5px solid ' + c.border, borderRadius: theme.radius.pill,
        padding: '16px 34px', fontSize: theme.type.emphasis, fontWeight: 700, color: c.fg,
        boxShadow: c.shadow,
      }}>
        {props.text}{props.accent && <span style={{ color: c.accent, fontWeight: 800 }}>{props.accent}</span>}
      </div>
    );
  }

  OMX.metaphors = Object.assign(OMX.metaphors || {}, {
    'frame-chrome': FrameChrome,
    'dot-grid': DotGrid,
    'chatbot-mockup': ChatbotMockup,
    'radial-network': RadialNetwork,
    'step-card-grid': StepCardGrid,
    'rebuttal-flow': RebuttalFlow,
    'checkmark-converge': CheckmarkConverge,
    'stat-trio': StatTrio,
    'cta-pill': CtaPill,
  });
  // 은유 내부 공용 헬퍼 — 템플릿 계층이 재사용
  OMX.motion = Object.assign(OMX.motion || {}, { A: A, rise: rise, easeOf: easeOf, toneOf: toneOf });
})();
