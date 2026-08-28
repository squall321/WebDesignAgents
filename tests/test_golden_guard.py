# 골든 회귀 가드 계약 — 가드가 실제로 무는지, 실패 원인을 구분해 말하는지
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_golden_threshold_is_much_tighter_than_frame_match():
    """frame_match(0.02)는 애니메이션 정합용 여유다. 골든에 그대로 쓰면 회귀를 놓친다.

    실측(2026-08-28): 배지 패딩 14→22px·32→56px 라는 눈에 띄는 변경이 0.0251 로 겨우
    0.02 를 넘겼다. 1px 변경(14→15)은 0.0072 라 그냥 통과했을 것이다.
    """
    from wdqa.config import QAConfig

    cfg = QAConfig()
    assert cfg.golden_max_ratio < cfg.frame_match_max_ratio / 5
    assert cfg.golden_max_ratio > 0


def test_golden_threshold_is_overridable_for_other_environments(monkeypatch):
    """다른 크로미움 빌드에서 AA 요동이 나면 코드가 아니라 허용치를 조정해야 한다."""
    from wdqa.config import QAConfig

    monkeypatch.setenv("WDA_GOLDEN_MAX_RATIO", "0.05")
    assert QAConfig().golden_max_ratio == 0.05


def test_every_scene_template_has_a_golden():
    """골든 없는 모듈은 회귀 가드가 없는 모듈이다."""
    reg = yaml.safe_load((REPO_ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    missing = [
        m["id"] for m in reg["modules"]
        if m["type"] == "scene-template"
        and not (REPO_ROOT / m["path"] / "fixtures" / "snapshots" / "typical.png").is_file()
    ]
    assert not missing, f"골든 없는 씬 템플릿: {missing}"


def _report(rows: list[tuple[str, float, float]]) -> dict:
    return {"results": [
        {"module": m, "fixtures": {"typical": {
            "golden_diff_ratio": g, "session_max_diff_ratio": s}}}
        for m, g, s in rows
    ]}


@pytest.mark.parametrize("rows,expect", [
    ([(f"m{i}", 0.004, 0.0) for i in range(40)], "환경 차이"),
    ([("m0", 0.007, 0.0)] + [(f"m{i}", 0.0, 0.0) for i in range(1, 40)], "코드 회귀"),
    ([(f"m{i}", 0.004, 0.001) for i in range(40)], "비결정성"),
])
def test_verdict_separates_environment_from_regression(rows, expect):
    """diff 숫자만으로는 환경 차이와 코드 회귀가 구분되지 않는다 — 고치는 방법이 다르다."""
    from wdpipeline.cli import _repro_verdict

    assert expect in _repro_verdict(_report(rows))


def test_ci_workflow_runs_the_golden_check():
    """골든은 사람이 기억해서 지킬 수 없다 — CI 가 돌지 않으면 가드가 없는 것과 같다."""
    wf = REPO_ROOT / ".github" / "workflows" / "ci.yml"
    assert wf.is_file(), "CI 워크플로가 없다"
    spec = yaml.safe_load(wf.read_text(encoding="utf-8"))
    assert {"test", "golden"} <= set(spec["jobs"])
    steps = " ".join(
        str(s.get("run", "")) for j in spec["jobs"].values() for s in j["steps"]
    )
    assert "wda repro" in steps, "재현력 검증이 CI 에 없다"
    assert "pytest" in steps, "테스트 실행이 CI 에 없다"
    # 크로미움 핀이 곧 골든의 전제다 — playwright 가 박아 주는 빌드를 써야 한다
    assert "playwright install" in steps
