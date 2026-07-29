# 세로 숏폼 규칙 조립 검증 — vtpl.hook/stack/metric/cta 빌더가 short-9x16 을 스키마 통과로 조립하는지
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file
from wdpipeline.scenario import assemble_demo_scenario, validate_scenario

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
SHORT_V1 = REPO_ROOT / "data" / "pipeline" / "short_v1"
MODULES = REPO_ROOT / "modules"
FORMAT = "short-9x16"
RATE = 5.5  # formats/short-9x16 narration.rate


@pytest.fixture(scope="module")
def short_v1_doc():
    """심의 확정본과 같은 입력(short_v1 의 norm+fragments)으로 규칙 조립한 문서."""
    norm = json.loads((SHORT_V1 / "report.norm.json").read_text(encoding="utf-8"))
    frags = json.loads((SHORT_V1 / "fragments.json").read_text(encoding="utf-8"))
    return assemble_demo_scenario(norm, frags, format=FORMAT)


@pytest.fixture(scope="module")
def delib_doc() -> dict:
    """short_v1 심의 확정본 (읽기 전용 — 규칙 조립과의 골격 대조 기준)."""
    return json.loads((SHORT_V1 / "scenario.json").read_text(encoding="utf-8"))


def test_rule_assembly_passes_schema_validation(short_v1_doc):
    """규칙 조립 결과가 vtpl 4종 schema.json 검증을 통과한다 (심의 없이도 유효 문서)."""
    assert validate_scenario(short_v1_doc, modules_root=MODULES) == []


def test_rule_assembly_matches_deliberated_skeleton(short_v1_doc, delib_doc):
    """씬 골격(포맷·tpl 순서·data_ref 역할)이 심의 확정본과 같다 — 심의는 내용만 바꾼다."""
    assert short_v1_doc.format == delib_doc["format"] == FORMAT
    assert [s.tpl for s in short_v1_doc.scenes] == [s["tpl"] for s in delib_doc["scenes"]]
    assert [s.data_ref for s in short_v1_doc.scenes] == [
        s["data_ref"] for s in delib_doc["scenes"]
    ]
    # 역할 키가 content 키 — problem/solution 이 서로 덮어쓰지 않는다
    assert set(short_v1_doc.content) == {"hook", "problem", "solution", "proof", "cta"}


def test_duration_stretched_to_format_target(short_v1_doc):
    """씬 nat 합(48s)이 duration.target(60s)으로 균일 스케일된다."""
    total = round(sum(s.dur for s in short_v1_doc.scenes), 2)
    assert total == 60.0
    assert 40.0 <= total <= 75.0


def test_stack_tone_follows_role_order(short_v1_doc):
    """vtpl.stack 2회 — 첫 호출(problem 역할)은 problem, 두 번째(solution)는 solution."""
    assert short_v1_doc.content["problem"]["tone"] == "problem"
    assert short_v1_doc.content["solution"]["tone"] == "solution"
    for role in ("problem", "solution"):
        cards = short_v1_doc.content[role]["cards"]
        assert 3 <= len(cards) <= 4
        frame = short_v1_doc.content[role]["frame"]
        assert isinstance(frame["idx"], int) and isinstance(frame["total"], int)
        assert frame["total"] == 5


def test_narration_stays_within_rate_budget(short_v1_doc):
    """x-read 내레이션이 포맷 낭독 예산(dur×5.5자) 안 — 첫 문장 예외만 허용."""
    for s in short_v1_doc.scenes:
        assert s.narration.strip(), f"씬 {s.name}: 내레이션이 비었다"
        chars = len(s.narration.replace(" ", ""))
        first = s.narration.split(". ")[0]
        budget = int(s.dur * RATE)
        assert chars <= max(budget, len(first.replace(" ", ""))), (
            f"씬 {s.name}: 낭독 {chars}자 > 예산 {budget}자"
        )


def test_metric_prefers_single_series_over_fallback():
    """report_sample 의 progress_bar(단일 계열)가 vtpl.metric 수치가 된다 — 폴백 아님."""
    norm = ingest_report_file(SAMPLE)
    frags = fragmentize(norm)
    doc = assemble_demo_scenario(norm, frags, format=FORMAT)
    assert validate_scenario(doc, modules_root=MODULES) == []
    proof = doc.content["proof"]
    assert proof["unit"] == "%"
    assert float(proof["value"]) == 100.0  # 7계열 중 최댓값 하나로 승부
    assert len(proof["value"]) <= 7 and len(proof["label"]) <= 20


def test_two_formats_from_same_inputs_do_not_interfere():
    """같은 입력으로 wide-16x9 다음 short-9x16 을 조립해도 상태가 새지 않는다."""
    norm = ingest_report_file(SAMPLE)
    frags = fragmentize(norm)
    wide = assemble_demo_scenario(norm, frags)
    short = assemble_demo_scenario(norm, frags, format=FORMAT)
    assert len(wide.scenes) == 7 and len(short.scenes) == 5
    # _stack_seq 카운터가 조립 호출마다 리셋 — 두 번째 조립도 problem 부터
    short2 = assemble_demo_scenario(norm, frags, format=FORMAT)
    assert short2.content["problem"]["tone"] == "problem"
    assert short2.content["solution"]["tone"] == "solution"
