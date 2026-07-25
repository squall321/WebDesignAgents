/* HWAX 협업진단 플랫폼 — 90s 소개영상 scenes. Engine: animations-v2.jsx (SceneStage). */
const { SceneStage, useTimeline, Easing, animate } = window;

const C = {
  bg: '#F6F7FA', ink: '#101B3E', sub: '#57607A', faint: '#8A92A8', line: '#E2E6F0',
  blue: '#1428A0', blue2: '#3D53C6', blueSoft: '#EBEEFA', blueBorder: '#C9D1F0',
  card: '#FFFFFF', red: '#A8402F', redSoft: '#F8ECE8', green: '#1F7A55', greenSoft: '#E7F2EC',
  skel: '#DDE1EC', chatGray: '#F1F3F8',
};
const F = "'Pretendard Variable', Pretendard, 'Noto Sans KR', sans-serif";
const SHADOW = '0 18px 44px rgba(16,27,62,0.08)';

const A = (t, start, dur, from, to, ease) =>
  animate({ from, to, start, end: start + dur, ease: ease || Easing.easeOutCubic })(t);
const rise = (t, at, dur = 0.7, dy = 26) => ({
  opacity: A(t, at, dur, 0, 1),
  transform: `translateY(${A(t, at, dur, dy, 0)}px)`,
});

function DotGrid({ t }) {
  return (
    <div style={{
      position: 'absolute', inset: -60, opacity: 0.55,
      backgroundImage: `radial-gradient(${'#E0E4F0'} 1.6px, transparent 1.6px)`,
      backgroundSize: '46px 46px',
      transform: `translateY(${(t * 2) % 46}px)`,
    }}></div>
  );
}

function Frame({ label, idx, kicker, title, titleSize = 56, t, children, hideFooter }) {
  const { time } = useTimeline();
  return (
    <div data-screen-label={`${label} @${Math.floor(time)}s`} style={{
      position: 'absolute', inset: 0, background: C.bg, fontFamily: F, color: C.ink, overflow: 'hidden', wordBreak: 'keep-all',
    }}>
      <DotGrid t={t} />
      <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(1400px 700px at 50% -12%, rgba(20,40,160,0.05), transparent)' }}></div>
      {kicker && (
        <div style={{ position: 'absolute', left: 140, top: 108, display: 'flex', alignItems: 'center', gap: 18, ...rise(t, 0.15) }}>
          <div style={{ width: 46, height: 5, background: C.blue, borderRadius: 3 }}></div>
          <div style={{ fontSize: 26, fontWeight: 700, letterSpacing: '0.18em', color: C.blue }}>{kicker}</div>
        </div>
      )}
      {title && (
        <div style={{ position: 'absolute', left: 140, top: 162, fontSize: titleSize, fontWeight: 800, letterSpacing: '-0.02em', lineHeight: 1.18, ...rise(t, 0.35) }}>{title}</div>
      )}
      {children}
      {!hideFooter && (
        <div style={{ position: 'absolute', left: 140, right: 140, bottom: 56, borderTop: `1px solid ${C.line}`, paddingTop: 22, display: 'flex', justifyContent: 'space-between', fontSize: 24, color: C.faint, opacity: A(t, 0.5, 0.8, 0, 1) }}>
          <span>HWAX 협업진단 플랫폼</span><span>{idx} / 07</span>
        </div>
      )}
    </div>
  );
}

/* ── 01 오프닝 (8s) ─────────────────────────────── */
function S1Opening({ localTime: t }) {
  const dots = [0, 1, 2, 3, 4, 5];
  const lineW = A(t, 2.7, 0.9, 0, 620);
  return (
    <Frame label="오프닝" t={t} hideFooter>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 38 }}>
        <div style={{ ...rise(t, 0.4), display: 'flex' }}>
          <div style={{ border: `1.5px solid ${C.blueBorder}`, background: '#FFFFFFB0', color: C.blue, fontSize: 26, fontWeight: 700, letterSpacing: '0.1em', padding: '14px 32px', borderRadius: 999 }}>
            전문가 다중 라운드 심의 시스템</div>
        </div>
        <div style={{ fontSize: 112, fontWeight: 800, letterSpacing: '-0.03em', lineHeight: 1.1, textAlign: 'center', ...rise(t, 1.0, 0.9, 34) }}>
          HWAX <span style={{ color: C.blue }}>협업진단</span> 플랫폼
        </div>
        <div style={{ fontSize: 36, color: C.sub, fontWeight: 500, ...rise(t, 1.9) }}>
          질문 하나가, 하나의 의사결정문이 되기까지</div>
        <div style={{ position: 'relative', width: 620, height: 40, marginTop: 12 }}>
          <div style={{ position: 'absolute', left: (620 - lineW) / 2, top: 19, width: lineW, height: 2, background: C.blueBorder }}></div>
          {dots.map((i) => {
            const pop = A(t, 3.0 + i * 0.16, 0.45, 0, 1, Easing.easeOutBack);
            const pulse = 1 + 0.09 * Math.sin(t * 2.2 + i * 1.1);
            return (
              <div key={i} style={{
                position: 'absolute', top: 12, left: 40 + i * 104, width: 16, height: 16, borderRadius: 999,
                background: i % 2 ? C.blue2 : C.blue, opacity: pop,
                transform: `scale(${pop * pulse})`,
              }}></div>
            );
          })}
        </div>
      </div>
      <div style={{ position: 'absolute', bottom: 72, left: 0, right: 0, textAlign: 'center', fontSize: 24, color: C.faint, opacity: A(t, 3.8, 0.8, 0, 1) }}>
        플랫폼 브리핑 · 2026</div>
    </Frame>
  );
}

/* ── 02 문제 (13s) ─────────────────────────────── */
function S2Problem({ localTime: t }) {
  const bars = [500, 560, 460, 320];
  const xRows = ['관점의 충돌이 없다', '상호 반박이 없다', '스스로 검증하지 못한다'];
  return (
    <Frame label="문제" idx="02" kicker="문제 인식" title="단일 AI 질의는 왜 부족한가" t={t}>
      <div style={{ position: 'absolute', left: 140, top: 330, width: 800, height: 490, background: C.card, border: `1px solid ${C.line}`, borderRadius: 24, boxShadow: SHADOW, ...rise(t, 0.9) }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '20px 28px', borderBottom: `1px solid ${C.line}` }}>
          {[0, 1, 2].map((i) => <div key={i} style={{ width: 14, height: 14, borderRadius: 99, background: C.skel }}></div>)}
          <div style={{ marginLeft: 12, fontSize: 24, color: C.faint, fontWeight: 600 }}>일반 챗봇 — 질의 1회</div>
        </div>
        <div style={{ padding: '30px 34px', display: 'flex', flexDirection: 'column', gap: 26 }}>
          <div style={{ alignSelf: 'flex-end', maxWidth: 560, background: C.blueSoft, color: C.ink, borderRadius: '20px 20px 4px 20px', padding: '20px 26px', fontSize: 28, fontWeight: 600, ...rise(t, 1.3, 0.6, 18) }}>
            AP 패키지 중앙 솔더볼, 왜 깨졌을까요?</div>
          <div style={{ alignSelf: 'flex-start', width: 620, background: C.chatGray, borderRadius: '20px 20px 20px 4px', padding: '26px 28px', ...rise(t, 2.7, 0.6, 18) }}>
            {bars.map((w, i) => (
              <div key={i} style={{ width: A(t, 3.0 + i * 0.35, 0.5, 0, w), height: 16, borderRadius: 8, background: C.skel, marginBottom: i === bars.length - 1 ? 0 : 16 }}></div>
            ))}
          </div>
          <div style={{ alignSelf: 'flex-start', display: 'flex', alignItems: 'center', gap: 12, background: '#EEF0F5', border: `1px solid ${C.line}`, borderRadius: 999, padding: '12px 24px', ...rise(t, 4.8, 0.6, 14) }}>
            <div style={{ width: 12, height: 12, borderRadius: 99, background: C.faint }}></div>
            <span style={{ fontSize: 25, color: C.sub, fontWeight: 600 }}>하나의 관점으로 뭉뚱그려진, 평균적인 답</span>
          </div>
        </div>
      </div>
      <div style={{ position: 'absolute', left: 1050, top: 372, width: 730 }}>
        <div style={{ fontSize: 35, lineHeight: 1.55, fontWeight: 500, color: C.ink, ...rise(t, 5.9) }}>
          불량 원인 규명, 설계안 선정 —<br />
          <span style={{ fontWeight: 800 }}>여러 분야의 전문성이 <span style={{ color: C.blue }}>동시에</span> 필요한</span> 문제입니다.
        </div>
        <div style={{ marginTop: 44, display: 'flex', flexDirection: 'column', gap: 24 }}>
          {xRows.map((s, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 20, ...rise(t, 7.7 + i * 1.1, 0.6, 18) }}>
              <div style={{ width: 50, height: 50, borderRadius: 14, background: C.redSoft, color: C.red, fontSize: 27, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>✕</div>
              <div style={{ fontSize: 31, fontWeight: 700 }}>{s}</div>
            </div>
          ))}
        </div>
        <div style={{ marginTop: 42, fontSize: 27, color: C.sub, ...rise(t, 11.2, 0.6, 14) }}>
          한 번의 답변으로는, 의사결정이 되지 않습니다.</div>
      </div>
    </Frame>
  );
}

/* ── 03 심의란 (11s) ─────────────────────────────── */
const PERSONAS = [
  { ini: '재', name: '재료역학' }, { ini: '공', name: '패키징 공정' }, { ini: '신', name: '신뢰성' },
  { ini: '열', name: '열 해석' }, { ini: '품', name: '품질·VOC' }, { ini: '설', name: '설계' },
];
function S3Approach({ localTime: t }) {
  const cx = 480, cy = 330, r = 246;
  const rounds = [
    { chip: 'R1', name: '초기 입장', desc: '전 전문가 병렬 발언 — 관점·데이터 해석·권장안' },
    { chip: 'R2', name: '상호 반박', desc: '수치·표준·실패모드 근거 반박, “두루뭉술 금지”' },
    { chip: 'R3', name: '수렴 · 표결', desc: '양보 불가 제약 명시, 동의/조건부/반대 집계' },
  ];
  return (
    <Frame label="심의란" idx="03" kicker="HWAX의 접근" title="여러 전문가가, 여러 라운드에 걸쳐 토론합니다" t={t}>
      <div style={{ position: 'absolute', left: 130, top: 330, width: 960, height: 640 }}>
        {PERSONAS.map((p, i) => {
          const ang = (i * 60 - 90) * Math.PI / 180;
          const lw = r - 118;
          return (
            <div key={'l' + i} style={{
              position: 'absolute', left: cx, top: cy, width: lw, height: 2, background: C.blueBorder,
              transformOrigin: 'left center',
              transform: `rotate(${i * 60 - 90}deg) translateX(64px) scaleX(${A(t, 2.6 + i * 0.1, 0.6, 0, 1)})`,
            }}>
              <div style={{
                position: 'absolute', top: -5, left: `${((Math.sin(t * 1.5 + i * 1.3) + 1) / 2) * 88}%`,
                width: 11, height: 11, borderRadius: 99, background: C.blue2,
                opacity: A(t, 3.4, 0.6, 0, 0.9),
              }}></div>
            </div>
          );
        })}
        {PERSONAS.map((p, i) => {
          const ang = (i * 60 - 90) * Math.PI / 180;
          const x = cx + Math.cos(ang) * r, y = cy + Math.sin(ang) * r;
          const pop = A(t, 1.0 + i * 0.18, 0.55, 0, 1, Easing.easeOutBack);
          return (
            <div key={i} style={{ position: 'absolute', left: x - 56, top: y - 56, width: 112, textAlign: 'center', opacity: pop, transform: `scale(${pop})` }}>
              <div style={{ width: 100, height: 100, margin: '0 auto', borderRadius: 999, background: C.card, border: `2px solid ${C.blueBorder}`, boxShadow: SHADOW, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 38, fontWeight: 800, color: C.blue }}>{p.ini}</div>
              <div style={{ marginTop: 10, fontSize: 24, fontWeight: 600, color: C.sub, whiteSpace: 'nowrap' }}>{p.name}</div>
            </div>
          );
        })}
        <div style={{ position: 'absolute', left: cx - 78, top: cy - 46, width: 156, height: 92, borderRadius: 20, background: C.blue, color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 34, fontWeight: 800, boxShadow: '0 16px 36px rgba(20,40,160,0.35)', ...rise(t, 0.6, 0.6, 14) }}>질문</div>
      </div>
      <div style={{ position: 'absolute', left: 1150, top: 350, width: 640, display: 'flex', flexDirection: 'column', gap: 26 }}>
        {rounds.map((rd, i) => (
          <div key={i} style={{ display: 'flex', gap: 22, alignItems: 'flex-start', ...rise(t, 5.4 + i * 1.3, 0.6, 20) }}>
            <div style={{ width: 62, height: 62, borderRadius: 16, background: C.blueSoft, color: C.blue, fontSize: 27, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>{rd.chip}</div>
            <div>
              <div style={{ fontSize: 31, fontWeight: 800 }}>{rd.name}</div>
              <div style={{ fontSize: 25, color: C.sub, marginTop: 6, lineHeight: 1.4 }}>{rd.desc}</div>
            </div>
          </div>
        ))}
        <div style={{ display: 'flex', gap: 22, alignItems: 'center', marginTop: 6, ...rise(t, 9.3, 0.7, 20) }}>
          <div style={{ width: 62, textAlign: 'center', fontSize: 34, color: C.faint, flexShrink: 0 }}>↓</div>
          <div style={{ flex: 1, background: C.blue, color: '#fff', borderRadius: 18, padding: '22px 28px', boxShadow: '0 16px 36px rgba(20,40,160,0.3)' }}>
            <div style={{ fontSize: 30, fontWeight: 800 }}>의장 의사결정문</div>
            <div style={{ fontSize: 24, opacity: 0.85, marginTop: 6 }}>결론 · 합의 근거 · 반대의견 · 미해결 쟁점</div>
          </div>
        </div>
      </div>
    </Frame>
  );
}

/* ── 04 절차 (18s) ─────────────────────────────── */
const STEPS = [
  { n: '01', name: '질문 접수', desc: '불량 화두면 최근 VOC·이슈를 먼저 자동 환기' },
  { n: '02', name: '전문가 발굴', desc: '300+ 페르소나 풀에서 의미검색 — 인원 제한 없음' },
  { n: '03', name: '정량 근거 준비', desc: 'DOE·적층해석 등 도구 계산값을 토론에 주입' },
  { n: '04', name: '다중 라운드 토론', desc: '초기 입장 → 상호 반박 → 수렴·표결 (2~8라운드)' },
  { n: '05', name: '의장 의사결정문', desc: '결정·합의 근거·반대의견·미해결 쟁점 필수 작성' },
  { n: '06', name: '기록', desc: 'Report Archive 보고서 + 대화 저장, 언제든 이어하기' },
];
function S4Process({ localTime: t }) {
  const stepAt = (i) => 2.0 + i * 2.35;
  return (
    <Frame label="절차" idx="04" kicker="표준 파이프라인" title="질문 하나가 의사결정문이 되기까지 — 6단계" t={t}>
      <div style={{ position: 'absolute', left: 140, top: 296, width: 1640, height: 5, background: C.line, borderRadius: 3 }}>
        <div style={{ width: A(t, 2.0, 13.5, 0, 1640, Easing.linear), height: 5, background: C.blue, borderRadius: 3 }}></div>
      </div>
      {STEPS.map((s, i) => {
        const col = i % 3, row = Math.floor(i / 3);
        const app = rise(t, 1.0 + i * 0.1, 0.6, 22);
        const on = A(t, stepAt(i), 0.55, 0, 1);
        return (
          <div key={i} style={{
            position: 'absolute', left: 140 + col * 562, top: 344 + row * 292, width: 516, height: 256,
            background: C.card, borderRadius: 22, padding: '30px 32px', boxSizing: 'border-box',
            border: `2px solid ${on > 0.5 ? C.blue2 : C.line}`,
            boxShadow: on > 0.5 ? '0 20px 44px rgba(20,40,160,0.14)' : '0 8px 22px rgba(16,27,62,0.05)',
            opacity: app.opacity * (0.45 + 0.55 * on),
            transform: `${app.transform} translateY(${-6 * on}px)`,
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
              <div style={{
                width: 62, height: 62, borderRadius: 16, fontSize: 27, fontWeight: 800,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: on > 0.5 ? C.blue : C.blueSoft, color: on > 0.5 ? '#fff' : C.blue2,
              }}>{s.n}</div>
              <div style={{ fontSize: 33, fontWeight: 800 }}>{s.name}</div>
            </div>
            <div style={{ marginTop: 22, fontSize: 26, color: C.sub, lineHeight: 1.5 }}>{s.desc}</div>
          </div>
        );
      })}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 952, textAlign: 'center', fontSize: 26, color: C.sub, ...rise(t, 16.0, 0.7, 16) }}>
        모든 도구 호출은 <span style={{ fontWeight: 800, color: C.ink }}>MCP 게이트웨이 한 곳</span>을 지납니다 — 인증·인가·감사 로그가 단일 지점에서 적용
      </div>
    </Frame>
  );
}

/* ── 05 자체교정 (13s) ─────────────────────────────── */
function S5SelfCorrect({ localTime: t }) {
  const cols = [
    {
      at: 1.1, chip: 'R1', chipBg: C.blueSoft, chipC: C.blue2, label: '투입된 초기 계산',
      quote: '“고온 구간은 무해하다”', tagAt: 2.6, tag: '체적탄성계수 유지 누락 — 오류', tagBg: C.redSoft, tagC: C.red,
    },
    {
      at: 4.3, chip: 'R2', chipBg: C.blueSoft, chipC: C.blue2, label: '다른 전문가의 반박',
      quote: '“얇은 충진층은 고온에서 유압잭처럼 팽창합니다”', tagAt: 6.0, tag: '초기 판정 번복 — 전원 수용', tagBg: C.blueSoft, tagC: C.blue,
    },
  ];
  return (
    <Frame label="자체교정" idx="05" kicker="차별점 — 자체 교정" title="근거 계산이 틀려도, 토론이 스스로 잡아냅니다" t={t}>
      {cols.map((c, i) => (
        <div key={i} style={{ position: 'absolute', left: 140 + i * 566, top: 356, width: 508 }}>
          <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 22, boxShadow: SHADOW, padding: '30px 32px', minHeight: 330, boxSizing: 'border-box', ...rise(t, c.at) }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
              <div style={{ width: 56, height: 56, borderRadius: 14, background: c.chipBg, color: c.chipC, fontSize: 25, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{c.chip}</div>
              <div style={{ fontSize: 25, color: C.sub, fontWeight: 600 }}>{c.label}</div>
            </div>
            <div style={{ marginTop: 26, fontSize: 31, fontWeight: 700, lineHeight: 1.45 }}>{c.quote}</div>
            <div style={{ marginTop: 26, display: 'inline-block', background: c.tagBg, color: c.tagC, fontSize: 24, fontWeight: 700, padding: '10px 20px', borderRadius: 999, opacity: A(t, c.tagAt, 0.5, 0, 1), transform: `translateY(${A(t, c.tagAt, 0.5, 12, 0)}px)` }}>{c.tag}</div>
          </div>
        </div>
      ))}
      <div style={{ position: 'absolute', left: 1272, top: 356, width: 508 }}>
        <div style={{ background: C.card, border: `1px solid ${C.line}`, borderRadius: 22, boxShadow: SHADOW, padding: '30px 32px', minHeight: 330, boxSizing: 'border-box', ...rise(t, 7.6) }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
            <div style={{ width: 56, height: 56, borderRadius: 14, background: C.greenSoft, color: C.green, fontSize: 25, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>R3</div>
            <div style={{ fontSize: 25, color: C.sub, fontWeight: 600 }}>수렴 · 표결</div>
          </div>
          <div style={{ marginTop: 30, display: 'flex', gap: 18 }}>
            {PERSONAS.map((p, i) => {
              const ck = A(t, 8.5 + i * 0.18, 0.4, 0, 1, Easing.easeOutBack);
              return (
                <div key={i} style={{ position: 'relative', width: 58, height: 58, borderRadius: 999, background: C.blueSoft, border: `2px solid ${C.blueBorder}`, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 24, fontWeight: 800, color: C.blue }}>
                  {p.ini}
                  <div style={{ position: 'absolute', right: -7, bottom: -7, width: 27, height: 27, borderRadius: 99, background: C.green, color: '#fff', fontSize: 17, fontWeight: 800, display: 'flex', alignItems: 'center', justifyContent: 'center', opacity: ck, transform: `scale(${ck})` }}>✓</div>
                </div>
              );
            })}
          </div>
          <div style={{ marginTop: 32, display: 'inline-block', background: C.green, color: '#fff', fontSize: 25, fontWeight: 800, padding: '12px 24px', borderRadius: 999, opacity: A(t, 10.1, 0.5, 0, 1), transform: `translateY(${A(t, 10.1, 0.5, 12, 0)}px)` }}>
            6인 만장일치 — 단일 메커니즘 수렴</div>
        </div>
      </div>
      {[0, 1].map((i) => (
        <div key={i} style={{ position: 'absolute', left: 662 + i * 566, top: 500, fontSize: 44, color: C.faint, opacity: A(t, 3.5 + i * 3.3, 0.5, 0, 1) }}>→</div>
      ))}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 782, textAlign: 'center', fontSize: 26, color: C.sub, ...rise(t, 11.0, 0.7, 16) }}>
        보고서 #14 · AP 패키지 중앙볼 크랙 — <span style={{ fontWeight: 800, color: C.ink }}>정답을 입력하지 않은 심의</span>가 사내 결론을 독립 재현했습니다
      </div>
    </Frame>
  );
}

/* ── 06 실증사례 (15s) ─────────────────────────────── */
const CASES = [
  {
    at: 1.1, rpt: '보고서 #14', meta: '전문가 6인 · 3라운드', title: 'AP 패키지\n중앙볼 크랙 규명',
    desc: '사내에서 이미 확인된 결론을 사전지식 없이 재현 — 초기 계산의 오류까지 토론이 자체 교정.',
    badge: '✓ 만장일치 · 결론 독립 재현', bBg: C.greenSoft, bC: C.green,
  },
  {
    at: 4.7, rpt: '보고서 #10', meta: '전문가 5인 · 이어하기', title: '폴더블 FPCB\n폴딩 구간 적층 설계',
    desc: '굴곡반경 0.7R 기준 도출 — 실무 결론과 독립 일치. 사람의 추가 질문이 4라운드로 같은 보고서에 증보.',
    badge: '✓ 만장일치 · 0.7R 실무와 일치', bBg: C.greenSoft, bC: C.green,
  },
  {
    at: 8.3, rpt: '보고서 #16', meta: '전문가 8인', title: '전기박리 테이프\n낙하강도 역설',
    desc: '사람이 제시하지 않은 새 후보축 3개를 자체 발견 — 성급한 확정 대신 게이트형 검증 로드맵으로 결론.',
    badge: '새 후보축 3개 자체 발견', bBg: C.blueSoft, bC: C.blue,
  },
];
function S6Cases({ localTime: t }) {
  return (
    <Frame label="실증사례" idx="06" kicker="실증" title="실제 난제 3건 — 정답을 알려주지 않고 검증했습니다" t={t}>
      {CASES.map((c, i) => (
        <div key={i} style={{
          position: 'absolute', left: 140 + i * 566, top: 350, width: 508, height: 520,
          background: C.card, border: `1px solid ${C.line}`, borderRadius: 24, boxShadow: SHADOW,
          padding: '34px 36px', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', ...rise(t, c.at, 0.7, 30),
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div style={{ background: C.blueSoft, color: C.blue, fontSize: 24, fontWeight: 800, padding: '8px 18px', borderRadius: 999 }}>{c.rpt}</div>
            <div style={{ fontSize: 24, color: C.faint, fontWeight: 600 }}>{c.meta}</div>
          </div>
          <div style={{ marginTop: 30, fontSize: 38, fontWeight: 800, lineHeight: 1.3, whiteSpace: 'pre-line', ...rise(t, c.at + 0.2, 0.6, 14) }}>{c.title}</div>
          <div style={{ marginTop: 22, fontSize: 26, color: C.sub, lineHeight: 1.55, ...rise(t, c.at + 0.35, 0.6, 14) }}>{c.desc}</div>
          <div style={{ marginTop: 'auto', alignSelf: 'flex-start', background: c.bBg, color: c.bC, fontSize: 24, fontWeight: 800, padding: '12px 22px', borderRadius: 999, opacity: A(t, c.at + 0.9, 0.5, 0, 1), transform: `translateY(${A(t, c.at + 0.9, 0.5, 10, 0)}px)` }}>{c.badge}</div>
        </div>
      ))}
      <div style={{ position: 'absolute', left: 0, right: 0, top: 906, textAlign: 'center', fontSize: 26, color: C.sub, ...rise(t, 12.3, 0.7, 16) }}>
        세 건 모두 회의록과 의사결정문이 <span style={{ fontWeight: 800, color: C.ink }}>Report Archive</span>에 남아, 누구든 근거를 되짚을 수 있습니다
      </div>
    </Frame>
  );
}

/* ── 07 클로징 (12s) ─────────────────────────────── */
function S7Closing({ localTime: t }) {
  const stats = [
    { v: '수 주 → 몇 시간', d: '6~8개 분야 교차 검토를 자동으로' },
    { v: '반증 가능한 결론', d: '킬 조건과 검증 실험이 함께 담긴 답' },
    { v: '전 과정 기록', d: '발언·반박·소수의견까지 추적 가능' },
  ];
  const out = A(t, 5.7, 0.7, 1, 0, Easing.easeInCubic);
  return (
    <Frame label="클로징" t={t} hideFooter>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 90, opacity: out, transform: `translateY(${(1 - out) * -26}px)` }}>
        {stats.map((s, i) => (
          <div key={i} style={{ width: 480, textAlign: 'center', ...rise(t, 0.7 + i * 0.8, 0.7, 26) }}>
            <div style={{ fontSize: 56, fontWeight: 800, color: C.blue, letterSpacing: '-0.02em' }}>{s.v}</div>
            <div style={{ fontSize: 27, color: C.sub, marginTop: 16 }}>{s.d}</div>
          </div>
        ))}
      </div>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 34 }}>
        <div style={{ width: A(t, 6.7, 0.8, 0, 120), height: 5, background: C.blue, borderRadius: 3 }}></div>
        <div style={{ fontSize: 92, fontWeight: 800, letterSpacing: '-0.03em', ...rise(t, 7.0, 0.9, 30) }}>
          HWAX <span style={{ color: C.blue }}>협업진단</span> 플랫폼</div>
        <div style={{ fontSize: 36, color: C.sub, fontWeight: 500, ...rise(t, 7.9) }}>
          질문을 던지세요 — 전문가 회의가 열립니다.</div>
        <div style={{ display: 'flex', gap: 24, marginTop: 14, ...rise(t, 8.9) }}>
          <div style={{ background: C.card, border: `1.5px solid ${C.blueBorder}`, borderRadius: 999, padding: '16px 34px', fontSize: 27, fontWeight: 700, color: C.ink, boxShadow: SHADOW }}>
            포털 웹 챗 · <span style={{ color: C.blue, fontWeight: 800 }}>/심의</span></div>
          <div style={{ background: C.card, border: `1.5px solid ${C.blueBorder}`, borderRadius: 999, padding: '16px 34px', fontSize: 27, fontWeight: 700, color: C.ink, boxShadow: SHADOW }}>
            개인 Claude 연결 · <span style={{ color: C.blue, fontWeight: 800 }}>MCP</span></div>
        </div>
        <div style={{ fontSize: 24, color: C.faint, marginTop: 20, opacity: A(t, 9.8, 0.7, 0, 1) }}>
          모든 심의는 Report Archive와 대화 저장소에 남습니다</div>
      </div>
    </Frame>
  );
}

/* ── App ─────────────────────────────── */
function HwaxIntroVideo() {
  return (
    <div style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <SceneStage width={1920} height={1080} bg="#F6F7FA" scenes={window.OM_SCENES} playback={window.OM_PLAYBACK}>
        {{
          '오프닝': S1Opening, '문제': S2Problem, '심의란': S3Approach,
          '절차': S4Process, '자체교정': S5SelfCorrect, '실증사례': S6Cases, '클로징': S7Closing,
        }}
      </SceneStage>
    </div>
  );
}
window.HwaxIntroVideo = HwaxIntroVideo;
