// 구조·목록 배치 씬 템플릿 2종 — tpl.c-branch(분기 흐름도: 조건 분기·병렬 절차)·tpl.c-grid(카드 그리드 4~9개).
// 커버리지 공백 1순위 ③④ — tpl.process(선형 6단계)·tpl.proof(3열 고정)가 못 담는 그릇.
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

  /* ══ tpl.c-branch — 분기 흐름도 (은유: 갈림길 — 길이 하나 그어지다 판단 앞에서 둘로 갈라진다) ══
     등장 순서 = 흐름의 서사: ① 레벨 0 노드 → ② 레벨 0→1 엣지(분기 라벨) → ③ 레벨 1 노드 → …
     → ④ 마지막 레벨 → ⑤ 풋노트. 분기 지점에서는 두 경로가 **같은 시각에** 뻗어 나간다.
     tpl.process(선형 6단계 그리드)로는 못 그린다 — 여기서는 판단(마름모)에서 길이 갈리고 다시 모인다.

     레이아웃 원칙 — 노드는 레벨(깊이)별로 열에 배치하고 같은 레벨은 세로 균등 배치한다.
     같은 부모의 자식을 인접 슬롯에 모아(부모 슬롯 순 정렬) 엣지 교차를 줄인다.
     엣지는 직교(ㄱ자) 경로이며 **세로 구간은 반드시 열 사이 거터(120px) 안**에 둔다 — 노드를
     관통할 수 없는 구조다. 레벨을 건너뛰는 엣지는 노드 띠 아래 우회 레인으로 빼서 역시 관통을 막는다. */

  var BR_MAX_LEVEL = 3;          // 레벨 0~3 (열 4개) — 스키마와 같은 상한
  var BR_COL_GAP = 120;          // 거터 — 분기 라벨 필(최대 88px)이 노드를 침범하지 않는 폭
  var BR_ROW_GAP = 28;
  var BR_NODE_MAX_H = 200;       // 레벨당 노드가 적어도 무한정 커지지 않게 하는 상한
  var BR_LINE = 3;               // 엣지 선 두께

  function brGeo(theme, levelCount, maxPerLevel) {
    var L = theme.layout;
    var W = L.stageW - 2 * L.marginX;                   // 1640
    var H = 592;
    var cols = Math.max(1, levelCount);
    var m = Math.max(1, maxPerLevel);
    var nodeW = (W - (cols - 1) * BR_COL_GAP) / cols;   // 4열 320 · 3열 466.7 · 2열 760
    // 띠 높이는 592 가 아니라 560 까지만 쓴다 — 남는 32px 이 우회 레인 자리다 (레벨당 3개 시 노드 168)
    var nodeH = Math.min(BR_NODE_MAX_H, (H - 32 - (m - 1) * BR_ROW_GAP) / m);
    var bandH = m * nodeH + (m - 1) * BR_ROW_GAP;
    var bandTop = L.contentTop + (H - bandH) / 2;
    return {
      x: L.marginX, y: L.contentTop, w: W, h: H,
      cols: cols, m: m, nodeW: nodeW, nodeH: nodeH,
      bandTop: bandTop, bandBottom: bandTop + bandH,
      // 레벨 건너뛰기 우회 레인 — 노드 띠 아래, 풋노트(952) 위. 띠가 내용 영역을 꽉 채워도 겹치지 않는다
      laneY: Math.min(bandTop + bandH + 18, L.contentTop + H + 14),
      pad: 14,
    };
  }
  // 레벨별 노드 묶음 — 같은 부모의 자식을 인접 배치(부모 슬롯 순 정렬)해 엣지 교차를 줄인다.
  // 정렬은 결정적이다(부모 슬롯 → 엣지 선언 순 → 원본 순).
  function branchLevels(d) {
    var nodes = d.nodes || [], edges = d.edges || [];
    var levels = [], maxLevel = 0, i;
    for (i = 0; i <= BR_MAX_LEVEL; i++) levels.push([]);
    nodes.forEach(function (n) {
      var l = Number(n.level);
      if (!(l === l)) l = 0;                            // NaN 방어 (순수 비교)
      l = Math.max(0, Math.min(BR_MAX_LEVEL, Math.round(l)));
      levels[l].push(n);
      if (l > maxLevel) maxLevel = l;
    });
    for (var lv = 1; lv <= maxLevel; lv++) {
      var posOf = {};
      levels[lv - 1].forEach(function (n, k) { posOf[n.id] = k; });
      var arr = levels[lv].map(function (n, k) {
        var key = 1e6, sub = 1e6;
        for (var e = 0; e < edges.length; e++) {
          if (edges[e].to !== n.id) continue;
          var p = posOf[edges[e].from];
          if (p == null || p >= key) continue;
          key = p; sub = e;
        }
        return { n: n, key: key, sub: sub, i: k };
      });
      arr.sort(function (a, b) { return (a.key - b.key) || (a.sub - b.sub) || (a.i - b.i); });
      levels[lv] = arr.map(function (x) { return x.n; });
    }
    return { levels: levels.slice(0, maxLevel + 1), maxLevel: maxLevel };
  }
  // 노드 id → 사각 상자 (레벨은 열, 같은 레벨은 세로 균등 + 중앙 정렬)
  function branchBoxes(d, theme) {
    var lay = branchLevels(d);
    var m = 1;
    lay.levels.forEach(function (arr) { if (arr.length > m) m = arr.length; });
    var g = brGeo(theme, lay.maxLevel + 1, m);
    var box = {};
    lay.levels.forEach(function (arr, l) {
      var off = (g.m - arr.length) / 2;
      arr.forEach(function (n, i) {
        box[n.id] = {
          id: n.id, node: n, level: l,
          x: g.x + l * (g.nodeW + BR_COL_GAP),
          y: g.bandTop + (off + i) * (g.nodeH + BR_ROW_GAP),
          w: g.nodeW, h: g.nodeH,
        };
      });
    });
    return { geo: g, box: box, levels: lay.levels, maxLevel: lay.maxLevel };
  }
  // 엣지 → 직교 경로 세그먼트 + 라벨 앵커. 세로 구간은 언제나 거터 안(노드 밖)이다.
  function branchRoutes(d, g, box) {
    var edges = d.edges || [];
    var outCnt = {}, inCnt = {}, outIdx = {}, inIdx = {}, gutterN = {};
    edges.forEach(function (e) {
      if (!box[e.from] || !box[e.to]) return;
      outCnt[e.from] = (outCnt[e.from] || 0) + 1;
      inCnt[e.to] = (inCnt[e.to] || 0) + 1;
    });
    return edges.map(function (e, i) {
      var A = box[e.from], B = box[e.to];
      if (!A || !B || B.level <= A.level) return null;  // 전진 엣지만 그린다 (스키마 계약)
      var oi = (outIdx[e.from] = (outIdx[e.from] || 0) + 1);
      var ii = (inIdx[e.to] = (inIdx[e.to] || 0) + 1);
      // 분기: 같은 노드의 출구를 오른쪽 변에 세로로 벌린다 — 두 경로가 동시에 뻗어도 겹치지 않는다
      var sy = A.y + A.h * oi / (outCnt[e.from] + 1);
      var ey = B.y + B.h * ii / (inCnt[e.to] + 1);
      var gk = 'L' + A.level;
      var gn = (gutterN[gk] = (gutterN[gk] || 0) + 1);
      var off = ((gn - 1) % 3 - 1) * 8;                 // 같은 거터의 세로선 결정적 분리
      var gx1 = A.x + A.w + BR_COL_GAP / 2 + off;
      var gx2 = B.x - BR_COL_GAP / 2 + off;
      var segs = [];
      function h(x1, x2, y) {
        segs.push({ dir: 'h', x: Math.min(x1, x2), y: y - BR_LINE / 2, w: Math.abs(x2 - x1), h: BR_LINE, rev: x2 < x1 });
      }
      function v(x, y1, y2) {
        segs.push({ dir: 'v', x: x - BR_LINE / 2, y: Math.min(y1, y2), w: BR_LINE, h: Math.abs(y2 - y1), down: y2 >= y1 });
      }
      var labelY;
      if (B.level - A.level === 1) {
        h(A.x + A.w, gx1, sy); v(gx1, sy, ey); h(gx1, B.x, ey);
        labelY = (sy + ey) / 2;
      } else {                                          // 레벨 건너뛰기 — 노드 띠 아래 우회 레인
        h(A.x + A.w, gx1, sy); v(gx1, sy, g.laneY); h(gx1, gx2, g.laneY);
        v(gx2, g.laneY, ey); h(gx2, B.x, ey);
        labelY = (sy + g.laneY) / 2;
      }
      return {
        i: i, from: e.from, to: e.to, label: e.label, segs: segs,
        labelX: gx1, labelY: labelY, arrowX: B.x, arrowY: ey, level: A.level,
      };
    }).filter(function (r) { return !!r; });
  }
  function brPlan(d, maxLevel) {
    var levelAt = function (l) { return 1.05 + l * 1.5; };
    var last = levelAt(maxLevel) + 0.6;
    return {
      levelAt: levelAt, nodeDur: 0.55, nodeStagger: 0.18,
      edgeDelay: 0.8, edgeDur: 0.2, edgeStep: 0.16, labelDelay: 1.3,
      note: { at: last + 0.9, dur: 0.7 },
    };
  }
  function brNodeTone(theme, n) {
    var c = theme.component.chip;
    if (n.kind === 'start') return { bg: theme.component.decision.bg, fg: theme.component.decision.fg };
    if (n.kind === 'end') {
      if (n.tone === 'positive') return { bg: c.successBg, fg: c.successFg };
      if (n.tone === 'caution') return { bg: c.errorBg, fg: c.errorFg };
      return { bg: theme.color.typingBg, fg: theme.color.sub };
    }
    return { bg: theme.component.card.bg, fg: theme.color.ink };
  }
  function BranchScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var L = branchBoxes(d, theme);
    var g = L.geo;
    var routes = branchRoutes(d, g, L.box);
    var p = brPlan(d, L.maxLevel);
    var card = theme.component.card;
    var lineColor = theme.color.blueBorder;
    return (
      <FrameChrome label="분기" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {/* ── 엣지 — 레벨이 열리기 직전에 그어져 흐름을 잇는다 ── */}
        {routes.map(function (r) {
          var at = p.levelAt(r.level) + p.edgeDelay;
          return (
            <React.Fragment key={'e' + r.i}>
              {r.segs.map(function (s, k) {
                var v = seg(t, at + k * p.edgeStep, p.edgeDur, 0, 1, Easing.linear || Easing.easeOutCubic);
                return (
                  <div key={'s' + k} style={{
                    position: 'absolute', left: s.x, top: s.y, width: s.w, height: s.h,
                    background: lineColor, borderRadius: 2,
                    transform: s.dir === 'h' ? 'scaleX(' + v + ')' : 'scaleY(' + v + ')',
                    transformOrigin: s.dir === 'h'
                      ? (s.rev ? '100% 50%' : '0% 50%')
                      : (s.down ? '50% 0%' : '50% 100%'),
                  }}></div>
                );
              })}
              {/* 화살촉 — 도착 노드 왼쪽 변 (텍스트 아님: CSS 삼각형) */}
              <div style={{
                position: 'absolute', left: r.arrowX - 14, top: r.arrowY - 9,
                width: 0, height: 0,
                borderTop: '9px solid transparent', borderBottom: '9px solid transparent',
                borderLeft: '14px solid ' + lineColor,
                opacity: seg(t, at + (r.segs.length - 1) * p.edgeStep + 0.1, 0.3, 0, 1),
              }}></div>
              {/* 분기 라벨 — 거터 안(±44px)에만 놓여 노드를 침범할 수 없다 */}
              {r.label && (
                <div style={Object.assign({
                  position: 'absolute', left: r.labelX - 44, top: r.labelY - 17,
                  width: 88, height: 34, boxSizing: 'border-box',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: theme.component.chip.accentBg, color: theme.component.chip.accentFg,
                  border: '1px solid ' + theme.color.blueBorder,
                  borderRadius: theme.radius.pill,
                  fontSize: theme.type.caption, fontWeight: 800, lineHeight: 1.2, whiteSpace: 'nowrap',
                }, popIn(theme, t, p.levelAt(r.level) + p.labelDelay))}>{r.label}</div>
              )}
            </React.Fragment>
          );
        })}
        {/* ── 노드 — 레벨(열)별 순차 등장, 같은 레벨은 위→아래 스태거 ── */}
        {L.levels.map(function (arr, l) {
          return arr.map(function (n, i) {
            var b = L.box[n.id];
            var at = p.levelAt(l) + i * p.nodeStagger;
            var tone = brNodeTone(theme, n);
            var lineH = Math.round(theme.type.caption * 1.25);       // 30
            var labelLines = n.note ? 2 : 3;
            var labelH = lineH * labelLines;
            var noteH = n.note ? lineH * 2 : 0;
            var blockH = labelH + (n.note ? 10 + noteH : 0);
            var blockTop = b.y + (b.h - blockH) / 2;
            if (n.kind === 'decision') {
              // 판단 — 마름모. 텍스트는 내접 사각(0.54w × 0.44h)에 가둔다 (0.54+0.44 ≤ 1)
              return (
                <React.Fragment key={'n' + l + '-' + i}>
                  <div style={Object.assign({
                    position: 'absolute', left: b.x, top: b.y, width: b.w, height: b.h,
                    background: theme.color.blueBorder,
                    clipPath: 'polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)',
                  }, popIn(theme, t, at, 0.5))}>
                    <div style={{
                      position: 'absolute', left: 3, top: 3, right: 3, bottom: 3,
                      background: theme.color.blueSoft,
                      clipPath: 'polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)',
                    }}></div>
                  </div>
                  <div style={Object.assign({
                    position: 'absolute', left: b.x + b.w * 0.23, top: b.y + b.h * 0.28,
                    width: b.w * 0.54, height: b.h * 0.44,
                    display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center',
                    fontSize: theme.type.caption, fontWeight: 800, color: theme.color.blue,
                    lineHeight: 1.25, overflowWrap: 'anywhere',
                  }, enter(theme, t, at + 0.12, 0.5, 8))}>{n.label}</div>
                </React.Fragment>
              );
            }
            var pill = n.kind === 'start' || n.kind === 'end';
            // 라벨·보조는 상자 **안에** 둔다 — 대비 게이트가 배경을 상자 색으로 읽어야 한다
            // (형제로 두면 흰 글자의 배경이 스테이지 배경으로 계산돼 대비 1.07:1 로 떨어진다)
            return (
              <div key={'n' + l + '-' + i} style={Object.assign({
                position: 'absolute', left: b.x, top: b.y, width: b.w, height: b.h,
                boxSizing: 'border-box', background: tone.bg,
                border: pill ? 'none' : '1px solid ' + card.border,
                borderRadius: pill ? theme.radius.pill : theme.radius.card,
                boxShadow: pill ? 'none' : card.shadowSoft,
              }, pill ? popIn(theme, t, at, 0.5) : enter(theme, t, at, p.nodeDur, 18))}>
                <div style={Object.assign({
                  position: 'absolute', left: g.pad, right: g.pad, top: blockTop - b.y,
                  height: labelH,
                  display: 'flex', alignItems: 'center', justifyContent: 'center', textAlign: 'center',
                  fontSize: theme.type.caption, fontWeight: pill ? 800 : 700, color: tone.fg,
                  lineHeight: 1.25, overflowWrap: 'anywhere',
                }, enter(theme, t, at + 0.12, 0.5, 8))}>{n.label}</div>
                {n.note && (
                  <div style={Object.assign({
                    position: 'absolute', left: g.pad, right: g.pad,
                    top: blockTop - b.y + labelH + 10, height: noteH,
                    display: 'flex', alignItems: 'flex-start', justifyContent: 'center', textAlign: 'center',
                    fontSize: theme.type.caption, fontWeight: 500,
                    color: pill ? tone.fg : theme.color.sub,
                    lineHeight: 1.25, overflowWrap: 'anywhere',
                  }, enter(theme, t, at + 0.22, 0.5, 8))}>{n.note}</div>
                )}
              </div>
            );
          });
        })}
        <LayoutNote t={t} theme={theme} data={d.note} top={theme.component.processNote.top} at={p.note.at} />
      </FrameChrome>
    );
  }
  BranchScene.nat = 14;
  BranchScene.schedule = function (d) {
    var lay = branchLevels(d);
    var p = brPlan(d, lay.maxLevel);
    var out = FRAME_SCHED.slice();
    var idOrder = {};
    lay.levels.forEach(function (arr, l) {
      if (arr.length) {
        out.push({
          id: 'level-' + l, kind: 'enter', at: p.levelAt(l), dur: p.nodeDur,
          stagger: p.nodeStagger, count: arr.length, path: '/nodes',
        });
      }
      arr.forEach(function (n) { idOrder[n.id] = l; });
    });
    (d.edges || []).forEach(function (e, i) {
      var l = idOrder[e.from];
      if (l == null) return;
      out.push({ id: 'edge-' + i, kind: 'enter', at: p.levelAt(l) + p.edgeDelay, dur: 0.8, path: '/edges/' + i });
      if (e.label) {
        out.push({ id: 'edge-label-' + i, kind: 'enter', at: p.levelAt(l) + p.labelDelay, dur: 0.45, path: '/edges/' + i + '/label' });
      }
    });
    if (d.note) out.push({ id: 'note', kind: 'enter', at: p.note.at, dur: p.note.dur, path: '/note' });
    return out;
  };

  /* ══ tpl.c-grid — 카드 그리드 (은유: 진열대 — 항목이 읽는 순서(좌상→우하)대로 놓인다) ══
     등장 순서 = 읽는 순서: ① 카드 상자 → ② 번호/아이콘 칩 → ③ 제목 → ④ 설명 → ⑤ 상태 배지
     (카드마다 반복, 좌상→우하) → ⑥ 풋노트. tpl.proof(3열 고정 2~3장)의 상한을 넘는 6~9개 목록용.

     밀도 원칙 — **배치는 데이터가 아니라 렌더가 정한다.** 개수로 열·행을 결정하고(4개=2×2,
     5~6개=3×2, 7~9개=3×3) 카드 크기·패딩·제목 크기를 거기서 역산한다. 스키마에는 cols/rows/
     fontSize 같은 필드가 없다 — 9개를 4열로 우겨넣어 글자를 줄이는 경로를 원천 차단한다.
     3행(밀집) 모드에서도 제목 26px·설명 24px 로 최소 폰트 24px 를 지킨다. */

  var GD_GAP = 24;
  function gridShape(n) {
    var count = Math.max(1, n);
    var cols = count <= 4 ? 2 : 3;
    return { cols: cols, rows: Math.ceil(count / cols), dense: Math.ceil(count / cols) >= 3 };
  }
  function gdGeo(theme, n) {
    var L = theme.layout;
    var W = L.stageW - 2 * L.marginX;                   // 1640
    var H = 592;
    var s = gridShape(n);
    var cardW = (W - (s.cols - 1) * GD_GAP) / s.cols;   // 3열 530.67 · 2열 808
    var cardH = (H - (s.rows - 1) * GD_GAP) / s.rows;   // 3행 181.33 · 2행 284
    var pad = s.dense ? 16 : 26;
    var chipH = s.dense ? 40 : 52;
    var badgeH = s.dense ? 36 : 40;
    var titleSize = s.dense ? theme.type.body : theme.type.cardTitle;   // 26 / 33
    var titleH = Math.round(titleSize * 1.25 * (s.dense ? 1 : 2));      // 33 / 83
    var titleTop = pad + chipH + (s.dense ? 8 : 12);
    var descLine = Math.round(theme.type.caption * 1.25);               // 30
    var descTop = titleTop + titleH + (s.dense ? 6 : 10);
    return {
      x: L.marginX, y: L.contentTop, w: W, h: H,
      cols: s.cols, rows: s.rows, dense: s.dense,
      cardW: cardW, cardH: cardH, pad: pad, innerW: cardW - 2 * pad,
      chipH: chipH, badgeH: badgeH,
      titleSize: titleSize, titleH: titleH, titleTop: titleTop,
      descTop: descTop, descH: descLine * 2,            // 설명은 최대 2줄 (밀집 여유 62.3 ≥ 60)
    };
  }
  function gdPlan(d) {
    var n = (d.cards || []).length;
    var at = function (i) { return 1.0 + i * 0.42; };
    var last = at(Math.max(0, n - 1)) + 0.5 + 0.55;
    return {
      count: n, at: at, dur: 0.6,
      chipDelay: 0.12, titleDelay: 0.22, descDelay: 0.36, badgeDelay: 0.5,
      note: { at: last + 0.8, dur: 0.7 },
    };
  }
  function gdBadgeTone(theme, tone) {
    var c = theme.component.chip;
    if (tone === 'positive') return { bg: c.successBg, fg: c.successFg };
    if (tone === 'caution') return { bg: c.errorBg, fg: c.errorFg };
    return { bg: c.infoBg, fg: c.infoFg };
  }
  function GridScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var cards = d.cards || [];
    var g = gdGeo(theme, cards.length);
    var p = gdPlan(d);
    var card = theme.component.card;
    var chip = theme.component.chip;
    return (
      <FrameChrome label="목록" t={t} theme={theme} kicker={d.kicker} title={d.title} frame={d.frame}>
        {cards.map(function (c, i) {
          var col = i % g.cols, row = Math.floor(i / g.cols);
          var at = p.at(i);
          var bt = gdBadgeTone(theme, c.tone);
          var left = g.x + col * (g.cardW + GD_GAP);
          var top = g.y + row * (g.cardH + GD_GAP);
          return (
            <div key={'c' + i} style={Object.assign({
              position: 'absolute', left: left, top: top,
              width: g.cardW, height: g.cardH, boxSizing: 'border-box',
              background: card.bg, border: '1px solid ' + card.border,
              borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
            }, enter(theme, t, at, p.dur, 20))}>
              {/* 번호 또는 아이콘 칩 — 읽는 순서를 눈에 박는다 */}
              <div style={Object.assign({
                position: 'absolute', left: g.pad, top: g.pad, height: g.chipH,
                minWidth: g.chipH, boxSizing: 'border-box', padding: '0 14px',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: chip.accentBg, color: chip.accentFg,
                borderRadius: theme.radius.pill,
                fontSize: theme.type.caption, fontWeight: 800, lineHeight: 1.2, whiteSpace: 'nowrap',
              }, popIn(theme, t, at + p.chipDelay))}>{c.icon || String(i + 1)}</div>
              {/* 상태/수치 배지 — 칩 행 오른쪽 끝 */}
              {c.badge && (
                <div style={Object.assign({
                  position: 'absolute', right: g.pad, top: g.pad + (g.chipH - g.badgeH) / 2,
                  height: g.badgeH, boxSizing: 'border-box', padding: '0 16px',
                  display: 'flex', alignItems: 'center',
                  background: bt.bg, color: bt.fg, borderRadius: theme.radius.pill,
                  fontSize: theme.type.caption, fontWeight: 800, lineHeight: 1.2, whiteSpace: 'nowrap',
                }, popIn(theme, t, at + p.badgeDelay))}>{c.badge}</div>
              )}
              {/* 제목 — 밀집(3행)은 1줄 26px, 여유(2행)는 2줄 33px */}
              <div style={Object.assign({
                position: 'absolute', left: g.pad, top: g.titleTop,
                width: g.innerW, height: g.titleH,
                display: 'flex', alignItems: 'center',
                fontSize: g.titleSize, fontWeight: 800, color: theme.color.ink,
                lineHeight: 1.25, letterSpacing: '-0.01em',
                whiteSpace: g.dense ? 'nowrap' : 'normal', overflowWrap: 'anywhere',
              }, enter(theme, t, at + p.titleDelay, 0.5, 12))}>{c.label}</div>
              {/* 설명 — 항상 24px 2줄 (개수가 늘어도 글자는 줄지 않는다) */}
              {c.desc && (
                <div style={Object.assign({
                  position: 'absolute', left: g.pad, top: g.descTop,
                  width: g.innerW, height: g.descH,
                  fontSize: theme.type.caption, fontWeight: 500, color: theme.color.sub,
                  lineHeight: 1.25, overflowWrap: 'anywhere',
                }, enter(theme, t, at + p.descDelay, 0.5, 10))}>{c.desc}</div>
              )}
            </div>
          );
        })}
        {d.omitted != null && (
          <div style={{
            position: 'absolute', left: g.x, top: g.y + g.h + 10, width: g.w,
            textAlign: 'right', fontSize: theme.type.caption, fontWeight: 600,
            color: theme.color.faint,
            opacity: seg(t, p.note.at - 0.4, 0.5, 0, 1),
          }}>…외 {d.omitted}건</div>
        )}
        <LayoutNote t={t} theme={theme} data={d.note} top={theme.component.processNote.top} at={p.note.at} />
      </FrameChrome>
    );
  }
  GridScene.nat = 13;
  GridScene.schedule = function (d) {
    var p = gdPlan(d);
    var cards = d.cards || [];
    var out = FRAME_SCHED.slice();
    for (var i = 0; i < p.count; i++) {
      var at = p.at(i);
      out.push({ id: 'card-' + i, kind: 'enter', at: at, dur: p.dur, path: '/cards/' + i });
      out.push({ id: 'chip-' + i, kind: 'enter', at: at + p.chipDelay, dur: 0.45, path: '/cards/' + i + '/icon' });
      out.push({ id: 'label-' + i, kind: 'enter', at: at + p.titleDelay, dur: 0.5, path: '/cards/' + i + '/label' });
      if (cards[i] && cards[i].desc) {
        out.push({ id: 'desc-' + i, kind: 'enter', at: at + p.descDelay, dur: 0.5, path: '/cards/' + i + '/desc' });
      }
      if (cards[i] && cards[i].badge) {
        out.push({ id: 'badge-' + i, kind: 'enter', at: at + p.badgeDelay, dur: 0.45, path: '/cards/' + i + '/badge' });
      }
    }
    if (d.omitted != null) out.push({ id: 'omitted', kind: 'enter', at: p.note.at - 0.4, dur: 0.5, path: '/omitted' });
    if (d.note) out.push({ id: 'note', kind: 'enter', at: p.note.at, dur: p.note.dur, path: '/note' });
    return out;
  };

  OMX.templates = Object.assign(OMX.templates || {}, {
    BranchScene: BranchScene,
    GridScene: GridScene,
  });
  OMX.templateIndex = Object.assign(OMX.templateIndex || {}, {
    'tpl.c-branch': BranchScene,
    'tpl.c-grid': GridScene,
  });
  // 레이아웃 정확성 규칙의 시험 좌석 — 순수 함수라 브라우저에서 단독 검증한다
  OMX.layoutsD = Object.assign(OMX.layoutsD || {}, {
    gridShape: gridShape,
    gdGeo: gdGeo,
    branchLevels: branchLevels,
    branchBoxes: branchBoxes,
    branchRoutes: branchRoutes,
  });
})();
