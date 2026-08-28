# 발표 레이아웃 8종 실증 드라이버 — 도달률 이전/이후 재측정 + 조립·빌드·씬 스틸·QA
"""실행: uv run python data/layout_check/driver.py [--skip-render]

무엇을 재는가.
  ① 도달률 이전/이후 — 같은 입력(examples/reportarchive/report_sample.json, 구조 12블록)
     을 두 포맷 풀로 재서 비교한다. 이전 = 본 formats/wide-16x9(7역할), 이후 =
     data/layout_check/formats(11역할, 신규 레이아웃 1순위).
  ② 렌더 실증 — 좌표 부록을 얹은 입력으로 12씬을 조립·빌드·캡처해 신규 8종이 한 번씩
     화면에 서는지 눈으로 확인한다(스틸은 data/quality_compare/layouts/).

레지스트리 주의. modules/registry.yaml 은 다른 워크플로가 편집 중이라 손대지 않는다.
대신 본 레지스트리 + modules/_pending/layouts-{a,b}.registry.yaml 을 **런타임에 합쳐**
data/layout_check/modules/registry.yaml 로 쓰고 WDA_MODULES_ROOT 로 주입한다.
빌드의 스크립트 로드 순서도 같은 이유로 병합본에서 파생시킨다(build._LOAD_ORDER 주입).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

REPORT = REPO / "examples" / "reportarchive" / "report_sample.json"
QUAD_REPORT = HERE / "report_sample_quad.json"
MODULES = HERE / "modules"
BUILD_DIR = REPO / "data" / "build" / "layout_check" / "main"
STILLS_DIR = REPO / "data" / "quality_compare" / "layouts"

# 병합 대기 조각 — 이번 라운드에서 심의할 8종
PENDING = ("layouts-a.registry.yaml", "layouts-b.registry.yaml")
# 병합 조각이 지시한 삽입 위치(둘 다 "<project scenes.jsx>" 앞이면 충돌 없음)
NEW_TEMPLATE_FILES = ("web/templates/omx-layouts-a.jsx", "web/templates/omx-layouts-b.jsx")


def merge_registry() -> Path:
    """본 registry.yaml + _pending 조각 → data/layout_check/modules/registry.yaml.

    scene-templates 는 심볼릭 링크로 원본을 가리킨다 — 사본을 뜨면 A·B 가 템플릿을
    고쳤을 때 이 실증이 옛 스키마를 재게 된다.
    """
    base = yaml.safe_load((REPO / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    have = {m["id"] for m in base.get("modules", [])}
    added: list[str] = []
    for name in PENDING:
        frag_path = REPO / "modules" / "_pending" / name
        if not frag_path.is_file():   # 오케스트레이터가 병합을 마치면 조각은 사라진다
            continue
        frag = yaml.safe_load(frag_path.read_text(encoding="utf-8"))
        for mod in frag.get("modules", []) or []:
            if mod["id"] not in have:
                base["modules"].append(mod)
                have.add(mod["id"])
                added.append(mod["id"])
    order = list(base.get("load_order_contract", []))
    tail = order.index("<project scenes.jsx>") if "<project scenes.jsx>" in order else len(order)
    for f in NEW_TEMPLATE_FILES:
        if f not in order:
            order.insert(tail, f)
            tail += 1
    base["load_order_contract"] = order

    MODULES.mkdir(parents=True, exist_ok=True)
    link = MODULES / "scene-templates"
    if not link.exists():
        link.symlink_to(REPO / "modules" / "scene-templates")
    out = MODULES / "registry.yaml"
    out.write_text(yaml.safe_dump(base, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"[registry] 병합 {len(added)}건 {added} · load_order {len(order)}단계 → {out}")
    return out


def quadrant_addendum() -> Path:
    """report_sample + 좌표 위젯 1블록 (l-quad 배선 실증용 — 합성임을 라벨에 밝힌다).

    y(세로)는 보고서의 실제 Phase 진척률이고 x(가로)는 심의가 매겨야 할 난이도라 원문에
    없다 — 그래서 이 블록은 '합성 부록'이고, 도달률 비교에는 쓰지 않는다.
    """
    doc = json.loads(REPORT.read_text(encoding="utf-8"))
    page = doc["pages"][-1]
    page["extra_blocks"].append(
        {
            "id": "quad_priority",
            "type": "quadrant",
            "props": {
                "label": "난이도 × 진척 (합성 부록)",
                "default_mode": "plot",
                "x_axis_title": "구현 난이도",
                "y_axis_title": "진척률",
                "x_range": [0, 10],
                "y_range": [0, 100],
            },
        }
    )
    page["content"]["quad_priority"] = {
        "mode": "plot",
        "plot_items": [
            {"id": "p01", "label": "게시 (Mount)", "x": 2, "y": 100},
            {"id": "p17", "label": "시스템 관리자 분리", "x": 3, "y": 100},
            {"id": "p2", "label": "작성자 hard lock", "x": 4, "y": 100},
            {"id": "p3", "label": "can_edit 풀 함수", "x": 8, "y": 70},
            {"id": "p4", "label": "내 공간 hub", "x": 6, "y": 30},
            {"id": "p5", "label": "종합보고 탭 분리", "x": 4, "y": 20},
            {"id": "p6", "label": "참조 복제 (Fork)", "x": 9, "y": 0},
        ],
    }
    page["block_sections"]["quad_priority"] = "reference"
    QUAD_REPORT.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return QUAD_REPORT


def fit_line(tag: str, rep: dict) -> str:
    t = rep["tally"]
    return (f"{tag:34s} 도달 {rep['reach_pct']:5.1f}% · 배치 {rep['placed_pct']:5.1f}% · "
            f"ok {t['ok']} trim {t['trim']} summ {t['summarized']} split {t['split']} "
            f"none {t['none']} · 씬 {len(rep['templates'])}종")


def main() -> int:
    merge_registry()
    os.environ["WDA_MODULES_ROOT"] = str(MODULES)

    from wdpipeline.fragmentize import fragmentize
    from wdpipeline.ingest import ingest_report_file
    from wdpipeline.scenario import assemble_demo_scenario, slot_fit_report, validate_scenario

    norm = ingest_report_file(REPORT)
    frags = fragmentize(norm)
    out: dict = {"input": str(REPORT.relative_to(REPO)), "structured_blocks": None, "runs": {}}

    # ── ① 도달률 이전/이후 (같은 12블록, 포맷 풀만 교체) ──────────────────
    os.environ["WDA_FORMATS_ROOT"] = str(REPO / "formats")
    before = slot_fit_report(norm, frags)
    before_st = slot_fit_report(norm, frags, structured_templates=True)
    os.environ["WDA_FORMATS_ROOT"] = str(HERE / "formats")
    after = slot_fit_report(norm, frags, structured_templates=True)
    out["structured_blocks"] = before["structured_blocks"]
    out["runs"] = {"before_default": before, "before_structured": before_st, "after_layouts": after}
    print(fit_line("이전 · 기본 7역할 풀", before))
    print(fit_line("이전 · 기본 풀 + 구조 대체", before_st))
    print(fit_line("이후 · 발표 레이아웃 11역할 풀", after))
    for r in after["rows"]:
        print(f"   {str(r['frag_id'])[-3:]} {str(r['widget']):14s} "
              f"{str(r['slot'] or '-'):26s} {r['items']:3d}→{r['carried']:3d} "
              f"{r['fit']:10s} placed={r['placed']}")

    # ── ② 렌더 실증 (좌표 부록 포함 12씬) ────────────────────────────────
    os.environ["WDA_FORMATS_ROOT"] = str(HERE / "formats_quad")
    qnorm = ingest_report_file(quadrant_addendum())
    qfrags = fragmentize(qnorm)
    doc = assemble_demo_scenario(qnorm, qfrags, structured_templates=True)
    errors = validate_scenario(doc)
    for e in errors:
        print(f"[검증 실패] {e}")
    if errors:
        return 1
    (HERE / "scenario.json").write_text(
        json.dumps(doc.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[조립] {len(doc.scenes)}씬 — {[s.tpl for s in doc.scenes]}")
    out["scenario"] = {"scenes": [{"name": s.name, "tpl": s.tpl, "dur": s.dur} for s in doc.scenes]}
    out["quad_fit"] = slot_fit_report(qnorm, qfrags, structured_templates=True)
    print(fit_line("부록 · 좌표 포함 13블록", out["quad_fit"]))

    if "--skip-render" not in sys.argv:
        out["render"] = render(doc)
    (HERE / "layout_fit.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[기록] {HERE / 'layout_fit.json'}")
    return 0


def render(doc) -> dict:
    """빌드 → 씬별 스틸 캡처 → 7게이트 QA."""
    from wdpipeline import build as buildmod
    from wdpipeline.build import ENTRY_NAME, build_render_package

    # 로드 순서는 registry 계약이 정본이다 — 병합본(WDA_MODULES_ROOT)에서 다시 파생시킨다
    contract = yaml.safe_load((MODULES / "registry.yaml").read_text(encoding="utf-8"))
    order = tuple(
        "./scenes.jsx" if s.startswith("<") else "./" + s[len("web/"):]
        for s in contract["load_order_contract"]
    )
    buildmod._LOAD_ORDER = order
    entry = build_render_package(doc, BUILD_DIR)
    print(f"[빌드] {entry} · 로드 {len(order)}단계 (신규 jsx 2건 포함)")

    from wdrender.page_session import RenderSession
    from wdrender.server import StaticServer

    STILLS_DIR.mkdir(parents=True, exist_ok=True)
    t0, plan = 0.0, []
    for i, s in enumerate(doc.scenes, 1):
        local = s.stills[0] if s.stills else s.dur * 0.9
        plan.append((f"{i:02d}_{s.tpl.split('@')[0]}", t0 + local))
        t0 += s.dur
    with StaticServer(BUILD_DIR) as srv, \
            RenderSession(srv.url_for(ENTRY_NAME), width=1920, height=1080) as sess:
        print(f"[렌더] duration={sess.duration}s sync_seek={sess.sync_seek}")
        for name, t in plan:
            sess.seek(t)
            sess.capture(STILLS_DIR / f"{name}.png")
    print(f"[렌더] 스틸 {len(plan)}장 → {STILLS_DIR}")

    from wdqa.gates import run_gates

    qa = run_gates(BUILD_DIR, scenario=doc.model_dump())
    (HERE / "qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    sev: dict[str, int] = {}
    for r in qa.get("results", []):
        sev[r.get("severity")] = sev.get(r.get("severity"), 0) + 1
    print(f"[QA] passed={qa.get('passed')} severities={sev}")
    return {"stills": [n for n, _ in plan], "qa_passed": qa.get("passed"), "severities": sev,
            "results": qa.get("results", [])}


if __name__ == "__main__":
    raise SystemExit(main())
