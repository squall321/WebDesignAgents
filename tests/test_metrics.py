# 성장 지표 계산 계약 — 숫자가 무엇을 세는지 못박는다 (PLAN §11 우상향 장치 ③)
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wdqa.metrics import REUSE_TARGET, first_pass_rate, token_trend


def _qa(dir_: Path, name: str, build: str, at: str, passed: bool) -> None:
    d = dir_ / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "qa.json").write_text(json.dumps({
        "passed": passed, "created_at": at, "build_dir": build,
        "summary": {"error": 0 if passed else 2},
    }), encoding="utf-8")


def test_first_pass_counts_the_first_attempt_not_the_last(tmp_path: Path):
    """고칠 때까지 다시 돌리면 전체 통과율은 1 에 수렴한다 — 처음에 맞았는지를 봐야 한다."""
    _qa(tmp_path, "r1", "build/a", "2026-08-01T10:00:00+00:00", False)
    _qa(tmp_path, "r2", "build/a", "2026-08-01T11:00:00+00:00", True)   # 고쳐서 재시도
    _qa(tmp_path, "r3", "build/b", "2026-08-02T10:00:00+00:00", True)

    r = first_pass_rate(tmp_path)
    assert r["builds"] == 2, "빌드 단위로 묶어야 한다"
    assert r["first_pass"] == 1 and r["rate"] == 0.5, "재시도 성공을 1회차로 세면 안 된다"
    assert r["reports_read"] == 3
    a = next(x for x in r["recent"] if x["build"] == "build/a")
    assert a["attempts"] == 2 and a["passed"] is False


def test_first_pass_survives_broken_reports(tmp_path: Path):
    """리포트 하나가 깨졌다고 지표 전체가 죽으면 대시보드를 못 쓴다."""
    _qa(tmp_path, "ok", "build/a", "2026-08-01T10:00:00+00:00", True)
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "qa.json").write_text("{깨진 json", encoding="utf-8")

    r = first_pass_rate(tmp_path)
    assert r["builds"] == 1 and r["rate"] == 1.0
    assert r["unreadable"] == 1, "읽지 못한 건수를 숨기면 안 된다"


def test_first_pass_is_none_when_there_is_nothing_to_measure(tmp_path: Path):
    """표본이 없을 때 0% 로 보고하면 '품질이 나쁘다' 로 읽힌다 — 없음은 없음이다."""
    r = first_pass_rate(tmp_path)
    assert r["builds"] == 0 and r["rate"] is None


def test_token_trend_reports_its_own_coverage(tmp_path: Path):
    """MCP 경로 회의는 서버가 LLM 을 부르지 않아 토큰이 없다.

    분모를 전체 회의로 잡으면 평균이 거짓이 되므로 계측 범위를 함께 낸다.
    """
    for i, has_usage in enumerate([True, False, False]):
        d = tmp_path / f"m{i}"
        d.mkdir()
        (d / "meta.json").write_text(json.dumps({
            "id": f"m{i}", "type": "design_review", "created_at": f"2026-08-0{i + 1}T00:00:00+00:00",
        }), encoding="utf-8")
        if has_usage:
            (d / "usage.json").write_text(json.dumps({
                "turns_submitted": 10,
                "usage": {"calls": 10, "total_tokens": 5000},
            }), encoding="utf-8")

    t = token_trend(tmp_path)
    assert t["meetings_total"] == 3 and t["meetings_measured"] == 1
    assert t["avg_tokens"] == 5000 and t["per_turn"] == 500
    assert "MCP" in t["coverage_note"], "계측 범위를 설명하지 않으면 평균이 오해된다"


def test_reuse_target_matches_the_plan():
    assert REUSE_TARGET == 0.80, "PLAN §6 의 목표선(80%)과 어긋나면 대시보드가 다른 말을 한다"


def test_metrics_reachable_from_every_interface():
    """지표도 창구 대칭 대상이다 — 한쪽에서만 보이면 다른 쪽 사용자는 모른다."""
    from wdmcp import server
    from wdpipeline import cli
    from wdweb.app import app

    assert callable(getattr(server, "metrics_report", None)), "MCP 도구가 없다"
    assert callable(getattr(cli, "metrics", None)), "CLI 명령이 없다"
    routes = {(m, getattr(r, "path", "")) for r in app.routes
              for m in (getattr(r, "methods", set()) or set())}
    assert ("GET", "/api/metrics") in routes, "웹 API 가 없다"


@pytest.mark.skipif(not Path("data/pipeline").is_dir(), reason="로컬 산출물 필요")
def test_reuse_on_real_data_is_bounded():
    """실 데이터에서 비율이 0~1 밖으로 나가면 계산이 틀린 것이다."""
    from wdqa.metrics import module_reuse

    r = module_reuse(Path("data/pipeline"))
    assert r["runs"] > 0
    assert r["rate"] is None or 0.0 <= r["rate"] <= 1.0
    for row in r["recent"]:
        assert row["reused"] + row["created"] + row["unknown"] == row["scenes"]
