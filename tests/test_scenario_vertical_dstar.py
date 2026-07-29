# d-* 씬(격자/도판/다계열) structured_templates 라우팅 검증 — 포맷 풀 옵트인 경계 포함 (임무 C §3)
from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file
from wdpipeline.scenario import assemble_demo_scenario, slot_fit_report, validate_scenario

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
MODULES = REPO_ROOT / "modules"

# d-* 옵트인 풀 — formats/wide-16x9/format.yaml 에 이 3줄을 열면 기본 경로에도 붙는다.
DSTAR_POOL = {
    "problem": ["tpl.problem", "tpl.d-media"],
    "differentiator": ["tpl.differentiator", "tpl.d-matrix", "tpl.compare"],
    "proof": ["tpl.proof", "tpl.dataviz", "tpl.d-multi"],
}


@pytest.fixture()
def dstar_formats_root(tmp_path: Path, monkeypatch) -> Path:
    """wide-16x9 스펙에 d-* 풀을 연 오버라이드 formats root (WDA_FORMATS_ROOT)."""
    spec = yaml.safe_load(
        (REPO_ROOT / "formats" / "wide-16x9" / "format.yaml").read_text(encoding="utf-8")
    )
    spec["template_pool"].update(DSTAR_POOL)
    out = tmp_path / "formats" / "wide-16x9"
    out.mkdir(parents=True)
    (out / "format.yaml").write_text(
        yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8"
    )
    monkeypatch.setenv("WDA_FORMATS_ROOT", str(tmp_path / "formats"))
    return tmp_path / "formats"


def _norm(blocks: list[dict], **extra) -> dict:
    return {
        "doc_id": "dstar01",
        "title": "d-스타 라우팅 검증 보고서",
        "report_date": "2026-07-28",
        "tags": ["검증", "라우팅"],
        "search_text": "d-스타 라우팅 검증",
        "pages": [{"name": "1. 본문", "blocks": blocks}],
        **extra,
    }


def _raci_block(rows: int = 9) -> dict:
    roles = [{"key": f"r{i}", "label": f"역할{i}"} for i in range(6)]
    return {
        "id": "raci1", "type": "raci_matrix", "section": None,
        "props": {"label": "권한 매트릭스", "default_roles": roles},
        "content": {
            "rows": [
                {"label": f"작업 항목 {i + 1}",
                 "assignments": {f"r{j}": "RACI"[(i + j) % 4] for j in range(6)}}
                for i in range(rows)
            ]
        },
    }


def _multi_chart_block() -> dict:
    return {
        "id": "ch1", "type": "chart", "section": None,
        "props": {
            "label": "분기별 비용 비교",
            "columns": [
                {"key": "q", "label": "분기"},
                {"key": "a", "label": "A안", "type": "number"},
                {"key": "b", "label": "B안", "type": "number"},
            ],
            "x_column_key": "q",
        },
        "content": {
            "rows": [
                {"q": f"{i + 1}Q", "a": 10.0 * (i + 1), "b": 8.0 * (i + 1)}
                for i in range(4)
            ]
        },
    }


def _image_norm(tmp_path: Path, resolved: bool = True) -> dict:
    img = tmp_path / "shot01.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")  # 빌더는 파일명만 쓴다 (사본 복사는 빌드 몫)
    block = {
        "id": "img1", "type": "image", "section": None,
        "props": {"label": "시험 장면"},
        "content": {"caption": "시험 장면",
                    "files": [{"file_id": "f1", "caption": "정면", "alt": "시험기 정면"}]},
    }
    meta = {"file_id": "f1", "local_path": str(img) if resolved else None,
            "status": "resolved" if resolved else "unresolved",
            "media_type": "image" if resolved else None}
    return _norm([block], assets_meta=[meta])


# ── 라우팅 — 오버라이드 풀에서 d-* 가 자리를 가져간다 ────────────────────


def test_dmatrix_takes_homeless_grid(dstar_formats_root):
    """갈 곳 없는 7열×9행 RACI 격자 → differentiator 역할을 d-matrix 가 가져간다."""
    norm = _norm([_raci_block(rows=9)])
    frags = fragmentize(norm)
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    assert validate_scenario(doc, modules_root=MODULES) == []
    scene = next(s for s in doc.scenes if s.tpl.startswith("d-matrix@"))
    assert scene.data_ref == "content.differentiator"
    data = doc.content["differentiator"]
    assert len(data["columns"]) == 7           # 작업 + 역할 6 (열 8 상한 이내)
    assert len(data["rows"]) == 8              # 행 8 상한 — 9행 중 첫·끝 표본
    assert data["omitted"] == 1                # 무언의 절단 금지
    cells = data["rows"][0]["cells"]
    assert len(cells) == 6
    assert all(c.get("chip") for c in cells)   # R/A/C/I 코드값은 칩


def test_dmedia_takes_resolved_images(dstar_formats_root, tmp_path):
    """해결된 이미지 자산 → problem 역할을 d-media 가 가져간다 (src=assets/{파일명})."""
    norm = _image_norm(tmp_path, resolved=True)
    frags = fragmentize(norm)
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    assert validate_scenario(doc, modules_root=MODULES) == []
    scene = next(s for s in doc.scenes if s.tpl.startswith("d-media@"))
    assert scene.data_ref == "content.problem"
    files = doc.content["problem"]["files"]
    assert files == [
        {"src": "assets/shot01.png", "caption": "정면", "alt": "시험기 정면", "source": "본문"}
    ]


def test_dmedia_ignores_unresolved_assets(dstar_formats_root, tmp_path):
    """미해결 자산은 실을 파일이 없다 — d-media 는 발동하지 않고 problem 이 유지된다."""
    norm = _image_norm(tmp_path, resolved=False)
    frags = fragmentize(norm)
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    assert not any(s.tpl.startswith("d-media@") for s in doc.scenes)
    assert any(s.tpl.startswith("problem@") for s in doc.scenes)


def test_dmulti_takes_grouped_series(dstar_formats_root):
    """다계열 chart(2계열×4항목) → proof 역할을 d-multi 가 가져간다 (값 날조 없음)."""
    norm = _norm([_multi_chart_block()])
    frags = fragmentize(norm)
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    assert validate_scenario(doc, modules_root=MODULES) == []
    scene = next(s for s in doc.scenes if s.tpl.startswith("d-multi@"))
    assert scene.data_ref == "content.proof"
    data = doc.content["proof"]
    assert [c["label"] for c in data["categories"]] == ["1Q", "2Q", "3Q", "4Q"]
    assert [s["name"] for s in data["series"]] == ["A안", "B안"]
    assert data["series"][0]["values"] == [10.0, 20.0, 30.0, 40.0]
    assert data["series"][1]["values"] == [8.0, 16.0, 24.0, 32.0]


# ── 옵트인 경계 — 현행 포맷 풀에서는 d-* 가 켜지지 않는다 ─────────────────


def test_default_pool_keeps_dstar_off():
    """formats/wide-16x9 현행 풀에는 d-* 미선언 — 기존 라우팅 결과가 그대로다."""
    norm = ingest_report_file(SAMPLE)
    frags = fragmentize(norm)
    report = slot_fit_report(norm, frags, structured_templates=True)
    assert not any(t.startswith("d-") for t in report["templates"])
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    assert not any(s.tpl.startswith("d-") for s in doc.scenes)
    assert validate_scenario(doc, modules_root=MODULES) == []


def test_slot_fit_report_counts_dstar_slots(dstar_formats_root):
    """오버라이드 풀에서 slot_fit_report 가 격자/다계열을 none 이 아니라 d-* 슬롯으로 센다."""
    norm = _norm([_raci_block(rows=9), _multi_chart_block()])
    frags = fragmentize(norm)
    report = slot_fit_report(norm, frags, structured_templates=True)
    rows = {r["widget"]: r for r in report["rows"]}
    raci = rows["raci_matrix"]
    assert raci["slot"] == "d-matrix.rows" and raci["fit"] != "none"
    assert raci["items"] == 9 and raci["carried"] == 8 and raci["omitted"] == 1
    chart = rows["chart"]
    assert chart["slot"] == "d-multi.series" and chart["fit"] != "none"
