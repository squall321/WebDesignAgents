# P4 build — ScenarioDoc 를 순수 HTML 엔트리 + 템플릿 바인딩 scenes.jsx + 엔진/토큰/vendor 사본의 렌더 패키지로 조립
from __future__ import annotations

import json
import shutil
from pathlib import Path

from wdcore.models.scenario import ScenarioDoc, check_om_scenes_budget, om_scenes_json

from .format import FormatSpec, load_format, resolve_modules_root, resolve_tpl_module_id

# repo 루트 (src/wdpipeline/build.py → 두 단계 위)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_RUNTIME_SRC = _REPO_ROOT / "web" / "runtime"
_TEMPLATES_SRC = _REPO_ROOT / "web" / "templates"
_TOKENS_SRC = _REPO_ROOT / "web" / "tokens"
_VENDOR_SRC = _REPO_ROOT / "web" / "vendor"
_FONTS_SRC = _REPO_ROOT / "web" / "fonts"
_FONT_FILE = "PretendardVariable.woff2"

_VENDOR_FILES = ("react.production.min.js", "react-dom.production.min.js", "babel.min.js")

ENTRY_NAME = "index.html"

# 엔진 계약 로드 순서 (브리프 P4 규약): 엔진 → 토큰 로더 → 은유 → 템플릿 → 프로젝트 scenes.
# **정본은 modules/registry.yaml 의 load_order_contract 다** — 템플릿 파일이 늘어날 때
# (창작 모드 승격·신규 포맷) 여기를 잊어 엔트리에서 누락되는 사고를 막는다.
# (실제 사고: omx-templates-ext.jsx 누락으로 tpl.dataviz 빌드가 재현 불능이었다 — v2 심의 TD 적발)
_FALLBACK_LOAD_ORDER = (
    "./runtime/animations-v2.jsx",
    "./tokens/loader.jsx",
    "./templates/omx-metaphors.jsx",
    "./templates/omx-templates.jsx",
    "./scenes.jsx",
)


def load_order() -> tuple[str, ...]:
    """registry.yaml 의 load_order_contract 를 빌드 상대경로로 변환한다."""
    registry = _REPO_ROOT / "modules" / "registry.yaml"
    if not registry.is_file():
        return _FALLBACK_LOAD_ORDER
    try:
        import yaml

        contract = (yaml.safe_load(registry.read_text(encoding="utf-8")) or {}).get(
            "load_order_contract"
        )
    except Exception:  # noqa: BLE001 — 레지스트리가 깨져도 빌드는 폴백으로 살린다
        return _FALLBACK_LOAD_ORDER
    if not isinstance(contract, list) or not contract:
        return _FALLBACK_LOAD_ORDER
    out: list[str] = []
    for item in contract:
        s = str(item)
        if s.startswith("<"):  # "<project scenes.jsx>" 자리표시자
            out.append("./scenes.jsx")
        elif s.startswith("web/"):
            out.append("./" + s[len("web/") :])
        else:
            out.append("./" + s.lstrip("./"))
    return tuple(out)


_LOAD_ORDER = load_order()

# 폰트는 로컬 사본을 @font-face 로 인라인한다 — CDN(jsdelivr) 의존을 끊어 렌더를 결정적으로
# 만들고 M3 egress-0(오프라인 SIF) 전제를 지킨다. woff2 는 build 시 out_dir/fonts/ 로 복사된다.
_PRETENDARD_FACE = (
    "@font-face{font-family:'Pretendard Variable';"
    "font-weight:45 920;font-style:normal;font-display:swap;"
    f"src:url('./fonts/{_FONT_FILE}') format('woff2-variations');}}"
)


def _js_string_literal(s: str) -> str:
    """파이썬 문자열 → 안전한 JS 문자열 리터럴 (</script> 조기 종료 방지 포함)."""
    return json.dumps(s, ensure_ascii=False).replace("</", "<\\/")


def _playback_json(doc: ScenarioDoc) -> str:
    if doc.playback.mode == "times":
        return json.dumps({"mode": "times", "count": doc.playback.count})
    return json.dumps({"mode": "loop"})


def _tpl_id(tpl_ref: str, spec: FormatSpec | None = None, modules_root: Path | None = None) -> str:
    """씬 tpl 참조 → templateIndex 키. "opening@1"→"tpl.opening", "hook@1"→"vtpl.hook".

    포맷 template_pool → modules/registry.yaml 순으로 모듈 id 를 찾고, 둘 다 실패하면
    기존 규약("tpl.{이름}")으로 떨어진다.
    """
    return resolve_tpl_module_id(tpl_ref, spec=spec, modules_root=modules_root)


def _template_files() -> tuple[str, ...]:
    """로드 순서 계약이 요구하는 web/templates/*.jsx 파일명 (엔트리 script 와 사본의 공통 원천)."""
    prefix = "./templates/"
    return tuple(s[len(prefix):] for s in _LOAD_ORDER if s.startswith(prefix))


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
<style>{_PRETENDARD_FACE}</style>
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


def _render_scenes_jsx(
    doc: ScenarioDoc, spec: FormatSpec, modules_root: Path | None = None
) -> str:
    """OMX 템플릿 바인딩 scenes.jsx — 씬 코드를 생성하지 않고 레지스트리 컴포넌트를 바인딩만 한다.

    무대 크기(SceneRoot width/height)는 코드 상수가 아니라 포맷 스펙 stage 에서 온다.
    babel standalone 전역 스코프 규약: 엔진 최상위 선언(Easing/Stage/SceneStage/animate 등)과
    겹치지 않는 wda* 접두 이름만 선언한다.
    """
    entries = ",\n".join(
        f"  {json.dumps(s.name, ensure_ascii=False)}: "
        f"wdaBind({json.dumps(_tpl_id(s.tpl, spec, modules_root))}, {json.dumps(s.data_ref)})"
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
      <SceneRoot width={{{spec.stage.w}}} height={{{spec.stage.h}}} bg={{wdaTheme.color.bg}}
                 scenes={{window.OM_SCENES}} playback={{window.OM_PLAYBACK}}>
        {{wdaChildren}}
      </SceneRoot>
    </div>
  );
}}
window.WdaEntry = WdaEntry;
ReactDOM.createRoot(document.getElementById('root')).render(<WdaEntry />);
"""


def build_render_package(
    doc: ScenarioDoc,
    out_dir: Path,
    *,
    spec: FormatSpec | None = None,
    modules_root: Path | None = None,
) -> Path:
    """ScenarioDoc → data/build/{slug}/ 렌더 패키지 생성, 엔트리 경로 반환 (모듈 간 계약).

    무대 크기는 doc.format 의 포맷 스펙(stage)이 지배한다 — 엔트리 SceneRoot width/height 와
    주입 테마의 layout.stageW/H 를 같은 값으로 맞춰 템플릿이 무대를 알게 한다.

    산출: index.html(순수 HTML 엔트리) + scenes.jsx(템플릿 바인딩) + scene-data.json
          + runtime/·templates/·tokens/·vendor/ 무수정 사본.
    """
    check_om_scenes_budget(doc)  # 16KB 주입 예산 — 빌드 전 최종 방어선
    modules_root = Path(modules_root) if modules_root is not None else resolve_modules_root()
    if spec is None:
        spec = load_format(doc.format, modules_root=modules_root)

    theme_path = _TOKENS_SRC / f"{doc.tokens_theme}.json"
    if not theme_path.is_file():
        raise FileNotFoundError(f"테마 토큰 없음: {theme_path} (tokens_theme={doc.tokens_theme})")
    theme_raw = theme_path.read_text(encoding="utf-8")
    theme_doc = json.loads(theme_raw)
    bg = theme_doc.get("raw", {}).get("palette", {}).get("bg", "#E9EBF1")
    # 주입 테마의 무대 좌표는 포맷이 덮어쓴다 (토큰 파일 사본은 원본 그대로 둔다 — 프리뷰 공용).
    theme_doc.setdefault("semantic", {}).setdefault("layout", {})
    theme_doc["semantic"]["layout"]["stageW"] = spec.stage.w
    theme_doc["semantic"]["layout"]["stageH"] = spec.stage.h
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
    # 템플릿 사본은 엔트리 script 와 같은 원천(load_order)에서 뽑는다 — 참조/사본 불일치로
    # 404 나는 빌드를 원천 차단한다 (선언만 되고 복사되지 않던 ext·vertical 사고).
    (out_dir / "templates").mkdir(exist_ok=True)
    for name in _template_files():
        src = _TEMPLATES_SRC / name
        if not src.is_file():
            raise FileNotFoundError(
                f"템플릿 미비: {src} — modules/registry.yaml 의 load_order_contract 가 선언한 "
                f"파일이 web/templates/ 에 없다"
            )
        shutil.copy2(src, out_dir / "templates" / name)
    (out_dir / "vendor").mkdir(exist_ok=True)
    for f in _VENDOR_FILES:
        shutil.copy2(_VENDOR_SRC / f, out_dir / "vendor" / f)
    # 폰트 로컬 사본 — @font-face 가 ./fonts/ 로 참조하므로 함께 복사 (CDN 의존 제거)
    (out_dir / "fonts").mkdir(exist_ok=True)
    shutil.copy2(_FONTS_SRC / _FONT_FILE, out_dir / "fonts" / _FONT_FILE)

    # 씬 데이터 + 바인딩 + 엔트리
    (out_dir / "scene-data.json").write_text(
        json.dumps(doc.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "scenes.jsx").write_text(
        _render_scenes_jsx(doc, spec, modules_root), encoding="utf-8"
    )
    entry = out_dir / ENTRY_NAME
    entry.write_text(_render_index_html(doc, theme_compact, bg), encoding="utf-8")
    return entry
