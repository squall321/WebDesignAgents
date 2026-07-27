# WebDesignAgents — 전문가 심의 기반 발표자료 자동 생성 플랫폼 전체 계획서

작성일 2026-07-24 · 울트라 코드 워크플로우(분석 3 + 설계 3 + 검증 1 에이전트) 결과를 통합한 정본.

---

## 0. 한눈에 보기

| 항목 | 내용 |
| --- | --- |
| 목표 | ReportArchive 보고서 → 다중 페르소나 심의 → 소개영상(mp4/dc.html) 또는 PPT 자동 생성 |
| 회의체 | 모더레이터 1 + 전문가 13인 페르소나 (ExpertAgents 심의 엔진 이식) |
| 이중 백엔드 | 경로 A: MCP(Claude가 페르소나 연기) / 경로 B: GLM-5-2 vLLM 무인 오케스트레이터(HWAXPortal 상속) |
| 렌더 스택 | zip의 엔진(support.js + animations-v2.jsx) 무수정 재사용, 씬 템플릿 7종 모듈화 |
| 생태계 연계 | HEAXHub 산하 등록(manifest 1파일, MCP Gateway 자동 노출) + VoiceRecorder TTS API 소비 |
| 품질 | 자동 게이트 7종 + 모듈 승격 심의 + 골든 스냅샷 회귀 = 우상향 성장 루프 |
| 패키징 | Python 3.13 전용 venv(uv, `.venv` 생성 완료) + vendor 커밋 + Apptainer SIF 렌더 노드 |
| 마일스톤 | M0 export 검증 → M1 MCP 심의 → M2 vLLM 오프로드 → M3 완전 자동 |

**핵심 원칙 3가지.**
1. **코어는 LLM을 모른다** — 심의 엔진(wdcore)은 순서·검증·기록만 강제하고, LLM 호출은 어댑터(MCP/vLLM)에만 둔다.
2. **시각은 시간의 순수 함수** — 모든 씬은 `localTime`의 결정적 함수. 재생·영상 export·PPT 정지 캡처가 같은 코드 경로를 공유한다.
3. **파일이 진실** — 회의·파이프라인 산출물 전 단계를 파일로 영속화. 어느 단계에서든 재조립·재개 가능.

### 0.1 구현 현황 (2026-07-26 기준)

| 영역 | 상태 | 실증 |
| --- | --- | --- |
| M0 렌더/export | ✅ 완료 | HWAX 소개영상 실렌더 mp4 90.000s·PPTX, 결정성 2160프레임 중 14프레임만 서브픽셀 차 |
| M1 심의 경로(MCP) | ✅ 완료 | 페르소나 14인·툴 11종·E2E(보고서→심의→mp4+PPTX). 첫 실전 심의 19턴 완주 |
| M2 vLLM 경로 | 🔶 골격 완료 | wdllm 클라이언트·오케스트레이터 구현, 로컬 vLLM 실호출 검증. GLM-5-2 실서버 검증은 cae00 필요 |
| 웹 콘솔 | ✅ 완료 | FastAPI+SPA, 대화형 제작 패널(대화→수정→재빌드→프리뷰), HEAXHub manifest 등록 |
| TTS | ✅ 완료 | VoiceRecorder 실연동 — 음성+자막 먹싱 mp4 산출 |
| 아카이브 순환 | ✅ 완료 | P6 역기록 + 왕복 무결성(생성 보고서를 자체 P0가 재소비) |
| 템플릿 카탈로그 | 10종 | 시딩 7 + 창작 모드 자가 저작 3(dataviz Go, timeline·compare Conditional) |
| 테스트 | 240 passed | 전 영역 회귀 |

**아직 남은 것** — GLM-5-2 실서버 검증(M2), SIF 오프라인 렌더 노드·하이브리드 PPTX(M3), ReportArchive REST 실연동(자격증명 필요).

---

## 1. 목표와 범위

클로드 디자인 없이 클로드 코드(및 자체 vLLM)에서 `전문가 심의 플랫폼 소개영상.zip` 수준의 발표자료를 만들어내는 플랫폼. 구체적으로는 다음을 달성한다.

1. 웹디자인/발표자료 제작 전문 페르소나 회의체가 심의를 통해 시나리오를 결정한다.
2. MCP로 Claude에 물려 쓰는 경로(A)와 자체 서빙 vLLM으로 토론을 오프로드하는 경로(B)가 **동일한 심의 엔진 코어**를 공유한다.
3. ReportArchive의 보고서(1순위 입력)가 mp4 영상 또는 PPTX로 자동 변환된다.
4. zip의 스택을 측면별로 모듈화하고, 모듈 조합으로 품질이 보장되는 산출물을 만든다.
5. 심의에서 나온 개선 아이디어가 모듈로 승격·축적되어 갈수록 고급 자료를 만드는 성장 플랫폼이 된다.

비범위(현 단계). 실사 촬영 영상 편집, 3D 렌더, ReportArchive 자체의 수정(읽기 전용 연동만).

---

## 2. 참조 자산 분석 요약

### 2.1 ExpertAgents (`/home/koopark/claude/ExpertAgents`) — 심의 엔진의 원본

- 631개 마이크로 전문가를 `knowledge/{expert_id}/expert.yaml` 1파일(SSOT)로 정의. pydantic StrictModel(extra=forbid) 검증.
- **"서버는 LLM을 호출하지 않는다"** — MCP 서버는 페르소나+근거 봉투(`{ok, data, session, claude_instructions, error}`)만 반환하고, 클라이언트 Claude가 전 페르소나를 연기한다.
- 회의는 결정론적 상태머신(`src/expertcore/meetings/engine.py`)이 강제. 회의 유형 5종(brainstorm/design_review/tradeoff/dfmea/rca)이 선언적 RoundSpec 리스트로 정의됨.
- stance 프로토콜(propose/support/concern/rebut/question/accept/summarize) + 미응답 반박 자동 추출로 가짜 합의 방지.
- 환각 인용 차단 — 브리핑으로 실제 전달된 카드 ID만 `known_refs` 화이트리스트로 인용 허용.
- 영속화 `data/meetings/{stamp}_{type}_{slug}_{id4}/`(meta.json + turns.jsonl + minutes.md). 파일이 진실, 요청마다 엔진 재조립으로 resume.
- 3계층 분리 expertcore(코어)/expertmcp(MCP)/expertapi(FastAPI) — **본 프로젝트가 그대로 계승할 구조**.
- vLLM/OpenAI 연동은 없음. 서버 구동 모드는 `docs/02-design/04-meeting-engine.md` §6에 설계만 존재(미구현) — 경로 B의 참조 설계.

### 2.2 소개영상 스택 (`전문가 심의 플랫폼 소개영상.zip`) — 렌더 엔진

- 3층 구조. `support.js`(DC 런타임, 수정 금지) / `animations-v2.jsx`(타임라인 엔진, 수정 금지) / `hwax-scenes.jsx`(씬, 주 편집 대상).
- 씬은 `{localTime, progress, dur, index, count, scene}` props의 순수 함수. 전역 시계·useEffect·자체 rAF 금지 — export 결정성의 근거.
- `window.OM_SCENES`(JSON 문자열 리터럴, ≤16KB·1~50씬·dur∈(0,300])와 `OM_PLAYBACK`이 단일 진실 소스. 엔트리 여분 필드는 검증 없이 `scene` prop으로 무가공 전달 — **스키마 확장 지점**.
- 프레임 seek 프로토콜 — `svg[data-om-exportable-video-with-duration-secs]`에 `CustomEvent('data-om-seek-to-time-frame', {detail:{time, sync:true}})` dispatch. sync 지원 시 flushSync 동기 커밋으로 반환 즉시 캡처 가능.
- mp4 인코딩은 zip에 없음(호스트 편집기 위임) — **exporter는 자체 구현 필요**. Playwright + ffmpeg 경로가 가장 단순.
- frame-match 계약(진입/퇴장 효과는 progress 0과 1에서 0) 덕에 씬별 특정 시각 seek로 완성된 정지 화면 획득 가능 — **PPT 추출의 근거**.
- 오프라인 훅 — `window.__resources`/`__resourceBlobs`로 React/Babel/폰트 CDN 의존 제거 가능. 렌더 노드 격리에 사용.
- `시나리오-구성-방법론.md`가 조각 분해(Claim/Evidence/Case/Metric/CTA) → 단일 메시지 → 설득 골격 재배열 → 씬 데이터 JSON의 자동화 파이프라인 스펙을 이미 정의.

### 2.3 ReportArchive (`/home/koopark/claude/ReportArchive`) — 입력 소스 (실계약 확정)

- FastAPI(:3000, prefix `/api`) + React/Vite + PostgreSQL. 운영은 Apptainer SIF 폐쇄망 배포.
- **보고서는 디스크 파일이 아니라 DB JSONB다.** `reports` 테이블 — `pages[] = {template_id, name, content{block_id→위젯content}, extra_blocks[{id,type,props}], blocks_order[], block_sections}` 구조. 위젯 38종(`backend/app/widgets/registry.py`가 스키마 단일 소스).
- 획득 경로 3가지. ① REST — `POST /api/auth/login`(JWT) 후 `Authorization: Bearer` + `X-Workspace-Slug` 헤더로 `GET /api/reports`, `GET /api/reports/{id}`, `GET /api/reports/search`. ② MCP — `http://127.0.0.1:3002/mcp`(streamable-http)의 `search_reports`/`get_report` 등. ③ DB 직결(비권장).
- 이미지/첨부는 `file_id` 참조 → `GET /api/files/{file_id}`로 바이트 획득.
- 활용 가능한 부가 장치 — `search_text`(전 위젯 평탄화 평문, 내레이션 소스), `GET /api/reports/{id}/ai-summary`(core_message 후보), `block_sections`(background/purpose/scope 등 섹션 태그 → 설득 골격 매핑 힌트), `page_slide_ratio`(작성자가 의도한 슬라이드 비율).
- 서버측 export는 설계만 존재(`docs/[미구현] 헤드리스_내보내기_설계.md`) — 본 플랫폼이 JSON→자체 렌더링을 담당하는 것이 정석 경로.

---

## 3. 전체 아키텍처 — 코어 1개, 어댑터 2개

```text
[클라이언트]           [어댑터 — LLM 접점]          [코어 — LLM 무호출]
Claude Code ──MCP──▶  wdmcp (FastMCP stdio)  ─┐
                       봉투+claude_instructions │    wdcore
wda CLI ────────────▶ wdllm (AutoOrchestrator) ─┼─▶  MeetingEngine / RoundSpec 템플릿
                       │ OpenAI 호환 HTTP        │    BriefingBuilder(full/recall, [F#])
                       ▼                        │    minutes 렌더러 / MeetingStore
                  vLLM 서버 (/v1/chat/completions)
```

- **wdcore** — ExpertAgents `expertcore`의 engine/templates/minutes/store/models를 도메인 교체 후 이식. 발언 순서 결정론, known_refs 인용 차단, 미응답 반박 추출을 그대로 유지.
- **경로 A (wdmcp)** — FastMCP stdio. Claude Code가 브리핑을 받아 페르소나를 연기하고 턴을 제출한다. API 키 불필요, 즉시 가동 가능. **1차 구현 대상.**
- **경로 B (wdllm)** — vLLM OpenAI 호환 서버에 붙는 무인 오케스트레이터. 턴 루프 = `next_speaker → 브리핑 → vLLM 호출 → submit_turn 검증 → 거부 시 hint로 repair 1회 → 재실패 시 skip 기록`. 페르소나별 messages 독립 구성(교차 오염 차단), MeetingTurn 부분 스키마를 guided_json으로 강제.
- 두 어댑터는 동일한 store 재조립 경로를 공유하므로 어느 경로로 진행한 회의든 산출물 포맷이 같다. 경로 A로 시작한 회의를 경로 B가 이어받는 것도 구조적으로 가능하다.

### MCP 툴 11종 (부록 스키마는 M1에서 pydantic으로 확정)

| # | 툴 | 역할 |
| --- | --- | --- |
| 1~5 | `meeting_start / meeting_get_briefing / meeting_submit_turn / meeting_status / meeting_close` | ExpertAgents 계약 그대로 (2단계 참가자 확정 포함) |
| 6 | `report_ingest(report_id)` | ReportArchive REST/MCP 프록시 → 정규화 JSON (P0) |
| 7 | `report_fragmentize(doc_id)` | 조각 분해 지시문 반환, 결과 재제출 검증·저장 (P1) |
| 8 | `scenario_build(meeting_id)` | 회의 산출물 → 시나리오 JSON 초안 + 검증 결과 (P3) |
| 9 | `render_submit(scenario_path, targets)` | 씬 빌드+export 잡 등록, 잡 ID 반환 (P4~P5) |
| 10 | `render_status(job_id)` | 렌더 잡 상태·산출물 경로 조회 |
| 11 | `qa_run(build_path, gates?)` | 품질 게이트 실행, 리포트 JSON 반환. **리포트는 지식카드로 등록되어 심의 인용 근거가 된다** |

---

## 4. 파이프라인 P0~P5 — 단계별 입출력 계약

각 단계는 `data/pipeline/{run_id}/`에 자기 산출물 파일을 쓰고 다음 단계는 파일만 읽는다(재시도·부분 재실행의 전제).

### P0 — ingest (ReportArchive 포맷 → 정규화)

입력 모드 2개, 출력은 동일 — 하류(P1~)는 모드 차이를 모른다.

- **모드 1 — 파일 복붙 (1차, M1·사용자 확정).** ReportArchive에서 복사해 온 `report_archive_draft_v1` JSON(`{_type, title, report_date, tags, pages[]}` — pages는 `{name, content{block_id→위젯content}, extra_blocks[{id,type,props}], blocks_order}` 블록 구조)을 파일로 받는다 — `wda ingest --file report.json`. 접속 정보·인증 불필요. 포맷 픽스처는 `examples/reportarchive/report_sample.json`(실물 5페이지 샘플). `file_id` 참조 자산은 로컬 경로 매핑 테이블(`--assets-dir`)로 대체하고, 없으면 스킵 기록.
- **모드 2 — REST/MCP 실연동 (후순위, M3+).** `report_id`로 ReportArchive REST(`GET /api/reports/{id}`, JWT + `X-Workspace-Slug`) 또는 기존 MCP(`get_report`)를 프록시. `file_id` 자산은 `GET /api/files/{file_id}`로 다운로드. 접속 정보는 이 단계에서 `.env`(`WDA_RA_*`)에 기입.
- **블록 구조 보존 정규화(공통)** — 마크다운 평탄화 금지. 출력 `report.norm.json` = `{doc_id, title, report_date, tags, pages[{name, blocks[{id, type, props, content, section}]}], assets[{file_id, local_path}], ai_summary?, search_text?}`. `blocks_order` 순서로 정렬. 복붙 모드에는 `search_text`/`ai_summary`가 없으므로 정규화기가 위젯 텍스트 평탄화로 `search_text`를 자체 생성한다.
- 사람 구두 정리 입력(부차)은 동일 스키마로 변환하는 얇은 어댑터를 별도 제공.

### P1 — fragmentize (조각 분해)

- 방법론 문서 0단계 그대로 `Claim / Evidence / Case / Metric / CTA` 5축. LLM 호출(경로 A는 지시문, 경로 B는 vLLM)로 수행하되 **위젯 타입별 기본 매핑**으로 선분류해 LLM 부담을 줄인다.

| 위젯 타입 | 기본 조각 | 씬 후보 |
| --- | --- | --- |
| heading, rich_text, bulleted_list | Claim / Case | tpl.problem, tpl.concept |
| table, comparison, key_value, chart 계열, progress_bar | Metric / Evidence | tpl.proof, 데이터시각화 씬 |
| flowchart, tree, network, mind_map | 절차/구조 Evidence | tpl.process, tpl.concept |
| milestone, raci_matrix, fmea | Evidence | tpl.process, tpl.proof |
| image, video, cad_3d | 시각 자산 | 씬 배경/삽화 후보 |
| block_sections 태그 (purpose/background/scope 등) | — | 설득 골격(문제→접근→절차→차별→실증→결론) 배치 힌트 |

- 출력 `fragments.json` — `[{frag_id: "RA-{doc_id}-{seq:03d}", type, text, source:{page, block_id}, confidence}]`. 이 frag_id 목록이 **P2 회의의 초기 known_refs 화이트리스트**가 된다. 페르소나는 보고서에서 실제 추출된 조각만 인용할 수 있다.

### P2 — deliberate (심의)

§5의 회의체가 수행. 산출은 `data/meetings/{stamp}_{type}_{slug}_{id4}/`의 meta.json + turns.jsonl + minutes.md.

### P3 — scenario (시나리오 JSON 조립·검증)

- **통합 ScenarioDoc 스키마 (단일 정본).** 세 설계안의 발산을 다음과 같이 통일한다.
  - 루트·검증 규칙은 설계안 1의 ScenarioDoc(pydantic, `src/wdcore/models/scenario.py`).
  - `content` 하위 템플릿별 데이터 스키마는 설계안 3의 JSON Schema($defs, `x-read`/maxLength 실측 상한 포함).
  - OM_SCENES 주입 시에는 설계안 2의 **축약형 규칙** — `name/dur/nat/stills/tpl`만 남긴다(16KB 상한 대응).

```jsonc
{
  "version": "1.0",
  "meta": { "core_message": "...", "audience": "...", "duration_sec": 90,
            "tone": "...", "meeting_id": "...", "source_report_id": 578 },
  "content": { "opening": {...}, "problem": {...}, "concept": {...},
               "process": {...}, "differentiator": {...}, "proof": {...}, "closing": {...} },
  "scenes": [{ "name": "오프닝", "dur": 8, "nat": 8, "tpl": "opening@1",
               "stills": [6.5], "data_ref": "content.opening",
               "narration": "...", "transition": "cut" }],
  "tokens_theme": "hwax-blue",
  "playback": { "mode": "times", "count": 1 }
}
```

- 검증 — ssParse/ppParse 제약 이식(1~50씬, dur∈(0,300], 주입 축약형 ≤16KB, count 1..99) + stills∈[0,dur] + `tpl` 레지스트리 존재·status≠deprecated + `data_ref` 실경로 + 템플릿별 데이터 스키마. **stills 기본값은 템플릿 `schedule(data)`의 마지막 등장 시각 + 0.8s로 자동 산정**(설계안 3 규칙으로 단일화), 다단 페이즈 씬은 심의에서 명시 결정.

### P4 — scene build (렌더 패키지 생성)

- 출력 `data/build/{slug}/` — 엔트리 HTML + `scenes.jsx`(템플릿 바인딩) + `runtime/`(animations-v2.jsx 무수정 복사) + `vendor/`(React/ReactDOM 18.3.1 UMD, @babel/standalone 7.29.0).
- 저작 계약 준수 — OM_SCENES는 vanilla 인라인 스크립트의 JSON 문자열 리터럴, x-import는 엔진 먼저 씬 나중, 씬 name과 children 키 정확 일치, 3층 구성(토큰/크롬/데이터) 유지.
- support.js(DC 런타임)는 편집기 write-back이 필요한 경우에만 사용. 자동 렌더 경로는 React+Babel+엔진+씬을 직접 로드하는 순수 HTML 엔트리를 기본으로 한다(계약 동일, 단순).

### P5 — export (산출물)

- 영상 — 로컬 http 서빙(x-import가 fetch 기반이라 file:// 불가) → `__resourceBlobs` 주입(오프라인) → 3단계 대기(svg 마운트 → document.fonts.ready → `data-om-fonts-inlined="true"`) → `[data-omelette-chrome]` 숨김 → t=i/fps sync seek 루프 → svg 스크린샷 PNG → ffmpeg 조립(`-c:v libx264 -pix_fmt yuv420p`). WebCodecs 경로는 2차 최적화.
- PPTX — §9 참조.
- TTS(내레이션) — **자체 구현하지 않고 VoiceRecorder API를 소비한다**(§10.2, 사용자 확정). 씬별 `narration`을 타임코드 포함 스크립트로 조립해 VoiceRecorder 프로젝트를 생성 → 합성 잡 폴링 → `fit-timecode`로 씬 슬롯 자동 정렬(부족분 무음·초과분 배속, 불가 씬은 over_budget 리포트) → 씬별 `duration_sec`을 받아 nat 타임 스트레치 ±15% 흡수 판단, 초과 시 dur 재조정 제안을 게이트 2 리포트 형식으로 출력 → 병합 mp3를 ffmpeg 먹싱, SRT는 자막 트랙으로 재사용.

---

## 5. 페르소나 회의체

### 5.1 로스터 — 모더레이터 1 + 전문가 13 (카테고리 8종)

카테고리 `dir/narr/vis/mot/ux/impl/av/qa`. 각 페르소나는 `personas/{id}/persona.yaml` SSOT(ExpertAgents expert.yaml 포맷 계승)로 정의한다.

| abbr | id | 전문분야 | 심의 역할 | 발언 권한 |
| --- | --- | --- | --- | --- |
| CD | `dir-creative-director` | 크리에이티브 디렉션 | 모더레이터. 진행·쟁점 조직화·판정 집계(기술 주장 생성 금지) | 동률 시 캐스팅 보트 |
| ST | `narr-story-architect` | 서사 구조·핵심 메시지 | 발제자. 시나리오 초안·통합 소유 | scenario_patch 독점 작성권 |
| CP | `narr-copywriter` | 카피·자막·타이틀 | 문안 심의 (화면당 한 문장) | 제안권 |
| TY | `vis-typographer` | 타이포그래피 | 폰트 스택·위계·최소 가독 크기 | 제안권 |
| CB | `vis-color-brand` | 컬러·브랜드 | 토큰 팔레트·브랜드 일관성 | **조건부 거부권** |
| LG | `vis-layout-grid` | 레이아웃·그리드 | Frame 크롬·여백·정렬 | 제안권 |
| DV | `vis-dataviz` | 데이터 시각화 | 수치·차트 씬 정확성 (왜곡 시 rebut 의무) | 제안권 |
| MO | `mot-motion-director` | 모션 디자인 | 안무·이징·씬 길이 배분 | dur 배분 발의권 |
| AX | `ux-accessibility` | 접근성 | WCAG 대비·글자 크기·모션 과다 | **조건부 거부권** |
| AU | `ux-audience-advocate` | 청중 리서치 | 타깃 이해도·인지 부하·러닝타임 | 제안권 |
| TD | `impl-technical-director` | 렌더 엔진 계약 | 구현성 심사. 엔진 제약의 최종 수문장 | **절대 거부권** |
| SL | `impl-slide-editor` | 정적 슬라이드 | PPT 관점 심의·stills 시각 선정 | stills 발의권 |
| NR | `av-narration` | 내레이션·사운드 | TTS 대본·씬-음성 동기 | 제안권 |
| QA | `qa-consistency` | 품질 감사 | 디자인 시스템 준수·모듈 레지스트리 대조·재발명 적발 | R4 검수 승인권 |

- 회의별 실참가자는 시맨틱 라우터(앵커 0.75 + 키워드 0.25 − anti)의 2단계 확정 흐름으로 5~8인 추천. 14인 전원은 판정 라운드가 있는 회의에만.
- 모듈 심사 회의(§8)는 TD·QA·MO·LG + 제안자 고정 참가 — 별도 6종 페르소나를 만들지 않고 14인 로스터의 부분집합으로 운영한다(설계안 간 로스터 발산 해소).

### 5.2 회의 파이프라인

| 단계 | 회의 유형 | 템플릿 | 산출 |
| --- | --- | --- | --- |
| M1 컨셉 브레인스톰 | `brainstorm` | 기존 재사용 | core_message·tone 후보 |
| M2 시나리오 빌드 | `scenario_build` | **신규** | ScenarioDoc |
| M3 시안 크리틱 | `design_review` | 기존 재사용 | 렌더 결과에 Go/Conditional-Go/No-Go |
| (선택) 시안 선정 | `tradeoff` | 기존 재사용 | 시안 A/B/C 가중합 결정 |
| M4 모듈 심사 | `module_review` | design_review 파생 | 모듈 레지스트리 등록 |

신규 `scenario_build` 라운드 구조 — R1 구조발산(ST 발제 후 각자 scene_draft 제출) → R2 교차반박(TD 엔진 계약·AX 접근성·AU 인지 부하 필수, citation_required) → R3 수렴타임라인(ST scenario_patch 통합, MO dur 배분, SL stills, NR narration 동기) → R4 검증판정(검증기 결과 근거로 TD→AX→QA→CD 순 판정).

### 5.3 판정 규칙 (만장일치 강요 금지)

1. **절대 거부권(TD)** — 엔진 계약 위반 rebut 미해소 시 자동 No-Go(minutes.py의 미응답 반박 추출 로직 활용).
2. **조건부 거부권(AX·CB)** — 접근성·브랜드 rebut 미해소 시 상한 Conditional-Go. 조건은 action_item으로 기록해야 폐회 허용.
3. **다수결** — 그 외 R4 참가자 다수결, 동률 시 CD 캐스팅 보트.
4. 합의 안 된 취향 충돌은 open_issue로 회의록에 보존(강제 봉합 금지).

artifact enum 확장 — 기존 5종 + `scene_draft / scenario_patch / module_candidate`. StrictModel enum 확장에 따른 기존 데이터 하위 호환은 마이그레이션 스크립트로 처리(크리틱 반영).

### 5.4 시각 심의 채널 (크리틱 반영)

- 경로 A — 렌더된 스틸 PNG를 대화에 첨부하는 절차를 claude_instructions에 명시(Claude는 이미지를 볼 수 있다).
- 경로 B — 게이트 리포트의 수치(대비비·오버플로 건수·frame-match diff)를 텍스트 근거로 대체. VLM(예: Qwen-VL 계열) 도입 여부는 M2 결정 항목.

---

## 6. 씬 템플릿 · 모듈 라이브러리 · 디자인 토큰

### 6.0 화면 구성의 소유권 (설계 명제)

ReportArchive 위젯은 콘텐츠 조각일 뿐 화면 구성을 지정하지 않는다(문서 흐름 적층 + `page_slide_ratio` 힌트뿐). **화면 구성은 이 플랫폼의 고유 책임이다** — 씬 템플릿이 구성(배치·위계·모션 순서 = 논리)을 소유하고, 어떤 조각이 어떤 구성에 담기는지는 심의(P2)가 결정한다. P1의 위젯→씬 매핑표는 후보 힌트일 뿐 자동 배정 규칙이 아니다. 템플릿은 위젯의 1:1 변환이 아니라 설득 단위(씬당 하나의 주장)다.

### 6.1 씬 템플릿 7종 (hwax-scenes.jsx S1~S7을 일반화해 시딩)

| 템플릿 ID | 씬 타입 | 기본 시각 은유 | 권장 길이(90s 기준) |
| --- | --- | --- | --- |
| `tpl.opening` | 오프닝(각인) | 배지 + 대형 타이틀 | 8s |
| `tpl.problem` | 문제/필요성 | 챗봇 목업 + 스켈레톤 + ✕ 목록 | 13s |
| `tpl.concept` | 접근/개념 | 방사형 네트워크 | 11s |
| `tpl.process` | 절차 | 순차 점등 스텝 카드 그리드 | 18s |
| `tpl.differentiator` | 차별점 | R1→R2→R3 반박 카드 + 체크마크 수렴 | 13s |
| `tpl.proof` | 실증/신뢰 | 3열 사례 카드 + 배지 | 15s |
| `tpl.closing` | 결론/CTA | 통계 트리오 → 타이틀 + CTA 필 | 12s |

- 각 템플릿은 데이터 스키마(JSON Schema, `x-read` 낭독 필드·실측 maxLength 포함) + **안무 스케줄 순수 함수 `schedule(data)`**(등장 시각 선언 — 게이트 2, stills 기본값, PPT 추출 시각을 모두 이것으로 결정) + `nat` 기본값을 export한다.
- 시각 은유 카탈로그 9종을 독립 컴포넌트(`window.OMX.metaphors.*`)로 추출 — chatbot-mockup, radial-network, step-card-grid, rebuttal-flow, checkmark-converge, stat-trio, cta-pill, dot-grid, frame-chrome. 원칙은 방법론 그대로 "명제는 물체로, 변화는 동작으로".

### 6.2 디자인 토큰 3층

- 1층 raw(브랜드가 교체하는 유일한 층 — 팔레트 16색·폰트·그림자) / 2층 시맨틱(타입 스케일 24~112px, 1920×1080 절대 좌표, 모션 프리셋, **contrastPairs 전수 선언**) / 3층 컴포넌트 별칭.
- 템플릿 코드에 hex·px·초 리터럴 금지(정적 린트 차단). 이징 이름은 엔진 `Easing` 실제 키만 허용.
- 테마 주입은 `window.OM_THEME` JSON 문자열 리터럴(ppParse와 동일한 방어적 파서). 테마 교체 시 대비 게이트만 재실행하면 된다.

### 6.3 저작 2모드 — 창작 모드와 재사용 모드 (토큰 최소화 원리)

플랫폼의 경제성 핵심. **이미 만든 패턴은 다시 만들지 않고, 없는 패턴만 창작한다.**

**재사용 모드 (기본값).**
- 레지스트리에 맞는 템플릿이 있으면 LLM은 씬 코드를 한 줄도 생성하지 않는다. 산출은 `tpl` 참조 + 데이터 JSON뿐(씬당 수백 토큰).
- 브리핑에는 모듈 **축약 인덱스**(id·용도 한 줄·props 요약·in_scope)만 전달한다. 모듈 상세(스키마 전문·프리뷰)는 ExpertAgents의 `delivered_personas` full/recall 델타 패턴을 모듈에 확장한 `delivered_modules` 원장으로 관리 — 회의당 최초 1회만 full, 이후 ID recall. 같은 세션에서 같은 모듈 설명을 반복 전송하지 않는다.
- 씬 JSX 자체도 재생성하지 않는다 — P4 빌드가 레지스트리의 `template.jsx`를 바인딩만 해서 조립한다.

**창작 모드 (신규 양식이 필요할 때만).**
- 발동 조건 — 라우터/QA가 "기존 템플릿의 in_scope로 소화 불가" 판정을 낸 경우, 또는 심의에서 신규 시각 은유가 decision으로 채택된 경우.
- LLM이 엔진 계약 위에서 새 씬 JSX를 자유 저작한다. 창작의 품질을 받치는 3종 세트 — ① 마이크로 헬퍼 계층(`A(t,start,dur,from,to)`, `rise(t,at)`)과 Easing 카탈로그 ② **모션 문법 지식카드**(이징 선택 기준, 스태거 간격 규칙, 시간 위계 = 근거의 위계, frame-match) — MO 페르소나가 심의에서 인용 강제 ③ motion 토큰 프리셋(rise/pop/tag/exit/stagger).
- 창작물은 게이트 1~7 통과 + `module_review` 심의를 거쳐 레지스트리에 등록되고, **그 순간부터 재사용 모드의 소비 대상이 된다.** 다음 프로젝트부터는 같은 양식이 수백 토큰짜리 데이터 주입으로 재현된다.

**효과.** 시간이 갈수록 창작 모드 발동 빈도가 줄고(모듈 재사용률 80% 목표선, §8), 산출물당 토큰 비용이 우하향한다. 동적 애니메이션의 표현력은 창작 모드가 계속 확장하고, 축적된 표현력은 재사용 모드가 공짜에 가깝게 재공급한다.

---

## 7. 품질 게이트 7종 — `wda qa` (omx-qa)

S(정적) → D(데이터) → R(런타임) → V(결정성) 순서, 앞 단계 실패 시 뒤 생략. 출력은 `{gate, rule, scene, path, severity, detail}` JSON 리포트 + exit code. **리포트는 지식카드로 등록되어 다음 심의의 인용 근거가 된다**(qa_run 툴).

| # | 게이트 | 방식 |
| --- | --- | --- |
| 1 | OM_SCENES ↔ 씬 매핑 키 일치 | 정적(AST) + 런타임(씬 레이어 DOM 확인) |
| 2 | 글자수 대비 씬 길이 | `x-read` 합산 + `schedule(data)` + 타임 스트레치 반영. 위반 시 최소 dur 제안값 출력 |
| 3 | 대비(contrast) | 정적(contrastPairs 전수 WCAG 계산) + 런타임(stills 샘플링, 미선언 색 조합 경고) |
| 4 | 최소 폰트 크기 | 정적(24px 미만 오류) + 런타임(computed 실측 교차 검증) |
| 5 | 텍스트 오버플로 | stills 시각 seek 후 scrollWidth/Height·스테이지 이탈·카드 밀림 검사 |
| 6 | localTime 결정성 | 정적(Date.now/Math.random/setTimeout/useEffect 등 금지 식별자 AST 린트) + 런타임(이중 seek 픽셀 동일성) |
| 7 | frame-match | 씬 첫/끝 프레임 diff가 임계 이하 |

- **프레임 비교 기준 통일(크리틱 반영)** — 같은 머신 회귀는 해시 완전 일치, 머신 간(CI)은 perceptual diff(SSIM 또는 픽셀 diff 비율) 임계값 기준. 임계값은 M0에서 실측으로 확정.
- 정적 AST 게이트(1·4·6)는 `@babel/parser` 기반 Node CLI로 구현하되 `tools/omx-qa/`에 격리(자체 package.json, dev 전용). **런타임·렌더 경로는 Node 무의존 유지**(Playwright는 Python 바인딩). 이중 스택 충돌에 대한 명시적 결정이다.

---

## 8. 성장 루프 — 심의가 모듈을 만들고 모듈이 심의의 근거가 된다

### 8.1 모듈 레지스트리 (`modules/` — 설계안 3 구조를 정본으로)

```text
modules/
├─ registry.yaml                        # 전 모듈 인덱스
├─ scene-templates/{name}/
│  ├─ module.yaml                       # SSOT — id(tpl.*), type, status, version(SemVer),
│  │                                    #   engine_compat, in_scope/out_of_scope, quality
│  ├─ template.jsx                      # 컴포넌트 + schedule(data) + nat
│  ├─ schema.json                       # 데이터 스키마
│  ├─ fixtures/{min,typical,max}.json   # 경계 픽스처 3종 (게이트 상시 입력)
│  ├─ preview.dc.html                   # 단독 구동 (심의·회귀용)
│  ├─ fixtures/snapshots/               # 골든 스냅샷 (회귀 기준)
│  └─ reviews/                          # 심의 회의록 보관
├─ metaphors/{name}/ …                  # 동일 구조
└─ themes/{id}/{module.yaml, theme.json}
```

### 8.0 성장의 두 층위 — 템플릿과 포맷 (사용자 확정 2026-07-26)

축적은 **씬 템플릿(화면 구성)** 과 **포맷(장르)** 두 층위에서 각각 일어난다. 템플릿만 쌓이면 매번 장르를 처음부터 설계해야 하므로, **한 번 겪어본 포맷은 노하우째로 템플릿화되어 다음번엔 선택만으로 재현**되어야 한다.

| 층위 | 자산 | 축적되는 것 |
| --- | --- | --- |
| 씬 템플릿 | `modules/scene-templates/{id}/` | 화면 구성 1개(배치·모션·데이터 스키마) |
| **포맷** | `formats/{id}/` | 장르 1개(무대·길이·골격·산출 + **제작 노하우**) |

**포맷이 담는 노하우 (format.yaml 확장 필드).** 무대·길이·골격·산출은 기본이고, 그 위에 한 번의 제작 경험에서 얻은 것을 싣는다.

```yaml
status: draft | pilot | active          # 템플릿과 같은 수명주기
origin: { meeting_id: "...", created: 2026-07-26 }   # 어느 심의에서 나왔나
usage_count: 0                          # 실제 산출물 수 (자동 집계)
presets:
  deliberation:                         # 이 장르를 심의할 때의 회의 프리셋
    type: scenario_build
    participants: [ST, CP, AU, MO, NR]  # 이 장르에 필요한 페르소나
    agenda: ["청중·주의지속", "역할별 조각 배치", "세로 카피 자수", "낭독 예산"]
  copy_guide: { hook: 18, stack_item: 24, metric_label: 12 }   # 실측된 자수 상한
  dur_plan: { hook: 4, problem: 12, solution: 16, proof: 14, cta: 8 }
  narration: { rate: 5.5, max_silence: 2.0 }   # 실측으로 검증된 값
golden: { run_id: short_v1, artifacts: [...], qa_report: "..." }  # 검증된 레퍼런스
lessons: ["세로는 좌우 마진 72px 안에서 3줄 이상 금지 — 엄지 가림"]  # 심의가 남긴 교훈
```

**승격 루프 (템플릿과 동형).**

| 전이 | 정량 조건 | 정성 조건 |
| --- | --- | --- |
| 등록(draft) | format.yaml 검증 통과, template_pool 이 실재 | 불필요 |
| draft → pilot | 그 포맷으로 산출물 1건 완주 + 게이트 error 0 | 제작 심의 Go/Conditional-Go |
| pilot → active | 산출물 2건 이상 + 골든 스냅샷 등록 | `format_review` 심의 Go |
| active → deprecated | 2분기 미사용 또는 대체 포맷 active | 정기 심의 |

**재사용 경로.** `wda run --format short-9x16` 한 줄이면 ① 골격·길이 예산이 자동 적용되고 ② 심의 프리셋이 회의 브리핑에 실려 페르소나가 그 장르의 교훈(`lessons`)을 인용할 수 있고 ③ 카피 가이드가 조립·검증에 반영되며 ④ 골든 산출물이 회귀 기준선이 된다. **두 번째 제작부터는 장르 설계가 아니라 콘텐츠 심의만 남는다.**

### 8.2 승격 절차 (정량 + 정성 2단, 크리틱 반영해 단일화)

| 전이 | 정량 조건 (`wda qa`) | 정성 조건 (회의체) |
| --- | --- | --- |
| 등록(draft) | registry 검증 통과, fixture 3종, preview 단독 구동 | 불필요 (등록 자유) |
| draft → pilot | fixtures 전부 게이트 1~6 통과, 골든 스냅샷 등록 | design_review Go/Conditional-Go |
| pilot → active | 실프로젝트 2건 사용(+무위반) **AND** 게이트 7 통과 | design_review Go, 미해결 쟁점 0 |
| active → deprecated | 대체 모듈 active 또는 2분기 미사용 | 정기 심의 의결 |

- 등록 시 module.yaml에서 지식카드를 자동 생성해 색인(설계안 1의 폐쇄 회로) → 이후 회의 브리핑의 known_refs 인용 대상 → QA 페르소나가 레지스트리 대조로 재발명 적발. 보조 수단으로 카드 임베딩 유사도 검사 추가(크리틱 반영).
- 우상향 강제 장치 4개 — ① 실패의 규칙화(실전 결함은 반드시 fixture + 게이트 규칙으로 편입, 규칙은 단조 증가) ② 골든 스냅샷 회귀 ③ 지표 대시보드(게이트 1회차 통과율·모듈 재사용률 80% 목표선) ④ 분기 정기 심의(트리거는 사람 발의 + cron 알림 병행).

---

## 9. 산출물 전략 — 영상 / dc.html / PPTX

### 9.1 HTML → PPT 3안 비교와 단계적 채택

| 기준 | ① 스크린샷 삽입형 | ② 완전 재구성형 | ③ 하이브리드 |
| --- | --- | --- | --- |
| 시각 일치도 | 100% | 낮음~중간 | 배경 100% + 텍스트 근사 |
| 편집 가능성 | 없음 | 완전 | 텍스트만(실무 수요 대부분) |
| 구현 비용 | 최소(P5 seek 재사용) | 최대(이중 유지보수) | 중간 |

- **M1까지 ①로 출하** — 씬별 stills 시각 seek 캡처 → 1920×1080 풀블리드 16:9 PPTX(python-pptx). frame-match 계약 덕에 씬별 1회 seek로 안정 화면 보장. `narration`을 발표자 노트로 삽입해 검색성·접근성을 즉시 보상(크리틱 반영).
- **M3에서 ③ 승격** — 씬 텍스트 요소에 `data-pptx-role="title|body|kicker"` 부여 → Playwright로 텍스트·bbox·폰트 추출(px→EMU) → 배경 캡처 시 해당 요소 숨김 → 같은 좌표에 네이티브 텍스트박스. 승격 전 폰트 대체 매핑 표(Pretendard→시스템 폰트)와 좌표 허용 오차 수치 기준을 정의한다.
- ②는 표현이 단순한 템플릿(stat-trio, step-card-grid)에 한해 동일 데이터 JSON을 소비하는 정적 렌더러로 선택 제공.
- ReportArchive의 `page_slide_ratio` 힌트를 PPTX 페이지 설정에 반영한다.

### 9.2 dc.html 패키지

그 자체로 재생 가능한 산출물(브라우저에서 열면 재생). 배포용은 vendor 인라인으로 오프라인 재생 가능하게 패키징.

---

## 10. LLM·TTS 백엔드 — HWAX 생태계 상속 (사용자 확정 반영)

WebDesignAgents는 LLM도 TTS도 자체 서빙하지 않는다. **HWAXPortal이 쓰는 GLM-5-2 vLLM을 상속받고, VoiceRecorder의 TTS API를 소비하며, HEAXHub 산하 연계 프로젝트로 관리된다.**

### 10.1 vLLM = GLM-5-2 (HWAXPortal 구성 상속)

- **접속 정보(운영)** — `base_url=http://10.198.143.137:10000/v1`(상암 B300, OpenAI 호환), `model=GLM-5-2`, Bearer 키. 정본은 ReportArchive `backend/.env`의 `LLM_BASE_URL/LLM_MODEL/LLM_API_KEY`.
- **상속 절차(HWAXPortal 방식 그대로)** — `HWAXPortal/infra/env-kits/webdesignagents.env` 킷 파일 신규 작성(`LLM_BASE_URL=@FROM_RA:LLM_BASE_URL@` 마커 3종 + `NO_PROXY=10.198.143.137,127.0.0.1,localhost`), `apply-envs.sh`의 MAP 배열에 `[webdesignagents]="WebDesignAgents:.env"` 1줄 추가 후 `bash infra/env-kits/apply-envs.sh webdesignagents` 실행. RA에 값이 없는 dev 박스에서는 키가 스킵되므로 코드 기본값은 로컬 dev vLLM(`http://127.0.0.1:8000/v1`, `qwen2.5-7b-dev`, `docs/start-dev-vllm.sh`)으로 둔다.
- **GLM-5-2 호출 규약(실전 검증된 5원칙 준수)** — ① 스트리밍+tool_calls 조합 금지, 비스트리밍 스위치 제공(`LLM_DISABLE_STREAMING` 패턴) ② reasoning 제어는 `extra_body={"chat_template_kwargs":{"reasoning_effort":...}}` 로만 ③ `max_tokens` 미전송 또는 8192 이상(작으면 thinking 토큰과 겹쳐 JSON 절단) ④ 타임아웃 120~600s ⑤ 구조화 출력은 `response_format={"type":"json_object"}`까지만 신뢰, 400 시 옵션 제거 재시도 폴백. `guided_json`/json_schema는 실사용 실적 0건 — M2에서 raw curl로 서버 지원을 직접 검증하고, 안 되면 프롬프트 JSON 계약 + 파서 재시도(ReportArchive `DELIB_PARSE_RETRIES` 패턴)로 간다.
- **클라이언트 구현** — 공용 패키지가 없으므로 ReportArchive `backend/app/ai/llm.py`(httpx, reasoning_content 파싱, json_object 폴백, 컨텍스트 초과 감지)를 `wdllm/client.py`로 copy-adapt. 이식 출처를 context-notes에 기록.
- **턴당 토큰 예산** — system(페르소나 ~1.5K) + 라운드 지시·최근 턴 gist(~2K) + [F#] fact(~2K) + 출력(~1K) ≈ 6~7K. 14인 4라운드 ≈ 60턴 ≈ 40만 토큰/회의를 상한 예산으로 계측(M2 검증 항목).
- **품질 루브릭(M2 통과 게이트)** — 인용 정확도(known_refs 위반율), 반박 해소율, 판정 재현율(동일 입력 3회), 페르소나 일관성(타인 명의 발화 0건). 경로 A(Claude) 결과를 기준선으로 비교.
- **하이브리드 배치(옵션)** — 발산 라운드(R1)는 GLM-5-2, 반박·판정(R2·R4)만 Claude. orchestrator에 라운드별 백엔드 라우팅 훅.
- **GPU 주의** — dev 박스 로컬 vLLM은 16GB VRAM에 `GPU_MEM_UTIL=0.80` 운용 중. WebDesignAgents 렌더/TTS가 같은 박스 GPU를 쓰면 vLLM 재기동 OOM 위험(`restart-vllm.sh` 좀비 정리 절차 참조).

### 10.2 TTS = VoiceRecorder API 소비 (자체 구현 폐기)

VoiceRecorder(`/home/koopark/claude/VoiceRecorder`)는 이미 완결된 TTS 서비스다 — FastAPI(:8177 운영, `scripts/serve.sh`), 로컬 엔진 3종(Chatterbox 주엔진 GPU/CPU 폴백·MeloTTS·CosyVoice3, 전부 한국어), 참조음성 보이스클로닝(`POST /api/voices` → voice_id), 비동기 합성 잡, ffmpeg atempo 속도 후처리(재합성 불필요).

**연동 계약 (wdrender/tts_client.py).**

1. 씬별 `narration`을 `01 제목 (0:00–0:08) "본문"` 타임코드 형식의 raw_script로 조립 → `POST /api/projects` (engine=chatterbox, language=ko, voice_id).
2. `POST /api/projects/{id}/synthesize` → 202 `{job_id}` → `GET /api/jobs/{job_id}` 폴링.
3. `POST /api/projects/{id}/fit-timecode {max_speed: 2.0}` — 씬 슬롯 자동 정렬(부족분 무음·초과분 배속). `over_budget` 리포트는 게이트 2의 dur 재조정 제안으로 변환.
4. `GET /api/projects/{id}` — 씬별 `duration_sec/start_sec/end_sec/drift_sec`·`total_sec` 수신 → 씬 nat 스트레치 판단.
5. `GET /api/projects/{id}/export/audio`(병합 mp3) + `/export/srt`(자막) → ffmpeg 먹싱, SRT는 자막 트랙 재사용.
6. 사용 후 `DELETE /api/projects/{id}` 정리(호출자 책임).

**경로 규약** — HEAXHub 연방이 정식화되면 Caddy 경유 `http://127.0.0.1:4180/apps/voice_recorder/api/*` + PAT Bearer가 정석(포트 직타는 인증 우회라 금지). 그 전 개발 단계에서는 동일 호스트 `http://localhost:8177` 직결 허용. `WDA_TTS_BASE_URL`로 전환.

**VoiceRecorder 측 추가 필요(PR로 제출)** — 원샷 stateless TTS 엔드포인트. 시나리오 빌드 단계(게이트 2)에서 프로젝트 생성 없이 문장 단위 실측 길이를 얻기 위함. 그 외(인증·CORS)는 HEAXHub Caddy forward_auth가 담당하므로 앱 수정 불필요.

### 10.3 데이터 거버넌스

ReportArchive는 사내 보고서다. 민감 보고서는 경로 B(폐쇄망 GLM-5-2) 전용으로 강제하는 `WDA_LOCAL_ONLY` 플래그를 둔다. **vLLM 오프로드는 비용 절감이자 보안 요건이다.** TTS도 전 엔진 로컬이라 폐쇄망 정합.

---

## 11. 사람 개입 지점 (HITL 5개, 크리틱 반영)

| # | 지점 | 구현 |
| --- | --- | --- |
| 1 | 참가자 확정 | 기존 needs_confirmation 2단계 흐름 |
| 2 | 시나리오 확정 | R4 판정 후 ScenarioDoc 승인(MCP needs_confirmation / CLI 프롬프트) |
| 3 | 출하 승인 | mp4/PPTX 최종 HITL 게이트 |
| 4 | Conditional-Go 액션아이템 이행 확인 | action_item 체크 후 재심의 소집 |
| 5 | 골든 스냅샷 갱신 승인 | 의도된 시각 변경 커밋에 회의록 링크 필수 |

무인 모드(경로 B 배치)에서는 ①라우터 top-N 자동 채택 ②검증기 통과 시 자동 확정 ③산출물을 `pending_review/`에 두고 사후 통지로 대체한다. **사람 편집 왕복 루프** — 사람이 scenario.json 또는 씬을 수정하면 `wda qa` 재실행 → 변경 요약과 함께 재심의(design_review) 소집 또는 직접 재렌더를 선택하는 `wda revise` 명령을 M1에 포함한다.

---

## 12. 저장소 구조 · 가상환경 · 패키징

### 12.1 모노레포 레이아웃

```text
WebDesignAgents/
├─ pyproject.toml                # requires-python >= 3.12, 콘솔 스크립트 wdmcp/wda
├─ uv.lock                       # 커밋 (완전 재현)
├─ .python-version               # 3.13
├─ .venv/                        # uv venv --python 3.13 (생성 완료, git 제외)
├─ .env.example                  # WDA_ 접두 환경변수 견본
├─ .mcp.json.example             # {"type":"stdio","command":".venv/bin/wdmcp", ...}
├─ PLAN.md  checklist.md  context-notes.md
├─ configs/{render.toml, vllm.toml}
├─ src/
│  ├─ wdcore/                    # 심의 엔진 코어 (expertcore 이식, LLM 무호출)
│  ├─ wdmcp/                     # 경로 A — FastMCP stdio 어댑터
│  ├─ wdllm/                     # 경로 B — vLLM 오케스트레이터
│  ├─ wdpipeline/                # P0~P3 (ingest/fragmentize/scenario/prompts)
│  ├─ wdrender/                  # P4~P5 (entry_generator/exporter_video/exporter_pptx/tts/server)
│  ├─ wdqa/                      # 품질 게이트 7종 (정적+런타임, Playwright 하네스)
│  └─ wdweb/                     # 웹 콘솔 백엔드 — FastAPI, HEAXHub 3계약 준수
├─ frontend/dist/                # 웹 콘솔 SPA (무번들러 정적 — fastapi_react 스택 규약)
├─ personas/                     # {persona_id}/persona.yaml SSOT + cards/*.md
├─ modules/                      # §8 모듈 레지스트리
├─ web/
│  ├─ runtime/                   # animations-v2.jsx, support.js (무수정 원본)
│  ├─ vendor/                    # React/ReactDOM UMD, @babel/standalone (커밋)
│  └─ fonts/                     # Pretendard (오프라인 렌더용)
├─ tools/omx-qa/                 # 정적 AST 게이트 (Node 격리, 자체 package.json)
├─ data/                         # 산출물 (git 제외) — meetings/ pipeline/ build/ renders/
└─ tests/
```

- 저장소 전략 — ExpertAgents 포크가 아니라 **신규 저장소에 wdcore를 이식(copy-adapt)** 한다. 근거는 카테고리·artifact enum·minutes 후처리 등 코어 수정이 불가피하고(설계안 1 §4.2), 도메인 지식(631 전문가)은 전혀 필요 없기 때문이다. 이식 시 원본 파일 경로를 context-notes에 기록해 업스트림 개선 역이식 경로를 남긴다.

### 12.2 Python — uv + 전용 venv (확정)

- **Python 3.13.11 전용 가상환경 `.venv` 생성 완료**(`uv venv --python 3.13`). 시스템 python3(3.10)과 완전 분리. 모든 실행은 `uv run` / `.venv/bin/` 경유, 전역 pip 설치 금지.
- `pyproject.toml` — `requires-python = ">=3.12"`, 의존성은 uv.lock으로 잠금.

```toml
[project]
name = "webdesignagents"
requires-python = ">=3.12"
dependencies = ["pydantic>=2.7", "pydantic-settings", "structlog", "PyYAML", "typer", "httpx"]

[project.optional-dependencies]
mcp    = ["mcp>=1.0"]
llm    = ["openai>=1.0"]
render = ["playwright", "python-pptx", "pillow"]
rag    = ["qdrant-client", "FlagEmbedding"]   # M2 이후 — 그 전엔 FakeEmbedder 패턴

[project.scripts]
wdmcp = "wdmcp.server:main"
wda   = "wdpipeline.cli:app"
```

- 임베딩은 ExpertAgents의 FakeEmbedder 패턴(`WDA_FAKE_EMBEDDER`)으로 M2까지 지연 — 회의 엔진은 임베딩 없이 완전 동작함이 원본에서 검증됨.
- ffmpeg는 시스템 의존으로 기동 시 존재 검사(현재 4.4.2 설치 확인).

### 12.3 Node — 무번들러 + vendor 커밋 + dev 도구 격리

- 렌더 런타임에 Node 빌드 체인 없음(빌드 스텝 없는 즉시성 = LLM 생성 씬 즉시 실행). React/Babel은 `web/vendor/` 파일 커밋 + `__resources` 주입으로 CDN 의존 제거.
- 유일한 Node 사용처는 `tools/omx-qa/`(정적 AST 린트, Node 20 확인됨) — dev 전용, 자체 package.json으로 격리, Python이 subprocess로 호출.

### 12.4 렌더 노드 패키징 — Apptainer SIF (크리틱 반영)

- ReportArchive와 동일한 SIF 폐쇄망 운영에 정합시킨다. SIF에 chromium 바이너리(`PLAYWRIGHT_BROWSERS_PATH` 사전 배포 — 현재 호스트에 chromium 캐시 확인됨), ffmpeg, Pretendard 폰트, `web/vendor/`를 내장해 **외부 egress 0으로 렌더 가능**하게 한다. M3 검증 항목.

### 12.5 HEAXHub 산하 연계 프로젝트 등록 (사용자 확정 반영)

WebDesignAgents는 VoiceRecorder와 마찬가지로 HEAXHub(`/home/koopark/claude/HEAXHub`, Caddy :4180 + FastAPI :4040) 산하에서 관리한다.

- **등록** — `HEAXHub/integrations/web_design_agents/.portal/manifest.yaml` 1파일(schema v2)로 끝. `build.stack: fastapi_react`(웹 콘솔 `wdweb` + `frontend/dist` 가 이 규약의 실체), `launch.mode: service`, `health_check.path: /api/health`, `source: {type: git, url: https://github.com/squall321/WebDesignAgents, ref: main}`. 스캐너가 5분 주기로 자동 발견 → SIF 빌드 → `/apps/web_design_agents/` 서브경로 서빙. 단축 경로는 `scripts/register-repo.sh web_design_agents <git-url> fastapi_react`.
- **웹 콘솔(wdweb)** — 보고서 JSON 붙여넣기 → 파이프라인 단계 실행·진행 표시 → 브라우저 프리뷰(영상 엔트리 iframe 재생) → 렌더/QA 실행 → mp4·PPTX 다운로드 + 실행 이력·모듈 갤러리·회의록 뷰어. API 는 `{success, data, message}` 봉투, 프런트는 상대경로 fetch(서브패스 프록시 대응).
- **런타임 3계약** — ① `127.0.0.1:$PORT`로만 listen(0.0.0.0 금지 — 인증 게이트 우회 차단) ② `uvicorn --root-path $ROOT_PATH`(=/apps/web_design_agents) ③ 쓰기 데이터는 `$HEAX_DATA_DIR`(/data) 아래에만(SIF rootfs는 읽기 전용) — `data/` 산출물 경로를 `WDA_DATA_DIR=$HEAX_DATA_DIR` 로 매핑.
- **MCP 노출 = Claude 연동** — manifest에 `mcp: {expose: true, path: /mcp, transport: streamable_http}` 선언 + status beta 이상이면 HWAX MCP Gateway(:9110)가 자동 흡수 → 포탈 챗과 개인 Claude에서 즉시 사용. 즉 **wdmcp는 이중 노출**이다 — ① 로컬 개발용 stdio(.mcp.json, Claude Code 직결) ② HEAXHub 연방용 streamable-http(`/mcp` 경로, 게이트웨이 경유).
- **서비스 간 호출** — WDA→VoiceRecorder는 Caddy 경유 `/apps/voice_recorder/api/*` + PAT Bearer(pat_service)가 정석. PAT 발급·수명 정책은 HEAXHub `docs/app-base-and-pat/` 기준으로 확정 필요.
- **선행 조건** — ① WebDesignAgents git 저장소 생성·push(현재 계획 문서만 존재, HEAXHub는 git source 필수·사설 저장소 토큰 인증 미지원이므로 공개 repo 또는 사내 미러) ② HEAXHub python 스택이 3.12 고정이므로 `requires-python >= 3.12` 유지가 필수(3.13 전용 문법 금지). 로컬 개발 venv는 3.13, SIF 빌드는 3.12 — 둘 다 지원하는 코드로 작성 ③ VoiceRecorder manifest는 status draft — 서비스 확정 시 beta 승격 필요(MCP 노출·무인증 통과 조건).
- **장시간 잡** — 영상 렌더·심의는 service 모드 동기 HTTP로는 타임아웃 위험 → 기존 설계(render_submit 잡 큐 + render_status 폴링)가 이 제약과 정합. HEAXHub job_runner 모드 병행은 M3에서 검토.

---

## 13. 마일스톤

### M0 — 수동 파이프라인 검증 (export 먼저)
- 범위 — 기존 `HWAX 소개영상.dc.html` 7씬을 대상으로 exporter_video / exporter_pptx(①안) 프로토타입. 심의는 수동.
- 검증 — ① mp4 길이 = Σdur ±0.1s ② 씬 경계 frame-match 확인 ③ 폰트 일치 ④ 동일 입력 2회 렌더 perceptual diff 임계 이내(같은 머신은 해시 일치) ⑤ PPTX 슬라이드 수 = 씬 수(+다단 페이즈 stills).

### M1 — MCP 심의 경로 + 반자동 생성
- 범위 — wdcore 이식, 페르소나 14인 yaml, wdmcp 서버(툴 11종), P0~P5 연결(P0는 ReportArchive REST 실연동), `wda revise` 왕복 루프, 게이트 1~6.
- 검증 — ① 전 페르소나 pydantic 검증 통과 ② 회의 3유형 완주 + minutes 생성 ③ known_refs 위반 거부 테스트 ④ 재시작 후 회의 resume ⑤ **ReportArchive에서 복붙한 보고서 JSON 1편(모드 1) → 심의 → scenario.json → mp4+PPTX end-to-end 1회**.

### M2 — vLLM 무인 심의 경로
- 범위 — wdllm 오케스트레이터(guided_json + repair), 모델 A/B 선정, 품질 루브릭 계측, 하이브리드 라우팅 훅, VLM 도입 결정, RAG 도입 판단.
- 검증 — ① 경로 A/B 산출물 스키마 동일 ② 무인 완주율 8/10 ③ **품질 루브릭(인용 정확도·반박 해소율·판정 재현율·페르소나 일관성) 기준선 대비 리포트** ④ 페르소나 격리 린트 0건 ⑤ 회의당 토큰·시간 상한 준수.

### M3 — 완전 자동 + 고급화
- 범위 — `wda run <report_id>` 단일 명령 무개입 완주, 단계 재시도·재개, TTS 먹싱, 하이브리드 PPTX(③), SIF 오프라인 렌더 노드, 모듈 승격 루프 실가동.
- 검증 — ① 신규 보고서 3편 무개입 완주 ② egress 0 렌더 성공 ③ 하이브리드 PPTX 텍스트 편집 가능 + 좌표 오차 기준 이내 ④ 단계 실패 주입 후 재개 ⑤ 모듈 신규 등록→pilot 승격 1건 실증.

---

## 14. 요구사항 추적 매트릭스

| 요구 | 설계 절 | 검증 마일스톤 |
| --- | --- | --- |
| R1 페르소나 회의체로 zip 수준 자료 생성 | §5, §6 | M1-⑤ |
| R2 MCP + vLLM 이중 백엔드 | §3, §10 | M1-②, M2-①② |
| R3 HTML→PPT 동일 외관 변환 | §9 | M0-⑤, M3-③ |
| R4 스택 모듈화 + 품질 보장 조합 | §6, §7 | M0-②④, M1(게이트) |
| R5 심의→모듈 승격 성장 루프 | §8 | M3-⑤ |
| R6 ReportArchive 입력 1순위 | §2.3, §4 P0~P1 | M1-⑤, M3-① |
| R7 가상환경 패키징 | §12 | M0(venv 완료), M3-② |
| R8 전체 계획 md | 본 문서 | 완료 |

---

## 15. 리스크와 대응

| 리스크 | 대응 |
| --- | --- |
| vLLM 소형 모델의 한국어 심의 품질 | M2 품질 루브릭 계량 + 하이브리드 배치(발산=vLLM, 판정=Claude) + 폴백은 경로 A |
| vLLM structured output 버전 편차 | vllm.toml에 버전·파라미터 호환 매트릭스 고정 |
| 하이브리드 PPT 폰트 부재 시 좌표 붕괴 | ①안 우선 출하, ③ 승격 전 폰트 대체 매핑 표 + 오차 수치 기준 |
| 머신 간 프레임 해시 불일치 | perceptual diff 임계값 기준(§7), 해시 일치는 동일 머신 회귀에만 |
| OM_SCENES 16KB 초과 | 주입 축약형(name/dur/nat/stills/tpl만) 규칙 고정 |
| Playwright 설치와 오프라인 렌더 모순 | SIF에 브라우저 사전 내장(PLAYWRIGHT_BROWSERS_PATH) |
| 회의 비용 폭주 | 회의당 토큰·시간 상한 + 참가자 5~8인 기본 + 델타 페르소나 전달 |
| 사내 보고서 외부 API 반출 | WDA_LOCAL_ONLY 플래그로 민감 보고서는 경로 B 전용(§10) |
| ExpertAgents 코어 수정에 따른 하위 호환 | enum 확장 마이그레이션 스크립트 + 이식 출처 기록 |
| GLM-5-2 스트리밍 tool_calls 유실(vLLM 0.23.0) | 비스트리밍 모드 기본(§10.1 규약 ①), guided_json은 M2 실검증 전 미신뢰 |
| VoiceRecorder 합성 워커 1개(직렬) | 영상 다편 동시 생성 시 대기열 — 배치 스케줄러가 TTS 잡을 선행 발주, 우선순위 필요 시 VoiceRecorder 측 후속 PR |
| HEAXHub 스택 python 3.12 고정 | `requires-python >= 3.12` 유지, 3.13 전용 문법 금지(로컬 3.13·SIF 3.12 이중 검증) |
| dev 박스 GPU 경합(vLLM 0.80 점유 + TTS/렌더) | 렌더는 CPU(Playwright), TTS는 Chatterbox CPU 폴백 허용, GPU 작업 직렬화 |

---

## 16. 쟁점 현황

**해소됨 (2026-07-25 사용자 확정).**

- ~~TTS 엔진~~ → **VoiceRecorder API 소비**(§10.2). 게이트 2 낭독 속도 기준은 VoiceRecorder 실측 `duration_sec`으로 대체 — 추정식은 사전 검증용으로만 사용.
- ~~vLLM 모델/자원~~ → **GLM-5-2, HWAXPortal env-kits 상속**(§10.1). dev는 로컬 Qwen vLLM.
- ~~git 저장소 위치~~ → **`https://github.com/squall321/WebDesignAgents`** (HEAXHub manifest의 source.git으로 사용).
- ~~ReportArchive 접속 정보~~ → 1차는 **복붙 모드(P0 모드 1)** 라 불필요. 실연동(모드 2)을 켜는 M3+ 시점에 다시 확인.

**미해결 (사용자 결정 필요).**

1. **접근성(AX) 권한 수준** — 조건부 거부권(초안) vs TD급 절대 거부권.
2. **대비 기준 수위** — WCAG AA 4.5:1 전면 vs 대형 텍스트 3:1 완화(영상 시청 거리 감안).
3. ~~편집기 연동(write-back) 필요 여부~~ → **순수 HTML 엔트리 확정**(2026-07-25). support.js dc.html 편집 레이어는 도입하지 않는다 (M0 export 는 읽기 전용 엔트리 기준). 필요 시 나중에 모듈로 승격.
4. **서비스 간 PAT 정책** — WDA→VoiceRecorder 호출용 서비스 계정 PAT의 수명·권한 범위(HEAXHub `docs/app-base-and-pat/` 기준).
5. **VoiceRecorder 내레이터 기본 음성** — 참조음성(3~10초 wav + 전사) 등록 필요. 누구 목소리로 할지.

---

## 부록 A. 원천 분석 자료

워크플로우 산출물(에이전트별 상세 분석·설계·크리틱 원문)은 세션 스크래치패드 `wf_results/`에 보관. 주요 원전 문서.
- 시나리오 자동화 스펙 — zip 내 `시나리오-구성-방법론.md`
- 회의 엔진 설계 — ExpertAgents `docs/02-design/04-meeting-engine.md`
- ReportArchive 위젯 스키마 — `backend/app/widgets/registry.py`
- ReportArchive 헤드리스 export 설계(미구현) — `docs/[미구현] 헤드리스_내보내기_설계.md`
