# wdqa 런타임 게이트 통합 테스트 — 의도적 위반 빌드로 게이트 3R/4/5/6R/7 검출을 증명하고 정상 빌드 전체 통과 확인
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from wdqa.config import QAConfig
from wdqa.gates import run_gates

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_DIR = REPO_ROOT / "web" / "runtime"
VENDOR_DIR = REPO_ROOT / "web" / "vendor"

_ENTRY = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<script src="./support.js"></script>
</head>
<body>
<x-dc>
<helmet>
<style>html, body { margin: 0; padding: 0; height: 100%; background: #111; }</style>
<script>window.OM_SCENES = '[{"name":"__SCENE__","dur":4}]';</script>
<script>window.OM_PLAYBACK = '{"mode":"times","count":1}';</script>
</helmet>
<x-import component-from-global-scope="__COMP__" from="./animations-v2.jsx ./scenes.jsx" style="position:fixed;inset:0" hint-size="100%,100%"></x-import>
</x-dc>
</body>
</html>
"""

# 의도적 위반 씬 — 저대비·작은 폰트·오버플로·스테이지 이탈·Math.random·프레임 불일치 배경
_BAD_SCENES = """const { SceneStage } = window;
function BadScene({ localTime: t }) {
  return (
    <div style={{ position: 'absolute', inset: 0, fontFamily: 'sans-serif' }}>
      <div style={{ position: 'absolute', inset: 0,
                    background: 'hsl(' + ((t * 977) % 360) + ', 80%, ' + (30 + (t * 53) % 40) + '%)' }}></div>
      <div style={{ position: 'absolute', left: 600, top: 200, width: 520, height: 420,
                    background: '#F6F7FA', padding: 20 }}>
        <div style={{ fontSize: 30, color: '#9AA0AA', background: '#AAB0BA', padding: 8 }}>저대비텍스트</div>
        <div style={{ fontSize: 14, color: '#101B3E' }}>작은글씨</div>
        <div data-qa-icon style={{ fontSize: 14, color: '#101B3E' }}>✓</div>
        <div style={{ width: 260, height: 40, overflow: 'hidden', fontSize: 26, color: '#101B3E',
                      whiteSpace: 'nowrap' }}>컨테이너 너비를 확실히 넘어가는 아주 아주 긴 문장입니다</div>
        <div style={{ fontSize: 30, color: '#101B3E' }}>{Math.random().toFixed(6)}</div>
      </div>
      <div style={{ position: 'absolute', left: 1850, top: 500, fontSize: 30, color: '#101B3E',
                    whiteSpace: 'nowrap' }}>이탈텍스트</div>
      <div data-qa-clip-ok style={{ position: 'absolute', left: 1850, top: 600, fontSize: 30,
                    color: '#101B3E', whiteSpace: 'nowrap' }}>면제텍스트</div>
      {/* 형제 글자 겹침 — 남남끼리 포개진다 */}
      <div style={{ position: 'absolute', left: 200, top: 800, fontSize: 30, color: '#101B3E',
                    whiteSpace: 'nowrap' }}>아래글자겹침</div>
      <div style={{ position: 'absolute', left: 200, top: 812, fontSize: 30, color: '#101B3E',
                    whiteSpace: 'nowrap' }}>위글자겹침</div>
      {/* 강조 span 이 든 한 문장 — 조상·자손이라 겹침이 아니다 */}
      <div style={{ position: 'absolute', left: 200, top: 900, fontSize: 30, color: '#101B3E',
                    whiteSpace: 'nowrap' }}>근거는 실측 <span style={{ fontWeight: 800 }}>0.82mm</span> 다</div>
      {/* 부모 상자 이탈 — 카드 안 글자가 카드 밖으로 나간다 */}
      <div style={{ position: 'absolute', left: 1200, top: 200, width: 200, height: 80,
                    background: '#F6F7FA' }}>
        <div style={{ position: 'absolute', left: 0, top: 120, fontSize: 30, color: '#101B3E',
                      whiteSpace: 'nowrap' }}>카드밖으로</div>
      </div>
      {/* 줄상자 여유만큼 걸친 배지 — 보고하지 않는다 (글자 크기 비례 한계) */}
      <div style={{ position: 'absolute', left: 1500, top: 200, width: 40, height: 62,
                    background: '#E8EAF6' }}>
        <div style={{ position: 'absolute', left: 8, top: 45, fontSize: 17, color: '#101B3E' }}>★</div>
      </div>
      {/* 면제된 쪽이 낀 겹침 — 보고하지 않는다 */}
      <div data-qa-clip-ok style={{ position: 'absolute', left: 900, top: 900, fontSize: 30,
                    color: '#101B3E', whiteSpace: 'nowrap' }}>면제겹침바탕</div>
      <div data-qa-clip-ok style={{ position: 'absolute', left: 900, top: 912, fontSize: 30,
                    color: '#101B3E', whiteSpace: 'nowrap' }}>면제겹침위</div>
    </div>
  );
}
function BadVideo() {
  return (
    <div style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <SceneStage width={1920} height={1080} bg="#F6F7FA" scenes={window.OM_SCENES}
                  playback={window.OM_PLAYBACK}>
        {{ '위반': BadScene }}
      </SceneStage>
    </div>
  );
}
window.BadVideo = BadVideo;
"""

# 정상 씬 — 정적 콘텐츠, 선언된 색 페어만 사용, localTime 무의존
_GOOD_SCENES = """const { SceneStage } = window;
function GoodScene() {
  return (
    <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center',
                  justifyContent: 'center', flexDirection: 'column', gap: 24,
                  fontFamily: 'sans-serif', color: '#101B3E' }}>
      <div style={{ fontSize: 64, fontWeight: 800 }}>정상 씬</div>
      <div style={{ fontSize: 28 }}>모든 게이트를 통과하는 정적 콘텐츠</div>
    </div>
  );
}
function GoodVideo() {
  return (
    <div style={{ position: 'relative', width: '100vw', height: '100vh', overflow: 'hidden' }}>
      <SceneStage width={1920} height={1080} bg="#F6F7FA" scenes={window.OM_SCENES}
                  playback={window.OM_PLAYBACK}>
        {{ '정상': GoodScene }}
      </SceneStage>
    </div>
  );
}
window.GoodVideo = GoodVideo;
"""

_CLEAN_THEME = {
    "id": "test-clean",
    "raw": {"palette": {"bg": "#F6F7FA", "ink": "#101B3E"}},
    "semantic": {
        "contrastPairs": [{"fg": "{palette.ink}", "bg": "{palette.bg}", "role": "본문"}]
    },
}


def _make_build(root: Path, scene_name: str, comp: str, scenes_jsx: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(RUNTIME_DIR / "support.js", root / "support.js")
    shutil.copy2(RUNTIME_DIR / "animations-v2.jsx", root / "animations-v2.jsx")
    (root / "vendor").mkdir()
    for f in ("react.production.min.js", "react-dom.production.min.js", "babel.min.js"):
        shutil.copy2(VENDOR_DIR / f, root / "vendor" / f)
    html = _ENTRY.replace("__SCENE__", scene_name).replace("__COMP__", comp)
    (root / "video.dc.html").write_text(html, encoding="utf-8")
    (root / "scenes.jsx").write_text(scenes_jsx, encoding="utf-8")
    (root / "tokens").mkdir()
    (root / "tokens" / "test-clean.json").write_text(
        json.dumps(_CLEAN_THEME, ensure_ascii=False), encoding="utf-8"
    )
    return root


@pytest.fixture(scope="module")
def bad_build(tmp_path_factory) -> Path:
    return _make_build(
        tmp_path_factory.mktemp("qa_bad"), "위반", "BadVideo", _BAD_SCENES
    )


@pytest.fixture(scope="module")
def good_build(tmp_path_factory) -> Path:
    return _make_build(
        tmp_path_factory.mktemp("qa_good"), "정상", "GoodVideo", _GOOD_SCENES
    )


def _cfg(tmp: Path, **kw) -> QAConfig:
    return QAConfig(reports_root=tmp / "qa_reports", **kw)


def _by_rule(res: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in res["results"]:
        out.setdefault(r["rule"], []).append(r)
    return out


def test_bad_build_all_gates_detect_violations(bad_build: Path, tmp_path: Path):
    scenario = {
        "tokens_theme": "test-clean",
        "scenes": [{"name": "위반", "dur": 4, "narration": "가" * 100}],  # 18.2s > 4s
    }
    res = run_gates(
        bad_build, scenario=scenario,
        config=_cfg(tmp_path, skip_on_phase_failure=False),
    )
    assert res["passed"] is False
    rules = _by_rule(res)

    # 게이트 6 정적 — Math.random
    assert any("Math.random" in r["detail"] for r in rules.get("banned-identifier", []))
    # 게이트 2 — 내레이션 속도 위반 + 최소 dur 제안
    assert any("최소 dur 제안" in r["detail"] for r in rules.get("narration-rate", []))
    # 게이트 3 런타임 — 저대비 실측 + 미선언 조합 경고
    assert any("저대비텍스트" in r["detail"] for r in rules.get("runtime-contrast", []))
    assert rules.get("undeclared-pair"), "미선언 색 조합 경고가 있어야 한다"
    # 게이트 4 — 작은 폰트 오류, data-qa-icon 은 면제
    assert any("작은글씨" in r["detail"] for r in rules.get("min-font", []))
    assert not any("✓" in r["detail"] for r in rules.get("min-font", []))
    # 게이트 5 — 텍스트 오버플로 + 스테이지 이탈, data-qa-clip-ok 는 면제
    assert rules.get("text-overflow")
    assert any("이탈텍스트" in r["detail"] for r in rules.get("stage-exit", []))
    assert not any("면제텍스트" in r["detail"] for r in rules.get("stage-exit", []))
    # 게이트 5 — 형제 글자 겹침(2026-11-17 모듈 심의). 각 요소가 자기 상자에는 꼭 맞으므로
    # text-overflow 로는 잡히지 않는다. 조상·자손과 data-qa-clip-ok 는 빠져야 한다.
    collisions = rules.get("text-collision", [])
    assert any("겹침" in r["detail"] for r in collisions), collisions
    assert all(r["severity"] == "error" for r in collisions)
    assert not any("0.82mm" in r["detail"] for r in collisions), \
        f"강조 span 은 조상·자손이라 겹침이 아니다: {collisions}"
    assert not any("면제겹침" in r["detail"] for r in collisions), \
        f"data-qa-clip-ok 는 면제다: {collisions}"
    # 게이트 5 — 부모 상자(카드·패널) 이탈. 글자 기준이므로 상자만 넘은 경우는 잡지 않는다.
    exits = rules.get("box-exit", [])
    assert any("카드밖으로" in r["detail"] for r in exits), exits
    assert all(r["severity"] == "error" for r in exits)
    # 재는 것이 잉크가 아니라 줄상자라, 몇 px 걸친 배지는 보고하지 않는다 —
    # 한계가 글자 크기에 비례한다(demo_sample 의 ✓ 17px·3px 가 그렇게 잡혔었다).
    assert not any("★" in r["detail"] for r in exits), \
        f"줄상자 여유만큼 걸친 배지는 이탈이 아니다: {exits}"
    # 게이트 6 런타임 — 이중 seek 해시 불일치
    assert rules.get("seek-nondeterministic")
    # 게이트 7 — 씬 경계 프레임 diff 초과
    assert rules.get("frame-match-head") or rules.get("frame-match-tail")
    # 리포트 파일 계약
    report = json.loads(Path(res["report_path"]).read_text(encoding="utf-8"))
    assert report["passed"] is False
    assert {"gate", "rule", "scene", "severity", "detail"} <= set(report["results"][0])


def test_phase_skip_blocks_runtime_on_static_failure(bad_build: Path, tmp_path: Path):
    # skip 모드(opt-in) — S 단계 실패(banned-identifier)로 R/V 를 생략, 브라우저 미기동
    res = run_gates(bad_build, config=_cfg(tmp_path, skip_on_phase_failure=True))
    assert res["passed"] is False
    rules = {r["rule"] for r in res["results"]}
    assert "banned-identifier" in rules
    assert "phase-skipped" in rules
    assert not any(r["rule"].startswith("frame-match") for r in res["results"])
    assert "seek-nondeterministic" not in rules


def test_good_build_passes_all_gates(good_build: Path, tmp_path: Path):
    scenario = {
        "tokens_theme": "test-clean",
        "scenes": [{"name": "정상", "dur": 4, "narration": "짧은 내레이션입니다"}],
    }
    res = run_gates(good_build, scenario=scenario, config=_cfg(tmp_path))
    errors = [r for r in res["results"] if r["severity"] == "error"]
    assert errors == [], errors
    assert res["passed"] is True


def test_gates_selection_and_contract_shape(good_build: Path, tmp_path: Path):
    res = run_gates(good_build, gates=["mapping", "6"], config=_cfg(tmp_path))
    assert set(res) >= {"passed", "results"}
    for r in res["results"]:
        assert {"gate", "rule", "scene", "severity", "detail"} <= set(r)
    with pytest.raises(ValueError):
        run_gates(good_build, gates=["없는게이트"], config=_cfg(tmp_path))
