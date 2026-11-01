# WebDesignAgents 실행 체크리스트

PLAN.md의 마일스톤을 실행 단위로 분해. 완료 시 체크하고, 검증 결과는 context-notes.md에 기록.

## 사전 준비 (완료분 포함)

- [x] 참조 자산 분석 — ExpertAgents / 소개영상 zip 스택 / ReportArchive 입력 계약
- [x] Python 3.13 전용 가상환경 생성 (`uv venv --python 3.13` → `.venv`)
- [x] 전체 계획서 작성 (PLAN.md)
- [x] 연계 구조 분석 — HEAXHub / HWAXPortal(GLM-5-2) / VoiceRecorder, 계획 반영 (PLAN.md §10, §12.5)
- [x] VoiceRecorder 원샷 TTS API PR 제출 — [VoiceRecorder#1](https://github.com/squall321/VoiceRecorder/pull/1) (머지됨 bb15c15 — 결정 18)
- [x] git 저장소 확정 — <https://github.com/squall321/WebDesignAgents> / ReportArchive는 복붙 모드 우선
- [ ] 미해결 쟁점 사용자 결정 (PLAN.md §16) — write-back=순수HTML **확정(2026-07-25)**. 잔여 4건: AX 권한(M1)·대비 기준(M1)·PAT 정책(M3)·내레이터 음성(M3)

## M0 — 수동 파이프라인 검증 (export 먼저)

- [x] `pyproject.toml` + `uv.lock` 생성, `uv sync` (render extra 포함)
- [x] `web/runtime/`에 zip의 animations-v2.jsx·support.js 원본 배치, `web/vendor/`에 React/ReactDOM UMD·Babel standalone 커밋
- [x] 로컬 정적 http 서빙 스크립트 (`wdrender/server.py` — StaticServer)
- [x] `exporter_video.py` — 3단계 대기 → sync seek 루프 → PNG → ffmpeg (길이=Σdur±0.1s 검증은 test_wdrender_smoke)
- [x] `exporter_pptx.py` ①안 — stills seek 캡처 → 16:9 풀블리드 (슬라이드수=씬수 검증 포함)
- [x] narration 발표자 노트 삽입 (cli 가 scene-data narration→notes 연결)
- [x] **결정성 검증** — verify_render_determinism 하네스 + 실측(2160프레임 중 14만 서브픽셀 차, max_diff_ratio 0.000002 ≪ 0.02) 확정
- [x] frame-match 씬 경계 픽셀 diff 확인 (gate7 + data/renders 경계 PNG 실산출)
- [x] Pretendard 폰트 로컬화 — web/fonts/PretendardVariable.woff2(2MB) + build.py @font-face 로컬 인라인, out_dir/fonts 복사. CDN 의존 제거(결정성·egress-0)

## M1 — MCP 심의 경로 + 반자동 생성

- [x] wdcore 이식 (engine/templates/minutes/store/models) + artifact enum 확장(scene_draft/scenario_patch/module_candidate) + 마이그레이션
- [x] 카테고리 8종 교체 + `scenario_build`/`module_review` 템플릿 추가
- [x] 페르소나 14인 persona.yaml 작성 → `wda validate` 통과
- [x] 모션 문법·디자인 원칙 지식카드 작성 (창작 모드의 인용 근거)
- [x] ScenarioDoc 모델·검증기 (ssParse/ppParse 제약 이식, stills 기본값 = schedule 마지막 등장 + 0.8s)
- [x] wdmcp 서버 — 봉투 + claude_instructions + 툴 11종 (pydantic 입출력 스키마 부록 확정)
- [x] delivered_modules 원장 (모듈 축약 인덱스 브리핑, full/recall 델타 — 토큰 최소화)
- [x] P0 ingest 모드 1 — 복붙 JSON 파일(`report_archive_draft_v1`) 파서 + 블록 구조 보존 정규화 + search_text 자체 생성 (픽스처: examples/reportarchive/report_sample.json)
- [x] P1 fragmentize — 위젯 타입별 매핑 + known_refs 연결
- [x] P4 entry_generator — 순수 HTML 엔트리 + 주입 축약형(16KB 규칙)
- [x] 씬 템플릿 7종 시딩 (tpl.opening~closing, schedule(data)·fixtures 3종·preview 포함)
- [x] 시각 은유 9종 추출 (window.OMX.metaphors.*)
- [x] 디자인 토큰 3층 + OM_THEME 주입 채널
- [x] 품질 게이트 1~7 (Python 구현 — 정적+런타임). Node omx-qa AST 린트는 미착수(선택)
- [x] 사람 편집 왕복 루프 — 웹 콘솔 대화 패널로 구현(CLI revise 대신, 상위 호환)
- [x] 회의 3유형 완주 + known_refs 위반 거부 테스트 + resume 테스트
- [x] **E2E — 복붙 보고서 JSON 1편(모드 1) → 심의 → scenario.json → mp4 + PPTX**

## M2 — vLLM 무인 심의 경로 (GLM-5-2)

- [x] env-kits 상속 — 킷 작성 + MAP 추가 + dev 박스 적용 확인 (HWAXPortal 8deefb0)
- [x] `.env` 의 LLM_* 가 wdllm 에 닿게 — 안 그러면 cae00 에서 조용히 dev 폴백→Errno 111
- [ ] cae00 실연결 검증 — apply-envs.sh 실행 후 실제 GLM-5-2 호출 1건 (사용자 작업)
- [x] wdllm/client.py — ReportArchive `backend/app/ai/llm.py` copy-adapt (json_object 폴백·reasoning_content 파싱·비스트리밍)
- [ ] GLM-5-2 guided_json/json_schema 서버 지원 raw curl 실검증 (미지원 시 프롬프트 JSON 계약 + 파서 재시도)
- [x] wdllm 오케스트레이터 — 턴 루프 + 구조화 출력 + repair 1회 + 페르소나 격리
- [ ] 하이브리드 라운드 라우팅 훅 (발산=vLLM, 판정=Claude 옵션)
- [ ] 품질 루브릭 계측 — 인용 정확도·반박 해소율·판정 재현율·페르소나 일관성 (경로 A 기준선 대비)
- [~] 무인 완주율 — FakeLLM 완주 검증 완료, 실 GLM-5-2 완주율 측정은 cae00 필요
- [ ] 회의당 토큰·시간 상한 계측 (~40만 토큰/회의 예산 검증)
- [ ] VLM 도입 여부 결정 (경로 B 시각 심의 채널)
- [ ] RAG(Qdrant+BGE-M3) 도입 판단 (그 전엔 WDA_FAKE_EMBEDDER)
- [ ] WDA_LOCAL_ONLY 플래그 (민감 보고서 경로 B 강제)

## 웹 콘솔 (HEAXHub 등록의 전제)

- [x] wdweb 백엔드 — FastAPI, HEAXHub 3계약(127.0.0.1:$PORT·--root-path·/api/health), 파이프라인 잡 실행 API
- [x] frontend/dist SPA — 보고서 붙여넣기→진행 표시→프리뷰 재생→렌더/QA→다운로드 + 이력·모듈 갤러리·회의록
- [x] Playwright 실브라우저 검증 + 경로 탈출·오입력 공격 방어

## 조합 라운드 (2026-07-26 완료분)

- [x] 창작 모드 실증 — 신규 템플릿 3종(dataviz/timeline/compare) + module_review 심의 승격
- [x] 대화형 제작 패널 — 대화→액션→검증→재빌드→프리뷰 갱신 (로컬 vLLM 실호출)
- [x] P6 아카이브 역기록 — 제작기록 보고서 생성 + 왕복 무결성 실증
- [x] docs/UI_PRINCIPLES.md — 인터페이스 품질 7항 상시 원칙
- [ ] 재심의 v2 최종본 — 신규 템플릿 채택 + TTS 실측 반영(90→78초) + 음성 먹싱
- [ ] 콘솔 UI 심의 라운드 — design_review 판정 + 개보수

## M3 — 완전 자동 + 고급화

- [ ] `wda run <report>` 단일 명령 무개입 완주 (신규 보고서 3편)
- [ ] P0 ingest 모드 2 — ReportArchive REST/MCP 실연동 (JWT + X-Workspace-Slug, file_id 자산 캐시, .env 접속 정보 확정)
- [x] 파이프라인 단계 재시도·재개 — wda resume · POST /api/runs/{id}/resume · 실패 주입 테스트 자동화
- [x] tts_client — VoiceRecorder 프로젝트 생성→합성→fit-timecode→duration_sec 수신→mp3+SRT (사용 후 프로젝트 삭제. ±15% 판단은 이때 없었고 2026-10-24 내레이션 단계에서 구현 — 결정 56)
- [ ] 내레이터 참조음성 등록 (POST /api/voices → voice_id)
- [x] HEAXHub 등록 — `integrations/web_design_agents/.portal/manifest.yaml` (mcp: expose 포함) + 런타임 3계약($PORT/$ROOT_PATH/$HEAX_DATA_DIR) 준수 + status beta 승격
- [ ] VoiceRecorder manifest status draft → beta 승격 (HEAXHub 쪽)
- [x] PDF 숫자 검색·복사 (tnum 제거 + 숫자 열 우측 정렬 + 부록 번호 텍스트화 — PUA 109→0)
- [x] 하이브리드 PPTX ③ 승격 — 기본 모드가 hybrid. 좌표 허용 오차 기준 정의(미덮힘 ≤0.5%, 실측 0.027%)
      + verify 옵션 + 네 창구 모두에 pptx_mode 노출
- [ ] Apptainer SIF 렌더 노드 (chromium·ffmpeg·Pretendard·vendor 내장) — egress 0 렌더 검증
- [x] 골든 스냅샷 회귀 CI — .github/workflows/ci.yml (전체 테스트 + 재현력 3층 별도 잡).
      임계를 frame_match 에서 분리(0.02→0.002)해 1px 변경도 잡는다. 실패는 환경/회귀/비결정성으로 구분해 보고.
- [x] 7게이트 CI 편입 — `wda qa` 신설(CLI 에 없었다) + CI 가 커밋된 시나리오로 빌드해 게이트 실행
- [x] 포맷 승격 루프 실가동 — wide-16x9 pilot→active (format_review 4인 14턴, Conditional-Go).
      심의를 열려면 포맷이 인용 가능해야 했다(meeting_start format_id). 승격 검사에 등식 3개 편입.
- [x] short-9x16 active 승격 — short_v2 완주(게이트 클린) + format_review 14턴 Conditional-Go
- [x] 브리핑이 템플릿 스키마 구조 제약 적재 (개수·x-read) — 직관이 실측을 이기던 것을 막는다
- [x] 모듈 승격 루프 실가동 — promote_module 신설(없었다) + vtpl.stack draft→pilot (module_review 14턴 Go)
- [ ] 모듈 active 승격 조건 2종 — schema.json 유효성 · 배열 상한 근거 (module_review 이월)
- [x] 지표 대시보드 — 게이트 1회차 94.7% · 모듈 재사용률 87.4%(목표 80% ✓) · 심의 토큰 4800/회의.
      네 창구 노출(wda metrics · metrics_report · GET /api/metrics · 콘솔 지표 탭)
- [x] HITL 5지점 승인 원장 + 무인 모드 자동 확정 규칙 (골든은 무인 예외 — 사람만)
- [x] 골든 갱신 강제 — --reason 필수, 이유가 골든 옆 golden.json 에 이력으로 남음
- [ ] HITL 강제 지점 확대 — 현재 골든만 실제로 막는다. 출하·시나리오는 원장만 있고 차단은 없음
- [x] `wda revise` — 사람 편집 왕복 루프 (변경 대조 + --rebuild/--review 선택, 차단 없음)
- [x] `wda revise` 창구 대칭 — scenario_revise · GET /api/runs/{id}/revise · 콘솔 편집 확인

## 2026-08-28 — MCP·웹 기능 대칭 (사용자 지시: "둘다 모든 기능이 있어야지")

두 호출 경로가 같은 플랫폼의 두 창구인데 창구마다 되는 일이 달랐다. 전수 대조로 결여를 메운다.

### 웹에 없던 것
- [x] `POST /api/meetings` — 심의 개회 (meeting_start 사영)
- [x] `GET /api/meetings/{id}/briefing` — 다음 발언자 브리핑
- [x] `POST /api/meetings/{id}/turns` — 턴 제출
- [x] `GET /api/meetings/{id}` — 심의 상태
- [x] `POST /api/meetings/{id}/close` — 폐회
- [x] `POST /api/meetings/{id}/scenario` — 심의 산출물 → 시나리오 (scenario_build 사영)
- [x] `POST /api/meetings/{id}/autorun` — vLLM 무인 완주 (웹 전용 경로, 계획 외 추가)
- [x] `POST /api/runs/{id}/render` 에 `doc_style`
- [x] 기본 targets 원복 — 문서 3형식을 기본에 넣으면 영상 한 번 뽑자고 5종을 다 굽는다
- [x] 문서 3종 다운로드 경로 (작업 중 발견 — 열람 URL 은 주는데 받을 수 없었다)
- [x] 콘솔 UI — 산출물 갈래·문체 선택, 심의 개회·상태판·자율 실행·폐회

### MCP 에 없던 것
- [x] `module_list` — 모듈·템플릿 카탈로그 (웹 GET /api/modules 사영)
- [x] `meeting_list` — 회의 목록
- [x] `meeting_minutes` — 회의록 열람

### 검증
- [x] 대칭 계약 테스트 — 능력 18종 × (MCP 도구, 웹 라우트) 표. 타깃·문체 집합 일치,
      열람 URL 을 주는 모든 타깃이 다운로드 가능한지도 함께 막는다
- [x] 웹 REST 만으로 심의 왕복 — 개회→브리핑→턴→상태→재브리핑(원장 full→recall 확인)
- [x] 콘솔 브라우저 완주 — 개회→상태판→폐회→회의록, 콘솔 오류 0
- [x] 전체 2300 passed, 8 skipped

## 2026-10-24 — 내레이션 파이프라인 연결 (사용자 지시: "내레이션 파이프라인 연결")

tts_client·mux 는 있었지만 어느 창구도 부르지 않았고, 목소리 입힌 영상은 data/ 의 일회용 드라이버로만
만들었다. 실측 길이로 씬을 다시 잡아 렌더하고 음성을 먹싱하는 일을 네 창구에 붙인다. 결정 56~59.

### 핵심
- [x] VoiceRecorder 클라이언트 정비 — `.env` 의 WDA_TTS_* 읽기, PAT Bearer, trust_env=False,
      씬 원문 그대로 측정(파서 우회), 씬 음성 내려받기, 실패해도 프로젝트 정리
- [x] 실측 길이로 dur 재조정 — 하한 nat×0.85, 상한 nat×1.15 를 넘으면 늘리고 경고(결정 56), stills 비례 이동
- [x] 씬 음성을 새 시작 시각에 놓아 내레이션 트랙·자막 조립, 먹싱, drift_report.json
- [x] 실측 길이를 시나리오에 남기고(narration_sec·narration_sha) 게이트 2 가 추정 대신 실측을 쓴다(결정 57)
- [x] 포맷 길이 범위를 넘으면 렌더하지 않고 줄일 씬과 함께 알린다

### 네 창구
- [x] CLI `wda render --narration` · `wda run --narration` (+ `wda run` 이 pptx_mode 를 안 넘겨 죽던 것)
- [x] MCP `render_submit(narration=)` · 잡 원장 · 영상 없는 타깃이면 INVALID_INPUT
- [x] 웹 `POST /api/runs/{id}/render` body.narration · 400
- [x] 콘솔 '내레이션 입히기' 선택 · 결과 요약

### 검증
- [x] 가짜 VoiceRecorder(MockTransport)로 단위·통합 테스트 — 재조정 규칙, 트랙 배치, 먹싱, 세 창구
- [x] 실제 VoiceRecorder(MeloTTS 1.2배)로 실렌더 1편 — delib_v2 7씬 Σ78→84.6초, 무음 6.9%(v1 41.8% · v2 25.2%), 한계 초과 0씬, 24fps 2030프레임+PPTX 8장 3분 42초
- [x] 전체 테스트(2347 passed, 실패 1 = 워크트리에 없는 gitignore 리포트 — main 체크아웃에선 통과) · 문서(PLAN §10.2, voicerecorder-api.md) 갱신

## 2026-11-01 — 포털 연계 (메인 심의=포털 · 발표자료=우리)

### A. cae00 VLM
- [ ] `wdllm` 메시지 구조를 블록 배열로 — 지금은 `content: str` 이라 이미지를 못 싣는다
- [ ] 이미지 첨부 헬퍼 (씬 스틸 PNG → data URL 블록)
- [x] 비전 모델 — **기존 GLM 그대로**(사용자 확정 2026-11-01). 별도 모델·엔드포인트 설정이 필요 없다
- [ ] 시각 심의 채널 — 렌더된 씬을 페르소나가 보고 비평하는 라운드
- [ ] cae00 실연결 확인 — env-kits 킷 적용 후 비전 호출 1건 (사용자 작업)

### B. 포털 챗 수신·가시화
- [~] `destApps.ts` 목적지 추가 — 포털 세션(hwaxportal-a5)에 요청 보냄 2026-11-01 (R1~R4)
- [ ] 포털 → WDA 전달 계약 (RA 보고서 또는 심의 결과 → render job)
- [ ] 결과를 챗에 돌려주는 경로 (포털에 `test_chat_ppt_in_browser.py` 선례 있음)
- [ ] 진행 상황 스트리밍 (심의는 `test_delib_stream_in_browser.py` 선례 있음)

### C. 심의 내용의 발표자료화
- [ ] 포털 심의 결과(의사결정문 + viz SVG) → 우리 ingest 어댑터
- [ ] viz_module 의 인라인 SVG 를 씬 자산으로 받는 경로 (지금 위젯은 ReportArchive 38종 기준)
- [ ] 리스크 심사 장르 포맷 (`risk-review` format) — 의사결정 매트릭스·민감도가 주인공인 골격

## 2026-11-01 — 역동 연출 (카메라 워크 · 화면 전환)
- [x] 테마 대응 실측 — 템플릿 40 × 테마 5 = 200 조합 전수 렌더 (15 → 200)
- [x] 카메라 워크 모션 토큰 — hold·pushIn·pullOut·panRight·kenBurns (테마 5종, 세기 차등)
- [x] 카메라를 바인딩 층에 — 템플릿 40종 무수정. 7게이트 클린 실증(delib_v2)
- [x] 전환 정본 = **짝 퇴장/등장**. xfade 는 씬별 세그먼트 렌더가 전제라 타임라인이 밀린다(결정 63)
- [ ] (보류) 영상 전용 xfade — 세그먼트 렌더 + 내레이션/SRT/stills 재계산이 선행 조건
- [x] `transition` 되살림 — 8종 enum(cut·push 4방향·slide 2·dissolve), 앞 씬이 이음매 소유
- [x] frame-match 통과 확인 — 카메라 경계 0.006%, 전환 경계 0.000% (임계 2%)
- [x] 요소 행동 어휘 6종 — countUp·drawIn·revealWord·wake·pulse·float (업계 수치 참조)
- [x] MO-C-003 연출 어휘 카드 — 창작 모드의 도달 경로
- [ ] 어휘를 쓰는 신규 템플릿 1종 — 지금은 창작 모드가 쓸 수 있을 뿐 실적이 없다
- [ ] (검토) stagger row 1.1s vs 업계 0.3~0.4s — 바꾸려면 심의가 필요하다
- [ ] (보류) 필름 룩 — grain 0.04~0.08 · vignette 0.2~0.35. 대비 게이트와 충돌 검토 필요

## 2026-11-01 — 심의 장르 (포털 심의 결과 → 영상)
측정 근거: `wr-20261101-083510-53a9`. 심의 템플릿 보고서(화두·라운드·결정·액션)를 태우니
조각 8건은 전부 정확히 추출되는데, 씬에는 결정문·액션아이템이 **안 들어간다**.
`scenario_build` 가 제품 소개용 7씬 설득 골격에 억지로 끼우고 빈자리를 필러로 채운다.
- [x] 측정 — 심의 보고서 표본 1건 전 구간 실행, 유실 지점 특정 (fragmentize ✅ / scenario_build ❌)
- [x] 섹션 추론 — heading 텍스트 → `section` 태그. **RA 정본 어휘를 따른다**(action_item·
      alternatives·recommendation·constraint·decision). 심의 전용만 신설(topic·round)
- [x] 빌더 6종 신설 — `o-question`·`o-statement`·`o-metric`·`x-next`·`x-quote`·`x-summary`
      (등록·JSX·스키마는 다 있는데 빌더가 없어 **어떤 시나리오도 쓸 수 없던** 템플릿들)
      → 템플릿 40종 전부 조립 경로 확보. 회귀 테스트가 이 불변을 지킨다
- [x] `delib-16x9` 포맷 (status draft) — 골격 `topic→rounds→decision→action→summary` 5씬 56초
      → 결정 수치(1.0mm·0.82mm·2.1%)·액션 담당(구조·열·품질)이 씬 데이터에 존재함을 테스트로 고정
      → 필러("보고서 참조"·"항목 1") 0건, 7게이트 통과(info 1), 5씬 스틸 육안 확인
- [x] 포맷 선택 경로 — 웹 `POST /api/runs {format}` · MCP `scenario_build` 가 회의 format_id 사용
      (종전 MCP 는 format_id 를 브리핑 인용에만 쓰고 **조립에는 안 넘겼다**)
- [x] 포맷 카탈로그 — `GET /api/formats` + MCP `format_list` + `/api/health` features
      (양쪽 어디에도 포맷을 발견할 방법이 없었다. 포털이 심의 단추를 가르는 표지)
- [x] 회귀 — `wide-16x9` 골격 불변 테스트 포함, 전체 테스트 통과
- [ ] pilot 승격 — format_review 심의 + 완주 산출물 (지금은 draft)
- [ ] 쟁점 씬 — 현 골격에 `problem` 역할이 없다. 라운드가 대립을 담지만 쟁점 자체는 안 선다

## 2026-11-01 — 승격 심의 + 포털 계약 W-1~W-15
정본: `/home/koopark/claude/HWAXPortal-wt-1101-wda-deck/docs/wda-deck/wda-request.md` (§11 체크리스트).
사용자 지시 "다 하자"(11-01).

### A. delib-16x9 승격 (draft → pilot → active)
- [x] 산출물 1건 — run wr-20261101-095212-e8ed (영상+PPTX, 게이트 error 0)
- [x] 제작 심의 design_review — 회의 9f6226ac, 6인 20턴 → **Conditional-Go** (조건 7건)
- [x] pilot 승격
- [x] 조건 이행 C-1~C-7 — 테마 적용·회귀 테스트·순서·게이트 재실행·core_message·프리셋·원장 영속화
- [x] 쟁점 역할 신설(O-1) — 골격 5→6씬, 득실 문장이 잘리지 않고 선다
- [x] 산출물 2건째 + 골든 등록 — wr-20261101-122319-7de1 (게이트 error 0 warning 0 **info 0**)
- [x] format_review 심의 — 회의 3efabdb0, 6인 20턴 → **Go** (전원 찬성)
- [x] **active 승격** → health 의 `formats["delib-16x9"] = "active"` — 포털 단추 전제 충족

### B. 포털 계약 (M0 필수 W-1~W-12)
- [x] W-1 `X-Heax-User-Email` → run.owner (본문 owner 칸은 안 믿는다, 대소문자 접음). 202 에 owner
- [x] W-2 **미들웨어 한 곳**으로 run 단위 경로 전부 — 남·익명은 404 NOT_FOUND
      (핸들러 14곳에 흩으면 다음 라우트에서 잊힌다. '전부' 는 구조가 보장해야 한다)
- [x] W-3 `GET /api/runs` = 내 것 + 주인 없는 것
- [x] W-4 MCP 도구 9종 + 렌더잡 내려받기 — run_id·서버 경로 양쪽 판정, NOT_FOUND
- [x] W-5 주인 있는 run id 128비트 + `RUN_ID_RE` 꼴 검사(경로 탈출 차단)
- [x] W-6 health features 7종 + 포맷 표지 + version
- [x] W-7 본문 16MB → 413 TOO_LARGE
- [x] W-8 만들기의 `render` 칸 — 빌드 뒤 이어서 렌더, 재개에도 이어진다
- [x] W-9 `render.requested` · `render.skipped[{target, reason}]`
- [x] W-10 오류 봉투 `code` 6종 + 상태별 기본 매핑
- [x] W-11 내려받기 머리 — attachment·Content-Length·nosniff·HTML 은 CSP sandbox
- [x] W-12 기동 시 끊긴 실행·렌더를 failed(interrupted)

### C. 권장 (W-13~W-15·W-22)
- [x] W-13 보존 기한 + 지운 뒤 410 — **기본 끔(0)**. 사용자 결정(11-01)으로 **꺼 둔다**.
      매니페스트 env 도 넣지 않는다. 포털이 잡 기록을 7일 두고 그 뒤 '기록 없음' 으로 말한다
- [x] W-14 렌더 동시 상한 **2 확정**(11-01 합의). 넘친 요청은 queued 로 대기.
      포털 박스 상한 4 보다 조이지만 박스가 죽는 것보다 낫다 — 실측 뒤 올릴 수 있다
- [x] W-15 `Idempotency-Key` — 같은 키 + 같은 주인이면 같은 run
- [x] W-22 `Authorization`·쿠키를 읽는 코드 없음 — 회귀 테스트가 못박는다

### D. 배포 (2026-11-01 사용자 지시로 내 몫이 됐다 — 정본 P-1 대체)
- [x] push — SSH 경로로 `origin/main = df446ae` (PAT 의 workflow 스코프 제약은 HTTPS 에만 걸린다)
- [x] SIF 재빌드 — push 로 스캐너가 자동 수행(커밋 기반 게이트). 673MB → 676MB
- [x] 라이브 전환 — `redeploy-app.sh web-design-agents`. **빌드만으로는 안 바뀐다**
- [x] 배치본 검증 1회차 — 6씬 64초·렌더 자동 연결·멱등·머리 정상, **소유권 무력 발견**
- [x] root_path 결함 교정 + 실기동 회귀 테스트
- [x] 재push(`38f95d3`) → 재빌드(20:00) → 재전환(port 9499) → **검증 2회차 통과**
      주인 200 / 남·익명 404(하위경로 6종 전부) · 6씬 64초 완주 · W-3·7·8·9·10·11·15 정상
- [ ] 포털이 스위치를 켜고 2절(남의 계정 404·익명 401·남의 목록에 없음) — **알림 보냄, 대기 중**
- [ ] 둘 다 통과하면 Drive push (**포털 세션이 한다** — 그쪽 절차서의 스크립트)
- [ ] cae00 반영 — Drive 뒤 `dist-from-drive` + 같은 redeploy

### 하지 않는 것
- 역사 다시 쓰기(rebase·force) — 문서가 커밋 해시를 인용한다
- 포털 `backend/.env` 의 `WDA_DECK_ENABLED` — 그쪽 설정이다
- W-16~W-20 — M2. W-19(슬라이드 PDF)는 청하지 않기로 결정됨.
