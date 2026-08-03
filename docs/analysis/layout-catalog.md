# 레이아웃 카탈로그 전수 — 32 아키타입 목표 대비 현황

작성 2026-07-29. 집계 기준은 `modules/scene-templates/*/module.yaml`(formats 선언)과
`*/schema.json`(minItems·maxItems·라벨 maxLength)을 **직접 읽은 실측**이다. 이 문서의
숫자는 손으로 적은 상수가 아니라 그 파일들에서 나온다 — 스키마가 바뀌면 이 표도 틀린다.

재실측 스크립트는 두 개다.

| 자 | 스크립트 | 무엇을 재는가 |
| --- | --- | --- |
| 블록 대조 | `data/coverage_check/template_fit_tier1.py` | payload 하나가 슬롯에 그대로 들어가는가 (schema.json 의 maxItems/maxLength 대조) |
| 조립기 실측 | `data/coverage_check/slot_fit_tier1.py` | 실제 조립 규칙·역할 경쟁까지 적용한 **도달**과 **배치** |

---

## 1. 이번 라운드 신규 4종 — 커버리지 공백 1순위

"보고서에 실제로 자주 있는데 담을 그릇이 없다"로 뽑은 네 개다.

| 템플릿 | 담는 데이터 | 항목 상한 (schema 실측) | 언제 쓰나 | structured payload 대응 |
| --- | --- | --- | --- | --- |
| `tpl.c-ratio` (nat 12) | 구성비 — 전체를 나눠 갖는 값 | `series` 4~7 · label 20자 · display 6자 | 점유율·예산 배분·유형별 분포. 막대로 그리면 "전체 대비"가 사라지는 자리 | `kind=series` → `series[{label,value}]`·`unit` 그대로. 위젯 `pie`·`waffle`·`treemap`·`packing`, 그리고 합 100 근사인 단일 계열 |
| `tpl.c-trend` (nat 13) | 값의 궤적 — 시점별 수치 변화 | `points` 4~12 (label 5자) × `lines` 1~3 (label 8자) | 월별 실적·누적 진척·추이 비교. `tpl.timeline` 은 사건의 이정표라 수치 변화를 못 담는다 | `kind=series` → `series[].label`→`points[].label`, `series[].group`→`lines[].label`, `series[].value`→`lines[].values[i]`, `axis`·`unit` 그대로. 위젯 `chart(line/area)`·시점 라벨을 가진 단일 계열 |
| `tpl.c-branch` (nat 14) | 조건 분기·병렬 절차 | `nodes` 3~12 (레벨 0~3, label 22자·판단 12자) · `edges` 2~14 (label 3자) | 판단이 있는 절차. `tpl.process` 는 선형 6단계라 갈림을 못 그린다 | `kind=graph` → `nodes[{id,label,level}]`·`edges[{from,to,label}]` **필드명 그대로**. 위젯 `flowchart(분기형)`·`tree`·`mind_map` |
| `tpl.c-grid` (nat 13) | 항목 목록 4~9개 | `cards` 4~9 · label 16자 · desc 36자 (배치 필드 없음) | 사례·기능·항목 목록. `tpl.proof` 는 3열 2~3장 고정이라 6~9항목을 못 담는다 | `kind=pairs`(6쌍+) → `label`→`cards[].label`, `value`→`cards[].desc` / `kind=table` 2열 6행+ → 첫 열이 label, 둘째 열이 desc. 위젯 `key_value`·`record`·`record_table`·2열 `table` |

### 왜곡 방지가 어디에 걸려 있는가 (심의 확인분)

| 템플릿 | 구조로 막은 것 | 실측 근거 |
| --- | --- | --- |
| `c-ratio` | `percent/share/angle/tilt/depth` 필드 부재 → 백분율을 저작할 수 없다. 화면 비율은 언제나 `value/Σvalue` 파생 | 조각 각도 합 **360.0000°** · 와플 칸 **정확히 100** · 지분 3.50% 조각은 링 밖 라벨 생략 (`dv_audit_report.json`) |
| `c-trend` | `axis.min` 기본 0, 0 이 아니면 절단 칩·파단 글리프 강제 표기. `axis.max` 는 데이터 최댓값으로 승격 | 절단 칩 표기 확인. **단, 하한은 미클램프** — `axis.min=80`·데이터 58 에서 값 3개가 플롯 밖 409.2px (심의 blocking F1) |
| `c-branch` | `level` 0~3 정수 · 전진 엣지만 렌더 · `contains{kind:decision} minContains 1` (선형 절차의 둔갑 차단) | 엣지 세로 구간이 거터 120px 안 — 노드 관통 0건. **단, 레벨당 노드 수 상한이 없다** — 9개 시 판단 노드 텍스트 영역 17px vs 글리프 27px (심의 blocking F2) |
| `c-grid` | `cols/rows/fontSize/cardWidth` 필드 자체가 없다 → 데이터가 폰트를 깎을 수 없다 | 상한을 채운 9장(label 16·desc 36·badge 8) 실렌더에서 카드 내부 텍스트 넘침 **0건** |

### 심의 판정 (module_review 4건 · 2026-07-29)

| 모듈 | 판정 | blocking | 회의록 |
| --- | --- | --- | --- |
| `tpl.c-ratio` | **Conditional-Go** | F1 `display` 생략 시 값 표기가 6자 계약 밖 → 값존 150px 를 47px 초과 | `data/meetings/20260729-025205_module_review_tpl-c-ratio_fe06/minutes.md` |
| `tpl.c-trend` | **Conditional-Go** | F1 `axis.min` 이 데이터 최솟값으로 클램프되지 않는다 (하단 절단) | `…_tpl-c-trend_7800/minutes.md` |
| `tpl.c-branch` | **Conditional-Go** | F2 레벨당 노드 수 상한 부재 (F1 게이트 2 미실행은 major) | `…_tpl-c-branch_bd7d/minutes.md` |
| `tpl.c-grid` | **Conditional-Go** | F1 게이트 2(글자수 대비 길이) 미실행 | `…_tpl-c-grid_3852/minutes.md` |

네 건 모두 `status: draft` 유지다. 조립기(`wdpipeline.scenario`)는 심의가 지적한 두
결함을 **조립 단계에서 우회**하도록 배선돼 있다 — `_build_c_ratio` 는 `display` 를 항상
채우고, `_build_c_trend` 는 데이터 최솟값 위의 `axis.min` 을 싣지 않으며,
`_branch_graph` 는 레벨당 3개로 자른다. 템플릿 자체의 수정은 제안자 몫으로 남았다.

---

## 2. 가로 무대(wide-16x9) 전수 표 — 31종

`formats: [wide-16x9]` 로 선언된 씬 템플릿 전부다. 항목 상한은 schema.json 의 주 배열
`minItems~maxItems (라벨 필드 maxLength)` 이고, 배열이 없는 템플릿은 고정 슬롯이다.

| # | 템플릿 | 라운드 | 담는 데이터 | 항목 상한 | structured payload |
| --- | --- | --- | --- | --- | --- |
| 1 | `tpl.opening` | 초판 | 배지·대형 타이틀·서브타이틀 | 고정 슬롯 | — (텍스트) |
| 2 | `tpl.problem` | 초판 | 챗봇 목업 + ✕ 실패 목록 | `failures` 2~4 | — (텍스트) |
| 3 | `tpl.concept` | 초판 | 방사형 개념 노드 + 라운드 | `nodes` 4~8 (12자) · `rounds` 2~4 | `graph` tree/network (계층·엣지 손실) |
| 4 | `tpl.process` | 초판 | 선형 절차 | `steps` 3~6 (12자) | `graph` shape=flow |
| 5 | `tpl.differentiator` | 초판 | 2안 대비 흐름 | `flow` 1~2 (16자) | `table` 3열 2안 비교 |
| 6 | `tpl.proof` | 초판 | 근거 카드 3열 | `cases` 2~3 (24자) | `pairs` · `table` 그룹 요약 |
| 7 | `tpl.closing` | 초판 | 수치 3칸 + CTA | `stats` 2~3 (24자) · `ctas` 1~3 | `pairs` · 단일 계열 `series` |
| 8 | `tpl.compare` | 07-26 | A/B 비교 표 | `rows` 2~4 (aspect 4자) | `table` 3열(항목+A+B) |
| 9 | `tpl.dataviz` | 07-26 | 단일 계열 가로 막대 | `bars` 2~5 (9자) · `insights` 1~3 | `series` 단일 계열 |
| 10 | `tpl.timeline` | 07-26 | 마일스톤(사건) | `milestones` 3~6 (14자) | `timeline` |
| 11 | `tpl.d-matrix` | 07-27 | N열×M행 격자 표 | `columns` 3~8 (10자) × `rows` 2~8 (24자) | `table` 3열+ |
| 12 | `tpl.d-media` | 07-27 | 도판·이미지 | `files` 1~3 (caption 18자) | `media` (자산 채널) |
| 13 | `tpl.d-multi` | 07-27 | 다계열 그룹 막대 | `series` 2~4 (10자) × `categories` 3~7 (8자) | `series` with `group` |
| 14 | **`tpl.c-ratio`** | **07-29 ★** | **구성비 도넛/와플 + 지분 범례** | **`series` 4~7 (20자)** | **`series` 비율형** |
| 15 | **`tpl.c-trend`** | **07-29 ★** | **추세 라인 + 판독 칼럼** | **`points` 4~12 × `lines` 1~3** | **`series` 시계열** |
| 16 | **`tpl.c-branch`** | **07-29 ★** | **분기 흐름도(판단 마름모)** | **`nodes` 3~12 · `edges` 2~14** | **`graph` 분기형** |
| 17 | **`tpl.c-grid`** | **07-29 ★** | **카드 그리드 4~9장** | **`cards` 4~9 (16자)** | **`pairs` 6쌍+ · 2열 `table`** |
| 18 | `tpl.l-split` | 07-29 | 좌 설명 / 우 근거 간이표 | `bullets` 3~5 (40자) | `table` (간이) |
| 19 | `tpl.l-list` | 07-29 | 목록형 상세 행 | `rows` 5~8 (30자) | `pairs` |
| 20 | `tpl.l-tree` | 07-29 | 계층 트리 | `nodes` 3~13 (22자) · `edges` 2~12 | `graph` shape=tree |
| 21 | `tpl.l-quote` | 07-29 | 인용·강조 문장 | 고정 슬롯 | — (편집 판단) |
| 22 | `tpl.l-kpi` | 07-29 | 다지표 계기판 | `metrics` 4~6 (14자) | `series` 다지표 |
| 23 | `tpl.l-quad` | 07-29 | 2×2 사분면 배치 | `items` 4~10 (18자) | `series` 좌표(quadrant) |
| 24 | `tpl.l-ba` | 07-29 | Before/After 대비 | 고정 슬롯 | `table` 2안 비교 |
| 25 | `tpl.l-mix` | 07-29 | 표 + 막대 혼합판 | `stats` 2~3 (14자) | `table` + `series` |
| 26 | `tpl.o-question` | 07-29 | 질문형 오프닝 | `question` 1~2 · `topics` 3 | — (텍스트) |
| 27 | `tpl.o-statement` | 07-29 | 선언형 오프닝 | `lines` 2~3 (18자) | — (텍스트) |
| 28 | `tpl.o-metric` | 07-29 | 수치형 오프닝 | 고정 슬롯 | 단일 수치 |
| 29 | `tpl.x-summary` | 07-29 | 요약형 클로징 | `points` 3~5 (34자) | — (텍스트) |
| 30 | `tpl.x-next` | 07-29 | 다음 단계형 클로징 | `steps` 3~4 | — (텍스트) |
| 31 | `tpl.x-quote` | 07-29 | 인용형 클로징 | 고정 슬롯 | — (텍스트) |

세로(`short-9x16`) 4종(`vtpl.hook/stack/metric/cta`)과 문서형(`deck-doc-16x9`·`deck-4x3`·
`print-a4`) 5종(`tpl.doc-cover/toc/section/body/summary`)은 무대가 달라 이 표 밖이다
(전체 디렉터리는 40개).

---

## 3. 32 아키타입 목표 대비

| 축 | 목표 | 현재 | 남은 것 |
| --- | --- | --- | --- |
| 가로(wide-16x9) 씬 아키타입 | **32** | **31** | **1칸** |
| 이번 라운드 기여 | — | +4 (`c-ratio`·`c-trend`·`c-branch`·`c-grid`) | — |
| 세로(short-9x16) | 4 | 4 | 0 |
| 문서형(deck-doc/deck-4x3/print-a4) | 5 | 5 | 0 |

라운드 시작 시 궤도는 24종이었고 공백 8칸 중 **1순위 4칸이 이번에 채워졌다**. 나머지
칸은 병렬 워크플로의 `o-*`(오프닝 변주 3)·`x-*`(클로징 변주 3)가 함께 들어와 31종이
됐다. 남은 1칸을 두고 아래 후보들이 경쟁한다 — 고르는 판단은 심의 몫이고, 파이프라인은
미수용 실측만 제출한다.

### 남은 칸의 후보 (2·3순위) — 실측 미수용 근거

| 순위 | 필요한 그릇 | 받아야 할 payload | 대상 위젯 | 현 상태 | 왜 지금 카탈로그로 안 되나 |
| --- | --- | --- | --- | --- | --- |
| 2 | **격자 수치(히트맵)** | `series` 2D 격자 | `heatmap` · `contour` | `widgets.py` 가 `"행 × 열"` 셀로 평탄화 | 격자 배치 자체를 받을 슬롯이 없다. 값은 무손실이라 슬롯만 생기면 완전 보존이 된다 |
| 2 | **분포(박스플롯·밀도)** | `series` 의 `values[]`/`n` | `box` · `density` · `treemap`(계층 루트) | **슬롯 없음(none)** — 재실측에서 유일하게 남은 미수용 | 통계를 지어내지 않으려고 원시값을 보존했는데, 원시값 목록을 담을 그릇이 없다 |
| 3 | **넓은 표(열 9+)** | `table` 열 9 이상 | `fmea`(12열) | `d-matrix` 열 8 상한 초과 | 행은 들어가나 열이 넘친다. 열 선별은 심의 판단이라 파이프라인이 자를 수 없다 |
| 3 | **계층 비중** | `series` 의 `parent` 계층 | `treemap` · `packing` | `c-ratio` 가 평탄화 수용 | 비중(값)과 계층(부모)을 동시에 그리는 그릇이 없다. `l-tree` 는 값이 없고 `c-ratio` 는 계층이 없다 |

---

## 4. 커버리지 재실측 — 이전/이후

### ① 블록 대조 (`template_fit_tier1.py` — schema.json 실측 대조)

| 대상 | 라운드 | ok | trim | overflow | none | 슬롯 도달(ok+trim) |
| --- | --- | --- | --- | --- | --- | --- |
| 실물 12블록 | 초판 (07-27) | 0 | 3 | 6 | 3 | 25% |
| 실물 12블록 | d-* 이후 (07-28) | 3 | 3 | 6 | 0 | 50% |
| 실물 12블록 | **1순위 4종 이후 (07-29)** | **5** | 3 | **4** | **0** | **67%** |
| 합성 34블록 | d-* 이후 | 30 | 2 | 1 | 1 | 94% |
| 합성 34블록 | **1순위 4종 이후** | **30** | 2 | 1 | **1** | **94%** |

실물에서 `ok`(구조를 그대로 싣는 블록)가 3 → **5**로 늘었다. 늘어난 2건은 `key_value`
9쌍·8쌍이 `c-grid.cards` 에 **잘리지 않고** 들어간 것이다(이전에는 `closing.stats` 3칸으로
가서 overflow). `tree` 15노드는 `c-branch` 로 도달하되 레벨당 3개 상한에 8노드가 걸려
`overflow` 로 남는다 — 측정기가 조립기의 절단분을 항목 수에서 빼지 않도록 원본 노드 수로
세기 때문이다(잘린 사실이 수치에서 사라지면 안 된다).

합성이 94%로 그대로인 이유는 합성 픽스처의 `pie`·`waffle`·`packing` 이 2~3항목뿐이라
`c-ratio` 하한(4항목)에 못 미쳐 기존 `dataviz` 슬롯에 남기 때문이다 — 이미 `ok` 였으므로
수치가 오르지 않는다.

### ② 조립기 실측 (`slot_fit_tier1.py` — 역할 경쟁까지 적용, 실물 12블록)

| 구성 | ok | trim | summarized | split | none | 도달 | 배치 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 기본 풀 · `structured_templates=False` | 0 | 3 | 2 | 4 | 3 | **75.0%** | **58.3%** |
| 기본 풀 · True | 0 | 3 | 3 | 2 | 4 | 66.7% | 41.7% |
| 1순위 4종 옵트인 풀 · True | **2** | 3 | 2 | **1** | 4 | 66.7% | 41.7% |
| **d-\* + 1순위 4종 풀 · True** | **5** | 3 | 1 | 2 | **1** | **91.7%** | 41.7% |

읽는 법 세 가지.

1. **기본 경로는 바뀌지 않았다.** 첫 줄(75.0% / 58.3%)이 이전 라운드 수치와 정확히
   같다 — `c-*` 는 포맷 `template_pool` 에 선언된 역할에서만 발동하는 옵트인이고
   현행 `formats/wide-16x9/format.yaml` 풀에는 없다. 회귀 위험 0.
2. **도달률보다 `ok` 를 봐야 한다.** 1순위 4종만 열면 도달은 66.7% 로 같지만 `ok` 가
   0 → 2, `split`(씬 분할 권고)이 4 → 1로 준다. 같은 payload 가 **잘리지 않고** 들어간
   것이다. d-* 까지 함께 열면 `ok` 5 · `none` 1 로 도달 91.7% 다.
3. **배치는 41.7% 에서 멈춘다.** 슬롯이 늘어도 씬 역할은 7개뿐이라 흐름도 3건이
   `process` 한 자리를 다투고, `differentiator` 를 `d-matrix` 가 가져가면 2안 비교가
   자리를 잃는다. 배치를 올리는 길은 **씬 분할**(split 힌트 소비)이지 슬롯 증설이 아니다.

### ③ 38종 위젯 중 아직 슬롯이 없는 것

`template_fit_tier1.py` 의 `uncovered` 집계(실물 + 합성 전수, 위젯당 최선 판정 기준).

| 판정 | 종수 | 위젯 |
| --- | --- | --- |
| `ok` 구조를 그대로 싣는다 | 30 | `chart` `comparison` `raci_matrix` `flowchart` `tree` `mind_map` `network` `sankey` `pie` `waffle` `packing` `progress_bar` `radar` `scatter` `scatter3d` `heatmap` `contour` `quadrant` `box` `density` `milestone` `key_value` `record` `table` `image` `video` `attachment` `cad_3d` `doc_viewer` `html_embed` |
| `trim` 라벨만 축약 필요 | 1 | `record_table` |
| `overflow` 용량 초과 | 1 | `fmea` (12열 > d-matrix 8열) |
| **`none` 받을 슬롯 없음** | **1** | **`treemap`** |
| 텍스트군 (의도적 제외) | 5 | `heading` `rich_text` `bulleted_list` `card` `equation` |
| 미측정 | 0 | (없음) |

**`treemap` 하나만 남았다.** 사유는 두 겹이다 — 합성 픽스처의 treemap 은 계층 루트
행(`{label:"전사", value:null, parent 없음}`)을 갖는데 ① `value: null` 이라 비율 조각으로
환원할 수 없고(`c-ratio` 는 전 항목 값 필수) ② `parent` 계층을 값과 함께 그릴 그릇이
없다. §3 표의 2·3순위 후보 "분포" 와 "계층 비중"이 이 한 건을 두고 갈린다.

`box`·`density` 가 `ok` 로 잡히는 것은 합성 픽스처가 **2그룹**뿐이라 `d-multi` 격자에
들어가기 때문이고, 원시 분포(`values[]`)를 분포로 그리는 그릇은 여전히 없다 —
값이 슬롯에 닿았다는 것과 분포로 읽힌다는 것은 다르다.

---

## 5. 구조 매핑 배선 — 판별 규칙이 곧 계약

`src/wdpipeline/scenario.py` 의 §"커버리지 1순위 4종 판별" 주석이 정본이고, 아래는 요약이다.

| payload | 신호 | 가는 곳 | 배타성 |
| --- | --- | --- | --- |
| `series` | `chart_type ∈ {pie, doughnut, waffle, treemap, packing}` **또는** 값 합이 100±0.5 | `c-ratio.series` | 항목 라벨이 시점 표기면 **제외** — 월별 구성비는 추세다 |
| `series` | `chart_type ∈ {line, area}` **또는** 항목 라벨의 2/3 이상이 시점 표기(`25.12` `2026-01` `3월` `4주` `Q1` `2026`) | `c-trend.points` × `c-trend.lines` | 비율 적격이면 **먼저 배제** (`_trend_series` 가 `_ratio_series` 를 먼저 본다) |
| `graph` | 한 노드의 자식이 2개 이상 **또는** 엣지 라벨 존재. 레벨 구간 4단 이하 | `c-branch.nodes` | 선형 절차는 `tpl.process`, 5단 이상은 부적격(축소·폰트 감소 금지) |
| `pairs` 6쌍+ / `table` 2열 6행+ | 항목 수 | `c-grid.cards` | 3열 이상 표는 `d-matrix` 가 정본 — 슬롯이 겹치지 않는다 |

네 그릇 모두 **포맷 `template_pool` 옵트인 경계** 안에 있다. 여는 방법은 아래 4줄이다
(`formats/wide-16x9/format.yaml` — 이 라운드에서는 열지 않았다).

```yaml
process:        [tpl.process, tpl.c-branch]
differentiator: [tpl.differentiator, tpl.c-ratio, tpl.compare]
proof:          [tpl.proof, tpl.c-trend, tpl.c-grid]
```

검증은 `tests/test_scenario_tier1_mapping.py`(19건)가 한다 — 판별 신호의 배타성,
빌더 산출의 스키마 통과, 심의 지적 2건의 조립기 우회, 옵트인 경계(기본 풀 불변)를 모두 고정한다.

---

## 6. 미결 — 레지스트리 병합 대기

`modules/registry.yaml` 의 `load_order_contract` 에 창작 라운드 산출 jsx 6개가 아직
안 실려 있다 (`omx-layouts-a/b/c/d.jsx` · `omx-openings.jsx` · `omx-closings.jsx`).
`tests/test_build_loadorder.py::test_every_template_file_is_loaded` 가 이걸 잡는다 —
전 회귀에서 **유일하게 실패하는 1건**이고, 병렬 워크플로 4개가 공유하는 상태다.
각 라운드가 `modules/_pending/*.registry.yaml` 에 병합 조각을 남겼으므로
오케스트레이터가 `load_order_contract` + `modules` 를 합치면 닫힌다.

---

## 7. 발표 레이아웃 8종(`tpl.l-*`) — 배치 다양성 라운드 (2026-07-29)

§2 전수 표의 18~25번을 상세화한 절이다. 앞선 라운드들이 **어떤 데이터를 담느냐**(위젯
커버리지)를 넓혔다면, 이 8종은 **같은 화면에 데이터를 어떻게 배치하느냐**를 넓혔다.
수치는 전부 `schema.json` 실측이다 —
재실측: `uv run python data/layout_check/catalog_scan.py` → `data/layout_check/catalog_slots.json`.

| 템플릿 | 담는 데이터 형태 | 주 슬롯 상한 (schema 실측) | 언제 쓰나 | 구조 payload 대응 |
| --- | --- | --- | --- | --- |
| `tpl.l-split` (nat 14) | 좌 설명(리드+불릿+꼬리) + 우 근거 슬롯 4종 | `bullets` 3~5 · text 40자(**5개면 22자**) / `visual.table.rows` 3~6 · label 20 · 셀 14 | 설명하며 근거를 내밀 때 — 실무 발표자료 최다 사용 배치 | `table`(간이표) · `series`(가로 막대) |
| `tpl.l-list` (nat 14) | 번호 배지 + 제목 + 설명(+상태 칩) 행 | `rows` 5~8 · title 30 · desc 100자(**6행↑ 50자**) · chip 6 | 항목이 많은 목록형 상세(기술 스택·점검 항목) | `pairs` 5쌍 이상 |
| `tpl.l-tree` (nat 12) | 루트 1 · 중간 2~4 · 리프 ≤8 의 3단 위계 | `nodes` 3~13 · label **14/18/22**(레벨별) · note 13 · `edges` 2~12 | 위계를 그릴 때(조직도·아키텍처) | `graph(shape=tree)` — **엣지 보존** |
| `tpl.l-quote` (nat 8) | 문장 하나 + 화자·직함 | `quote` 70자(80/70/60px 자동 하향) · speaker 20 · role 26 | 챕터 전환·결론 각인 | — (문장 선택은 편집 판단) |
| `tpl.l-kpi` (nat 11) | 지표 타일(라벨·수치·단위·증감·스파크) | `metrics` 4~6 · label 14 · value **6자 숫자 문자열** · unit 3 | 지표 4개 이상 동시 제시 | `series` 단일 4항목 이상(축 무관) |
| `tpl.l-quad` (nat 13) | 좌표판 번호 점 + 번호 범례 | `items` 4~10 · label 18 · x·y **0~1 정규화** | 포지셔닝·우선순위 논증 | `series` **x 동반**(quadrant·scatter·matrix) |
| `tpl.l-ba` (nat 14) | 좌우 두 상태(칩·제목·항목·대표 수치) | `before/after.items` 3~5 · text 22 · title 30 · summary.value 6 | 상태 **전체** 대비(도입 전/후) | `table` 3열 비교 |
| `tpl.l-mix` (nat 15) | 요약 수치 띠 + 간이표 + 막대 | `stats` 2~3 **또는** `lead`(oneOf 배타) / `table.rows` 3~5 · label 13 · 셀 **6자** / `chart.bars` 3~4 | 표와 수치를 한 화면에 | `table` + `series` **동시**(유일) |

### 7.1 경계 — 같은 payload 를 여러 그릇이 받을 때

심의가 가장 자주 묻는 질문이다. 조립기(`_fit_record`·`_assign`)는 아래 순서로 자동
배정하지만 **우선순위의 정본은 포맷 `template_pool` 선언 순서**이고, 조립기 순서는 풀이
둘 이상을 열었을 때의 기본값이다.

| payload | 받을 수 있는 씬 (조립기 순서) | 무엇으로 갈리나 |
| --- | --- | --- |
| `table` 3열 비교 | `compare` → `differentiator` → `l-ba` | 행 짝 비교면 `compare`, 상태 서술이면 `l-ba` |
| `table` 격자·요약 | `proof`(그룹 요약) → `l-mix` → `d-matrix` → `l-split` | 표가 주인공이면 `d-matrix`, 수치와 함께면 `l-mix`, 설명의 근거면 `l-split` |
| `graph(tree)` | `concept` → `l-tree` | 동등한 참여자면 `concept`(엣지 버림), 위계면 `l-tree`(엣지 보존) |
| `series` 단일 | `l-quad`(x 있으면) → `l-kpi` → `l-mix` → `dataviz` → `closing` | 좌표가 있으면 계기판이 아니라 좌표판, 지표 나열이면 `l-kpi`, 축이 주장이면 `dataviz` |
| `pairs` | `l-list` → `proof` → `closing` | 5쌍 이상 목록이면 `l-list`, 근거 카드면 `proof` |

**밀도 축으로도 갈린다** — 같은 종류를 담아도 담기는 양이 다르다(라벨 자수 합).

| 그릇 | 문자 예산 | 성격 |
| --- | --- | --- |
| `proof.cases` | 3장 × (24 + 70) = 282자 | 카드 — 서술을 압축 |
| `process.steps` | 6칸 × (12 + 40) = 312자 | 절차 — 순서가 정보 |
| `l-list.rows` | 8행 × (30 + 100) = 1040자 | 목록 — 스캔이 정보 |
| `closing.stats` | 3칸 × (14 + 24) | 수치 요약 |
| `l-kpi.metrics` | 6타일 × (14 + 6 + 3) | 다지표 — 축 없음 |

### 7.2 도달률 이전/이후 — 역할을 늘리면 배치가 오른다

같은 입력(`report_sample`, 구조 payload 12블록)을 **포맷 풀만 바꿔** 재측정했다. 측정기는
`wdpipeline.scenario.slot_fit_report`, 기록은 `data/layout_check/layout_fit.json`
(재현: `uv run python data/layout_check/driver.py`).

| 구성 | ok | trim | summarized | split | none | 도달 | 배치 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 기본 7역할 풀 (이전) | 0 | 3 | 2 | 4 | 3 | **75.0%** | **58.3%** |
| 기본 풀 + 구조 대체(True) | 0 | 3 | 3 | 2 | 4 | 66.7% | 41.7% |
| **발표 레이아웃 11역할 풀 (이후)** | **2** | 3 | 5 | **1** | **1** | **91.7%** | **75.0%** |

§4②의 `d-* + 1순위 4종 풀`(91.7% / 41.7%)과 도달은 같고 배치가 다르다. 원인은 슬롯이
아니라 **역할 수**다 — 그 구성은 7역할, 이 구성은 11역할이라 흐름도 3건이 `process` 한
자리를 다투는 병목이 완화된다. "배치를 올리는 길은 슬롯 증설이 아니다"라는 §4 관측과
같은 이야기이며, 이번 라운드는 그 다음 문장을 실측했다 — **역할을 늘리면 오른다**.

신규 슬롯이 받아낸 5건.

| 원문 블록 | 이전 | 이후 |
| --- | --- | --- |
| `key_value` 9쌍 | `proof.cases` split (9→2, 카드 한 장에 2줄) | `l-list.rows` **9→8행** + 타이틀에 "외 1건" |
| `tree` 15노드 | `concept.nodes` 15→8 (엣지 전부 손실) | `l-tree.nodes` **15→12** + 엣지 11 + `omitted` 3 |
| `comparison` 4열 5행 | **none**(받을 슬롯 없음) | `l-split.visual.table` 5→5 **ok** |
| `raci` 6열 8행 | **none** | `l-mix.table` 8→5행 + 진척 막대 4개 **동시** |
| `progress_bar` 7계열 | `closing.stats` split (7→3) | `l-kpi.metrics` **7→6** + `omitted` 1 |

남은 `none` 1건은 4열 **2행** 표다 — 모든 표 슬롯의 행 하한이 3이라 어디에도 못 들어간다.
행 2개짜리 표는 씬이 아니라 문장으로 쓰는 편이 낫다는 것이 현재 카탈로그의 답이다.

**화면 밀도**(같은 보고서, 공백·비표시 필드 제외 실린 글자 수): 기본 7씬 **1351자** →
발표 레이아웃 12씬 **2388자(+76.8%)**. 씬별 최대는 `l-tree` 395 · `l-list` 339 ·
`l-split` 272 · `l-ba` 260 으로 기존 최대(`proof` 256)를 넘겼다. 반대로 `l-kpi` 68 ·
`l-quad` 119 는 12씬 중 최소인데, 전자는 증감·스파크를 구조 payload 가 만들 수 없어서이고
후자는 판 자체가 정보라서다(§7.3 판정 참조).

실증 산출물 — 12씬 빌드·렌더 스틸 `data/quality_compare/layouts/` 12장, QA 게이트 7종
`error 0 · warning 0 · info 0`(`data/layout_check/qa.json → data/qa_reports/20260729-040042-4f73fe/qa.json`),
조립 결과 `data/layout_check/scenario.json`.

### 7.3 심의 판정 (module_review 8건 · 2026-07-29)

패널은 TD·QA·MO·LG + 제안자 대리, 134턴, Finding 19건. 판정 원장은
`data/layout_check/verdicts_20260729.json`, 회의록은 `data/meetings/*_module_review_tpl-l-*/`.

| 템플릿 | 판정 | 등록 조건 (blocking·major) |
| --- | --- | --- |
| `tpl.l-quote` | **Go** | 없음 (minor 1건 — "각인 문장은 원문에서만 온다"를 계약에 명시) |
| `tpl.l-split` | Conditional-Go | F1 `conclusion` 34자 슬롯의 이름·용량 불일치("소결론"을 담을 수 없다) |
| `tpl.l-list` | Conditional-Go | F1 `omitted` 필드 부재 — 생략 표기가 타이틀 26자를 잠식 |
| `tpl.l-tree` | Conditional-Go | F1 가지당 리프 상한이 description 문구뿐(스키마 유효 입력이 세로 예산을 깬다) |
| `tpl.l-kpi` | Conditional-Go | F1 `delta`·`spark` 부재 시 타일 하단 공백 — 68자로 12씬 중 최소 |
| `tpl.l-ba` | Conditional-Go | F1 `summary` required 인데 비교 표에 수치가 없다(좌우가 같은 "5 개 관점") |
| `tpl.l-mix` | Conditional-Go | F1 파생 집계의 산식이 화면에 없다 · F2 "짧은 값 열만"이 스키마 밖(조립기)에 있다 |
| `tpl.l-quad` | **No-Go** | F1 사분면 이름 ↔ 극단 좌표 점 **34×32px 겹침**(영역 x<0.335 ∧ y>0.904) · F2 가로 정규화 기준 불일치 |

`tpl.l-quad` 만 등록 보류다. 다른 7종의 결함은 "덜 담긴다"인데 이것은 "다르게 말한다"이기
때문이다 — `widgets._x_quadrant` 가 `props.x_range`·축 이름을 payload 에 싣지 않아 가로
정규화 기준이 데이터 범위로 떨어지고(실증 2~9 vs 선언 0~10, 최대 20%p 이동), 항목이 원
위젯과 **다른 사분면에 앉을 수 있다**. 이 건은 템플릿 밖(`wdpipeline.widgets` payload 계약)
이라 제안자 혼자 닫지 못한다. 부수 성과로 게이트의 사각이 하나 확인됐다 — **게이트 5는
스크롤 넘침만 본다. 요소 간 겹침은 어느 게이트도 검사하지 않는다.**

### 7.4 쓰는 법 — 포맷 풀에 여는 것이 전부다

8종은 `d-*`·`c-*` 와 같은 옵트인 경계 안에 있다(포맷 `template_pool` 에 선언된 역할에서만
발동). 기본 `formats/wide-16x9/format.yaml` 은 손대지 않았으므로 기존 경로 동작은 불변이다.
실증에 쓴 스펙은 `data/layout_check/formats/wide-16x9/format.yaml`(11역할)과
`formats_quad/`(좌표 역할 추가 12역할)다.

```yaml
skeleton: [opening, problem, concept, detail, process, differentiator,
           evidence, matrix, dashboard, verdict, closing]
template_pool:
  problem:   [tpl.l-split, tpl.problem]   # 표/계열이 있으면 좌 설명 + 우 근거
  concept:   [tpl.l-tree, tpl.concept]    # 위계면 트리, 동등하면 방사형
  detail:    [tpl.l-list, tpl.proof]      # 키값 5쌍 이상이면 목록형 상세
  matrix:    [tpl.l-mix, tpl.d-matrix]    # 표+계열 동시면 혼합판
  dashboard: [tpl.l-kpi, tpl.closing]     # 지표 4개 이상이면 계기판
  verdict:   [tpl.l-quote]                # 결론 문장 각인
```

1순위가 payload 전용 템플릿인데 대응 payload 가 없으면 조립기가 폴백 가능한 템플릿에
자리를 넘긴다(`scenario._NEEDS_PAYLOAD`). 그래서 좌표 위젯이 없는 보고서에 `tpl.l-quad` 를
1순위로 걸어도 조립이 무너지지 않고 대안이 그 역할을 채운다.

검증은 `tests/test_scenario_layouts.py`(12건)가 한다 — 기본 풀 회귀(75.0%/58.3% 불변),
8종 라우팅, 용량과 정직 표기(생략 계상), 좌표 정규화의 순서 보존, 드라이버 기록 대조.
