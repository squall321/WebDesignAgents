# 위젯 구조 보존 커버리지 — ReportArchive 38종 전수

작성 2026-07-27. 구현 `src/wdpipeline/widgets.py`, 검증 `tests/test_widgets_extract.py`,
합성 픽스처 `data/widget_check/synthetic_blocks.json`.

스키마 단일 소스는 `/home/koopark/claude/ReportArchive/backend/app/widgets/registry.py`
의 `WIDGET_REGISTRY`(38종)다. 이 문서의 content 구조 서술은 그 `content_schema_for` /
`props_schema` 를 직접 덤프해 확인한 것이고, 실물 대조는
`examples/reportarchive/report_sample.json` 으로 했다.

## 0. 이 라운드가 고친 것

이전 `fragmentize` 는 모든 위젯을 평문으로 눌러 담았다. 흐름도의 엣지, 표의 열 정의,
진행률의 수치·상한이 문장으로 뭉개져 씬 템플릿이 데이터로 받을 방법이 없었다.

| 항목 | 이전 | 이후 |
| --- | --- | --- |
| report_sample.json 조각 수 | 140 | 63 |
| 구조 payload 를 실은 조각 | 0 | 12 |
| 구조 위젯 블록 중 추출 성공 | 0 / 12 | 12 / 12 |
| 표 1개(33행)가 차지하는 조각 | 33 | 1 (+ `structured.rows` 33행) |
| 미디어 자산의 블록 문맥 | 없음(file_id 평면 집합) | `collect_media()` 로 복원 |

## 1. 핵심 함정 — 열 정의는 content 가 아니라 props 에 있다

`table.columns`, `comparison.cases`, `progress_bar.default_max`/`unit`,
`milestone.start_date`/`end_date`, `flowchart.orientation`, `raci_matrix.default_roles`
는 **props** 에 저장된다(실물 `report_sample.json` 확인). content 스키마에도 같은 키가
있어 content 가 있으면 그쪽이 이긴다. 그래서 어댑터는 블록 전체
(`{type, props, content}`)를 받고 **content → props** 순으로 필드를 찾는다.
content 만 보는 구현은 표의 열 이름을 통째로 잃는다.

부수 함정 두 가지.

- `fmea` content 는 `{"fmea_items": {...rows: [...]}}` 로 한 겹 감싸여 있다.
- `key_value` 의 `items` 는 **필드 선언**이고 실제 값은 `content[<key>]` 최상위에 있다.

## 2. payload 6종

| kind | 형태 |
| --- | --- |
| `table` | `{columns:[{key,label}], rows:[{col_key: str}], caption, files?}` |
| `graph` | `{nodes:[{id,label,level?,note?,group?,value?}], edges:[{from,to,label?}], shape:"flow"\|"tree"\|"network", caption}` |
| `series` | `{series:[{label,value?,unit?,max?,group?,parent?,x?,z?,values?,n?}], axis:{min?,max?}, chart_type, caption, unit?}` |
| `timeline` | `{milestones:[{label,date,status,note?}], range?:{start,end}, caption}` |
| `pairs` | `{pairs:[{key,label,value}], caption}` |
| `media` | `{media_type, files:[{file_id,caption,alt}], caption}` |

## 3. 38종 전수 표

씬 템플릿 후보는 현재 카탈로그 10종(`modules/scene-templates/`: opening · problem ·
concept · process · differentiator · proof · closing · compare · dataviz · timeline)
기준이다. 세로 포맷 4종(vtpl.hook/metric/stack/cta)은 다른 워크플로가 작업 중이라 뺐다.

> 이 열은 **의미상 후보**다. 슬롯이 실제로 그 데이터를 담을 수 있는지(`maxItems` ·
> `maxLength`)는 별개이고, 실측 결과는 §8 이다. 실물 12블록 중 슬롯에 도달하는 건
> 3건(25%)뿐이다.

### 표군 (5종) — 전부 보존

| 위젯 | 구조 보존 | payload | 씬 템플릿 후보 | 비고 |
| --- | --- | --- | --- | --- |
| `table` | ✅ 완전 | table | compare · proof · dataviz | 열 정의는 props.columns. 열 선언이 없으면 행 키 합집합으로 유도 |
| `comparison` | ✅ 완전 | table | **compare**(정확 대응) · differentiator | cases → 열. `kind:"image"` 셀은 alt/caption 을 텍스트로 낮추고 `file_id` 는 `files` 로 승격 |
| `raci_matrix` | ✅ 완전 | table | proof · process | roles → 열, `assignments` → 셀(R/A/C/I) |
| `fmea` | ✅ 완전 | table | problem · proof | content 가 `fmea_items` 로 한 겹 감싸짐. `failure_mode` 는 `{name,entity_id}` → name |
| `record_table` | ✅ 완전 | table | proof | `properties` 키 합집합이 열이 된다 |

### 다이어그램군 (5종) — 전부 보존

| 위젯 | 구조 보존 | payload | 씬 템플릿 후보 | 비고 |
| --- | --- | --- | --- | --- |
| `flowchart` | ✅ 완전 | graph(flow) | **process**(정확 대응) · concept | items 는 선형이라 엣지를 순차 생성(n1→n2→…). `description` → node.note |
| `tree` | ✅ 완전 | graph(tree) | concept · process | `parent` 가 **라벨**을 가리킨다(id 아님). 라벨 중복은 `라벨#2` 로 분리, level 은 parent 체인 깊이 |
| `mind_map` | ✅ 완전 | graph(tree) | concept | tree 와 같은 parent-rows 구조 |
| `network` | ✅ 완전 | graph(network) | **concept**(방사형 노드) | id 기반 nodes/edges 를 그대로 |
| `sankey` | ✅ 완전 | graph(network) | process · dataviz | links 의 source/target 은 노드 **라벨**. value 는 엣지 label + value 로 |

### 수치군 (14종) — 12종 완전 · 2종 부분

| 위젯 | 구조 보존 | payload | 씬 템플릿 후보 | 비고 |
| --- | --- | --- | --- | --- |
| `progress_bar` | ✅ 완전 | series | **dataviz**(정확 대응) · proof | value/max/unit/note/status 보존. axis `{min:0,max:default_max}` |
| `chart` | ✅ 완전 | series | **dataviz** | x_column_key 를 뺀 number 열마다 계열. 다계열이면 `group`=열 라벨 |
| `pie` | ✅ 완전 | series | dataviz · proof | rows label/value, chart_type=pie\|doughnut |
| `waffle` | ✅ 완전 | series | dataviz | pie 와 동형 |
| `treemap` | ✅ 완전 | series | dataviz | `parent` 를 계열 항목에 남겨 계층 보존 |
| `packing` | ✅ 완전 | series | dataviz | treemap 과 동형 |
| `radar` | ✅ 완전 | series | proof · concept | 계열×축 격자를 항목으로 펼침. 다계열이면 `"계열 · 축"` 라벨 + `group` |
| `quadrant` | ✅ 완전 | series | differentiator · concept | plot 모드는 `x`/`value(y)`, bucket 모드는 `group`=사분면 |
| `scatter` | ✅ 완전 | series | dataviz · proof | series 정의의 x_key/y_key 로 행을 훑어 `x`/`value` |
| `scatter3d` | ✅ 완전 | series | dataviz | scatter + `z` |
| `box` | ✅ 완전 | series | proof | **통계를 지어내지 않는다** — 그룹별 원시값을 `values`+`n` 으로 보존 |
| `density` | ✅ 완전 | series | proof | box 와 동형(groups[].values) |
| `heatmap` | ⚠️ 부분 | series | dataviz | 2D 격자를 `"행 × 열"` 셀 항목으로 **평탄화**. 값은 무손실이나 격자 배치는 잃는다 |
| `contour` | ⚠️ 부분 | series | dataviz | heatmap 과 동일. matrix 모드·long-form(rows: x,y,z) 모드 둘 다 처리 |

`heatmap`/`contour` 가 부분인 이유: 격자를 그대로 받을 씬 템플릿이 카탈로그에 없다.
값 자체는 전부 살아 있으므로, 격자 씬이 생기면 `x_labels`/`y_labels`/`matrix` 를
payload 에 덧붙이는 것으로 완전 보존이 된다.

### 일정군 (1종) · 키값군 (2종) — 전부 보존

| 위젯 | 구조 보존 | payload | 씬 템플릿 후보 | 비고 |
| --- | --- | --- | --- | --- |
| `milestone` | ✅ 완전 | timeline | **timeline**(정확 대응 — status done/current/planned 가 스키마 그대로 일치) | props 의 start/end_date → `range` |
| `key_value` | ✅ 완전 | pairs | opening · closing · proof | `items` 는 필드 선언, 값은 `content[key]` |
| `record` | ✅ 완전 | pairs | proof | `properties` dict + `name` |

### 미디어군 (6종) — 자산 채널로 보존

| 위젯 | 구조 보존 | payload | 씬 템플릿 후보 | 비고 |
| --- | --- | --- | --- | --- |
| `image` | ✅ 완전 | media | 전 템플릿 배경/삽화 | `files[].{file_id,caption,alt}`. 일부 보고서는 `props.file_id` 로 참조해서 props 까지 훑는다 |
| `video` | ✅ 완전 | media | proof | files + caption |
| `attachment` | ✅ 완전 | media | (직접 배치 없음 — 출처 표기) | filename → alt |
| `cad_3d` | ✅ 완전 | media | proof | 단일 `content.file_id` + `loaded_filename` |
| `doc_viewer` | ✅ 완전 | media | (출처 표기) | 단일 file_id |
| `html_embed` | ✅ 완전 | media | (렌더 불가 — 링크만) | file_id/bundle_id |

**미디어군은 텍스트 조각을 만들지 않는다.** 이미지 캡션이 claim 조각으로 둔갑하면
심의가 그것을 근거로 인용한다. 대신 `widgets.collect_media(norm)` 이 블록 문맥
(page/block_id/section/caption/alt)과 함께 자산 목록을 내고, `norm["assets_meta"]`
(= `wdpipeline.assets.resolve_assets` 산출: local_path/width/height/aspect/미해결 사유)를
file_id 로 조인해 `asset` 키에 붙인다. `comparison` 의 이미지 셀도 같은 목록에 잡힌다.

### 텍스트군 (5종) — 구조 payload 없음 (의도)

| 위젯 | 구조 보존 | 미커버 사유 |
| --- | --- | --- |
| `heading` | — | 텍스트 그 자체. 기존 claim 조각으로 충분 |
| `rich_text` | — | 마크다운 산문. 문장 분해는 LLM 정제 몫 |
| `bulleted_list` | — | 항목당 1조각이 이미 씬 배치 단위와 일치 |
| `card` | — | `cards[].{title,body,badge,stat}` 는 구조가 있으나 이번 라운드 범위 밖. **tpl.v-stack 매핑 후보** — 다음 라운드 1순위 |
| `equation` | — | `latex` 는 KaTeX 렌더가 필요. 씬 엔진에 수식 렌더러 없음 |

## 4. 조각 분해 정책 — 왜 대표 1건으로 압축했는가

구조 payload 가 나오는 위젯은 **대표 조각 1건 + `structured`** 로 압축한다
(텍스트군은 기존대로 항목당 1조각 유지).

1. **중복** — 행 단위 텍스트 조각은 `structured.rows` 의 열화 사본이다. 같은 정보를
   두 형태로 두 번 싣는다.
2. **브리핑 독점** — `wdmcp.server._facts_for_briefing` 은 조각을 키워드 점수로
   top_k=5 만 고른다. 표 1개가 조각 33건이면 관련 표 하나가 브리핑 근거 5칸을
   전부 먹는다. 실제 report_sample.json 에서 evidence 조각 82건 중 35건(43%)이
   **표 블록 단 2개**에서 나왔다(table 35 · comparison 10 · flowchart 18 ·
   key_value 17 · tree 1 · raci 1).
3. **무손실** — 행/노드/수치는 `structured` 에 전부 남는다. 사라진 게 아니라 자리를 옮겼다.

대가: 대표 조각의 `text` 는 200자 상한(기존 계약)이라 심의가 **텍스트로 읽는** 표 본문은
줄어든다. `text` 는 `"{한 줄 요약} — {평탄화 본문}"` 형태로 채워 요약만은 항상 남긴다
(예: `"표 3열×33행: 카테고리/위젯/용도 — 텍스트 heading 섹션 제목 …"`).
브리핑이 그 요약을 별도 필드로 끌어올리는 배관은 §7 에서 붙였다.

## 5. 미지 타입 추적

`GROUP_BY_TYPE` 에 없는 위젯은 `extract_structured` 가 `None` 을 돌려주고,
`coverage_stats(norm)` 이 `unknown_types: {타입: 건수}` 로 남긴다. ReportArchive 가
위젯을 추가하면 여기서 0 이 아닌 값으로 드러난다. `tests/test_widgets_extract.py::
test_group_table_covers_registry` 는 38종 집합 자체를 고정해 조용한 누락을 막는다.

## 6. 실측

```text
$ uv run pytest tests/test_widgets_extract.py -q
35 passed

# report_sample.json (실물)
블록 44 · 구조군 12 → 추출 성공 12 / 실패 0 / 미지 0
by_kind: table 5 · graph 4 · pairs 2 · series 1
조각 140 → 63 (구조 조각 12건이 payload 동반)

# synthetic_blocks.json (registry content_schema 근거 합성)
40블록 / 39타입(38종 + 미지 1) → 구조 성공 34 · 텍스트군 5 · 미지 1 · 실패 0

# report_with_images.json + assets/ (자산 경로 교차 확인)
블록 5 · image 4 → 구조 성공 4 / 실패 0
collect_media: f-hero 2400x1350 · f-diagram 800x600 · f-logo 512x512 resolved,
               f-nowhere unresolved(사유 기록) — 텍스트 조각은 heading 1건뿐

$ uv run pytest tests/test_widgets_briefing.py -q
12 passed

$ uv run python data/widget_check/template_fit.py
[real]      구조 블록 12 · 그대로 0 · 라벨 축약 필요 3 · 용량 초과 6 · 슬롯 없음 3 → 슬롯 도달 25%
[synthetic] 구조 블록 34 · 그대로 14 · 라벨 축약 필요 2 · 용량 초과 0 · 슬롯 없음 18 → 슬롯 도달 47%
```

### 커버리지 % 정리

| 지표 | 분모 | 분자 | % |
| --- | --- | --- | --- |
| 위젯 타입 구조 보존 (설계) | 38종 | 33종 (텍스트군 5종은 의도적 제외) | **87%** |
| 구조 대상 타입 추출 성공 (합성 전수) | 33종 | 33종 | **100%** |
| 실물 구조군 블록 추출 성공 | 12블록 | 12블록 | **100%** |
| 실물 전체 블록 중 구조 payload 보유 | 44블록 | 12블록 | 27% (나머지는 텍스트군 32) |
| 조각 중 구조 동반 | 63조각 | 12조각 | 19% |
| **구조 조각의 심의 브리핑 도달** | 12조각 | 12조각 | **100%** (§7) |
| **구조 payload 의 씬 슬롯 도달 (실물)** | 12블록 | 3블록 | **25%** (§8) |
| 구조 payload 의 씬 슬롯 도달 (합성 33종) | 34블록 | 16블록 | 47% (§8) |
| 미디어 자산 file_id 해결 | 4건 | 3건 | 75% (미해결 1건 사유 기록) |
| **해결된 자산이 들어갈 씬 슬롯** | 3건 | **0건** | **0%** — 이미지 슬롯이 카탈로그에 없다 (§9) |

## 7. 심의 브리핑까지의 배관 — 구조 요약이 [F#] 로 간다

구조를 조각에 실어도 **심의가 그것을 못 보면** 씬 템플릿 선택 근거가 되지 않는다.
브리핑 경로는 두 개이고 둘 다 같은 포맷터(`wdmcp.session.split_fact_structure`)를 쓴다.

| 경로 | 소비자 | 변경 |
| --- | --- | --- |
| `wdmcp.server._facts_for_briefing` → `BriefingFact` | MCP 클라이언트(Claude 페르소나) | `structured`(요약 한 줄) · `widget`(원천 타입) 필드 추가 |
| `wdllm.orchestrator._load_fragments` → `[F#]` 프롬프트 줄 | GLM 무인 심의 | 라벨 칸이 `조각:evidence` → 구조 요약으로 |

`split_fact_structure(frag) -> (요약, 본문)` 은 fragmentize 가 만든
`"{요약} — {본문}"` 에서 요약을 떼어 별도 칸으로 올린다. **중복 없음**이 핵심이다 —
요약이 text 에도 남으면 같은 문자열을 두 번 싣는다.

실측 — report_sample.json 구조 조각 12건.

```text
브리핑 문자수 2391 → 2355 (요약 335자 분리, 구분자 " — " 제거로 -36)
요약 길이 min 10 · max 58 · 평균 28자 — 한 줄 예산 준수 (테스트가 120자 상한 강제)
```

MCP 브리핑 fact 실물 — `meeting_get_briefing` 응답.

```json
{"marker":"[F61]","ref":"RA-d077508a-061","type":"metric","widget":"progress_bar",
 "structured":"진행률 7계열: 100%/100%/100%",
 "text":"Phase 0/1 — 작성자 owner check · 게시(Mount) 100% Phase 1.7 — …"}
{"marker":"[F43]","ref":"RA-d077508a-043","type":"evidence","widget":"raci_matrix",
 "structured":"표 6열×8행: 작업/작성자/추가 편집자/보직장…",
 "text":"작성자 추가 편집자 보직장 부서 멤버 시스템 관리자 보고서 본문 작성 / 저장 …"}
```

GLM 오케스트레이터 프롬프트 실물.

```text
[F17] ref=RA-d077508a-017 | 흐름도 6노드 선형 | 엔지니어 — 개인 공간 작성 — 초안/메모/…
[F30] ref=RA-d077508a-030 | 표 3열×33행: 카테고리/위젯/용도 | 텍스트 heading 섹션 제목 …
[F61] ref=RA-d077508a-061 | 진행률 7계열: 100%/100%/100% | Phase 0/1 — 작성자 owner …
[F1]  ref=RA-d077508a-001 | 조각:claim | ReportArchive 플랫폼 개요          ← 구조 없는 조각은 종전 라벨
```

**원 데이터는 브리핑에 싣지 않는다.** rows·nodes·values 는 `fragments.json` 에 남고
씬 조립이 직접 읽는다. 브리핑에 가는 것은 요약 한 줄뿐이다
(`test_summary_is_a_summary_not_the_data` 가 `{`/`[`/개행 유입을 차단).

## 8. 씬 템플릿 수용 실측 — 세 번의 측정 (초판 → 구조 매핑 → d-* 3종)

측정기는 두 개다. 기준이 달라 수치도 다르다 — 표마다 어느 기준인지 명시한다.

- **블록 대조** `data/widget_check/template_fit.py` — 블록 하나씩 "받아줄 슬롯이
  있고 그대로 들어가는가"를 카탈로그 `schema.json` 의 maxItems/maxLength 로 대조
  (하드코딩 없음). 판정 4단계: `ok` / `trim`(라벨만 초과) / `overflow`(용량 초과 —
  잘라야 들어간다) / `none`(슬롯 없음).
- **조립기 실측** `wdpipeline.scenario.slot_fit_report` — 실제 조립 규칙(그룹 요약·
  대표 선별·씬 분할 힌트)까지 적용한 판정 5단계(`ok/trim/summarized/split/none`)와,
  역할 7개를 두고 경쟁한 끝에 **실제 문서에 실렸는가**(placed)를 따로 센다.
  도달(reach) = none 제외 비율, 배치(placed) = 실린 비율.

### 슬롯 용량 (schema.json 실측 — d-* 3종 추가 후)

| 슬롯 | maxItems | 라벨 필드 maxLength |
| --- | --- | --- |
| `process.steps` | 6 | `name` 12 |
| `timeline.milestones` | 6 | `name` 14 |
| `dataviz.bars` | 5 | `label` 9 |
| `compare.rows` | 4 | `aspect` 4 |
| `concept.nodes` | 8 | `name` 12 |
| `proof.cases` | 3 | `title` 24 |
| `closing.stats` | 3 | `d` 24 |
| `v-stack.cards` | 4 | `title` 30 |
| **`d-matrix.rows`** | **8** (열 ≤8) | `label` 24 |
| **`d-media.files`** | **3** | `caption` 18 |
| **`d-multi.series`** | **4** (항목 ≤7) | `name` 10 |

### 이전/이후 — 블록 대조 (template_fit.py, d-* 포함 재실행 2026-07-28)

| 대상 | 라운드 | ok | trim | overflow | none | 슬롯 도달(ok+trim) |
| --- | --- | --- | --- | --- | --- | --- |
| 실물 12블록 | 초판 (07-27) | 0 | 3 | 6 | **3** | **25%** |
| 실물 12블록 | d-* 이후 | **3** | 3 | 6 | **0** | **50%** |
| 합성 34블록 | 초판 (07-27) | 14 | 2 | 0 | **18** | **47%** |
| 합성 34블록 | d-* 이후 | **30** | 2 | 1 | **1** | **94%** |

실물의 `none` 3건(raci 6열×8행 · table 4열 · comparison 3안)이 전부
`d-matrix.rows` 로 도달했고, raci 8행은 용량에 **정확히** 들어간다(ok).
합성의 `none` 18건 중 17건이 해소 — 다계열 8종은 `d-multi.series`, 미디어 6종은
`d-media.files`, 격자 2종은 `d-matrix.rows`. 남은 미수용은 분포형 `treemap` 1건
(§9 #7)과 `fmea` 12열(행은 들어가나 열 8 초과 — overflow, 열 선별은 심의 몫)이다.

### 이전/이후 — 조립기 실측 (slot_fit_report, 실물 report_sample 12블록)

| 구성 | ok | trim | summarized | split | none | 도달 | 배치 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 기본 풀 · structured_templates=False | 0 | 3 | 2 | 4 | 3 | **75.0%** | **58.3%** |
| 기본 풀 · True (compare/dataviz 대체) | 0 | 3 | 3 | 2 | 4 | 66.7% | 41.7% |
| **d-\* 옵트인 풀 · True** | **3** | 3 | 2 | 3 | **1** | **91.7%** | 41.7% |

읽는 법 두 가지.

1. **도달과 배치는 다르다.** d-* 풀에서 도달은 91.7%까지 오르지만 배치는 41.7%다 —
   씬 역할은 7개뿐이라 같은 종류 payload 끼리(흐름도 3건 → process 1자리) 그리고
   대체 템플릿끼리(아래 2번) 자리를 다툰다. 배치를 올리는 길은 씬 분할(split 힌트
   소비)이지 슬롯 증설이 아니다.
2. **대체는 공짜가 아니다.** structured_templates=True 는 역할의 기본 씬을 대체
   템플릿으로 바꾸는 것이라, proof 가 dataviz 로 바뀌면 33행 표의 그룹 요약 카드
   (proof.cases)가 사라지고, differentiator 를 d-matrix 가 가져가면 2안 비교가
   자리를 잃는다(도달 91.7% 의 none 1건이 그것이다). 어느 대체가 이 보고서에
   맞는지는 심의가 고른다 — 파이프라인은 선택지와 손실을 정직하게 계상할 뿐이다.

### d-* 옵트인 경계 — 열어야 붙는 곳

조립 라우팅(`_EXACT_MATCH`·빌더)은 `wdpipeline.scenario` 에 편입 완료. 다만 d-* 는
**포맷 template_pool 에 선언된 역할에서만** 발동한다. 현행
`formats/wide-16x9/format.yaml` 풀에는 아직 없어 기본 경로 동작은 불변이고,
아래 3역할을 여는 것이 남은 전부다 (실증에 쓴 오버라이드 스펙:
`data/pipeline/widget_e2e/formats/wide-16x9/format.yaml`).

```yaml
problem:        [tpl.problem, tpl.d-media]
differentiator: [tpl.differentiator, tpl.d-matrix, tpl.compare]
proof:          [tpl.proof, tpl.dataviz, tpl.d-multi]
```

빌드에도 미결 하나 — `build_render_package` 에 자산 복사 단계가 없어 d-media 의
`src: assets/{파일명}` 사본은 호출측이 복사해야 한다(`widget_e2e/driver.py` 가 실례).

### E2E 실증 (2026-07-28 — data/renders/widget_e2e/stills/)

report_sample + 합성 이미지 2장을 `d-*` 옵트인 풀 · structured_templates=True 로
빌드·렌더해 씬 스틸로 확인했다 — flowchart 6단계 → 절차 씬 실노드 6개(01~06),
progress_bar 7계열 → dataviz 막대 5개 + "외 2계열은 원문 참조", raci 6열×8행 →
d-matrix 격자(R/A·C·I 코드 칩, "6열×8행 원문 수록"), 합성 이미지 2장 → d-media
도판 카드(캡션·출처 표기). 7게이트 QA `passed=True` (error 0 · warning 1 —
tpl.concept 노드 라벨 4px 초과, d-* 무관 기존 이슈).

### 잘라 넣기가 왜 답이 아닌가

`overflow` 를 상위 N개 절단으로 해결하면 33행 표에서 4행만 남는다. 심의가 근거로 인용한
표가 화면에서는 다른 표가 된다. 자르는 판단은 **심의(무엇이 핵심 행인가)**의 몫이지
파이프라인의 몫이 아니다. 조립기는 자르는 대신 그룹 요약·대표 선별로 압축하고
생략 건수를 화면에 명시하며(`외 N건`), d-matrix 도 같은 원칙(`외 N행`)을 따른다.

## 9. 신규 템플릿 필요 목록 — 다음 라운드 창작 대상

§8 의 `overflow`/`none` 을 슬롯 형태별로 묶은 것이다. 우선순위는 실물 미수용 건수 순.

| # | 필요한 씬 | 받아야 할 payload | 대상 위젯 | 실물 미수용 | 현 카탈로그 대체 가능? |
| --- | --- | --- | --- | --- | --- |
| 1 | **격자 표** (N열×M행, 스크롤/행 강조) | `kind=table`, 열 3개 초과 또는 행 4개 초과 | table · comparison(3안+) · raci_matrix · fmea · record_table | 5블록 | 불가 — compare 는 2안×4행 고정 |
| 2 | **이미지/도판** (file_id + 캡션 + alt) | `kind=media` | image · video · cad_3d · doc_viewer · attachment · html_embed | 0블록\* | **불가 — 14종 어디에도 이미지 슬롯이 없다** |
| 3 | **스펙 목록** (키·값 6~12쌍) | `kind=pairs`, 4쌍 이상 | key_value · record | 2블록 | 불가 — closing.stats 3칸 |
| 4 | **다계열·다항목 차트** (계열×축, 6항목 이상) | `kind=series` 에 `group` 있거나 항목 6+ | chart · radar · scatter · scatter3d · box · density · quadrant · progress_bar(6계열+) | 1블록 | 불가 — dataviz.bars 는 단일 계열 5칸 |
| 5 | **계층 트리** (depth 2~4, 노드 8+) | `kind=graph`, `shape=tree` | tree · mind_map · treemap · packing | 1블록 | 불가 — concept.nodes 는 방사형 8개 |
| 6 | **긴 흐름도** (7단계+) 또는 process 용량 확장 | `kind=graph`, `shape=flow`, 노드 7+ | flowchart · sankey | 0블록 | 6단계까지만 |
| 7 | **격자 수치**(히트맵) | `kind=series` 2D 격자 | heatmap · contour | 0블록 | 불가 — 현재 widgets.py 도 평탄화 중 |

\* 실물 `report_sample.json` 에는 image 블록이 없다. 별도 픽스처
`data/widget_check/report_with_images.json` 의 image 4블록(자산 3건 해결)이 대상이고,
**해결된 자산 3건이 들어갈 슬롯이 0개**라 화면에는 아직 한 장도 못 들어간다.
이 라운드의 목표 중 "이미지가 화면에 들어갈 길" 은 자산 해결(75%)까지 왔고
씬 슬롯에서 막혀 있다 — #2 가 다음 라운드 최우선인 이유다.

라벨 길이 문제(§8 `trim`)는 신규 템플릿이 아니라 **LLM 정제**로 푼다. 흐름도 6노드는
슬롯 6칸에 정확히 맞지만 실물 라벨("엔지니어 — 개인 공간 작성" 등)이 12자를 넘는다.
구조는 파이프라인이, 축약은 심의가 담당하는 경계가 여기다.
