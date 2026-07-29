# 포맷 승격 루프 테스트 — 경험(프리셋·교훈·골든)이 format.yaml 에 응축되고 승격이 수치로 판정되는지 검증
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from wdcore.meetings.templates import rounds_for
from wdcore.models.meeting import ArtifactType, MeetingType
from wdpipeline.format import (
    PROMOTION_PATH,
    FormatError,
    format_presets_briefing,
    load_format,
    load_usage,
    promote_format,
    record_usage,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
FORMATS = REPO_ROOT / "formats"


# ── 실물 포맷: 경험이 실제로 채워졌는가 ─────────────────────────────────


def test_short_9x16_carries_the_short_v1_experience():
    """세로 숏폼 심의 19턴의 실측이 format.yaml 에 남아 있어야 한다."""
    spec = load_format("short-9x16")
    assert spec.status == "pilot"
    assert spec.usage_count == 1
    assert spec.origin.meeting_id == "67bd5d0d-e44f-47f1-bc80-d9fa1c10e5ea"

    # 심의가 확정한 구간 예산 — 합계 46.0초 (목표 60을 의도적으로 안 채웠다)
    assert spec.presets.dur_plan == {
        "hook": 6.2, "problem": 11.2, "solution": 11.6, "proof": 9.6, "cta": 7.4
    }
    assert round(sum(spec.presets.dur_plan.values()), 2) == 46.0
    assert spec.duration.min <= 46.0 <= spec.duration.max

    assert spec.presets.deliberation.type == "scenario_build"
    assert spec.presets.deliberation.participants == [
        "narr-story-architect", "narr-copywriter", "ux-audience-advocate",
        "mot-motion-director", "av-narration",
    ]
    assert len(spec.presets.deliberation.agenda) == 4
    assert spec.presets.narration.max_silence == 3.6  # short_v1 씬별 무음 실측 최대(문제 3.56s)
    assert spec.golden.run_id == "short_v1" and spec.golden.registered()
    assert len(spec.lessons) >= 5


def test_short_9x16_copy_guide_matches_vertical_schemas():
    """카피 가이드는 임의 숫자가 아니라 vtpl.* schema.json maxLength 의 사본이어야 한다."""
    spec = load_format("short-9x16")
    dirs = {"hook": "v-hook", "problem": "v-stack", "solution": "v-stack",
            "proof": "v-metric", "cta": "v-cta"}
    for key, limit in spec.presets.copy_guide.items():
        role, path = key.split(".", 1)
        schema = json.loads(
            (REPO_ROOT / "modules" / "scene-templates" / dirs[role] / "schema.json").read_text(
                encoding="utf-8"
            )
        )
        node = schema
        for seg in path.split("."):
            node = node["properties"][seg]
            if node.get("type") == "array":
                node = node["items"]
        assert node["maxLength"] == limit, f"{key} 가이드 {limit} ≠ 스키마 {node.get('maxLength')}"


def test_short_v1_scenario_obeys_its_own_presets():
    """골든 시나리오가 프리셋(구간 예산·자수 상한)을 실제로 지켰는가 — 프리셋이 사후 창작이 아님을 증명."""
    spec = load_format("short-9x16")
    doc = json.loads((REPO_ROOT / "data" / "pipeline" / "short_v1" / "scenario.json").read_text(
        encoding="utf-8"
    ))
    assert doc["format"] == "short-9x16"
    assert [s["dur"] for s in doc["scenes"]] == [
        spec.presets.dur_plan[r] for r in spec.skeleton
    ]
    assert doc["meta"]["duration_sec"] == round(sum(spec.presets.dur_plan.values()), 2)

    over = []
    for key, limit in spec.presets.copy_guide.items():
        role, path = key.split(".", 1)
        node: object = doc["content"][role]
        for seg in path.split("."):
            if isinstance(node, list):
                node = [x[seg] for x in node]
            elif isinstance(node, dict):
                node = node[seg]
        values = node if isinstance(node, list) else [node]
        over += [(key, v) for v in values if len(str(v)) > limit]
    assert over == [], f"자수 상한 초과 {over}"


def test_wide_16x9_carries_the_delib_v2_experience():
    spec = load_format("wide-16x9")
    assert spec.status == "pilot"
    assert spec.usage_count == 2  # delib_v1 · delib_v2
    assert round(sum(spec.presets.dur_plan.values()), 2) == 78.0
    assert spec.golden.run_id == "delib_v2" and spec.golden.registered()
    assert (REPO_ROOT / spec.golden.qa_report).is_file()
    assert any("dataviz" in t for t in spec.lessons)


def test_golden_artifacts_exist():
    """골든이 회귀 기준선이 되려면 파일이 실재해야 한다."""
    for fid in ("short-9x16", "wide-16x9"):
        spec = load_format(fid)
        missing = [a for a in spec.golden.artifacts if not (REPO_ROOT / a).is_file()]
        assert missing == [], f"{fid} 골든 산출물 부재 {missing}"


def test_usage_ledger_matches_usage_count():
    for fid in ("short-9x16", "wide-16x9"):
        runs = load_usage(fid)
        assert len({r["run_id"] for r in runs}) == load_format(fid).usage_count
        assert all(r["gate_errors"] == 0 for r in runs)


def test_wide_active_promotion_blocked_by_missing_format_review():
    """가로는 산출물 2건·골든 등록을 채웠고 남은 미충족은 format_review 하나뿐이다 (apply=False 로 판정만)."""
    r = promote_format("wide-16x9", evidence={"verdicts": []}, apply=False)
    assert r["target"] == "active" and r["promoted"] is False
    named = {c["name"]: c for c in r["checks"]}
    assert named["산출물"]["ok"] and named["골든"]["ok"]
    assert named["format_review"]["ok"] is False
    assert r["missing"] == [named["format_review"]["detail"]]


# ── 승격 판정 규칙 (임시 포맷으로 격리 검증) ────────────────────────────


def _sandbox(tmp_path: Path, fid: str = "short-9x16", **over) -> Path:
    """실물 포맷을 tmp 로 복사해 status 등을 바꿔 놓는다 (template_pool 검사는 실물 modules 사용)."""
    raw = yaml.safe_load((FORMATS / fid / "format.yaml").read_text(encoding="utf-8"))
    raw.update(over)
    (tmp_path / fid).mkdir(parents=True, exist_ok=True)
    (tmp_path / fid / "format.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return tmp_path


GO = [{"meeting_id": "m1", "type": "scenario_build", "verdict": "Conditional-Go"}]


def test_draft_to_pilot_needs_one_artifact(tmp_path: Path):
    root = _sandbox(tmp_path, status="draft", usage_count=0)
    r = promote_format("short-9x16", evidence={"runs": [], "verdicts": GO}, formats_root=root)
    assert r["promoted"] is False
    assert any("산출물 0건 / 필요 1건" in m for m in r["missing"])


def test_draft_to_pilot_needs_zero_gate_errors(tmp_path: Path):
    root = _sandbox(tmp_path, status="draft")
    ev = {"runs": [{"run_id": "r1", "gate_errors": 2}], "verdicts": GO}
    r = promote_format("short-9x16", evidence=ev, formats_root=root)
    assert r["promoted"] is False
    assert any("게이트 error 합계 2건 / 허용 0건" in m for m in r["missing"])


def test_draft_to_pilot_rejects_unrecorded_gates(tmp_path: Path):
    root = _sandbox(tmp_path, status="draft")
    ev = {"runs": [{"run_id": "r1"}], "verdicts": GO}
    r = promote_format("short-9x16", evidence=ev, formats_root=root)
    assert r["promoted"] is False
    assert any("게이트 결과 미기록" in m for m in r["missing"])


def test_draft_to_pilot_rejects_no_go(tmp_path: Path):
    root = _sandbox(tmp_path, status="draft")
    ev = {
        "runs": [{"run_id": "r1", "gate_errors": 0}],
        "verdicts": [{"meeting_id": "m1", "type": "scenario_build", "verdict": "No-Go"}],
    }
    r = promote_format("short-9x16", evidence=ev, formats_root=root)
    assert r["promoted"] is False
    assert any("scenario_build=No-Go" in m for m in r["missing"])


def test_draft_to_pilot_writes_status_back(tmp_path: Path):
    root = _sandbox(tmp_path, status="draft")
    ev = {"runs": [{"run_id": "r1", "gate_errors": 0}], "verdicts": GO}
    r = promote_format("short-9x16", evidence=ev, formats_root=root)
    assert (r["promoted"], r["applied"], r["status"]) == (True, True, "pilot")
    assert load_format("short-9x16", formats_root=root).status == "pilot"


def test_pilot_to_active_needs_golden_and_format_review(tmp_path: Path):
    root = _sandbox(tmp_path, status="pilot", golden={"run_id": "", "artifacts": [], "qa_report": ""})
    ev = {
        "runs": [{"run_id": "r1", "gate_errors": 0}, {"run_id": "r2", "gate_errors": 0}],
        "verdicts": GO,  # 제작 심의만으로는 active 가 되지 않는다
    }
    r = promote_format("short-9x16", evidence=ev, formats_root=root)
    assert r["target"] == "active" and r["promoted"] is False
    assert any("골든 run_id=(미등록)" in m for m in r["missing"])
    assert any("format_review 없음" in m for m in r["missing"])


def test_pilot_to_active_succeeds_with_format_review_go(tmp_path: Path):
    root = _sandbox(tmp_path, status="pilot")
    ev = {
        "runs": [{"run_id": "r1", "gate_errors": 0}, {"run_id": "r2", "gate_errors": 0}],
        "verdicts": [{"meeting_id": "m9", "type": "format_review", "verdict": "Go"}],
    }
    r = promote_format("short-9x16", evidence=ev, formats_root=root)
    assert (r["promoted"], r["status"]) == (True, "active")


def test_active_has_no_next_transition(tmp_path: Path):
    root = _sandbox(tmp_path, status="active")
    r = promote_format("short-9x16", evidence={"verdicts": []}, formats_root=root)
    assert r["target"] is None and r["promoted"] is False
    assert "마지막 단계" in r["missing"][0]
    assert PROMOTION_PATH == {"draft": "pilot", "pilot": "active"}


# ── 사용 원장 ───────────────────────────────────────────────────────────


def test_record_usage_counts_and_dedupes(tmp_path: Path):
    root = _sandbox(tmp_path, status="draft", usage_count=0)
    a = record_usage("short-9x16", "run-a", gate_errors=0, formats_root=root)
    b = record_usage("short-9x16", "run-b", gate_errors=0, formats_root=root)
    dup = record_usage("short-9x16", "run-a", formats_root=root)
    assert (a["usage_count"], b["usage_count"]) == (1, 2)
    assert dup["recorded"] is False and dup["usage_count"] == 2
    assert load_format("short-9x16", formats_root=root).usage_count == 2


def test_record_usage_feeds_promotion_without_explicit_runs(tmp_path: Path):
    """원장이 곧 증거다 — evidence.runs 를 안 줘도 usage.jsonl 로 산출물 건수·게이트를 집계한다."""
    root = _sandbox(tmp_path, status="draft", usage_count=0)
    record_usage("short-9x16", "run-a", gate_errors=0, formats_root=root)
    r = promote_format("short-9x16", evidence={"verdicts": GO}, formats_root=root)
    assert r["promoted"] is True


def test_record_usage_unknown_format(tmp_path: Path):
    with pytest.raises(FormatError, match="포맷 디렉터리 없음"):
        record_usage("nope-1x1", "run-a", formats_root=tmp_path)


def test_line_edit_preserves_comments_and_fields(tmp_path: Path):
    """status·usage_count 갱신은 한 줄 교체다 — 주석과 필드 순서를 재직렬화로 날리지 않는다."""
    (tmp_path / "short-9x16").mkdir(parents=True)
    src = (FORMATS / "short-9x16" / "format.yaml").read_text(encoding="utf-8")
    dst = tmp_path / "short-9x16" / "format.yaml"
    dst.write_text(src, encoding="utf-8")
    record_usage("short-9x16", "run-y", gate_errors=0, formats_root=tmp_path)
    record_usage("short-9x16", "run-z", gate_errors=0, formats_root=tmp_path)
    after = dst.read_text(encoding="utf-8")
    assert "# ── 승격 루프 (PLAN §8.0)" in after
    assert "# 세로 숏폼 시나리오 심의 19턴 (Conditional-Go)" in after
    assert "usage_count: 2" in after
    assert after.splitlines()[0] == src.splitlines()[0]


# ── 프리셋 브리핑 ───────────────────────────────────────────────────────


def test_presets_briefing_carries_the_reusable_knowhow():
    text = format_presets_briefing("short-9x16")
    assert "포맷 short-9x16 — 세로 숏폼 브리핑 (pilot · 산출물 1건)" in text
    assert "무대 1080×1920" in text
    assert "hook(vtpl.hook) → problem(vtpl.stack)" in text
    assert "narr-story-architect" in text                     # 심의 프리셋 참가자
    assert "hook 6.2 · problem 11.2" in text and "합계 46" in text
    assert "hook.line.accent 10자" in text                     # 카피 가이드
    assert "무음 상한 3.6초" in text
    assert "run short_v1" in text                              # 골든
    assert "목표 60초를 채우지 않는다" in text                  # 교훈
    assert "67bd5d0d-e44f-47f1-bc80-d9fa1c10e5ea" in text       # 출처 심의


def test_presets_briefing_skips_empty_sections(tmp_path: Path):
    """프리셋이 비어 있으면(신규 draft) 빈 항목을 늘어놓지 않는다."""
    root = _sandbox(tmp_path, status="draft", usage_count=0, presets={}, golden={}, lessons=[],
                    origin={})
    text = format_presets_briefing("short-9x16", formats_root=root)
    assert "구간 예산" not in text and "골든" not in text and "교훈" not in text
    assert "무대 1080×1920" in text  # 기본 정보는 남는다


# ── 스펙 검증: 프리셋 키가 골격을 벗어나면 거절 ─────────────────────────


def test_reject_dur_plan_role_outside_skeleton(tmp_path: Path):
    root = _sandbox(tmp_path, presets={"dur_plan": {"hook": 6.0, "closing": 8.0}})
    with pytest.raises(FormatError) as e:
        load_format("short-9x16", formats_root=root)
    assert "presets.dur_plan 에 골격 밖 역할 ['closing']" in str(e.value)


def test_reject_copy_guide_role_outside_skeleton(tmp_path: Path):
    root = _sandbox(tmp_path, presets={"copy_guide": {"opening.title": 12}})
    with pytest.raises(FormatError) as e:
        load_format("short-9x16", formats_root=root)
    assert "presets.copy_guide 에 골격 밖 역할 ['opening']" in str(e.value)


def test_origin_created_accepts_yaml_date(tmp_path: Path):
    """created 를 따옴표 없이 써도(YAML date 파싱) 문자열로 받는다."""
    import datetime

    root = _sandbox(tmp_path, origin={"meeting_id": "m1", "created": datetime.date(2026, 7, 27)})
    assert load_format("short-9x16", formats_root=root).origin.created == "2026-07-27"


# ── format_review 회의 유형 ─────────────────────────────────────────────


def test_format_review_meeting_type_registered():
    assert MeetingType("format_review") is MeetingType.format_review
    assert ArtifactType("format_candidate") is ArtifactType.format_candidate
    rounds = rounds_for(MeetingType.format_review)
    assert [r.name for r in rounds] == ["present", "review", "rebuttal", "verdict"]
    assert [r.speaker_order for r in rounds] == [
        "fixed", "round_robin", "round_robin", "fixed"
    ]
    assert rounds[1].citation_required and rounds[2].citation_required


def test_format_review_matches_design_review_shape():
    """design_review 파생 — 라운드 이름·순서·인용 의무가 원형과 같아야 한다."""
    base = rounds_for(MeetingType.design_review)
    got = rounds_for(MeetingType.format_review)
    assert [(r.name, r.speaker_order, r.cycles, r.citation_required) for r in got] == [
        (r.name, r.speaker_order, r.cycles, r.citation_required) for r in base
    ]
