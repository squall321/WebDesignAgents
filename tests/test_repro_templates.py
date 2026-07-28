# 전 모듈 재현력 회귀 — 세션 간·골든 대비·빌드 간 3층 (대표 6종 전체 픽스처, 나머지 typical 계층화)
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wdqa.repro import (
    FIXTURES,
    record_quality,
    template_modules,
    verify_all,
    verify_build,
)

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "reportarchive" / "report_sample.json"

# 계층화 근거 — 재현력 위험은 템플릿 "파일 계열" 단위로 갈린다 (같은 파일은 같은 코딩 규약·
# 같은 스케줄 유틸을 공유). 대표 6종으로 4계열 × 무대 2종 × 고위험 경로를 덮는다.
#   tpl.opening   — omx-templates.jsx 기본 7종 대표 (가로 1920x1080)
#   tpl.dataviz   — omx-templates-ext.jsx 대표 (막대 스케일 계산 경로)
#   tpl.d-matrix  — omx-templates-data.jsx 표 위젯 대표 (행·열 초과 절삭 경로)
#   tpl.d-media   — 이미지 자산 로드 경로 (외부 리소스 타이밍 = 비결정성 최고 위험)
#   vtpl.hook     — omx-templates-vertical.jsx 대표 (세로 1080x1920)
#   vtpl.stack    — 데이터 길이에 스케줄이 민감한 적층 씬 (min/max 차가 가장 큼)
# 나머지 11종은 typical 만 2회 — min/max 렌더 정합은 각 계열의 기존 렌더 테스트가 이미 덮는다.
FULL_TIER = {
    "tpl.opening", "tpl.dataviz", "tpl.d-matrix", "tpl.d-media",
    "vtpl.hook", "vtpl.stack",
}

MODULES = template_modules()
MODULE_IDS = [m["id"] for m in MODULES]

# 이 라운드 기준 레지스트리 17종 — 늘어나는 건 허용, 빠지면 회귀
KNOWN_17 = {
    "tpl.opening", "tpl.problem", "tpl.concept", "tpl.process", "tpl.differentiator",
    "tpl.proof", "tpl.closing", "tpl.dataviz", "tpl.timeline", "tpl.compare",
    "tpl.d-matrix", "tpl.d-media", "tpl.d-multi",
    "vtpl.hook", "vtpl.stack", "vtpl.metric", "vtpl.cta",
}


@pytest.fixture(scope="module")
def report() -> dict:
    fbm = {mid: FIXTURES if mid in FULL_TIER else ("typical",) for mid in MODULE_IDS}
    return verify_all(runs=2, fixtures_by_module=fbm)


def test_registry_covers_known_17():
    assert KNOWN_17 <= set(MODULE_IDS), f"레지스트리 결손: {KNOWN_17 - set(MODULE_IDS)}"


@pytest.mark.parametrize("module_id", MODULE_IDS)
def test_module_reproducible(report, module_id):
    r = next(r for r in report["results"] if r["module"] == module_id)
    detail = {fx: {k: v for k, v in fr.items() if k != "png"}
              for fx, fr in r["fixtures"].items()}
    assert r["passed"], f"{module_id} 재현력 실패 — {json.dumps(detail, ensure_ascii=False)}"


@pytest.mark.parametrize("module_id", MODULE_IDS)
def test_schedule_deterministic(report, module_id):
    r = next(r for r in report["results"] if r["module"] == module_id)
    for fx, fr in r["fixtures"].items():
        assert fr.get("schedule_deterministic"), (
            f"{module_id}/{fx}: 스케줄 시각(still/nat/duration)이 세션 간 다르다"
        )


@pytest.mark.parametrize("module_id", MODULE_IDS)
def test_golden_matches_stage_dims(module_id):
    """골든은 무대 원척(포맷 stage)과 같은 크기여야 골든 대비 diff 가 성립한다."""
    from PIL import Image

    mod = next(m for m in MODULES if m["id"] == module_id)
    p = mod["mod_dir"] / "fixtures" / "snapshots" / "typical.png"
    assert p.is_file(), f"{module_id}: 골든 스냅샷이 없다 — {p}"
    size = Image.open(p).size
    assert size == (mod["stage"]["w"], mod["stage"]["h"]), (
        f"{module_id}: 골든 {size} ≠ 무대 {mod['stage']}"
    )


def test_verify_build_deterministic(tmp_path):
    """같은 scenario 로 2회 빌드한 산출 3파일(scene-data/scenes.jsx/index.html)은 바이트 동일."""
    from wdpipeline.build import build_render_package
    from wdpipeline.fragmentize import fragmentize
    from wdpipeline.ingest import ingest_report_file
    from wdpipeline.scenario import assemble_demo_scenario

    norm = ingest_report_file(SAMPLE)
    doc = assemble_demo_scenario(norm, fragmentize(norm))
    build_dir = tmp_path / "pkg"
    build_render_package(doc, build_dir)
    r = verify_build(build_dir)
    assert r["passed"], f"빌드 간 비결정성 — {r['files']}"
    assert all(v["identical"] for v in r["files"].values())
    # 방금 만든 빌드와도 일치해야 한다 (같은 코드·같은 시나리오)
    assert all(r["matches_original"].values()), r["matches_original"]


def test_record_quality_surgical(tmp_path):
    """quality.reproducibility 기록은 주석·기존 키를 보존하고 재실행 시 자기 블록만 교체한다."""
    import yaml

    src = ("# 헤더 주석은 보존되어야 한다\n"
           "id: tpl.x\n"
           "quality:\n"
           "  gates_passed:\n"
           "    - \"abc\"  # 인라인 주석\n"
           "  reviews: []\n"
           "maintenance:\n"
           "  notes: []\n")
    mod_dir = tmp_path / "x"
    mod_dir.mkdir()
    (mod_dir / "module.yaml").write_text(src, encoding="utf-8")
    result = {"passed": True, "max_diff_ratio": 0.0}
    record_quality(mod_dir, result, checked_at="2026-07-28T00:00:00")
    record_quality(mod_dir, {"passed": False, "max_diff_ratio": 0.5},
                   checked_at="2026-07-28T01:00:00")  # 갱신 — 블록 중복 금지
    text = (mod_dir / "module.yaml").read_text(encoding="utf-8")
    assert text.count("reproducibility:") == 1
    assert "# 헤더 주석은 보존되어야 한다" in text
    assert "# 인라인 주석" in text
    doc = yaml.safe_load(text)
    assert doc["quality"]["reproducibility"]["verdict"] == "fail"
    assert doc["quality"]["reproducibility"]["max_diff_ratio"] == 0.5
    assert doc["quality"]["gates_passed"] == ["abc"]
    assert doc["maintenance"]["notes"] == []
