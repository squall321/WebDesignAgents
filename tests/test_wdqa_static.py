# wdqa 정적·데이터 게이트 단위 테스트 — 브라우저 없이 게이트 1S/2/3S/6S 위반 검출을 증명
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wdqa import gate1_mapping, gate2_length, gate3_contrast, gate6_determinism
from wdqa.config import QAConfig
from wdqa.entry import (
    extract_scene_map_keys,
    load_static_context,
    parse_om_scenes,
    strip_js_comments,
)
from wdqa.wcag import contrast_ratio, parse_css_color

REPO_ROOT = Path(__file__).resolve().parents[1]

_BAD_ENTRY = """<!DOCTYPE html>
<html><head>
<script>window.OM_SCENES = '[{"name":"본문","dur":4},{"name":"유령","dur":2}]';</script>
</head><body>
<x-dc>
<x-import component-from-global-scope="V" from="./animations-v2.jsx ./scenes.jsx"></x-import>
</x-dc>
</body></html>
"""

# '유령' 미매핑 + '고아' 죽은 키 + Math.random 사용. 주석 속 setTimeout 은 잡히면 안 된다.
_BAD_SCENES = """/* setTimeout 이라는 단어가 주석에 있어도 게이트 6은 무시해야 한다 */
const { SceneStage } = window;
function Main({ localTime: t }) {
  const r = Math.random();
  return <div>{r}</div>;
}
function Orphan() { return <div>고아</div>; }
function V() {
  return (
    <SceneStage width={1920} height={1080} bg="#fff" scenes={window.OM_SCENES}>
      {{ '본문': Main, '고아': Orphan }}
    </SceneStage>
  );
}
window.V = V;
"""


@pytest.fixture()
def bad_build(tmp_path: Path) -> Path:
    (tmp_path / "bad.dc.html").write_text(_BAD_ENTRY, encoding="utf-8")
    (tmp_path / "scenes.jsx").write_text(_BAD_SCENES, encoding="utf-8")
    return tmp_path


def _rules(rows: list[dict]) -> set[str]:
    return {r["rule"] for r in rows}


# ── OM_SCENES ssParse 미러 ──────────────────────────────────────────────────

def test_parse_om_scenes_mirrors_ssparse():
    ok, err = parse_om_scenes('[{"name":"a","dur":4}]')
    assert ok and err is None
    assert parse_om_scenes('[{"name":"a","dur":0}]')[0] is None       # dur (0,300]
    assert parse_om_scenes('[{"name":"a","dur":301}]')[0] is None
    assert parse_om_scenes('[]')[0] is None                            # 빈 배열
    many = json.dumps([{"name": f"s{i}", "dur": 1} for i in range(51)])
    assert parse_om_scenes(many)[0] is None                            # 51씬
    assert parse_om_scenes('[{"dur":4}]')[0] is None                   # name 누락


# ── 게이트 1 정적 — 양방향 매핑 대조 ────────────────────────────────────────

def test_gate1_static_detects_both_directions(bad_build: Path):
    ctx = load_static_context(bad_build)
    rows = gate1_mapping.run_static(ctx)
    rules = _rules(rows)
    assert "map-missing" in rules   # '유령' 이 맵에 없다
    assert "map-orphan" in rules    # '고아' 가 OM_SCENES 에 없다
    assert all(r["severity"] == "error" for r in rows)
    assert any(r["scene"] == "유령" for r in rows)
    assert any(r["scene"] == "고아" for r in rows)


def test_gate1_static_real_previews_pass():
    for mod in ("process", "closing"):
        ctx = load_static_context(REPO_ROOT / "modules" / "scene-templates" / mod)
        assert gate1_mapping.run_static(ctx) == []


def test_scene_map_extraction_on_real_example():
    ctx = load_static_context(REPO_ROOT / "examples" / "hwax_intro")
    keys, _ = extract_scene_map_keys(ctx.sources)
    assert keys == ["오프닝", "문제", "심의란", "절차", "자체교정", "실증사례", "클로징"]


# ── 게이트 2 — 글자수 대비 길이 ─────────────────────────────────────────────

def test_gate2_caption_rate_violation_suggests_min_dur():
    cfg = QAConfig()
    data = json.loads(
        (REPO_ROOT / "modules/scene-templates/process/fixtures/typical.json").read_text()
    )
    scenario = {
        "content": {"process": data},
        "scenes": [{"name": "절차", "dur": 3, "tpl": "tpl.process", "data_ref": "content.process"}],
    }
    rows = gate2_length.run_data(scenario, cfg)
    viol = [r for r in rows if r["rule"] == "caption-rate"]
    assert len(viol) == 1 and viol[0]["severity"] == "error"
    assert "최소 dur 제안" in viol[0]["detail"]


def test_gate2_narration_rate_and_stretch():
    cfg = QAConfig()
    scenario = {
        "scenes": [
            {"name": "길다", "dur": 4, "narration": "가" * 100},          # 100/5.5=18.2s > 4s
            {"name": "짧다", "dur": 4, "narration": "짧은 내레이션"},      # 통과
            {"name": "늘림", "dur": 13, "nat": 10, "narration": "가나다"},  # 30% 스트레치
        ]
    }
    rows = gate2_length.run_data(scenario, cfg)
    assert any(r["rule"] == "narration-rate" and r["scene"] == "길다" for r in rows)
    assert not any(r["scene"] == "짧다" and r["severity"] == "error" for r in rows)
    assert any(r["rule"] == "stretch-limit" and r["scene"] == "늘림" for r in rows)


def test_gate2_collect_read_chars_matches_schema():
    schema = json.loads(
        (REPO_ROOT / "modules/scene-templates/process/schema.json").read_text()
    )
    data = json.loads(
        (REPO_ROOT / "modules/scene-templates/process/fixtures/typical.json").read_text()
    )
    # x-read: kicker+title+steps[].name/desc (footnote·frame 제외), 공백 제외 실측 회귀값.
    # 픽스처를 게이트 2 예산(162자)에 맞게 압축한 뒤의 값 — 예산 이내임을 함께 고정한다.
    n = gate2_length.collect_read_chars(schema, data)
    assert n == 130
    assert n <= 18 * 9  # nat 18s × 자막 9자/초


# ── 게이트 3 정적 — WCAG 대비 ───────────────────────────────────────────────

def test_wcag_contrast_math():
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0, abs=0.01)
    assert parse_css_color("#FFFFFFB0") == (255.0, 255.0, 255.0, pytest.approx(0.69, abs=0.01))
    assert parse_css_color("rgba(16, 27, 62, 0.5)") == (16.0, 27.0, 62.0, 0.5)


def _theme(tmp_path: Path, name: str, pairs, palette) -> Path:
    d = tmp_path / "tokens"
    d.mkdir(exist_ok=True)
    doc = {"id": name, "raw": {"palette": palette}, "semantic": {"contrastPairs": pairs}}
    (d / f"{name}.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return tmp_path


def test_gate3_static_flags_low_contrast_pair(tmp_path: Path):
    cfg = QAConfig()
    root = _theme(
        tmp_path, "test-bad",
        [{"fg": "{palette.gray1}", "bg": "{palette.gray2}", "role": "저대비"}],
        {"bg": "#FFFFFF", "gray1": "#777777", "gray2": "#888888"},
    )
    rows = gate3_contrast.run_static("test-bad", root, cfg)
    assert any(r["rule"] == "pair-contrast" and r["severity"] == "error" for r in rows)


def test_gate3_static_clean_theme_passes(tmp_path: Path):
    cfg = QAConfig()
    root = _theme(
        tmp_path, "test-clean",
        [{"fg": "{palette.ink}", "bg": "{palette.bg}", "role": "본문"}],
        {"bg": "#F6F7FA", "ink": "#101B3E"},
    )
    assert gate3_contrast.run_static("test-clean", root, cfg) == []


def test_gate3_static_hwax_blue_passes():
    # 실테마 회귀 — faint 를 #7A8298 로 교정한 뒤로는 선언 페어 전수가 통과해야 한다
    cfg = QAConfig()
    rows = gate3_contrast.run_static("hwax-blue", REPO_ROOT, cfg)
    assert not [r for r in rows if r.get("severity") in ("error", "warning")], rows


def test_gate3_static_detects_bad_pair(tmp_path):
    # 검출력 회귀 — 저대비 페어를 가진 합성 테마는 반드시 잡아야 한다
    import json as _json

    tokens_dir = tmp_path / "web" / "tokens"
    tokens_dir.mkdir(parents=True)
    theme = {
        "id": "bad-theme",
        "raw": {"palette": {"bg": "#F6F7FA", "faint": "#C9CDD8"}},
        "semantic": {"contrastPairs": [
            {"fg": "{palette.faint}", "bg": "{palette.bg}", "role": "저대비 테스트"},
        ]},
    }
    (tokens_dir / "bad-theme.json").write_text(_json.dumps(theme), encoding="utf-8")
    rows = gate3_contrast.run_static("bad-theme", tmp_path, QAConfig())
    assert any(r["rule"] == "pair-contrast" and r["severity"] == "error" for r in rows)


# ── 게이트 6 정적 — 금지 식별자 ─────────────────────────────────────────────

def test_gate6_static_detects_math_random_not_comment(bad_build: Path):
    ctx = load_static_context(bad_build)
    rows = gate6_determinism.run_static(ctx)
    assert any("Math.random" in r["detail"] for r in rows)
    assert not any("setTimeout" in r["detail"] for r in rows)  # 주석은 무시


def test_strip_js_comments_keeps_strings():
    src = "const url = 'https://x/y'; // Math.random\n/* Date.now */ const a = 1;"
    out = strip_js_comments(src)
    assert "https://x/y" in out
    assert "Math.random" not in out and "Date.now" not in out
