# 씬 단위 HTML 출력(light/self)·스틸 PNG 캡처·핀포인트 패치 적용 — 핀포인트 수정 루프의 실체 (PLAN §5.9)
"""빌드 산출물(data/build/{slug}/)에서 씬 하나만 도는 엔트리를 만들어낸다.

- light 모드: 빌드 상대 자원(runtime/templates/tokens/vendor/fonts) 참조 경량판.
  빌드 디렉터리 루트에 두거나 base_href 로 서빙 경로를 맞추면 그대로 돈다.
- self 모드: react·react-dom·babel·엔진·토큰 로더·템플릿·씬 데이터·폰트를 전부
  인라인한 자립형 단일 html — http 서빙 없이 file:// 로도 열린다 (chat 임베드·첨부용).

스틸 PNG 는 전체 엔트리를 RenderSession 으로 열고 씬 누적 오프셋 + 로컬 시각으로
seek 해 캡처한다 (포맷 스펙 stage 원척, 캡처 직렬화 잠금 + scene-data 기준 캐시).
"""
from __future__ import annotations

import base64
import json
import re
import threading
from pathlib import Path

from . import runs as runledger
from .runs import data_dir

# 파일명으로 안전한 문자만 남기는 치환 (씬 이름은 한국어 허용)
_SAFE_RE = re.compile(r"[^0-9A-Za-z가-힣_-]+")
# 씬 로컬 seek 시각을 씬 끝에서 살짝 안쪽으로 클램프 (경계 프레임 = 다음 씬 방지)
_EDGE_EPS = 0.02

# 캡처 직렬화 — Playwright 크로미엄 동시 기동 폭주 방지 (요청은 FastAPI 스레드풀에서 온다)
_CAPTURE_LOCK = threading.Lock()


def safe_name(name: str) -> str:
    return _SAFE_RE.sub("-", str(name)).strip("-") or "scene"


# ── 씬 목록 ──────────────────────────────────────────────────────────────────


def scene_doc(build_dir: Path) -> dict:
    """빌드 산출물의 scene-data.json (ScenarioDoc dump)을 읽는다."""
    path = Path(build_dir) / "scene-data.json"
    if not path.is_file():
        raise FileNotFoundError(f"scene-data.json 이 없다: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _find(doc: dict, scene_name: str) -> dict:
    scene = next((s for s in doc.get("scenes", []) if s.get("name") == scene_name), None)
    if scene is None:
        names = [s.get("name") for s in doc.get("scenes", [])]
        raise KeyError(f"씬 {scene_name!r} 이 없다 (씬 목록: {names})")
    return scene


def _brief(value, limit: int = 240) -> str:
    s = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return s if len(s) <= limit else s[:limit] + "…"


def list_scenes(build_dir: Path) -> list[dict]:
    """씬 목록 요약 — name/tpl/dur/nat/stills/narration/data_ref/data 요약."""
    doc = scene_doc(build_dir)
    out: list[dict] = []
    for s in doc.get("scenes", []):
        data = _data_of(doc, s)
        nar = (s.get("narration") or "").replace("\n", " ")
        out.append({
            "name": s.get("name"),
            "tpl": s.get("tpl"),
            "dur": s.get("dur"),
            "nat": s.get("nat"),
            "stills": s.get("stills") or [],
            "narration": nar if len(nar) <= 160 else nar[:160] + "…",
            "data_ref": s.get("data_ref"),
            "data_brief": _brief(data) if isinstance(data, dict) else "{}",
        })
    return out


def _data_of(doc: dict, scene: dict):
    node = doc
    for seg in (scene.get("data_ref") or "").split("."):
        if isinstance(node, dict) and seg in node:
            node = node[seg]
        else:
            return None
    return node


# ── 씬 엔트리 HTML ───────────────────────────────────────────────────────────


def _js_str(s: str) -> str:
    """파이썬 문자열 → JS 문자열 리터럴 (</script> 조기 종료 방지 포함 — build.py 규약)."""
    return json.dumps(s, ensure_ascii=False).replace("</", "<\\/")


def _guard(text: str) -> str:
    """인라인 스크립트 본문의 </script 조기 종료 방지.

    JS 주석·문자열 안의 "</script" 를 "<\\/script" 로 바꾼다 — 두 맥락 모두에서
    의미 불변이다 (엔진 헤더 주석의 예제 코드가 실제 해당 사례).
    """
    return text.replace("</script", "<\\/script")


def _load_order_files() -> list[str]:
    """registry 로드 순서 계약에서 프로젝트 scenes.jsx 를 뺀 빌드 상대 경로 목록."""
    from wdpipeline.build import load_order

    return [p for p in load_order() if p != "./scenes.jsx"]


def _scene_binding_jsx(scene: dict, tpl_id: str, stage_w: int, stage_h: int) -> str:
    """단일 씬 바인딩 스크립트 — 빌드 scenes.jsx 동형이되 데이터는 인라인 전역에서 읽는다."""
    name = json.dumps(scene["name"], ensure_ascii=False)
    data_ref = json.dumps(scene.get("data_ref") or "")
    tpl = json.dumps(tpl_id)
    return f"""// 씬 단위 자동 생성 바인딩 — 데이터는 window.WDA_SCENE_DATA 인라인 (fetch 무사용, file:// 가능)
const SceneRoot = window.SceneStage; // 비충돌 별칭 (const 충돌 규약)
const wdaDoc = window.WDA_SCENE_DATA;
const wdaTheme = window.OMX.themes.fromGlobal();

function wdaRef(path) {{
  var node = wdaDoc;
  var segs = path.split('.');
  for (var i = 0; i < segs.length; i++) {{
    if (node == null) throw new Error('scene entry: data_ref 해석 실패 — ' + path);
    node = node[segs[i]];
  }}
  return node;
}}

const WdaTpl = window.OMX.templateIndex[{tpl}];
if (!WdaTpl) throw new Error('scene entry: 레지스트리에 없는 템플릿 — ' + {tpl});
const wdaData = wdaRef({data_ref});
const wdaChildren = {{
  {name}: function WdaBound(props) {{
    return <WdaTpl {{...props}} data={{wdaData}} theme={{wdaTheme}} />;
  }}
}};

function WdaSceneEntry() {{
  return (
    <div style={{{{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden' }}}}>
      <SceneRoot width={{{stage_w}}} height={{{stage_h}}} bg={{wdaTheme.color.bg}}
                 scenes={{window.OM_SCENES}} playback={{window.OM_PLAYBACK}}>
        {{wdaChildren}}
      </SceneRoot>
    </div>
  );
}}
window.WdaSceneEntry = WdaSceneEntry;
ReactDOM.createRoot(document.getElementById('root')).render(<WdaSceneEntry />);
"""


def _still_script(t: float) -> str:
    """씬 마운트 후 t(초)로 seek 해 정지시키는 바닐라 스크립트 (엔진 seek 프로토콜).

    seek 이벤트는 엔진 자체 시계를 멈춘다(setPlaying(false)) — 리스너 부착 경합에
    대비해 발견 후 몇 회 반복 발사한다. 스페이스로 재생 재개는 그대로 가능하다.
    """
    return f"""(function () {{
  var t = {t};
  var fired = 0, tries = 0;
  var iv = setInterval(function () {{
    var el = document.querySelector('svg[data-om-exportable-video-with-duration-secs]');
    if (el) {{
      el.dispatchEvent(new CustomEvent('data-om-seek-to-time-frame', {{ detail: {{ time: t }} }}));
      if (++fired >= 4) clearInterval(iv);
    }} else if (++tries > 300) {{
      clearInterval(iv);
    }}
  }}, 150);
}})();"""


def scene_entry_html(
    build_dir: Path,
    scene_name: str,
    *,
    still: float | None = None,
    mode: str = "light",
    base_href: str | None = None,
) -> str:
    """해당 씬 하나만 도는(loop) 엔트리 HTML 을 생성한다.

    mode="light": 빌드 상대 자원 참조 경량판 (base_href 로 서빙 경로 보정 가능).
    mode="self": 모든 JS·토큰·데이터·폰트 인라인 자립형 단일 html (file:// 가능).
    still: 씬 로컬 시각(초) — 지정 시 마운트 후 그 프레임에서 정지.
    """
    if mode not in ("light", "self"):
        raise ValueError(f"mode 는 light|self 다: {mode!r}")
    build_dir = Path(build_dir)
    doc = scene_doc(build_dir)
    scene = _find(doc, scene_name)

    from wdpipeline.format import load_format, resolve_tpl_module_id

    spec = load_format(str(doc.get("format") or "wide-16x9"))
    tpl_id = resolve_tpl_module_id(str(scene.get("tpl") or ""), spec=spec)

    # OM_SCENES — 이 씬 하나, OM_PLAYBACK — loop (주입 축약형 규약: name/dur/nat/stills/tpl)
    entry: dict = {"name": scene["name"], "dur": scene["dur"], "tpl": scene["tpl"]}
    if scene.get("nat") is not None:
        entry["nat"] = scene["nat"]
    if scene.get("stills"):
        entry["stills"] = scene["stills"]
    om_scenes = _js_str(json.dumps([entry], ensure_ascii=False, separators=(",", ":")))
    om_playback = _js_str(json.dumps({"mode": "loop"}))

    # 테마 — 빌드 사본 토큰 + 포맷 stage 좌표 주입 (build.py 동형 규약)
    theme_name = str(doc.get("tokens_theme") or "hwax-blue")
    theme_path = build_dir / "tokens" / f"{theme_name}.json"
    if not theme_path.is_file():
        raise FileNotFoundError(f"빌드 토큰 사본이 없다: {theme_path}")
    theme_doc = json.loads(theme_path.read_text(encoding="utf-8"))
    bg = theme_doc.get("raw", {}).get("palette", {}).get("bg", "#E9EBF1")
    theme_doc.setdefault("semantic", {}).setdefault("layout", {})
    theme_doc["semantic"]["layout"]["stageW"] = spec.stage.w
    theme_doc["semantic"]["layout"]["stageH"] = spec.stage.h
    om_theme = _js_str(json.dumps(theme_doc, ensure_ascii=False, separators=(",", ":")))

    scene_data = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    if still is not None:
        dur = float(scene["dur"])
        still = max(0.0, min(float(still), max(dur - _EDGE_EPS, 0.0)))

    # 자원 — light 는 상대 참조, self 는 전부 인라인
    fonts = sorted((build_dir / "fonts").glob("*.woff2"))
    if mode == "self":
        if not fonts:
            raise FileNotFoundError(f"빌드 폰트 사본이 없다: {build_dir / 'fonts'}")
        b64 = base64.b64encode(fonts[0].read_bytes()).decode("ascii")
        font_src = f"url(data:font/woff2;base64,{b64}) format('woff2-variations')"
        vendor_tags = "\n".join(
            f"<script>{_guard((build_dir / 'vendor' / f).read_text(encoding='utf-8'))}</script>"
            for f in ("react.production.min.js", "react-dom.production.min.js", "babel.min.js")
        )
        babel_tags = "\n".join(
            '<script type="text/babel" data-presets="react">'
            + _guard((build_dir / p.lstrip("./")).read_text(encoding="utf-8"))
            + "</script>"
            for p in _load_order_files()
        )
        base_tag = ""
    else:
        font_name = fonts[0].name if fonts else "PretendardVariable.woff2"
        font_src = f"url('./fonts/{font_name}') format('woff2-variations')"
        vendor_tags = "\n".join(
            f'<script src="./vendor/{f}"></script>'
            for f in ("react.production.min.js", "react-dom.production.min.js", "babel.min.js")
        )
        babel_tags = "\n".join(
            f'<script type="text/babel" data-presets="react" src="{p}"></script>'
            for p in _load_order_files()
        )
        base_tag = f'<base href="{base_href}">\n' if base_href else ""

    binding = _guard(_scene_binding_jsx(scene, tpl_id, spec.stage.w, spec.stage.h))
    still_tag = f"<script>{_still_script(still)}</script>\n" if still is not None else ""
    title = f"{doc.get('meta', {}).get('core_message', '')} — {scene['name']}".replace("<", "&lt;")

    return f"""<!DOCTYPE html>
<!-- 씬 단위 자동 생성 엔트리 ({mode}) — 씬 {scene['name']!r} 단독 loop 재생{', still=' + str(still) if still is not None else ''} -->
<html lang="ko">
<head>
<meta charset="utf-8">
{base_tag}<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>@font-face{{font-family:'Pretendard Variable';font-weight:45 920;font-style:normal;font-display:swap;src:{font_src};}}</style>
<style>html, body {{ margin: 0; padding: 0; height: 100%; background: {bg}; }}</style>
<script>window.OM_SCENES = {om_scenes};</script>
<script>window.OM_PLAYBACK = {om_playback};</script>
<script>window.OM_THEME = {om_theme};</script>
<script>window.WDA_SCENE_DATA = {scene_data};</script>
{vendor_tags}
</head>
<body>
<div id="root"></div>
{babel_tags}
<script type="text/babel" data-presets="react">
{binding}
</script>
{still_tag}</body>
</html>
"""


# ── 씬 스틸 PNG ──────────────────────────────────────────────────────────────


def _scene_offset(doc: dict, scene_name: str) -> float:
    off = 0.0
    for s in doc.get("scenes", []):
        if s.get("name") == scene_name:
            return off
        off += float(s.get("dur") or 0)
    raise KeyError(f"씬 {scene_name!r} 이 없다")


def _default_still(scene: dict, progress: float) -> float:
    if scene.get("stills"):
        return float(scene["stills"][0])
    dur = float(scene["dur"])
    return round(min(dur * progress, dur - _EDGE_EPS), 3)


def _still_path(build_dir: Path, scene_name: str, t: float) -> Path:
    return Path(build_dir) / "scene-stills" / f"{safe_name(scene_name)}@{t:.2f}.png"


def _fresh(build_dir: Path, path: Path) -> bool:
    src = Path(build_dir) / "scene-data.json"
    return path.is_file() and path.stat().st_mtime >= src.stat().st_mtime


def _capture_batch(build_dir: Path, jobs: list[tuple[float, Path]], entry: str = "index.html") -> None:
    """전체 엔트리 1세션에서 (전역 시각, 저장 경로) 목록을 순서대로 캡처한다.

    전용 스레드에서 돈다 — 호출 스레드에 asyncio 루프가 살아 있으면(인프로세스 MCP 등)
    sync Playwright 가 기동을 거부하기 때문이다. 예외는 그대로 재전파한다.
    """
    doc = scene_doc(build_dir)
    from wdrender.config import apply_format, load_config
    from wdrender.page_session import RenderSession, vendor_resources
    from wdrender.server import StaticServer

    cfg = apply_format(load_config(), doc.get("format"))
    resources = vendor_resources("/vendor") if (Path(build_dir) / "vendor").is_dir() else None

    failure: list[BaseException] = []

    def _work() -> None:
        try:
            with _CAPTURE_LOCK:
                # 동시 요청 우르르 몰림 붕괴 — 앞선 캡처가 이미 만들어 둔 스틸은 건너뛴다
                todo = [(gt, p) for gt, p in sorted(jobs) if not _fresh(build_dir, p)]
                if not todo:
                    return
                with StaticServer(build_dir) as srv:
                    with RenderSession(
                        srv.url_for(entry),
                        width=cfg.width, height=cfg.height,
                        viewport_margin=cfg.viewport_margin, resources=resources,
                    ) as sess:
                        for gt, path in todo:
                            path.parent.mkdir(parents=True, exist_ok=True)
                            sess.seek(min(gt, max(sess.duration - _EDGE_EPS, 0.0)))
                            sess.capture(path)
        except BaseException as exc:  # noqa: BLE001 — 호출자에게 원형 재전파
            failure.append(exc)

    t = threading.Thread(target=_work, name="wda-scene-still", daemon=True)
    t.start()
    t.join()
    if failure:
        raise failure[0]


def scene_still_png(
    build_dir: Path, scene_name: str, t: float | None = None, entry: str = "index.html"
) -> Path:
    """씬 로컬 시각 t 의 스틸 PNG 경로를 반환한다 (없거나 낡았으면 캡처).

    t 미지정 = 기본 스틸(stills[0], 없으면 default_still_progress 지점). 기본 스틸이
    낡았으면 전 씬의 기본 스틸을 한 세션에 일괄 캡처한다 — 씬 스트립 첫 로드 비용을
    브라우저 1회 기동으로 눌러 놓는다.
    """
    build_dir = Path(build_dir)
    doc = scene_doc(build_dir)
    scene = _find(doc, scene_name)
    from wdrender.config import load_config

    progress = load_config().default_still_progress

    if t is None:
        t = _default_still(scene, progress)
        want = _still_path(build_dir, scene_name, t)
        if _fresh(build_dir, want):
            return want
        jobs = []
        for s in doc.get("scenes", []):
            st = _default_still(s, progress)
            path = _still_path(build_dir, s["name"], st)
            if not _fresh(build_dir, path):
                jobs.append((_scene_offset(doc, s["name"]) + st, path))
        _capture_batch(build_dir, jobs, entry)
        return want

    dur = float(scene["dur"])
    t = max(0.0, min(float(t), max(dur - _EDGE_EPS, 0.0)))
    want = _still_path(build_dir, scene_name, t)
    if not _fresh(build_dir, want):
        _capture_batch(build_dir, [(_scene_offset(doc, scene_name) + t, want)], entry)
    return want


# ── 핀포인트 패치 적용 (PATCH /api/runs/{id}/scenario 본체) ──────────────────


def apply_patch_to_run(run: dict, ops: list[dict]) -> dict:
    """patch_scenario 로 시나리오를 수정·검증하고 저장 + 재빌드 + 원장 갱신한다.

    실패는 wdpipeline.patch.PatchError 로 전파된다 (원본 무손상 — 호출자가 봉투로 변환).
    """
    from wdpipeline.build import build_render_package
    from wdpipeline.patch import patch_scenario
    from wdcore.models.scenario import ScenarioDoc

    run_id = run["run_id"]
    scen_path = data_dir() / "pipeline" / run_id / "scenario.json"
    if not scen_path.is_file():
        raise FileNotFoundError(f"scenario.json 이 없다: {scen_path}")
    scenario = json.loads(scen_path.read_text(encoding="utf-8"))

    patched, diffs = patch_scenario(scenario, ops)  # PatchError 시 여기서 중단 (원본 무손상)
    doc = ScenarioDoc.model_validate(patched)

    scen_path.write_text(json.dumps(patched, ensure_ascii=False, indent=2), encoding="utf-8")
    build_dir = Path(run["build_dir"]) if run.get("build_dir") else data_dir() / "build" / run["slug"]
    entry = Path(build_render_package(doc, build_dir))
    summary = {
        "scene_count": len(doc.scenes),
        "total_dur": round(sum(s.dur for s in doc.scenes), 3),
        "core_message": doc.meta.core_message,
    }
    runledger.update_run(
        run_id, build_dir=str(entry.parent), entry=entry.name, scenario_summary=summary,
    )
    return {"applied": diffs, "rebuilt": True, "scenario_summary": summary}
