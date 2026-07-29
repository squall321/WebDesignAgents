// 문서형 슬라이드 템플릿 5종 — tpl.doc-cover(표지)·doc-toc(목차)·doc-section(섹션 구분)·doc-body(본체 2단)·doc-summary(요약). 영상 씬이 "한 화면 한 메시지 + 모션이 논리"라면 이쪽은 **읽는 자료**다: 정보 밀도 2~3배, 스캔 가능한 위계, 정지 화면이 최종형.
// 계약: 엔진 props(localTime 등) + data + theme, 정적 .schedule(data)/.nat, frame-match(첫/끝 프레임 정지), 모든 표현은 t 의 순수 함수. 다만 안무는 최소 — 진입 0.15~1.3초에 전부 정착하고 그 뒤는 완전 정지다.
// 좌표를 px 로 박지 않는다 — 한 벌의 코드가 deck-doc-16x9(1920×1080)·deck-4x3(1440×1080)·print-a4(1240×1754) 세 무대를 탄다. 배치는 flex 흐름 + 비율, 상수는 여백·간격·타입 스케일뿐이다.
(function () {
  'use strict';
  var OMX = (window.OMX = window.OMX || {});
  var Easing = window.Easing;
  var animate = window.animate;

  /* ══ 문서형 무대 스펙 — 3무대 공통 상수 ═══════════════════════════════
     padX 84 : 최소 무대 폭 1240 기준 6.8%(A4 2cm 여백 관행), 1920 기준 4.4%.
     type    : 24px 하한(게이트 4) 위에서 세운 **읽기용** 스케일. 영상 스케일보다 한 단계씩 낮다
               — 영상 sectionTitle 56 → 문서 title 38, 영상 item 31 → 문서 body 26, 영상 hero 112 → 표지 62.
     밀도의 근거: 한글 1자 ≈ 1em 이므로 한 줄 수용 글자수 ≈ 열폭 / fontSize.
               본체 좌열은 4:3(가장 좁고 낮은 무대)에서 689px → 26px 기준 26자/줄 — 스키마 maxLength 역산의 바닥. */
  var D = {
    stages: {
      'deck-doc-16x9': { w: 1920, h: 1080 },
      'deck-4x3': { w: 1440, h: 1080 },
      'print-a4': { w: 1240, h: 1754 },
    },
    padX: 84,
    padTop: 48,
    padBottom: 40,
    gutter: 44,
    type: {
      micro: 24,     // 푸터·페이지 번호·출처·표 셀 (게이트 4 하한과 동일)
      meta: 25,      // 킥커·메타 라벨·차트 축 라벨
      body: 26,      // 불릿 본문·목차 항목·소결론
      lead: 28,      // 리드문·섹션 요지
      sub: 30,       // 근거 카드 제목·목차 그룹명
      title: 38,     // 슬라이드 제목
      name: 46,      // 섹션명
      display: 62,   // 표지 제목
      numeral: 108,  // 섹션 번호
    },
  };

  // ── 마이크로 헬퍼 — 엔진 원자 animate/Easing 로만 재구성 ─────────────
  function easeOf(name) { return (name && Easing[name]) || Easing.easeOutCubic; }
  function seg(t, at, dur, from, to, ease) {
    return animate({ from: from, to: to, start: at, end: at + dur, ease: ease || Easing.easeOutCubic })(t);
  }
  /* 문서형 진입 — 페이드 + 8px 상승 0.5초. 영상의 rise(26px·0.7s)보다 짧고 얕다:
     읽는 자료는 모션이 논리가 아니라 잡음이므로 "있었는지 모르게" 정착시킨다. */
  var IN_DUR = 0.5;
  function docIn(theme, t, at, dy) {
    var e = easeOf(theme.motion.riseSm.ease);
    var y = dy == null ? 8 : dy;
    return { opacity: seg(t, at, IN_DUR, 0, 1, e), transform: 'translateY(' + seg(t, at, IN_DUR, y, 0, e) + 'px)' };
  }
  // 문장 텍스트 공통 — 한글 단어를 지키되 초과 시에만 분절
  var TEXT_WRAP = { wordBreak: 'keep-all', overflowWrap: 'break-word' };

  // ── 스케줄 유틸 (가로·세로판과 동일 계약, 문서 파일 자립용) ───────────
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
  function listAt(base, i, stagger) { return base + i * (stagger == null ? 0.07 : stagger); }

  /* ══ doc-page — 문서형 공통 크롬 ══════════════════════════════════════
     영상 크롬(대형 킥커·중앙 타이틀·도트 텍스처)과 정반대다. 문서는 훑어보는 것이므로
     상단은 위치 표시(섹션 라벨 + 페이지), 하단은 출처 표시만 남기고 나머지 높이를 전부 본문에 준다.
     장식 배경 없음 — 인쇄(print-a4)에서 잉크만 먹는다. */
  function DocPage(props) {
    var t = props.t, theme = props.theme;
    var fr = theme.component.frame;
    var page = props.page || null;
    var footer = props.footer || null;
    var showHead = !props.plain && (props.kicker || page);
    var showFoot = !!footer;   // plain 은 머리말만 지운다 — 표지·간지도 꼬리말은 남는 것이 문서 관행
    return (
      <div data-screen-label={(props.label || '') + ' @' + Math.floor(t) + 's'}
        data-doc-page={props.label || ''}
        style={{
          position: 'absolute', inset: 0, background: fr.bg, color: fr.ink,
          fontFamily: theme.font.base, boxSizing: 'border-box', overflow: 'hidden',
          padding: D.padTop + 'px ' + D.padX + 'px ' + D.padBottom + 'px',
          display: 'flex', flexDirection: 'column',
        }}>
        {showHead && (
          <div style={Object.assign({ flex: '0 0 auto' }, docIn(theme, t, 0.15))}>
            <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 24 }}>
              <div style={{
                fontSize: D.type.meta, fontWeight: 700, letterSpacing: '0.12em', color: fr.kicker,
              }}>{props.kicker || ''}</div>
              {page && (
                <div style={{ fontSize: D.type.micro, color: fr.footerInk, whiteSpace: 'nowrap' }}>
                  {page.no}{page.total ? ' / ' + page.total : ''}
                </div>
              )}
            </div>
            <div style={{ marginTop: 12, height: 3, background: theme.color.blue, width: 84 }}></div>
            <div style={{ marginTop: -1.5, height: 1, background: fr.line }}></div>
          </div>
        )}
        <div data-doc-fit="main" style={{
          flex: '1 1 auto', minHeight: 0, display: 'flex', flexDirection: 'column',
          paddingTop: showHead ? 26 : 0,
        }}>{props.children}</div>
        {showFoot && (
          <div style={Object.assign({
            flex: '0 0 auto', marginTop: 18, paddingTop: 14, borderTop: '1px solid ' + fr.line,
            display: 'flex', justifyContent: 'space-between', gap: 24,
            fontSize: D.type.micro, color: fr.footerInk,
          }, docIn(theme, t, 0.75))}>
            <span style={TEXT_WRAP}>{footer.left || ''}</span>
            <span style={{ whiteSpace: 'nowrap' }}>{footer.right || ''}</span>
          </div>
        )}
      </div>
    );
  }

  // 공통 소제목 룰 — 제목 아래 짧은 청색 룰 (스캔 앵커)
  function DocRule(props) {
    return <div style={{
      width: props.w || 84, height: 4, borderRadius: 2,
      background: props.color || props.theme.color.blue, margin: props.margin || '18px 0',
    }}></div>;
  }

  /* ══ tpl.doc-cover — 표지 ═════════════════════════════════════════════
     상단 워드마크 + 문서 종류 배지 / 중앙 제목·부제 / 하단 메타 2열(작성일·출처 보고서·작성 조직).
     세 무대 모두 세로 space-between 이라 A4 세로에서도 무너지지 않는다. */
  function coverPlan(d) {
    var n = (d.meta || []).length;
    return {
      head: { at: 0.15, dur: IN_DUR },
      rule: { at: 0.4, dur: 0.6 },
      title: { at: 0.5, dur: IN_DUR },
      subtitle: { at: 0.7, dur: IN_DUR },
      meta: { at: 0.95, dur: IN_DUR, stagger: 0.08, count: n },
      footer: { at: 0.95 + n * 0.08 + 0.2, dur: IN_DUR },
    };
  }
  function DocCoverScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = coverPlan(d);
    var fr = theme.component.frame;
    var chip = theme.component.chip;
    var meta = d.meta || [];
    return (
      <DocPage label="표지" t={t} theme={theme} plain>
        <div style={Object.assign({
          flex: '0 0 auto', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 24,
        }, docIn(theme, t, p.head.at))}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{
              width: 40, height: 40, borderRadius: theme.radius.tag, background: theme.color.blue,
            }}></div>
            <div style={{
              fontSize: D.type.sub, fontWeight: 800, letterSpacing: '-0.01em', color: theme.color.blue,
            }}>{d.logo || ''}</div>
          </div>
          {d.badge && (
            <div style={{
              background: chip.accentBg, color: chip.accentFg, borderRadius: theme.radius.pill,
              padding: '10px 26px', fontSize: D.type.meta, fontWeight: 700, letterSpacing: '0.04em',
              whiteSpace: 'nowrap',
            }}>{d.badge}</div>
          )}
        </div>

        <div style={{
          flex: '1 1 auto', minHeight: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center',
        }}>
          <div style={{
            width: seg(t, p.rule.at, p.rule.dur, 0, 132), height: 8, borderRadius: 4,
            background: theme.color.blue, marginBottom: 34,
          }}></div>
          <div style={Object.assign({
            fontSize: D.type.display, fontWeight: 800, letterSpacing: '-0.035em', lineHeight: 1.24,
          }, TEXT_WRAP, docIn(theme, t, p.title.at, 12))}>{d.title}</div>
          {d.subtitle && (
            <div style={Object.assign({
              marginTop: 22, fontSize: D.type.lead, color: theme.color.sub, lineHeight: 1.45,
            }, TEXT_WRAP, docIn(theme, t, p.subtitle.at))}>{d.subtitle}</div>
          )}
        </div>

        <div style={{ flex: '0 0 auto' }}>
          <div style={{ height: 1, background: fr.line, marginBottom: 22 }}></div>
          <div style={{ display: 'flex', flexWrap: 'wrap', rowGap: 16, columnGap: D.gutter }}>
            {meta.map(function (m, i) {
              return (
                <div key={i} style={Object.assign({
                  flex: '1 1 40%', minWidth: 0, display: 'flex', alignItems: 'baseline', gap: 14,
                }, docIn(theme, t, listAt(p.meta.at, i, p.meta.stagger)))}>
                  <div style={{
                    flex: '0 0 auto', fontSize: D.type.micro, fontWeight: 700, letterSpacing: '0.06em',
                    color: theme.color.faint, minWidth: 116,
                  }}>{m.label}</div>
                  <div style={Object.assign({
                    flex: '1 1 auto', minWidth: 0, fontSize: D.type.body, fontWeight: 600, lineHeight: 1.35,
                  }, TEXT_WRAP)}>{m.value}</div>
                </div>
              );
            })}
          </div>
          {d.footer && (
            <div style={Object.assign({
              marginTop: 24, fontSize: D.type.micro, color: theme.color.faint,
            }, TEXT_WRAP, docIn(theme, t, p.footer.at))}>{d.footer}</div>
          )}
        </div>
      </DocPage>
    );
  }
  DocCoverScene.nat = 6;
  DocCoverScene.schedule = function (d) {
    var p = coverPlan(d);
    return [
      { id: 'head', kind: 'enter', at: p.head.at, dur: p.head.dur, path: '/logo' },
      { id: 'rule', kind: 'enter', at: p.rule.at, dur: p.rule.dur },
      { id: 'title', kind: 'enter', at: p.title.at, dur: p.title.dur, path: '/title' },
      { id: 'subtitle', kind: 'enter', at: p.subtitle.at, dur: p.subtitle.dur, path: '/subtitle' },
      { id: 'meta', kind: 'enter', at: p.meta.at, dur: p.meta.dur, stagger: p.meta.stagger, count: p.meta.count, path: '/meta' },
      { id: 'footer', kind: 'enter', at: p.footer.at, dur: p.footer.dur, path: '/footer' },
    ];
  };

  /* ══ tpl.doc-toc — 목차 ═══════════════════════════════════════════════
     항목 4~10개 + 페이지 번호. group 이 바뀌는 지점에 그룹 머리글이 들어간다(섹션 그룹핑).
     7개 이상이면 2열로 갈라 넣는다 — 한 열에 10줄을 세우면 4:3(높이 1080)에서 무너지고,
     문서 목차는 좌→우 2열 읽기가 관행이다. */
  function tocSplit(items) {
    if (items.length < 7) return [items, []];
    var half = Math.ceil(items.length / 2);
    return [items.slice(0, half), items.slice(half)];
  }
  function tocPlan(d) {
    var n = (d.items || []).length;
    return {
      title: { at: 0.25, dur: IN_DUR },
      items: { at: 0.5, dur: IN_DUR, stagger: 0.06, count: n },
      note: { at: 0.5 + n * 0.06 + 0.25, dur: IN_DUR },
    };
  }
  function TocColumn(props) {
    var items = props.items, theme = props.theme, t = props.t, p = props.plan, offset = props.offset;
    var fr = theme.component.frame;
    var prevGroup = null;
    var out = [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i];
      var at = listAt(p.items.at, offset + i, p.items.stagger);
      if (it.group && it.group !== prevGroup) {
        out.push(
          <div key={'g' + i} style={Object.assign({
            marginTop: i === 0 ? 0 : 14, marginBottom: 6,
            fontSize: D.type.meta, fontWeight: 800, letterSpacing: '0.1em', color: theme.color.blue2,
          }, docIn(theme, t, at))}>{it.group}</div>
        );
      }
      prevGroup = it.group || prevGroup;
      out.push(
        <div key={'i' + i} data-doc-toc-item={offset + i} style={Object.assign({
          // 행 패딩 7px — 10항목(2열 × 5행) + 그룹 머리글 최악 구성이 4:3 본문 높이 737px 안에 들어야 한다
          display: 'flex', alignItems: 'baseline', gap: 14,
          padding: '7px 0', borderBottom: '1px solid ' + fr.line,
        }, docIn(theme, t, at))}>
          {it.no && (
            <div style={{
              flex: '0 0 auto', minWidth: 44, fontSize: D.type.body, fontWeight: 800, color: theme.color.blue,
            }}>{it.no}</div>
          )}
          <div style={{ flex: '0 1 auto', minWidth: 0 }}>
            <div style={Object.assign({ fontSize: D.type.body, fontWeight: 700, lineHeight: 1.32 }, TEXT_WRAP)}>{it.text}</div>
            {it.note && (
              <div style={Object.assign({
                marginTop: 2, fontSize: D.type.micro, color: theme.color.sub, lineHeight: 1.34,
              }, TEXT_WRAP)}>{it.note}</div>
            )}
          </div>
          <div style={{ flex: '1 1 auto', minWidth: 16, borderBottom: '2px dotted ' + fr.line, transform: 'translateY(-7px)' }}></div>
          <div style={{
            flex: '0 0 auto', fontSize: D.type.body, fontWeight: 700, color: theme.color.sub, whiteSpace: 'nowrap',
          }}>{it.page}</div>
        </div>
      );
    }
    return <div style={{ flex: '1 1 0', minWidth: 0 }}>{out}</div>;
  }
  function DocTocScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = tocPlan(d);
    var items = d.items || [];
    var cols = tocSplit(items);
    return (
      <DocPage label="목차" t={t} theme={theme} kicker={d.kicker} page={d.page} footer={d.footer}>
        <div style={Object.assign({ flex: '0 0 auto' }, docIn(theme, t, p.title.at))}>
          <div style={Object.assign({
            fontSize: D.type.title, fontWeight: 800, letterSpacing: '-0.025em', lineHeight: 1.24,
          }, TEXT_WRAP)}>{d.title}</div>
          <DocRule theme={theme} margin="16px 0 10px" />
        </div>
        <div data-doc-fit="row" style={{ flex: '1 1 auto', minHeight: 0, display: 'flex', gap: D.gutter, alignItems: 'flex-start' }}>
          <TocColumn items={cols[0]} offset={0} theme={theme} t={t} plan={p} />
          {cols[1].length > 0 && <TocColumn items={cols[1]} offset={cols[0].length} theme={theme} t={t} plan={p} />}
        </div>
        {d.note && (
          <div style={Object.assign({
            flex: '0 0 auto', marginTop: 16, fontSize: D.type.micro, color: theme.color.faint,
          }, TEXT_WRAP, docIn(theme, t, p.note.at))}>{d.note}</div>
        )}
      </DocPage>
    );
  }
  DocTocScene.nat = 7;
  DocTocScene.schedule = function (d) {
    var p = tocPlan(d);
    return [
      { id: 'title', kind: 'enter', at: p.title.at, dur: p.title.dur, path: '/title' },
      { id: 'items', kind: 'enter', at: p.items.at, dur: p.items.dur, stagger: p.items.stagger, count: p.items.count, path: '/items' },
      { id: 'note', kind: 'enter', at: p.note.at, dur: p.note.dur, path: '/note' },
    ];
  };

  /* ══ tpl.doc-section — 섹션 구분 ══════════════════════════════════════
     큰 번호 + 섹션명 + 한 줄 요지. 여기서 독자는 "장이 바뀌었다"만 읽으면 되므로 밀도를 일부러 비운다
     (문서형 5종 중 유일하게 저밀도 — 대신 이 장에서 다룰 항목을 선택 목록으로 예고할 수 있다). */
  function sectionPlan(d) {
    var n = (d.points || []).length;
    return {
      no: { at: 0.2, dur: IN_DUR },
      name: { at: 0.35, dur: IN_DUR },
      rule: { at: 0.5, dur: 0.6 },
      lead: { at: 0.6, dur: IN_DUR },
      points: { at: 0.85, dur: IN_DUR, stagger: 0.08, count: n },
    };
  }
  function DocSectionScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = sectionPlan(d);
    var points = d.points || [];
    return (
      <DocPage label="섹션" t={t} theme={theme} plain footer={d.footer}>
        <div style={{
          flex: '1 1 auto', minHeight: 0, display: 'flex', alignItems: 'center',
        }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 52, width: '100%' }}>
            <div style={Object.assign({
              // lineHeight 1.16 — 108px 글리프의 잉크 박스(실측 123px = 1.139em)가 줄 상자를 넘지 않게 (오버플로 실측 보정)
              flex: '0 0 auto', fontSize: D.type.numeral, fontWeight: 800, lineHeight: 1.16,
              letterSpacing: '-0.05em', color: theme.color.blue,
            }, docIn(theme, t, p.no.at, 14))}>{d.no}</div>
            <div style={{ flex: '1 1 auto', minWidth: 0, paddingTop: 8 }}>
              <div style={Object.assign({
                fontSize: D.type.name, fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.24,
              }, TEXT_WRAP, docIn(theme, t, p.name.at, 12))}>{d.name}</div>
              <div style={{
                width: seg(t, p.rule.at, p.rule.dur, 0, 108), height: 6, borderRadius: 3,
                background: theme.color.blue, margin: '20px 0',
              }}></div>
              <div style={Object.assign({
                fontSize: D.type.lead, color: theme.color.sub, lineHeight: 1.5,
              }, TEXT_WRAP, docIn(theme, t, p.lead.at))}>{d.lead}</div>
              {points.length > 0 && (
                <div style={{ marginTop: 28, display: 'flex', flexWrap: 'wrap', gap: 12 }}>
                  {points.map(function (pt, i) {
                    return (
                      <div key={i} style={Object.assign({
                        background: theme.component.chip.accentBg, color: theme.component.chip.accentFg,
                        borderRadius: theme.radius.chip, padding: '10px 20px',
                        fontSize: D.type.micro, fontWeight: 700, maxWidth: '100%', boxSizing: 'border-box',
                      }, TEXT_WRAP, docIn(theme, t, listAt(p.points.at, i, p.points.stagger)))}>{pt}</div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </DocPage>
    );
  }
  DocSectionScene.nat = 5;
  DocSectionScene.schedule = function (d) {
    var p = sectionPlan(d);
    return [
      { id: 'no', kind: 'enter', at: p.no.at, dur: p.no.dur, path: '/no' },
      { id: 'name', kind: 'enter', at: p.name.at, dur: p.name.dur, path: '/name' },
      { id: 'rule', kind: 'enter', at: p.rule.at, dur: p.rule.dur },
      { id: 'lead', kind: 'enter', at: p.lead.at, dur: p.lead.dur, path: '/lead' },
      { id: 'points', kind: 'enter', at: p.points.at, dur: p.points.dur, stagger: p.points.stagger, count: p.points.count, path: '/points' },
    ];
  };

  /* ══ 근거 슬롯 — 표/차트/이미지 택1 ═══════════════════════════════════
     본체 우열에 들어가는 근거 1점. 셋 다 같은 카드 그릇(흰 면 + 테두리)에 담고
     캡션·출처를 아래에 붙인다 — 문서에서 그림 번호·출처 표기가 본문만큼 중요하기 때문. */
  function EvidenceTable(props) {
    var e = props.table, theme = props.theme;
    var fr = theme.component.frame;
    var chip = theme.component.chip;
    var headers = e.headers || [];
    var rows = e.rows || [];
    function cellStyle(i, head) {
      return Object.assign({
        flex: i === 0 ? '1.5 1 0' : '1 1 0', minWidth: 0, padding: '9px 10px', boxSizing: 'border-box',
        fontSize: D.type.micro, lineHeight: 1.32,
        fontWeight: head ? 700 : (i === 0 ? 600 : 400),
        color: head ? chip.accentFg : theme.color.ink,
        textAlign: i === 0 ? 'left' : 'right',
      }, TEXT_WRAP);
    }
    return (
      <div style={{ display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', background: chip.accentBg, borderRadius: theme.radius.tag }}>
          {headers.map(function (h, i) {
            return <div key={i} style={cellStyle(i, true)}>{h}</div>;
          })}
        </div>
        {rows.map(function (r, ri) {
          return (
            <div key={ri} style={{ display: 'flex', borderBottom: '1px solid ' + fr.line }}>
              {(r.cells || []).map(function (c, ci) {
                return <div key={ci} style={cellStyle(ci, false)}>{c}</div>;
              })}
            </div>
          );
        })}
      </div>
    );
  }
  function EvidenceChart(props) {
    var c = props.chart, theme = props.theme;
    var fr = theme.component.frame;
    var bars = c.bars || [];
    var max = 0;
    for (var i = 0; i < bars.length; i++) max = Math.max(max, Math.abs(+bars[i].value || 0));
    if (max <= 0) max = 1;
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {bars.map(function (b, i) {
          var ratio = Math.max(0, Math.min(1, (+b.value || 0) / max));  // 0 기준선 · 비례 정확
          var strong = !!b.emphasis;
          return (
            <div key={i}>
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
                <div style={Object.assign({
                  fontSize: D.type.micro, fontWeight: strong ? 800 : 600,
                  color: strong ? theme.color.ink : theme.color.sub, minWidth: 0, lineHeight: 1.3,
                }, TEXT_WRAP)}>{b.label}</div>
                <div style={{
                  fontSize: D.type.micro, fontWeight: 800, whiteSpace: 'nowrap',
                  color: strong ? theme.color.blue : theme.color.sub,
                }}>{b.value}{c.unit || ''}</div>
              </div>
              <div style={{ marginTop: 6, height: 16, borderRadius: theme.radius.bar, background: fr.line }}>
                <div style={{
                  width: (ratio * 100) + '%', height: '100%', borderRadius: theme.radius.bar,
                  background: strong ? theme.color.blue : theme.color.blueBorder,
                }}></div>
              </div>
            </div>
          );
        })}
      </div>
    );
  }
  function EvidenceImage(props) {
    var im = props.image, theme = props.theme;
    var fr = theme.component.frame;
    if (!im.src) {
      return (
        <div style={{
          width: '100%', aspectRatio: '16 / 10', borderRadius: theme.radius.box,
          border: '2px dashed ' + theme.color.blueBorder, background: theme.color.blueSoft,
          display: 'flex', alignItems: 'center', justifyContent: 'center', boxSizing: 'border-box', padding: 20,
        }}>
          <div style={Object.assign({
            fontSize: D.type.micro, color: theme.color.blue, textAlign: 'center', fontWeight: 600,
          }, TEXT_WRAP)}>{im.alt}</div>
        </div>
      );
    }
    return (
      // contain — 문서의 도판은 잘리면 근거가 아니다(영상 d-media 의 cover 규약과 반대로 간다)
      <img src={im.src} alt={im.alt} style={{
        display: 'block', width: '100%', aspectRatio: '16 / 10', objectFit: 'contain',
        borderRadius: theme.radius.box, border: '1px solid ' + fr.line, background: theme.color.card,
      }} />
    );
  }
  function EvidenceCard(props) {
    var e = props.evidence, theme = props.theme, t = props.t, at = props.at;
    var card = theme.component.card;
    var body = null;
    if (e.kind === 'table' && e.table) body = <EvidenceTable table={e.table} theme={theme} />;
    else if (e.kind === 'chart' && e.chart) body = <EvidenceChart chart={e.chart} theme={theme} />;
    else if (e.kind === 'image' && e.image) body = <EvidenceImage image={e.image} theme={theme} />;
    return (
      <div style={Object.assign({
        flex: '1 1 auto', minWidth: 0, display: 'flex', flexDirection: 'column',
        background: card.bg, border: '1px solid ' + card.border, borderRadius: theme.radius.card,
        boxShadow: card.shadowSoft, padding: '22px 24px 20px', boxSizing: 'border-box',
      }, docIn(theme, t, at))}>
        <div style={Object.assign({
          fontSize: D.type.meta, fontWeight: 800, letterSpacing: '-0.01em', lineHeight: 1.3, marginBottom: 16,
        }, TEXT_WRAP)}>{e.caption}</div>
        {body}
        {e.source && (
          <div style={Object.assign({
            marginTop: 'auto', paddingTop: 16, fontSize: D.type.micro, color: theme.color.faint, lineHeight: 1.3,
          }, TEXT_WRAP)}>{e.source}</div>
        )}
      </div>
    );
  }

  /* ══ tpl.doc-body — 본체 (문서형의 중심) ══════════════════════════════
     좌: 제목 + 리드 + 불릿 3~6 + 소결론 / 우: 근거 1점(표·차트·이미지 택1).
     flex 비율 배분이라 세 무대에서 열폭만 달라진다 — 1920: 좌 981/우 727, 1440: 좌 689/우 539,
     A4 1240: 좌 567/우 461. 스키마 maxLength 는 이 중 가장 좁은 열에서 줄 수가 터지지 않는 값이다. */
  function bodyPlan(d) {
    var n = (d.bullets || []).length;
    return {
      title: { at: 0.25, dur: IN_DUR },
      lead: { at: 0.4, dur: IN_DUR },
      bullets: { at: 0.55, dur: IN_DUR, stagger: 0.09, count: n },
      takeaway: { at: 0.55 + n * 0.09 + 0.2, dur: IN_DUR },
      evidence: { at: 0.5, dur: IN_DUR },
    };
  }
  function DocBodyScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = bodyPlan(d);
    var bullets = d.bullets || [];
    var chip = theme.component.chip;
    return (
      <DocPage label="본문" t={t} theme={theme} kicker={d.kicker} page={d.page} footer={d.footer}>
        <div data-doc-fit="row" style={{ flex: '0 1 auto', minHeight: 0, display: 'flex', gap: D.gutter, alignItems: 'stretch' }}>
          <div data-doc-col="text" style={{ flex: '1.55 1 520px', minWidth: 0 }}>
            <div style={Object.assign({
              fontSize: D.type.title, fontWeight: 800, letterSpacing: '-0.025em', lineHeight: 1.26,
            }, TEXT_WRAP, docIn(theme, t, p.title.at))}>{d.title}</div>
            {d.lead && (
              <div style={Object.assign({
                marginTop: 12, fontSize: D.type.lead, color: theme.color.sub, lineHeight: 1.45,
              }, TEXT_WRAP, docIn(theme, t, p.lead.at))}>{d.lead}</div>
            )}
            <div style={{ marginTop: 18 }}>
              {bullets.map(function (b, i) {
                return (
                  <div key={i} data-doc-bullet={i} style={Object.assign({
                    display: 'flex', gap: 14, marginTop: i === 0 ? 0 : 10,
                  }, docIn(theme, t, listAt(p.bullets.at, i, p.bullets.stagger)))}>
                    <div style={{
                      flex: '0 0 auto', width: 12, height: 12, marginTop: 12, borderRadius: 3,
                      background: theme.color.blue,
                    }}></div>
                    <div style={Object.assign({
                      // lineHeight 1.36 — 6불릿 × 2줄 최악 구성이 4:3(가장 낮은 무대) 본문 높이 886px 안에 들어야 한다
                      flex: '1 1 auto', minWidth: 0, fontSize: D.type.body, lineHeight: 1.36,
                    }, TEXT_WRAP)}>
                      {b.tag && (
                        <span style={{
                          display: 'inline-block', marginRight: 8, padding: '1px 10px',
                          borderRadius: theme.radius.tag, background: chip.accentBg, color: chip.accentFg,
                          fontSize: D.type.micro, fontWeight: 700, verticalAlign: '2px',
                        }}>{b.tag}</span>
                      )}
                      {b.text}
                    </div>
                  </div>
                );
              })}
            </div>
            {d.takeaway && (
              <div style={Object.assign({
                marginTop: 18, background: chip.accentBg, borderRadius: theme.radius.box,
                borderLeft: '6px solid ' + theme.color.blue, padding: '14px 20px', boxSizing: 'border-box',
              }, docIn(theme, t, p.takeaway.at))}>
                <div style={Object.assign({
                  fontSize: D.type.body, fontWeight: 700, color: chip.accentFg, lineHeight: 1.38,
                }, TEXT_WRAP)}>{d.takeaway}</div>
              </div>
            )}
          </div>
          <div data-doc-col="evidence" style={{ flex: '1 1 430px', minWidth: 0, display: 'flex' }}>
            <EvidenceCard evidence={d.evidence} theme={theme} t={t} at={p.evidence.at} />
          </div>
        </div>
      </DocPage>
    );
  }
  DocBodyScene.nat = 9;
  DocBodyScene.schedule = function (d) {
    var p = bodyPlan(d);
    return [
      { id: 'title', kind: 'enter', at: p.title.at, dur: p.title.dur, path: '/title' },
      { id: 'lead', kind: 'enter', at: p.lead.at, dur: p.lead.dur, path: '/lead' },
      { id: 'evidence', kind: 'enter', at: p.evidence.at, dur: p.evidence.dur, path: '/evidence' },
      { id: 'bullets', kind: 'enter', at: p.bullets.at, dur: p.bullets.dur, stagger: p.bullets.stagger, count: p.bullets.count, path: '/bullets' },
      { id: 'takeaway', kind: 'enter', at: p.takeaway.at, dur: p.takeaway.dur, path: '/takeaway' },
    ];
  };

  /* ══ tpl.doc-summary — 요약·결론 ══════════════════════════════════════
     좌: 핵심 3~5줄(번호) / 우: 다음 행동(담당·기한 칩). 문서의 마지막 장은
     "무엇을 알았나 / 이제 무엇을 하나" 두 열로 갈리는 것이 회의 자료 관행이다. */
  function summaryPlan(d) {
    var np = (d.points || []).length;
    var na = (d.actions || []).length;
    return {
      title: { at: 0.25, dur: IN_DUR },
      points: { at: 0.45, dur: IN_DUR, stagger: 0.09, count: np },
      actions: { at: 0.6, dur: IN_DUR, stagger: 0.09, count: na },
      note: { at: 0.6 + na * 0.09 + 0.25, dur: IN_DUR },
    };
  }
  function DocSummaryScene(props) {
    var t = props.localTime, d = props.data, theme = props.theme;
    var p = summaryPlan(d);
    var points = d.points || [];
    var actions = d.actions || [];
    var card = theme.component.card;
    var chip = theme.component.chip;
    var fr = theme.component.frame;
    return (
      <DocPage label="요약" t={t} theme={theme} kicker={d.kicker} page={d.page} footer={d.footer}>
        <div style={Object.assign({ flex: '0 0 auto' }, docIn(theme, t, p.title.at))}>
          <div style={Object.assign({
            fontSize: D.type.title, fontWeight: 800, letterSpacing: '-0.025em', lineHeight: 1.26,
          }, TEXT_WRAP)}>{d.title}</div>
          <DocRule theme={theme} margin="16px 0 4px" />
        </div>
        <div data-doc-fit="row" style={{ flex: '0 1 auto', minHeight: 0, display: 'flex', gap: D.gutter, alignItems: 'stretch', paddingTop: 18 }}>
          <div data-doc-col="points" style={{ flex: '1.3 1 500px', minWidth: 0 }}>
            {points.map(function (pt, i) {
              return (
                <div key={i} data-doc-point={i} style={Object.assign({
                  display: 'flex', gap: 16, marginTop: i === 0 ? 0 : 16,
                  paddingBottom: 16, borderBottom: '1px solid ' + fr.line,
                }, docIn(theme, t, listAt(p.points.at, i, p.points.stagger)))}>
                  <div style={{
                    flex: '0 0 auto', width: 38, height: 38, borderRadius: theme.radius.tag,
                    background: chip.accentBg, color: chip.accentFg,
                    fontSize: D.type.micro, fontWeight: 800,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>{i + 1}</div>
                  <div style={{ flex: '1 1 auto', minWidth: 0 }}>
                    <div style={Object.assign({
                      fontSize: D.type.body, fontWeight: 700, lineHeight: 1.4,
                    }, TEXT_WRAP)}>{pt.text}</div>
                    {pt.note && (
                      <div style={Object.assign({
                        marginTop: 4, fontSize: D.type.micro, color: theme.color.sub, lineHeight: 1.34,
                      }, TEXT_WRAP)}>{pt.note}</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <div data-doc-col="actions" style={{
            flex: '1 1 400px', minWidth: 0, background: card.bg, border: '1px solid ' + card.border,
            borderRadius: theme.radius.card, boxShadow: card.shadowSoft,
            padding: '20px 22px', boxSizing: 'border-box',
          }}>
            <div style={Object.assign({
              fontSize: D.type.meta, fontWeight: 800, color: theme.color.blue, letterSpacing: '0.02em',
            }, docIn(theme, t, p.actions.at - 0.1))}>{d.actions_title || '다음 행동'}</div>
            <div style={{ marginTop: 14 }}>
              {actions.map(function (a, i) {
                return (
                  <div key={i} data-doc-action={i} style={Object.assign({
                    display: 'flex', gap: 12, alignItems: 'flex-start',
                    marginTop: i === 0 ? 0 : 12, paddingTop: i === 0 ? 0 : 12,
                    borderTop: i === 0 ? 'none' : '1px solid ' + fr.line,
                  }, docIn(theme, t, listAt(p.actions.at, i, p.actions.stagger)))}>
                    <div style={{
                      flex: '0 0 auto', width: 22, height: 22, marginTop: 6, borderRadius: 6,
                      border: '2px solid ' + theme.color.blueBorder, background: theme.color.blueSoft,
                      boxSizing: 'border-box',
                    }}></div>
                    <div style={{ flex: '1 1 auto', minWidth: 0 }}>
                      <div style={Object.assign({
                        fontSize: D.type.body, lineHeight: 1.38,
                      }, TEXT_WRAP)}>{a.text}</div>
                      {(a.owner || a.due) && (
                        <div style={{ marginTop: 6, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                          {a.owner && (
                            <span style={{
                              padding: '2px 12px', borderRadius: theme.radius.tag,
                              background: chip.accentBg, color: chip.accentFg,
                              fontSize: D.type.micro, fontWeight: 700, whiteSpace: 'nowrap',
                            }}>{a.owner}</span>
                          )}
                          {a.due && (
                            <span style={{
                              padding: '1px 12px', borderRadius: theme.radius.tag,
                              background: card.bg, color: theme.color.sub,
                              border: '1px solid ' + fr.line,
                              fontSize: D.type.micro, fontWeight: 700, whiteSpace: 'nowrap',
                            }}>{a.due}</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        {d.note && (
          <div style={Object.assign({
            flex: '0 0 auto', marginTop: 16, fontSize: D.type.micro, color: theme.color.faint,
          }, TEXT_WRAP, docIn(theme, t, p.note.at))}>{d.note}</div>
        )}
      </DocPage>
    );
  }
  DocSummaryScene.nat = 8;
  DocSummaryScene.schedule = function (d) {
    var p = summaryPlan(d);
    return [
      { id: 'title', kind: 'enter', at: p.title.at, dur: p.title.dur, path: '/title' },
      { id: 'points', kind: 'enter', at: p.points.at, dur: p.points.dur, stagger: p.points.stagger, count: p.points.count, path: '/points' },
      { id: 'actions', kind: 'enter', at: p.actions.at, dur: p.actions.dur, stagger: p.actions.stagger, count: p.actions.count, path: '/actions' },
      { id: 'note', kind: 'enter', at: p.note.at, dur: p.note.dur, path: '/note' },
    ];
  };

  OMX.templates = Object.assign(OMX.templates || {}, {
    DocCoverScene: DocCoverScene,
    DocTocScene: DocTocScene,
    DocSectionScene: DocSectionScene,
    DocBodyScene: DocBodyScene,
    DocSummaryScene: DocSummaryScene,
  });
  OMX.templateIndex = Object.assign(OMX.templateIndex || {}, {
    'tpl.doc-cover': DocCoverScene,
    'tpl.doc-toc': DocTocScene,
    'tpl.doc-section': DocSectionScene,
    'tpl.doc-body': DocBodyScene,
    'tpl.doc-summary': DocSummaryScene,
  });
  // 문서형 공개면 — 지원 무대 3종·문서 크롬·스케줄 유틸 (가로/세로 자산과 이름 충돌 없음)
  OMX.doc = Object.assign(OMX.doc || {}, {
    formats: ['deck-doc-16x9', 'deck-4x3', 'print-a4'],
    stages: D.stages,
    spec: D,
    settleOf: settleOf,
    stillOf: stillOf,
    metaphors: { 'doc-page': DocPage, 'doc-rule': DocRule },
  });
})();
