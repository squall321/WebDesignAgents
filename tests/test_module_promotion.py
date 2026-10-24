# 모듈 승격 계약 — 창작물이 재사용 자산이 되는 관문 (PLAN §6)
from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from wdpipeline.module import (
    ACTIVE_MIN_USAGE,
    MODULE_PROMOTION_PATH,
    count_module_usage,
    module_status,
    promote_module,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
GO = [{"meeting_id": "m1", "type": "module_review", "verdict": "Go"}]


@pytest.fixture
def sandbox(tmp_path: Path) -> Path:
    """실물 modules/ 를 복사해 status 를 마음대로 바꿔 본다."""
    dst = tmp_path / "modules"
    shutil.copytree(REPO_ROOT / "modules", dst)
    return dst


def _set(sandbox: Path, module_id: str, **fields) -> Path:
    reg = yaml.safe_load((sandbox / "registry.yaml").read_text(encoding="utf-8"))
    entry = next(m for m in reg["modules"] if m["id"] == module_id)
    mod_yaml = sandbox.parent / entry["path"] / "module.yaml"
    data = yaml.safe_load(mod_yaml.read_text(encoding="utf-8"))
    data.setdefault("quality", {}).update(fields)
    mod_yaml.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                        encoding="utf-8")
    return mod_yaml


def test_promotion_ladder_matches_the_format_one():
    """포맷과 같은 사다리를 쓴다 — 두 자산이 다른 말을 하면 배우는 사람이 혼란스럽다."""
    assert MODULE_PROMOTION_PATH == {"draft": "pilot", "pilot": "active"}


def test_module_review_is_required(sandbox: Path):
    """게이트를 다 통과해도 심의 없이는 못 올라간다 (PLAN §6)."""
    r = promote_module("vtpl.hook", evidence={}, modules_root=sandbox, apply=False)
    assert r["promoted"] is False
    assert any("module_review" in m for m in r["missing"])


def test_rejected_verdict_blocks(sandbox: Path):
    r = promote_module("vtpl.hook", modules_root=sandbox, apply=False, evidence={
        "verdicts": [{"meeting_id": "m2", "type": "module_review", "verdict": "No-Go"}]})
    assert r["promoted"] is False
    assert any("No-Go" in m for m in r["missing"])


def test_gates_record_is_required(sandbox: Path):
    """창작물은 게이트 1~7 통과 + 심의를 거쳐야 한다 — 심의만으로는 안 된다."""
    _set(sandbox, "vtpl.hook", gates_passed=[])
    r = promote_module("vtpl.hook", evidence={"verdicts": GO},
                       modules_root=sandbox, apply=False)
    assert r["promoted"] is False
    assert any("게이트" in c["name"] and not c["ok"] for c in r["checks"])


def test_reproducibility_is_required(sandbox: Path):
    """재현력이 없으면 재사용 자산이 아니다 — 같은 코드가 같은 그림을 내야 한다."""
    _set(sandbox, "vtpl.hook", reproducibility={"verdict": "fail", "max_diff_ratio": 0.4})
    r = promote_module("vtpl.hook", evidence={"verdicts": GO},
                       modules_root=sandbox, apply=False)
    assert r["promoted"] is False
    assert any("재현력" in c["name"] and not c["ok"] for c in r["checks"])


def test_active_additionally_requires_real_usage(sandbox: Path, tmp_path: Path):
    """쓰이지 않은 모듈을 기본값으로 올리면 재사용률이 숫자만 오른다."""
    reg_path = sandbox / "registry.yaml"
    reg = yaml.safe_load(reg_path.read_text(encoding="utf-8"))
    next(m for m in reg["modules"] if m["id"] == "vtpl.hook")["status"] = "pilot"
    reg_path.write_text(yaml.safe_dump(reg, allow_unicode=True, sort_keys=False),
                        encoding="utf-8")

    empty = tmp_path / "pipeline"
    empty.mkdir()
    r = promote_module("vtpl.hook", evidence={"verdicts": GO}, modules_root=sandbox,
                       pipeline_dir=empty, apply=False)
    assert r["target"] == "active"
    usage = next(c for c in r["checks"] if c["name"] == "실사용")
    assert usage["ok"] is False and f"필요 {ACTIVE_MIN_USAGE}" in usage["detail"]


def test_usage_counts_real_scenarios():
    """tpl 참조→모듈 id 변환은 build 정본을 쓴다 — 다시 파싱하면 vtpl 규칙이 갈라진다."""
    runs = count_module_usage("vtpl.stack")
    assert "short_v1" in runs and "short_v2" in runs


def test_vtpl_stack_was_actually_promoted():
    """모듈 승격 루프 실가동 1건 (PLAN M3 검증 ⑤)."""
    assert module_status("vtpl.stack") == "pilot"
    data = yaml.safe_load(
        (REPO_ROOT / "modules" / "scene-templates" / "v-stack" / "module.yaml")
        .read_text(encoding="utf-8"))
    reviews = (data.get("quality") or {}).get("reviews") or []
    assert reviews and reviews[0]["meeting_id"], "승격 근거가 module.yaml 에 없다"


def test_promote_is_a_cli_command():
    import inspect

    from wdpipeline import cli

    assert callable(getattr(cli, "promote", None))
    assert {"kind", "target_id", "apply"} <= set(inspect.signature(cli.promote).parameters)
