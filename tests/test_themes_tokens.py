# 테마 토큰 4종 검증 — hwax-blue 대비 키 완전성·참조 해석·WCAG 대비 실계산·이징 키 유효성
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TOKENS = ROOT / "web" / "tokens"
ENGINE = ROOT / "web" / "runtime" / "animations-v2.jsx"

BASE_ID = "hwax-blue"
THEMES = ["neutral-slate", "warm-amber", "deep-dark", "fresh-teal"]

AA_NORMAL = 4.5   # WCAG 2.1 AA 본문
AA_LARGE = 3.0    # WCAG 2.1 AA 대형 텍스트(≥24px bold / ≥18.66px)

REF_RE = re.compile(r"^\{([A-Za-z0-9_.\-]+)\}$")


# ── 토큰 문서 유틸 ────────────────────────────────────────────────────────

def load_theme(theme_id: str) -> dict:
    return json.loads((TOKENS / f"{theme_id}.json").read_text(encoding="utf-8"))


def key_paths(node, prefix: str = "") -> set[str]:
    """딕셔너리 키 경로 집합. 배열은 인덱스 대신 '[]' 로 접어 원소 구조만 비교한다."""
    out: set[str] = set()
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{prefix}.{k}" if prefix else k
            out.add(p)
            out |= key_paths(v, p)
    elif isinstance(node, list):
        for item in node:
            out |= key_paths(item, f"{prefix}[]")
    return out


def resolve_ref(doc: dict, path: str):
    """loader.jsx lookupRef 와 동일 규칙 — raw.* 우선, 다음 semantic.*."""
    for space in (doc.get("raw", {}), doc.get("semantic", {})):
        cur = space
        ok = True
        for seg in path.split("."):
            if isinstance(cur, dict) and seg in cur:
                cur = cur[seg]
            else:
                ok = False
                break
        if ok:
            return cur
    raise KeyError(path)


def resolve_node(node, doc):
    if isinstance(node, str):
        m = REF_RE.match(node)
        return resolve_node(resolve_ref(doc, m.group(1)), doc) if m else node
    if isinstance(node, list):
        return [resolve_node(x, doc) for x in node]
    if isinstance(node, dict):
        return {k: resolve_node(v, doc) for k, v in node.items()}
    return node


def iter_refs(node, prefix: str = ""):
    """문서 안의 모든 "{...}" 참조 문자열을 (경로, 참조키) 로 흘린다."""
    if isinstance(node, str):
        m = REF_RE.match(node)
        if m:
            yield prefix, m.group(1)
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from iter_refs(v, f"{prefix}.{k}" if prefix else k)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from iter_refs(v, f"{prefix}[{i}]")


# ── WCAG 상대 휘도·대비비 ─────────────────────────────────────────────────

def _channel(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def parse_color(value: str, backdrop: tuple[float, float, float] | None = None):
    """#RGB/#RRGGBB/#RRGGBBAA → 선형 합성 전 sRGB 튜플. 알파는 backdrop 위로 합성."""
    h = value.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    if len(h) not in (6, 8):
        raise ValueError(f"색 표기를 해석할 수 없다: {value}")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    a = int(h[6:8], 16) / 255 if len(h) == 8 else 1.0
    if a < 1.0:
        bd = backdrop if backdrop is not None else (1.0, 1.0, 1.0)
        r = r * a + bd[0] * (1 - a)
        g = g * a + bd[1] * (1 - a)
        b = b * a + bd[2] * (1 - a)
    return (r, g, b)


def luminance(rgb) -> float:
    r, g, b = (_channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(fg: str, bg: str, backdrop: str | None = None) -> float:
    bd = parse_color(backdrop) if backdrop else None
    lf, lb = luminance(parse_color(fg, bd)), luminance(parse_color(bg, bd))
    hi, lo = max(lf, lb), min(lf, lb)
    return (hi + 0.05) / (lo + 0.05)


def pair_ratios(theme_id: str) -> list[tuple[str, str, str, float]]:
    """테마의 contrastPairs 전수를 실계산 — 반투명 배경은 palette.bg 위로 합성."""
    doc = load_theme(theme_id)
    stage_bg = doc["raw"]["palette"]["bg"]
    out = []
    for pair in doc["semantic"]["contrastPairs"]:
        fg = resolve_node(pair["fg"], doc)
        bg = resolve_node(pair["bg"], doc)
        out.append((pair["role"], fg, bg, contrast(fg, bg, backdrop=stage_bg)))
    return out


def engine_easing_keys() -> set[str]:
    src = ENGINE.read_text(encoding="utf-8")
    start = src.index("const Easing = {")
    depth, i = 0, start + len("const Easing = ")
    while True:
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body = src[start:i + 1]
    return set(re.findall(r"^\s{2}([A-Za-z][A-Za-z0-9]*):", body, re.M))


def collect_eases(node, prefix: str = ""):
    if isinstance(node, dict):
        for k, v in node.items():
            p = f"{prefix}.{k}" if prefix else k
            if k == "ease":
                yield p, v
            else:
                yield from collect_eases(v, p)


# ── 검증 ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("theme_id", THEMES)
def test_theme_file_parses_and_ids_match(theme_id):
    doc = load_theme(theme_id)
    assert doc["id"] == theme_id, f"{theme_id}: id 필드가 파일명과 다르다 — {doc['id']}"
    assert doc.get("name") and doc.get("version") and doc.get("description")


@pytest.mark.parametrize("theme_id", THEMES)
def test_key_set_identical_to_base(theme_id):
    """키 하나라도 빠지면 템플릿이 깨진다 — hwax-blue 와 키 경로 집합이 정확히 같아야 한다."""
    base, doc = key_paths(load_theme(BASE_ID)), key_paths(load_theme(theme_id))
    missing = sorted(base - doc)
    extra = sorted(doc - base)
    assert not missing, f"{theme_id}: 누락 키 {len(missing)}개 — {missing}"
    assert not extra, f"{theme_id}: 기준에 없는 키 {len(extra)}개 — {extra}"


@pytest.mark.parametrize("theme_id", THEMES)
def test_shared_geometry_is_untouched(theme_id):
    """좌표 체계(semantic.layout·radius·type)와 component 기하 수치는 전 테마 공용이다."""
    base, doc = load_theme(BASE_ID), load_theme(theme_id)
    for section in ("layout", "radius", "type"):
        assert doc["semantic"][section] == base["semantic"][section], (
            f"{theme_id}: semantic.{section} 이 기준 테마와 다르다"
        )
    for comp, node in base["component"].items():
        for k, v in node.items():
            if isinstance(v, (int, float)):
                assert doc["component"][comp][k] == v, (
                    f"{theme_id}: component.{comp}.{k} 기하 수치가 {doc['component'][comp][k]} "
                    f"(기준 {v}) — 좌표 체계는 공통이어야 한다"
                )


@pytest.mark.parametrize("theme_id", THEMES)
def test_every_reference_resolves(theme_id):
    """"{palette.*}" 참조가 전부 해석된다 (loader.jsx 와 동일 규칙)."""
    doc = load_theme(theme_id)
    bad = []
    for path, ref in iter_refs(doc):
        try:
            value = resolve_ref(doc, ref)
        except KeyError:
            bad.append((path, ref))
            continue
        if isinstance(value, str) and REF_RE.match(value):
            bad.append((path, ref))   # 참조가 참조를 가리키는 무한 루프 방지
    assert not bad, f"{theme_id}: 해석 실패 참조 — {bad}"


@pytest.mark.parametrize("theme_id", THEMES)
def test_all_colors_are_hex(theme_id):
    doc = load_theme(theme_id)
    bad = []
    for section in ("palette", "extra"):
        for k, v in doc["raw"][section].items():
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", v):
                bad.append((f"{section}.{k}", v))
    assert not bad, f"{theme_id}: 색 표기 위반 — {bad}"


@pytest.mark.parametrize("theme_id", THEMES + [BASE_ID])
def test_contrast_pairs_meet_aa(theme_id):
    """contrastPairs 전수 4.5:1 통과 — AX 페르소나 기준상 미달은 결격이다."""
    rows = pair_ratios(theme_id)
    assert len(rows) == len(load_theme(BASE_ID)["semantic"]["contrastPairs"])
    bad = [(role, fg, bg, round(r, 2)) for role, fg, bg, r in rows if r < AA_NORMAL]
    assert not bad, f"{theme_id}: 4.5:1 미달 {len(bad)}건 — {bad}"


@pytest.mark.parametrize("theme_id", THEMES)
def test_contrast_pair_structure_matches_base(theme_id):
    """대비 쌍의 (fg, bg) 참조 구조가 기준 테마와 같아야 계약이 유지된다."""
    def sig(doc):
        return [(p["fg"], p["bg"]) for p in doc["semantic"]["contrastPairs"]]
    assert sig(load_theme(theme_id)) == sig(load_theme(BASE_ID))


@pytest.mark.parametrize("theme_id", THEMES)
def test_motion_ease_keys_exist_in_engine(theme_id):
    """ease 이름은 엔진 Easing 실제 키여야 한다 (loader.validateEasing 이 던지는 조건)."""
    keys = engine_easing_keys()
    assert "easeOutCubic" in keys and "easeOutBack" in keys, keys
    motion = load_theme(theme_id)["semantic"]["motion"]
    bad = [(p, v) for p, v in collect_eases(motion) if v not in keys]
    assert not bad, f"{theme_id}: 엔진에 없는 이징 키 — {bad} (사용 가능: {sorted(keys)})"


@pytest.mark.parametrize("theme_id", THEMES)
def test_motion_personality_differs_from_base(theme_id):
    """색만 바꾼 테마는 다양성이 아니다 — 모션 프리셋이 기준과 실제로 달라야 한다."""
    base = load_theme(BASE_ID)["semantic"]["motion"]
    doc = load_theme(theme_id)["semantic"]["motion"]
    assert doc != base, f"{theme_id}: 모션 프리셋이 hwax-blue 와 동일하다"
    changed = [k for k in ("rise", "riseSm", "pop", "tag", "exit") if doc[k] != base[k]]
    assert len(changed) >= 3, f"{theme_id}: 바뀐 모션 프리셋이 {changed} 뿐"


@pytest.mark.parametrize("theme_id", THEMES)
def test_motion_durations_fit_still_slack(theme_id):
    """등장 지속시간이 stillOf 여유(마지막 settle + 0.8초)를 넘지 않아야 스틸이 잘리지 않는다."""
    doc = load_theme(theme_id)["semantic"]["motion"]
    for k in ("rise", "riseSm", "pop", "tag"):
        dur = doc[k].get("dur", 0)
        assert dur <= 1.5, f"{theme_id}: motion.{k}.dur={dur} — 스틸 여유(0.8s) 대비 과다"


@pytest.mark.parametrize("theme_id", THEMES)
def test_theme_payload_fits_loader_budget(theme_id):
    """loader.jsx MAX_THEME_BYTES(64KB) 안에 들어와야 OM_THEME 주입이 가능하다."""
    size = len(json.dumps(load_theme(theme_id), ensure_ascii=False).encode("utf-8"))
    assert size < 64 * 1024, f"{theme_id}: 테마 페이로드 {size}B > 64KB"


def test_palettes_are_actually_distinct():
    """4종 + 기준의 강조색·배경이 서로 달라야 '같은 시리즈'를 벗어난다."""
    seen: dict[str, list[str]] = {}
    for theme_id in [BASE_ID] + THEMES:
        p = load_theme(theme_id)["raw"]["palette"]
        seen.setdefault(f"{p['bg']}|{p['blue']}", []).append(theme_id)
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    assert not dupes, f"배경·강조색이 겹치는 테마 — {dupes}"


def test_dark_theme_is_actually_dark():
    """deep-dark 는 배경 휘도가 잉크보다 낮은 반전 구조여야 한다."""
    p = load_theme("deep-dark")["raw"]["palette"]
    assert luminance(parse_color(p["bg"])) < 0.05, "deep-dark 배경이 어둡지 않다"
    assert luminance(parse_color(p["ink"])) > 0.5, "deep-dark 잉크가 밝지 않다"
    assert luminance(parse_color(p["card"])) > luminance(parse_color(p["bg"])), (
        "다크에서 카드는 배경보다 한 단 밝아야 면이 읽힌다"
    )


def test_light_themes_stay_light():
    for theme_id in ("neutral-slate", "warm-amber", "fresh-teal"):
        p = load_theme(theme_id)["raw"]["palette"]
        assert luminance(parse_color(p["bg"])) > 0.8, f"{theme_id}: 배경이 밝지 않다"
        assert luminance(parse_color(p["ink"])) < 0.1, f"{theme_id}: 잉크가 어둡지 않다"


if __name__ == "__main__":
    for theme_id in [BASE_ID] + THEMES:
        print(f"\n== {theme_id} ==")
        for role, fg, bg, r in pair_ratios(theme_id):
            mark = "OK " if r >= AA_NORMAL else ("large" if r >= AA_LARGE else "FAIL")
            print(f"  {r:6.2f}:1  {mark:5s} {fg} on {bg}  — {role}")
