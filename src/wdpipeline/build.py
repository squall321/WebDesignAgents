# P4 build — ScenarioDoc 를 순수 HTML 엔트리 + 템플릿 바인딩 scenes.jsx + 엔진/토큰/vendor 사본의 렌더 패키지로 조립
from __future__ import annotations

import json
import shutil
from pathlib import Path

from wdcore.models.scenario import ScenarioDoc, check_om_scenes_budget, om_scenes_json

# repo 루트 (src/wdpipeline/build.py → 두 단계 위)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_SRC = _REPO_ROOT / "web" / "runtime"
_TEMPLATES_SRC = _REPO_ROOT / "web" / "templates"
_TOKENS_SRC = _REPO_ROOT / "web" / "tokens"
_VENDOR_SRC = _REPO_ROOT / "web" / "vendor"

_VENDOR_FILES = ("react.production.min.js", "react-dom.production.min.js", "babel.min.js")

ENTRY_NAME = "index.html"

# 엔진 계약 로드 순서 (브리프 P4 규약): 엔진 → 토큰 로더 → 은유 → 템플릿 → 프로젝트 scenes
_LOAD_ORDER = (
    "./runtime/animations-v2.jsx",
    "./tokens/loader.jsx",
    "./templates/omx-metaphors.jsx",
    "./templates/omx-templates.jsx",
    "./scenes.jsx",
)

_PRETENDARD_CSS = (
    "https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9"
    "/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
)


def _js_string_literal(s: str) -> str:
    """파이썬 문자열 → 안전한 JS 문자열 리터럴 (</script> 조기 종료 방지 포함)."""
    return json.dumps(s, ensure_ascii=False).replace("</", "<\\/")


def _playback_json(doc: ScenarioDoc) -> str:
    if doc.playback.mode == "times":
        return json.dumps({"mode": "times", "count": doc.playback.count})
    return json.dumps({"mode": "loop"})


def _tpl_id(tpl_ref: str) -> str:
    """씬 tpl 참조("opening@1") → templateIndex 키("tpl.opening")."""
    return "tpl." + tpl_ref.split("@", 1)[0]


def _render_index_html(doc: ScenarioDoc, theme_raw: str, bg: str) -> str:
    scripts = "\n".join(
        f'<script type="text/babel" data-presets="react" src="{src}"></script>'
        for src in _LOAD_ORDER
    )
    om_scenes = _js_string_literal(om_scenes_json(doc))
    om_playback = _js_string_literal(_playback_json(doc))
    om_theme = _js_string_literal(theme_raw)
    title = doc.meta.core_message.replace("<", "&lt;")
    return f"""<!DOCTYPE html>
<!-- P4 자동 생성 순수 HTML 엔트리 — React+Babel+엔진+씬 직접 로드 (support.js 무사용 경로) -->
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="stylesheet" href="{_PRETENDARD_CSS}">
<style>html, body {{ margin: 0; padding: 0; height: 100%; background: {bg}; }}</style>
<script>window.OM_SCENES = {om_scenes};</script>
<script>window.OM_PLAYBACK = {om_playback};</script>
<script>window.OM_THEME = {om_theme};</script>
<script src="./vendor/react.production.min.js"></script>
<script src="./vendor/react-dom.production.min.js"></script>
<script src="./vendor/babel.min.js"></script>
</head>
<body>
<div id="root"></div>
{scripts}
</body>
</html>
"""


def _render_scenes_jsx(doc: ScenarioDoc) -> str:
    """OMX 템플릿 바인딩 scenes.jsx — 씬 코드를 생성하지 않고 레지스트리 컴포넌트를 바인딩만 한다.

    babel standalone 전역 스코프 규약: 엔진 최상위 선언(Easing/Stage/SceneStage/animate 등)과
    겹치지 않는 wda* 접두 이름만 선언한다.
    """
    entries = ",\n".join(
        f"  {json.dumps(s.name, ensure_ascii=False)}: "
        f"wdaBind({json.dumps(_tpl_id(s.tpl))}, {json.dumps(s.data_ref)})"
        for s in doc.scenes
    )
    return f"""// P4 자동 생성 씬 바인딩 — 템플릿 재사용 모드 (손편집 금지, 데이터는 scene-data.json)
const SceneRoot = window.SceneStage; // 비충돌 별칭 (const 충돌 규약)
const wdaDoc = window.OMX.io.loadJson('./scene-data.json');
const wdaTheme = window.OMX.themes.fromGlobal(); // window.OM_THEME 주입 채널

function wdaRef(path) {{
  var node = wdaDoc;
  var segs = path.split('.');
  for (var i = 0; i < segs.length; i++) {{
    if (node == null) throw new Error('scenes.jsx: data_ref 해석 실패 — ' + path);
    node = node[segs[i]];
  }}
  return node;
}}

function wdaBind(tplId, dataRef) {{
  var Tpl = window.OMX.templateIndex[tplId];
  if (!Tpl) throw new Error('scenes.jsx: 레지스트리에 없는 템플릿 — ' + tplId);
  var data = wdaRef(dataRef);
  return function WdaBound(props) {{
    return <Tpl {{...props}} data={{data}} theme={{wdaTheme}} />;
  }};
}}

const wdaChildren = {{
{entries}
}};

function WdaEntry() {{
  return (
    <div style={{{{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden' }}}}>
      <SceneRoot width={{1920}} height={{1080}} bg={{wdaTheme.color.bg}}
                 scenes={{window.OM_SCENES}} playback={{window.OM_PLAYBACK}}>
        {{wdaChildren}}
      </SceneRoot>
    </div>
  );
}}
window.WdaEntry = WdaEntry;
ReactDOM.createRoot(document.getElementById('root')).render(<WdaEntry />);
"""


def build_render_package(doc: ScenarioDoc, out_dir: Path) -> Path:
    """ScenarioDoc → data/build/{slug}/ 렌더 패키지 생성, 엔트리 경로 반환 (모듈 간 계약).

    산출: index.html(순수 HTML 엔트리) + scenes.jsx(템플릿 바인딩) + scene-data.json
          + runtime/·templates/·tokens/·vendor/ 무수정 사본.
    """
    check_om_scenes_budget(doc)  # 16KB 주입 예산 — 빌드 전 최종 방어선

    theme_path = _TOKENS_SRC / f"{doc.tokens_theme}.json"
    if not theme_path.is_file():
        raise FileNotFoundError(f"테마 토큰 없음: {theme_path} (tokens_theme={doc.tokens_theme})")
    theme_raw = theme_path.read_text(encoding="utf-8")
    theme_doc = json.loads(theme_raw)
    bg = theme_doc.get("raw", {}).get("palette", {}).get("bg", "#E9EBF1")
    # OM_THEME 주입은 압축 직렬화로 (ppParse 계열 64KB 상한 방어)
    theme_compact = json.dumps(theme_doc, ensure_ascii=False, separators=(",", ":"))

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 엔진/토큰/템플릿/vendor 무수정 사본
    (out_dir / "runtime").mkdir(exist_ok=True)
    shutil.copy2(_RUNTIME_SRC / "animations-v2.jsx", out_dir / "runtime" / "animations-v2.jsx")
    (out_dir / "tokens").mkdir(exist_ok=True)
    shutil.copy2(_TOKENS_SRC / "loader.jsx", out_dir / "tokens" / "loader.jsx")
    shutil.copy2(theme_path, out_dir / "tokens" / theme_path.name)
    (out_dir / "templates").mkdir(exist_ok=True)
    shutil.copy2(_TEMPLATES_SRC / "omx-metaphors.jsx", out_dir / "templates" / "omx-metaphors.jsx")
    shutil.copy2(_TEMPLATES_SRC / "omx-templates.jsx", out_dir / "templates" / "omx-templates.jsx")
    (out_dir / "vendor").mkdir(exist_ok=True)
    for f in _VENDOR_FILES:
        shutil.copy2(_VENDOR_SRC / f, out_dir / "vendor" / f)

    # 씬 데이터 + 바인딩 + 엔트리
    (out_dir / "scene-data.json").write_text(
        json.dumps(doc.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "scenes.jsx").write_text(_render_scenes_jsx(doc), encoding="utf-8")
    entry = out_dir / ENTRY_NAME
    entry.write_text(_render_index_html(doc, theme_compact, bg), encoding="utf-8")
    return entry
