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


# ── 7게이트의 CI 편입 (2026-10-24) ───────────────────────────────────────────


def test_qa_is_a_cli_command_too():
    """게이트가 MCP·웹·콘솔에만 있고 CLI 에 없으면 CI 가 그것을 돌릴 수 없다.

    실제로 그랬다 — `wda revise --rebuild` 의 안내문이 존재하지 않는 `wda qa` 를
    가리키고 있었다(2026-10-24).
    """
    import inspect

    from wdpipeline import cli

    assert callable(getattr(cli, "qa", None)), "wda qa 명령이 없다"
    assert "slug" in inspect.signature(cli.qa).parameters


def test_ci_runs_gates_on_a_real_build():
    """템플릿 픽스처가 아니라 조립된 산출물에 게이트를 돌려야 한다.

    pytest 안의 게이트 호출은 템플릿 단위라 조립 결과의 매핑·길이·대비를 보지 않는다.
    빌드 산출물은 data/(gitignore) 라 CI 에 없으므로 커밋된 시나리오로 직접 굽는다.
    """
    import yaml

    spec = yaml.safe_load((REPO_ROOT / ".github" / "workflows" / "ci.yml")
                          .read_text(encoding="utf-8"))
    steps = " ".join(str(s.get("run", ""))
                     for j in spec["jobs"].values() for s in j["steps"])
    assert "wda build" in steps, "CI 가 빌드를 하지 않으면 게이트를 돌릴 산출물이 없다"
    assert "wda qa" in steps, "7게이트가 CI 에 없다"


def test_gate_fixture_scenario_is_committed():
    """CI 는 새 체크아웃이다 — 빌드할 시나리오가 추적돼 있어야 한다."""
    scen = REPO_ROOT / "data" / "pipeline" / "delib_v2" / "scenario.json"
    assert scen.is_file(), f"게이트 단계가 쓰는 시나리오가 없다: {scen}"
