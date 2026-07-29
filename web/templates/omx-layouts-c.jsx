// 수치 표현 씬 템플릿 2종 — tpl.c-ratio(비율·구성비: 도넛/와플 + 범례)·tpl.c-trend(추세 시계열: 라인/영역 + 판독 칼럼).
// 커버리지 공백 ①비율(pie·waffle·treemap·packing)·②추세(chart line/area)를 담는 그릇. 계약: 엔진 props(localTime 등) + data + theme,
// 정적 .schedule(data)/.nat, frame-match(첫/끝 프레임 안정), 모든 모션은 t(localTime)의 순수 함수.
// 수치 왜곡 방지는 렌더러 구조로 강제한다 — 백분율은 저작 불가(값에서 파생 → 각도 합 정확히 360°), y 하한 기본 0(절단 시 화면 표기 강제).
(function () {
  'use strict';
  var OMX = (window.OMX = window.OMX || {});
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

  // ── 토큰 색 램프 — 하드코딩 hex 없이 테마 두 색 사이를 보간 ────────────
  function hex2rgb(h) {
    var s = String(h).replace('#', '');
    if (s.length === 3) s = s[0] + s[0] + s[1] + s[1] + s[2] + s[2];
    return [parseInt(s.slice(0, 2), 16), parseInt(s.slice(2, 4), 16), parseInt(s.slice(4, 6), 16)];
  }
  function rgb2hex(c) {
    var out = '#';
    for (var i = 0; i < 3; i++) {
      var v = Math.max(0, Math.min(255, Math.round(c[i]))).toString(16);
      out += v.length < 2 ? '0' + v : v;
    }
    return out;
  }
  function mixHex(a, b, k) {
    var x = hex2rgb(a), y = hex2rgb(b);
    return rgb2hex([x[0] + (y[0] - x[0]) * k, x[1] + (y[1] - x[1]) * k, x[2] + (y[2] - x[2]) * k]);
  }

  var FRAME_SCHED = [
    { id: 'kicker', kind: 'enter', at: 0.15, dur: 0.7, path: '/kicker' },
    { id: 'title', kind: 'enter', at: 0.35, dur: 0.7, path: '/title' },
  ];

  /* ══ tpl.c-ratio — 비율·구성비 (은유: 하나의 원을 나눠 갖는다) ═══════════
     전체를 100 으로 놓고 구성 비중을 보여준다 — 점유율·예산 배분·유형별 분포.
     등장 순서 = 비중의 위계: ① 링 트랙(전체의 테두리) → ② 큰 조각부터 시계 방향으로 자라며
     짝이 되는 범례 행이 함께 들어온다 → ③ 중앙 총계 → ④ 각주(보정·출처).

     수치 왜곡 방지 (구조로 강제):
       · 백분율/각도 필드가 스키마에 없다 — 화면 비율은 value/Σvalue 파생이라 각도 합 = 360°.
       · value minimum 0 — 음수 조각 불가. 조각 정렬도 렌더러가 한다(저작 순서로 위계 왜곡 불가).
       · 3D·기울임 없음 — 정면 평면 원환만 그린다.
       · total 선언 시 미표기 잔량은 '기타(미표기)' 조각으로 자동 편입하고 각주에 명시한다.
       · 5% 미만 조각은 링 밖 라벨을 생략하고 범례로만 — 겹침 오독 방지. */

  var RATIO_LABEL_MIN_SHARE = 5;   // 링 밖 비율 라벨을 다는 최소 지분(%)
  var RATIO_OTHER_LABEL = '기타(미표기)';
  var WAFFLE_CELLS = 100;          // 10×10 = 100칸 (1칸 = 1%)
  var WAFFLE_COLS = 10;

  // 최대잔여법 — 반올림해도 칸 합이 정확히 100 이 되게 배분한다 (합계 왜곡 차단)
  function waffleCounts(shares) {
    var base = [], rema = [], used = 0, i;
    for (i = 0; i < shares.length; i++) {
      var raw = shares[i] * WAFFLE_CELLS / 100;
      var f = Math.floor(raw);
      base.push(f);
      rema.push({ i: i, r: raw - f });
      used += f;
    }
    rema.sort(function (a, b) { return b.r - a.r || a.i - b.i; });
    for (i = 0; i < WAFFLE_CELLS - used; i++) base[rema[i % Math.max(1, rema.length)].i] += 1;
    return base;
  }

  function ratioModel(d) {
    var src = d.series || [];
    var items = [], i;
    for (i = 0; i < src.length; i++) {
      items.push({
        label: src[i].label, display: src[i].display,
        value: Math.max(0, Number(src[i].value) || 0), idx: i,
      });
    }
    // 큰 것부터 — 동값이면 저작 순서 유지 (안정 정렬)
    items.sort(function (a, b) { return b.value - a.value || a.idx - b.idx; });
    var sum = 0;
    for (i = 0; i < items.length; i++) sum += items[i].value;
    var total = d.total || {};
    var declared = total.value != null ? Number(total.value) : null;
    var gap = 0, over = 0;
    if (declared != null && declared > 0) {
      var eps = declared * 0.005;                 // ±0.5% 허용대
      if (declared - sum > eps) {
        gap = declared - sum;
        items.push({ label: RATIO_OTHER_LABEL, value: gap, idx: items.length, other: true });
        sum = declared;
      } else if (sum - declared > eps) {
        over = sum - declared;                    // 초과는 숨기지 않고 각주에 드러낸다
      }
    }
    if (!(sum > 0)) sum = 1;
    var shares = [], deg = [], start = [], acc = 0;
    for (i = 0; i < items.length; i++) {
      shares.push(items[i].value / sum * 100);
      deg.push(items[i].value / sum * 360);
      start.push(acc);
      acc += deg[i];
    }
    return { items: items, sum: sum, shares: shares, deg: deg, start: start,
             gap: gap, over: over, declared: declared };
  }

  function ratioPlan(d) {
    var m = ratioModel(d);
    var n = m.items.length;
    var at = function (i) { return 1.5 + i * 0.5; };
    var last = at(Math.max(0, n - 1)) + 0.8;
    return {
      model: m, n: n, at: at, dur: 0.8, legendDelay: 0.15, legendDur: 0.5,
      ring: { at: 0.9, dur: 0.6 },
      center: { at: last + 0.3, dur: 0.7 },
      foot: { at: last + 1.0, dur: 0.6 },
    };
  }

  function raGeo(theme) {
    var L = theme.layout;
    var top = L.contentTop, bot = botLimit(theme);        // 330 · 955
    var zoneW = 660, gap = 40;
    return {
      top: top, bot: bot, h: bot - top,
      cx: L.marginX + zoneW / 2, cy: top + 300,           // 470 · 630
      R: 240, rIn: 158, labelR: 280,
      wCell: 46, wGap: 7, wTop: top + 88, wX: L.marginX,
      legX: L.marginX + zoneW + gap,                      // 840
      legW: L.stageW - L.marginX - (L.marginX + zoneW + gap),  // 940
      footTop: top + 555,
    };
  }

  // 원환 조각 path — 12시 기준 시계 방향(a0→a1, 도 단위). 정면 평면만 그린다.
  function arcPath(cx, cy, R, r, a0, a1) {
    var sweep = Math.max(0, Math.min(a1 - a0, 359.999));
    var rad = Math.PI / 180;
    function pt(ang, rr) {
      return [cx + rr * Math.sin(ang * rad), cy - rr * Math.cos(ang * rad)];
    }
    var e = a0 + sweep;
    var pA = pt(a0, R), pB = pt(e, R), pC = pt(e, r), pD = pt(a0, r);
    var large = sweep > 180 ? 1 : 0;
    return 'M' + pA[0] + ' ' + pA[1]
      + 'A' + R + ' ' + R + ' 0 ' + large + ' 1 ' + pB[0] + ' ' + pB[1]
      + 'L' + pC[0] + ' ' + pC[1]
      + 'A' + r + ' ' + r + ' 0 ' + large + ' 0 ' + pD[0] + ' ' + pD[1] + 'Z';
  }

  function sliceColor(theme, i, n, other) {
    if (other) return theme.color.skel;                 // 미표기 잔량은 중립 회색
    var k = n > 1 ? (i / (n - 1)) * 0.78 : 0;           // 진한 강조색 → 옅은 테두리색
    return mixHex(theme.color.blue, theme.color.blueBorder, k);
  }

  // ── 도넛 ─────────────────────────────────────────────────────────────
  function RatioDonut(props) {
    var t = props.t, theme = props.theme, g = props.g, p = props.p, m = props.m;
    var n = m.items.length;
    var mid = (g.R + g.rIn) / 2;
    return (
      <React.Fragment>
        <svg width={g.R * 2 + 4} height={g.R * 2 + 4} viewBox={'0 0 ' + (g.R * 2 + 4) + ' ' + (g.R * 2 + 4)}
          data-c-donut="1"
          style={{
            position: 'absolute', left: g.cx - g.R - 2, top: g.cy - g.R - 2,
            opacity: seg(t, p.ring.at, p.ring.dur, 0, 1),
          }}>
          <circle cx={g.R + 2} cy={g.R + 2} r={mid} fill="none"
            stroke={theme.color.blueSoft} strokeWidth={g.R - g.rIn} />
          {m.items.map(function (it, i) {
            var grow = seg(t, p.at(i), p.dur, 0, 1);
            if (grow <= 0) return null;
            return (
              <path key={'sl' + i}
                data-c-slice={i}
                data-c-slice-deg={m.deg[i].toFixed(4)}
                data-c-slice-share={m.shares[i].toFixed(4)}
                d={arcPath(g.R + 2, g.R + 2, g.R, g.rIn,
                  m.start[i], m.start[i] + m.deg[i] * grow)}
                fill={sliceColor(theme, i, n, it.other)} />
            );
          })}
        </svg>
        {/* 링 밖 비율 라벨 — 5% 미만은 범례로만 (겹침 오독 방지) */}
        {m.items.map(function (it, i) {
          if (m.shares[i] < RATIO_LABEL_MIN_SHARE) return null;
          var ang = (m.start[i] + m.deg[i] / 2) * Math.PI / 180;
          return (
            <div key={'rl' + i} style={{
              position: 'absolute',
              left: g.cx + g.labelR * Math.sin(ang), top: g.cy - g.labelR * Math.cos(ang),
              transform: 'translate(-50%, -50%)', whiteSpace: 'nowrap',
              fontSize: theme.type.caption, fontWeight: 800, color: theme.color.ink,
              lineHeight: 1.2,
              opacity: seg(t, p.at(i) + p.dur - 0.2, 0.5, 0, 1),
            }}>{fmtNum(m.shares[i])}%</div>
          );
        })}
      </React.Fragment>
    );
  }

  // ── 와플 (10×10 = 100칸, 1칸 = 1%) ───────────────────────────────────
  function RatioWaffle(props) {
    var t = props.t, theme = props.theme, g = props.g, p = props.p, m = props.m;
    var n = m.items.length;
    var counts = waffleCounts(m.shares);
    var cells = [], i, k;
    for (i = 0; i < n; i++) for (k = 0; k < counts[i]; k++) cells.push({ i: i, k: k, c: counts[i] });
    var pitch = g.wCell + g.wGap;
    return (
      <React.Fragment>
        {cells.map(function (c, idx) {
          var col = idx % WAFFLE_COLS, rowN = Math.floor(idx / WAFFLE_COLS);
          var at = p.at(c.i) + (c.k / Math.max(1, c.c)) * p.dur;
          return (
            <div key={'wc' + idx} data-c-waffle={idx} data-c-waffle-item={c.i} style={Object.assign({
              position: 'absolute', left: g.wX + col * pitch, top: g.wTop + rowN * pitch,
              width: g.wCell, height: g.wCell, borderRadius: theme.radius.bar,
              background: sliceColor(theme, c.i, n, m.items[c.i].other),
            }, popIn(theme, t, at, 0.4))}></div>
          );
        })}
      </React.Fragment>
    );
  }

  function RatioScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = ratioPlan(d);
    var m = p.model;
    var g = raGeo(theme);
    var n = m.items.length;
    var waffle = d.style === 'waffle';
    var unit = d.unit || '';
    var center = d.center || {};
    var total = d.total || {};
    var centerValue = center.value != null ? center.value
      : (m.declared != null ? fmtNum(m.declared) + unit : fmtNum(m.sum) + unit);
    var centerLabel = center.label != null ? center.label : (total.label || '전체');
    // 각주 — 자동 보정·초과는 숨기지 않고 화면에 쓴다
    var notes = [];
    if (m.gap > 0) notes.push(RATIO_OTHER_LABEL + ' ' + fmtNum(m.gap) + unit + ' 자동 편입');
    if (m.over > 0) notes.push('명시 합이 전체를 ' + fmtNum(m.over) + unit + ' 초과');
    if (d.footnote && d.footnote.text) notes.push(d.footnote.text);
    var footText = notes.join(' · ');
    var legH = footText ? 545 : g.h;
    var pitch = legH / Math.max(1, n);
    var rowH = pitch - 10;
    // 범례 행 우측 고정 존 — 비율(150) + 절대값(150) + 간격(16)
    var pctRight = 162, pctW = 150, dispW = 150;
    var labelW = g.legW - 34 - pctRight - pctW - 16;   // 578
    return (
      <FrameChrome label="비율" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {waffle ? (
          <React.Fragment>
            <div style={Object.assign({
              position: 'absolute', left: theme.layout.marginX, top: g.top + 4,
              width: 660, display: 'flex', alignItems: 'baseline', gap: 16,
            }, enter(theme, t, p.ring.at, p.ring.dur, 16))}>
              <div style={{
                fontSize: theme.type.sectionTitle, fontWeight: 800, color: theme.color.blue,
                lineHeight: 1.15, letterSpacing: '-0.02em', whiteSpace: 'nowrap',
              }}>{centerValue}</div>
              <div style={{
                fontSize: theme.type.body, fontWeight: 700, color: theme.color.sub,
                lineHeight: 1.2, whiteSpace: 'nowrap',
              }}>{centerLabel}</div>
            </div>
            <RatioWaffle t={t} theme={theme} g={g} p={p} m={m} />
          </React.Fragment>
        ) : (
          <React.Fragment>
            <RatioDonut t={t} theme={theme} g={g} p={p} m={m} />
            <div style={Object.assign({
              position: 'absolute', left: g.cx - g.rIn + 12, top: g.cy - 76,
              width: 2 * (g.rIn - 12), textAlign: 'center',
            }, enter(theme, t, p.center.at, p.center.dur, 18))}>
              <div style={{
                fontSize: theme.type.display, fontWeight: 800, color: theme.color.blue,
                lineHeight: 1.15, letterSpacing: '-0.02em', whiteSpace: 'nowrap',
              }}>{centerValue}</div>
              <div style={{
                marginTop: 8, fontSize: theme.type.caption, fontWeight: 700,
                color: theme.color.sub, lineHeight: 1.2, whiteSpace: 'nowrap',
              }}>{centerLabel}</div>
            </div>
          </React.Fragment>
        )}
        {/* ── 범례 — 조각과 짝이 되어 같은 순서로 들어온다 ── */}
        {m.items.map(function (it, i) {
          var at = p.at(i) + p.legendDelay;
          var color = sliceColor(theme, i, n, it.other);
          var trackW = labelW;
          return (
            <div key={'lg' + i} data-c-legend={i} style={Object.assign({
              position: 'absolute', left: g.legX, top: g.top + i * pitch,
              width: g.legW, height: rowH, boxSizing: 'border-box',
              borderBottom: i === n - 1 ? 'none' : '1px solid ' + theme.color.line,
            }, enter(theme, t, at, p.legendDur, 14))}>
              <div style={{
                position: 'absolute', left: 0, top: (rowH - 50) / 2, width: g.legW, height: 50,
              }}>
                <div style={{
                  position: 'absolute', left: 0, top: 5, width: 20, height: 20,
                  borderRadius: theme.radius.bar, background: color,
                }}></div>
                <div style={{
                  position: 'absolute', left: 34, top: 0, width: labelW,
                  fontSize: theme.type.body, fontWeight: 700, color: theme.color.ink,
                  lineHeight: 1.2, overflowWrap: 'anywhere',
                }}>{it.label}</div>
                <div style={{
                  position: 'absolute', left: 34, top: 40, width: trackW, height: 8,
                  borderRadius: theme.radius.pill, background: theme.color.blueSoft,
                }}>
                  {/* 트랙 전체 = 100% — 지분만큼만 채운다 (상대 최대값 정규화 금지) */}
                  <div style={{
                    width: seg(t, at + 0.15, 0.6, 0, trackW * m.shares[i] / 100),
                    height: 8, borderRadius: theme.radius.pill, background: color,
                  }}></div>
                </div>
                <div style={{
                  position: 'absolute', right: pctRight, top: -2, width: pctW, textAlign: 'right',
                  fontSize: theme.type.subtitle, fontWeight: 800, color: theme.color.blue,
                  lineHeight: 1.2, whiteSpace: 'nowrap',
                }}>{fmtNum(m.shares[i])}%</div>
                <div style={{
                  position: 'absolute', right: 0, top: 8, width: dispW, textAlign: 'right',
                  fontSize: theme.type.caption, fontWeight: 600, color: theme.color.faint,
                  lineHeight: 1.2, whiteSpace: 'nowrap',
                }}>{it.display != null ? it.display : fmtNum(it.value) + unit}</div>
              </div>
            </div>
          );
        })}
        {footText && (
          <div style={Object.assign({
            position: 'absolute', left: g.legX, top: g.footTop, width: g.legW,
            fontSize: theme.type.caption, fontWeight: 600, color: theme.color.faint,
            lineHeight: 1.35, overflowWrap: 'anywhere',
          }, enter(theme, t, p.foot.at, p.foot.dur, 12))}>{footText}</div>
        )}
      </FrameChrome>
    );
  }
  RatioScene.nat = 12;
  RatioScene.schedule = function (d) {
    var p = ratioPlan(d);
    var m = p.model;
    var out = FRAME_SCHED.concat([
      { id: 'ring', kind: 'enter', at: p.ring.at, dur: p.ring.dur },
    ]);
    for (var i = 0; i < p.n; i++) {
      // '기타(미표기)' 자동 조각은 원본 data 에 대응 경로가 없다 — path 를 달지 않는다
      var slice = { id: 'slice-' + i, kind: 'enter', at: p.at(i), dur: p.dur };
      var legend = {
        id: 'legend-' + i, kind: 'enter', at: p.at(i) + p.legendDelay, dur: p.legendDur + 0.25,
      };
      if (!m.items[i].other) {
        slice.path = '/series/' + m.items[i].idx;
        legend.path = slice.path;
      }
      out.push(slice);
      out.push(legend);
    }
    out.push({ id: 'center', kind: 'enter', at: p.center.at, dur: p.center.dur, path: '/center' });
    if (m.gap > 0 || m.over > 0 || (d.footnote && d.footnote.text)) {
      out.push({ id: 'footnote', kind: 'enter', at: p.foot.at, dur: p.foot.dur, path: '/footnote' });
    }
    return out;
  };

  /* ══ tpl.c-trend — 추세 시계열 (은유: 값이 지나온 궤적) ═══════════════════
     시간에 따른 수치 변화 — 월별 실적·누적 진척·추이 비교. tpl.timeline(마일스톤)과 다르다.
     저건 사건의 이정표고 이건 값의 궤적이다.
     등장 순서 = 판독 순서: ① 패널 → ② 축·격자(측정 기준) → ③ 시점 라벨(구간 호명) →
     ④ 계열 범례 → ⑤ 라인이 좌→우로 그려짐(주계열 먼저) → ⑥ 최신 점 강조 링 →
     ⑦ 최신값 대형 수치 → ⑧ 변화율 배지 → ⑨ 한 줄 해석.

     수치 왜곡 방지 (구조로 강제):
       · y 하한 기본 0. axis.min 이 0 이 아니면 '축 절단' 칩과 축 파단 표식을 화면에 강제 표기.
       · axis.max 는 데이터 최댓값 미만이면 최댓값으로 승격 — 라인 절단 불가.
       · points[].at 이 전부 있으면 x 를 값 비례로 배치 (시점 간격 불균등을 등간격으로 속이지 않는다).
       · 변화 방향(direction ▲▼)과 평가(polarity 색)를 분리 — '불량률 하락'을 붉게 칠하지 않는다. */

  var TREND_TICKS = 5;             // y 눈금 5개 (하한 포함 ¼ 간격)
  var TREND_DIR_GLYPH = { up: '▲', down: '▼', flat: '■' };

  function trGeoC(theme) {
    var L = theme.layout;
    var readW = 420, gap = 40;
    var panelW = L.stageW - 2 * L.marginX - readW - gap;   // 1180
    return {
      panel: { x: L.marginX, y: L.contentTop, w: panelW, h: 600 },
      read: { x: L.marginX + panelW + gap, y: L.contentTop, w: readW },
      pad: 32, yLabW: 108,
      plotX: 156, plotW: panelW - 156 - 44,                // 980
      plotTop: 112, plotH: 372,                            // 하단 = 484
      xLabTop: 498, xLabH: 44,
      legendTop: 26,
    };
  }

  function trendModel(d) {
    var pts = d.points || [], lines = d.lines || [], i, k;
    var vmax = 0;
    for (k = 0; k < lines.length; k++) {
      var vs = lines[k].values || [];
      for (i = 0; i < vs.length; i++) {
        var v = Number(vs[i]);
        if (isFinite(v) && v > vmax) vmax = v;
      }
    }
    var ax = d.axis || {};
    var amin = ax.min != null ? Number(ax.min) : 0;
    // 상한은 언제나 데이터 최댓값 이상 — 라인 절단 불가
    var amax = ax.max != null ? Math.max(Number(ax.max), vmax) : niceCeil(vmax);
    if (!(amax > amin)) amax = amin + (vmax > amin ? vmax - amin : 1);
    var hasAt = pts.length > 1;
    for (i = 0; i < pts.length; i++) if (typeof pts[i].at !== 'number') hasAt = false;
    var xs = [];
    if (hasAt) {
      var a0 = Number(pts[0].at), a1 = Number(pts[pts.length - 1].at);
      var span = a1 - a0;
      for (i = 0; i < pts.length; i++) {
        xs.push(span > 0 ? (Number(pts[i].at) - a0) / span : i / Math.max(1, pts.length - 1));
      }
    } else {
      for (i = 0; i < pts.length; i++) xs.push(pts.length > 1 ? i / (pts.length - 1) : 0.5);
    }
    return { amin: amin, amax: amax, truncated: amin !== 0, xs: xs, proportional: hasAt };
  }

  function trendPlan(d) {
    var m = trendModel(d);
    var lines = d.lines || [];
    var lineAt = function (k) { return 2.4 + k * 0.5; };
    var lineDur = function (k) { return k === 0 ? 1.6 : 1.4; };
    var end = 0;
    for (var k = 0; k < lines.length; k++) end = Math.max(end, lineAt(k) + lineDur(k));
    var ringAt = end + 0.1;
    return {
      model: m, lineCount: lines.length, pointCount: (d.points || []).length,
      panel: { at: 0.9, dur: 0.7 },
      axis: { at: 1.3, dur: 0.6 },
      xlabels: { at: 1.7, dur: 0.5, stagger: 0.05 },
      legend: { at: 2.0, dur: 0.5 },
      lineAt: lineAt, lineDur: lineDur,
      ring: { at: ringAt, dur: 0.5 },
      headline: { at: ringAt + 0.4, dur: 0.7 },
      delta: { at: ringAt + 0.8, dur: 0.5 },
      insight: { at: ringAt + 1.2, dur: 0.6 },
      source: { at: ringAt + 1.8, dur: 0.6 },
    };
  }

  function lineStyleOf(theme, k, declared) {
    var s = declared || (k === 0 ? 'solid' : k === 1 ? 'dashed' : 'dotted');
    var color = k === 0 ? theme.color.blue : k === 1 ? theme.color.blue2 : theme.color.faint;
    var w = k === 0 ? 5 : 4;
    var dash = s === 'dashed' ? '16 10' : s === 'dotted' ? '2 10' : '';
    return { color: color, w: w, dash: dash, cap: s === 'dotted' ? 'round' : 'butt' };
  }

  function TrendScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = trendPlan(d);
    var m = p.model;
    var g = trGeoC(theme);
    var pts = d.points || [], lines = d.lines || [];
    var card = theme.component.card;
    var chip = theme.component.chip;
    var unit = d.unit || '';
    var span = m.amax - m.amin;
    function X(i) { return m.xs[i] * g.plotW; }
    function Y(v) { return g.plotH - (Number(v) - m.amin) / span * g.plotH; }
    var axisOp = seg(t, p.axis.at + 0.15, p.axis.dur, 0, 1);
    var ro = d.readout || {};
    var delta = ro.delta || {};
    var dTone = delta.polarity === 'good' ? { bg: chip.successBg, fg: chip.successFg }
      : delta.polarity === 'bad' ? { bg: chip.errorBg, fg: chip.errorFg }
      : { bg: chip.infoBg, fg: chip.infoFg };
    // 주계열 최신 점 — 강조 링의 자리
    var mainVals = (lines[0] || {}).values || [];
    var lastIdx = Math.min(pts.length, mainVals.length) - 1;
    return (
      <FrameChrome label="추세" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {/* ── 플롯 패널 ── */}
        <div style={Object.assign({
          position: 'absolute', left: g.panel.x, top: g.panel.y, width: g.panel.w, height: g.panel.h,
          background: card.bg, border: '1px solid ' + card.border,
          borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
        }, enter(theme, t, p.panel.at, p.panel.dur))}>
          {unit && (
            <div style={{
              position: 'absolute', right: g.pad, top: g.legendTop + 4,
              fontSize: theme.type.caption, color: theme.color.faint, fontWeight: 600,
              opacity: axisOp,
            }}>단위 · {unit}</div>
          )}
          {/* 계열 범례 */}
          <div style={Object.assign({
            position: 'absolute', left: g.pad, top: g.legendTop,
            display: 'flex', alignItems: 'center', gap: 30,
          }, enter(theme, t, p.legend.at, p.legend.dur, 10))}>
            {lines.map(function (ln, k) {
              var st = lineStyleOf(theme, k, ln.style);
              return (
                <div key={'lg' + k} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 40, height: st.w, borderRadius: 2, background: st.color,
                    backgroundImage: st.dash
                      ? 'repeating-linear-gradient(90deg, ' + st.color + ' 0 8px, transparent 8px 14px)'
                      : 'none',
                  }}></div>
                  <div style={{
                    fontSize: theme.type.caption, fontWeight: 700, color: theme.color.sub,
                    lineHeight: 1.2, whiteSpace: 'nowrap',
                  }}>{ln.label}</div>
                </div>
              );
            })}
          </div>
          {/* y 눈금 — 격자선 + 라벨 (하한선은 진하게) */}
          {Array.apply(null, Array(TREND_TICKS)).map(function (_, k) {
            var v = m.amin + span * k / (TREND_TICKS - 1);
            var y = g.plotTop + Y(v);
            var base = k === 0;
            return (
              <React.Fragment key={'yt' + k}>
                <div style={{
                  position: 'absolute', left: g.plotX, top: y - (base ? 1 : 0.5),
                  height: base ? 2 : 1, width: seg(t, p.axis.at + k * 0.04, p.axis.dur, 0, g.plotW),
                  background: base ? theme.color.sub : theme.color.line,
                }}></div>
                <div style={{
                  position: 'absolute', left: g.pad, top: y - 16, width: g.yLabW, textAlign: 'right',
                  fontSize: theme.type.caption, color: theme.color.faint, fontWeight: 600,
                  lineHeight: 1.3, whiteSpace: 'nowrap', opacity: axisOp,
                }}>{fmtNum(v)}</div>
              </React.Fragment>
            );
          })}
          {/* 축 절단 표식 — 하한이 0 이 아니면 기준선 위 파단 글리프 + 칩을 반드시 띄운다 */}
          {m.truncated && (
            <React.Fragment>
              {[6, 22].map(function (dx) {
                return (
                  <div key={'brk' + dx} style={{
                    position: 'absolute', left: g.plotX + dx, top: g.plotTop + g.plotH - 10,
                    width: 28, height: 4, background: theme.color.red, borderRadius: 2,
                    transform: 'rotate(-26deg)', opacity: axisOp,
                  }}></div>
                );
              })}
              <div data-c-truncated="1" style={Object.assign({
                position: 'absolute', left: g.plotX, top: g.legendTop + 42,
                background: chip.errorBg, color: chip.errorFg,
                fontSize: theme.type.caption, fontWeight: 800, lineHeight: 1,
                padding: '10px 18px', borderRadius: theme.radius.pill, whiteSpace: 'nowrap',
              }, popIn(theme, t, p.axis.at + 0.3, 0.5))}>
                축 절단 · 하한 {fmtNum(m.amin)}{unit}
              </div>
            </React.Fragment>
          )}
          {/* 시점 라벨 — 상자 폭은 시점 간격에서 역산(이웃 침범 방지), 넘치면 줄바꿈 */}
          {pts.map(function (pt, i) {
            var boxW = Math.min(160, Math.max(64, g.plotW / Math.max(1, pts.length - 1) - 6));
            return (
              <div key={'xl' + i} style={{
                position: 'absolute', left: g.plotX + X(i) - boxW / 2, top: g.xLabTop,
                width: boxW, textAlign: 'center',
                fontSize: theme.type.caption, color: theme.color.sub, fontWeight: 700,
                lineHeight: 1.2, overflowWrap: 'anywhere',
                opacity: seg(t, p.xlabels.at + i * p.xlabels.stagger, p.xlabels.dur, 0, 1),
              }}>{pt.label}</div>
            );
          })}
          {/* 라인·영역 — 좌→우 클립 스윕으로 그려진다 */}
          {lines.map(function (ln, k) {
            var st = lineStyleOf(theme, k, ln.style);
            var vs = ln.values || [];
            var cnt = Math.min(pts.length, vs.length);
            if (cnt < 2) return null;
            var dline = '', darea = '', i;
            for (i = 0; i < cnt; i++) {
              dline += (i === 0 ? 'M' : 'L') + X(i) + ' ' + Y(vs[i]);
            }
            darea = dline + 'L' + X(cnt - 1) + ' ' + g.plotH + 'L' + X(0) + ' ' + g.plotH + 'Z';
            var clipW = seg(t, p.lineAt(k), p.lineDur(k), 0, g.plotW + 8);
            return (
              <div key={'ln' + k} style={{
                position: 'absolute', left: g.plotX, top: g.plotTop,
                width: clipW, height: g.plotH, overflow: 'hidden',
              }}>
                <svg width={g.plotW} height={g.plotH}
                  viewBox={'0 0 ' + g.plotW + ' ' + g.plotH}
                  style={{ position: 'absolute', left: 0, top: 0, display: 'block' }}>
                  {ln.fill && <path d={darea} fill={st.color} fillOpacity="0.12" />}
                  <path d={dline} fill="none" stroke={st.color} strokeWidth={st.w}
                    strokeDasharray={st.dash || undefined} strokeLinecap={st.cap}
                    strokeLinejoin="round" />
                </svg>
              </div>
            );
          })}
          {/* 점 표식 + 최신 점 강조 링 — 스윕이 지나간 순서대로 켜진다 */}
          <svg width={g.plotW} height={g.plotH} viewBox={'0 0 ' + g.plotW + ' ' + g.plotH}
            data-c-plot={JSON.stringify({
              x0: g.panel.x + g.plotX, y0: g.panel.y + g.plotTop,
              w: g.plotW, h: g.plotH, min: m.amin, max: m.amax,
              proportional: m.proportional, truncated: m.truncated,
            })}
            style={{
              position: 'absolute', left: g.plotX, top: g.plotTop,
              display: 'block', overflow: 'visible',   // 최신 점 강조 링이 플롯 폭을 넘어도 잘리지 않게
            }}>
            {lines.map(function (ln, k) {
              var st = lineStyleOf(theme, k, ln.style);
              var vs = ln.values || [];
              var cnt = Math.min(pts.length, vs.length);
              return (
                <React.Fragment key={'pt' + k}>
                  {Array.apply(null, Array(cnt)).map(function (_, i) {
                    return (
                      <circle key={'p' + i}
                        data-c-point={k + '-' + i}
                        data-c-point-x={X(i).toFixed(3)}
                        data-c-point-y={Y(vs[i]).toFixed(3)}
                        data-c-point-value={String(vs[i])}
                        cx={X(i)} cy={Y(vs[i])} r={k === 0 ? 8 : 6}
                        fill={theme.color.card} stroke={st.color} strokeWidth={k === 0 ? 5 : 3}
                        opacity={seg(t, p.lineAt(k) + m.xs[i] * p.lineDur(k), 0.3, 0, 1)} />
                    );
                  })}
                </React.Fragment>
              );
            })}
            {lastIdx >= 0 && (
              <circle cx={X(lastIdx)} cy={Y(mainVals[lastIdx])}
                r={seg(t, p.ring.at, p.ring.dur, 8, 22)} fill="none"
                stroke={theme.color.blue} strokeWidth="3"
                opacity={seg(t, p.ring.at, p.ring.dur, 0, 0.55)} />
            )}
          </svg>
        </div>
        {/* ── 판독 칼럼 — 최신값 → 변화율 배지 → 한 줄 해석 ── */}
        <div style={{ position: 'absolute', left: g.read.x, top: g.read.y, width: g.read.w }}>
          <div style={Object.assign({
            fontSize: theme.type.display, fontWeight: 800, letterSpacing: '-0.02em',
            color: theme.color.blue, lineHeight: 1.15, whiteSpace: 'nowrap',
          }, enter(theme, t, p.headline.at, p.headline.dur, 24))}>{ro.value}</div>
          <div style={Object.assign({
            marginTop: 10, fontSize: theme.type.emphasis, color: theme.color.sub, fontWeight: 600,
            lineHeight: 1.3, overflowWrap: 'anywhere',
          }, enter(theme, t, p.headline.at + 0.15, p.headline.dur, 14))}>{ro.desc}</div>
          {delta.text && (
            <div style={{ marginTop: 22, display: 'flex' }}>
              <div style={Object.assign({
                background: dTone.bg, color: dTone.fg,
                fontSize: theme.type.caption, fontWeight: 800, lineHeight: 1,
                padding: '13px 22px', borderRadius: theme.radius.pill, whiteSpace: 'nowrap',
              }, popIn(theme, t, p.delta.at, p.delta.dur))}>
                {TREND_DIR_GLYPH[delta.direction] || TREND_DIR_GLYPH.flat} {delta.text}
              </div>
            </div>
          )}
          {((ro.insight && ro.insight.text) || (d.source && d.source.text)) && (
            <div style={{
              marginTop: 26, height: 1, background: theme.color.line,
              opacity: seg(t, p.delta.at + 0.3, 0.6, 0, 1),
            }}></div>
          )}
          {ro.insight && ro.insight.text && (
            <div style={Object.assign({
              marginTop: 26, background: theme.color.blueSoft,
              borderLeft: '5px solid ' + theme.color.blue,
              borderRadius: theme.radius.box, padding: '20px 22px', boxSizing: 'border-box',
              fontSize: theme.type.note, fontWeight: 700, color: theme.color.ink,
              lineHeight: 1.45, overflowWrap: 'anywhere',
            }, enter(theme, t, p.insight.at, p.insight.dur, 18))}>{ro.insight.text}</div>
          )}
          {d.source && d.source.text && (
            <div style={Object.assign({
              marginTop: 24, fontSize: theme.type.caption, fontWeight: 600,
              color: theme.color.faint, lineHeight: 1.35, overflowWrap: 'anywhere',
            }, enter(theme, t, p.source.at, p.source.dur, 12))}>출처 · {d.source.text}</div>
          )}
        </div>
      </FrameChrome>
    );
  }
  TrendScene.nat = 13;
  TrendScene.schedule = function (d) {
    var p = trendPlan(d);
    var out = FRAME_SCHED.concat([
      { id: 'panel', kind: 'enter', at: p.panel.at, dur: p.panel.dur },
      { id: 'axis', kind: 'enter', at: p.axis.at, dur: p.axis.dur + 0.2 },
      { id: 'xlabels', kind: 'enter', at: p.xlabels.at, dur: p.xlabels.dur,
        stagger: p.xlabels.stagger, count: p.pointCount, path: '/points' },
      { id: 'legend', kind: 'enter', at: p.legend.at, dur: p.legend.dur },
    ]);
    for (var k = 0; k < p.lineCount; k++) {
      out.push({ id: 'line-' + k, kind: 'enter', at: p.lineAt(k), dur: p.lineDur(k),
        path: '/lines/' + k });
    }
    out.push({ id: 'latest-ring', kind: 'enter', at: p.ring.at, dur: p.ring.dur });
    out.push({ id: 'headline', kind: 'enter', at: p.headline.at, dur: p.headline.dur + 0.15,
      path: '/readout' });
    if ((d.readout || {}).delta) {
      out.push({ id: 'delta', kind: 'enter', at: p.delta.at, dur: p.delta.dur,
        path: '/readout/delta' });
    }
    if (((d.readout || {}).insight || {}).text) {
      out.push({ id: 'insight', kind: 'enter', at: p.insight.at, dur: p.insight.dur,
        path: '/readout/insight' });
    }
    if ((d.source || {}).text) {
      out.push({ id: 'source', kind: 'enter', at: p.source.at, dur: p.source.dur, path: '/source' });
    }
    return out;
  };

  OMX.templates = Object.assign(OMX.templates || {}, {
    RatioScene: RatioScene,
    TrendScene: TrendScene,
  });
  OMX.templateIndex = Object.assign(OMX.templateIndex || {}, {
    'tpl.c-ratio': RatioScene,
    'tpl.c-trend': TrendScene,
  });
})();
