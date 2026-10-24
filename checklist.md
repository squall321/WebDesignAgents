# WebDesignAgents 실행 체크리스트

PLAN.md의 마일스톤을 실행 단위로 분해. 완료 시 체크하고, 검증 결과는 context-notes.md에 기록.

## 사전 준비 (완료분 포함)

- [x] 참조 자산 분석 — ExpertAgents / 소개영상 zip 스택 / ReportArchive 입력 계약
- [x] Python 3.13 전용 가상환경 생성 (`uv venv --python 3.13` → `.venv`)
- [x] 전체 계획서 작성 (PLAN.md)
- [x] 연계 구조 분석 — HEAXHub / HWAXPortal(GLM-5-2) / VoiceRecorder, 계획 반영 (PLAN.md §10, §12.5)
- [x] VoiceRecorder 원샷 TTS API PR 제출 — [VoiceRecorder#1](https://github.com/squall321/VoiceRecorder/pull/1) (머지 대기)
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
- [x] tts_client — VoiceRecorder 프로젝트 생성→합성→fit-timecode→duration_sec 수신→mp3+SRT (±15% nat 스트레치 판단, 사용 후 프로젝트 삭제)
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
