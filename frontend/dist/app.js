// WebDesignAgents 콘솔 SPA 로직 — 상대경로 api/* fetch(서브패스 프록시 대응), hwax-blue 토큰 주입
'use strict';

// ── 공통 유틸 ────────────────────────────────────────────────────────────────

function esc(s) {
  return String(s == null ? '' : s)
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

function $(id) { return document.getElementById(id); }

async function api(path, options) {
  const res = await fetch(path, options);
  let body = null;
  try { body = await res.json(); } catch (_) { /* 빈 응답 허용 */ }
  if (body && typeof body === 'object' && 'success' in body) {
    if (!body.success) throw new Error(body.message || ('HTTP ' + res.status));
    return body.data;
  }
  if (!res.ok) throw new Error('HTTP ' + res.status);
  return body;
}

function fmtBytes(n) {
  if (n == null) return '';
  if (n > 1048576) return (n / 1048576).toFixed(1) + ' MB';
  if (n > 1024) return (n / 1024).toFixed(1) + ' KB';
  return n + ' B';
}

function fmtTime(iso) {
  if (!iso) return '';
  return iso.replace('T', ' ').replace(/\+.*$/, '').slice(0, 19);
}

/** 화면에 남기는 상태 라벨 — 매핑 누락 시 영문 원값이 새지 않게 전 상태를 선언한다. */
const STATUS_KO = {
  pending: '대기', queued: '대기', running: '실행 중', done: '완료', failed: '실패',
  rendering: '렌더 중', created: '생성됨', in_progress: '진행 중', closed: '폐회',
  draft: '초안', active: '운영', deprecated: '폐기',
};
const ko = (v) => STATUS_KO[v] || (v ? String(v) : '');

const MEETING_TYPE_KO = {
  brainstorm: '컨셉 발산', design_review: '시안 크리틱', tradeoff: '시안 선정',
  scenario_build: '시나리오 빌드', module_review: '모듈 승격 심사',
};

/** 파이프라인 4단계의 서사 — 이름만이 아니라 "지금 무슨 일이 일어나는가"를 말한다. */
const STAGE_STORY = [
  { key: 'ingest', name: '정규화', desc: '보고서 JSON 을 블록 단위 표준 구조로 정리합니다' },
  { key: 'fragmentize', name: '조각화', desc: '문장·수치·목록을 근거 조각으로 잘라 신뢰도를 매깁니다' },
  { key: 'scenario', name: '시나리오', desc: '조각을 씬으로 배치하고 템플릿·길이를 정합니다' },
  { key: 'build', name: '빌드', desc: '씬 데이터를 렌더 패키지로 묶어 프리뷰를 만듭니다' },
];

function announce(text) {
  const el = $('live-status');
  if (el) el.textContent = text;
}

// ── 테마 토큰 주입 (hwax-blue.json → CSS 변수) ──────────────────────────────

(async function applyTheme() {
  try {
    const res = await fetch('api/web/tokens/hwax-blue.json');
    const theme = await res.json();
    const raw = theme.raw || {};
    const p = raw.palette || {};
    const x = raw.extra || {};
    const sh = raw.shadow || {};
    const map = {
      '--c-bg': p.bg, '--c-ink': p.ink, '--c-sub': p.sub, '--c-faint': p.faint,
      '--c-line': p.line, '--c-blue': p.blue, '--c-blue2': p.blue2,
      '--c-blue-soft': p.blueSoft, '--c-blue-border': p.blueBorder, '--c-card': p.card,
      '--c-red': p.red, '--c-red-soft': p.redSoft,
      '--c-green': p.green, '--c-green-soft': p.greenSoft,
      '--c-skel': p.skel, '--c-chat-gray': p.chatGray,
      '--c-white': x.white,
      // 그림자도 토큰 주입 경로에 태운다 — 브랜드 교체 시 잔영이 남지 않게
      '--shadow-card': sh.card, '--shadow-soft': sh.cardSoft,
    };
    const root = document.documentElement;
    for (const [k, v] of Object.entries(map)) if (v) root.style.setProperty(k, v);
    if (raw.font && raw.font.base) root.style.setProperty('--font-base', raw.font.base);
  } catch (_) { /* 폴백 CSS 변수로 동작 */ }
})();

// ── iframe 포커스 링 (AX-F11) ───────────────────────────────────────────────
// Tab 이 iframe 내부 문서로 들어가면 부모 문서에서 :focus/:focus-within 이 매칭되지
// 않는다(크로미엄 실측). 그 순간 부모 window 는 blur 되고 activeElement 가 iframe 으로
// 남는다 — 이 신호로 프레임 상자에 링 클래스를 단다.
window.addEventListener('blur', () => {
  const el = document.activeElement;
  if (el && el.tagName === 'IFRAME') {
    const box = el.closest('.frame-box');
    if (box) box.classList.add('has-focus');
  }
});
window.addEventListener('focus', () => {
  document.querySelectorAll('.frame-box.has-focus').forEach((b) => b.classList.remove('has-focus'));
});

// ── 헬스 표시 ────────────────────────────────────────────────────────────────

async function checkHealth() {
  const dot = $('health-dot');
  const text = $('health-text');
  try {
    const res = await fetch('api/health');
    const body = await res.json();
    const ok = body && body.status === 'ok';
    dot.className = 'health-dot ' + (ok ? 'ok' : 'bad');
    text.textContent = ok ? '서비스 정상' : '상태 이상 — 서버 로그를 확인하세요';
  } catch (_) {
    dot.className = 'health-dot bad';
    text.textContent = '연결 실패 — 서버가 떠 있는지 확인하세요';
  }
}
checkHealth();
setInterval(checkHealth, 30000);

// ── 탭 전환 (APG tabs 패턴) ─────────────────────────────────────────────────

const TAB_NAMES = ['create', 'history', 'modules', 'meetings'];
const LOADERS = { history: loadHistory, modules: loadModules, meetings: loadMeetings };

$('tabs').addEventListener('click', (e) => {
  const btn = e.target.closest('.tab');
  if (btn) switchTab(btn.dataset.tab);
});

$('tabs').addEventListener('keydown', (e) => {
  const idx = TAB_NAMES.indexOf(document.activeElement.dataset?.tab);
  if (idx < 0) return;
  let next = null;
  if (e.key === 'ArrowRight') next = (idx + 1) % TAB_NAMES.length;
  else if (e.key === 'ArrowLeft') next = (idx - 1 + TAB_NAMES.length) % TAB_NAMES.length;
  else if (e.key === 'Home') next = 0;
  else if (e.key === 'End') next = TAB_NAMES.length - 1;
  if (next === null) return;
  e.preventDefault();
  switchTab(TAB_NAMES[next]);
  $('tab-' + TAB_NAMES[next]).focus();
});

function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t) => {
    const on = t.dataset.tab === name;
    t.setAttribute('aria-selected', on ? 'true' : 'false');
    t.tabIndex = on ? 0 : -1;
    t.classList.toggle('active', on);
  });
  document.querySelectorAll('.panel').forEach((p) => {
    const on = p.id === 'panel-' + name;
    p.classList.toggle('active', on);
    p.hidden = !on;
  });
  if (LOADERS[name]) LOADERS[name]();
}

// ── ① 생성 탭 ───────────────────────────────────────────────────────────────

let currentRunId = null;
let pollTimer = null;
let runStartedAt = 0;
let lastSummary = null;   // 대화 수정 전후 델타 계산용
let sourceLabel = '';     // 접힌 소스 바에 남길 투입원

const panel = $('panel-create');
const setPhase = (p) => panel.setAttribute('data-phase', p);

// 예시 보고서 원클릭 투입 — 첫 사용자가 34KB JSON 을 구하러 나가지 않게
$('sample-btn').addEventListener('click', async () => {
  const btn = $('sample-btn');
  const errBox = $('create-error');
  btn.disabled = true;
  errBox.textContent = '';
  try {
    const res = await fetch('sample-report.json');
    if (!res.ok) throw new Error('HTTP ' + res.status);
    const text = await res.text();
    $('report-json').value = text;
    $('file-name').textContent = 'report_sample.json (예시)';
    if (!$('slug-input').value.trim()) $('slug-input').value = 'sample';
    sourceLabel = '예시 보고서 report_sample.json';
    announce('예시 보고서를 넣었습니다. 파이프라인 실행을 누르세요.');
  } catch (e) {
    errBox.textContent = '예시 보고서를 불러오지 못했습니다 (' + e.message
      + '). 직접 report_archive_draft_v1 JSON 을 붙여넣어 주세요.';
  } finally {
    btn.disabled = false;
  }
});

const fileInput = $('report-file');
fileInput.addEventListener('change', async () => {
  const f = fileInput.files[0];
  $('file-name').textContent = f ? f.name : '파일 선택…';
  if (!f) return;
  try {
    $('report-json').value = await f.text();
    sourceLabel = f.name + ' · ' + fmtBytes(f.size);
  } catch (e) {
    $('create-error').textContent = '파일을 읽지 못했습니다 (' + e.message
      + '). 다른 파일을 선택하거나 내용을 직접 붙여넣어 주세요.';
  }
});

$('run-btn').addEventListener('click', async () => {
  const errBox = $('create-error');
  errBox.textContent = '';
  const raw = $('report-json').value.trim();
  if (!raw) {
    errBox.textContent = '보고서 JSON 이 비어 있습니다. 파일을 선택하거나 '
      + '“예시 보고서 넣기”를 눌러 바로 시작하세요.';
    $('report-json').focus();
    return;
  }
  let report;
  try {
    report = JSON.parse(raw);
  } catch (e) {
    const pos = /position (\d+)/.exec(e.message);
    errBox.textContent = '보고서 JSON 형식이 아닙니다'
      + (pos ? ` (${Number(pos[1]) + 1}번째 글자 부근)` : '')
      + '. 보고서 전체를 붙여넣었는지 확인하거나, “예시 보고서 넣기”를 눌러 바로 시작하세요.';
    $('report-json').focus();
    return;
  }
  const slug = $('slug-input').value.trim() || undefined;
  if (!sourceLabel) sourceLabel = '붙여넣은 JSON · ' + fmtBytes(new Blob([raw]).size);
  const btn = $('run-btn');
  btn.disabled = true;
  try {
    const data = await api('api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_json: report, slug }),
    });
    openRun(data.run_id, sourceLabel);
  } catch (e) {
    errBox.textContent = '파이프라인을 시작하지 못했습니다: ' + e.message
      + '. 보고서가 report_archive_draft_v1 형식인지 확인 후 다시 실행하세요.';
  } finally {
    btn.disabled = false;
  }
});

$('reset-btn').addEventListener('click', () => {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
  currentRunId = null;
  lastSummary = null;
  sourceLabel = '';
  setPhase('idle');
  $('report-json').focus();
});

function openRun(runId, label) {
  currentRunId = runId;
  lastSummary = null;
  runStartedAt = Date.now();
  sourceLabel = label || sourceLabel || '';
  $('sb-name').textContent = sourceLabel ? sourceLabel.split(' · ')[0] : '보고서';
  $('sb-meta').textContent = sourceLabel.includes(' · ') ? sourceLabel.split(' · ').slice(1).join(' · ') : '';
  $('qa-result').hidden = true;
  $('run-error').textContent = '';
  $('preview-wrap').hidden = true;
  $('preview-frame').removeAttribute('src');
  $('rail-wrap').classList.remove('done');
  buildRail();
  renderRail(null);
  setPhase('running');
  switchTab('create');
  // 방금 누른 트리거(실행 버튼·이력 항목)가 국면 전환으로 사라진다 — 포커스를 실행 화면 머리로 옮긴다 (WCAG 2.4.3)
  $('source-bar').focus();
  loadChat(runId);
  if (pollTimer) clearInterval(pollTimer);
  refreshRun();
  pollTimer = setInterval(refreshRun, 1500);
}

async function refreshRun() {
  if (!currentRunId) return;
  let run;
  try {
    run = await api('api/runs/' + encodeURIComponent(currentRunId));
  } catch (e) {
    // 조회 실패(유령 id 등) — 이전 실행의 잔상을 지우고 폴링을 멈춘다
    $('run-error').textContent = '실행 정보를 불러오지 못했습니다: ' + e.message
      + '. 실행 이력 탭에서 다시 선택하거나 새 보고서를 투입하세요.';
    $('run-status').textContent = '조회 실패';
    $('run-status').className = 'badge s-failed';
    $('run-downloads').innerHTML = '';
    $('run-summary').hidden = true;
    $('run-actions').hidden = true;
    $('preview-wrap').hidden = true;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    return;
  }
  renderRunDetail(run);
  const render = run.render || {};
  const settled = (run.status === 'done' || run.status === 'failed')
    && !['queued', 'rendering'].includes(render.status || '');
  if (settled && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

/** 단계 레일 — 순번·이름·한 줄 설명·상태·완료 체크·현재 강조 6요소 (UIP-2).
 *  골격은 한 번만 만들고 이후엔 상태만 갱신한다 — 폴링마다 innerHTML 을 갈면
 *  진입 애니메이션이 1.5초마다 재시작해 레일 전체가 깜빡인다(진입 1회 규칙). */
function buildRail() {
  $('run-stages').innerHTML = STAGE_STORY.map((st, i) => `
      <li class="st-pending" data-stage="${esc(st.key)}">
        <div class="st-top">
          <span class="st-no" aria-hidden="true">${i + 1}</span>
          <span class="st-name">${esc(st.name)}</span>
          <span class="st-state">대기</span>
        </div>
        <span class="st-desc">${esc(st.desc)}</span>
      </li>`).join('');
}

function renderRail(stages) {
  const byKey = {};
  for (const s of stages || []) byKey[s.stage] = s;
  STAGE_STORY.forEach((st, i) => {
    const li = $('run-stages').querySelector(`[data-stage="${st.key}"]`);
    if (!li) return;
    const state = (byKey[st.key] || {}).status || 'pending';
    const cls = 'st-' + state;
    if (li.className !== cls) li.className = cls;
    const mark = state === 'done' ? '✓' : (state === 'failed' ? '!' : String(i + 1));
    const noEl = li.querySelector('.st-no');
    if (noEl.textContent !== mark) noEl.textContent = mark;
    const stEl = li.querySelector('.st-state');
    const label = ko(state);
    if (stEl.textContent !== label) stEl.textContent = label;
  });
}

function renderRunDetail(run) {
  const stages = run.stages || [];
  renderRail(stages);

  // 이력에서 연 실행은 투입원 문자열이 없다 — 슬러그·id 로 소스 바를 채운다
  if (!sourceLabel) {
    $('sb-name').textContent = run.slug;
    $('sb-meta').textContent = run.run_id + ' · ' + fmtTime(run.created_at);
  }

  const st = $('run-status');
  st.textContent = ko(run.status);
  st.className = 'badge s-' + run.status;

  const doneCount = stages.filter((s) => s.status === 'done').length;
  const cur = stages.find((s) => s.status === 'running');
  const elapsed = ((Date.now() - runStartedAt) / 1000).toFixed(1);
  // 서사(단계 전이)만 라이브 리전에 싣는다 — 경과 타이머는 눈으로만 보이는 별도 칸 (AX-live)
  let noteMsg = '';
  let noteTimer = '';
  if (run.status === 'running' || run.status === 'queued') {
    const story = STAGE_STORY.find((s) => cur && s.key === cur.stage);
    noteMsg = `4단계 중 ${doneCount}단계 완료` + (story ? ` · 지금: ${story.name}` : '');
    noteTimer = ` · ${elapsed}초 경과`;
  } else if (run.status === 'done') {
    noteMsg = '4단계 모두 완료 · 아래에서 완성본을 확인하고 대화로 수정하세요';
  } else if (run.status === 'failed') {
    noteMsg = `${doneCount}단계까지 진행 후 중단됐습니다`;
  }
  const noteMsgEl = $('rail-note-msg');
  // 같은 문자열 재대입도 스크린리더 재낭독을 유발한다 — 바뀐 때만 쓴다
  if (noteMsgEl.textContent !== noteMsg) noteMsgEl.textContent = noteMsg;
  const noteTimerEl = $('rail-note-timer');
  if (noteTimerEl.textContent !== noteTimer) noteTimerEl.textContent = noteTimer;
  // 서사가 끝나면 레일은 영수증으로 축약한다 — 프리뷰에 세로 공간을 넘긴다
  $('rail-wrap').classList.toggle('done', run.status === 'done');

  const sum = run.scenario_summary;
  const sumBox = $('run-summary');
  if (sum) {
    sumBox.hidden = false;
    $('sum-scenes').textContent = sum.scene_count;
    $('sum-dur').textContent = sum.total_dur;
    $('sum-core').textContent = sum.core_message || '–';
    // 수정 결과를 화면에 남긴다 — 무엇이 몇 초 바뀌었는지 (UIP-6)
    const delta = $('sum-delta');
    if (lastSummary && lastSummary.total_dur !== sum.total_dur) {
      delta.hidden = false;
      delta.textContent = `${lastSummary.total_dur}초 → ${sum.total_dur}초`;
    }
    lastSummary = sum;
  } else {
    sumBox.hidden = true;
  }

  if (run.error) {
    $('run-error').textContent = '파이프라인이 중단됐습니다: ' + run.error
      + '. 보고서 내용을 확인한 뒤 “다른 보고서 투입”으로 다시 시도하세요.';
  } else {
    $('run-error').textContent = '';
  }

  const built = run.status === 'done' && run.build_dir && run.entry;
  $('run-actions').hidden = !built;

  const render = run.render || {};
  const note = $('render-status');
  if (render.status) {
    note.textContent = '렌더 ' + ko(render.status)
      + (render.error ? ' — ' + render.error + ' (렌더 로그를 확인하세요)' : '');
  } else {
    note.textContent = '';
  }
  $('render-btn').disabled = ['queued', 'rendering'].includes(render.status || '');

  if (built) {
    const wrap = $('preview-wrap');
    const frame = $('preview-frame');
    const src = 'api/runs/' + encodeURIComponent(run.run_id) + '/preview/' + run.entry;
    if (wrap.hidden || (frame.getAttribute('src') || '').split('?')[0] !== src) {
      wrap.hidden = false;
      frame.src = src;
      announce('빌드가 완료됐습니다. 프리뷰와 대화 패널을 사용할 수 있습니다.');
    }
    setPhase('done');
    refreshDownloads(run.run_id);
  } else {
    $('run-downloads').innerHTML = '';
  }
}

async function refreshDownloads(runId) {
  try {
    const arts = await api('api/runs/' + encodeURIComponent(runId) + '/artifacts');
    const box = $('run-downloads');
    const base = 'api/runs/' + encodeURIComponent(runId) + '/download/';
    const links = [];
    const add = (kind, label) => {
      const a = arts[kind];
      if (a && a.exists) links.push(`<a href="${base}${kind}">${label} 내려받기 (${fmtBytes(a.size)})</a>`);
    };
    add('mp4', '영상 mp4');
    add('pptx', '슬라이드 pptx');
    add('scenario', '시나리오 json');
    box.innerHTML = links.join('');
  } catch (_) { /* 다운로드 목록은 부가 정보 */ }
}

$('render-btn').addEventListener('click', async () => {
  if (!currentRunId) return;
  const btn = $('render-btn');
  btn.disabled = true;
  $('render-status').textContent = '렌더를 요청하는 중…';
  try {
    await api('api/runs/' + encodeURIComponent(currentRunId) + '/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targets: ['video', 'pptx'] }),
    });
    announce('렌더를 시작했습니다.');
    if (!pollTimer) pollTimer = setInterval(refreshRun, 1500);
  } catch (e) {
    $('run-error').textContent = '렌더를 시작하지 못했습니다: ' + e.message
      + '. 빌드가 끝난 뒤 다시 시도하세요.';
    btn.disabled = false;
  }
});

$('qa-btn').addEventListener('click', async () => {
  if (!currentRunId) return;
  const btn = $('qa-btn');
  const box = $('qa-result');
  btn.disabled = true;
  box.hidden = false;
  box.className = 'qa-result';
  box.textContent = 'QA 게이트 실행 중… 런타임 게이트를 포함해 수십 초 걸릴 수 있습니다.';
  announce('QA 게이트를 실행합니다.');
  try {
    const result = await api('api/runs/' + encodeURIComponent(currentRunId) + '/qa', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    box.className = 'qa-result ' + (result.passed ? 'pass' : 'fail');
    const rows = (result.results || [])
      .filter((r) => r.severity !== 'info')
      .slice(0, 30)
      .map((r) => `[${esc(r.severity)}] gate${esc(r.gate)} ${esc(r.rule)}${r.scene ? ' @' + esc(r.scene) : ''} — ${esc(r.detail)}`);
    box.innerHTML = `<b>${result.passed ? 'QA 통과' : 'QA 실패'}</b>`
      + (rows.length ? '<br>' + rows.join('<br>') : '<br>지적 사항 없음');
    announce(result.passed ? 'QA 게이트를 통과했습니다.' : 'QA 게이트에서 지적이 나왔습니다.');
  } catch (e) {
    box.className = 'qa-result fail';
    box.textContent = 'QA 게이트를 실행하지 못했습니다: ' + e.message
      + '. 빌드 산출물이 남아 있는지 확인한 뒤 다시 시도하세요.';
  } finally {
    btn.disabled = false;
  }
});

// ── 대화형 제작 패널 ────────────────────────────────────────────────────────

let chatRunId = null;

const CHAT_SUGGESTIONS = [
  '오프닝을 7초로 줄여줘',
  '절차 씬 길이를 14초로',
  '전체를 80초 안에 맞춰줘',
  'QA 게이트 돌려줘',
];

function renderSuggestions() {
  $('chat-suggest').innerHTML = CHAT_SUGGESTIONS
    .map((s) => `<button type="button" data-suggest="${esc(s)}">${esc(s)}</button>`).join('');
}
renderSuggestions();

$('chat-suggest').addEventListener('click', (e) => {
  const b = e.target.closest('[data-suggest]');
  if (!b) return;
  $('chat-input').value = b.dataset.suggest;
  $('chat-input').focus();
});

function appendChatMsg(msg) {
  const box = $('chat-messages');
  const div = document.createElement('div');
  div.className = 'chat-msg ' + (msg.role === 'user' ? 'user' : 'assistant')
    + (msg.pending ? ' pending' : '');
  div.textContent = msg.content;
  box.appendChild(div);
  const badges = (msg.actions || []).map((b) => `<span class="chat-badge">${esc(b)}</span>`);
  if (msg.rebuilt) badges.push('<span class="chat-badge rebuilt">재빌드 완료</span>');
  if (msg.role !== 'user' && badges.length) {
    box.insertAdjacentHTML('beforeend', `<div class="chat-actions">${badges.join('')}</div>`);
  }
  box.scrollTop = box.scrollHeight;
  return div;
}

function chatEmptyHint() {
  $('chat-messages').innerHTML =
    '<p class="chat-empty">완성본을 보면서 고칠 곳을 말하세요. 씬 길이·문안·템플릿을 바꾸면 '
    + '자동으로 다시 빌드하고 프리뷰에 반영합니다.</p>';
}

async function loadChat(runId) {
  chatRunId = runId;
  $('chat-messages').innerHTML = '';
  $('chat-error').textContent = '';
  try {
    const data = await api('api/runs/' + encodeURIComponent(runId) + '/chat');
    const items = data.chat || [];
    if (!items.length) { chatEmptyHint(); return; }
    for (const m of items) appendChatMsg(m);
  } catch (_) { chatEmptyHint(); /* 이력은 부가 정보 */ }
}

/** 재빌드 반영 — 흰 플래시를 덮개로 감싸 의도된 전환으로 만든다 (MO-F17). */
function reloadPreview() {
  const frame = $('preview-frame');
  const cover = $('frame-cover');
  const src = frame.getAttribute('src');
  if (!src) return;
  cover.hidden = false;
  cover.classList.remove('fading');
  const onLoad = () => {
    frame.removeEventListener('load', onLoad);
    cover.classList.add('fading');
    setTimeout(() => { cover.hidden = true; }, 320);
  };
  frame.addEventListener('load', onLoad);
  frame.src = src.split('?')[0] + '?v=' + Date.now();
}

async function sendChat() {
  const input = $('chat-input');
  const text = input.value.trim();
  if (!text || !chatRunId) return;
  const btn = $('chat-send');
  const errBox = $('chat-error');
  errBox.textContent = '';
  const empty = document.querySelector('#chat-messages .chat-empty');
  if (empty) empty.remove();
  appendChatMsg({ role: 'user', content: text });
  const pending = appendChatMsg({ role: 'assistant', content: '생각 중…', pending: true });
  input.value = '';
  input.disabled = true; btn.disabled = true;
  announce('수정 요청을 보냈습니다. 응답을 기다리는 중입니다.');
  try {
    const data = await api('api/runs/' + encodeURIComponent(chatRunId) + '/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    pending.remove();
    appendChatMsg({
      role: 'assistant',
      content: data.reply || '(응답 없음)',
      actions: data.applied || [],
      rebuilt: !!data.rebuilt,
    });
    if (data.rebuilt) {
      reloadPreview();
      // 요약이 옛 값을 그대로 들고 있지 않게 원장을 다시 읽는다 (TY-F24)
      refreshRun();
    }
    announce('수정 응답이 도착했습니다.');
  } catch (e) {
    pending.remove();
    errBox.textContent = '수정을 반영하지 못했습니다: ' + e.message
      + '. 잠시 후 다시 요청하거나 문장을 더 구체적으로 적어보세요.';
  } finally {
    input.disabled = false; btn.disabled = false; input.focus();
  }
}

$('chat-send').addEventListener('click', sendChat);
$('chat-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.isComposing) sendChat();
});

// ── ② 실행 이력 탭 ──────────────────────────────────────────────────────────

async function loadHistory() {
  const box = $('history-list');
  box.innerHTML = '<p class="empty">불러오는 중…</p>';
  try {
    const data = await api('api/runs');
    const items = data.runs || [];
    const nDone = items.filter((r) => r.status === 'done').length;
    const nFail = items.filter((r) => r.status === 'failed').length;
    $('history-meta').innerHTML =
      `<span class="stat-strip"><span><b>${items.length}</b><span>건</span></span>`
      + `<span><b>${nDone}</b><span>완료</span></span>`
      + `<span><b>${nFail}</b><span>실패</span></span></span>`;
    if (!items.length) {
      box.innerHTML = '<p class="empty">아직 실행한 보고서가 없습니다. '
        + '생성 탭에서 “예시 보고서 넣기”로 첫 실행을 시작해 보세요.</p>';
      return;
    }
    box.innerHTML = items.map((r) => {
      const s = r.scenario_summary;
      const rd = r.render && r.render.status ? ko(r.render.status) : '–';
      return `
      <button class="list-item" type="button" data-open="${esc(r.run_id)}">
        <span class="li-main">
          <span class="li-title">${esc(r.slug)} <span class="badge s-${esc(r.status)}">${esc(ko(r.status))}</span></span>
          <span class="li-sub">${esc(fmtTime(r.created_at))} · ${esc(r.run_id)}${r.error ? ' · ' + esc(String(r.error).slice(0, 60)) : ''}</span>
        </span>
        <span class="li-stats">
          <span class="li-stat"><b>${s ? esc(s.scene_count) : '–'}</b><span>씬</span></span>
          <span class="li-stat"><b>${s ? esc(s.total_dur) : '–'}</b><span>초</span></span>
          <span class="li-stat"><b>${esc(rd)}</b><span>렌더</span></span>
        </span>
        <span class="li-go" aria-hidden="true">열기 →</span>
      </button>`;
    }).join('');
  } catch (e) {
    box.innerHTML = `<p class="empty">실행 이력을 불러오지 못했습니다: ${esc(e.message)}. `
      + `새로고침을 누르거나 서버 상태를 확인하세요.</p>`;
  }
}

$('history-list').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-open]');
  if (btn) openRun(btn.dataset.open, '');
});
$('history-refresh').addEventListener('click', loadHistory);

// ── ③ 모듈 갤러리 탭 ────────────────────────────────────────────────────────

let modulesCache = null;
let moduleFilter = 'scene-template';

const TYPE_KO = { 'scene-template': '씬 템플릿', metaphor: '시각 은유', theme: '테마' };

async function loadModules() {
  if (modulesCache) { renderModules(); return; }
  const grid = $('modules-grid');
  grid.innerHTML = '<p class="empty">불러오는 중…</p>';
  try {
    const registry = await api('api/modules');
    modulesCache = registry;
    renderModules();
  } catch (e) {
    grid.innerHTML = `<p class="empty">모듈 목록을 불러오지 못했습니다: ${esc(e.message)}. `
      + `modules/registry.yaml 이 있는지 확인하세요.</p>`;
  }
}

function renderModules() {
  const registry = modulesCache || {};
  const all = registry.modules || [];
  const types = [...new Set(all.map((m) => m.type))];
  $('modules-meta').textContent =
    `registry v${registry.version || '?'} · 총 ${all.length}종 · 갱신 ${registry.updated || '–'}`;
  $('module-filters').innerHTML = [['all', '전체']].concat(
    types.map((t) => [t, `${TYPE_KO[t] || t} ${all.filter((m) => m.type === t).length}`]),
  ).map(([k, label]) =>
    `<button type="button" data-filter="${esc(k)}" aria-pressed="${k === moduleFilter}">${esc(label)}</button>`,
  ).join('');

  const shown = moduleFilter === 'all' ? all : all.filter((m) => m.type === moduleFilter);
  $('modules-grid').innerHTML = shown.map((m) => `
    <article class="module-card">
      <div class="m-head">
        <span class="m-id">${esc(m.id)}</span>
        <span class="badge s-${esc(m.status || 'draft')}">${esc(ko(m.status))}</span>
      </div>
      <p class="m-summary">${esc(m.summary || '')}</p>
      <p class="m-use"><b>쓰는 곳</b><br>${esc(m.in_scope_hint || '용도 미기재')}</p>
      <p class="m-meta">
        <span>${esc(TYPE_KO[m.type] || m.type || '')}</span>
        <span>v${esc(m.version || '')}</span>
        ${m.nat_default ? `<span>기본 ${esc(m.nat_default)}초</span>` : ''}
      </p>
      <button class="btn" type="button" data-preview="${esc(m.id)}">프리뷰 보기</button>
    </article>`).join('');
}

$('module-filters').addEventListener('click', (e) => {
  const b = e.target.closest('[data-filter]');
  if (!b) return;
  moduleFilter = b.dataset.filter;
  renderModules();
});

$('modules-grid').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-preview]');
  if (!btn) return;
  const id = btn.dataset.preview;
  const wrap = $('module-preview-wrap');
  wrap.hidden = false;
  $('module-preview-title').textContent = '모듈 프리뷰 — ' + id;
  $('module-preview-frame').src =
    'api/modules/' + encodeURIComponent(id) + '/preview/preview.html';
  wrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  announce(id + ' 프리뷰를 열었습니다.');
});

$('module-preview-close').addEventListener('click', () => {
  $('module-preview-wrap').hidden = true;
  $('module-preview-frame').removeAttribute('src');
});

// ── ④ 회의록 탭 ─────────────────────────────────────────────────────────────

/** 회의록 마크다운 경량 렌더 — 제목·표·목록·강조만. 입력은 전부 이스케이프 후 처리한다. */
function renderMarkdown(md) {
  const inline = (s) => esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  const lines = String(md).split('\n');
  const out = [];
  let i = 0;
  let inList = false;
  const closeList = () => { if (inList) { out.push('</ul>'); inList = false; } };
  while (i < lines.length) {
    const line = lines[i];
    const t = line.trim();
    if (!t) { closeList(); i++; continue; }
    if (/^\|.*\|$/.test(t) && /^\|[\s:|-]+\|$/.test((lines[i + 1] || '').trim())) {
      closeList();
      const cells = (row) => row.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());
      const head = cells(t);
      i += 2;
      const body = [];
      while (i < lines.length && /^\|.*\|$/.test(lines[i].trim())) { body.push(cells(lines[i])); i++; }
      out.push('<table><thead><tr>'
        + head.map((c) => `<th>${inline(c)}</th>`).join('')
        + '</tr></thead><tbody>'
        + body.map((r) => '<tr>' + r.map((c) => `<td>${inline(c)}</td>`).join('') + '</tr>').join('')
        + '</tbody></table>');
      continue;
    }
    const h = /^(#{1,3})\s+(.*)$/.exec(t);
    if (h) { closeList(); out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); i++; continue; }
    if (/^([-*])\s+/.test(t)) {
      if (!inList) { out.push('<ul>'); inList = true; }
      out.push(`<li>${inline(t.replace(/^([-*])\s+/, ''))}</li>`);
      i++; continue;
    }
    if (/^-{3,}$/.test(t)) { closeList(); out.push('<hr>'); i++; continue; }
    closeList();
    out.push(`<p>${inline(t)}</p>`);
    i++;
  }
  closeList();
  return out.join('');
}

let meetingsCache = [];

async function loadMeetings() {
  const box = $('meetings-list');
  box.innerHTML = '<p class="empty">불러오는 중…</p>';
  try {
    const data = await api('api/meetings');
    const items = data.meetings || [];
    meetingsCache = items;
    const nClosed = items.filter((m) => m.status === 'closed').length;
    $('meetings-meta').textContent = `${items.length}건 · 폐회 ${nClosed}건 · 진행 중 ${items.length - nClosed}건`;
    if (!items.length) {
      box.innerHTML = '<p class="empty">저장된 회의가 없습니다. '
        + '심의를 실행하면 회의록이 여기에 쌓입니다.</p>';
      return;
    }
    box.innerHTML = items.map((m) => `
      <button class="list-item" type="button" data-meeting="${esc(m.id)}">
        <span class="li-main">
          <span class="li-title">${esc(m.topic)} <span class="badge s-${esc(m.status)}">${esc(ko(m.status))}</span></span>
          <span class="li-sub">${esc(MEETING_TYPE_KO[m.type] || m.type)} · 참가 ${(m.participants || []).length}인 · ${esc(fmtTime(m.created_at))}</span>
        </span>
      </button>`).join('');
  } catch (e) {
    box.innerHTML = `<p class="empty">회의 목록을 불러오지 못했습니다: ${esc(e.message)}. `
      + `새로고침을 누르거나 data/meetings 경로를 확인하세요.</p>`;
  }
}

$('meetings-list').addEventListener('click', async (e) => {
  const item = e.target.closest('[data-meeting]');
  if (!item) return;
  document.querySelectorAll('#meetings-list .list-item')
    .forEach((el) => el.setAttribute('aria-current', el === item ? 'true' : 'false'));
  const id = item.dataset.meeting;
  const meta = meetingsCache.find((m) => m.id === id) || {};
  const body = $('minutes-body');
  // 진행 중 회의는 minutes.md 가 아직 없다 — 404 를 오류로 옮기지 않고 상태로 안내한다
  if (meta.status && meta.status !== 'closed') {
    body.innerHTML = '<div class="minutes-notice"><b>아직 진행 중인 회의입니다.</b>'
      + '<span>회의가 폐회되면 회의록(minutes.md)이 생성되어 여기에 표시됩니다. '
      + '지금은 라운드가 진행 중이라 확정된 결론이 없습니다.</span></div>';
    return;
  }
  body.innerHTML = '<p class="empty">불러오는 중…</p>';
  try {
    const data = await api('api/meetings/' + encodeURIComponent(id) + '/minutes');
    body.innerHTML = renderMarkdown(data.markdown);
    body.scrollTop = 0;
  } catch (err) {
    body.innerHTML = `<div class="minutes-notice"><b>회의록을 불러오지 못했습니다.</b>`
      + `<span>${esc(err.message)} — 회의가 폐회됐는지 확인한 뒤 새로고침하세요.</span></div>`;
  }
});

$('meetings-refresh').addEventListener('click', loadMeetings);
