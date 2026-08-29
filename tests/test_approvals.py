# HITL 승인 원장 계약 — 승인이 없을 때 무엇이 막히는가 (PLAN §11)
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wdcore.approvals import (
    HITL_POINTS,
    UNATTENDED_RULES,
    Approval,
    ApprovalStore,
    unattended_mode,
)


def test_plan_defines_five_points():
    assert len(HITL_POINTS) == 5
    assert set(HITL_POINTS) == {
        "participants", "scenario", "shipping", "action_items", "golden"
    }
    for point, why in HITL_POINTS.items():
        assert "—" in why, f"{point}: 이름만 있고 '없으면 무엇이 잘못되는가' 가 없다"


def test_approval_requires_a_reason():
    """이유 없는 승인은 나중에 아무도 되짚을 수 없다."""
    with pytest.raises(ValueError, match="reason"):
        Approval(point="scenario", subject="run-1", reason="")
    Approval(point="scenario", subject="run-1", reason="R4 판정 확인")   # 통과


def test_reject_does_not_need_a_reason_but_blocks(tmp_path: Path):
    store = ApprovalStore(tmp_path)
    store.record(Approval(point="shipping", subject="run-1",
                          decision="reject", reason="무음 4.1초 미해소"))
    assert store.is_approved("shipping", "run-1") is False
    with pytest.raises(PermissionError, match="거절"):
        store.require("shipping", "run-1")


def test_require_blocks_without_approval(tmp_path: Path):
    store = ApprovalStore(tmp_path)
    with pytest.raises(PermissionError, match="승인이 없다"):
        store.require("scenario", "run-2")


def test_unattended_auto_confirms_only_with_evidence(tmp_path: Path):
    """무인 모드는 사람을 없애는 게 아니라 근거가 충분할 때만 대신 눌러 준다."""
    store = ApprovalStore(tmp_path)
    env = {"WDA_UNATTENDED": "1"}

    a = store.require("shipping", "run-3",
                      evidence={"qa_report": "qa.json", "gate_errors": 0}, env=env)
    assert a.mode == "unattended" and a.by == "rule:gates-clean"
    assert store.is_approved("shipping", "run-3")

    with pytest.raises(PermissionError, match="조건 미충족"):
        store.require("shipping", "run-4", evidence={"qa_report": "qa.json"}, env=env)


def test_zero_and_empty_evidence_still_count(tmp_path: Path):
    """gate_errors=0 · validation_errors=[] 은 **좋은 값**이다.

    truthy 로 검사하면 깨끗한 빌드일수록 자동 확정이 거절된다(실측 결함).
    """
    store = ApprovalStore(tmp_path)
    env = {"WDA_UNATTENDED": "1"}
    assert store.require("shipping", "clean",
                         evidence={"qa_report": "q", "gate_errors": 0}, env=env)
    assert store.require("scenario", "clean",
                         evidence={"validation_errors": []}, env=env)


def test_golden_has_no_unattended_rule(tmp_path: Path):
    """회귀 기준선을 무인으로 지우면 가드가 조용히 사라진다 — 사람이 봐야 한다."""
    assert "golden" not in UNATTENDED_RULES
    store = ApprovalStore(tmp_path)
    with pytest.raises(PermissionError, match="무인 자동 확정이 없다"):
        store.require("golden", "tpl.opening", evidence={"anything": 1},
                      env={"WDA_UNATTENDED": "1"})


def test_unattended_is_off_by_default():
    assert unattended_mode({}) is False
    assert unattended_mode({"WDA_UNATTENDED": "1"}) is True


def test_history_accumulates(tmp_path: Path):
    """마지막 결정만 남기면 언제 무엇이 뒤집혔는지 되짚을 수 없다."""
    store = ApprovalStore(tmp_path)
    store.record(Approval(point="scenario", subject="r", reason="1차 승인"))
    store.record(Approval(point="scenario", subject="r", decision="reject", reason="철회"))
    d = json.loads((tmp_path / "scenario" / "r.json").read_text(encoding="utf-8"))
    assert len(d["history"]) == 2
    assert d["latest"]["decision"] == "reject"


def test_approvals_reachable_from_every_interface():
    from wdmcp import server
    from wdpipeline import cli
    from wdweb.app import app

    assert callable(getattr(server, "approval_record", None))
    assert callable(getattr(server, "approval_status", None))
    assert callable(getattr(cli, "approve", None))
    routes = {(m, getattr(r, "path", "")) for r in app.routes
              for m in (getattr(r, "methods", set()) or set())}
    assert ("GET", "/api/approvals") in routes and ("POST", "/api/approvals") in routes


def test_golden_update_requires_a_reason():
    """--update-golden 은 회귀 기준선을 덮어쓴다 — 이유 없이 되면 가드가 사라진다."""
    import inspect

    from wdpipeline import cli
    from wdqa import repro

    assert "golden_reason" in inspect.signature(repro.verify_all).parameters
    src = Path(repro.__file__).read_text(encoding="utf-8")
    assert "골든 갱신에는 이유가 필요하다" in src
    assert "reason" in inspect.signature(cli.repro).parameters


def test_golden_note_lives_next_to_the_snapshot():
    """리포트는 data/(gitignore) 라 다른 체크아웃에 없다 — 이유는 골든 옆에 있어야 한다."""
    from wdqa.repro import GOLDEN_NOTE

    assert GOLDEN_NOTE == "golden.json"
    src = Path(__import__("wdqa.repro", fromlist=["x"]).__file__).read_text(encoding="utf-8")
    assert "golden_unchanged" in src, "픽셀이 같아도 덮어쓰면 리포지터리가 흔들린다"
