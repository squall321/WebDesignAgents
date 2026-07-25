# 엔트리 html 발견·서빙 루트 계산·OM_SCENES 추출(ssParse 미러)·프로젝트 jsx 소스 수집 (정적 게이트 공용)
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# ssParse 계약 미러 (web/runtime/animations-v2.jsx ssParse — 16KB·1~50씬·dur∈(0,300])
OM_SCENES_MAX_CHARS = 16 * 1024
OM_SCENES_MAX_COUNT = 50

# 엔진·벤더 파일 — 게이트 스캔에서 제외 (web/runtime 불가침 + vendor)
RUNTIME_BASENAMES = {"animations-v2.jsx", "support.js"}

_OM_SCENES_RE = re.compile(
    r"window\.OM_SCENES\s*=\s*(?P<q>['\"])(?P<body>(?:\\.|(?!(?P=q))[^\\])*)(?P=q)"
)
_ESCAPE_RE = re.compile(r"\\u([0-9a-fA-F]{4})|\\x([0-9a-fA-F]{2})|\\(.)")
_SIMPLE_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "0": "\0"}
_INLINE_BABEL_RE = re.compile(
    r"<script\b[^>]*type=[\"']text/babel[\"'][^>]*>(?P<body>.*?)</script>",
    re.DOTALL | re.IGNORECASE,
)
_SCRIPT_SRC_RE = re.compile(r"<script\b[^>]*\bsrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
_XIMPORT_FROM_RE = re.compile(r"<x-import\b[^>]*\bfrom=[\"']([^\"']+)[\"']", re.IGNORECASE)
_UPREF_RE = re.compile(r"(?:\.\./)+")


def js_unquote(body: str) -> str:
    """JS 문자열 리터럴 본문의 이스케이프를 해제한다 (한글 리터럴 보존)."""

    def repl(m: re.Match) -> str:
        if m.group(1) is not None:
            return chr(int(m.group(1), 16))
        if m.group(2) is not None:
            return chr(int(m.group(2), 16))
        c = m.group(3)
        return _SIMPLE_ESCAPES.get(c, c)

    return _ESCAPE_RE.sub(repl, body)


def strip_js_comments(src: str) -> str:
    """문자열 리터럴을 보존하며 //·/* */ 주석을 제거한다 (정적 근사 린트용)."""
    out: list[str] = []
    i, n = 0, len(src)
    state = ""  # ''|quote char|'line'|'block'
    while i < n:
        c = src[i]
        nxt = src[i + 1] if i + 1 < n else ""
        if state == "":
            if c in "'\"`":
                state = c
                out.append(c)
            elif c == "/" and nxt == "/":
                state = "line"
                i += 1
            elif c == "/" and nxt == "*":
                state = "block"
                i += 1
            else:
                out.append(c)
        elif state == "line":
            if c == "\n":
                state = ""
                out.append(c)
        elif state == "block":
            if c == "*" and nxt == "/":
                state = ""
                i += 1
        else:  # 문자열 내부
            out.append(c)
            if c == "\\" and nxt:
                out.append(nxt)
                i += 1
            elif c == state:
                state = ""
        i += 1
    return "".join(out)


def parse_om_scenes(raw: str) -> tuple[list[dict] | None, str | None]:
    """ssParse 규칙 미러 — (씬 리스트, 오류 메시지)를 반환한다. 위반 시 (None, 사유)."""
    if not raw:
        return None, "OM_SCENES 문자열이 비어 있다"
    if len(raw) > OM_SCENES_MAX_CHARS:
        return None, f"OM_SCENES 길이 {len(raw)} > {OM_SCENES_MAX_CHARS} (16KB 상한)"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return None, f"OM_SCENES JSON 파싱 실패: {e}"
    if not isinstance(parsed, list) or not parsed:
        return None, "OM_SCENES 는 비어있지 않은 배열이어야 한다"
    if len(parsed) > OM_SCENES_MAX_COUNT:
        return None, f"씬 수 {len(parsed)} > {OM_SCENES_MAX_COUNT}"
    for i, s in enumerate(parsed):
        if not isinstance(s, dict):
            return None, f"씬[{i}] 이 객체가 아니다"
        if not isinstance(s.get("name"), str):
            return None, f"씬[{i}].name 이 문자열이 아니다"
        dur = s.get("dur")
        if not isinstance(dur, (int, float)) or isinstance(dur, bool):
            return None, f"씬[{i}].dur 이 숫자가 아니다"
        if not (0 < float(dur) <= 300):
            return None, f"씬[{i}].dur={dur} 가 (0,300] 범위를 벗어났다"
    return parsed, None


@dataclass
class JsxSource:
    """게이트 스캔 대상 jsx 소스 1개 (인라인 스크립트 또는 파일)."""

    label: str  # 리포트 path 표기 (예: "preview.html#inline-1", "scenes.jsx")
    text: str
    inline: bool = False


@dataclass
class StaticContext:
    """정적 게이트 공용 입력 — 엔트리 파싱 결과."""

    serve_root: Path
    entry_rel: str
    entry_path: Path
    html: str
    om_scenes_raw: str | None = None
    scenes: list[dict] | None = None
    scenes_error: str | None = None
    sources: list[JsxSource] = field(default_factory=list)  # 프로젝트+토큰+템플릿 (runtime 제외)


def _is_runtime_path(p: str) -> bool:
    base = Path(p).name
    if base in RUNTIME_BASENAMES:
        return True
    posix = Path(p).as_posix()
    return "web/runtime/" in posix or "/vendor/" in posix or posix.startswith("vendor/")


def resolve_entry(build_dir: Path) -> tuple[Path, str, Path]:
    """(서빙 루트, 엔트리 상대경로, 엔트리 절대경로)를 계산한다.

    build_dir 가 html 파일이면 그것이 엔트리. 디렉터리면 *.dc.html → preview.html →
    아무 *.html 순으로 발견. 서빙 루트는 엔트리가 참조하는 최대 ../ 깊이만큼 위로 올린다.
    """
    build_dir = Path(build_dir).resolve()
    if build_dir.is_file():
        entry = build_dir
    else:
        candidates = sorted(build_dir.glob("*.dc.html"))
        if not candidates and (build_dir / "preview.html").exists():
            candidates = [build_dir / "preview.html"]
        if not candidates:
            candidates = sorted(build_dir.glob("*.html"))
        if not candidates:
            raise FileNotFoundError(f"엔트리 html 을 찾지 못했다: {build_dir}")
        entry = candidates[0]
    html = entry.read_text(encoding="utf-8")
    updepth = max((m.group(0).count("../") for m in _UPREF_RE.finditer(html)), default=0)
    serve_root = entry.parent
    for _ in range(updepth):
        if serve_root.parent == serve_root:
            break
        serve_root = serve_root.parent
    entry_rel = entry.relative_to(serve_root).as_posix()
    return serve_root, entry_rel, entry


def load_static_context(build_dir: Path) -> StaticContext:
    """엔트리를 읽어 OM_SCENES·jsx 소스를 수집한다."""
    serve_root, entry_rel, entry = resolve_entry(build_dir)
    html = entry.read_text(encoding="utf-8")
    ctx = StaticContext(
        serve_root=serve_root, entry_rel=entry_rel, entry_path=entry, html=html
    )

    m = _OM_SCENES_RE.search(html)
    if m:
        ctx.om_scenes_raw = js_unquote(m.group("body"))
        ctx.scenes, ctx.scenes_error = parse_om_scenes(ctx.om_scenes_raw)
    else:
        ctx.scenes_error = "엔트리에서 window.OM_SCENES 리터럴을 찾지 못했다"

    # 인라인 babel 스크립트
    for i, im in enumerate(_INLINE_BABEL_RE.finditer(html), start=1):
        body = im.group("body")
        if body.strip():
            ctx.sources.append(
                JsxSource(label=f"{entry_rel}#inline-{i}", text=body, inline=True)
            )

    # script src / x-import from 참조 파일 (엔트리 기준 상대, runtime·vendor 제외)
    refs: list[str] = []
    refs.extend(_SCRIPT_SRC_RE.findall(html))
    for from_attr in _XIMPORT_FROM_RE.findall(html):
        refs.extend(from_attr.split())
    seen: set[Path] = set()
    for ref in refs:
        if ref.startswith(("http://", "https://", "//")):
            continue
        if not ref.endswith((".jsx", ".js")):
            continue
        if _is_runtime_path(ref):
            continue
        p = (entry.parent / ref).resolve()
        if p in seen or not p.exists():
            continue
        seen.add(p)
        try:
            label = p.relative_to(serve_root).as_posix()
        except ValueError:
            label = str(p)
        ctx.sources.append(JsxSource(label=label, text=p.read_text(encoding="utf-8")))
    return ctx


# ── 씬 맵 키 정적 추출 (정규식 근사) ─────────────────────────────────────────

_SCENES_ATTR_RE = re.compile(r"<([A-Za-z_$][\w$.]*)\b[^<]*?\bscenes=\{")
_KEY_RE = re.compile(r"(?:['\"]([^'\"]+)['\"]|([A-Za-z_$][\w$]*))\s*:")


def _scan_tag_end(src: str, start: int) -> int:
    """여는 태그의 '>' 위치를 중괄호·문자열 인식 스캔으로 찾는다. 실패 시 -1."""
    depth = 0
    i = start
    quote = ""
    while i < len(src):
        c = src[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = ""
        elif c in "'\"`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == ">" and depth == 0:
            return i
        i += 1
    return -1


def _scan_braced(src: str, start: int) -> tuple[str, int] | None:
    """src[start]=='{' 에서 매칭 '}' 까지의 내부 문자열을 반환한다."""
    if start >= len(src) or src[start] != "{":
        return None
    depth = 0
    quote = ""
    i = start
    while i < len(src):
        c = src[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = ""
        elif c in "'\"`":
            quote = c
        elif c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return src[start + 1 : i], i
        i += 1
    return None


def extract_scene_map_keys(sources: list[JsxSource]) -> tuple[list[str] | None, str | None]:
    """scenes={...} 를 받는 JSX 요소의 children 객체 리터럴 {{ 'k': V }} 에서 키를 추출한다.

    반환: (키 목록, 발견 소스 label). 추출 불가면 (None, None).
    """
    for src in sources:
        text = strip_js_comments(src.text)
        m = _SCENES_ATTR_RE.search(text)
        if not m:
            continue
        tag_end = _scan_tag_end(text, m.end() - 1)
        if tag_end < 0:
            continue
        # 태그 뒤 공백을 건너뛰고 {{ ... }} children 을 찾는다
        j = tag_end + 1
        while j < len(text) and text[j].isspace():
            j += 1
        outer = _scan_braced(text, j)
        if outer is None:
            continue
        inner_src = outer[0].strip()
        inner = _scan_braced(inner_src, 0)
        if inner is None:
            # P4 정본 출력은 children 을 변수 참조({wdaChildren})로 넘긴다 —
            # `const wdaChildren = { ... }` 선언을 찾아 그 객체 리터럴에서 키를 뽑는다.
            ident_m = re.fullmatch(r"[A-Za-z_$][\w$]*", inner_src)
            if not ident_m:
                continue
            decl = re.search(r"(?:const|let|var)\s+" + re.escape(inner_src) + r"\s*=\s*\{", text)
            if not decl:
                continue
            inner = _scan_braced(text, decl.end() - 1)
            if inner is None:
                continue
        keys: list[str] = []
        body = inner[0]
        for km in _KEY_RE.finditer(body):
            keys.append(km.group(1) if km.group(1) is not None else km.group(2))
        if keys:
            return keys, src.label
    return None, None
