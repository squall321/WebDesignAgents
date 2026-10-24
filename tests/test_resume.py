# 파이프라인 재개 계약 — 끊긴 자리부터 다시 돈다 (PLAN M3 검증 ④)
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wdpipeline.resume import STAGES, resume_point, stage_state, stages_from


def _write(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def test_empty_run_resumes_from_the_first_stage(tmp_path: Path):
    assert resume_point(tmp_path) == "ingest"


def test_resume_point_is_the_first_missing_output(tmp_path: Path):
    _write(tmp_path / "report.norm.json", {"a": 1})
    assert resume_point(tmp_path) == "fragmentize"
    _write(tmp_path / "fragments.json", [])
    assert resume_point(tmp_path) == "scenario"


def test_truncated_output_counts_as_missing(tmp_path: Path):
    """쓰다 만 파일이 남을 수 있다 — 존재만으로는 끝났다고 볼 수 없다."""
    (tmp_path / "report.norm.json").write_text('{"a": ', encoding="utf-8")
    assert resume_point(tmp_path) == "ingest"


def test_empty_file_counts_as_missing(tmp_path: Path):
    (tmp_path / "report.norm.json").write_text("", encoding="utf-8")
    assert resume_point(tmp_path) == "ingest"


def test_later_outputs_do_not_skip_a_broken_earlier_stage(tmp_path: Path):
    """뒤 산출물이 남아 있어도 앞이 깨졌으면 그것은 옛 입력으로 만들어진 것이다."""
    _write(tmp_path / "fragments.json", [])
    _write(tmp_path / "scenario.json", {"scenes": []})
    assert resume_point(tmp_path) == "ingest", "앞 단계를 건너뛰면 안 된다"


def test_build_is_judged_by_its_own_artifacts(tmp_path: Path):
    pipe, build = tmp_path / "pipe", tmp_path / "build"
    for name in ("report.norm.json", "fragments.json", "scenario.json"):
        _write(pipe / name, {})
    assert resume_point(pipe, build) == "build"
    build.mkdir(parents=True, exist_ok=True)
    (build / "index.html").write_text("<html>", encoding="utf-8")
    _write(build / "scene-data.json", {"scenes": []})
    assert resume_point(pipe, build) is None, "전부 있으면 다시 돌릴 것이 없다"


def test_stages_from_covers_the_tail():
    assert stages_from("scenario") == ("scenario", "build")
    assert stages_from(None) == ()
    with pytest.raises(ValueError, match="알 수 없는 단계"):
        stages_from("없는단계")


def test_stage_state_reports_every_stage(tmp_path: Path):
    state = stage_state(tmp_path)
    assert set(state) == set(STAGES), "단계 하나가 빠지면 재개 지점이 틀린다"


def test_resume_is_reachable_from_cli_and_web():
    """창구 대칭 — 한쪽에서만 재개되면 다른 쪽 사용자는 처음부터 돌려야 한다."""
    import inspect

    from wdpipeline import cli
    from wdweb import runs as runledger
    from wdweb.app import app

    assert callable(getattr(cli, "resume", None))
    assert callable(getattr(runledger, "resume_run", None))
    assert "start_from" in inspect.signature(runledger._run_pipeline).parameters
    routes = {(m, getattr(r, "path", "")) for r in app.routes
              for m in (getattr(r, "methods", set()) or set())}
    assert ("POST", "/api/runs/{run_id}/resume") in routes


def test_failure_injection_then_resume_completes(tmp_path: Path, monkeypatch):
    """실패를 주입하고 재개해 완주하는가 — PLAN M3 검증 ④ 의 본문.

    재개가 앞 단계를 **다시 돌리지 않는다**는 것도 함께 본다. 다시 돌리면 재개가 아니라
    재실행이고, 사람이 고쳐 둔 중간 산출물을 덮어쓴다.
    """
    import time

    from fastapi.testclient import TestClient

    import wdpipeline.fragmentize as frag
    import wdpipeline.ingest as ing
    from wdweb import runs as runledger
    from wdweb.app import app

    monkeypatch.setattr(runledger, "data_dir", lambda: tmp_path)

    report = json.loads(
        Path("examples/reportarchive/report_sample.json").read_text(encoding="utf-8"))

    calls = {"ingest": 0, "frag": 0}
    real_ingest, real_frag = ing.ingest_report_file, frag.fragmentize

    def counted_ingest(path):
        calls["ingest"] += 1
        return real_ingest(path)

    def flaky_frag(norm):
        calls["frag"] += 1
        if calls["frag"] == 1:
            raise RuntimeError("주입된 실패 — 조각 분해 중단")
        return real_frag(norm)

    monkeypatch.setattr(ing, "ingest_report_file", counted_ingest)
    monkeypatch.setattr(frag, "fragmentize", flaky_frag)

    # with 를 쓰지 않는다 — lifespan 이 MCP 세션 매니저를 띄우는데 그건 프로세스당 1회다
    # (전체 스위트에서 다른 웹 테스트가 이미 띄운다). tests/test_wdweb_api.py 와 같은 방식.
    client = TestClient(app)
    if True:
        run_id = client.post(
            "/api/runs", json={"report_json": report, "slug": "resume-it"}
        ).json()["data"]["run_id"]

        def wait() -> dict:
            for _ in range(120):
                d = client.get(f"/api/runs/{run_id}").json()["data"]
                if d["status"] in ("done", "failed"):
                    return d
                time.sleep(0.5)
            pytest.fail("파이프라인이 끝나지 않았다")

        first = wait()
        assert first["status"] == "failed"
        stages = {s["stage"]: s["status"] for s in first["stages"]}
        assert stages["ingest"] == "done" and stages["fragmentize"] == "failed"

        r = client.post(f"/api/runs/{run_id}/resume")
        assert r.status_code == 202
        assert r.json()["data"]["start_from"] == "fragmentize"

        second = wait()
        assert second["status"] == "done", second.get("error")
        assert all(s["status"] == "done" for s in second["stages"])

    assert calls["ingest"] == 1, "재개가 ingest 를 다시 돌렸다 — 그건 재실행이다"
    assert calls["frag"] == 2, "fragmentize 는 실패분 포함 두 번 돌아야 한다"
