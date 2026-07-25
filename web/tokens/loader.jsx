// 3층 디자인 토큰 JSON 을 로드·참조해석·Easing 검증해 window.OMX.themes 로 노출하는 로더
// 로드 순서 계약: animations-v2.jsx(엔진) → 본 파일 → omx-metaphors.jsx → omx-templates.jsx → 프로젝트 scenes.jsx
(function () {
  'use strict';
  var OMX = (window.OMX = window.OMX || {});

  var MAX_THEME_BYTES = 64 * 1024; // 방어적 파서 상한 (ppParse 계열)
  var REF_RE = /^\{([A-Za-z0-9_.\-]+)\}$/;

  // ── 동기 JSON 로더 (프리뷰·단독 구동용, http 서빙 전제) ──────────────
  function loadJson(url) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, false);
    xhr.send(null);
    if (xhr.status >= 200 && xhr.status < 300) return JSON.parse(xhr.responseText);
    throw new Error('OMX.io.loadJson: HTTP ' + xhr.status + ' — ' + url);
  }

  // ── 방어적 테마 파서 — 위반 시 null (렌더를 파괴하지 않는다) ─────────
  function parseTheme(raw) {
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) return raw;
    if (typeof raw !== 'string' || !raw || raw.length > MAX_THEME_BYTES) return null;
    var parsed;
    try { parsed = JSON.parse(raw); } catch (e) { return null; }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    return parsed;
  }

  // ── "{palette.blue}" 참조 해석 — raw.* 우선, 다음 semantic.* ─────────
  function lookupRef(doc, path) {
    var segs = path.split('.');
    var spaces = [doc.raw || {}, doc.semantic || {}];
    for (var s = 0; s < spaces.length; s++) {
      var cur = spaces[s];
      var ok = true;
      for (var i = 0; i < segs.length; i++) {
        if (cur && typeof cur === 'object' && segs[i] in cur) cur = cur[segs[i]];
        else { ok = false; break; }
      }
      if (ok) return cur;
    }
    throw new Error('OMX.themes: 해석할 수 없는 토큰 참조 "{' + path + '}"');
  }

  function resolveNode(node, doc) {
    if (typeof node === 'string') {
      var m = REF_RE.exec(node);
      if (m) return resolveNode(lookupRef(doc, m[1]), doc);
      return node;
    }
    if (Array.isArray(node)) {
      var arr = [];
      for (var i = 0; i < node.length; i++) arr.push(resolveNode(node[i], doc));
      return arr;
    }
    if (node && typeof node === 'object') {
      var out = {};
      for (var k in node) if (Object.prototype.hasOwnProperty.call(node, k)) out[k] = resolveNode(node[k], doc);
      return out;
    }
    return node;
  }

  // ── motion 프리셋의 ease 이름이 엔진 Easing 실제 키인지 전수 검증 ────
  function validateEasing(motion) {
    var Easing = window.Easing;
    if (!Easing) throw new Error('OMX.themes: window.Easing 이 없다 — 엔진(animations-v2.jsx)을 먼저 로드하라');
    function check(obj, path) {
      for (var k in obj) {
        if (!Object.prototype.hasOwnProperty.call(obj, k)) continue;
        var v = obj[k];
        if (k === 'ease') {
          if (typeof v !== 'string' || typeof Easing[v] !== 'function')
            throw new Error('OMX.themes: motion.' + path + 'ease="' + v + '" 는 엔진 Easing 에 없는 키');
        } else if (v && typeof v === 'object') check(v, path + k + '.');
      }
    }
    check(motion || {}, '');
  }

  // ── 테마 문서 → 해석 완료된 소비용 트리 ─────────────────────────────
  // load(input): input 은 테마 객체 | JSON 문자열 | 등록된 themeId.
  // 반환 트리: { id, name, version, color, font, shadow, type, layout, radius,
  //             motion, contrastPairs, component, raw, semantic }
  function load(input) {
    var doc = null;
    if (typeof input === 'string' && registry[input]) doc = registry[input];
    else doc = parseTheme(input);
    if (!doc) return null;

    var motion = resolveNode((doc.semantic || {}).motion || {}, doc);
    validateEasing(motion);

    var component = resolveNode(doc.component || {}, doc);
    var semantic = resolveNode(doc.semantic || {}, doc);
    var raw = doc.raw || {};

    var palette = raw.palette || {};
    var extra = raw.extra || {};
    var color = {};
    var k;
    for (k in palette) if (Object.prototype.hasOwnProperty.call(palette, k)) color[k] = palette[k];
    for (k in extra) if (Object.prototype.hasOwnProperty.call(extra, k)) color[k] = extra[k];

    return {
      id: doc.id || null,
      name: doc.name || doc.id || null,
      version: doc.version || null,
      color: color,
      font: raw.font || {},
      shadow: raw.shadow || {},
      type: semantic.type || {},
      layout: semantic.layout || {},
      radius: semantic.radius || {},
      motion: motion,
      contrastPairs: semantic.contrastPairs || [],
      component: component,
      raw: raw,
      semantic: semantic,
    };
  }

  var registry = {};

  var themes = {
    registry: registry,
    register: function (id, doc) { registry[id] = doc; },
    load: load,
    // URL 에서 테마 JSON 을 동기 로드해 해석 (프리뷰 엔트리용)
    loadUrl: function (url) { return load(loadJson(url)); },
    // PLAN §6.2 주입 채널 — window.OM_THEME JSON 문자열 리터럴을 읽는다
    fromGlobal: function () { return load(window.OM_THEME || null); },
  };

  Object.assign(OMX, { themes: themes, io: { loadJson: loadJson } });
})();
