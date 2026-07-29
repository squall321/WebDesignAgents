# 레이아웃 4종(tpl.l-kpi/l-quad/l-ba/l-mix)을 한 빌드에 담아 wdqa 게이트 1~7 을 실행하고 error 0 을 증명
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
LAYOUT_JSX = ROOT / "web" / "templates" / "omx-layouts-b.jsx"

SCENES = [
    ("지표", "l-kpi", 11),
    ("사분면", "l-quad", 13),
    ("대비", "l-ba", 14),
    ("혼합", "l-mix", 15),
]


def _fixture(name: str) -> dict:
    return json.loads((TPL_DIR / name / "fixtures" / "typical.json").read_text(encoding="utf-8"))


def _scenario_doc():
    from wdcore.models.scenario import ScenarioDoc

    return ScenarioDoc(
        meta={
            "core_message": "가로 16:9 데이터 배치 레이아웃 4종 게이트 점검",
            "audience": "품질 게이트",
            "duration_sec": float(sum(nat for _, _, nat in SCENES)),
        },
        format="wide-16x9",
        content={name: _fixture(name) for _, name, _ in SCENES},
        scenes=[
            {
                "name": scene,
                "dur": float(nat),
                "nat": float(nat),
                "tpl": f"{name}@1",
                "data_ref": f"content.{name}",
            }
            for scene, name, nat in SCENES
        ],
        tokens_theme="hwax-blue",
        playback={"mode": "times", "count": 1},
    )


def _inject_layout_jsx(build_dir: Path) -> None:
    """레지스트리 병합 전이라 빌드 로드 순서에 없는 omx-layouts-b.jsx 를 엔트리에 끼워 넣는다.

    병합이 끝나면(load_order_contract 에 파일이 들어가면) 이 주입은 무동작이 된다.
    """
    entry = build_dir / "index.html"
    html = entry.read_text(encoding="utf-8")
    tag = '<script type="text/babel" data-presets="react" src="./templates/omx-layouts-b.jsx"></script>'
    if tag in html:
        return
    shutil.copy2(LAYOUT_JSX, build_dir / "templates" / "omx-layouts-b.jsx")
    anchor = '<script type="text/babel" data-presets="react" src="./scenes.jsx"></script>'
    assert anchor in html, "빌드 엔트리에서 scenes.jsx 로드 지점을 찾지 못했다"
    entry.write_text(html.replace(anchor, tag + "\n" + anchor), encoding="utf-8")


@pytest.fixture(scope="module")
def gate_result(tmp_path_factory) -> dict:
    from wdpipeline.build import build_render_package
    from wdqa.config import QAConfig
    from wdqa.gates import run_gates

    tmp = tmp_path_factory.mktemp("layouts_b_gates")
    doc = _scenario_doc()
    build_dir = tmp / "build"
    build_render_package(doc, build_dir)
    _inject_layout_jsx(build_dir)
    return run_gates(
        build_dir,
        scenario=doc.model_dump(),
        config=QAConfig(reports_root=tmp / "qa_reports"),
    )


def test_gates_1_to_7_have_no_errors(gate_result):
    errors = [r for r in gate_result["results"] if r["severity"] == "error"]
    assert errors == [], f"게이트 error {len(errors)}건 — {errors}"
    assert gate_result["passed"] is True


def test_no_warnings_either(gate_result):
    """error 0 은 물론 warning 도 0 — 선언되지 않은 색 조합·타임 스트레치가 없다."""
    noisy = [r for r in gate_result["results"] if r["severity"] in ("error", "warning")]
    assert noisy == [], f"경고 이상 {len(noisy)}건 — {noisy}"


def test_no_phase_was_skipped(gate_result):
    """게이트가 조용히 건너뛴 채 '통과'로 보이는 상황을 막는다."""
    skipped = [r for r in gate_result["results"] if r["rule"] == "phase-skipped"]
    assert not skipped, f"단계 생략이 발생했다 — {skipped}"
    assert {r["gate"] for r in gate_result["results"]} <= set(range(1, 8))


def test_scene_map_covers_four_layouts(gate_result):
    """4종이 모두 씬으로 매핑돼 실제로 검사 대상이 됐다 (게이트 1 매핑)."""
    report = json.loads(Path(gate_result["report_path"]).read_text(encoding="utf-8"))
    assert report["passed"] is True
    missing = [r for r in report["results"] if r["rule"] in ("map-missing", "map-orphan")]
    assert not missing, f"씬 맵 불일치 — {missing}"


def test_gate_harness_has_teeth_on_this_build(tmp_path):
    """'error 0' 이 게이트가 이 빌드를 실제로 본 결과임을 증명한다 — 씬 이름을 깨면 게이트 1이 잡는다."""
    from wdpipeline.build import build_render_package
    from wdqa.config import QAConfig
    from wdqa.gates import run_gates

    doc = _scenario_doc()
    build_dir = tmp_path / "broken"
    build_render_package(doc, build_dir)
    _inject_layout_jsx(build_dir)
    scenes_jsx = build_dir / "scenes.jsx"
    src = scenes_jsx.read_text(encoding="utf-8")
    assert '"지표"' in src
    scenes_jsx.write_text(src.replace('"지표"', '"없는씬"', 1), encoding="utf-8")

    res = run_gates(
        build_dir, scenario=doc.model_dump(), gates=["mapping"],
        config=QAConfig(reports_root=tmp_path / "qa_reports"),
    )
    rules = {r["rule"] for r in res["results"] if r["severity"] == "error"}
    assert {"map-missing", "map-orphan"} <= rules, f"게이트 1이 씬 맵 파손을 못 잡았다 — {res}"
    assert res["passed"] is False


def test_runtime_scan_actually_inspects_this_build(tmp_path):
    """런타임 단계가 실제로 이 빌드를 스캔했음을 증명한다 — 글자를 12px 로 눌러 게이트 4가 잡게 한다."""
    from wdpipeline.build import build_render_package
    from wdqa.config import QAConfig
    from wdqa.gates import run_gates

    doc = _scenario_doc()
    build_dir = tmp_path / "tiny_font"
    build_render_package(doc, build_dir)
    _inject_layout_jsx(build_dir)
    entry = build_dir / "index.html"
    html = entry.read_text(encoding="utf-8")
    entry.write_text(
        html.replace("</head>", "<style>[data-screen-label] div{font-size:12px !important;}</style></head>"),
        encoding="utf-8",
    )

    res = run_gates(
        build_dir, scenario=doc.model_dump(), gates=["font"],
        config=QAConfig(reports_root=tmp_path / "qa_reports"),
    )
    small = [r for r in res["results"] if r["rule"] == "min-font" and r["severity"] == "error"]
    assert small, f"게이트 4 런타임 스캔이 12px 텍스트를 못 잡았다 — {res}"
    scenes = {r["scene"] for r in small}
    assert scenes == {"지표", "사분면", "대비", "혼합"}, f"스캔이 닿은 씬이 4종이 아니다 — {scenes}"
