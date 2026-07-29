// 오프닝 변주 3종 — tpl.o-statement(선언형) · tpl.o-metric(수치 충격형) · tpl.o-question(질문형).
// 기존 tpl.opening(배지→타이틀→서브타이틀→도트 순차 등장)과 **각인 전략 자체가 다르다**:
//   선언형 — 장식 0. 문장 실루엣이 먼저 있고 좌→우로 밝아지며 완성된다. 마지막에 출처가 조용히.
//   수치형 — 숫자를 먼저 던진다. 초대형 수치가 0에서 목표값까지 오르고, 그 다음 의미·제목.
//   질문형 — 질문을 띄우고 답이 들어갈 빈 자리를 보여준 뒤, 다룰 항목 3개를 예고한다.
// 계약: 엔진 props(localTime 등) + data + theme, 정적 .schedule(data)/.nat,
//       frame-match(첫/끝 프레임 정지), 모든 모션은 t(localTime)의 순수 함수 — Date/Math.random 금지.
(function () {
  'use strict';
  var OMX = (window.OMX = window.OMX || {});
  var Easing = window.Easing;
  var animate = window.animate;
  var FrameChrome = OMX.metaphors['frame-chrome']; // 허용된 공통 크롬 (dot-grid 내장)

  var STAGE_W = 1920;
  var STAGE_H = 1080;
  // Pretendard 글리프 박스 실측 비율(숫자 241/220=1.10 · 물음표 196/168=1.17) 위 —
  // line-height 1 은 글리프가 줄상자를 넘어 게이트 5 오버플로 경고를 만든다. 초대형 글리프 전용.
  var GLYPH_LH = 1.25;

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

  /* ══ tpl.o-statement — 선언형 ═════════════════════════════════════════
     각인 전략: **문장 자체가 화면이다.** 배지도 도트도 없다. 좌측 정렬 대형 문장이
     처음부터 옅은 실루엣으로 놓여 있고(ST_GHOST), 단어 단위로 좌→우 순서로 불이 켜지며
     문장이 완성된다. 강조어는 색만 다르다(굵기 동일 — "강조어만 색이 다르고").
     완성된 뒤 출처 한 줄이 아래에 조용히 페이드인.

     자수 → 폰트: 행 최대 자수로 렌더가 96~120px 을 정한다. 스키마가 행을 18자로 묶어
     최악(18자)에도 96px 아래로 내려가지 않는다 — "많이 쓰면 글자가 준다"는 경로 차단. */

  var ST_MARGIN = 100;                       // 오프닝 전용 좌우 여백 (문장·질문이 주인공 — 크롬 여백 140보다 넓게 쓴다)
  var ST_W = STAGE_W - ST_MARGIN * 2;        // 1720
  var ST_MIN_SIZE = 96;
  var ST_MAX_SIZE = 120;
  var ST_CHAR_EM = 0.99;                     // 한글 1em + letterSpacing -0.02em 보정 계수
  var ST_LINE_H = 1.24;
  var ST_GHOST = 0.16;                       // 점등 전 실루엣 불투명도 (t=0 정지 — frame-match)
  var ST_SOURCE_GAP = 54;
  var ST_SOURCE_H = 36;
  var ST_START = 0.4;
  var ST_STAGGER = 0.28;
  var ST_DUR = 0.7;

  // 행 최대 자수 → 폰트 크기·행 높이·블록 수직 중앙 배치
  function stGeo(d) {
    var lines = d.lines || [];
    var maxChars = 1;
    for (var i = 0; i < lines.length; i++) {
      var n = (lines[i].text || '').length;
      if (n > maxChars) maxChars = n;
    }
    var size = Math.floor(ST_W / (maxChars * ST_CHAR_EM));
    if (size > ST_MAX_SIZE) size = ST_MAX_SIZE;
    if (size < ST_MIN_SIZE) size = ST_MIN_SIZE;
    var lineH = Math.round(size * ST_LINE_H);
    var blockH = lineH * lines.length;
    var srcH = d.source ? ST_SOURCE_GAP + ST_SOURCE_H : 0;
    return {
      maxChars: maxChars, fontSize: size, lineH: lineH, blockH: blockH,
      top: Math.round((STAGE_H - (blockH + srcH)) / 2),
    };
  }

  // 단어(+뒤 공백) 단위 분해 — 좌→우 점등의 최소 단위
  function stWords(text) {
    var out = [];
    var re = /\S+\s*|\s+/g;
    var m;
    while ((m = re.exec(text)) !== null) out.push(m[0]);
    return out.length ? out : [text];
  }
  // 한 행 → 점등 토큰 배열. accent 는 text 안의 부분 문자열이며 통째로 한 토큰(한 번에 켜진다)
  function stTokens(line) {
    var text = (line && line.text) || '';
    var acc = (line && line.accent) || '';
    var start = acc ? text.indexOf(acc) : -1;
    var out = [];
    function pushPlain(s) {
      if (!s) return;
      var ws = stWords(s);
      for (var i = 0; i < ws.length; i++) out.push({ text: ws[i], accent: false });
    }
    if (start < 0) { pushPlain(text); return mergeBlank(out); }
    pushPlain(text.slice(0, start));
    out.push({ text: acc, accent: true });
    pushPlain(text.slice(start + acc.length));
    return mergeBlank(out);
  }
  // 공백만 있는 토큰은 다음(없으면 앞) 토큰에 붙인다 — 빈 조각은 점등 단위가 되지 못한다
  function mergeBlank(list) {
    var out = [];
    for (var i = 0; i < list.length; i++) {
      var cur = list[i];
      if (cur.text.trim()) { out.push(cur); continue; }
      if (i + 1 < list.length) {
        list[i + 1] = { text: cur.text + list[i + 1].text, accent: list[i + 1].accent };
      } else if (out.length) {
        out[out.length - 1] = {
          text: out[out.length - 1].text + cur.text, accent: out[out.length - 1].accent,
        };
      }
    }
    return out;
  }

  function stPlan(d) {
    var lines = d.lines || [];
    var at = [];
    var k = 0;
    for (var i = 0; i < lines.length; i++) {
      var toks = stTokens(lines[i]);
      var rowAt = [];
      for (var j = 0; j < toks.length; j++) { rowAt.push(ST_START + k * ST_STAGGER); k++; }
      at.push(rowAt);
    }
    var last = k ? ST_START + (k - 1) * ST_STAGGER : ST_START;
    return { at: at, count: k, dur: ST_DUR, source: { at: last + ST_DUR + 0.6, dur: 0.9 } };
  }

  function StatementOpeningScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var g = stGeo(d);
    var p = stPlan(d);
    var lines = d.lines || [];
    return (
      <FrameChrome label="오프닝" t={t} theme={theme} hideFooter>
        <div style={{ position: 'absolute', left: ST_MARGIN, top: g.top, width: ST_W }}>
          {lines.map(function (line, i) {
            var toks = stTokens(line);
            return (
              <div key={i} style={{
                fontSize: g.fontSize, lineHeight: ST_LINE_H, fontWeight: 800,
                letterSpacing: '-0.02em', whiteSpace: 'nowrap', color: theme.color.ink,
              }}>
                {toks.map(function (tok, j) {
                  var lit = seg(t, p.at[i][j], p.dur, 0, 1);
                  return (
                    <span key={j} style={{
                      color: tok.accent ? theme.color.blue : theme.color.ink,
                      opacity: ST_GHOST + (1 - ST_GHOST) * lit,
                    }}>{tok.text}</span>
                  );
                })}
              </div>
            );
          })}
          {d.source && (
            <div style={{
              marginTop: ST_SOURCE_GAP, height: ST_SOURCE_H, lineHeight: ST_SOURCE_H + 'px',
              fontSize: theme.type.body, color: theme.color.faint, letterSpacing: '0.01em',
              opacity: seg(t, p.source.at, p.source.dur, 0, 1),
            }}>{'— ' + d.source}</div>
          )}
        </div>
      </FrameChrome>
    );
  }
  StatementOpeningScene.nat = 8;
  StatementOpeningScene.schedule = function (d) {
    var p = stPlan(d);
    var lines = d.lines || [];
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      var rowAt = p.at[i];
      if (!rowAt.length) continue;
      out.push({
        id: 'line-' + i, kind: 'enter', at: rowAt[0], dur: p.dur,
        settle: rowAt[rowAt.length - 1] + p.dur, path: '/lines/' + i,
      });
    }
    if (d.source) out.push({ id: 'source', kind: 'enter', at: p.source.at, dur: p.source.dur, path: '/source' });
    return out;
  };

  /* ══ tpl.o-metric — 수치 충격형 ═══════════════════════════════════════
     각인 전략: **숫자를 먼저 던진다.** 제목도 배지도 없이 화면 중앙 220px 수치가
     0에서 목표값까지 오른다(카운트업은 localTime 의 순수 함수 — 같은 시각이면 같은 픽셀).
     수치가 멈춘 뒤 그 수치의 '의미' 한 줄, 그 다음 제목이 작게, 마지막에 출처.
     크기 위계가 뒤집혀 있다 — 이 오프닝에서 제목은 조연이다. */

  var MT_VALUE_SIZE = 220;                       // 초대형 수치 (브리프 180~220 대역 상단)
  var MT_SUFFIX_RATIO = 0.5;                     // 단위는 수치의 절반 — 숫자가 주인공
  var MT_SUFFIX_GAP = 12;
  var MT_INK_OVERHANG = 0.05;                    // 글리프 잉크가 advance 를 넘는 실측 여유(em)

  // 천단위 구분 + 소수 자릿수 — toFixed 기반 순수 함수 (로캘 비의존)
  function mtFormat(v, decimals) {
    var dec = decimals || 0;
    var s = (v < 0 ? 0 : v).toFixed(dec);
    var parts = s.split('.');
    var ip = parts[0];
    var out = '';
    for (var i = 0; i < ip.length; i++) {
      if (i > 0 && (ip.length - i) % 3 === 0) out += ',';
      out += ip.charAt(i);
    }
    return parts.length > 1 ? out + '.' + parts[1] : out;
  }
  // 최종 수치 문자열의 폭 추정(em) — 스키마 상한(6자리·소수 1·단위 3자)에서도 1720px 안이라는 근거.
  // MT_INK_OVERHANG 은 글리프 잉크가 advance 폭을 넘는 실측 여유(약 7px @220px) — 추정을 보수적으로 유지한다.
  function mtWidthEm(d) {
    var text = mtFormat(d.value, d.decimals);
    var em = MT_INK_OVERHANG;
    for (var i = 0; i < text.length; i++) {
      var c = text.charAt(i);
      em += (c === ',' || c === '.') ? 0.3 : 0.6;
    }
    var suffix = d.suffix || '';
    if (suffix) em += suffix.length * MT_SUFFIX_RATIO + MT_SUFFIX_GAP / MT_VALUE_SIZE;
    return em;
  }

  function mtPlan() {
    return {
      value: { at: 0.35, dur: 0.55 },
      count: { at: 0.45, dur: 1.75 },
      meaning: { at: 2.55, dur: 0.7 },
      title: { at: 3.35, dur: 0.6 },
      source: { at: 4.15, dur: 0.8 },
    };
  }

  function MetricOpeningScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = mtPlan();
    var shown = mtFormat(seg(t, p.count.at, p.count.dur, 0, d.value), d.decimals);
    var popE = easeOf(theme.motion.pop.ease);
    return (
      <FrameChrome label="오프닝" t={t} theme={theme} hideFooter>
        <div style={{
          position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column',
          alignItems: 'center', justifyContent: 'center',
        }}>
          <div style={{
            display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: MT_SUFFIX_GAP,
            opacity: seg(t, p.value.at, p.value.dur, 0, 1),
            transform: 'scale(' + seg(t, p.value.at, p.value.dur, 0.93, 1, popE) + ')',
          }}>
            <span style={{
              fontSize: MT_VALUE_SIZE, lineHeight: GLYPH_LH, fontWeight: 800,
              letterSpacing: '-0.035em', color: theme.color.blue,
              fontVariantNumeric: 'tabular-nums',
            }}>{shown}</span>
            {d.suffix && (
              <span style={{
                fontSize: Math.round(MT_VALUE_SIZE * MT_SUFFIX_RATIO), lineHeight: GLYPH_LH,
                fontWeight: 800, letterSpacing: '-0.02em', color: theme.color.ink,
              }}>{d.suffix}</span>
            )}
          </div>
          <div style={Object.assign({
            marginTop: 36, fontSize: theme.type.subtitle, fontWeight: 600,
            lineHeight: 1.4, color: theme.color.ink,
          }, enter(theme, t, p.meaning.at, p.meaning.dur, 20))}>{d.meaning}</div>
          <div style={Object.assign({
            marginTop: 28, fontSize: theme.type.body, fontWeight: 700,
            letterSpacing: '0.16em', color: theme.color.blue,
          }, enter(theme, t, p.title.at, p.title.dur, 14))}>{d.title}</div>
        </div>
        {d.source && (
          <div style={{
            position: 'absolute', bottom: 78, left: 0, right: 0, textAlign: 'center',
            fontSize: theme.type.caption, color: theme.color.faint,
            opacity: seg(t, p.source.at, p.source.dur, 0, 1),
          }}>{d.source}</div>
        )}
      </FrameChrome>
    );
  }
  MetricOpeningScene.nat = 8;
  MetricOpeningScene.schedule = function (d) {
    var p = mtPlan();
    var out = [
      { id: 'value', kind: 'enter', at: p.value.at, dur: p.value.dur,
        settle: p.count.at + p.count.dur, path: '/value' },
      { id: 'meaning', kind: 'enter', at: p.meaning.at, dur: p.meaning.dur, path: '/meaning' },
      { id: 'title', kind: 'enter', at: p.title.at, dur: p.title.dur, path: '/title' },
    ];
    if (d.source) out.push({ id: 'source', kind: 'enter', at: p.source.at, dur: p.source.dur, path: '/source' });
    return out;
  };

  /* ══ tpl.o-question — 질문형 ══════════════════════════════════════════
     각인 전략: **답을 비워 둔다.** 상단에 질문을 띄우고, 중앙에 답이 들어갈 빈 자리
     (흰 원 + 물음표)를 보여준 뒤, 하단에서 "이 보고서가 답합니다" 류의 예고와
     다룰 항목 3개 칩을 차례로 켠다. 시청자에게 남는 것은 문장이 아니라 궁금증이다. */

  var QS_TOP = 118;
  var QS_RING = 300;
  var QS_RING_CY = 566;
  var QS_MARK_RATIO = 0.56;
  var QS_PROMISE_TOP = 790;
  var QS_CHIP_TOP = 866;

  function qsPlan(d) {
    var q = d.question || [];
    var topics = d.topics || [];
    var topicsAt = 3.5;
    return {
      question: { at: 0.4, dur: 0.8, stagger: 0.26, count: q.length },
      ring: { at: 1.5, dur: 0.8 },
      mark: { at: 1.9, dur: 0.7 },
      promise: { at: 2.9, dur: 0.7 },
      topics: { at: topicsAt, dur: 0.55, stagger: 0.3, count: topics.length },
      source: { at: topicsAt + topics.length * 0.3 + 0.6, dur: 0.8 },
    };
  }

  function QuestionOpeningScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = qsPlan(d);
    var popE = easeOf(theme.motion.pop.ease);
    var chip = theme.component.chip;
    var ringScale = seg(t, p.ring.at, p.ring.dur, 0.72, 1, popE);
    return (
      <FrameChrome label="오프닝" t={t} theme={theme} hideFooter>
        <div style={{ position: 'absolute', left: ST_MARGIN, top: QS_TOP, width: ST_W, textAlign: 'center' }}>
          {(d.question || []).map(function (line, i) {
            return (
              <div key={i} style={Object.assign({
                fontSize: theme.type.display, lineHeight: 1.22, fontWeight: 800,
                letterSpacing: '-0.025em', whiteSpace: 'nowrap', color: theme.color.ink,
              }, enter(theme, t, p.question.at + i * p.question.stagger, p.question.dur, 30))}>{line}</div>
            );
          })}
        </div>
        <div style={{
          position: 'absolute', left: (STAGE_W - QS_RING) / 2, top: QS_RING_CY - QS_RING / 2,
          width: QS_RING, height: QS_RING, borderRadius: theme.radius.pill,
          background: theme.component.card.bg, border: '3px solid ' + theme.color.blueBorder,
          boxShadow: theme.shadow.cardSoft,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          opacity: seg(t, p.ring.at, p.ring.dur, 0, 1),
          transform: 'scale(' + ringScale + ')',
        }}>
          <span style={{
            fontSize: Math.round(QS_RING * QS_MARK_RATIO), lineHeight: GLYPH_LH, fontWeight: 800,
            color: theme.color.blue, letterSpacing: '-0.04em',
            opacity: seg(t, p.mark.at, p.mark.dur, 0, 1),
          }}>?</span>
        </div>
        <div style={Object.assign({
          position: 'absolute', left: 0, right: 0, top: QS_PROMISE_TOP, textAlign: 'center',
          fontSize: theme.type.subtitle, fontWeight: 600, color: theme.color.sub,
        }, enter(theme, t, p.promise.at, p.promise.dur, 18))}>{d.promise}</div>
        <div style={{
          position: 'absolute', left: 0, right: 0, top: QS_CHIP_TOP,
          display: 'flex', justifyContent: 'center', gap: 24,
        }}>
          {(d.topics || []).map(function (topic, i) {
            var at = p.topics.at + i * p.topics.stagger;
            var v = seg(t, at, p.topics.dur, 0, 1, popE);
            return (
              <div key={i} style={{
                padding: '16px 34px', borderRadius: theme.radius.pill,
                background: chip.accentBg, color: chip.accentFg,
                fontSize: theme.type.chipLg, fontWeight: 700, lineHeight: 1.4,
                whiteSpace: 'nowrap',
                opacity: Math.min(1, v), transform: 'scale(' + v + ')',
              }}>{topic}</div>
            );
          })}
        </div>
        {d.source && (
          <div style={{
            position: 'absolute', bottom: 66, left: 0, right: 0, textAlign: 'center',
            fontSize: theme.type.caption, color: theme.color.faint,
            opacity: seg(t, p.source.at, p.source.dur, 0, 1),
          }}>{d.source}</div>
        )}
      </FrameChrome>
    );
  }
  QuestionOpeningScene.nat = 9;
  QuestionOpeningScene.schedule = function (d) {
    var p = qsPlan(d);
    var out = [
      { id: 'question', kind: 'enter', at: p.question.at, dur: p.question.dur,
        stagger: p.question.stagger, count: p.question.count, path: '/question' },
      { id: 'ring', kind: 'enter', at: p.ring.at, dur: p.ring.dur },
      { id: 'mark', kind: 'enter', at: p.mark.at, dur: p.mark.dur },
      { id: 'promise', kind: 'enter', at: p.promise.at, dur: p.promise.dur, path: '/promise' },
      { id: 'topics', kind: 'enter', at: p.topics.at, dur: p.topics.dur,
        stagger: p.topics.stagger, count: p.topics.count, path: '/topics' },
    ];
    if (d.source) out.push({ id: 'source', kind: 'enter', at: p.source.at, dur: p.source.dur, path: '/source' });
    return out;
  };

  OMX.templates = Object.assign(OMX.templates || {}, {
    StatementOpeningScene: StatementOpeningScene,
    MetricOpeningScene: MetricOpeningScene,
    QuestionOpeningScene: QuestionOpeningScene,
  });
  OMX.templateIndex = Object.assign(OMX.templateIndex || {}, {
    'tpl.o-statement': StatementOpeningScene,
    'tpl.o-metric': MetricOpeningScene,
    'tpl.o-question': QuestionOpeningScene,
  });
  // 순수 기하/포맷 함수의 시험 좌석 — 브라우저에서 단독 검증한다 (프리뷰 meta 가 소비)
  OMX.openings = Object.assign(OMX.openings || {}, {
    stGeo: stGeo,
    stTokens: stTokens,
    stPlan: stPlan,
    mtFormat: mtFormat,
    mtWidthEm: mtWidthEm,
    mtPlan: mtPlan,
    qsPlan: qsPlan,
    consts: {
      stMargin: ST_MARGIN, stWidth: ST_W, stMin: ST_MIN_SIZE, stMax: ST_MAX_SIZE,
      mtValueSize: MT_VALUE_SIZE, mtSuffixRatio: MT_SUFFIX_RATIO, qsRing: QS_RING,
    },
  });
})();
