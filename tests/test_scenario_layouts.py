# 발표 레이아웃 8종(l-*) 구조 매핑 검증 — 라우팅·용량·정직 표기·기존 경로 회귀
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file
from wdpipeline.scenario import assemble_demo_scenario, slot_fit_report, validate_scenario

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
PENDING = ("layouts-a.registry.yaml", "layouts-b.registry.yaml")
LAYOUT_FORMAT = REPO_ROOT / "data" / "layout_check" / "formats" / "wide-16x9" / "format.yaml"
QUAD_FORMAT = REPO_ROOT / "data" / "layout_check" / "formats_quad" / "wide-16x9" / "format.yaml"

# 도달률 기준선 — 이 수치가 바뀌면 조립 규칙이 바뀐 것이다 (docs/analysis/layout-catalog.md)
BEFORE_REACH, BEFORE_PLACED = 75.0, 58.3
AFTER_REACH, AFTER_PLACED = 91.7, 75.0

NEW_SHORTS = {"l-split", "l-list", "l-tree", "l-quote", "l-kpi", "l-quad", "l-ba", "l-mix"}


def _roots(tmp_path: Path, monkeypatch, format_file: Path) -> Path:
    """신규 8종이 등록된 modules root + 주어진 포맷 스펙의 formats root 를 주입한다.

    modules/registry.yaml 은 다른 워크플로가 편집 중이라 손대지 않는다 — 본 레지스트리와
    modules/_pending/layouts-{a,b}.registry.yaml 을 tmp 에서 합쳐 쓴다(오케스트레이터가
    병합하면 이 픽스처 없이도 같은 결과가 나온다).
    """
    base = yaml.safe_load((REPO_ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    have = {m["id"] for m in base["modules"]}
    for name in PENDING:
        frag = yaml.safe_load((REPO_ROOT / "modules" / "_pending" / name).read_text("utf-8"))
        for mod in frag.get("modules", []) or []:
            if mod["id"] not in have:
                base["modules"].append(mod)
                have.add(mod["id"])
    modules = tmp_path / "modules"
    modules.mkdir()
    (modules / "registry.yaml").write_text(
        yaml.safe_dump(base, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (modules / "scene-templates").symlink_to(REPO_ROOT / "modules" / "scene-templates")

    formats = tmp_path / "formats" / "wide-16x9"
    formats.mkdir(parents=True)
    (formats / "format.yaml").write_text(format_file.read_text(encoding="utf-8"), "utf-8")
    monkeypatch.setenv("WDA_MODULES_ROOT", str(modules))
    monkeypatch.setenv("WDA_FORMATS_ROOT", str(tmp_path / "formats"))
    return tmp_path


@pytest.fixture()
def layout_roots(tmp_path: Path, monkeypatch) -> Path:
    """발표 레이아웃 11역할 풀 — 도달률 측정과 본 실증이 쓰는 구성."""
    return _roots(tmp_path, monkeypatch, LAYOUT_FORMAT)


@pytest.fixture()
def quad_roots(tmp_path: Path, monkeypatch) -> Path:
    """좌표 역할(tpl.l-quad)까지 연 12역할 풀 — 좌표 payload 가 있을 때만 쓴다."""
    return _roots(tmp_path, monkeypatch, QUAD_FORMAT)


@pytest.fixture()
def sample() -> tuple[dict, list[dict]]:
    norm = ingest_report_file(SAMPLE)
    return norm, fragmentize(norm)


def _content(doc, short: str) -> dict:
    """조립 문서에서 해당 템플릿 씬의 data 를 꺼낸다."""
    scene = next(s for s in doc.scenes if s.tpl.split("@")[0] == short)
    node = doc.model_dump()
    for seg in scene.data_ref.split("."):
        node = node[seg]
    return node


def _quadrant_norm() -> dict:
    """좌표(x·y) payload 를 만드는 유일한 위젯군 — quadrant plot 모드 합성 보고서."""
    return {
        "doc_id": "quad01",
        "title": "우선순위 좌표 검증",
        "report_date": "2026-07-29",
        "tags": ["검증"],
        "search_text": "좌표",
        "pages": [{"name": "1. 본문", "blocks": [{
            "id": "q1", "type": "quadrant", "section": None,
            "props": {"label": "난이도 × 효과", "default_mode": "plot",
                      "x_range": [0, 10], "y_range": [0, 100]},
            "content": {"mode": "plot", "plot_items": [
                {"id": "a", "label": "자동 리포트", "x": 2, "y": 90},
                {"id": "b", "label": "전면 재설계", "x": 9, "y": 70},
                {"id": "c", "label": "권한 정리", "x": 5, "y": 40},
                {"id": "d", "label": "폐기 예정", "x": 8, "y": 10},
            ]},
        }]}],
    }


# ── 1. 기존 경로 회귀 — 풀을 열지 않으면 아무것도 달라지지 않는다 ──────────


def test_default_pool_is_untouched(sample):
    """기본 7역할 풀에서는 신규 레이아웃이 등장하지 않고 도달률도 그대로다."""
    norm, frags = sample
    rep = slot_fit_report(norm, frags)
    assert (rep["reach_pct"], rep["placed_pct"]) == (BEFORE_REACH, BEFORE_PLACED)
    doc = assemble_demo_scenario(norm, frags)
    shorts = {s.tpl.split("@")[0] for s in doc.scenes}
    assert len(doc.scenes) == 7
    assert not (shorts & NEW_SHORTS)


# ── 2. 라우팅 — payload 종류가 그릇을 고른다 ─────────────────────────────


def test_layout_pool_routes_every_new_template(layout_roots, sample):
    """발표 레이아웃 풀에서 구조 payload 가 신규 7종을 자리에 앉힌다(좌표는 별도 테스트)."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    shorts = [s.tpl.split("@")[0] for s in doc.scenes]
    assert set(shorts) >= {"l-split", "l-tree", "l-list", "l-ba", "l-mix", "l-kpi", "l-quote"}
    assert validate_scenario(doc) == []      # 8종 전부 자기 schema.json 을 통과한다


def test_reach_and_placement_improve(layout_roots, sample):
    """도달률·배치율이 기준선 이상으로 오른다 — 이 라운드의 수치 약속."""
    norm, frags = sample
    rep = slot_fit_report(norm, frags, structured_templates=True)
    assert rep["reach_pct"] >= AFTER_REACH
    assert rep["placed_pct"] >= AFTER_PLACED
    slots = {r["slot"] for r in rep["rows"] if r["slot"]}
    assert {"l-list.rows", "l-tree.nodes", "l-kpi.metrics", "l-mix.table.rows",
            "l-split.visual.table.rows"} <= slots


def test_quadrant_payload_routes_to_l_quad(quad_roots):
    """x 를 가진 계열은 l-quad 로 간다 — 좌표는 0~1 정규화되고 순서는 보존된다."""
    norm = _quadrant_norm()
    frags = fragmentize(norm)
    rep = slot_fit_report(norm, frags, structured_templates=True)
    assert [r["slot"] for r in rep["rows"]] == ["l-quad.items"]
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    assert validate_scenario(doc) == []
    items = _content(doc, "l-quad")["items"]
    assert [i["label"] for i in items] == ["자동 리포트", "전면 재설계", "권한 정리", "폐기 예정"]
    assert all(0.0 <= i["x"] <= 1.0 and 0.0 <= i["y"] <= 1.0 for i in items)
    assert items[0]["x"] < items[2]["x"] < items[1]["x"]      # 가로 순서 보존
    assert items[0]["y"] > items[3]["y"]                      # 세로 순서 보존


# ── 3. 용량과 정직 표기 — 넘치면 줄이고 줄인 만큼 밝힌다 ──────────────────


def test_l_tree_keeps_payload_keys_and_states_omission(layout_roots, sample):
    """graph(tree) 의 nodes/edges 키를 개명 없이 받고, 15노드 중 못 담은 3개를 계상한다."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    data = _content(doc, "l-tree")
    payload = next(f["structured"] for f in frags
                   if isinstance(f.get("structured"), dict)
                   and f["structured"].get("shape") == "tree")
    src_ids = {str(n["id"]) for n in payload["nodes"]}
    assert {str(n["id"]) for n in data["nodes"]} <= src_ids          # 없던 노드를 만들지 않는다
    assert all(set(n) <= {"id", "label", "level"} | {"note"} for n in data["nodes"])
    assert all(set(e) == {"from", "to"} for e in data["edges"])
    ids = {n["id"] for n in data["nodes"]}
    assert all(e["from"] in ids and e["to"] in ids for e in data["edges"])
    levels = [n["level"] for n in data["nodes"]]
    assert levels.count(0) == 1 and 2 <= levels.count(1) <= 4 and levels.count(2) <= 8
    assert data["omitted"] == len(payload["nodes"]) - len(data["nodes"]) > 0


def test_l_list_carries_rows_and_marks_the_rest(layout_roots, sample):
    """키값 9쌍 → 8행(2줄 압축 아님) + 담지 못한 1건을 타이틀에 밝힌다."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    data = _content(doc, "l-list")
    assert len(data["rows"]) == 8
    assert "외 1건" in data["title"]
    assert all(r.get("desc") for r in data["rows"])   # 설명이 살아 있다(제목만 남기지 않는다)


def test_l_kpi_values_are_numeric_strings(layout_roots, sample):
    """큰 수치는 숫자 문자열 계약(^-?[0-9][0-9.,]*$)을 지키고 단위는 별도 필드다."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    data = _content(doc, "l-kpi")
    assert 4 <= len(data["metrics"]) <= 6
    assert all(re.fullmatch(r"-?[0-9][0-9.,]*", m["value"]) for m in data["metrics"])
    assert all(len(m["label"]) <= 14 for m in data["metrics"])
    assert data["omitted"] == 1                       # 7계열 중 6개만 실렸다
    # 증감·스파크바는 비교 시점이 필요한 값 — 자동 조립은 지어내지 않는다
    assert all("delta" not in m and "spark" not in m for m in data["metrics"])


def test_l_mix_table_and_chart_do_not_contradict(layout_roots, sample):
    """같은 화면의 표와 막대는 서로 다른 수치를 말하지 않는다 (교차 배열 규칙)."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    data = _content(doc, "l-mix")
    by_row = {r["label"]: [c["v"] for c in r["cells"]] for r in data["table"]["rows"]}
    for bar in data["chart"]["bars"]:
        if bar["label"] in by_row:
            assert bar["display"] in by_row[bar["label"]]
    assert 3 <= len(data["chart"]["bars"]) <= 4
    assert 3 <= len(data["table"]["rows"]) <= 5
    assert "stats" in data and "lead" not in data     # 스키마 oneOf 배타
    assert "생략" in data["note"]["pre"]               # 잘라낸 행·열·계열을 밝힌다


def test_l_split_marks_dropped_column(layout_roots, sample):
    """3안 비교 표를 2열 간이표로 줄이면 빠진 열을 소결론에 적는다."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    data = _content(doc, "l-split")
    assert data["visual"]["kind"] == "table"
    assert len(data["visual"]["table"]["columns"]) <= 3
    assert "외 1열" in data["conclusion"].get("post", "")
    assert 3 <= len(data["bullets"]) <= 5


def test_l_ba_summary_is_metadata_not_invented(layout_roots, sample):
    """비교 표에 수치 행이 없으면 대표 수치는 비교 관점 수다 — 없는 수치를 만들지 않는다."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    data = _content(doc, "l-ba")
    for side in ("before", "after"):
        assert re.fullmatch(r"-?[0-9][0-9.,]*", data[side]["summary"]["value"])
        assert 3 <= len(data[side]["items"]) <= 5
    assert data["before"]["label"] != data["after"]["label"]


def test_l_quote_uses_a_sentence_from_the_report(layout_roots, sample):
    """각인 문장은 지어낸 선언이 아니라 원문에서 온 문장이다."""
    norm, frags = sample
    doc = assemble_demo_scenario(norm, frags, structured_templates=True)
    quote = _content(doc, "l-quote")["quote"]
    texts = " ".join(f["text"] for f in frags)
    assert quote.rstrip("…") in texts
    assert len(quote) <= 70


# ── 4. 실증 산출물 — 드라이버가 남긴 수치와 스틸이 실재하는가 ─────────────


def test_layout_fit_record_matches_thresholds():
    """드라이버 기록(layout_fit.json)이 문서에 적힌 수치와 같은지 — 없으면 skip."""
    path = REPO_ROOT / "data" / "layout_check" / "layout_fit.json"
    if not path.is_file():
        pytest.skip("드라이버 미실행 — uv run python data/layout_check/driver.py")
    rec = json.loads(path.read_text(encoding="utf-8"))
    assert rec["runs"]["before_default"]["reach_pct"] == BEFORE_REACH
    assert rec["runs"]["after_layouts"]["reach_pct"] >= AFTER_REACH
    assert rec["runs"]["after_layouts"]["placed_pct"] >= AFTER_PLACED
    if "render" in rec:
        assert rec["render"]["qa_passed"] is True
        stills = REPO_ROOT / "data" / "quality_compare" / "layouts"
        assert {p.stem.split("_", 1)[1] for p in stills.glob("*.png")} >= NEW_SHORTS
