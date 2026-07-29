# 오프라인 렌더 전제 정적 검사 — 빌드 산출물이 외부 URL(CDN)을 로드하지 않음을 증명한다 (PLAN §12.4)
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from wdcore.models.scenario import ScenarioDoc
from wdpipeline.build import ENTRY_NAME, build_render_package

REPO_ROOT = Path(__file__).resolve().parents[1]

# 렌더 노드가 실제로 "가져오는" 참조만 본다. 문서 문자열·에러 메시지 URL
# (vendor/babel.min.js 안의 babeljs.io 안내문 등)은 네트워크를 타지 않으므로 대상이 아니다.
_REF_PATTERNS = (
    re.compile(r"""\bsrc\s*=\s*["']([^"']+)["']"""),
    re.compile(r"""\bhref\s*=\s*["']([^"']+)["']"""),
    re.compile(r"""\burl\(\s*["']?([^"')]+)"""),
    re.compile(r"""@import\s+["']([^"']+)["']"""),
    re.compile(r"""\bfetch\(\s*["']([^"']+)["']"""),
    re.compile(r"""\bimport\s*\(\s*["']([^"']+)["']"""),
    re.compile(r"""\bfrom\s+["'](https?://[^"']+)["']"""),
)

_EXTERNAL_SCHEME = re.compile(r"^(?:https?:)?//", re.IGNORECASE)

# 스킴까지 붙은 형태만 잡는다 — 주석 안의 맨 도메인 언급
# (web/runtime/animations-v2.jsx 의 "fonts.googleapis.com <link>" 설명)은 참조가 아니다.
_CDN_DOMAINS = (
    "unpkg.com",
    "jsdelivr.net",
    "jsdelivr.com",
    "cdnjs.cloudflare.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "ajax.googleapis.com",
    "esm.sh",
    "skypack.dev",
    "cdn.tailwindcss.com",
    "cdn.skypack.dev",
    "raw.githubusercontent.com",
)
_CDN_RE = re.compile(
    r"https?://[a-z0-9.-]*(?:" + "|".join(d.replace(".", r"\.") for d in _CDN_DOMAINS) + ")",
    re.IGNORECASE,
)

# 렌더가 로컬에서 반드시 찾아야 하는 자산 (없으면 오프라인에서 CDN 폴백을 타게 된다)
_REQUIRED_LOCAL = (
    "index.html",
    "scenes.jsx",
    "scene-data.json",
    "fonts/PretendardVariable.woff2",
    "vendor/react.production.min.js",
    "vendor/react-dom.production.min.js",
    "vendor/babel.min.js",
    "runtime/animations-v2.jsx",
    "tokens/loader.jsx",
)

_TEXT_SUFFIXES = {".html", ".htm", ".jsx", ".js", ".css", ".json", ".svg"}


def _text_files(root: Path) -> list[Path]:
    return sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _TEXT_SUFFIXES
    )


def _external_refs(root: Path) -> list[tuple[str, int, str]]:
    """(파일상대경로, 줄번호, 참조) — 외부 스킴을 가리키는 로드 참조 목록."""
    hits: list[tuple[str, int, str]] = []
    for path in _text_files(root):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            for pat in _REF_PATTERNS:
                for ref in pat.findall(line):
                    if _EXTERNAL_SCHEME.match(ref.strip()):
                        hits.append((str(path.relative_to(root)), lineno, ref.strip()[:160]))
    return hits


def _cdn_hits(root: Path) -> list[tuple[str, int, str]]:
    hits: list[tuple[str, int, str]] = []
    for path in _text_files(root):
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
        ):
            for m in _CDN_RE.finditer(line):
                hits.append((str(path.relative_to(root)), lineno, m.group(0)[:160]))
    return hits


def _scenario_docs() -> list[tuple[str, ScenarioDoc]]:
    """현행 빌드 산출물의 scene-data.json(=ScenarioDoc 덤프)에서 시나리오를 회수한다."""
    out: list[tuple[str, ScenarioDoc]] = []
    build_root = REPO_ROOT / "data" / "build"
    if not build_root.is_dir():
        return out
    for sd in sorted(build_root.glob("*/scene-data.json")):
        try:
            out.append((sd.parent.name, ScenarioDoc.model_validate(json.loads(sd.read_text("utf-8")))))
        except Exception:  # noqa: BLE001 — 옛 스키마 산출물은 표본에서 제외
            continue
    return out


@pytest.fixture(scope="module")
def fresh_build(tmp_path_factory) -> Path:
    """현행 build.py 로 새로 조립한 렌더 패키지. 옛 빌드 잔재를 검사하지 않기 위함이다."""
    docs = _scenario_docs()
    if not docs:
        pytest.skip("data/build/*/scene-data.json 표본 없음 — wda build 를 먼저 실행하라")
    slug, doc = docs[0]
    out = tmp_path_factory.mktemp("offline_build") / slug
    build_render_package(doc, out, modules_root=REPO_ROOT / "modules")
    return out


def test_fresh_build_has_no_external_load_refs(fresh_build: Path) -> None:
    """엔트리·씬·토큰·vendor 어디에도 외부 스킴 로드 참조가 없어야 한다."""
    hits = _external_refs(fresh_build)
    assert hits == [], "외부 로드 참조 발견:\n" + "\n".join(
        f"  {f}:{n} → {r}" for f, n, r in hits
    )


def test_fresh_build_has_no_cdn_urls(fresh_build: Path) -> None:
    """CDN 도메인 금지 목록이 산출물에 스킴째로 등장하면 안 된다."""
    hits = _cdn_hits(fresh_build)
    assert hits == [], "CDN URL 발견:\n" + "\n".join(f"  {f}:{n} → {r}" for f, n, r in hits)


def test_fresh_build_ships_local_assets(fresh_build: Path) -> None:
    """오프라인 렌더에 필요한 로컬 사본이 빠짐없이 들어 있어야 한다."""
    missing = [rel for rel in _REQUIRED_LOCAL if not (fresh_build / rel).is_file()]
    assert missing == [], f"로컬 자산 누락: {missing}"


def test_entry_font_face_points_at_local_woff2(fresh_build: Path) -> None:
    """@font-face src 가 로컬 ./fonts/ 를 가리켜야 한다 (jsdelivr Pretendard 회귀 방지)."""
    html = (fresh_build / ENTRY_NAME).read_text(encoding="utf-8")
    faces = re.findall(r"@font-face\{[^}]*\}", html)
    assert faces, "엔트리에 @font-face 가 없다"
    for face in faces:
        srcs = re.findall(r"""src:\s*url\(\s*['"]?([^'")]+)""", face)
        assert srcs, f"@font-face 에 src 없음: {face[:120]}"
        for s in srcs:
            assert s.startswith("./fonts/"), f"비로컬 폰트 참조: {s}"


def test_repo_web_assets_have_no_cdn_urls() -> None:
    """빌드로 복사되는 원본(web/runtime·templates·tokens·vendor)에도 CDN 참조가 없어야 한다.

    support.js 는 빌드 산출물에 복사되지 않는 CDN 부트스트랩 경로라 대상에서 제외한다.
    """
    hits: list[tuple[str, int, str]] = []
    for sub in ("runtime", "templates", "tokens", "vendor"):
        root = REPO_ROOT / "web" / sub
        if not root.is_dir():
            continue
        for f, n, r in _cdn_hits(root):
            if sub == "runtime" and Path(f).name == "support.js":
                continue
            hits.append((f"web/{sub}/{f}", n, r))
    assert hits == [], "원본 자산에 CDN URL:\n" + "\n".join(
        f"  {f}:{n} → {r}" for f, n, r in hits
    )


def test_sif_definition_pins_offline_env() -> None:
    """SIF 정의가 브라우저 경로 고정·다운로드 차단·데이터 경로 매핑을 선언해야 한다."""
    def_path = REPO_ROOT / "deploy" / "apptainer" / "wda-render.def"
    assert def_path.is_file(), f"SIF 정의 없음: {def_path}"
    text = def_path.read_text(encoding="utf-8")
    for token in (
        "PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright",
        "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1",
        "WDA_DATA_DIR=/data",
    ):
        assert token in text, f"SIF 정의에 {token} 선언 없음"
