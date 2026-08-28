# 발표 레이아웃 8종(tpl.l-*) 모듈 승격 심사 8건을 wdcore MeetingEngine 으로 실구동한다
"""실행: uv run python data/layout_check/review_driver.py

산출: data/meetings/{stamp}_module_review_tpl-l-*/ (meta.json · turns.jsonl · minutes.md)
      data/layout_check/verdicts_20260729.json

발언은 이 스크립트가 쓰지만 **진행은 엔진이 강제**한다 — 라운드 템플릿(present →
review×2사이클 → rebuttal → verdict), 발언 차례, 인용 필수 라운드의 citations,
known_refs 밖 인용 차단이 전부 MeetingEngine.submit_turn 검증을 통과한 것이다.

근거 카드(known_refs)는 전부 이번 라운드의 실행 산출물이다 — 도달률 재실측
(data/layout_check/layout_fit.json), 게이트 리포트(data/qa_reports/*), 12씬 실렌더
스틸(data/quality_compare/layouts/), 조립 결과(data/layout_check/scenario.json),
슬롯 상한 스캔(catalog_slots.json), 테스트 수치, 그리고 스키마·소스 사실.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "src"))

from wdcore.meetings.engine import MeetingEngine          # noqa: E402
from wdcore.meetings.store import MeetingStore            # noqa: E402
from wdcore.models.meeting import (                       # noqa: E402
    Artifact,
    Citation,
    MeetingTurn,
    MeetingType,
    SpeakerRole,
)
from wdcore.registry.registry import load_registry        # noqa: E402

# ── 근거 카드 — 전부 실행 산출물의 실측 수치다 (환각 인용은 엔진이 거부한다) ──
EVIDENCE: dict[str, str] = {
    "EV-FIT-BEFORE": "data/layout_check/layout_fit.json runs.before_default — 기본 7역할 풀, "
                     "report_sample 구조 12블록: 도달 75.0% · 배치 58.3% "
                     "(ok 0 · trim 3 · summarized 2 · split 4 · none 3)",
    "EV-FIT-STRUCT": "layout_fit.json runs.before_structured — 기본 풀 + 구조 대체(True): "
                     "도달 66.7% · 배치 41.7%. 대체는 자리를 바꿀 뿐 늘리지 못한다는 기존 관측 재확인",
    "EV-FIT-AFTER": "layout_fit.json runs.after_layouts — 발표 레이아웃 11역할 풀: "
                    "도달 91.7% · 배치 75.0% (ok 2 · trim 3 · summarized 5 · split 1 · none 1). "
                    "신규 슬롯 도달 5건 — l-list.rows 9→8 · l-tree.nodes 15→12 · "
                    "l-split.visual.table.rows 5→5(ok) · l-mix.table.rows 8→5 · l-kpi.metrics 7→6. "
                    "남은 none 1건은 4열 2행 표(모든 표 슬롯의 행 하한 3 미달)",
    "EV-QA": "data/qa_reports/20260729-030823-2c540c/qa.json — 12씬 빌드에 게이트 7종"
             "(contrast·determinism·font·frame_match·length·mapping·overflow) 전부 실행, "
             "error 0 · warning 0 · info 0",
    "EV-STILLS": "data/quality_compare/layouts/ 12장(01_opening~12_closing) — 신규 8종이 "
                 "한 번씩 실렌더된 1920×1080 씬 스틸",
    "EV-DENSITY": "같은 보고서의 실린 글자수(공백·비표시 필드 제외) — 기본 7씬 1351자 vs "
                  "발표 레이아웃 12씬 2388자(+76.8%). 씬별 최대 l-tree 395 · l-list 339 · "
                  "l-split 272 · l-ba 260 (기존 최대는 proof 256)",
    "EV-DENSITY-THIN": "같은 집계에서 l-kpi 68자 · l-quad 119자 — 12씬 중 최소 2건. "
                       "opening(67자)과 같은 급이다",
    "EV-SLOTS": "data/layout_check/catalog_slots.json (schema.json 실측) — proof.cases 2~3 "
                "title24/desc70 · process.steps 3~6 name12/desc40 · compare.rows 2~4 "
                "aspect4/a44/b44 · concept.nodes 4~8 name12 · closing.stats 2~3 v14/d24 · "
                "dataviz.bars 2~5 label9 · d-matrix.rows 2~8 label24 || l-list.rows 5~8 "
                "title30/desc100 · l-tree.nodes 3~13 label22/note13 · l-kpi.metrics 4~6 "
                "label14/value6/unit3 · l-quad.items 4~10 label18 · l-ba.before.items 3~5 "
                "text22 · l-mix.table.rows 3~5 label13 · l-mix.chart.bars 3~4 label18/display6 · "
                "l-split.bullets 3~5 text40 · l-split.visual.table.rows 3~6 label20",
    "EV-SCENE-SPLIT": "data/layout_check/scenario.json content.problem — visual.kind=table, "
                      "columns ['항목','게시 (Mount)','참조 복제 (Fork)'](원문 4열 중 3열), "
                      "conclusion {pre:'근거는 원문 ', strong:'표 그대로', post:' · 외 1열'}. "
                      "초판에서는 주장 문장을 12자에 넣어 '엔지니어 → 임원… 설명서· 외 1열' 로 깨졌다",
    "EV-SCENE-LIST": "content.detail — rows 8행(전부 desc 보유), title '런타임 / 의존성 (외 1건)'. "
                     "l-list 스키마에 omitted 필드가 없어 생략 표기를 타이틀 26자에 얹었다",
    "EV-SCENE-TREE": "content.concept — nodes 12(레벨 0/1/2 = 1/3/8) · edges 11 · omitted 3. "
                     "키는 payload 의 {id,label,level,note}·{from,to} 그대로",
    "EV-SCENE-BA": "content.differentiator — before.summary {value:'5', desc:'개 관점'} · "
                   "after.summary {value:'5', desc:'개 관점'}. comparison payload 에 수치 행이 "
                   "없어 비교 관점 수로 채웠고, 92px display 두 개가 같은 값을 띄운다",
    "EV-SCENE-MIX": "content.matrix — stats [7개 전체 항목 / 100% Phase 0/1 / 60% 평균]"
                    "(원 계열의 산술 집계), table 은 raci 6열 중 3열, note '생략 3행·2열·3계열'",
    "EV-SCENE-KPI": "content.dashboard — metrics 6개 전부 {label, value, unit} 뿐. "
                    "delta·spark 없음, omitted 1. label 은 'Phase 0/1'(원문 38자 라벨의 앞머리)",
    "EV-SCENE-QUAD": "content.position — items 7, xAxis {name:'난이도', low:'2', high:'9'}, "
                     "yAxis {name:'진척', low:'0', high:'100'}, quadrants {tl:'좌상', tr:'우상', "
                     "bl:'좌하', br:'우하'}. 축 이름은 캡션 '난이도 × 진척' 파싱으로 복구했고 "
                     "사분면 이름은 위치어다",
    "EV-SCENE-QUOTE": "content.verdict — quote '보고서를 사본이 아닌 live link로 여러 게시판에 "
                      "동시 노출(Mount)한다.'(원문 purpose 절 문장), speaker/role 은 보고서 제목·날짜",
    "EV-QUAD-OVERLAP": "기하 실측(omx-layouts-b.jsx qdGeo: plot 110,52,858×488 · dot 44 · "
                       "inset 26 · 사분면 이름 note 25px) — tl 라벨 상자 (124,66)~(384,98) 와 "
                       "항목 점(x=0,y=1) 상자 (114,56)~(158,100) 이 34×32px 겹친다. "
                       "겹치는 좌표 영역은 x<0.335 ∧ y>0.904 (판 좌상 1/3×1/10)",
    "EV-QUAD-UPSTREAM": "src/wdpipeline/widgets.py _x_quadrant — props.x_axis_title/"
                        "y_axis_title/x_range 를 payload 에 싣지 않는다(y_range 만 axis 로). "
                        "가로 정규화가 데이터 범위(2~9)로 떨어져 원 위젯 선언(0~10) 대비 최대 "
                        "20%p 이동한다 — x=5 항목은 선언 기준 경계 0.5, 데이터 기준 0.43(좌측 사분면)",
    "EV-OWNER-ORDER": "src/wdpipeline/scenario.py _assign — owner 배정 순서에서 concept.nodes 가 "
                      "l-tree.nodes 보다 먼저 graph payload 를 가져간다. 두 템플릿이 같은 풀에 "
                      "있으면 소유권이 스키마가 아니라 코드 순서로 갈린다",
    "EV-FIT-CHAIN": "scenario.py _fit_record 표 분기 순서 — compare/differentiator/l-ba → "
                    "proof(그룹 요약) → l-mix → d-matrix → l-split. 하나의 표를 받을 수 있는 "
                    "씬이 5개이고 우선순위는 스키마가 아니라 이 if/elif 순서다",
    "EV-NEEDS-PAYLOAD": "scenario.py _NEEDS_PAYLOAD — payload 전용 템플릿이 역할 1순위인데 "
                        "대응 payload 가 없으면 폴백 가능한 템플릿에 자리를 넘긴다. "
                        "l-quad 단독 풀에서 조립이 붕괴하던 것을 이 규칙으로 막았다",
    "EV-SCHEMA-SPLIT": "modules/scene-templates/l-split/schema.json — bullets 3~5, "
                       "allOf: bullets.minItems 5 이면 text.maxLength 40→22. "
                       "conclusion {pre 12, strong 10, post 12}, visual.table columns 2~3·rows 3~6, "
                       "ratio enum ['6:4','5:5']",
    "EV-SCHEMA-LIST": "l-list/schema.json — rows 5~8, allOf: rows.minItems 6 이면 "
                      "desc.maxLength 100→50. chip {text 6, tone 4종}. omitted 필드 없음",
    "EV-SCHEMA-TREE": "l-tree/schema.json — nodes 3~13, contains/maxContains 로 레벨별 "
                      "1 / 2~4 / ≤8, 레벨별 label 14/18/22. 가지당 리프 상한은 description "
                      "문구('가지당 4개')뿐 — 검증되지 않는다. note 는 모든 레벨에 허용",
    "EV-SCHEMA-QUOTE": "l-quote/schema.json — quote 70자(x-read), speaker 20 / role 26, "
                       "texture enum none/rule/marks. 구조 payload 대응 없음",
    "EV-SCHEMA-KPI": "l-kpi/schema.json — metrics 4~6, value pattern ^-?[0-9][0-9.,]*$ maxLength 6, "
                     "unit 3, delta {dir up/down/flat, tone good/bad/neutral} optional, "
                     "spark 3~8 optional, omitted 있음",
    "EV-SCHEMA-QUAD": "l-quad/schema.json — items 4~10 (x·y 0~1 필수), xAxis/yAxis {name 14, "
                      "low·high}, quadrants tl/tr/bl/br 전부 required(각 9자), highlight optional",
    "EV-SCHEMA-BA": "l-ba/schema.json — $defs/side 를 before·after 가 공유. side.summary 는 "
                    "required 이고 value pattern ^-?[0-9][0-9.,]*$. rows 필드 없음(compare 와 "
                    "모양이 겹치지 않게)",
    "EV-SCHEMA-MIX": "l-mix/schema.json — oneOf 로 stats(2~3)와 lead 배타, table columns 3~4 · "
                     "rows 3~5 · cells v 6자, chart.bars 3~4. 셀 6자 조건은 스키마가 표현하지 "
                     "못해 조립기 _mix_table 이 '짧은 값 열만' 고르는 필터를 따로 갖는다",
    "EV-TESTS-MINE": "uv run pytest tests/test_scenario_layouts.py → 12 passed "
                     "(기본 풀 회귀 · 라우팅 8종 · 용량/정직 표기 · 좌표 정규화 순서 보존)",
    "EV-TESTS-AB": "uv run pytest tests/test_layouts_a_* → 191 passed · "
                   "tests/test_layouts_b_* → 145 passed (템플릿 제작측 검증)",
    "EV-SUITE": "uv run pytest -q → 1971 passed · 1 failed · 6 skipped. 유일한 실패는 "
                "test_build_loadorder.py::test_every_template_file_is_loaded — registry.yaml "
                "병합 대기(omx-layouts-a/b/c/d·openings·closings 6파일, 4개 워크플로 공통 항목)",
    "EV-REG-PENDING": "modules/_pending/layouts-a.registry.yaml · layouts-b.registry.yaml — "
                      "registry.yaml 직접 수정 없이 병합 조각으로 제출됨(로드 순서 삽입 지시 포함)",
    "EV-CATALOG": "docs/analysis/layout-catalog.md — 레이아웃 21종 전수 표(기존 13 + 신규 8): "
                  "담는 데이터 형태 · 항목 상한 · 언제 쓰나 · 구조 payload 대응",
    "EV-PRIOR-0726": "data/module_review/verdicts_20260726.json — 선례 3건 "
                     "(tpl.dataviz Go / tpl.timeline·tpl.compare Conditional-Go). "
                     "'max 픽스처가 스키마 상한의 54%만 검증' 이 당시 blocking finding 이었다",
    "EV-PRIOR-0729": "data/coverage_check/verdicts_20260729.json — 같은 날 선례 4건"
                     "(c-ratio/c-trend/c-branch/c-grid). '왜곡을 구조로 막는다'는 주장은 "
                     "적대적 입력에서 검증돼야 한다는 기준이 확립됐다",
    "EV-A-CLAIM": "제안자(A) 주장 — l-split/l-list/l-tree/l-quote 는 '밀도를 스키마가 강제한다'. "
                  "maxLength 를 1920×1080 실측 역산으로 잡고 조건부 allOf 로 개수↑ = 자수↓ 를 강제",
    "EV-B-CLAIM": "제안자(B) 주장 — l-kpi/l-quad/l-ba/l-mix 는 '수치의 방향과 평가를 분리'하고"
                  "(delta.dir vs delta.tone) 좌표 라벨 충돌을 번호↔범례 구조로 없앴다",
}

PANEL = ["impl-technical-director", "qa-consistency", "mot-motion-director", "vis-layout-grid"]
TD, QA, MO, LG = PANEL
TY, DV, CW, SA = ("vis-typographer", "vis-dataviz", "narr-copywriter", "narr-story-architect")

# 제안자 대리 — 텍스트 배치 4종은 TY/CW, 수치 배치 4종은 DV, 전환 서사는 SA 가 대리한다.
# l-tree 는 배치 계산이 본체라 LG 가 제안자를 겸한다(2026-07-26 MO 겸임 · 07-29 c-branch 선례).
REVIEWS: dict[str, dict] = {
    "tpl.l-split": {"topic": "tpl.l-split 모듈 승격 심사 — 좌 설명 + 우 근거 2단", "proxy": TY},
    "tpl.l-list": {"topic": "tpl.l-list 모듈 승격 심사 — 목록형 상세 5~8행", "proxy": TY},
    "tpl.l-tree": {"topic": "tpl.l-tree 모듈 승격 심사 — 계층 구조도", "proxy": None},
    "tpl.l-quote": {"topic": "tpl.l-quote 모듈 승격 심사 — 핵심 문장 강조", "proxy": CW},
    "tpl.l-kpi": {"topic": "tpl.l-kpi 모듈 승격 심사 — 다지표 계기판", "proxy": DV},
    "tpl.l-quad": {"topic": "tpl.l-quad 모듈 승격 심사 — 4분면 포지셔닝", "proxy": DV},
    "tpl.l-ba": {"topic": "tpl.l-ba 모듈 승격 심사 — Before/After 반반", "proxy": SA},
    "tpl.l-mix": {"topic": "tpl.l-mix 모듈 승격 심사 — 표 + 차트 혼합", "proxy": DV},
}


def T(round_no: int, role: str, text: str, *, who: str | None = None,
      stance: str | None = None, refs: list[str] | None = None,
      arts: list[tuple[str, str]] | None = None) -> MeetingTurn:
    return MeetingTurn(
        round_no=round_no,
        role=SpeakerRole(role),
        expert_id=who,
        stance=stance,
        content_md=text,
        citations=[Citation(ref=r, quote=EVIDENCE[r][:180]) for r in (refs or [])],
        artifacts=[Artifact(type=a, content=c) for a, c in (arts or [])],
    )


# ── 심의 대본 8건 (라운드·차례·인용은 엔진이 강제한다 — 여기는 내용만) ─────


def s_split(px: str) -> list[MeetingTurn]:
    return [
        T(0, "moderator",
          "모듈 후보 tpl.l-split 을 대독한다. 용도는 실무 발표자료의 최다 사용 배치 — 좌 열에 "
          "리드 + 불릿 3~5 + 하단 고정 소결론, 우 열에 근거 슬롯 4종(간이표/막대/도판/강조 박스). "
          "구조 매핑에서는 '달리 갈 곳 없던 표'를 받아 도달률을 올렸다. 심사 범위는 ① 기존 표 씬"
          "(d-matrix·l-mix·proof)과의 경계 ② 슬롯 이름과 실제 용량의 일치 ③ 생략 표기의 정직성이다.",
          refs=["EV-SCHEMA-SPLIT", "EV-FIT-AFTER", "EV-STILLS"],
          arts=[("module_candidate", "tpl.l-split v1.0.0 draft — 좌 설명 + 우 근거 2단 (nat 14)")]),
        # ── review 사이클 1 ──
        T(1, "expert", who=TD, stance="support",
          text="엔진 축은 통과다. 12씬 빌드에서 게이트 7종 error 0 · warning 0 · info 0 이고 "
               "frame-match 도 걸리지 않았다. 다만 ratio enum('6:4'/'5:5')은 데이터가 아니라 저작 "
               "선택인데 조립기는 항상 '6:4'만 쓴다 — Finding F3(minor): 쓰이지 않는 자유도가 "
               "스키마에 남아 있고 default 선언도 없다.",
          refs=["EV-QA", "EV-SCHEMA-SPLIT"],
          arts=[("finding", "F3(minor) ratio enum 이 저작 전용 자유도인데 default 미선언 — "
                            "자동 경로는 항상 6:4")]),
        T(1, "expert", who=QA, stance="concern",
          text="Finding F1(major): 슬롯 이름과 용량이 어긋난다. conclusion 은 pre 12 + strong 10 "
               "+ post 12 = 34자인데 스키마는 이걸 '소결론'이라 부른다. 조립기가 주장 문장을 넣자 "
               "'엔지니어 → 임원… 설명서· 외 1열' 로 뜻이 깨져, 지금은 근거 출처 문구"
               "('근거는 원문 표 그대로 · 외 1열')로 대체했다. 즉 이 자리는 결론이 아니라 꼬리표다.",
          refs=["EV-SCENE-SPLIT", "EV-SCHEMA-SPLIT"],
          arts=[("finding", "F1(major) conclusion 34자 슬롯에 '소결론'을 담을 수 없다 — "
                            "이름과 용량 불일치, 자동 경로는 출처 문구로 우회 중")]),
        T(1, "expert", who=MO, stance="support",
          text="등장 순서가 논증 순서와 일치한다 — 좌 텍스트가 다 서고 우 근거가 뒤따르는 순서라 "
               "'설명하고 근거를 내민다'는 서사가 모션으로 성립한다. 소결론이 bottom 앵커라 불릿이 "
               "길어져도 바닥이 흔들리지 않는 것도 확인했다. 모션 축 결함 없다.",
          refs=["EV-STILLS", "EV-A-CLAIM"]),
        T(1, "expert", who=LG, stance="concern",
          text="격자는 실측과 맞다(설명 열 637px · 근거 열 955px). Finding F2(minor): 생략 표기 "
               "자리가 conclusion.post 12자 하나뿐이다. 이번 실증에서 원문 4열 중 1열이 빠져 "
               "'· 외 1열'이 들어갔는데, 행까지 잘리는 표에서는 열·행 생략이 자리를 두고 다툰다 — "
               "조립기가 둘 중 하나만 적는다.",
          refs=["EV-SCENE-SPLIT", "EV-SLOTS"],
          arts=[("finding", "F2(minor) 생략 표기 자리가 12자 하나뿐 — 열 생략과 행 생략이 "
                            "동시에 나면 한쪽이 사라진다")]),
        T(1, "expert", who=px, stance="propose",
          text="제안자 대리로 설계 의도를 밝힌다. 이 템플릿의 핵심은 밀도를 스키마가 강제한다는 "
               "것이다 — bullets.minItems 5 이면 text.maxLength 가 40에서 22로 조인다. '많이 넣으면 "
               "글자가 작아진다'가 아니라 '많이 넣으면 스키마가 먼저 거절한다'가 되게 했다. "
               "F1 은 부인하지 않는다. conclusion 은 원래 '한 줄 착지'로 설계했고 이름이 과했다.",
          refs=["EV-SCHEMA-SPLIT", "EV-A-CLAIM"]),
        # ── review 사이클 2 ──
        T(1, "expert", who=TD, stance="question",
          text="F1 의 수정 방향을 묻는다. 슬롯을 넓히면(예: lead 급 30자) 하단 고정 높이 137px "
               "전제가 흔들리고, 이름을 tail 로 바꾸면 저작 시나리오가 기대하던 '결론' 자리가 "
               "사라진다. 제안자가 둘 중 하나를 골라야 한다.",
          refs=["EV-SCHEMA-SPLIT"]),
        T(1, "expert", who=QA, stance="concern",
          text="재발명 축을 따로 남긴다. 하나의 표를 받을 수 있는 씬이 지금 5개다 — "
               "compare/l-ba → proof → l-mix → d-matrix → l-split 순으로 조립기 if/elif 가 "
               "정한다. l-split 은 '설명의 근거'라는 자리로 구분되지만 그 구분이 스키마에 없다. "
               "재발명은 아니되 경계는 문서에만 있다.",
          refs=["EV-FIT-CHAIN", "EV-CATALOG"],
          arts=[("open_issue", "표를 받는 씬 5개의 우선순위가 조립기 if/elif 에만 있다 — "
                               "포맷 풀 규약으로 올려야 한다")]),
        T(1, "expert", who=MO, stance="support",
          text="추가 지적 없다. 낭독은 15.0초에 50자(3.33자/초)로 예산 5.5 안이다.",
          refs=["EV-DENSITY"]),
        T(1, "expert", who=LG, stance="support",
          text="밀도는 목적을 달성했다 — 이 씬이 272자로 기존 최대(proof 256자)를 넘겼고 "
               "표까지 같은 화면에 있다.",
          refs=["EV-DENSITY"]),
        T(1, "expert", who=px, stance="accept",
          text="F1 은 이름을 고치는 쪽으로 수용한다 — 슬롯을 넓히면 하단 고정이 깨지므로 "
               "'conclusion → tail(꼬리 한 줄)' 로 개명하고 description 에 '결론 문장은 저작 "
               "시나리오의 lead 를 쓰라'고 못박겠다. F2 는 생략 표기 전용 필드(omitted 계열) "
               "신설로, F3 은 ratio default '6:4' 선언으로 수용한다.",
          refs=["EV-SCENE-SPLIT", "EV-SCHEMA-SPLIT"]),
        # ── rebuttal ──
        T(2, "expert", who=TD, stance="accept",
          text="개명은 스키마 major 변경이 아니다(draft 상태). 수정 후 게이트 7종 재실행 조건을 단다.",
          refs=["EV-QA"]),
        T(2, "expert", who=QA, stance="accept",
          text="F1 을 minor 로 낮추자는 주장은 없었다. 다만 blocking 은 아니다 — 화면이 거짓을 "
               "말하지는 않기 때문이다. major 유지하고 등록 조건으로 건다.",
          refs=["EV-SCENE-SPLIT"]),
        T(2, "expert", who=MO, stance="accept",
          text="세 Finding 모두 스케줄에 영향 없다. schedule(data) 경로는 그대로다.",
          refs=["EV-A-CLAIM"]),
        T(2, "expert", who=LG, stance="accept",
          text="F2 는 F1 과 함께 닫힌다 — 꼬리 한 줄이 생략 전용 자리를 얻으면 둘 다 해소된다.",
          refs=["EV-SCENE-SPLIT"]),
        T(2, "expert", who=px, stance="accept", text="반박하지 않는다. 세 건 전부 수용한다.",
          refs=["EV-SCHEMA-SPLIT"]),
        T(3, "moderator",
          "판정 — **Conditional-Go**. 재발명은 아니다(좌 설명 + 우 근거 2단 슬롯이 카탈로그 13종 "
          "어디에도 없었고, 이 씬 덕에 4열 5행 비교 표가 처음으로 ok 판정을 받았다). 밀도 주장도 "
          "실측으로 성립한다(272자, 기존 최대 초과). 걸린 것은 슬롯 이름과 용량의 불일치 하나다. "
          "status draft 유지.",
          arts=[("decision", "tpl.l-split — Conditional-Go (F1 해소 시 draft→pilot). "
                             "구조 매핑 도달 기여 확인: 표 1건이 none→ok"),
                ("action_item", "F1: conclusion 을 tail 로 개명하고 '한 줄 꼬리표' 계약을 "
                                "description 에 명시 (vis-typographer)"),
                ("action_item", "F2: 생략 표기 전용 필드 신설 — 열·행 생략이 서로를 지우지 않게 "
                                "(vis-typographer)"),
                ("action_item", "F3: ratio default '6:4' 선언 (vis-typographer)"),
                ("action_item", "수정 후 게이트 7종 재실행 (impl-technical-director)")]),
    ]


def s_list(px: str) -> list[MeetingTurn]:
    return [
        T(0, "moderator",
          "모듈 후보 tpl.l-list 를 대독한다. 용도는 process(6칸 그리드)·proof(3열 카드)가 못 담는 "
          "목록형 상세 5~8행이다. 구조 매핑에서 키값 9쌍을 받아 8행으로 실었다 — 기존 경로는 "
          "proof.cases 카드 1장에 2줄로 뭉개던 자리다. 심사 범위는 ① 재발명 여부 ② 생략의 정직성 "
          "③ 상태 칩이 자동 경로에서 채워지는가다.",
          refs=["EV-SCHEMA-LIST", "EV-FIT-AFTER", "EV-SCENE-LIST"],
          arts=[("module_candidate", "tpl.l-list v1.0.0 draft — 목록형 상세 5~8행 (nat 14)")]),
        T(1, "expert", who=TD, stance="support",
          text="엔진 축 통과. 행 순차 등장과 홀짝 교차는 전부 localTime 의 함수이고 게이트 7종 "
               "error 0 이다. 8행 픽스처에서 스크롤 넘침도 0건이다.",
          refs=["EV-QA", "EV-STILLS"]),
        T(1, "expert", who=QA, stance="rebut",
          text="Finding F1(blocking): omitted 필드가 없다. 키값 9쌍 중 8행만 실리는데 스키마에 "
               "생략을 계상할 자리가 없어 조립기가 타이틀 꼬리로 우회했다 — 실제 결과가 "
               "'런타임 / 의존성 (외 1건)' 이고, 26자 타이틀을 생략 표기가 잠식한다. "
               "l-tree·l-kpi·d-matrix 는 모두 omitted 를 가진다. 카탈로그 일관성 위반이다.",
          refs=["EV-SCENE-LIST", "EV-SLOTS", "EV-SCHEMA-LIST"],
          arts=[("finding", "F1(blocking) omitted 필드 부재 — 생략 표기가 타이틀 26자를 "
                            "잠식한다. 같은 카탈로그의 l-tree·l-kpi·d-matrix 와 불일치")]),
        T(1, "expert", who=MO, stance="support",
          text="위→아래 순차 등장이 읽는 순서와 같다. 8행에서도 행 간 지연이 누적 과다로 가지 "
               "않는다(낭독 13자/15초 — 이 씬은 화면을 읽히는 씬이라 낭독이 짧은 게 옳다).",
          refs=["EV-DENSITY", "EV-STILLS"]),
        T(1, "expert", who=LG, stance="concern",
          text="Finding F2(minor): 우측 상태 칩은 4톤을 갖지만 구조 payload(pairs)에는 상태 필드가 "
               "없다. 자동 경로에서는 절대 채워지지 않아 폭 180px 가 상시 공백이다. 스틸에서도 "
               "8행 전부 칩이 없다. 저작 시나리오 전용 슬롯이면 그렇게 선언해야 한다.",
          refs=["EV-SCENE-LIST", "EV-STILLS"],
          arts=[("finding", "F2(minor) chip 은 구조 payload 로 채울 수 없다 — 자동 경로에서 "
                            "우측 180px 상시 공백")]),
        T(1, "expert", who=px, stance="propose",
          text="제안자 대리로 밝힌다. 이 템플릿의 계약은 '행이 늘면 스키마가 설명을 조인다'다 — "
               "rows.minItems 6 이면 desc 가 100자에서 50자로 내려간다. 실증에서 8행 전부 desc 를 "
               "달고도 최소 폰트 24px 를 지켰다. F1 은 수용한다.",
          refs=["EV-SCHEMA-LIST", "EV-SCENE-LIST"]),
        T(1, "expert", who=TD, stance="support",
          text="추가 없음. F1 은 스키마 필드 추가라 렌더 변경이 작다(타이틀 옆 표기 1개).",
          refs=["EV-SCHEMA-LIST"]),
        T(1, "expert", who=QA, stance="support",
          text="재발명 심사 결과를 남긴다 — **재발명 아니다**. 실측 용량으로 축이 다르다: "
               "proof.cases 는 3장 × (title 24 + desc 70) = 282자, process.steps 는 6칸 × "
               "(name 12 + desc 40) = 312자인데 l-list 는 8행 × (title 30 + desc 100) = 1040자다. "
               "밀도 축이 3배 이상 다르면 같은 그릇이 아니다.",
          refs=["EV-SLOTS", "EV-DENSITY"]),
        T(1, "expert", who=MO, stance="support", text="추가 없음.", refs=["EV-STILLS"]),
        T(1, "expert", who=LG, stance="support",
          text="밀도 실측 339자로 12씬 중 2위다. 목적을 달성했다.", refs=["EV-DENSITY"]),
        T(1, "expert", who=px, stance="accept",
          text="F1 은 omitted(integer, minimum 1) 신설로, F2 는 chip 을 '저작 전용'으로 "
               "description 에 명시하고 위젯이 status 를 싣게 되면 자동 경로를 열겠다.",
          refs=["EV-SCHEMA-LIST"]),
        T(2, "expert", who=TD, stance="accept",
          text="수용. 필드 추가 후 게이트 재실행과 픽스처 3종 갱신이 조건이다.", refs=["EV-QA"]),
        T(2, "expert", who=QA, stance="rebut",
          text="F1 을 minor 로 낮추자는 반론이 있다면 반박한다. 생략을 타이틀에 얹는 것은 "
               "'무언의 절단 금지' 규칙을 형식만 지킨 것이고, 타이틀이 잘리면 생략 표기 자체가 "
               "사라진다. blocking 유지.",
          refs=["EV-SCENE-LIST"]),
        T(2, "expert", who=MO, stance="accept", text="이견 없다.", refs=["EV-STILLS"]),
        T(2, "expert", who=LG, stance="accept",
          text="F2 는 non-blocking 으로 남긴다 — 빈 칩 자리는 왜곡이 아니라 여백이다.",
          refs=["EV-SCENE-LIST"]),
        T(2, "expert", who=px, stance="accept", text="두 건 모두 수용한다.",
          refs=["EV-SCHEMA-LIST"]),
        T(3, "moderator",
          "판정 — **Conditional-Go**. 재발명 없음(밀도 축이 proof·process 와 3배 이상 다르고, "
          "이 씬 덕에 키값 9쌍이 2줄 압축에서 8행으로 올라왔다). 걸린 것은 생략 계상 필드 부재 "
          "하나이며 이는 카탈로그 일관성 문제다. status draft 유지.",
          arts=[("decision", "tpl.l-list — Conditional-Go (blocking F1 해소 시 draft→pilot). "
                             "키값 payload 도달 개선 확인: proof.cases split → l-list.rows"),
                ("action_item", "F1: omitted 필드 신설 + 렌더 표기 (vis-typographer)"),
                ("action_item", "F2: chip 을 저작 전용으로 명시, 위젯 status 전달 시 자동 경로 "
                                "개방 (vis-typographer)"),
                ("action_item", "필드 추가 후 픽스처 3종 갱신 + 게이트 재실행 "
                                "(impl-technical-director)")]),
    ]


def s_tree(_px: str | None) -> list[MeetingTurn]:
    return [
        T(0, "moderator",
          "모듈 후보 tpl.l-tree 를 대독한다. 용도는 위계다 — tpl.concept 의 방사형이 '동등한 "
          "참여자'를 그린다면 이것은 루트 1 · 중간 2~4 · 리프 ≤8 의 3단 위계를 직교 경로로 잇는다. "
          "structured graph(shape=tree)의 nodes/edges 를 개명 없이 받는다. 제안자가 배치 계산을 "
          "본체로 만든 템플릿이라 LG 가 제안자를 겸한다(07-26 MO 겸임 선례). 심사 범위는 "
          "① concept 과의 재발명 ② 용량이 구조로 강제되는가 ③ 생략의 정직성이다.",
          refs=["EV-SCHEMA-TREE", "EV-SCENE-TREE", "EV-PRIOR-0726"],
          arts=[("module_candidate", "tpl.l-tree v1.0.0 draft — 계층 구조도 (nat 12)")]),
        T(1, "expert", who=TD, stance="support",
          text="엔진 축 통과. 12씬 빌드 게이트 7종 error 0 이고, 실증에서 15노드 트리가 "
               "12노드(레벨 1/3/8) + 엣지 11개로 실렸으며 남은 3개는 omitted 로 계상됐다. "
               "payload 키를 그대로 받는다는 주장도 확인했다 — nodes 는 {id,label,level,note}, "
               "edges 는 {from,to} 그대로다.",
          refs=["EV-SCENE-TREE", "EV-QA"]),
        T(1, "expert", who=QA, stance="concern",
          text="Finding F1(major): 가지당 리프 상한이 **검증되지 않는다**. 스키마는 리프 총합 8만 "
               "강제하고 '가지당 4개'는 description 문구뿐이다. 한 가지에 8리프를 몰아넣은 입력도 "
               "스키마 유효이고, 그러면 세로 예산 650~948px 를 깬다. 이번 조립기는 올림 배분"
               "(3·3·2)으로 피했지만 저작 시나리오에는 방어가 없다.",
          refs=["EV-SCHEMA-TREE", "EV-SCENE-TREE"],
          arts=[("finding", "F1(major) 가지당 리프 상한이 description 문구뿐 — 한 가지 8리프 "
                            "입력이 스키마 유효이고 세로 예산을 깬다")]),
        T(1, "expert", who=MO, stance="support",
          text="레벨별 순차 등장(루트 스텁 → 가로 버스 → 가지 스텁 → 세로 레일)이 위계를 읽는 "
               "순서와 같다. 스틸에서 '…외 3개 노드'가 루트와 같은 높이 우측에 서서 생략을 "
               "먼저 알린다 — 순서상 옳다. 모션 결함 없다.",
          refs=["EV-STILLS", "EV-SCENE-TREE"]),
        T(1, "expert", who=LG, stance="propose",
          text="제안자를 겸해 설계 의도를 밝힌다. 레벨을 화면 축으로 삼은 것이 핵심이다 — "
               "concept 은 15노드에서 얕은 레벨 8개만 남기고 **엣지를 전부 버린다**(방사형은 "
               "관계를 그리지 못한다). l-tree 는 12노드 + 엣지 11개를 남긴다. 같은 payload 를 "
               "받되 보존하는 정보가 다르다. F1 은 수용한다 — 배분을 렌더가 아니라 스키마가 "
               "막아야 한다는 지적이 맞다.",
          refs=["EV-SCENE-TREE", "EV-SLOTS"]),
        T(1, "expert", who=TD, stance="concern",
          text="Finding F3(minor): 소유권 경쟁이 코드 순서로 갈린다. _assign 에서 concept.nodes 가 "
               "l-tree.nodes 보다 먼저 graph payload 를 가져가므로, 두 템플릿을 같은 포맷 풀에 "
               "두면 방사형이 이긴다. 이번 실증은 concept 을 대체해서 드러나지 않았을 뿐이다.",
          refs=["EV-OWNER-ORDER", "EV-FIT-AFTER"],
          arts=[("finding", "F3(minor) concept 과의 payload 소유권이 스키마가 아니라 "
                            "_assign 코드 순서로 결정된다")]),
        T(1, "expert", who=QA, stance="concern",
          text="Finding F2(minor): note 는 렌더가 level 1 에서만 그리는데 스키마는 모든 레벨에 "
               "허용한다. 리프에 note 를 단 저작 데이터는 검증을 통과하고도 화면에서 조용히 "
               "사라진다 — 무언의 손실이다.",
          refs=["EV-SCHEMA-TREE"],
          arts=[("finding", "F2(minor) note 가 level 1 에서만 렌더되는데 스키마는 전 레벨 허용 — "
                            "리프 note 는 무언의 손실")]),
        T(1, "expert", who=MO, stance="support", text="추가 없음.", refs=["EV-STILLS"]),
        T(1, "expert", who=LG, stance="accept",
          text="F2·F3 모두 수용한다. F2 는 조건부 allOf 로 level 2 에서 note 를 금지하면 되고"
               "(스키마가 이미 레벨별 label 상한에 같은 기법을 쓴다), F3 은 포맷 풀 규약 문제라 "
               "내 소관 밖이지만 카탈로그에 경계를 적겠다.",
          refs=["EV-SCHEMA-TREE", "EV-CATALOG"]),
        T(2, "expert", who=TD, stance="accept",
          text="F1 은 스키마 표현이 까다롭다 — JSON Schema 로 '가지당'을 세려면 edges 를 봐야 "
               "한다. 현실적 대안은 렌더가 가지당 4개를 넘는 입력에서 초과분을 omitted 로 "
               "계상하는 것이다. 그러면 검증 대신 표기로 정직성을 지킨다.",
          refs=["EV-SCHEMA-TREE"]),
        T(2, "expert", who=QA, stance="accept",
          text="TD 안을 수용한다. 다만 회귀 테스트로 '한 가지 8리프' 케이스를 고정할 것 — "
               "지금은 조립기 경로만 검증돼 있다.",
          refs=["EV-TESTS-MINE"]),
        T(2, "expert", who=MO, stance="accept", text="스케줄 영향 없다.", refs=["EV-STILLS"]),
        T(2, "expert", who=LG, stance="accept",
          text="세 건 모두 수용. 반박 없다.", refs=["EV-SCHEMA-TREE"]),
        T(3, "moderator",
          "판정 — **Conditional-Go**. 재발명 아니다 — 같은 graph payload 를 받지만 concept 은 "
          "엣지를 버리고 8노드를 평면에 놓고, l-tree 는 12노드와 엣지 11개로 위계를 그린다"
          "(실증 수치). 걸린 것은 가지당 배분이 렌더·조립기에만 있고 계약에 없다는 점이다. "
          "status draft 유지.",
          arts=[("decision", "tpl.l-tree — Conditional-Go (F1 해소 시 draft→pilot). "
                             "concept 대비 정보 보존 우위 실측: 엣지 0 → 11"),
                ("action_item", "F1: 가지당 리프 초과분을 렌더가 omitted 로 계상 + "
                                "'한 가지 8리프' 회귀 테스트 (vis-layout-grid · qa-consistency)"),
                ("action_item", "F2: level 2 에서 note 금지를 조건부 allOf 로 (vis-layout-grid)"),
                ("open_issue", "F3: concept 과의 graph payload 소유권 규약 — 포맷 풀 우선순위로 "
                               "올릴지 조립기 규칙으로 둘지 미결")]),
    ]


def s_quote(px: str) -> list[MeetingTurn]:
    return [
        T(0, "moderator",
          "모듈 후보 tpl.l-quote 를 대독한다. 용도는 챕터 전환·결론 각인 한 문장이며, 글자 크기가 "
          "문장 길이에 따라 80/70/60px 로 자동 하향한다. 이 후보는 **구조 payload 대응이 없다** — "
          "문장 선택은 데이터가 아니라 편집 판단이라는 것이 제안자의 주장이다. 심사 범위는 "
          "① 저밀도가 이 라운드의 목적과 충돌하지 않는가 ② 문장 출처의 정직성이다.",
          refs=["EV-SCHEMA-QUOTE", "EV-SCENE-QUOTE", "EV-STILLS"],
          arts=[("module_candidate", "tpl.l-quote v1.0.0 draft — 핵심 문장 강조 (nat 8)")]),
        T(1, "expert", who=TD, stance="support",
          text="엔진 축 통과. 자동 하향은 문자열 길이의 순수 함수라 프레임마다 흔들리지 않고, "
               "texture 'marks' 는 텍스트가 아닌 CSS 도형이라 대비·폰트 게이트 대상 밖이라는 "
               "제안자 설명도 코드와 일치한다. 게이트 7종 error 0.",
          refs=["EV-QA", "EV-SCHEMA-QUOTE"]),
        T(1, "expert", who=QA, stance="concern",
          text="Finding F1(minor): 문장을 **누가 고르는가**가 계약에 없다. 지금 규칙은 조립기 "
               "안에만 있다 — ai_summary → purpose 절의 종결형 문장 중 최장 → 첫 주장 순. "
               "실증 결과는 원문 문장이 그대로 올라와 정직하지만, 다른 조립기가 다른 문장을 "
               "고르면 같은 보고서에서 다른 결론이 각인된다.",
          refs=["EV-SCENE-QUOTE", "EV-CATALOG"],
          arts=[("finding", "F1(minor) 각인 문장 선택 규칙이 조립기에만 있다 — "
                            "템플릿 계약에 '원문 문장만' 이 명시돼 있지 않다")]),
        T(1, "expert", who=MO, stance="support",
          text="낭독 38자 / 8.6초 = 4.43자/초로 예산 안이고, 룰 → 문장 → 화자 순서가 각인의 "
               "호흡과 맞는다. 8초는 짧지만 한 문장을 읽히기에는 충분하다.",
          refs=["EV-DENSITY", "EV-STILLS"]),
        T(1, "expert", who=LG, stance="support",
          text="이 씬의 75자는 저밀도지만 결함이 아니다 — 이번 라운드의 밀도 목표는 '한 화면이 "
               "감당할 최대치를 스키마 상한으로 잡는 것'이지 모든 씬을 채우라는 게 아니다. "
               "12씬 전체 2388자(기본 7씬 1351자 대비 +76.8%)가 목표 달성을 말한다.",
          refs=["EV-DENSITY", "EV-DENSITY-THIN"]),
        T(1, "expert", who=px, stance="propose",
          text="제안자 대리로 밝힌다. 이 씬의 계약은 '문장을 지어내지 않는다'이다. 조립기는 "
               "ai_summary 가 없으면 원문 종결형 문장만 고르고, 못 고르면 제목으로 떨어진다. "
               "F1 은 수용하되 스키마가 아니라 module.yaml 계약 문구로 못박는 게 맞다고 본다 — "
               "선택 규칙은 데이터 형식이 아니기 때문이다.",
          refs=["EV-SCENE-QUOTE", "EV-SCHEMA-QUOTE"]),
        T(1, "expert", who=TD, stance="support", text="추가 없음.", refs=["EV-QA"]),
        T(1, "expert", who=QA, stance="support",
          text="재발명 심사 결과 — 아니다. opening.title 은 pre/accent/post 3분할 제목이고 "
               "closing 은 stats + CTA 묶음이라 '문장 하나 70자'를 받는 슬롯이 카탈로그에 없었다. "
               "l-quote 를 뺐다면 결론 문장은 여전히 갈 곳이 없다.",
          refs=["EV-SLOTS", "EV-CATALOG"]),
        T(1, "expert", who=MO, stance="support", text="추가 없음.", refs=["EV-STILLS"]),
        T(1, "expert", who=LG, stance="support",
          text="폭 1400px · 3행 상한도 실측과 맞다. 추가 없음.", refs=["EV-SCHEMA-QUOTE"]),
        T(1, "expert", who=px, stance="accept",
          text="F1 수용. module.yaml 에 '문장은 원문에서만 온다' 계약을 적고 조립기 규칙을 "
               "카탈로그에 옮기겠다.", refs=["EV-CATALOG"]),
        T(2, "expert", who=TD, stance="accept", text="이견 없다.", refs=["EV-QA"]),
        T(2, "expert", who=QA, stance="accept",
          text="F1 은 minor 이고 화면이 거짓을 말하지 않으므로 등록 조건으로 걸지 않는다. "
               "액션아이템으로만 남긴다.", refs=["EV-SCENE-QUOTE"]),
        T(2, "expert", who=MO, stance="accept", text="이견 없다.", refs=["EV-STILLS"]),
        T(2, "expert", who=LG, stance="accept", text="이견 없다.", refs=["EV-DENSITY"]),
        T(2, "expert", who=px, stance="accept", text="반박 없다.", refs=["EV-SCHEMA-QUOTE"]),
        T(3, "moderator",
          "판정 — **Go**. 8종 중 유일하게 blocking·major Finding 이 없다. 재발명 없음"
          "(70자 문장 슬롯이 카탈로그에 없었다), 게이트 7종 통과, 실증에서 원문 문장이 그대로 "
          "각인됐다. minor 1건은 계약 문구 보완이라 등록을 막지 않는다. draft→pilot 승격 가능.",
          arts=[("decision", "tpl.l-quote — Go (draft→pilot 승격 가능). "
                             "blocking·major Finding 없음"),
                ("action_item", "F1: '각인 문장은 원문에서만 온다' 를 module.yaml 계약과 "
                                "카탈로그에 명시 (narr-copywriter)")]),
    ]


def s_kpi(px: str) -> list[MeetingTurn]:
    return [
        T(0, "moderator",
          "모듈 후보 tpl.l-kpi 를 대독한다. 용도는 closing.stats 3칸 상한이 못 담던 다지표 제시로, "
          "지표 4~6개를 2×2 또는 3×2 타일에 [라벨 + 큰 수치 + 단위 + 증감 배지 + 스파크바]로 "
          "담는다. 구조 매핑에서 7계열 progress_bar 를 받아 6타일 + omitted 1 로 실었다. "
          "심사 범위는 ① 수치 슬롯 3종과의 경계 ② 자동 경로에서의 밀도 ③ 큰 수치 표기 계약이다.",
          refs=["EV-SCHEMA-KPI", "EV-SCENE-KPI", "EV-FIT-AFTER"],
          arts=[("module_candidate", "tpl.l-kpi v1.0.0 draft — 다지표 계기판 (nat 11)")]),
        T(1, "expert", who=TD, stance="concern",
          text="엔진 축은 통과다(게이트 7종 error 0). 다만 Finding F3(minor): value 는 6자에 "
               "패턴 ^-?[0-9][0-9.,]*$ 라 지수·축약 표기가 금지되는데 축약 단위 필드도 없다. "
               "백만 단위 값은 조립기가 반올림·절단으로 떨어뜨려야 하고, 지금은 꼬리 구분자를 "
               "털어내는 방어 코드가 조립기에 있다. 수치 규모가 큰 보고서에서 터진다.",
          refs=["EV-QA", "EV-SCHEMA-KPI"],
          arts=[("finding", "F3(minor) value 6자 + 지수 금지 + 축약 단위 필드 부재 — "
                            "백만 단위 수치를 담을 방법이 스키마에 없다")]),
        T(1, "expert", who=QA, stance="rebut",
          text="Finding F1(major): '고밀도 계기판'이라는 존재 이유가 자동 경로에서 성립하지 "
               "않는다. delta 와 spark 는 **비교 시점**이 있어야 만들 수 있는데 구조 payload 에는 "
               "이전 값이 없다. 실증 6타일은 {label, value, unit} 뿐이고 씬 전체가 68자로 12씬 중 "
               "최소다 — opening(67자)과 같은 급이다. 타일 하단 절반이 비어 있다.",
          refs=["EV-SCENE-KPI", "EV-DENSITY-THIN", "EV-STILLS"],
          arts=[("finding", "F1(major) delta·spark 부재 시 타일 하단이 비어 68자 — "
                            "12씬 중 최소 밀도. 계기판의 존재 이유가 자동 경로에서 무너진다")]),
        T(1, "expert", who=MO, stance="support",
          text="타일 순차 점등은 읽는 순서(좌상→우하)와 같고 스파크바가 없어도 등장 리듬은 "
               "성립한다. 낭독 9자/11.8초는 이 씬이 '보는 씬'임을 말한다 — 모션 결함 없다.",
          refs=["EV-DENSITY", "EV-STILLS"]),
        T(1, "expert", who=LG, stance="concern",
          text="Finding F2(minor): label 14자는 실물 라벨에 좁다. 원문은 'Phase 0/1 — 작성자 "
               "owner check · 게시(Mount)' 38자이고 그대로 자르면 'Phase 0/1 —…' 이 돼 무엇의 "
               "수치인지 사라진다. 조립기가 '— 앞머리만' 규칙을 따로 만들어 'Phase 0/1' 로 "
               "복구했는데, 그 규칙이 템플릿이 아니라 조립기에 산다.",
          refs=["EV-SCENE-KPI", "EV-SLOTS"],
          arts=[("finding", "F2(minor) label 14자 대비 원문 38자 — 앞머리 절단 규칙이 "
                            "템플릿 계약이 아니라 조립기에 있다")]),
        T(1, "expert", who=px, stance="propose",
          text="제안자 대리로 설계 의도를 밝힌다. 핵심은 증감의 **방향과 평가를 분리**한 것이다 — "
               "delta.dir 은 글리프 ▲▼■ 만 정하고 색은 delta.tone 이 정한다. 그래서 "
               "'미착수 ▼ -2개'가 녹색이고 '지연 ▲ +1개'가 적색이다. F1 은 부인하지 않되, "
               "delta 를 required 로 올리면 시점 비교가 없는 보고서에서 조립이 막힌다는 점을 "
               "함께 봐야 한다.",
          refs=["EV-B-CLAIM", "EV-SCHEMA-KPI"]),
        T(1, "expert", who=TD, stance="question",
          text="F1 의 현실적 해법을 묻는다. delta 없이 타일이 차게 하려면 (a) 타일 높이를 delta "
               "유무로 바꾸거나 (b) 빈 자리에 값의 맥락(축 최댓값 대비 비율)을 넣어야 한다. "
               "(b)는 계열 안에서 파생되는가?",
          refs=["EV-SCENE-KPI"]),
        T(1, "expert", who=QA, stance="concern",
          text="(b)를 경계한다. progress_bar 는 max 를 가지므로 '100 중 70' 파생은 원 데이터 "
               "안이지만, max 가 없는 계열에는 근거가 없다. 조건부 파생은 '있을 때만 채우고 "
               "없으면 비운다'가 되어 F1 을 절반만 푼다.",
          refs=["EV-SCENE-KPI", "EV-SLOTS"]),
        T(1, "expert", who=MO, stance="support",
          text="(a) 안이 모션에는 낫다 — 타일 높이가 줄면 6타일이 위로 모여 여백이 아래로 몰리므로 "
               "'빈 계기판'처럼 보이지 않는다.", refs=["EV-STILLS"]),
        T(1, "expert", who=LG, stance="support",
          text="(a)를 지지한다. 3열 타일 안폭 461px 는 그대로 두고 높이만 두 단계면 격자가 "
               "흔들리지 않는다.", refs=["EV-SLOTS"]),
        T(1, "expert", who=px, stance="accept",
          text="F1 은 (a)로 수용한다 — delta·spark 가 없으면 타일 높이를 줄이고 그리드를 위로 "
               "모은다. F2 는 label 의 '이름 — 설명' 관례를 description 으로 못박고 앞머리 규칙을 "
               "카탈로그로 옮긴다. F3 은 unit 을 4자로 넓혀 k/M 접두를 허용하는 안을 낸다.",
          refs=["EV-SCENE-KPI", "EV-SCHEMA-KPI"]),
        T(2, "expert", who=TD, stance="accept",
          text="세 안 모두 엔진 계약을 건드리지 않는다. 수정 후 게이트 재실행 조건.", refs=["EV-QA"]),
        T(2, "expert", who=QA, stance="accept",
          text="F1 을 blocking 으로 올리지는 않는다 — 빈 자리는 왜곡이 아니라 여백이다. major "
               "유지하고 등록 조건으로 건다. 재발명 심사 결과도 남긴다: closing.stats(3칸·v14/d24)"
               "·dataviz.bars(5개·축 있음)와 축이 다르다 — l-kpi 는 축 없는 4~6 타일이다. "
               "재발명 아님.",
          refs=["EV-SLOTS", "EV-SCENE-KPI"],
          arts=[("open_issue", "수치 슬롯 3종(closing.stats·dataviz.bars·l-kpi.metrics)의 "
                               "선택 기준을 '축의 유무·개수'로 카탈로그에 명문화")]),
        T(2, "expert", who=MO, stance="accept", text="이견 없다.", refs=["EV-STILLS"]),
        T(2, "expert", who=LG, stance="accept", text="F2 는 F1 과 별개로 닫힌다. 둘 다 수용.",
          refs=["EV-SLOTS"]),
        T(2, "expert", who=px, stance="accept", text="반박 없다.", refs=["EV-B-CLAIM"]),
        T(3, "moderator",
          "판정 — **Conditional-Go**. 재발명 아니다(수치 슬롯 3종과 축·개수가 다르고, 7계열이 "
          "closing.stats 3칸에서 6타일로 올라왔다). 걸린 것은 자동 경로 밀도다 — delta·spark 를 "
          "구조 payload 가 만들 수 없으므로 타일이 그 부재를 견디게 해야 한다. status draft 유지.",
          arts=[("decision", "tpl.l-kpi — Conditional-Go (F1 해소 시 draft→pilot). "
                             "다지표 도달 개선 확인: closing.stats 3 → l-kpi.metrics 6 + omitted 1"),
                ("action_item", "F1: delta·spark 부재 시 타일 높이 축소 레이아웃 (vis-dataviz)"),
                ("action_item", "F2: label '이름 — 설명' 관례 명시 + 앞머리 규칙 카탈로그 이관 "
                                "(vis-dataviz)"),
                ("action_item", "F3: unit 4자 확장으로 축약 접두(k/M) 허용 (vis-dataviz)")]),
    ]


def s_quad(px: str) -> list[MeetingTurn]:
    return [
        T(0, "moderator",
          "모듈 후보 tpl.l-quad 를 대독한다. 용도는 포지셔닝·우선순위 논증으로, 항목 4~10개를 "
          "0~1 정규화 좌표로 판에 놓고 번호 점 ↔ 범례 이름으로 라벨 충돌을 없앤 설계다. "
          "심사 범위는 ① 좌표가 원 데이터의 위치를 보존하는가 ② 판 위 텍스트가 서로를 가리지 "
          "않는가다. 이 후보만 실증 입력이 합성 부록이었음을 밝힌다 — report_sample 에 좌표 "
          "위젯이 없다.",
          refs=["EV-SCHEMA-QUAD", "EV-SCENE-QUAD", "EV-STILLS"],
          arts=[("module_candidate", "tpl.l-quad v1.0.0 draft — 4분면 포지셔닝 (nat 13)")]),
        T(1, "expert", who=TD, stance="rebut",
          text="Finding F2(blocking): 좌표가 원 위젯의 좌표가 아니다. widgets._x_quadrant 는 "
               "props.x_axis_title·y_axis_title·x_range 를 payload 에 싣지 않는다(y_range 만 "
               "axis 로 간다). 그래서 가로 정규화 기준이 데이터 범위(실증 2~9)가 되고 선언 "
               "범위(0~10) 대비 최대 20%p 이동한다 — x=5 인 항목은 선언 기준 경계 0.5 인데 "
               "데이터 기준 0.43 이라 **다른 사분면에 앉는다**. 템플릿 단독으로 못 고친다.",
          refs=["EV-QUAD-UPSTREAM", "EV-SCENE-QUAD"],
          arts=[("finding", "F2(blocking) 가로 범위가 payload 에 없어 정규화 기준이 데이터 "
                            "범위로 떨어진다 — 사분면 귀속이 뒤바뀔 수 있다 (widgets.py 계약)")]),
        T(1, "expert", who=QA, stance="rebut",
          text="Finding F1(blocking): 사분면 이름과 극단 좌표 점이 겹친다. 렌더 상수로 기하를 "
               "계산했다 — tl 라벨 상자 (124,66)~(384,98), 항목 점(x=0,y=1) 상자 "
               "(114,56)~(158,100) → 34×32px 겹침. 겹치는 좌표 영역은 x<0.335 ∧ y>0.904 로 "
               "판 좌상의 1/3×1/10 이다. 스틸에서도 1번 점이 '좌상'을 가린다. 게이트 5는 "
               "스크롤 넘침만 보므로 이 겹침을 잡지 못한다.",
          refs=["EV-QUAD-OVERLAP", "EV-STILLS", "EV-QA"],
          arts=[("finding", "F1(blocking) 사분면 이름과 극단 좌표 점이 34×32px 겹친다 "
                            "(겹침 영역 x<0.335 ∧ y>0.904) — 게이트 5 무능 구간")]),
        T(1, "expert", who=MO, stance="support",
          text="등장 순서는 옳다 — 판 → 범례 → 축 → 사분면 이름 → 항목 점(0.35s 간격) → 각주. "
               "번호 점과 범례 행이 0.12s 차로 짝지어 들어와 시선이 이어진다. 다만 F1 때문에 "
               "사분면 이름이 뜬 자리에 점이 내려앉는 순서라, 모션이 겹침을 **만드는** 순서다.",
          refs=["EV-STILLS", "EV-QUAD-OVERLAP"]),
        T(1, "expert", who=LG, stance="concern",
          text="격자 자체는 좋다 — 좌표판 1000px + 범례 600px 분리로 판 위 텍스트를 번호로만 "
               "제한한 것이 이 템플릿 최선의 결정이다. 실증 7항목에서 범례·판 어디에도 텍스트 "
               "겹침이 없다. F1 은 그 원칙의 유일한 예외가 사분면 이름이라는 뜻이다 — 이름도 "
               "판 밖 스트립으로 빼면 원칙이 완성된다.",
          refs=["EV-STILLS", "EV-SCENE-QUAD"]),
        T(1, "expert", who=px, stance="concern",
          text="제안자 대리로서 두 건 모두 인정한다. 점을 반지름+4px 안쪽으로 물린 것은 판 테두리 "
               "이탈을 막으려던 것이지 사분면 이름과의 충돌까지 본 게 아니었다. F2 는 더 무겁다 — "
               "축 이름조차 payload 에 없어 조립기가 캡션 '난이도 × 진척'을 파싱해 복구했고 "
               "사분면 이름은 '좌상/우상/좌하/우하' 위치어로 떨어졌다. 화면이 무엇의 사분면인지 "
               "말하지 못한다.",
          refs=["EV-SCENE-QUAD", "EV-QUAD-UPSTREAM"]),
        T(1, "expert", who=TD, stance="concern",
          text="F2 의 수정 범위를 분명히 한다. widgets.py 는 이번 라운드 소유 밖이고, payload "
               "계약(series 에 axis.x 추가)을 바꾸면 d-multi·dataviz 도 영향을 받는다. 템플릿 "
               "단독으로 닫을 수 없는 Finding 이다.",
          refs=["EV-QUAD-UPSTREAM", "EV-FIT-CHAIN"]),
        T(1, "expert", who=QA, stance="concern",
          text="정직성 축에서 하나 더. 조립기는 note 에 '축 이름은 원문 위젯 속성 미전달 · 범위는 "
               "데이터 기준'을 찍어 사실을 밝히지만, 그 문구는 좌표가 **틀릴 수 있다**는 말을 "
               "하지 않는다. 밝히는 것과 막는 것은 다르다.",
          refs=["EV-SCENE-QUAD", "EV-QUAD-UPSTREAM"]),
        T(1, "expert", who=MO, stance="support",
          text="추가 없음. 밀도 119자는 이 씬의 성격상 문제가 아니다(판이 정보다).",
          refs=["EV-DENSITY-THIN"]),
        T(1, "expert", who=LG, stance="support",
          text="추가 없음. 사분면 이름을 판 밖으로 빼는 안이면 격자 예산은 충분하다.",
          refs=["EV-SCENE-QUAD"]),
        T(1, "expert", who=px, stance="accept",
          text="두 blocking 모두 수용한다. F1 은 사분면 이름을 판 밖 스트립으로 옮기거나 점 배치 "
               "inset 을 라벨 상자만큼 더 물려 닫을 수 있다. F2 는 upstream 계약 변경이 필요해 "
               "이 템플릿 혼자 닫지 못한다.",
          refs=["EV-QUAD-OVERLAP", "EV-QUAD-UPSTREAM"]),
        T(2, "expert", who=TD, stance="accept",
          text="F2 가 upstream 소관이라는 데 동의한다. 등록을 미루는 근거로 충분하다.",
          refs=["EV-QUAD-UPSTREAM"]),
        T(2, "expert", who=QA, stance="rebut",
          text="'note 로 밝혔으니 Conditional-Go 로 가자'는 주장이 있다면 반박한다. 이 씬은 "
               "**위치가 곧 주장**인 템플릿이다. 위치가 선언 범위와 다른 기준으로 계산되고 그 "
               "사분면의 이름마저 가려지면 화면이 말하는 주장이 원문과 달라진다. 다른 7종의 "
               "결함은 '덜 담긴다'였지만 이건 '다르게 말한다'다. No-Go 를 낸다.",
          refs=["EV-QUAD-OVERLAP", "EV-QUAD-UPSTREAM", "EV-SCENE-QUAD"]),
        T(2, "expert", who=MO, stance="accept",
          text="동의한다. 모션이 겹침을 만드는 순서라는 점도 같은 결론을 가리킨다.",
          refs=["EV-QUAD-OVERLAP"]),
        T(2, "expert", who=LG, stance="accept",
          text="동의한다. 다만 판/범례 분리 설계 자체는 보존할 가치가 있다 — 재심 때 이 구조는 "
               "다시 논하지 말자.", refs=["EV-STILLS"]),
        T(2, "expert", who=px, stance="accept",
          text="No-Go 를 받아들인다. F1 은 내 소관에서 즉시 고치고, F2 해소는 widgets.py "
               "소유자에게 넘긴 뒤 재심을 청구하겠다.", refs=["EV-QUAD-UPSTREAM"]),
        T(3, "moderator",
          "판정 — **No-Go**. 재발명은 없고(좌표 배치 슬롯이 카탈로그에 없었다) 판/범례 분리 "
          "설계도 유효하다. 그러나 blocking 두 건이 남는다 — 사분면 이름이 극단 좌표 점에 "
          "가려지고(F1), 가로 정규화 기준이 원 위젯 선언과 달라 항목이 다른 사분면에 앉을 수 "
          "있다(F2). 후자는 이 템플릿 밖(widgets.py payload 계약)이라 오늘 닫을 수 없다. "
          "레지스트리 등록 보류, status draft 유지, 두 건 해소 후 재심.",
          arts=[("decision", "tpl.l-quad — No-Go (등록 보류). blocking 2건 — 사분면 이름 겹침, "
                             "정규화 기준 불일치. 판/범례 분리 설계는 재심에서 재론하지 않는다"),
                ("action_item", "F1: 사분면 이름을 판 밖 스트립으로 이동하거나 점 inset 을 "
                                "라벨 상자만큼 확대 (vis-dataviz)"),
                ("action_item", "F2: series payload 에 axis.x{min,max}·축 이름을 싣도록 "
                                "widgets._x_quadrant 계약 확장 요청 (wdpipeline 소유자)"),
                ("action_item", "F1 회귀: 극단 좌표(x≤0.04·y≥0.96) 항목과 사분면 이름 겹침 0 을 "
                                "렌더 테스트로 고정 (qa-consistency)"),
                ("open_issue", "게이트 5는 스크롤 넘침만 본다 — 요소 간 겹침 검사는 어느 "
                               "게이트도 하지 않는다")]),
    ]


def s_ba(px: str) -> list[MeetingTurn]:
    return [
        T(0, "moderator",
          "모듈 후보 tpl.l-ba 를 대독한다. 용도는 전체 상태 대비 — 무대를 x=960 에서 반으로 갈라 "
          "AS-IS / TO-BE 를 각각 [칩 + 제목 + 항목 3~5 + 요약 수치]로 세우고, 좌가 끝난 뒤 우가 "
          "등장해 등장 순서가 곧 전환이 되게 했다. 제안자는 tpl.compare 와 겹치지 않게 rows 를 "
          "두지 않았다고 밝혔다. 심사 범위는 ① compare 와의 재발명 ② 요약 수치의 출처다.",
          refs=["EV-SCHEMA-BA", "EV-SCENE-BA", "EV-B-CLAIM"],
          arts=[("module_candidate", "tpl.l-ba v1.0.0 draft — Before/After 반반 (nat 14)")]),
        T(1, "expert", who=TD, stance="support",
          text="엔진 축 통과다. $defs/side 를 좌우가 공유해 두 패널의 계약이 하나이고 게이트 7종 "
               "error 0 이다. 참고로 이번 라운드에서 조립기의 스키마 조회에 로컬 $ref 해석을 "
               "넣었다 — 그게 없으면 side 의 상한을 못 읽고 코드 기본값으로 떨어졌다.",
          refs=["EV-QA", "EV-SCHEMA-BA"]),
        T(1, "expert", who=QA, stance="rebut",
          text="Finding F1(blocking): summary 가 required 인데 그 수치를 만들 데이터가 없다. "
               "comparison payload 는 관점×2안 표라 수치 행이 없을 수 있고, 실증이 정확히 그 "
               "경우였다 — 좌우 모두 {value:'5', desc:'개 관점'} 이 나왔다. 92px display 두 개가 "
               "같은 값을 띄우는 화면은 '대비'라는 이 씬의 주장을 스스로 무너뜨린다. 조립기는 "
               "지어내지 않았지만, 지어내지 않으면 무의미한 수치가 나오는 구조다.",
          refs=["EV-SCENE-BA", "EV-SCHEMA-BA", "EV-STILLS"],
          arts=[("finding", "F1(blocking) summary required 인데 comparison payload 에 수치가 "
                            "없다 — 좌우가 같은 '5 개 관점'을 92px 로 띄운다")]),
        T(1, "expert", who=MO, stance="support",
          text="전환 서사는 성립한다 — 좌 패널이 요약 수치까지 끝난 뒤 화살표, 그다음 우 패널이 "
               "같은 순서로 들어온다. 스틸에서 중앙 화살표가 두 상태의 시간축 역할을 한다. "
               "모션 결함 없다.",
          refs=["EV-STILLS", "EV-B-CLAIM"]),
        T(1, "expert", who=LG, stance="concern",
          text="Finding F2(major): compare 와 **같은 payload**를 받는다. 제안자는 rows 를 두지 "
               "않아 배타라 했지만 배타적인 건 스키마 모양이지 입력이 아니다 — 조립기 판정에서 "
               "comparison 3열 표는 compare → differentiator → l-ba 순 if/elif 로 갈린다. "
               "포맷 풀 순서를 바꾸면 같은 보고서가 다른 씬을 얻는다.",
          refs=["EV-FIT-CHAIN", "EV-SCENE-BA"],
          arts=[("finding", "F2(major) tpl.compare 와 동일 payload 경쟁 — 스키마가 아니라 "
                            "조립기 if/elif 순서가 정본이다")]),
        T(1, "expert", who=px, stance="propose",
          text="제안자 대리로 밝힌다. compare 는 **행 짝 비교**(관점마다 A/B 한 줄씩)이고 l-ba 는 "
               "**상태 서술**(각 패널이 하나의 완결된 상태)이다. 실측으로도 다르다 — compare.rows "
               "는 4행 × (aspect 4 + a 44 + b 44), l-ba 는 2패널 × (제목 30 + 항목 5×22 + 수치). "
               "같은 표에서 서로 다른 문장을 만든다. F2 는 경계 문서화로 닫자는 입장이다.",
          refs=["EV-SLOTS", "EV-SCENE-BA"]),
        T(1, "expert", who=TD, stance="question",
          text="F1 의 대안을 묻는다. summary 를 optional 로 내리면 스키마 하나로 두 종류의 화면"
               "(수치 있는 대비/없는 대비)이 생긴다. 그게 나은가, '수치 없음' 표기 규약이 나은가?",
          refs=["EV-SCHEMA-BA"]),
        T(1, "expert", who=QA, stance="concern",
          text="optional 쪽을 지지한다. 다만 조건이 있다 — 좌우 중 한쪽만 수치가 있으면 대비가 "
               "성립하지 않으므로 '둘 다 있거나 둘 다 없거나'를 스키마가 강제해야 한다. "
               "Draft 2020-12 의 dependentRequired 로 표현 가능한 제약이다.",
          refs=["EV-SCHEMA-BA"]),
        T(1, "expert", who=MO, stance="support",
          text="수치가 빠지면 패널 하단 여백이 생기는데 항목 5개까지 쓰는 배치로 흡수하면 된다. "
               "스케줄은 그대로다.", refs=["EV-STILLS"]),
        T(1, "expert", who=LG, stance="support",
          text="F2 를 카탈로그 경계로 닫는 데 동의한다 — '행 짝 비교는 compare, 상태 서술은 "
               "l-ba'. 다만 포맷 풀 우선순위 규약이 함께 있어야 실효가 있다.",
          refs=["EV-CATALOG", "EV-FIT-CHAIN"]),
        T(1, "expert", who=px, stance="accept",
          text="F1 은 summary optional + 양쪽 동시 요구로, F2 는 카탈로그 경계 + 풀 우선순위 "
               "규약으로 수용한다. 자동 조립이 관점 수를 수치로 올리는 현재 동작은 그때 제거한다.",
          refs=["EV-SCHEMA-BA", "EV-CATALOG"]),
        T(2, "expert", who=TD, stance="accept",
          text="dependentRequired 는 2020-12 에서 쓸 수 있다. 수정 후 게이트 재실행 조건.",
          refs=["EV-QA"]),
        T(2, "expert", who=QA, stance="accept",
          text="F1 을 blocking 으로 유지하되 등록 자체를 막지는 않는다 — 화면이 거짓을 말하는 게 "
               "아니라 무의미한 수치를 크게 띄우는 것이라 조건부 등록으로 충분하다.",
          refs=["EV-SCENE-BA"]),
        T(2, "expert", who=MO, stance="accept", text="이견 없다.", refs=["EV-STILLS"]),
        T(2, "expert", who=LG, stance="accept", text="두 건 수용.", refs=["EV-FIT-CHAIN"]),
        T(2, "expert", who=px, stance="accept", text="반박 없다.", refs=["EV-SCHEMA-BA"]),
        T(3, "moderator",
          "판정 — **Conditional-Go**. 재발명은 아니다 — compare 는 행 짝 비교, l-ba 는 상태 "
          "서술이고 실측 용량도 다르다. 다만 같은 payload 를 두고 경쟁하므로 경계가 문서와 풀 "
          "규약에 있어야 한다. blocking F1(요약 수치의 출처 부재)을 등록 조건으로 건다. "
          "status draft 유지.",
          arts=[("decision", "tpl.l-ba — Conditional-Go (blocking F1 해소 시 draft→pilot)"),
                ("action_item", "F1: summary 를 optional 로 내리고 좌우 동시 요구"
                                "(dependentRequired) — 자동 조립의 '관점 수' 대체값 제거 "
                                "(narr-story-architect)"),
                ("action_item", "F2: 'compare = 행 짝 / l-ba = 상태 서술' 경계를 카탈로그에 "
                                "명시 + 포맷 풀 우선순위 규약 (narr-story-architect · "
                                "vis-layout-grid)"),
                ("open_issue", "comparison payload 하나를 5개 씬이 받을 수 있다 — 우선순위의 "
                               "정본을 조립기에서 포맷 스펙으로 옮길지 미결")]),
    ]


def s_mix(px: str) -> list[MeetingTurn]:
    return [
        T(0, "moderator",
          "모듈 후보 tpl.l-mix 를 대독한다. 용도는 표와 차트를 한 화면에 세우는 실무 패턴으로, "
          "상단 40%에 요약 수치 2~3개 **또는** 한 줄 결론(oneOf 배타), 하단 60%에 좌 간이표"
          "(≤4열×≤5행)와 우 막대 3~4개를 놓는다. structured table 과 series 를 동시에 받는 "
          "유일한 템플릿이다. 심사 범위는 ① d-matrix 와의 재발명 ② 상단 띠의 밀도 ③ 표와 막대의 "
          "수치 일치다.",
          refs=["EV-SCHEMA-MIX", "EV-SCENE-MIX", "EV-FIT-AFTER"],
          arts=[("module_candidate", "tpl.l-mix v1.0.0 draft — 표 + 차트 혼합 (nat 15)")]),
        T(1, "expert", who=TD, stance="support",
          text="엔진 축 통과. 게이트 7종 error 0 이고 교차 배열 규칙(라벨이 겹치는 행과 막대는 "
               "같은 수치)도 회귀 테스트로 고정돼 있다. 실증에서는 표(RACI)와 막대(진척)가 서로 "
               "다른 payload 라 라벨 충돌 자체가 없었다.",
          refs=["EV-QA", "EV-TESTS-MINE", "EV-SCENE-MIX"]),
        T(1, "expert", who=QA, stance="concern",
          text="Finding F1(major): 상단 stats 는 자동 경로에서 **집계를 만들어야** 채워진다. "
               "실증 값은 [7개 전체 항목 / 100% Phase 0/1 / 60% 평균] 인데 '평균'은 원 계열의 "
               "단순평균이다. 산술 집계라 거짓은 아니지만 라벨 14자에 산식이 들어가지 않아 "
               "화면은 그냥 '60%'라고 말한다. 원문에 없던 수치를 92px 로 띄우는 구조다.",
          refs=["EV-SCENE-MIX", "EV-SCHEMA-MIX"],
          arts=[("finding", "F1(major) stats 는 자동 경로에서 파생 집계로만 채워진다 — "
                            "'평균'의 산식이 화면에 없다(label 14자)")]),
        T(1, "expert", who=MO, stance="support",
          text="상단 띠 → 표 → 막대 순서가 '결론 먼저, 근거 나중'이라 발표 화법과 맞는다. "
               "낭독 32자/16.1초로 예산 안이고, 같은 수치를 숫자와 길이로 두 번 읽히는 구성도 "
               "리듬이 겹치지 않는다.",
          refs=["EV-DENSITY", "EV-STILLS"]),
        T(1, "expert", who=LG, stance="rebut",
          text="Finding F2(major): 셀 6자 제약을 스키마가 표현하지 못한다. cells.v 가 6자라 문장 "
               "표를 통째로 못 받는데, 그 판정은 스키마가 아니라 조립기 _mix_table 필터가 한다 — "
               "'셀이 전부 6자 이하인 열만' 데이터 열로 고른다. 실증에서 RACI 6열 중 3열만 실렸고 "
               "2열은 생략 표기로 남았다. 저작 시나리오는 이 필터 없이 검증만 통과하면 되므로 "
               "긴 셀을 넣고 전부 잘린다.",
          refs=["EV-SCHEMA-MIX", "EV-SCENE-MIX"],
          arts=[("finding", "F2(major) '짧은 값 열만'이라는 실질 제약이 스키마 밖(조립기)에 "
                            "있다 — 저작 경로는 긴 셀을 넣고 전부 잘린다")]),
        T(1, "expert", who=px, stance="propose",
          text="제안자 대리로 밝힌다. 이 템플릿은 수치·코드값 표 전용이다 — 6자 상한이 그 "
               "선언이고 문장 표는 d-matrix(라벨 24자)나 l-split 간이표(셀 14자)가 받는다. "
               "F2 는 그 의도를 스키마가 말하지 못한다는 지적이라 수용한다. F1 은 oneOf 의 lead "
               "쪽을 쓰면 피할 수 있지만 그러면 상단 226px 를 한 줄이 차지해 밀도가 무너진다.",
          refs=["EV-SCHEMA-MIX", "EV-SLOTS"]),
        T(1, "expert", who=TD, stance="concern",
          text="Finding F3(minor): 제안자가 말한 lead 경로의 밀도 붕괴를 실측으로 확인했다. "
               "초판 조립이 lead 를 썼을 때 상단 흰 카드가 한 줄만 담아 비어 보였고, stats 로 "
               "바꾼 뒤 씬 밀도가 회복됐다. oneOf 두 갈래의 화면 품질이 대칭이 아니다.",
          refs=["EV-SCENE-MIX", "EV-STILLS"],
          arts=[("finding", "F3(minor) oneOf 의 lead 갈래는 상단 226px 를 한 줄이 차지 — "
                            "두 갈래의 밀도가 비대칭")]),
        T(1, "expert", who=QA, stance="support",
          text="재발명 심사 결과 — 아니다. d-matrix 는 8행×8열 격자 전용(label 24자)이고 l-mix 는 "
               "5행×3열 + 막대 동시다. 실증에서도 RACI 가 d-matrix 로 갈 때와 l-mix 로 갈 때 "
               "화면이 다르다 — 후자는 진척 막대가 같은 화면에 선다. 축이 '격자냐 격자+수치냐'로 "
               "갈린다.",
          refs=["EV-SLOTS", "EV-SCENE-MIX"]),
        T(1, "expert", who=MO, stance="support", text="추가 없음.", refs=["EV-STILLS"]),
        T(1, "expert", who=LG, stance="support",
          text="밀도 166자는 중간이지만 표 15칸 + 막대 4개가 들어간 결과라 글자 수로만 재면 "
               "과소평가다. 격자 축으로는 결함 없다.", refs=["EV-DENSITY"]),
        T(1, "expert", who=px, stance="accept",
          text="F1 은 stats.label 을 18자로 넓혀 '평균(단순)' 같은 산식 표기를 허용하고, F2 는 "
               "cells.v 6자의 의도를 description 에 '수치·코드값 전용'으로 못박고 카탈로그 경계에 "
               "적는다. F3 은 lead 갈래를 '표·막대만으로 충분할 때'로 한정하겠다.",
          refs=["EV-SCHEMA-MIX", "EV-CATALOG"]),
        T(2, "expert", who=TD, stance="accept",
          text="세 안 모두 렌더 변경이 작다. 수정 후 게이트 재실행 조건.", refs=["EV-QA"]),
        T(2, "expert", who=QA, stance="accept",
          text="F1 을 blocking 으로 올리지 않는다 — 파생 집계 자체는 정당하고 문제는 표기다. "
               "label 확장으로 닫히면 충분하다.", refs=["EV-SCENE-MIX"]),
        T(2, "expert", who=MO, stance="accept", text="이견 없다.", refs=["EV-STILLS"]),
        T(2, "expert", who=LG, stance="accept",
          text="F2 를 major 로 유지한다 — 저작 경로가 조용히 잘리는 건 '무언의 절단 금지'에 "
               "걸린다.", refs=["EV-SCHEMA-MIX"]),
        T(2, "expert", who=px, stance="accept", text="반박 없다. 세 건 수용.",
          refs=["EV-SCHEMA-MIX"]),
        T(3, "moderator",
          "판정 — **Conditional-Go**. 재발명 아니다(표+수치 동시 슬롯이 카탈로그에 없었고, 이 씬 "
          "덕에 6열×8행 RACI 가 진척 막대와 한 화면에 섰다). 걸린 것은 실질 제약이 스키마 밖에 "
          "있다는 점(F2)과 파생 집계의 표기(F1)다. status draft 유지.",
          arts=[("decision", "tpl.l-mix — Conditional-Go (F1·F2 해소 시 draft→pilot). "
                             "table+series 동시 수용 확인: 표 5행 + 막대 4개 + 생략 표기"),
                ("action_item", "F1: stats.label 18자 확장 — 파생 집계의 산식을 표기 가능하게 "
                                "(vis-dataviz)"),
                ("action_item", "F2: cells.v 6자의 '수치·코드값 전용' 의도를 description 과 "
                                "카탈로그에 명시 (vis-dataviz)"),
                ("action_item", "F3: lead 갈래의 사용 조건을 description 에 한정 (vis-dataviz)")]),
    ]


SCRIPTS = {
    "tpl.l-split": s_split, "tpl.l-list": s_list, "tpl.l-tree": s_tree,
    "tpl.l-quote": s_quote, "tpl.l-kpi": s_kpi, "tpl.l-quad": s_quad,
    "tpl.l-ba": s_ba, "tpl.l-mix": s_mix,
}


def run(mid: str, cfg: dict, engine: MeetingEngine, turns: list[MeetingTurn]) -> dict:
    """회의 1건을 실제로 진행한다 — 라운드·차례·인용은 엔진이 검증한다."""
    panel = list(PANEL) + ([cfg["proxy"]] if cfg["proxy"] else [])
    meta = engine.create(MeetingType.module_review, cfg["topic"], panel)
    for turn in turns:
        engine.submit_turn(meta, turn, known_refs=set(EVIDENCE))
    _, saved = engine.store.load(meta.id)
    minutes = engine.close(meta, saved)
    verdict = next(
        (a.content for t in saved for a in t.artifacts if a.type.value == "decision"), "")
    actions = [a.content for t in saved for a in t.artifacts if a.type.value == "action_item"]
    issues = [a.content for t in saved for a in t.artifacts if a.type.value == "open_issue"]
    findings = [a.content for t in saved for a in t.artifacts if a.type.value == "finding"]
    print(f"[{mid}] 턴 {len(saved)} · finding {len(findings)} · "
          f"판정 {verdict.split('—')[-1].strip()[:40]}")
    return {
        "module": mid, "meeting_id": meta.id, "topic": cfg["topic"], "panel": panel,
        "turns": len(saved), "findings": findings, "decision": verdict,
        "action_items": actions, "open_issues": issues, "minutes": str(minutes),
    }


def main() -> int:
    engine = MeetingEngine(MeetingStore(REPO / "data" / "meetings"), registry=load_registry())
    out = []
    for mid, cfg in REVIEWS.items():
        out.append(run(mid, cfg, engine, SCRIPTS[mid](cfg["proxy"])))
    path = HERE / "verdicts_20260729.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    tally: dict[str, int] = {}
    for r in out:
        key = ("No-Go" if "No-Go" in r["decision"]
               else "Conditional-Go" if "Conditional-Go" in r["decision"] else "Go")
        tally[key] = tally.get(key, 0) + 1
    print(f"[판정 집계] {tally} · finding 합계 "
          f"{sum(len(r['findings']) for r in out)} · → {path}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(HERE))
    raise SystemExit(main())
