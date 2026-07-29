// 발표 레이아웃 씬 템플릿 4종 — tpl.l-split(좌 설명 + 우 근거 2단)·tpl.l-list(목록형 상세)·tpl.l-tree(계층 구조도)·tpl.l-quote(핵심 문장 각인).
// 실무 발표자료의 주력 배치 패턴을 가로 16:9 한 화면에 담는 그릇. 계약: 엔진 props(localTime 등) + data + theme,
// 정적 .schedule(data)/.nat, frame-match(첫/끝 프레임 안정), 모든 모션은 t(localTime)의 순수 함수.
(function () {
  'use strict';
  var OMX = (window.OMX = window.OMX || {});
  var Easing = window.Easing;
  var FrameChrome = OMX.metaphors['frame-chrome']; // 허용된 공통 크롬 (dot-grid 내장)
  var A = OMX.motion.A;                            // 은유 계층 공용 헬퍼 재사용
  var rise = OMX.motion.rise;
  var easeOf = OMX.motion.easeOf;

  function seg(t, at, dur, from, to, ease) {
    return A(t, at, dur, from, to, ease);
  }
  function enter(theme, t, at, dur, dy) {
    return rise(theme, t, at, dur, dy);
  }
  function popIn(theme, t, at, dur) {
    var m = theme.motion.pop;
    var d = dur == null ? m.dur : dur;
    var v = seg(t, at, d, 0, 1, easeOf(m.ease));
    return { opacity: Math.min(1, v), transform: 'scale(' + v + ')' };
  }
  // 콘텐츠 하단 한계 — 푸터(bottom+padTop+캡션 1행)와 18px 간격을 토큰에서 역산 → 955
  function botLimit(theme) {
    var L = theme.layout;
    return L.stageH - (L.footerBottom + L.footerPadTop + Math.round(theme.type.caption * 1.2) + 18);
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
  // 톤 → 칩/막대 색 (모두 contrastPairs 선언 조합)
  function chipTone(theme, tone) {
    var c = theme.component.chip;
    if (tone === 'success') return { bg: c.successBg, fg: c.successFg };
    if (tone === 'caution') return { bg: c.errorBg, fg: c.errorFg };
    if (tone === 'active') return { bg: c.activeBg, fg: c.activeFg };
    return { bg: c.accentBg, fg: c.accentFg }; // info (기본)
  }
  function barTone(theme, tone) {
    if (tone === 'secondary') return theme.color.blue2;
    if (tone === 'positive') return theme.color.green;
    if (tone === 'caution') return theme.color.red;
    return theme.color.blue;
  }
  var FRAME_SCHED = [
    { id: 'kicker', kind: 'enter', at: 0.15, dur: 0.7, path: '/kicker' },
    { id: 'title', kind: 'enter', at: 0.35, dur: 0.7, path: '/title' },
  ];

  /* ══ tpl.l-split — 좌측 설명 + 우측 시각물 2단 (은유: 말하고 나서 증거를 내민다) ══
     등장 순서 = 설득 순서: ① 리드 → ② 불릿 위→아래 → ③ 소결론(하단 고정) →
     ④ 근거 패널 → ⑤ 근거 내용(표 행 / 막대 / 도판 / 강조 문구).
     좌우 비율은 데이터가 아니라 스키마 고정값 2안 — '6:4'(시각물 60% : 설명 40%) · '5:5'(균형). */

  function spGeo(theme, d) {
    var L = theme.layout;
    var W = L.stageW - 2 * L.marginX;                 // 1640
    var gap = 48;
    var textW = d.ratio === '5:5' ? Math.round((W - gap) / 2) : Math.round((W - gap) * 0.4);
    var top = L.contentTop, bot = botLimit(theme);    // 330 · 955
    return {
      x: L.marginX, top: top, h: bot - top, bot: bot,
      textW: textW, visW: W - gap - textW, visX: L.marginX + textW + gap,
    };
  }
  function spVisualCount(v) {
    if (!v) return 0;
    if (v.kind === 'table') return 1 + ((v.table || {}).rows || []).length;
    if (v.kind === 'bars') return ((v.bars || {}).items || []).length;
    if (v.kind === 'note') return 1 + ((v.note || {}).lines || []).length;
    return 1;                                         // image
  }
  function spPlan(d) {
    var n = (d.bullets || []).length;
    var bAt = function (i) { return 1.5 + i * 0.45; };
    var lastB = bAt(Math.max(0, n - 1)) + 0.6;
    var concAt = lastB + 0.3;
    var panelAt = concAt + 0.5;
    var vn = spVisualCount(d.visual);
    var vAt = function (i) { return panelAt + 0.55 + i * 0.2; };
    return {
      bullets: n, bAt: bAt, bDur: 0.6,
      lead: { at: 0.9, dur: 0.7 },
      conclusion: { at: concAt, dur: 0.6 },
      panel: { at: panelAt, dur: 0.7 },
      vn: vn, vAt: vAt, vDur: 0.5,
    };
  }

  // ── 근거 슬롯 ① 간이표 — 헤더 + 행 순차 ─────────────────────────────
  function SplitTable(props) {
    var t = props.t, theme = props.theme, d = props.d, g = props.g, p = props.p;
    var cols = d.columns || [], rows = d.rows || [];
    var pad = 24, headerH = 56;
    var inner = g.visW - 2 * pad;
    var firstW = Math.round(inner * 0.42);
    var restW = (inner - firstW) / Math.max(1, cols.length - 1);
    var bodyH = g.h - 2 * pad - headerH;
    var rowH = bodyH / Math.max(1, rows.length);
    function colX(j) { return pad + (j === 0 ? 0 : firstW + (j - 1) * restW); }
    function colW(j) { return j === 0 ? firstW : restW; }
    return (
      <React.Fragment>
        {cols.map(function (c, j) {
          return (
            <div key={'th' + j} style={{
              position: 'absolute', left: colX(j), top: pad, width: colW(j), height: headerH,
              display: 'flex', alignItems: 'center',
              justifyContent: j === 0 ? 'flex-start' : 'center',
              paddingRight: j === 0 ? 12 : 0, boxSizing: 'border-box',
              fontSize: theme.type.caption, fontWeight: 800, color: theme.color.sub,
              lineHeight: 1.2, textAlign: j === 0 ? 'left' : 'center', overflowWrap: 'anywhere',
              opacity: seg(t, p.vAt(0) + j * 0.06, p.vDur, 0, 1),
            }}>{c.label}</div>
          );
        })}
        <div style={{
          position: 'absolute', left: pad, top: pad + headerH, height: 2,
          background: theme.color.sub, opacity: 0.5,
          width: seg(t, p.vAt(0) + 0.15, 0.6, 0, inner),
        }}></div>
        {rows.map(function (r, i) {
          var at = p.vAt(i + 1);
          return (
            <div key={'tr' + i} style={Object.assign({
              position: 'absolute', left: pad, top: pad + headerH + 4 + i * rowH,
              width: inner, height: rowH, boxSizing: 'border-box',
              background: i % 2 === 1 ? theme.color.bg : 'transparent', borderRadius: 10,
            }, enter(theme, t, at, p.vDur, 12))}>
              <div style={{
                position: 'absolute', left: 0, top: 0, width: firstW, height: '100%',
                boxSizing: 'border-box', padding: '0 12px 0 0',
                display: 'flex', alignItems: 'center',
                fontSize: theme.type.caption, lineHeight: 1.25, overflowWrap: 'anywhere',
                fontWeight: 800, color: theme.color.ink,
              }}>{r.label}</div>
              {(r.cells || []).map(function (cell, j) {
                return (
                  <div key={'tc' + j} style={{
                    position: 'absolute', left: colX(j + 1) - pad, top: 0,
                    width: colW(j + 1), height: '100%', boxSizing: 'border-box',
                    padding: '0 8px',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: theme.type.caption, lineHeight: 1.25,
                    textAlign: 'center', overflowWrap: 'anywhere',
                    fontWeight: cell.em ? 800 : 600,
                    color: cell.em ? theme.color.blue : theme.color.ink,
                  }}>{cell.v}</div>
                );
              })}
            </div>
          );
        })}
      </React.Fragment>
    );
  }

  // ── 근거 슬롯 ② 가로 막대 — 라벨/값 한 줄 + 트랙 성장 ────────────────
  function SplitBars(props) {
    var t = props.t, theme = props.theme, d = props.d, g = props.g, p = props.p;
    var items = d.items || [];
    var pad = 28;
    var inner = g.visW - 2 * pad;
    var dataMax = 0;
    items.forEach(function (it) { if (it.value > dataMax) dataMax = it.value; });
    var max = d.axisMax != null ? Math.max(d.axisMax, dataMax) : niceCeil(dataMax);
    if (!(max > 0)) max = 1;
    var rowPitch = 80, trackH = 16;
    var top = pad + Math.max(0, (g.h - 2 * pad - items.length * rowPitch) / 2);
    return (
      <React.Fragment>
        {items.map(function (it, i) {
          var at = p.vAt(i);
          var v = Math.max(0, Number(it.value) || 0);
          return (
            <div key={'br' + i} style={Object.assign({
              position: 'absolute', left: pad, top: top + i * rowPitch, width: inner, height: rowPitch,
            }, enter(theme, t, at, p.vDur, 14))}>
              <div style={{
                display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
                fontSize: theme.type.caption, lineHeight: 1.2, marginBottom: 10,
              }}>
                <span style={{ color: theme.color.ink, fontWeight: 700 }}>{it.label}</span>
                <span style={{ color: theme.color.blue, fontWeight: 800, whiteSpace: 'nowrap' }}>
                  {fmtNum(v)}{d.unit}
                </span>
              </div>
              <div style={{
                width: inner, height: trackH, borderRadius: theme.radius.pill,
                background: theme.color.blueSoft,
              }}>
                <div style={{
                  width: seg(t, at + 0.2, 0.8, 0, inner * Math.min(1, v / max)),
                  height: trackH, borderRadius: theme.radius.pill,
                  background: barTone(theme, it.tone),
                }}></div>
              </div>
            </div>
          );
        })}
      </React.Fragment>
    );
  }

  // ── 근거 슬롯 ③ 도판 — cover 로 채우고 하단 캡션 스트립 ──────────────
  function SplitImage(props) {
    var t = props.t, theme = props.theme, d = props.d, g = props.g, p = props.p;
    var capH = d.caption ? 100 : 0;
    var at = p.vAt(0);
    return (
      <React.Fragment>
        <img src={d.src} alt={d.alt} style={{
          position: 'absolute', left: 0, top: 0, width: '100%', height: g.h - capH,
          objectFit: 'cover', display: 'block',
          transform: 'scale(' + seg(t, at, 1.1, 1.05, 1) + ')',
        }} />
        {d.caption && (
          <div style={{
            position: 'absolute', left: 0, right: 0, bottom: 0, height: capH,
            background: theme.component.card.bg, borderTop: '1px solid ' + theme.color.line,
            boxSizing: 'border-box', padding: '0 24px',
            display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6,
          }}>
            <div style={Object.assign({
              fontSize: theme.type.note, fontWeight: 800, color: theme.color.ink,
              lineHeight: 1.2, overflowWrap: 'anywhere',
            }, enter(theme, t, at + 0.35, p.vDur, 10))}>{d.caption}</div>
            {d.source && (
              <div style={{
                fontSize: theme.type.caption, fontWeight: 600, color: theme.color.faint,
                lineHeight: 1.2, overflowWrap: 'anywhere',
                opacity: seg(t, at + 0.5, p.vDur, 0, 1),
              }}>출처 · {d.source}</div>
            )}
          </div>
        )}
      </React.Fragment>
    );
  }

  // ── 근거 슬롯 ④ 강조 박스 — 한 문장 + 부연 줄 ────────────────────────
  function SplitNote(props) {
    var t = props.t, theme = props.theme, d = props.d, g = props.g, p = props.p;
    var lines = d.lines || [];
    var tone = chipTone(theme, d.tone || 'info');
    return (
      <div style={{
        position: 'absolute', inset: 0, boxSizing: 'border-box', padding: '40px 36px',
        display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 26,
      }}>
        <div style={Object.assign({
          fontSize: theme.type.subtitle, fontWeight: 800, color: theme.color.ink,
          lineHeight: 1.3, letterSpacing: '-0.01em', overflowWrap: 'anywhere',
        }, enter(theme, t, p.vAt(0), p.vDur, 18))}>{d.headline}</div>
        {lines.length > 0 && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            {lines.map(function (ln, i) {
              return (
                <div key={'nl' + i} style={Object.assign({
                  display: 'flex', gap: 14, alignItems: 'flex-start',
                }, enter(theme, t, p.vAt(i + 1), p.vDur, 12))}>
                  <div style={{
                    flex: '0 0 auto', width: 10, height: 10, marginTop: 12,
                    borderRadius: theme.radius.pill, background: tone.fg,
                  }}></div>
                  <div style={{
                    fontSize: theme.type.body, color: theme.color.sub, fontWeight: 600,
                    lineHeight: 1.4, overflowWrap: 'anywhere',
                  }}>{ln}</div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    );
  }

  function SplitScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var g = spGeo(theme, d);
    var p = spPlan(d);
    var bullets = d.bullets || [];
    var v = d.visual || {};
    var card = theme.component.card;
    var isImage = v.kind === 'image';
    return (
      <FrameChrome label="2단" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {/* ── 좌: 설명 (리드 → 불릿, 정상 흐름 배치) ── */}
        <div style={{ position: 'absolute', left: g.x, top: g.top, width: g.textW }}>
          {d.lead && (
            <div style={Object.assign({
              fontSize: theme.type.lead, fontWeight: 800, color: theme.color.ink,
              lineHeight: 1.3, letterSpacing: '-0.01em', marginBottom: 26,
              overflowWrap: 'anywhere',
            }, enter(theme, t, p.lead.at, p.lead.dur))}>{d.lead}</div>
          )}
          {bullets.map(function (b, i) {
            // 불릿 간격 — 개수가 적으면 넓혀 열을 채운다(최악 2행 × 4개도 소결론 위에 든다)
            var bulletGap = bullets.length >= 4 ? 28 : 36;
            return (
              <div key={'bl' + i} style={Object.assign({
                display: 'flex', gap: 22, alignItems: 'flex-start',
                marginBottom: i === bullets.length - 1 ? 0 : bulletGap,
              }, enter(theme, t, p.bAt(i), p.bDur, 16))}>
                <div style={{
                  flex: '0 0 auto', width: 12, height: 12, marginTop: 11,
                  borderRadius: theme.radius.pill, background: theme.color.blue,
                }}></div>
                <div style={{
                  fontSize: theme.type.body, lineHeight: 1.4, overflowWrap: 'anywhere',
                  color: b.em ? theme.color.ink : theme.color.sub,
                  fontWeight: b.em ? 800 : 600,
                }}>{b.text}</div>
              </div>
            );
          })}
        </div>
        {/* ── 좌 하단 고정: 소결론 (불릿이 길어져도 바닥이 흔들리지 않는다) ── */}
        {d.conclusion && (
          <div style={Object.assign({
            position: 'absolute', left: g.x, width: g.textW,
            bottom: theme.layout.stageH - g.bot, boxSizing: 'border-box',
            background: theme.color.blueSoft, borderLeft: '5px solid ' + theme.color.blue,
            borderRadius: theme.radius.box, padding: '20px 24px',
            fontSize: theme.type.emphasis, lineHeight: 1.35, color: theme.color.ink,
            fontWeight: 700, overflowWrap: 'anywhere',
          }, enter(theme, t, p.conclusion.at, p.conclusion.dur, 18))}>
            {d.conclusion.pre}
            {d.conclusion.strong && (
              <span style={{ fontWeight: 800, color: theme.color.blue }}>{d.conclusion.strong}</span>
            )}
            {d.conclusion.post}
          </div>
        )}
        {/* ── 우: 근거 슬롯 (kind 로 분기) ── */}
        <div style={Object.assign({
          position: 'absolute', left: g.visX, top: g.top, width: g.visW, height: g.h,
          background: card.bg, border: '1px solid ' + card.border,
          borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
          overflow: isImage ? 'hidden' : 'visible',
        }, enter(theme, t, p.panel.at, p.panel.dur))}>
          {v.kind === 'table' && <SplitTable t={t} theme={theme} d={v.table || {}} g={g} p={p} />}
          {v.kind === 'bars' && <SplitBars t={t} theme={theme} d={v.bars || {}} g={g} p={p} />}
          {isImage && <SplitImage t={t} theme={theme} d={v.image || {}} g={g} p={p} />}
          {v.kind === 'note' && <SplitNote t={t} theme={theme} d={v.note || {}} g={g} p={p} />}
        </div>
      </FrameChrome>
    );
  }
  SplitScene.nat = 14;
  SplitScene.schedule = function (d) {
    var p = spPlan(d);
    var out = FRAME_SCHED.slice();
    if (d.lead) out.push({ id: 'lead', kind: 'enter', at: p.lead.at, dur: p.lead.dur, path: '/lead' });
    for (var i = 0; i < p.bullets; i++) {
      out.push({ id: 'bullet-' + i, kind: 'enter', at: p.bAt(i), dur: p.bDur, path: '/bullets/' + i });
    }
    if (d.conclusion) {
      out.push({ id: 'conclusion', kind: 'enter', at: p.conclusion.at, dur: p.conclusion.dur, path: '/conclusion' });
    }
    out.push({ id: 'visual-panel', kind: 'enter', at: p.panel.at, dur: p.panel.dur, path: '/visual' });
    for (var j = 0; j < p.vn; j++) {
      out.push({ id: 'visual-' + j, kind: 'enter', at: p.vAt(j), dur: p.vDur + 0.3 });
    }
    return out;
  };

  /* ══ tpl.l-list — 목록형 상세 (은유: 점검표 훑기 — 위에서 아래로 한 항목씩) ══
     행마다 [번호/아이콘] + 제목 + 설명(+상태 칩). 행 순차 등장 + 홀짝 배경 교차로
     스캔성을 확보한다. 행 수가 늘면 스키마가 설명 길이를 조이고(6행 이상 1줄)
     제목 글자 크기를 한 단 낮춘다 — 최소 폰트 24px 는 어느 경우에도 지킨다. */

  function lsGeo(theme, n) {
    var L = theme.layout;
    var top = L.contentTop, bot = botLimit(theme);
    var pitch = (bot - top) / Math.max(1, n);
    return {
      x: L.marginX, w: L.stageW - 2 * L.marginX, top: top, bot: bot,
      pitch: pitch, boxH: pitch - 4,
      badge: 56, padX: 24, chipW: 180, gap: 20,
    };
  }
  function lsPlan(d) {
    var n = (d.rows || []).length;
    var at = function (i) { return 1.1 + i * 0.4; };
    return { count: n, at: at, dur: 0.6, chipDelay: 0.3 };
  }
  function ListScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var rows = d.rows || [];
    var n = rows.length;
    var g = lsGeo(theme, n);
    var p = lsPlan(d);
    var card = theme.component.card;
    // 행이 많아지면 제목 한 단 축소 — 24px 하한 위에서만 움직인다
    var titleSize = n <= 6 ? theme.type.item : theme.type.emphasis;
    var textW = g.w - 2 * g.padX - g.badge - g.gap - (rows.some(function (r) { return !!r.chip; })
      ? g.chipW + g.gap : 0);
    return (
      <FrameChrome label="목록" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {rows.map(function (r, i) {
          var at = p.at(i);
          var even = i % 2 === 0;
          var tone = chipTone(theme, (r.chip || {}).tone);
          return (
            <div key={'lr' + i} style={Object.assign({
              position: 'absolute', left: g.x, top: g.top + i * g.pitch,
              width: g.w, height: g.boxH, boxSizing: 'border-box',
              background: even ? card.bg : 'transparent',
              border: '1px solid ' + (even ? card.border : 'transparent'),
              borderRadius: theme.radius.box,
              boxShadow: even ? card.shadowSoft : 'none',
              display: 'flex', alignItems: 'center', gap: g.gap,
              padding: '0 ' + g.padX + 'px',
            }, enter(theme, t, at, p.dur, 18))}>
              {/* 번호/아이콘 배지 */}
              <div style={{
                flex: '0 0 auto', width: g.badge, height: g.badge,
                borderRadius: theme.radius.chip,
                background: theme.color.blueSoft, color: theme.color.blue,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: theme.type.emphasis, fontWeight: 800, lineHeight: 1,
              }}>{r.icon || r.num || String(i + 1)}</div>
              {/* 제목 + 설명 */}
              <div style={{ flex: '1 1 auto', width: textW, minWidth: 0 }}>
                <div style={{
                  fontSize: titleSize, fontWeight: 800, color: theme.color.ink,
                  lineHeight: 1.2, overflowWrap: 'anywhere',
                }}>{r.title}</div>
                {r.desc && (
                  <div style={{
                    fontSize: theme.type.caption, fontWeight: 600, color: theme.color.sub,
                    lineHeight: 1.2, marginTop: 4, overflowWrap: 'anywhere',
                  }}>{r.desc}</div>
                )}
              </div>
              {/* 상태 칩 */}
              {r.chip && (
                <div style={Object.assign({
                  flex: '0 0 auto', maxWidth: g.chipW,
                  background: tone.bg, color: tone.fg,
                  fontSize: theme.type.caption, fontWeight: 800, lineHeight: 1,
                  padding: '11px 18px', borderRadius: theme.radius.pill, whiteSpace: 'nowrap',
                }, popIn(theme, t, at + p.chipDelay))}>{r.chip.text}</div>
              )}
            </div>
          );
        })}
      </FrameChrome>
    );
  }
  ListScene.nat = 14;
  ListScene.schedule = function (d) {
    var p = lsPlan(d);
    var out = FRAME_SCHED.slice();
    for (var i = 0; i < p.count; i++) {
      out.push({ id: 'row-' + i, kind: 'enter', at: p.at(i), dur: p.dur, path: '/rows/' + i });
      if (((d.rows || [])[i] || {}).chip) {
        out.push({ id: 'row-' + i + '-chip', kind: 'enter', at: p.at(i) + p.chipDelay, dur: 0.45 });
      }
    }
    return out;
  };

  /* ══ tpl.l-tree — 계층 구조도 (은유: 조직도 — 위계를 선으로 그린다) ══
     concept 의 방사형(동등한 참여자)과 달리 이것은 상하 위계를 그린다.
     structured graph(shape=tree) payload 를 그대로 받는다 — nodes[{id,label,level,note}] + edges[{from,to}].
     등장은 레벨 순서: ① 루트 → ② 루트 스텁·버스·가지 스텁(직교 ㄱ자) → ③ 중간 노드 → ④ 레일 → ⑤ 리프. */

  var TREE_BRANCH_MAX = 4;   // 중간 노드 상한 (스키마 maxContains 와 동일)
  var TREE_LEAF_MAX = 4;     // 가지당 리프 상한 — 세로 공간 실측 역산

  function treeModel(d) {
    var nodes = d.nodes || [], edges = d.edges || [];
    var root = null, branches = [], leafOf = {};
    var i;
    for (i = 0; i < nodes.length; i++) {
      if (nodes[i].level === 0 && root === null) root = nodes[i];
      else if (nodes[i].level === 1 && branches.length < TREE_BRANCH_MAX) branches.push(nodes[i]);
    }
    var parentOf = {};
    for (i = 0; i < edges.length; i++) parentOf[edges[i].to] = edges[i].from;
    for (i = 0; i < branches.length; i++) leafOf[branches[i].id] = [];
    for (i = 0; i < nodes.length; i++) {
      var nd = nodes[i];
      if (nd.level !== 2) continue;
      var pid = parentOf[nd.id];
      if (leafOf[pid] && leafOf[pid].length < TREE_LEAF_MAX) leafOf[pid].push(nd);
    }
    return { root: root, branches: branches, leafOf: leafOf };
  }
  function trGeo(theme, n) {
    var L = theme.layout;
    var W = L.stageW - 2 * L.marginX;
    var gap = 36;
    var colW = (W - Math.max(0, n - 1) * gap) / Math.max(1, n);
    var rootW = 560, rootH = 100;
    return {
      x: L.marginX, w: W, gap: gap, colW: colW,
      rootX: L.marginX + (W - rootW) / 2, rootY: L.contentTop, rootW: rootW, rootH: rootH,
      busY: L.contentTop + rootH + 40,
      brY: L.contentTop + rootH + 82, brH: 116,
      leafTop: L.contentTop + rootH + 82 + 116 + 22,
      leafPitch: 78, leafH: 68, railDx: 30, leafDx: 62,
      bot: botLimit(theme),
    };
  }
  function trPlan(d) {
    var m = treeModel(d);
    var nb = m.branches.length;
    var brAt = function (i) { return 2.3 + i * 0.28; };
    var railAt = function (i) { return 3.4 + i * 0.3; };
    var leafAt = function (i, k) { return 3.7 + i * 0.3 + k * 0.16; };
    return {
      model: m, nb: nb,
      root: { at: 0.9, dur: 0.7 },
      stub: { at: 1.5, dur: 0.4 }, bus: { at: 1.8, dur: 0.5 }, drop: { at: 2.1, dur: 0.4 },
      brAt: brAt, brDur: 0.6, railAt: railAt, railDur: 0.5,
      leafAt: leafAt, leafDur: 0.5,
      omitted: { at: brAt(Math.max(0, nb - 1)) + 0.6, dur: 0.5 },
    };
  }
  function TreeScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = trPlan(d);
    var m = p.model;
    var branches = m.branches;
    var g = trGeo(theme, branches.length);
    var card = theme.component.card;
    var net = theme.component.network;
    function brX(i) { return g.x + i * (g.colW + g.gap); }
    function brCx(i) { return brX(i) + g.colW / 2; }
    var firstCx = branches.length ? brCx(0) : g.x;
    var lastCx = branches.length ? brCx(branches.length - 1) : g.x;
    var busW = Math.max(1, lastCx - firstCx);
    var rootCx = g.rootX + g.rootW / 2;
    return (
      <FrameChrome label="계층" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {/* ── 루트 ── */}
        {m.root && (
          <div style={Object.assign({
            position: 'absolute', left: g.rootX, top: g.rootY, width: g.rootW, height: g.rootH,
            boxSizing: 'border-box', borderRadius: theme.radius.card,
            background: net.centerBg, color: net.centerFg, boxShadow: net.centerShadow,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: theme.type.cardTitle, fontWeight: 800, lineHeight: 1.2,
            padding: '0 24px', whiteSpace: 'nowrap',
          }, enter(theme, t, p.root.at, p.root.dur))}>{m.root.label}</div>
        )}
        {/* ── 직교 연결선 (비텍스트) — 루트 스텁 → 가로 버스 → 가지 스텁 ── */}
        <div style={{
          position: 'absolute', left: rootCx - 1.5, top: g.rootY + g.rootH, width: 3,
          height: seg(t, p.stub.at, p.stub.dur, 0, g.busY - (g.rootY + g.rootH)),
          background: net.line,
        }}></div>
        <div style={{
          position: 'absolute', left: firstCx, top: g.busY - 1.5, width: busW, height: 3,
          background: net.line, transformOrigin: '50% 50%',
          transform: 'scaleX(' + seg(t, p.bus.at, p.bus.dur, 0, 1) + ')',
        }}></div>
        {branches.map(function (b, i) {
          return (
            <div key={'st' + i} style={{
              position: 'absolute', left: brCx(i) - 1.5, top: g.busY, width: 3,
              height: seg(t, p.drop.at + i * 0.06, p.drop.dur, 0, g.brY - g.busY),
              background: net.line,
            }}></div>
          );
        })}
        {/* ── 중간 노드 ── */}
        {branches.map(function (b, i) {
          return (
            <div key={'br' + i} style={Object.assign({
              position: 'absolute', left: brX(i), top: g.brY, width: g.colW, height: g.brH,
              boxSizing: 'border-box', background: card.bg,
              border: '2px solid ' + net.nodeBorder, borderRadius: theme.radius.card,
              boxShadow: card.shadowSoft, padding: '0 20px',
              display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: 6,
            }, enter(theme, t, p.brAt(i), p.brDur, 20))}>
              <div style={{
                fontSize: theme.type.note, fontWeight: 800, color: theme.color.blue,
                lineHeight: 1.25, overflowWrap: 'anywhere',
              }}>{b.label}</div>
              {b.note && (
                <div style={{
                  fontSize: theme.type.caption, fontWeight: 600, color: theme.color.sub,
                  lineHeight: 1.2, overflowWrap: 'anywhere',
                }}>{b.note}</div>
              )}
            </div>
          );
        })}
        {/* ── 리프 — 가지별 세로 레일 + ㄱ자 스텁 ── */}
        {branches.map(function (b, i) {
          var leaves = m.leafOf[b.id] || [];
          if (!leaves.length) return null;
          var railX = brX(i) + g.railDx;
          var lastCy = g.leafTop + (leaves.length - 1) * g.leafPitch + g.leafH / 2;
          return (
            <React.Fragment key={'lf' + i}>
              <div style={{
                position: 'absolute', left: railX - 1.5, top: g.brY + g.brH, width: 3,
                height: seg(t, p.railAt(i), p.railDur, 0, lastCy - (g.brY + g.brH)),
                background: net.line,
              }}></div>
              {leaves.map(function (lf, k) {
                var at = p.leafAt(i, k);
                var cy = g.leafTop + k * g.leafPitch + g.leafH / 2;
                return (
                  <React.Fragment key={'lfn' + k}>
                    <div style={{
                      position: 'absolute', left: railX, top: cy - 1.5, height: 3,
                      width: seg(t, at, 0.35, 0, g.leafDx - g.railDx), background: net.line,
                    }}></div>
                    <div style={Object.assign({
                      position: 'absolute', left: brX(i) + g.leafDx,
                      top: g.leafTop + k * g.leafPitch,
                      width: g.colW - g.leafDx, height: g.leafH, boxSizing: 'border-box',
                      background: card.bg, border: '1px solid ' + card.border,
                      borderRadius: theme.radius.chip, padding: '0 16px',
                      display: 'flex', alignItems: 'center',
                      fontSize: theme.type.caption, fontWeight: 700, color: theme.color.ink,
                      lineHeight: 1.25, overflowWrap: 'anywhere',
                    }, enter(theme, t, at + 0.12, p.leafDur, 10))}>{lf.label}</div>
                  </React.Fragment>
                );
              })}
            </React.Fragment>
          );
        })}
        {/* ── 표시하지 못한 노드 수 — 루트 우측 여백에 정직하게 ── */}
        {d.omitted != null && (
          <div style={{
            position: 'absolute', right: theme.layout.marginX,
            top: g.rootY + g.rootH / 2 - 16, textAlign: 'right',
            fontSize: theme.type.caption, fontWeight: 600, color: theme.color.faint,
            opacity: seg(t, p.omitted.at, p.omitted.dur, 0, 1),
          }}>…외 {d.omitted}개 노드</div>
        )}
      </FrameChrome>
    );
  }
  TreeScene.nat = 12;
  TreeScene.schedule = function (d) {
    var p = trPlan(d);
    var out = FRAME_SCHED.concat([
      { id: 'root', kind: 'enter', at: p.root.at, dur: p.root.dur, path: '/nodes/0' },
      { id: 'stub', kind: 'enter', at: p.stub.at, dur: p.stub.dur },
      { id: 'bus', kind: 'enter', at: p.bus.at, dur: p.bus.dur },
      { id: 'drop', kind: 'enter', at: p.drop.at, dur: p.drop.dur, stagger: 0.06, count: p.nb },
    ]);
    var m = p.model;
    for (var i = 0; i < m.branches.length; i++) {
      out.push({ id: 'branch-' + i, kind: 'enter', at: p.brAt(i), dur: p.brDur });
      var leaves = m.leafOf[m.branches[i].id] || [];
      if (!leaves.length) continue;
      out.push({ id: 'rail-' + i, kind: 'enter', at: p.railAt(i), dur: p.railDur });
      out.push({
        id: 'leaves-' + i, kind: 'enter', at: p.leafAt(i, 0) + 0.12,
        dur: p.leafDur, stagger: 0.16, count: leaves.length,
      });
    }
    if (d.omitted != null) {
      out.push({ id: 'omitted', kind: 'enter', at: p.omitted.at, dur: p.omitted.dur, path: '/omitted' });
    }
    return out;
  };

  /* ══ tpl.l-quote — 핵심 문장 강조 (은유: 각인 — 여백이 문장을 밀어 올린다) ══
     선언·인용 한 문장을 화면 중앙에 크게. 챕터 전환·결론 각인용.
     글자 크기는 문장 길이에 따라 80/70/60px 3단 — 토큰 타입 스케일이 56 다음 92 로 건너뛰므로
     이 구간만 명시 사다리를 쓴다(모두 최소 폰트 24px 을 크게 상회). */

  var QUOTE_SIZES = [80, 70, 60];
  var QUOTE_BREAKS = [30, 48];        // 이 글자수 이하면 각각 80·70, 초과면 60
  var QUOTE_W = 1400;

  function quoteSize(text) {
    var n = (text || '').length;
    if (n <= QUOTE_BREAKS[0]) return QUOTE_SIZES[0];
    if (n <= QUOTE_BREAKS[1]) return QUOTE_SIZES[1];
    return QUOTE_SIZES[2];
  }
  function qtPlan(d) {
    return {
      texture: { at: 0.6, dur: 0.7 },
      quote: { at: 0.9, dur: 0.9 },
      rule: { at: 1.8, dur: 0.5 },
      speaker: { at: 2.05, dur: 0.6 },
      role: { at: 2.25, dur: 0.6 },
    };
  }
  // 인용부호 장식 — 텍스트가 아닌 도형 2개 (대비 게이트 대상 외)
  function QuoteMarks(props) {
    var t = props.t, theme = props.theme, p = props.p;
    var op = seg(t, p.texture.at, p.texture.dur, 0, 1);
    function mark(flip, left, top) {
      return (
        <div style={{
          position: 'absolute', left: left, top: top, display: 'flex', gap: 14,
          opacity: op, transform: flip ? 'rotate(180deg)' : 'none',
        }}>
          <div style={{
            width: 30, height: 54, background: theme.color.blueBorder,
            borderRadius: '50% 50% 8px 50%',
          }}></div>
          <div style={{
            width: 30, height: 54, background: theme.color.blueBorder,
            borderRadius: '50% 50% 8px 50%',
          }}></div>
        </div>
      );
    }
    return (
      <React.Fragment>
        {mark(false, (theme.layout.stageW - QUOTE_W) / 2 - 84, 300)}
        {mark(true, (theme.layout.stageW + QUOTE_W) / 2 + 10, 706)}
      </React.Fragment>
    );
  }
  function QuoteScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = qtPlan(d);
    var size = quoteSize(d.quote);
    var texture = d.texture || 'none';
    return (
      <FrameChrome label="각인" t={t} theme={theme} kicker={d.kicker} frame={d.frame}>
        {texture === 'marks' && <QuoteMarks t={t} theme={theme} p={p} />}
        <div style={{
          position: 'absolute', left: 0, right: 0, top: Math.round(theme.layout.stageH * 0.52),
          transform: 'translateY(-50%)',
          display: 'flex', flexDirection: 'column', alignItems: 'center',
        }}>
          {texture === 'rule' && (
            <div style={{
              width: seg(t, p.texture.at, p.texture.dur, 0, 120), height: 5,
              background: theme.color.blue, borderRadius: 3, marginBottom: 44,
            }}></div>
          )}
          <div style={Object.assign({
            width: QUOTE_W, textAlign: 'center',
            fontSize: size, fontWeight: 800, color: theme.color.ink,
            lineHeight: 1.28, letterSpacing: '-0.02em', overflowWrap: 'anywhere',
          }, enter(theme, t, p.quote.at, p.quote.dur, 30))}>{d.quote}</div>
          {(d.speaker || d.role) && (
            <div style={{
              width: seg(t, p.rule.at, p.rule.dur, 0, 90), height: 3,
              background: theme.color.blue, borderRadius: 2, marginTop: 52, marginBottom: 28,
            }}></div>
          )}
          {d.speaker && (
            <div style={Object.assign({
              fontSize: theme.type.subtitle, fontWeight: 800, color: theme.color.blue,
              lineHeight: 1.3, textAlign: 'center', maxWidth: QUOTE_W, overflowWrap: 'anywhere',
            }, enter(theme, t, p.speaker.at, p.speaker.dur, 14))}>{d.speaker}</div>
          )}
          {d.role && (
            <div style={Object.assign({
              fontSize: theme.type.body, fontWeight: 600, color: theme.color.sub,
              lineHeight: 1.3, marginTop: 8, textAlign: 'center',
              maxWidth: QUOTE_W, overflowWrap: 'anywhere',
            }, enter(theme, t, p.role.at, p.role.dur, 12))}>{d.role}</div>
          )}
        </div>
      </FrameChrome>
    );
  }
  QuoteScene.nat = 8;
  QuoteScene.schedule = function (d) {
    var p = qtPlan(d);
    var out = [{ id: 'kicker', kind: 'enter', at: 0.15, dur: 0.7, path: '/kicker' }];
    if (d.texture && d.texture !== 'none') {
      out.push({ id: 'texture', kind: 'enter', at: p.texture.at, dur: p.texture.dur });
    }
    out.push({ id: 'quote', kind: 'enter', at: p.quote.at, dur: p.quote.dur, path: '/quote' });
    if (d.speaker || d.role) {
      out.push({ id: 'rule', kind: 'enter', at: p.rule.at, dur: p.rule.dur });
    }
    if (d.speaker) out.push({ id: 'speaker', kind: 'enter', at: p.speaker.at, dur: p.speaker.dur, path: '/speaker' });
    if (d.role) out.push({ id: 'role', kind: 'enter', at: p.role.at, dur: p.role.dur, path: '/role' });
    return out;
  };

  OMX.templates = Object.assign(OMX.templates || {}, {
    SplitScene: SplitScene,
    ListScene: ListScene,
    TreeScene: TreeScene,
    QuoteScene: QuoteScene,
  });
  OMX.templateIndex = Object.assign(OMX.templateIndex || {}, {
    'tpl.l-split': SplitScene,
    'tpl.l-list': ListScene,
    'tpl.l-tree': TreeScene,
    'tpl.l-quote': QuoteScene,
  });
})();
