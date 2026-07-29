# 발표 레이아웃 템플릿 4종에 wdqa 게이트 1~7 전수 실행 — error 0 (게이트 5 오버플로는 max 픽스처까지)
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"

# (모듈 디렉터리, 템플릿 id, 씬 이름, 게이트를 돌릴 픽스처)
# max/deep 은 밀도 상한 — 게이트 5(오버플로)가 걸린다면 여기서 걸린다
CASES = [
    ("l-split", "tpl.l-split", "2단", "typical"),
    ("l-split", "tpl.l-split", "2단", "max"),
    ("l-split", "tpl.l-split", "2단", "note"),
    ("l-list", "tpl.l-list", "목록", "typical"),
    ("l-list", "tpl.l-list", "목록", "max"),
    ("l-tree", "tpl.l-tree", "계층", "typical"),
    ("l-tree", "tpl.l-tree", "계층", "max"),
    ("l-tree", "tpl.l-tree", "계층", "deep"),
    ("l-quote", "tpl.l-quote", "각인", "typical"),
    ("l-quote", "tpl.l-quote", "각인", "max"),
]


def _entry_for(mod: str, fixture: str) -> Path:
    """preview.html 을 픽스처 고정 엔트리로 복제한다 (같은 디렉터리 = 상대 경로 그대로 유효)."""
    src = (TPL_DIR / mod / "preview.html").read_text(encoding="utf-8")
    fixed = src.replace(
        "(new URLSearchParams(location.search).get('fixture') || 'typical')",
        f"('{fixture}')",
    )
    assert fixed != src, "프리뷰의 픽스처 선택 표현식을 찾지 못했다"
    p = TPL_DIR / mod / f"_qa_{fixture}.html"
    p.write_text(fixed, encoding="utf-8")
    return p


def _scenario(mod: str, tpl: str, scene: str, fixture: str) -> dict:
    nat = yaml.safe_load((TPL_DIR / mod / "module.yaml").read_text(encoding="utf-8"))["nat_default"]
    data = json.loads((TPL_DIR / mod / "fixtures" / f"{fixture}.json").read_text(encoding="utf-8"))
    return {
        "tokens_theme": "hwax-blue",
        "scenes": [{"name": scene, "dur": float(nat), "nat": float(nat), "tpl": tpl}],
        "content": {mod: data},
    }


@pytest.fixture(scope="module")
def gate_results(tmp_path_factory) -> dict:
    from wdqa.config import QAConfig
    from wdqa.gates import run_gates

    cfg = QAConfig(reports_root=tmp_path_factory.mktemp("qa_reports"))
    out: dict = {}
    entries: list[Path] = []
    try:
        for mod, tpl, scene, fixture in CASES:
            entry = _entry_for(mod, fixture)
            entries.append(entry)
            out[f"{mod}:{fixture}"] = run_gates(
                entry, scenario=_scenario(mod, tpl, scene, fixture), config=cfg
            )
    finally:
        for p in entries:
            p.unlink(missing_ok=True)
    return out


@pytest.mark.parametrize("mod,tpl,scene,fixture", CASES)
def test_gates_have_no_errors(gate_results, mod, tpl, scene, fixture):
    res = gate_results[f"{mod}:{fixture}"]
    errors = [r for r in res["results"] if r["severity"] == "error"]
    assert not errors, f"{mod}/{fixture}: 게이트 error {len(errors)}건 — {errors[:6]}"
    assert res["passed"], f"{mod}/{fixture}: passed=False — {res['summary']}"


@pytest.mark.parametrize("mod,tpl,scene,fixture", CASES)
def test_all_seven_gates_ran(gate_results, mod, tpl, scene, fixture):
    """게이트를 골라 돌리지 않았다 — 1~7 전수 실행 결과다."""
    res = gate_results[f"{mod}:{fixture}"]
    report = json.loads(Path(res["report_path"]).read_text(encoding="utf-8"))
    assert set(report["gates_run"]) == {
        "mapping", "length", "contrast", "font", "overflow", "determinism", "frame_match"
    }, report["gates_run"]


@pytest.mark.parametrize("mod,tpl,scene,fixture", CASES)
def test_no_overflow_warnings_either(gate_results, mod, tpl, scene, fixture):
    """게이트 5 는 error 뿐 아니라 warning(카드 밀림·safe margin 접근)도 없어야 한다.

    밀도를 올린 이번 라운드에서 여백이 실제로 남아 있는지의 증거다.
    """
    res = gate_results[f"{mod}:{fixture}"]
    bad = [r for r in res["results"] if r["gate"] == 5 and r["severity"] in ("error", "warning")]
    assert not bad, f"{mod}/{fixture}: 게이트 5 지적 — {bad[:6]}"
