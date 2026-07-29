# 문서형(읽는 자료) 조립 검증 — doc-cover/toc/section/body/summary 로 보고서 구조를 슬라이드로 펴는지
#
# 씬 템플릿은 **modules/scene-templates/doc-*/ 실물**을 그대로 쓴다(임무 B 소유 — schema.json ·
# module.yaml · registry 전부 실재). 합성하는 것은 format.yaml 하나뿐이다.
# 현행 formats/{deck-doc-16x9,deck-4x3,print-a4} 의 template_pool 이 아직 native.*(exporter 가
# 텍스트로 조립) 라 tpl.doc-* 씬 경로가 켜지지 않기 때문이다 — 같은 포맷 id 에 pool 만
# tpl.doc-* 로 바꾼 스펙을 tmp 에 두고 WDA_FORMATS_ROOT 로 가리킨다. 그 한 줄이 뒤집히는
# 순간 이 테스트가 곧 실사용 경로다.
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file
from wdpipeline.scenario import (
    assemble_demo_scenario,
    assemble_doc_scenario,
    slot_fit_report,
    validate_scenario,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"
MODULES = REPO_ROOT / "modules"          # 실물 모듈 레지스트리

FORMAT = "deck-doc-16x9"     # 문서형 브리핑 덱 (낭독 없음 · outputs [pptx])
FORMAT_VOICED = "deck-4x3"   # 같은 골격에 낭독만 켠 변형 (x-read 배선 확인용)

_POOL = {r: [f"tpl.doc-{r}"] for r in ("cover", "toc", "section", "body", "summary")}
_SKELETON = ["cover", "toc", "section", "body", "summary"]


def _format_specs() -> dict[str, dict]:
    """실물 format.yaml 과 같되 template_pool 만 tpl.doc-* 로 바꾼 스펙."""
    return {
        FORMAT: {
            "id": FORMAT, "name_ko": "문서형 브리핑 덱",
            "stage": {"w": 1920, "h": 1080},
            "slides": {"target": 15, "min": 5, "max": 30},
            "skeleton": _SKELETON, "template_pool": _POOL,
            "narration": {"enabled": False, "rate": 5.5}, "outputs": ["pptx"],
            "pptx": {"slide_w_in": 13.333, "slide_h_in": 7.5},
            "constraints": {"min_font": 21, "safe_margin": 81},
        },
        FORMAT_VOICED: {
            "id": FORMAT_VOICED, "name_ko": "4:3 사내 표준 덱(낭독 시험)",
            "stage": {"w": 1440, "h": 1080},
            "duration": {"target": 150.0, "min": 60.0, "max": 400.0},
            "skeleton": _SKELETON, "template_pool": _POOL,
            "narration": {"enabled": True, "rate": 5.5}, "outputs": ["video", "pptx"],
            "pptx": {"slide_w_in": 10.0, "slide_h_in": 7.5},
            "constraints": {"min_font": 21, "safe_margin": 81},
        },
    }


def _write_formats(root: Path) -> Path:
    for fid, spec in _format_specs().items():
        d = root / fid
        d.mkdir(parents=True, exist_ok=True)
        (d / "format.yaml").write_text(
            yaml.safe_dump(spec, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return root


@pytest.fixture(scope="module")
def doc_env(tmp_path_factory):
    for short in ("cover", "toc", "section", "body", "summary"):
        if not (MODULES / "scene-templates" / f"doc-{short}" / "module.yaml").is_file():
            pytest.skip(f"tpl.doc-{short} 모듈 미도착 (임무 B 진행 중)")
    root = _write_formats(tmp_path_factory.mktemp("docfmt"))
    mp = pytest.MonkeyPatch()
    mp.setenv("WDA_FORMATS_ROOT", str(root))
    yield root
    mp.undo()


@pytest.fixture(scope="module")
def sample() -> tuple[dict, list[dict]]:
    norm = ingest_report_file(SAMPLE)
    return norm, fragmentize(norm)


@pytest.fixture(scope="module")
def doc(doc_env, sample):
    norm, frags = sample
    return assemble_doc_scenario(norm, frags, format=FORMAT)


def _keys(doc_) -> list[str]:
    """씬 data_ref → content 키 (cover/toc/section-1/body-1-1/summary)."""
    return [s.data_ref.split(".", 1)[1] for s in doc_.scenes]


def _bodies(doc_) -> list[dict]:
    return [v for k, v in doc_.content.items() if k.startswith("body-")]


# ── 1. 골격 — 슬라이드 수를 보고서가 정한다 ─────────────────────────────


def test_doc_deck_structure_follows_report_pages(doc, sample):
    """cover 1 + toc 1 + section 5 + body 10 + summary 1 = 18장 — 골격이 아니라 보고서가 정한 수."""
    norm, _ = sample
    keys = _keys(doc)
    sections = [k for k in keys if k.startswith("section-")]
    bodies = [k for k in keys if k.startswith("body-")]
    assert keys[0] == "cover" and keys[1] == "toc" and keys[-1] == "summary"
    assert len(sections) == len(norm["pages"]) == 5
    assert len(bodies) == 10
    assert len(doc.scenes) == 18 == 1 + 1 + len(sections) + len(bodies) + 1
    for n in range(1, 6):      # 페이지당 본문 1~3장
        assert 1 <= len([k for k in bodies if k.startswith(f"body-{n}-")]) <= 3
    assert keys.index("section-2") > keys.index("body-1-1")   # 섹션 뒤에 그 섹션의 본문


def test_doc_scenario_passes_schema_validation(doc, doc_env):
    """조립 결과가 doc-* 5종 실물 schema.json 검증을 통과한다 (씬 데이터·tpl·data_ref 전부)."""
    assert validate_scenario(doc, modules_root=MODULES, formats_root=doc_env) == []


def test_scene_names_unique_and_durations_natural(doc):
    """씬 이름 중복 없음 · nat 합(136s)이 허용대 안이라 균일 스케일 없이 그대로 쓴다."""
    names = [s.name for s in doc.scenes]
    assert len(set(names)) == len(names)
    assert [s.dur for s in doc.scenes] == [s.nat for s in doc.scenes]
    assert round(sum(s.dur for s in doc.scenes), 1) == 136.0   # 6+7+5×5+9×10+8
    for s in doc.scenes:
        assert s.stills and 0 <= s.stills[0] <= s.dur


def test_video_entry_point_delegates_to_doc_path(doc_env, sample, doc):
    """assemble_demo_scenario 도 문서형 포맷이면 문서형 골격으로 간다 (파이프라인 배선)."""
    norm, frags = sample
    via_demo = assemble_demo_scenario(norm, frags, format=FORMAT)
    assert [s.tpl for s in via_demo.scenes] == [s.tpl for s in doc.scenes]


# ── 2. 내용 — 표지 서지 · 목차 유도 · 요약 ──────────────────────────────


def test_cover_carries_bibliographic_meta(doc, sample):
    """표지는 제목·작성일·분류·구성 — 읽는 자료의 표지는 서지사항이 본체다."""
    norm, _ = sample
    cover = doc.content["cover"]
    assert cover["title"] == norm["title"]
    assert {m["label"]: m["value"] for m in cover["meta"]}["작성일"] == "2026-05-27"
    assert {m["label"] for m in cover["meta"]} == {"작성일", "분류", "구성", "근거"}
    assert cover["badge"] == norm["tags"][0]
    assert "18장" in {m["label"]: m["value"] for m in cover["meta"]}["구성"]


def test_toc_is_derived_from_sections(doc):
    """목차는 섹션 목록에서 자동 유도되고 page 번호가 실제 섹션 슬라이드를 가리킨다."""
    keys = _keys(doc)
    items = doc.content["toc"]["items"]
    assert [it["no"] for it in items] == ["1.", "2.", "3.", "4.", "5."]
    assert items[0]["text"] == "플랫폼 개요"      # 원문 "1. 플랫폼 개요" 의 선두 번호 제거
    for i, it in enumerate(items, 1):
        assert keys[int(it["page"]) - 1] == f"section-{i}"
    assert doc.content["toc"]["note"].startswith("전 18장 · 섹션 5개")


def test_section_slides_preview_page_headings(doc):
    """섹션 간지는 원 페이지 이름 + 그 페이지의 소제목 예고 칩."""
    sec = doc.content["section-1"]
    assert sec["no"] == "01" and sec["name"] == "플랫폼 개요"
    assert sec["points"][:2] == ["ReportArchive…", "도입 목적"]   # 칩 16자 상한
    assert len(sec["points"]) <= 4 and sec["lead"]


def test_summary_uses_top_claims_and_honest_actions(doc, sample):
    """report_sample 은 ai_summary 가 비어 있다 — 상위 claim 이 결론, 행동은 원문 대조뿐."""
    norm, frags = sample
    assert not norm.get("ai_summary")
    s = doc.content["summary"]
    assert 3 <= len(s["points"]) <= 5
    texts = {" ".join(f["text"].split()).replace(" ", "") for f in frags if f["type"] == "claim"}
    for p in s["points"]:
        assert any(t.startswith(p["text"].rstrip("…").replace(" ", "")[:12]) for t in texts)
    # 절마다 하나씩 — 5줄이 한 절에서만 나오지 않는다 (note = 출처 절)
    assert [p["note"] for p in s["points"]] == [
        "플랫폼 개요", "보고서 워크플로", "위젯 카탈로그", "권한 모델", "배포 · 실행 · 향후 계획"]
    # 행동은 지어내지 않는다 — 원문 확인·미수록 근거 대조만
    assert s["actions"][0]["text"] == "원문 5페이지 전문 확인"
    assert any("미수록 근거 2건" in a["text"] for a in s["actions"])


# ── 3. 구조 payload 를 근거 슬롯에 직결 ─────────────────────────────────


def _evidences(doc_, kind: str) -> list[dict]:
    return [b["evidence"] for b in _bodies(doc_) if b["evidence"]["kind"] == kind]


def test_every_body_slide_carries_evidence(doc):
    """doc-body 계약대로 본문 슬라이드는 예외 없이 근거를 하나씩 들고 있다."""
    evs = [b["evidence"] for b in _bodies(doc)]
    assert len(evs) == 10
    assert all(e["caption"] and e["kind"] in ("table", "chart", "image") for e in evs)
    # kind 와 블록이 정확히 하나만 대응 (스키마 allOf 가 강제하는 조건)
    for e in evs:
        assert sum(1 for k in ("table", "chart", "image") if k in e) == 1 and e["kind"] in e


def test_wide_table_lands_as_rows_not_group_counts(doc):
    """33행 표가 개별 행 5개로 실린다 — 영상 경로의 '카테고리별 건수' 요약이 아니다."""
    big = next(e for e in _evidences(doc, "table")
               if e["caption"] == "사용 가능한 위젯 (총 35종)"[:26])
    assert big["table"]["headers"] == ["카테고리", "위젯", "용도"]
    assert len(big["table"]["rows"]) == 5
    assert big["table"]["rows"][0]["cells"][:2] == ["텍스트", "heading"]   # 원문 첫 행 그대로
    assert big["source"] == "원문 3열×33행 중 3열×5행"


def test_raci_matrix_reports_dropped_columns(doc):
    """6열 RACI 는 3열 상한에 걸린다 — 몇 열을 못 실었는지 source 로 밝힌다."""
    raci = next(e for e in _evidences(doc, "table")
                if e["table"]["headers"][0] == "작업")
    assert len(raci["table"]["headers"]) == 3 and len(raci["table"]["rows"]) == 5
    assert raci["source"] == "원문 6열×8행 중 3열×5행"
    assert raci["table"]["rows"][0]["cells"][1] == "R/A"


def test_graph_and_pairs_are_reduced_to_tables(doc):
    """흐름도·계층·키값은 표로 환원되고 원문 규모는 source 에 남는다."""
    flow = next(e for e in _evidences(doc, "table")
                if e["table"]["headers"][:2] == ["#", "단계"])
    assert flow["table"]["rows"][0]["cells"][0] == "1"
    assert "단계 중" in flow["source"]
    tree = next(e for e in _evidences(doc, "table")
                if e["table"]["headers"] == ["항목", "층"])
    assert tree["source"].startswith("15노드 중 5")
    assert {c["cells"][1] for c in [r for r in tree["table"]["rows"]]} >= {"L0"}
    kv = next(e for e in _evidences(doc, "table") if e["table"]["headers"] == ["항목", "값"])
    assert kv["source"] == "9쌍 중 5 · 원문 전수 수록"


def test_single_series_maps_to_chart(doc_env, sample):
    """단일 계열 수치는 막대 근거로 간다 (값 극단+중앙값, 강조 1개, 0 기준선)."""
    from wdpipeline.scenario import _doc_evidence

    _norm, frags = sample
    payload = next(f["structured"] for f in frags
                   if isinstance(f.get("structured"), dict)
                   and f["structured"].get("kind") == "series")
    ev = _doc_evidence(payload)
    assert ev["kind"] == "chart" and ev["caption"] == "Phase 별 진척"
    bars = ev["chart"]["bars"]
    assert len(bars) == 5 and ev["chart"]["unit"] == "%"
    assert sum(1 for b in bars if b.get("emphasis")) == 1
    assert max(b["value"] for b in bars) == 100.0 and min(b["value"] for b in bars) >= 0
    assert ev["source"] == "7계열 중 5 · 외 2계열 원문"


def test_overflowing_evidence_is_declared_not_hidden(doc):
    """페이지당 본문 3장 상한에 걸린 근거 2건이 화면(takeaway)과 요약 행동에 남는다."""
    last = doc.content["body-5-3"]
    assert "2건 근거는 원문 참조" in last["takeaway"]
    assert any("미수록 근거 2건" in a["text"] for a in doc.content["summary"]["actions"])


# ── 4. slot_fit_report — 문서형 도달률·배치율 ───────────────────────────


def test_slot_fit_report_reaches_every_payload(doc, sample):
    """구조 payload 12건 전부 근거 슬롯에 도달(100%)하고 10건이 실제 슬라이드에 배치된다."""
    norm, frags = sample
    rep = slot_fit_report(norm, frags, format=FORMAT)
    assert rep["format"] == FORMAT and rep["structured_blocks"] == 12
    assert rep["tally"]["none"] == 0 and rep["reach_pct"] == 100.0
    assert rep["placed_pct"] == round(100 * 10 / 12, 1) == 83.3
    assert rep["sections"] == 5 and rep["bodies"] == 10
    assert {r["placed_slot"] for r in rep["rows"] if r["placed"]} == {"doc-body.evidence"}


def test_doc_places_more_payloads_than_video(doc, sample):
    """같은 입력에서 배치율이 영상보다 높다 — 문서형은 근거마다 슬라이드가 생겨 경쟁이 없다."""
    norm, frags = sample
    docfit = slot_fit_report(norm, frags, format=FORMAT)
    with pytest.MonkeyPatch.context() as mp:   # 영상 경로는 repo 의 실제 formats/
        mp.delenv("WDA_FORMATS_ROOT", raising=False)
        wide = slot_fit_report(norm, frags)
    assert wide["placed_pct"] == 58.3          # 12건 중 7건 — 나머지는 슬롯 경쟁에서 탈락
    assert docfit["placed_pct"] == 83.3        # 12건 중 10건


def test_split_hint_for_oversized_table(doc, sample):
    """33행 표는 5칸 슬롯의 2배를 넘어 split — 몇 장으로 나눠야 하는지 수치로 낸다."""
    norm, frags = sample
    rep = slot_fit_report(norm, frags, format=FORMAT)
    hint = next(h for h in rep["split_hints"] if h["frag_id"] == "RA-d077508a-030")
    assert hint["scenes"] == 7 and "본문 슬라이드 7장" in hint["detail"]


# ── 5. 포맷 계약 — 낭독 스위치 · 씬 상한 방어 ───────────────────────────


def test_narration_follows_format_switch(doc, sample):
    """낭독 없는 포맷은 대본이 비고, 켠 포맷은 x-read 필드로 대본이 붙는다."""
    norm, frags = sample
    assert all(s.narration == "" for s in doc.scenes)
    spoken = assemble_doc_scenario(norm, frags, format=FORMAT_VOICED)
    assert spoken.format == FORMAT_VOICED
    assert all(s.narration.strip() for s in spoken.scenes)
    for s in spoken.scenes:
        chars = len(s.narration.replace(" ", ""))
        first = s.narration.split(". ")[0]
        assert chars <= max(int(s.dur * 5.5), len(first.replace(" ", "")))


def _big_report(n_pages: int) -> tuple[dict, list[dict]]:
    """구조 블록이 하나도 없고 페이지만 많은 합성 보고서 (상한 방어 + 폴백 근거 검증)."""
    pages, frags = [], []
    for p in range(1, n_pages + 1):
        name = f"{p}. 페이지 {p}"
        pages.append({"name": name, "blocks": [
            {"type": "heading", "id": f"h{p}", "content": {"text": f"제목 {p}"}},
            {"type": "bulleted_list", "id": f"b{p}", "content": {"items": [f"항목 {p}"]}},
            {"type": "heading", "id": f"g{p}", "content": {"text": f"부제 {p}"}},
            {"type": "rich_text", "id": f"r{p}", "content": {"markdown": f"리드 {p}"}},
        ]})
        frags.append({"frag_id": f"F{p}a", "type": "claim", "text": f"항목 {p} 본문",
                      "source": {"page": name, "block_id": f"b{p}"},
                      "widget": "bulleted_list", "confidence": 0.7})
        frags.append({"frag_id": f"F{p}b", "type": "claim", "text": f"리드 {p} 문장",
                      "source": {"page": name, "block_id": f"r{p}"},
                      "widget": "rich_text", "confidence": 0.6})
    norm = {"title": "대용량 보고서", "report_date": "2026-07-29", "tags": ["시험"],
            "pages": pages, "ai_summary": "", "search_text": ""}
    return norm, frags


def test_pages_without_structured_blocks_still_get_bodies(doc_env):
    """구조 블록이 없는 페이지도 본문이 생긴다 — 근거 슬롯은 그 페이지의 소절 구성으로 채운다."""
    norm, frags = _big_report(3)
    small = assemble_doc_scenario(norm, frags, format=FORMAT)
    assert validate_scenario(small, modules_root=MODULES, formats_root=doc_env) == []
    body = small.content["body-1-1"]
    assert body["evidence"]["kind"] == "table"
    assert body["evidence"]["table"]["headers"] == ["소절", "항목"]
    assert body["evidence"]["source"] == "원문 1. 페이지 1"
    assert len(body["bullets"]) >= 3      # 하한 3 — 원문에서 끌어온 것만


def test_scene_count_guard_truncates_sections(doc_env):
    """페이지가 많아도 ScenarioDoc 상한(50씬)을 넘지 않고, 잘린 절 수를 목차에 밝힌다."""
    norm, frags = _big_report(60)
    big = assemble_doc_scenario(norm, frags, format=FORMAT)
    assert len(big.scenes) <= 50
    assert validate_scenario(big, modules_root=MODULES, formats_root=doc_env) == []
    assert len([k for k in _keys(big) if k.startswith("section-")]) < 60
    assert "원문 참조" in big.content["toc"]["note"]


def test_video_formats_untouched_by_doc_path(sample):
    """문서형 추가가 영상 조립을 건드리지 않는다 — wide 7씬 / short 5씬 그대로."""
    norm, frags = sample
    with pytest.MonkeyPatch.context() as mp:
        mp.delenv("WDA_FORMATS_ROOT", raising=False)
        assert len(assemble_demo_scenario(norm, frags).scenes) == 7
        assert len(assemble_demo_scenario(norm, frags, format="short-9x16").scenes) == 5
