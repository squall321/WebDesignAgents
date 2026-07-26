// WebDesignAgents 콘솔 SPA 로직 — 상대경로 api/* fetch(서브패스 프록시 대응), hwax-blue 토큰 주입
'use strict';

// ── 공통 유틸 ────────────────────────────────────────────────────────────────

function esc(s) {
  return String(s == null ? '' : s)
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#39;');
}

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

const STAGE_KO = { ingest: '정규화', fragmentize: '조각화', scenario: '시나리오', build: '빌드' };
const STATUS_KO = {
  queued: '대기', running: '실행 중', done: '완료', failed: '실패', rendering: '렌더 중',
};

// ── 테마 토큰 주입 (hwax-blue.json → CSS 변수) ──────────────────────────────

(async function applyTheme() {
  try {
    const res = await fetch('api/web/tokens/hwax-blue.json');
    const theme = await res.json();
    const p = (theme.raw && theme.raw.palette) || {};
    const map = {
      '--c-bg': p.bg, '--c-ink': p.ink, '--c-sub': p.sub, '--c-faint': p.faint,
      '--c-line': p.line, '--c-blue': p.blue, '--c-blue2': p.blue2,
      '--c-blue-soft': p.blueSoft, '--c-blue-border': p.blueBorder, '--c-card': p.card,
      '--c-red': p.red, '--c-red-soft': p.redSoft,
      '--c-green': p.green, '--c-green-soft': p.greenSoft,
    };
    const root = document.documentElement;
    for (const [k, v] of Object.entries(map)) if (v) root.style.setProperty(k, v);
    if (theme.raw && theme.raw.font && theme.raw.font.base) {
      root.style.setProperty('--font-base', theme.raw.font.base);
    }
  } catch (_) { /* 폴백 CSS 변수로 동작 */ }
})();

// ── 헬스 표시 ────────────────────────────────────────────────────────────────

async function checkHealth() {
  const dot = document.getElementById('health-dot');
  const text = document.getElementById('health-text');
  try {
    const res = await fetch('api/health');
    const body = await res.json();
    const ok = body && body.status === 'ok';
    dot.className = 'health-dot ' + (ok ? 'ok' : 'bad');
    text.textContent = ok ? '서비스 정상' : '상태 이상';
  } catch (_) {
    dot.className = 'health-dot bad';
    text.textContent = '연결 실패';
  }
}
checkHealth();
setInterval(checkHealth, 30000);

// ── 탭 전환 ─────────────────────────────────────────────────────────────────

const LOADERS = { history: loadHistory, modules: loadModules, meetings: loadMeetings };

document.getElementById('tabs').addEventListener('click', (e) => {
  const btn = e.target.closest('.tab');
  if (!btn) return;
  switchTab(btn.dataset.tab);
});

function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.panel').forEach((p) => p.classList.toggle('active', p.id === 'panel-' + name));
  if (LOADERS[name]) LOADERS[name]();
}

// ── ① 생성 탭 ───────────────────────────────────────────────────────────────

let currentRunId = null;
let pollTimer = null;

const fileInput = document.getElementById('report-file');
fileInput.addEventListener('change', async () => {
  const f = fileInput.files[0];
  document.getElementById('file-name').textContent = f ? f.name : '파일 선택…';
  if (f) {
    try { document.getElementById('report-json').value = await f.text(); } catch (_) { /* 무시 */ }
  }
});

document.getElementById('run-btn').addEventListener('click', async () => {
  const errBox = document.getElementById('create-error');
  errBox.textContent = '';
  const raw = document.getElementById('report-json').value.trim();
  if (!raw) { errBox.textContent = '보고서 JSON 을 입력하세요.'; return; }
  let report;
  try { report = JSON.parse(raw); } catch (e) { errBox.textContent = 'JSON 파싱 실패: ' + e.message; return; }
  const slug = document.getElementById('slug-input').value.trim() || undefined;
  const btn = document.getElementById('run-btn');
  btn.disabled = true;
  try {
    const data = await api('api/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ report_json: report, slug }),
    });
    openRun(data.run_id);
  } catch (e) {
    errBox.textContent = '실행 실패: ' + e.message;
  } finally {
    btn.disabled = false;
  }
});

function openRun(runId) {
  currentRunId = runId;
  document.getElementById('run-detail').hidden = false;
  document.getElementById('qa-result').hidden = true;
  document.getElementById('preview-wrap').hidden = true;
  document.getElementById('preview-frame').removeAttribute('src');
  switchTab('create');
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
    document.getElementById('run-error').textContent = e.message;
    document.getElementById('run-status').textContent = '조회 실패';
    document.getElementById('run-downloads').innerHTML = '';
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    return;
  }
  renderRunDetail(run);
  const render = run.render || {};
  const settled = (run.status === 'done' || run.status === 'failed')
    && !['queued', 'rendering'].includes(render.status || '');
  if (settled && pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function renderRunDetail(run) {
  document.getElementById('run-title').textContent = run.slug + ' (' + run.run_id + ')';
  const st = document.getElementById('run-status');
  st.textContent = STATUS_KO[run.status] || run.status;
  st.className = 'badge ' + run.status;

  document.getElementById('run-stages').innerHTML = (run.stages || []).map((s) => `
    <li class="st-${esc(s.status)}">
      <span class="st-name">${esc(STAGE_KO[s.stage] || s.stage)}</span>
      ${esc(STATUS_KO[s.status] || s.status)}
    </li>`).join('');

  const sumBox = document.getElementById('run-summary');
  if (run.scenario_summary) {
    const s = run.scenario_summary;
    sumBox.hidden = false;
    sumBox.innerHTML =
      `<span>씬 <b>${esc(s.scene_count)}</b>개</span>` +
      `<span>총 <b>${esc(s.total_dur)}</b>초</span>` +
      `<span>핵심 메시지: <b>${esc(s.core_message)}</b></span>`;
  } else {
    sumBox.hidden = true;
  }

  document.getElementById('run-error').textContent = run.error ? '오류: ' + run.error : '';

  const built = run.status === 'done' && run.build_dir && run.entry;
  document.getElementById('run-actions').hidden = !built;

  const render = run.render || {};
  const note = document.getElementById('render-status');
  if (render.status) {
    note.textContent = '렌더: ' + (STATUS_KO[render.status] || render.status)
      + (render.error ? ' — ' + render.error : '');
  } else {
    note.textContent = '';
  }
  document.getElementById('render-btn').disabled = ['queued', 'rendering'].includes(render.status || '');

  if (built) {
    const wrap = document.getElementById('preview-wrap');
    const frame = document.getElementById('preview-frame');
    const src = 'api/runs/' + encodeURIComponent(run.run_id) + '/preview/' + run.entry;
    if (wrap.hidden || frame.getAttribute('src') !== src) {
      wrap.hidden = false;
      frame.src = src;
    }
    refreshDownloads(run.run_id);
  } else {
    document.getElementById('run-downloads').innerHTML = '';
  }
}

async function refreshDownloads(runId) {
  try {
    const arts = await api('api/runs/' + encodeURIComponent(runId) + '/artifacts');
    const box = document.getElementById('run-downloads');
    const links = [];
    const base = 'api/runs/' + encodeURIComponent(runId) + '/download/';
    if (arts.mp4 && arts.mp4.exists) links.push(`<a href="${base}mp4">mp4 다운로드 (${fmtBytes(arts.mp4.size)})</a>`);
    if (arts.pptx && arts.pptx.exists) links.push(`<a href="${base}pptx">pptx 다운로드 (${fmtBytes(arts.pptx.size)})</a>`);
    if (arts.scenario && arts.scenario.exists) links.push(`<a href="${base}scenario">scenario.json (${fmtBytes(arts.scenario.size)})</a>`);
    box.innerHTML = links.join('');
  } catch (_) { /* 다운로드 목록은 부가 정보 */ }
}

document.getElementById('render-btn').addEventListener('click', async () => {
  if (!currentRunId) return;
  const btn = document.getElementById('render-btn');
  btn.disabled = true;
  try {
    await api('api/runs/' + encodeURIComponent(currentRunId) + '/render', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ targets: ['video', 'pptx'] }),
    });
    if (!pollTimer) pollTimer = setInterval(refreshRun, 1500);
  } catch (e) {
    document.getElementById('run-error').textContent = '렌더 요청 실패: ' + e.message;
    btn.disabled = false;
  }
});

document.getElementById('qa-btn').addEventListener('click', async () => {
  if (!currentRunId) return;
  const btn = document.getElementById('qa-btn');
  const box = document.getElementById('qa-result');
  btn.disabled = true;
  box.hidden = false;
  box.className = 'qa-result';
  box.textContent = 'QA 게이트 실행 중… (런타임 게이트 포함, 수십 초 걸릴 수 있습니다)';
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
  } catch (e) {
    box.className = 'qa-result fail';
    box.textContent = 'QA 실행 실패: ' + e.message;
  } finally {
    btn.disabled = false;
  }
});

// ── ② 실행 이력 탭 ──────────────────────────────────────────────────────────

async function loadHistory() {
  const box = document.getElementById('history-list');
  box.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    const data = await api('api/runs');
    const items = data.runs || [];
    if (!items.length) { box.innerHTML = '<div class="empty">실행 이력이 없습니다.</div>'; return; }
    box.innerHTML = items.map((r) => {
      const s = r.scenario_summary;
      return `
      <div class="list-item">
        <div class="li-main">
          <div class="li-title">${esc(r.slug)} <span class="badge ${esc(r.status)}">${esc(STATUS_KO[r.status] || r.status)}</span></div>
          <div class="li-sub">${esc(r.run_id)} · ${esc(fmtTime(r.created_at))}${s ? ` · 씬 ${esc(s.scene_count)}개 · ${esc(s.total_dur)}초` : ''}${r.render && r.render.status ? ` · 렌더 ${esc(STATUS_KO[r.render.status] || r.render.status)}` : ''}</div>
        </div>
        <button class="btn" data-open="${esc(r.run_id)}">열기</button>
      </div>`;
    }).join('');
  } catch (e) {
    box.innerHTML = `<div class="empty">이력 조회 실패: ${esc(e.message)}</div>`;
  }
}

document.getElementById('history-list').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-open]');
  if (btn) openRun(btn.dataset.open);
});
document.getElementById('history-refresh').addEventListener('click', loadHistory);

// ── ③ 모듈 갤러리 탭 ────────────────────────────────────────────────────────

let modulesLoaded = false;

async function loadModules() {
  if (modulesLoaded) return;
  const grid = document.getElementById('modules-grid');
  grid.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    const registry = await api('api/modules');
    const modules = registry.modules || [];
    document.getElementById('modules-meta').textContent =
      `registry v${registry.version || '?'} · ${modules.length}개 모듈 · ${registry.updated || ''}`;
    grid.innerHTML = modules.map((m) => `
      <div class="module-card">
        <div class="m-head">
          <span class="m-id">${esc(m.id)}</span>
          <span class="badge">${esc(m.status || '')}</span>
        </div>
        <div class="m-summary">${esc(m.summary || '')}</div>
        <div class="m-meta">${esc(m.type || '')} · v${esc(m.version || '')}${m.nat_default ? ` · 기본 ${esc(m.nat_default)}초` : ''}</div>
        <div><button class="btn" data-preview="${esc(m.id)}">프리뷰 열기</button></div>
      </div>`).join('');
    modulesLoaded = true;
  } catch (e) {
    grid.innerHTML = `<div class="empty">모듈 조회 실패: ${esc(e.message)}</div>`;
  }
}

document.getElementById('modules-grid').addEventListener('click', (e) => {
  const btn = e.target.closest('[data-preview]');
  if (!btn) return;
  const id = btn.dataset.preview;
  const wrap = document.getElementById('module-preview-wrap');
  wrap.hidden = false;
  document.getElementById('module-preview-title').textContent = '모듈 프리뷰 — ' + id;
  document.getElementById('module-preview-frame').src =
    'api/modules/' + encodeURIComponent(id) + '/preview/preview.html';
  wrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
});

// ── ④ 회의록 탭 ─────────────────────────────────────────────────────────────

async function loadMeetings() {
  const box = document.getElementById('meetings-list');
  box.innerHTML = '<div class="empty">불러오는 중…</div>';
  try {
    const data = await api('api/meetings');
    const items = data.meetings || [];
    if (!items.length) { box.innerHTML = '<div class="empty">저장된 회의가 없습니다.</div>'; return; }
    box.innerHTML = items.map((m) => `
      <div class="list-item selectable" data-meeting="${esc(m.id)}" data-topic="${esc(m.topic)}">
        <div class="li-main">
          <div class="li-title">${esc(m.topic)} <span class="badge ${m.status === 'closed' ? 'done' : ''}">${esc(m.status)}</span></div>
          <div class="li-sub">${esc(m.type)} · 참가 ${((m.participants || []).length)}인 · ${esc(fmtTime(m.created_at))}</div>
        </div>
      </div>`).join('');
  } catch (e) {
    box.innerHTML = `<div class="empty">회의 조회 실패: ${esc(e.message)}</div>`;
  }
}

document.getElementById('meetings-list').addEventListener('click', async (e) => {
  const item = e.target.closest('[data-meeting]');
  if (!item) return;
  const title = document.getElementById('minutes-title');
  const body = document.getElementById('minutes-body');
  title.textContent = '회의록 — ' + item.dataset.topic;
  body.textContent = '불러오는 중…';
  try {
    const data = await api('api/meetings/' + encodeURIComponent(item.dataset.meeting) + '/minutes');
    body.textContent = data.markdown;
  } catch (err) {
    body.textContent = '회의록 조회 실패: ' + err.message;
  }
});

document.getElementById('meetings-refresh').addEventListener('click', loadMeetings);
