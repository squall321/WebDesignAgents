// 세로 숏폼(1080×1920) 전용 씬 템플릿 4종 — vtpl.hook(각인)·vtpl.stack(적층)·vtpl.metric(단일 수치)·vtpl.cta(진입점). 가로 템플릿을 늘인 것이 아니라 세로 무대 고유 문법(위로 밀려 올라오는 적층·엄지 시야 중앙 배치·하단 UI 회피)으로 새로 저작.
// 계약: 엔진 props(localTime 등) + data + theme, 정적 .schedule(data)/.nat, frame-match(첫/끝 프레임 정지), 모든 모션은 t(localTime)의 순수 함수. 재사용은 엔진 원자(animate/Easing)·토큰(색·라운드·모션·폰트)뿐 — 크롬(v-frame/v-dot-column)은 세로 전용으로 신규.
(function () {
  'use strict';
  var OMX = (window.OMX = window.OMX || {});
  var Easing = window.Easing;
  var animate = window.animate;

  /* ══ 세로 무대 스펙 — 1080×1920 실측 역산값 ═══════════════════════════
     safe 72 : 포맷 계약 안전 여백(글리프 기준 하한). marginX 84 : 안전 여백 + 12 여유.
     type    : 최소 32(포맷 min_font) 위에서 세운 모바일 우선 스케일.
               폭 912 기준 1줄 수용 글자수 ≈ 912 / fontSize (한글 1em 가정) — 스키마 maxLength 의 역산 근거. */
  var V = {
    stage: { w: 1080, h: 1920 },
    safe: 72,
    marginX: 84,
    contentW: 912,
    kickerTop: 116,
    titleTop: 182,
    footerTextBottom: 88,
    footerRailBottom: 150,
    type: {
      caption: 32,   // 최소 폰트 = 포맷 하한 (킥커·캡션·구간 라벨)
      note: 36,      // 보조 설명·힌트
      body: 40,      // 본문·결론 필
      sub: 44,       // CTA 보조 줄
      item: 46,      // 카드 논지·진입점 필
      lead: 52,      // 수치 근거 한 줄
      title: 72,     // 씬 타이틀
      word: 76,      // 후킹 키워드 블록
      headline: 88,  // CTA 대형 문구
      hook: 96,      // 후킹 초대형 문구
    },
  };

  // ── 마이크로 헬퍼 — 엔진 원자 animate/Easing 로만 재구성 ─────────────
  function easeOf(name) { return (name && Easing[name]) || Easing.easeOutCubic; }
  function seg(t, at, dur, from, to, ease) {
    return animate({ from: from, to: to, start: at, end: at + dur, ease: ease || Easing.easeOutCubic })(t);
  }
  // 세로 기본 진입 — 아래에서 위로 (dy 양수 = 아래에서 출발)
  function riseUp(theme, t, at, dur, dy) {
    var m = theme.motion.rise;
    var d = dur == null ? m.dur : dur;
    var y = dy == null ? m.dy : dy;
    var e = easeOf(m.ease);
    return { opacity: seg(t, at, d, 0, 1, e), transform: 'translateY(' + seg(t, at, d, y, 0, e) + 'px)' };
  }
  // 토큰 pop 프리셋 — 배율 등장(opacity 는 1 클램프)
  function popIn(theme, t, at, dur, from) {
    var m = theme.motion.pop;
    var d = dur == null ? m.dur : dur;
    var f = from == null ? 0 : from;
    var v = seg(t, at, d, f, 1, easeOf(m.ease));
    var o = seg(t, at, d * 0.7, 0, 1);
    return { opacity: Math.min(1, o), transform: 'scale(' + v + ')' };
  }
  function toneOf(map, tone, fallback) {
    var key = tone || fallback;
    return { bg: map[key + 'Bg'], fg: map[key + 'Fg'] };
  }
  // 문장 텍스트 공통 — 세로 폭에서 한글 단어를 지키되 초과 시에만 분절
  var TEXT_WRAP = { wordBreak: 'keep-all', overflowWrap: 'break-word' };

  // {pre, accent, post} 강조 텍스트
  function VAccent(props) {
    var d = props.data || {};
    return (
      <React.Fragment>
        {d.pre}{d.accent && <span style={{ color: props.accentColor }}>{d.accent}</span>}{d.post}
      </React.Fragment>
    );
  }

  // ── 스케줄 유틸 — 정착 시각/기본 still (가로판과 동일 계약, 세로 파일 자립용) ──
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

  /* ══ v-dot-column — 세로 전용 점 텍스처 (위로 흐르는 질감) ═══════════
     가로판 dot-grid 가 아래로 흐르는 것과 반대 — 세로 숏폼의 "위로 넘어간다" 감각. */
  function VDotColumn(props) {
    var t = props.t, theme = props.theme;
    return (
      <div data-qa-clip-ok="true" style={{
        position: 'absolute', inset: -80, opacity: 0.5,
        backgroundImage: 'radial-gradient(' + theme.component.frame.dot + ' 2px, transparent 2px)',
        backgroundSize: '40px 40px',
        transform: 'translateY(' + (-((t * 4) % 40)) + 'px)',
      }}></div>
    );
  }

  /* ══ v-frame — 세로 전용 크롬 ════════════════════════════════════════
     가로 크롬(좌우 마진 140·좌측 정렬 킥커/타이틀)은 세로에 부적합 — 세로는 중앙 정렬,
     상단 1/5 헤더, 하단은 모바일 UI 가 덮는 구역이라 진행 표시만 남긴다. */
  function VFrame(props) {
    var t = props.t, theme = props.theme;
    var fr = theme.component.frame;
    var at = props.at || {};
    var kickerAt = at.kicker != null ? at.kicker : 0.15;
    var titleAt = at.title != null ? at.title : 0.3;
    var footerAt = at.footer != null ? at.footer : 0.6;
    var meta = props.frame || {};
    var total = +meta.total || 0;
    var idx = +meta.idx || 0;
    var showFooter = !props.hideFooter && (meta.brand || total > 0);
    var segs = [];
    for (var i = 0; i < total; i++) segs.push(i);
    var segW = total > 0 ? (V.contentW - (total - 1) * 12) / total : 0;
    return (
      <div data-screen-label={(props.label || '') + ' @' + Math.floor(t) + 's'} style={{
        position: 'absolute', inset: 0, background: fr.bg, fontFamily: theme.font.base,
        color: fr.ink, overflow: 'hidden',
      }}>
        <VDotColumn t={t} theme={theme} />
        <div data-qa-clip-ok="true" style={{
          position: 'absolute', left: -160, right: -160, top: -320, height: 1200,
          background: 'radial-gradient(circle at 50% 40%, ' + theme.color.blueSoft + ' 0%, transparent 62%)',
          opacity: 0.85,
        }}></div>
        {props.kicker && (
          <div style={Object.assign({
            position: 'absolute', left: V.marginX, right: V.marginX, top: V.kickerTop,
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 16,
          }, riseUp(theme, t, kickerAt, 0.6, 14))}>
            <div style={{ width: 40, height: 4, background: fr.rule, borderRadius: 2 }}></div>
            <div style={{
              fontSize: V.type.caption, fontWeight: 700, letterSpacing: '0.18em', color: fr.kicker,
            }}>{props.kicker}</div>
            <div style={{ width: 40, height: 4, background: fr.rule, borderRadius: 2 }}></div>
          </div>
        )}
        {props.title && (
          <div style={Object.assign({
            position: 'absolute', left: V.marginX, right: V.marginX, top: V.titleTop,
            fontSize: V.type.title, fontWeight: 800, letterSpacing: '-0.03em',
            lineHeight: 1.25, textAlign: 'center',
          }, TEXT_WRAP, riseUp(theme, t, titleAt, 0.7, 24))}>{props.title}</div>
        )}
        {props.children}
        {showFooter && (
          <React.Fragment>
            {total > 0 && (
              <div style={{
                position: 'absolute', left: V.marginX, bottom: V.footerRailBottom,
                display: 'flex', gap: 12, opacity: seg(t, footerAt, 0.8, 0, 1),
              }}>
                {segs.map(function (i) {
                  return <div key={i} style={{
                    width: segW, height: 8, borderRadius: 4,
                    background: i < idx ? theme.color.blue : fr.line,
                  }}></div>;
                })}
              </div>
            )}
            <div style={{
              position: 'absolute', left: V.marginX, right: V.marginX, bottom: V.footerTextBottom,
              display: 'flex', justifyContent: 'space-between',
              fontSize: V.type.caption, color: fr.footerInk,
              opacity: seg(t, footerAt, 0.8, 0, 1),
            }}>
              <span>{meta.brand || ''}</span>
              <span>{total > 0 ? idx + ' / ' + total : ''}</span>
            </div>
          </React.Fragment>
        )}
      </div>
    );
  }

  /* ══ vtpl.hook — 첫 3초 각인 ═════════════════════════════════════════
     상단 1/3 초대형 후킹 문구 → 중앙 핵심 시각 요소(파문 + 키워드 블록) → 하단 진행 힌트.
     하단 1700px 아래는 비운다 — 숏폼 플레이어 UI(자막·버튼)가 덮는 구역. */
  var HOOK = {
    lineTop: 200,
    ringCx: 540, ringCy: 1000, ringR: [240, 340, 440], ringOpacity: [0.9, 0.62, 0.4],
    cardW: 760, cardTop: 850, cardH: 300,
    captionTop: 1198,
    hintTop: 1420, beatLabelTop: 1508, beatBarTop: 1566,
  };
  function hookPlan(d) {
    var nb = ((d.hint || {}).beats || []).length;
    return {
      line: { at: 0.3, dur: 0.8 },
      rings: { at: 0.9, dur: 0.9, stagger: 0.12 },
      focus: { at: 1.15, dur: 0.6 },
      caption: { at: 1.75, dur: 0.6 },
      hint: { at: 2.4, dur: 0.6 },
      beats: { at: 2.7, dur: 0.5, stagger: 0.14, count: nb },
    };
  }
  function VHookScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = hookPlan(d);
    var focus = d.focus || {};
    var hint = d.hint || {};
    var beats = hint.beats || [];
    var dec = theme.component.decision;
    var nb = beats.length;
    var colW = nb > 0 ? (V.contentW - (nb - 1) * 16) / nb : 0;
    var cardIn = seg(t, p.focus.at, p.focus.dur, 0, 1, easeOf(theme.motion.pop.ease));
    return (
      <VFrame label="후킹" t={t} theme={theme} kicker={d.kicker} hideFooter at={{ kicker: 0.15 }}>
        <div style={Object.assign({
          position: 'absolute', left: V.marginX, right: V.marginX, top: HOOK.lineTop,
          fontSize: V.type.hook, fontWeight: 800, letterSpacing: '-0.035em',
          lineHeight: 1.16, textAlign: 'center',
        }, TEXT_WRAP, riseUp(theme, t, p.line.at, p.line.dur, 30))}>
          <VAccent data={d.line} accentColor={theme.color.blue} />
        </div>

        {HOOK.ringR.map(function (r, i) {
          var at = p.rings.at + i * p.rings.stagger;
          return (
            <div key={'r' + i} data-qa-clip-ok="true" style={{
              position: 'absolute', left: HOOK.ringCx - r, top: HOOK.ringCy - r,
              width: r * 2, height: r * 2, borderRadius: theme.radius.pill,
              border: '2px solid ' + theme.color.blueBorder,
              opacity: seg(t, at, p.rings.dur, 0, HOOK.ringOpacity[i]),
              transform: 'scale(' + seg(t, at, p.rings.dur + 0.2, 0.72, 1) + ')',
            }}></div>
          );
        })}
        <div data-qa-clip-ok="true" style={{
          position: 'absolute', left: HOOK.ringCx - 320, top: HOOK.ringCy - 320,
          width: 640, height: 640, borderRadius: theme.radius.pill,
          background: 'radial-gradient(circle, ' + theme.color.blueSoft + ' 0%, transparent 70%)',
          opacity: seg(t, p.rings.at, 1.0, 0, 1),
        }}></div>

        <div style={{
          position: 'absolute', left: (V.stage.w - HOOK.cardW) / 2, top: HOOK.cardTop,
          width: HOOK.cardW, height: HOOK.cardH, boxSizing: 'border-box',
          background: dec.bg, color: dec.fg, borderRadius: theme.radius.card,
          boxShadow: dec.shadow, padding: '44px 46px',
          display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', gap: 18,
          opacity: Math.min(1, seg(t, p.focus.at, p.focus.dur * 0.7, 0, 1)),
          transform: 'scale(' + (0.9 + 0.1 * cardIn) + ') rotate(' + (-5 + 5 * cardIn) + 'deg)',
        }}>
          {focus.label && (
            <div style={{ fontSize: V.type.caption, fontWeight: 700, letterSpacing: '0.16em' }}>{focus.label}</div>
          )}
          <div style={Object.assign({
            fontSize: V.type.word, fontWeight: 800, letterSpacing: '-0.02em', textAlign: 'center',
          }, TEXT_WRAP)}>{focus.word}</div>
        </div>
        {focus.caption && (
          <div style={Object.assign({
            position: 'absolute', left: V.marginX, right: V.marginX, top: HOOK.captionTop,
            fontSize: V.type.body, color: theme.color.sub, textAlign: 'center', lineHeight: 1.4,
          }, TEXT_WRAP, riseUp(theme, t, p.caption.at, p.caption.dur, 18))}>{focus.caption}</div>
        )}

        {hint.text && (
          <div style={Object.assign({
            position: 'absolute', left: V.marginX, right: V.marginX, top: HOOK.hintTop,
            fontSize: V.type.note, color: theme.color.faint, textAlign: 'center', letterSpacing: '0.02em',
          }, TEXT_WRAP, riseUp(theme, t, p.hint.at, p.hint.dur, 14))}>{hint.text}</div>
        )}
        {beats.map(function (b, i) {
          var at = p.beats.at + i * p.beats.stagger;
          var on = i === 0;
          var op = seg(t, at, p.beats.dur, 0, 1);
          var x = V.marginX + i * (colW + 16);
          return (
            <React.Fragment key={'b' + i}>
              <div style={{
                position: 'absolute', left: x, top: HOOK.beatLabelTop, width: colW,
                fontSize: V.type.caption, fontWeight: on ? 800 : 600, textAlign: 'center',
                color: on ? theme.color.ink : theme.color.faint, opacity: op,
              }}>{b}</div>
              <div style={{
                position: 'absolute', left: x, top: HOOK.beatBarTop, width: colW, height: 8,
                borderRadius: 4, background: on ? theme.color.blue : theme.component.frame.line,
                opacity: op,
              }}></div>
            </React.Fragment>
          );
        })}
      </VFrame>
    );
  }
  VHookScene.nat = 6;
  VHookScene.schedule = function (d) {
    var p = hookPlan(d);
    return [
      { id: 'kicker', kind: 'enter', at: 0.15, dur: 0.6, path: '/kicker' },
      { id: 'line', kind: 'enter', at: p.line.at, dur: p.line.dur, path: '/line' },
      { id: 'rings', kind: 'enter', at: p.rings.at, dur: p.rings.dur, stagger: p.rings.stagger, count: 3 },
      { id: 'focus', kind: 'enter', at: p.focus.at, dur: p.focus.dur, path: '/focus' },
      { id: 'focus-caption', kind: 'enter', at: p.caption.at, dur: p.caption.dur, path: '/focus/caption' },
      { id: 'hint', kind: 'enter', at: p.hint.at, dur: p.hint.dur, path: '/hint/text' },
      { id: 'beats', kind: 'enter', at: p.beats.at, dur: p.beats.dur, stagger: p.beats.stagger, count: p.beats.count, path: '/hint/beats' },
    ];
  };

  /* ══ vtpl.stack — 세로 적층 (아래에서 위로 밀려 올라오는 논지) ═══════
     새 카드가 하단 앵커로 들어오면 먼저 온 카드들이 그만큼 위로 밀린다 —
     세로 스크롤(피드가 위로 넘어가는) 은유를 모션 자체로 구현. tone 으로 문제/해법 양용. */
  var STACK_BAND = { top: 430, bottom: 1610 };
  // 카드 높이는 데이터에서 결정 — 논지 46px(줄높이 1.3=60px, 텍스트열 730px 기준 16자/줄)
  // + 보조 36px(50px) + 상하 패딩 60px, 칩 76px 이 하한. 4장 최악(2줄 논지 + 보조) = 240px.
  function cardHeightOf(c) {
    var lines = Math.min(2, Math.max(1, Math.ceil(((c.title || '').length) / 16)));
    var h = lines * 60;
    if (c.desc) h += 10 + 50;
    return Math.max(76, h) + 60;
  }
  function stackGeo(cards) {
    var n = cards.length;
    var cardH = 0;
    for (var i = 0; i < n; i++) cardH = Math.max(cardH, cardHeightOf(cards[i]));
    var pitch = cardH + 56;
    var stackH = (n - 1) * pitch + cardH;
    var slack = (STACK_BAND.bottom - STACK_BAND.top) - stackH;
    return { top: STACK_BAND.top + (slack > 0 ? slack / 2 : 0), pitch: pitch, cardH: cardH };
  }
  function stackPlan(d) {
    var n = (d.cards || []).length;
    var first = 1.4, step = 1.8, dur = 0.65;
    return {
      count: n, dur: dur, step: step,
      cardAt: function (i) { return first + i * step; },
      conclusion: { at: first + (n - 1) * step + 1.4, dur: 0.7 },
    };
  }
  function VStackScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = stackPlan(d);
    var cards = d.cards || [];
    var g = stackGeo(cards);
    var problem = d.tone !== 'solution';
    var markTone = problem
      ? { bg: theme.component.chip.errorBg, fg: theme.component.chip.errorFg }
      : { bg: theme.component.chip.accentBg, fg: theme.component.chip.accentFg };
    var railColor = problem ? theme.color.red : theme.color.blue;
    var concTone = problem
      ? toneOf(theme.component.tag, 'error', 'error')
      : toneOf(theme.component.tag, 'accept', 'accept');
    var card = theme.component.card;
    return (
      <VFrame label="적층" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {cards.map(function (c, i) {
          var at = p.cardAt(i);
          var push = 0;
          for (var j = i + 1; j < cards.length; j++) {
            push += (1 - seg(t, p.cardAt(j), p.dur, 0, 1)) * g.pitch;
          }
          var inn = seg(t, at, p.dur, 0, 1);
          var dy = push + (1 - inn) * 150;
          var mark = c.mark != null ? c.mark : (problem ? '✕' : String(i + 1));
          return (
            <div key={i} data-v-card={i} style={{
              position: 'absolute', left: V.marginX, top: g.top + i * g.pitch,
              width: V.contentW, height: g.cardH, boxSizing: 'border-box',
              background: card.bg, border: '1px solid ' + card.border,
              borderLeft: '12px solid ' + railColor,
              borderRadius: theme.radius.card, boxShadow: card.shadow,
              padding: '30px 34px', display: 'flex', alignItems: 'center', gap: 26,
              opacity: seg(t, at, p.dur, 0, 1),
              transform: 'translateY(' + dy + 'px) scale(' + (0.95 + 0.05 * inn) + ')',
            }}>
              <div style={{
                width: 76, height: 76, flexShrink: 0, borderRadius: theme.radius.chip,
                background: markTone.bg, color: markTone.fg,
                fontSize: V.type.body, fontWeight: 800,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>{mark}</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={Object.assign({
                  fontSize: V.type.item, fontWeight: 800, lineHeight: 1.3, letterSpacing: '-0.02em',
                }, TEXT_WRAP)}>{c.title}</div>
                {c.desc && (
                  <div style={Object.assign({
                    marginTop: 10, fontSize: V.type.note, color: theme.color.sub, lineHeight: 1.4,
                  }, TEXT_WRAP)}>{c.desc}</div>
                )}
              </div>
            </div>
          );
        })}
        {d.conclusion && (
          <div style={Object.assign({
            position: 'absolute', left: V.marginX, right: V.marginX, top: 1660,
            display: 'flex', justifyContent: 'center',
          }, riseUp(theme, t, p.conclusion.at, p.conclusion.dur, 20))}>
            <div style={Object.assign({
              background: concTone.bg, color: concTone.fg, borderRadius: theme.radius.pill,
              padding: '22px 44px', fontSize: V.type.body, fontWeight: 800, textAlign: 'center',
              maxWidth: V.contentW, boxSizing: 'border-box',
            }, TEXT_WRAP)}>{d.conclusion}</div>
          </div>
        )}
      </VFrame>
    );
  }
  VStackScene.nat = 12;
  VStackScene.schedule = function (d) {
    var p = stackPlan(d);
    var out = [
      { id: 'kicker', kind: 'enter', at: 0.15, dur: 0.6, path: '/kicker' },
      { id: 'title', kind: 'enter', at: 0.3, dur: 0.7, path: '/title' },
    ];
    for (var i = 0; i < p.count; i++) {
      out.push({ id: 'card-' + i, kind: 'enter', at: p.cardAt(i), dur: p.dur, path: '/cards/' + i });
    }
    out.push({ id: 'conclusion', kind: 'enter', at: p.conclusion.at, dur: p.conclusion.dur, path: '/conclusion' });
    return out;
  };

  /* ══ vtpl.metric — 화면 절반을 차지하는 단일 수치 ════════════════════
     모바일 가독 우선: 수치 하나 + 근거 한 줄. 후광(halo)이 화면 중앙 절반(470~1350)을 채우고
     그 안에 초대형 수치가 앉는다. 글자수에 따라 폰트를 단계적으로 낮춰 폭 912 안에 항상 수용. */
  var METRIC = {
    plateCx: 540, plateCy: 870, plateR: 380,   // 원판 490~1250 — 화면 세로의 40%를 수치 블록이 점유
    labelTop: 580, valueTop: 690, deltaTop: 1300,
    ruleTop: 1420, evidenceTop: 1480, sourceTop: 1650,
  };
  // 폭 912 실측 역산 — Pretendard 숫자 글리프 ≈ 0.6em 기준으로 단계 하향
  function valueFontFor(text) {
    var n = (text || '').length;
    if (n <= 3) return 320;
    if (n === 4) return 280;
    if (n === 5) return 230;
    if (n === 6) return 195;
    return 170;
  }
  function metricPlan(d) {
    return {
      halo: { at: 0.7, dur: 1.0 },
      label: { at: 0.5, dur: 0.6 },
      value: { at: 1.0, dur: 0.8 },
      unit: { at: 1.35, dur: 0.6 },
      delta: { at: 1.9, dur: 0.5 },
      rule: { at: 2.5, dur: 0.6 },
      evidence: { at: 2.9, dur: 0.7 },
      source: { at: 3.6, dur: 0.6 },
    };
  }
  function VMetricScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = metricPlan(d);
    var vSize = valueFontFor(d.value);
    var uSize = Math.round(vSize * 0.32);
    var delta = d.delta;
    // 방향(dir)과 평가(tone)는 분리한다 — "오류율 ▼" 처럼 내려가는 것이 좋은 수치가 있다
    var dGlyph = delta ? (delta.dir === 'down' ? '▼' : delta.dir === 'flat' ? '＝' : '▲') : '';
    var dTone = delta
      ? toneOf(theme.component.chip, delta.tone === 'bad' ? 'error' : delta.tone === 'neutral' ? 'info' : 'success', 'success')
      : null;
    var vIn = seg(t, p.value.at, p.value.dur, 0, 1, easeOf(theme.motion.pop.ease));
    return (
      <VFrame label="수치" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        <div data-qa-clip-ok="true" style={{
          position: 'absolute', left: METRIC.plateCx - METRIC.plateR, top: METRIC.plateCy - METRIC.plateR,
          width: METRIC.plateR * 2, height: METRIC.plateR * 2, borderRadius: theme.radius.pill,
          background: theme.component.card.bg, border: '2px solid ' + theme.color.blueBorder,
          boxShadow: theme.component.card.shadowSoft,
          opacity: seg(t, p.halo.at, p.halo.dur, 0, 1),
          transform: 'scale(' + seg(t, p.halo.at, p.halo.dur, 0.88, 1) + ')',
        }}></div>

        <div style={Object.assign({
          position: 'absolute', left: V.marginX, right: V.marginX, top: METRIC.labelTop,
          fontSize: V.type.note, fontWeight: 700, letterSpacing: '0.14em',
          color: theme.color.sub, textAlign: 'center',
        }, TEXT_WRAP, riseUp(theme, t, p.label.at, p.label.dur, 16))}>{d.label}</div>

        <div style={{
          position: 'absolute', left: V.marginX, right: V.marginX, top: METRIC.valueTop,
          display: 'flex', alignItems: 'flex-end', justifyContent: 'center', gap: 14,
        }}>
          <div style={{
            // lineHeight 1.18 — 초대형 글리프의 잉크 박스(≈1.12em)가 줄 상자를 넘지 않게 (오버플로 실측 보정)
            fontSize: vSize, fontWeight: 800, letterSpacing: '-0.045em', lineHeight: 1.18,
            color: theme.color.blue,
            opacity: Math.min(1, seg(t, p.value.at, p.value.dur * 0.6, 0, 1)),
            transform: 'scale(' + (0.82 + 0.18 * vIn) + ')',
          }}>{d.value}</div>
          {d.unit && (
            <div style={{
              fontSize: uSize, fontWeight: 800, color: theme.color.blue2,
              lineHeight: 1.6, paddingBottom: Math.round(vSize * 0.06),
              opacity: seg(t, p.unit.at, p.unit.dur, 0, 1),
              transform: 'translateY(' + seg(t, p.unit.at, p.unit.dur, 16, 0) + 'px)',
            }}>{d.unit}</div>
          )}
        </div>

        {delta && (
          <div style={Object.assign({
            position: 'absolute', left: V.marginX, right: V.marginX, top: METRIC.deltaTop,
            display: 'flex', justifyContent: 'center',
          }, popIn(theme, t, p.delta.at, p.delta.dur, 0.86))}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 14,
              background: dTone.bg, color: dTone.fg, borderRadius: theme.radius.pill,
              padding: '18px 38px', fontSize: V.type.item, fontWeight: 800,
            }}>
              <span>{dGlyph}</span><span>{delta.text}</span>
            </div>
          </div>
        )}

        <div style={{
          position: 'absolute', left: (V.stage.w - 120) / 2, top: METRIC.ruleTop,
          width: seg(t, p.rule.at, p.rule.dur, 0, 120), height: 6,
          background: theme.color.blue, borderRadius: 3,
        }}></div>
        <div style={Object.assign({
          position: 'absolute', left: V.marginX, right: V.marginX, top: METRIC.evidenceTop,
          fontSize: V.type.lead, fontWeight: 700, lineHeight: 1.35, textAlign: 'center',
        }, TEXT_WRAP, riseUp(theme, t, p.evidence.at, p.evidence.dur, 22))}>{d.evidence}</div>
        {d.source && (
          <div style={Object.assign({
            position: 'absolute', left: V.marginX, right: V.marginX, top: METRIC.sourceTop,
            fontSize: V.type.caption, color: theme.color.faint, textAlign: 'center',
          }, TEXT_WRAP, { opacity: seg(t, p.source.at, p.source.dur, 0, 1) })}>{d.source}</div>
        )}
      </VFrame>
    );
  }
  VMetricScene.nat = 10;
  VMetricScene.schedule = function (d) {
    var p = metricPlan(d);
    return [
      { id: 'kicker', kind: 'enter', at: 0.15, dur: 0.6, path: '/kicker' },
      { id: 'title', kind: 'enter', at: 0.3, dur: 0.7, path: '/title' },
      { id: 'label', kind: 'enter', at: p.label.at, dur: p.label.dur, path: '/label' },
      { id: 'halo', kind: 'enter', at: p.halo.at, dur: p.halo.dur },
      { id: 'value', kind: 'enter', at: p.value.at, dur: p.value.dur, path: '/value' },
      { id: 'unit', kind: 'enter', at: p.unit.at, dur: p.unit.dur, path: '/unit' },
      { id: 'delta', kind: 'enter', at: p.delta.at, dur: p.delta.dur, path: '/delta' },
      { id: 'rule', kind: 'enter', at: p.rule.at, dur: p.rule.dur },
      { id: 'evidence', kind: 'enter', at: p.evidence.at, dur: p.evidence.dur, path: '/evidence' },
      { id: 'source', kind: 'enter', at: p.source.at, dur: p.source.dur, path: '/source' },
    ];
  };

  /* ══ vtpl.cta — 마지막 행동 유도 ═════════════════════════════════════
     중앙 정렬 대형 문구 + 전폭 진입점 필(엄지 도달 구역인 하단 1/3 에 세로 적층). */
  var CTA = { ruleTop: 480, headlineTop: 540, subTop: 910, entryTop: 1120, entryH: 116, entryGap: 28, footnoteTop: 1660 };
  function ctaPlan(d) {
    var n = (d.entries || []).length;
    return {
      rule: { at: 0.4, dur: 0.7 },
      headline: { at: 0.7, dur: 0.8 },
      sub: { at: 1.4, dur: 0.6 },
      entries: { at: 2.0, dur: 0.6, stagger: 0.28, count: n },
      footnote: { at: 2.0 + n * 0.28 + 0.8, dur: 0.6 },
    };
  }
  function VCtaScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = ctaPlan(d);
    var entries = d.entries || [];
    var pill = theme.component.ctaPill;
    var dec = theme.component.decision;
    return (
      <VFrame label="행동유도" t={t} theme={theme} kicker={d.kicker} hideFooter at={{ kicker: 0.15 }}>
        <div style={{
          position: 'absolute', left: (V.stage.w - 120) / 2, top: CTA.ruleTop,
          width: seg(t, p.rule.at, p.rule.dur, 0, 120), height: 6,
          background: theme.color.blue, borderRadius: 3,
        }}></div>
        <div style={Object.assign({
          position: 'absolute', left: V.marginX, right: V.marginX, top: CTA.headlineTop,
          fontSize: V.type.headline, fontWeight: 800, letterSpacing: '-0.035em',
          lineHeight: 1.2, textAlign: 'center',
        }, TEXT_WRAP, riseUp(theme, t, p.headline.at, p.headline.dur, 28))}>
          <VAccent data={d.headline} accentColor={theme.color.blue} />
        </div>
        {d.sub && (
          <div style={Object.assign({
            position: 'absolute', left: V.marginX, right: V.marginX, top: CTA.subTop,
            fontSize: V.type.sub, color: theme.color.sub, textAlign: 'center', lineHeight: 1.4,
          }, TEXT_WRAP, riseUp(theme, t, p.sub.at, p.sub.dur, 20))}>{d.sub}</div>
        )}
        {entries.map(function (e, i) {
          var at = p.entries.at + i * p.entries.stagger;
          var primary = e.kind !== 'secondary';
          return (
            <div key={i} style={Object.assign({
              position: 'absolute', left: V.marginX, top: CTA.entryTop + i * (CTA.entryH + CTA.entryGap),
              width: V.contentW, height: CTA.entryH, boxSizing: 'border-box',
              borderRadius: theme.radius.pill,
              background: primary ? dec.bg : pill.bg,
              color: primary ? dec.fg : pill.fg,
              border: primary ? 'none' : '2px solid ' + pill.border,
              boxShadow: primary ? dec.shadow : pill.shadow,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: V.type.item, fontWeight: 800, letterSpacing: '-0.01em',
            }, TEXT_WRAP, riseUp(theme, t, at, p.entries.dur, 26))}>{e.text}</div>
          );
        })}
        {d.footnote && (
          <div style={{
            position: 'absolute', left: V.marginX, right: V.marginX, top: CTA.footnoteTop,
            fontSize: V.type.caption, color: theme.color.faint, textAlign: 'center',
            opacity: seg(t, p.footnote.at, p.footnote.dur, 0, 1),
          }}>{d.footnote}</div>
        )}
      </VFrame>
    );
  }
  VCtaScene.nat = 8;
  VCtaScene.schedule = function (d) {
    var p = ctaPlan(d);
    return [
      { id: 'kicker', kind: 'enter', at: 0.15, dur: 0.6, path: '/kicker' },
      { id: 'rule', kind: 'enter', at: p.rule.at, dur: p.rule.dur },
      { id: 'headline', kind: 'enter', at: p.headline.at, dur: p.headline.dur, path: '/headline' },
      { id: 'sub', kind: 'enter', at: p.sub.at, dur: p.sub.dur, path: '/sub' },
      { id: 'entries', kind: 'enter', at: p.entries.at, dur: p.entries.dur, stagger: p.entries.stagger, count: p.entries.count, path: '/entries' },
      { id: 'footnote', kind: 'enter', at: p.footnote.at, dur: p.footnote.dur, path: '/footnote' },
    ];
  };

  OMX.templates = Object.assign(OMX.templates || {}, {
    VHookScene: VHookScene,
    VStackScene: VStackScene,
    VMetricScene: VMetricScene,
    VCtaScene: VCtaScene,
  });
  OMX.templateIndex = Object.assign(OMX.templateIndex || {}, {
    'vtpl.hook': VHookScene,
    'vtpl.stack': VStackScene,
    'vtpl.metric': VMetricScene,
    'vtpl.cta': VCtaScene,
  });
  // 세로 포맷 전용 공개면 — 무대 스펙·세로 크롬·스케줄 유틸 (가로 자산과 이름 충돌 없음)
  OMX.vertical = Object.assign(OMX.vertical || {}, {
    format: 'short-9x16',
    stage: V.stage,
    spec: V,
    settleOf: settleOf,
    stillOf: stillOf,
    metaphors: { 'v-frame': VFrame, 'v-dot-column': VDotColumn },
  });
})();
