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

- [ ] wdcore 이식 (engine/templates/minutes/store/models) + artifact enum 확장(scene_draft/scenario_patch/module_candidate) + 마이그레이션
- [ ] 카테고리 8종 교체 + `scenario_build`/`module_review` 템플릿 추가
- [ ] 페르소나 14인 persona.yaml 작성 → `wda validate` 통과
- [ ] 모션 문법·디자인 원칙 지식카드 작성 (창작 모드의 인용 근거)
- [ ] ScenarioDoc 모델·검증기 (ssParse/ppParse 제약 이식, stills 기본값 = schedule 마지막 등장 + 0.8s)
- [ ] wdmcp 서버 — 봉투 + claude_instructions + 툴 11종 (pydantic 입출력 스키마 부록 확정)
- [ ] delivered_modules 원장 (모듈 축약 인덱스 브리핑, full/recall 델타 — 토큰 최소화)
- [ ] P0 ingest 모드 1 — 복붙 JSON 파일(`report_archive_draft_v1`) 파서 + 블록 구조 보존 정규화 + search_text 자체 생성 (픽스처: examples/reportarchive/report_sample.json)
- [ ] P1 fragmentize — 위젯 타입별 매핑 + known_refs 연결
- [ ] P4 entry_generator — 순수 HTML 엔트리 + 주입 축약형(16KB 규칙)
- [ ] 씬 템플릿 7종 시딩 (tpl.opening~closing, schedule(data)·fixtures 3종·preview 포함)
- [ ] 시각 은유 9종 추출 (window.OMX.metaphors.*)
- [ ] 디자인 토큰 3층 + OM_THEME 주입 채널
- [ ] 품질 게이트 1~6 (`tools/omx-qa` Node 격리 + Python 런타임 게이트)
- [ ] `wda revise` — 사람 편집 왕복 루프
- [ ] 회의 3유형 완주 + known_refs 위반 거부 테스트 + resume 테스트
- [ ] **E2E — 복붙 보고서 JSON 1편(모드 1) → 심의 → scenario.json → mp4 + PPTX**

## M2 — vLLM 무인 심의 경로 (GLM-5-2)

- [ ] env-kits 상속 — `HWAXPortal/infra/env-kits/webdesignagents.env` 킷 작성 + apply-envs.sh MAP 추가
- [ ] wdllm/client.py — ReportArchive `backend/app/ai/llm.py` copy-adapt (json_object 폴백·reasoning_content 파싱·비스트리밍)
- [ ] GLM-5-2 guided_json/json_schema 서버 지원 raw curl 실검증 (미지원 시 프롬프트 JSON 계약 + 파서 재시도)
- [ ] wdllm 오케스트레이터 — 턴 루프 + 구조화 출력 + repair 1회 + 페르소나 격리
- [ ] 하이브리드 라운드 라우팅 훅 (발산=vLLM, 판정=Claude 옵션)
- [ ] 품질 루브릭 계측 — 인용 정확도·반박 해소율·판정 재현율·페르소나 일관성 (경로 A 기준선 대비)
- [ ] 무인 완주율 8/10 달성
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
- [ ] 파이프라인 단계 재시도·재개 (실패 주입 테스트)
- [x] tts_client — VoiceRecorder 프로젝트 생성→합성→fit-timecode→duration_sec 수신→mp3+SRT (±15% nat 스트레치 판단, 사용 후 프로젝트 삭제)
- [ ] 내레이터 참조음성 등록 (POST /api/voices → voice_id)
- [x] HEAXHub 등록 — `integrations/web_design_agents/.portal/manifest.yaml` (mcp: expose 포함) + 런타임 3계약($PORT/$ROOT_PATH/$HEAX_DATA_DIR) 준수 + status beta 승격
- [ ] VoiceRecorder manifest status draft → beta 승격 (HEAXHub 쪽)
- [ ] 하이브리드 PPTX ③ 승격 — data-pptx-role + bbox 추출 + 폰트 대체 매핑 표 + 좌표 오차 기준
- [ ] Apptainer SIF 렌더 노드 (chromium·ffmpeg·Pretendard·vendor 내장) — egress 0 렌더 검증
- [ ] 게이트 7(frame-match) + 골든 스냅샷 회귀 CI
- [ ] 모듈 승격 루프 실가동 — 신규 창작 모듈 1건 등록→pilot 승격 실증
- [ ] 지표 대시보드 — 게이트 1회차 통과율·모듈 재사용률(80% 목표)·토큰/산출물 추이
- [ ] HITL 5지점 + 무인 모드 자동 확정 규칙 구현
