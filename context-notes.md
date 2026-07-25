# WebDesignAgents 컨텍스트 노트

작업 중 내린 결정과 근거를 시간순으로 누적. 다음 세션(사람/에이전트)이 재도출 없이 이어받기 위한 문서.

## 2026-07-24 — 프로젝트 착수·계획 수립

### 결정 1. Python 3.13 + uv 전용 가상환경
- 사용자 지시 — 시스템 기본 3.10은 구식, 3.12/3.13 사용 + 반드시 가상환경.
- `.venv`를 `uv venv --python 3.13`으로 생성 완료(3.13.11, `/usr/bin/python3.13` 기반). `requires-python >= 3.12`.
- 모든 실행은 `uv run`/`.venv/bin/` 경유. 전역 pip 설치 금지.

### 결정 2. ExpertAgents는 포크가 아니라 copy-adapt 이식
- 카테고리 상수·artifact enum·minutes 후처리 등 코어 수정이 불가피하고, 631 전문가 도메인 지식은 불필요.
- `expertcore → wdcore`로 이식하되 원본 경로를 기록해 업스트림 역이식 경로 유지.
- 무수정 재사용 목록과 수정 목록은 PLAN.md §2.1·설계안 원문(스크래치패드 wf_results/) 참조.

### 결정 3. ReportArchive 입력은 REST API (파일 glob 아님)
- 분석 결과 보고서는 디스크 파일이 아니라 PostgreSQL JSONB. 파일 경로 기반 ingest 설계는 폐기.
- `report_ingest(report_id)` — JWT(`POST /api/auth/login`) + `X-Workspace-Slug` 헤더, `GET /api/reports/{id}`.
- 블록 구조 보존 정규화(마크다운 평탄화 금지) — 위젯 38종 타입 정보가 씬 매핑의 핵심 정보라서.
- 루트의 `report_578_platform_guide.json`은 MCP 초안 페이로드 샘플일 뿐 보고서 저장 포맷이 아님(혼동 주의).

### 결정 4. 세 설계안의 스키마 발산을 단일안으로 통합 (크리틱 반영)
- 시나리오 정본 = 설계안1 ScenarioDoc 루트 + 설계안3 템플릿별 데이터 스키마($defs) + 설계안2 OM_SCENES 주입 축약형(name/dur/nat/stills/tpl만).
- stills 기본값 = `schedule(data)` 마지막 등장 시각 + 0.8s (설계안3 규칙으로 단일화).
- 모듈 레지스트리 = 설계안3 `modules/`+`tpl.*` 정본, 설계안1의 지식카드 자동 생성·재유통 폐쇄 회로를 그 위에 결합.
- 승격 조건 = 정량 게이트 통과 AND design_review Go (양쪽 모두 필요).
- 페르소나 = 14인 로스터 단일안. 모듈 심사는 별도 6종이 아니라 14인의 부분집합(TD·QA·MO·LG+제안자).

### 결정 5. Node 정책 — 런타임 무의존, dev 도구만 격리 허용
- 렌더 런타임은 무번들러(빌드 스텝 없는 즉시성 = LLM 생성 씬 즉시 실행) + `web/vendor/` 커밋 + `__resources` 주입.
- 정적 AST 게이트(omx-qa)만 Node CLI로 `tools/omx-qa/`에 격리(자체 package.json, Python이 subprocess 호출). Playwright는 Python 바인딩.

### 결정 6. PPT 전략 — ① 스크린샷 삽입형 선출하, M3에서 ③ 하이브리드 승격
- frame-match 계약 덕에 stills seek 1회로 안정 화면 보장, 비용 대비 품질 최상.
- ①에서도 narration을 발표자 노트로 삽입(검색성·접근성 보상).
- ② 완전 재구성형은 단순 템플릿(stat-trio, step-card-grid)에만 선택 제공.

### 결정 7. 프레임 비교 기준 이원화 (크리틱 리스크 반영)
- 같은 머신 회귀 = 해시 완전 일치. 머신 간 CI = perceptual diff 임계값(M0에서 실측 확정).
- 폰트 래스터라이즈·GPU·AA 편차로 머신 간 해시 일치는 비현실적.

### 결정 8. TTS를 1차 범위(P5)에 편입 (크리틱 반영 — 무음 영상 방지)
- 합성 실측 길이 ↔ dur 동기는 nat 타임 스트레치 ±15%까지 흡수, 초과 시 dur 재조정 제안 리포트.
- 엔진 선정은 미해결 쟁점(폐쇄망 정합 여부가 관건).

### 결정 9. vLLM 오프로드는 비용 절감이자 보안 요건
- ReportArchive는 사내 보고서 — 민감 보고서는 `WDA_LOCAL_ONLY`로 경로 B(폐쇄망 vLLM) 강제.
- 모델 후보 Qwen3-32B(AWQ)/EXAONE 4.0-32B/폴백 Qwen3-14B. M2에서 품질 루브릭으로 A/B 확정.
- 하이브리드 배치(발산 라운드=vLLM, 반박·판정=Claude)를 중간 단계 옵션으로 설계.

### 결정 10. 저작 2모드 — 창작 모드 / 재사용 모드 (사용자 추가 요구 반영)
- 사용자 요구 — "새 양식·동적 애니메이션 창작을 잘 해야 하고, 이미 한 패턴은 토큰 최소화".
- 재사용 모드(기본) — 레지스트리에 있으면 씬 코드 0토큰, `tpl` 참조 + 데이터 JSON만. 브리핑은 모듈 축약 인덱스 + delivered_modules full/recall 델타.
- 창작 모드(예외) — in_scope 소화 불가 판정 시만 발동. 마이크로 헬퍼 + 모션 문법 지식카드 + motion 토큰이 품질을 받침. 창작물은 게이트+심의 후 레지스트리 등록 → 이후 재사용 모드 소비.
- PLAN.md §6.3에 명문화.

### 진행 기록
- 울트라 코드 워크플로우(wf_ef4dcf43-8f8) — 분석 3 + 설계 3 + 크리틱 1. ReportArchive 리더 1개가 권한 거부로 실패 → 대체 에이전트로 재분석 완료. 원문은 세션 스크래치패드 `wf_results/`에 보관.
- 환경 확인 — uv 0.11.21, Node 20.19.6, ffmpeg 4.4.2, Playwright 1.58(chromium 캐시 있음), python3.13.11.
- 산출 — PLAN.md / checklist.md / context-notes.md(본 문서).

### 미해결 (사용자 결정 대기)
PLAN.md §16의 6건 — TTS 엔진, vLLM GPU 자원, AX 권한 수준, 대비 기준 수위, ReportArchive 접속 정보, write-back 필요 여부.

## 2026-07-25 — HWAX 생태계 연계 확정 (사용자 지시)

### 결정 11. TTS = VoiceRecorder API 소비 (자체 구현 폐기)
- 사용자 지시 — VoiceRecorder를 그대로 활용, HEAXHub에 넣어 관리, API 개방 후 WDA가 가져다 쓰는 연계 구조.
- VoiceRecorder는 이미 완결된 TTS 서비스(:8177) — 프로젝트/씬/잡 API, 씬별 duration_sec, 타임코드 fit(무음/배속 자동 정렬), SRT export, 보이스클로닝. 미해결 쟁점 "TTS 엔진" 해소.
- 부족분은 원샷 stateless TTS 엔드포인트뿐 → VoiceRecorder에 PR 제출. 인증·CORS는 HEAXHub Caddy forward_auth 담당이라 앱 수정 불필요.
- 게이트 2 낭독 속도 추정식은 사전 검증용으로 격하 — 실측 duration_sec이 정본.

### 결정 12. vLLM = GLM-5-2, HWAXPortal env-kits 상속
- 사용자 지시 — GLM 5.2, HWAXPortal에서 쓰는 것을 상속.
- 운영 base_url=http://10.198.143.137:10000/v1, model=GLM-5-2, 키 정본은 ReportArchive backend/.env. 상속은 env-kits @FROM_RA 마커(webdesignagents.env 킷 + MAP 1줄).
- GLM 호출 5원칙(비스트리밍·reasoning_effort는 extra_body·max_tokens 8192↑·타임아웃 여유·json_object까지만 신뢰+400 폴백)을 wdllm에 반영. guided_json은 실적 0건이라 M2에서 raw curl 검증.
- 클라이언트는 ReportArchive backend/app/ai/llm.py copy-adapt (공용 패키지 없음).
- dev 박스는 상암 도달 불가 → 로컬 Qwen2.5-7B vLLM(:8000)이 개발 기본값.

### 결정 13. HEAXHub 산하 연계 프로젝트로 등록
- 등록 = integrations/web_design_agents/.portal/manifest.yaml 1파일. 런타임 3계약(127.0.0.1:$PORT, $ROOT_PATH, $HEAX_DATA_DIR).
- MCP는 이중 노출 — 로컬 stdio(.mcp.json, Claude Code 직결) + manifest mcp:{expose:true}로 HWAX MCP Gateway 자동 흡수(포탈 챗·개인 Claude).
- WDA→VoiceRecorder 호출은 Caddy /apps/voice_recorder/api/* + PAT가 정석(개발 중엔 :8177 직결 허용, WDA_TTS_BASE_URL 전환).
- 주의 — HEAXHub 스택 python 3.12 고정. requires-python >= 3.12 유지, 3.13 전용 문법 금지(로컬 3.13 venv·SIF 3.12 이중 호환).
- 선행 조건 — WDA git 저장소 생성·push 필요(사설 토큰 인증 미지원 → 공개 repo 또는 사내 미러).

### 진행 기록 (추가)
- 연계 분석 워크플로우(wf_1989bc7f-36e) — VoiceRecorder/HWAXPortal/HEAXHub 3 에이전트, 원문은 스크래치패드 wf2_results/.
- VoiceRecorder 저장소 상태 — main에 미커밋 수정 4건(README.md, backend/app/tts/cosy_engine.py, scripts/*) 존재. PR 브랜치는 이 파일들을 건드리지 않는 신규 파일 위주로 작업.

### 결정 14. VoiceRecorder 원샷 TTS API — PR 제출 완료
- https://github.com/squall321/VoiceRecorder/pull/1 (feature/oneshot-tts-api, 5파일 +130줄)
- POST /api/tts(202, 기존 잡 큐 경유 GPU 직렬화 유지) / GET /api/tts/{id}/audio / DELETE /api/tts/{id}. 씬 합성과 동일한 정규화·엔진·속도 경로 재사용, DB 무흔적(jobs.project_id 센티널 "_tts").
- 검증 — py_compile + TestClient 스모크(제출→완료→다운로드→삭제, 400/404/422, 기존 라우트 회귀 없음). 실모델 E2E는 GPU 박스에서 1회 확인 필요.
- 저장소는 main으로 복귀, 사용자 미커밋 수정 4건 무손상.

### 결정 15. 저장소 확정 + ReportArchive는 복붙 모드 우선 (사용자 지시)
- git 저장소 = https://github.com/squall321/WebDesignAgents (초기화·푸시 완료, HEAXHub source.git으로 사용 예정).
- ReportArchive 실연동(REST/MCP)은 후순위(M3+). 1차 입력은 **복붙 모드** — report_archive_draft_v1 JSON 파일을 `wda ingest --file`로 받는다. 접속 정보·인증 불필요.
- 포맷 픽스처 examples/reportarchive/report_sample.json (ReportArchive 루트의 report_578_platform_guide.json 사본, 5페이지 실물).
- 복붙 모드엔 search_text/ai_summary가 없음 → 정규화기가 위젯 텍스트 평탄화로 search_text 자체 생성.
