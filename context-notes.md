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

## 2026-07-25 — 2차 빌드 + 교차 리뷰 라운드 완료

### 2차 빌드 (워크플로우 4 빌드 + 2 리뷰)
- wdmcp(툴 11종+봉투+known_refs/delivered_modules 원장), wdpipeline(P0~P4+CLI), wdllm(GLM 5원칙 클라이언트+무인 오케스트레이터), wdqa(게이트 7종) 완성.
- E2E 실증 — report_sample.json → 심의 없이 규칙 조립 → mp4 90.000s + PPTX 7장(발표자 노트=narration).
- 적대적 리뷰 결론: 빌드 에이전트 허위 보고 0건. 경계 공격(빈 보고서·씬51·dur0/301·16KB) 방어 확인.

### 리뷰 지적 수정 (이 라운드에서 전부 처리)
- major 5건 — ① render_submit out_dir slug 정합 ② gate2 x-read 서브트리 합산 ③ wdllm fragments 배관(에이전트 수행, frag_id 초기 known_refs) ④ 테마 faint #8A92A8→#667085(4.5:1+) ⑤ QA 단락 기본값 해제(skip_on_phase_failure=False).
- minor — gate1 wdaChildren 변수 해석, modules_root env 존중, cli 검증오류 정제, ingest 빈 입력 거부, _truncate 어절 경계, process 픽스처 압축(193→130자), FakeLLM 모더레이터 인용.
- 게이트 실전 가동으로 발견된 템플릿 결함 추가 수정 — stills 기본값 dur-1.0(페이드 중 캡처 방지), DotGrid/아바타 data-qa-clip-ok, 체크 글리프 data-qa-icon, 네트워크 라벨 폭 확장, 히어로 lineHeight 1.15, 내레이션 낭독 예산 절단(dur×5.5자), gate3 미선언-통과 조합 info 강등.
- 최종 상태: pytest 165 passed/4 skipped, QA 게이트 passed=True(경고 0, info 1), E2E mp4 90.000s+PPTX 7장 재현.

## M0 결정성 실측 (2026-07-25)

**하네스**: `wdrender.exporter_video.verify_render_determinism` — 동일 입력을 두 번 독립
렌더(별도 세션·별도 PNG 시퀀스)해 프레임별 SHA 비교 + perceptual diff(max 채널차 > tol 픽셀 비율).
기존 `verify_seek_determinism`(한 세션 내 재-seek)이 못 잡던 "독립 2회 렌더 일치"를 커버.

**실측 (demo_sample, 24fps × 90s = 2160프레임)**:
- 프레임수 일치 True, 2146/2160 프레임 비트(SHA) 동일 — **14프레임만** 차이.
- 차이도 극미: max_diff_ratio 0.000002 (1920×1080 ≈ 200만 픽셀 중 최대 4개), mean 0.000001.
- 원인은 서브픽셀 안티에일리어싱(완전 비트 결정성은 아님). perceptual 기준 사실상 결정적.

**결론**: `QAConfig.frame_match_max_ratio=0.02`(2%)는 실측(0.000002)보다 1만 배 보수적 → 확정.
Pretendard 폰트를 CDN → 로컬 @font-face(`web/fonts/PretendardVariable.woff2`)로 전환해
네트워크 비결정 요인도 제거(M3 egress-0 전제와도 일치).

## 2026-07-26 — 첫 실전 심의 (경로 A 실구동) 완료

- 회의 1c82515e — scenario_build, CD 모더레이터 + ST/CP/TD/AX/SL 5인, 19턴 전부 엔진 검증 통과(거부 0), known_refs 146건(조각 140+카드 6), minutes.md 생성.
- 실제 거부권 행사 — TD 절대 거부권(랜덤 스켈레톤 바 = 결정성 위반 → 고정 폭 배열로 패치 후 철회), AX 조건부 거부권(20px 각주 → 24px 토큰 위임). CP 재집필(31자 타이틀 → 19자 단일 주장), SL 등장 스케줄 계산으로 ✕ 4항목 → 3항목 축소.
- 핵심 메시지 "보고서는 한 번만 작성한다"가 전 씬 지배. 산출: scenario 검증 0오류 → mp4 90.000s + pptx 8장 → QA 게이트 error/warning 0.
- 판정(별도 에이전트, 71필드 전수 원문 대조): 데모 조립본 복붙 43건·말줄임 28건 vs 심의본 0건·0건. 8개 기준 전부 심의본 우세. "형태 끼워맞춤" 지적 해소 판정.
- 남은 격차 — 거부→수리 실전 데이터 없음, R1이 모더레이터 대독 형식(템플릿 개선 여지), MCP 경로 델타 전달 실전 미사용, contrastPairs 1건 미선언(info).

## 2026-07-26 — 조합 라운드 (웹 콘솔·창작 모드·TTS·아카이브 순환)

### 결정 16. 웹 콘솔(wdweb) — HEAXHub 등록의 전제이자 대화형 제작의 무대
- FastAPI + 무번들러 SPA. HEAXHub 3계약 준수(127.0.0.1:$PORT, --root-path, /api/health).
- 적대적 검증이 critical 2건 적발 → 수정: QA 라우트 async→sync def(sync Playwright가 asyncio 루프와 충돌해 QA 100% 거짓 실패 + 이벤트 루프 전역 블로킹), slug에 run_id 꼬리 부착(같은 slug 두 실행이 build/renders 공유해 산출물 오염).
- HEAXHub manifest 등록 완료(HEAXHub 저장소 2966a69) — mcp:{expose:true} 포함.

### 결정 17. 창작 모드 실증 — 외부 샘플 0개로 신규 템플릿 3종
- tpl.dataviz(증거의 저울)·tpl.timeline(이정표의 길)·tpl.compare(거울 대면). 엔진 원자+토큰+방법론만으로 저작, hex 하드코딩 0, 게이트 1~7 error 0.
- module_review 실심의 45턴 — dataviz Go(→pilot), timeline·compare Conditional-Go. 게이트가 통과시킨 것을 회의체가 실측으로 추가 적발(footnote 상한 시 푸터 룰 41px 침범 계산, 결론 배지 룰 걸침, schedule-렌더 0.05s 편차).
- 결론: 새 포맷은 샘플 투입 없이 자가 창작 가능. 샘플은 필수가 아니라 가속기(취향 골든·역설계 대상).

### 결정 18. TTS는 VoiceRecorder 실연동 — 실측이 심의의 입력이 된다
- PR #1 머지 확인(bb15c15). 프로젝트 플로우로 delib_v1 실합성 → delib_v1_voiced.mp4(90.000s, h264+aac+mov_text).
- 전 씬 drift -3.4~-6.7s(내레이션이 슬롯보다 짧아 무음 패드) → 이 실측이 v2 심의의 dur 재조정 근거가 됨(90s→78s 압축, dataviz 채택).

### 결정 19. P6 아카이브 역기록 — 순환 완성
- build_archive_draft: 실행 산출물(정규화 보고서·회의록·씬 구성·QA)을 report_archive_draft_v1 4페이지로. 위젯은 실물 샘플 타입만.
- **왕복 무결성 실증** — 생성 초안을 자체 P0 ingest→P1 fragmentize로 재소비(4페이지 13블록→47조각). "보고서→발표자료→제작기록 보고서" 순환이 코드로 닫힘.
- submit_draft는 WDA_RA_* 자격증명 투입 시 켜지는 선택 업로드(실호출 미검증 — 운영 DB 무접촉).

### 결정 20. 대화형 제작 — Claude 없이 폐쇄망 LLM만으로 왕복
- POST /api/runs/{id}/chat — 씬 요약+레지스트리 인덱스+허용 액션 8종 스키마로 {reply, actions} 강제. 액션은 사본 검증 후 원자 적용/전체 취소.
- 로컬 vLLM(qwen2.5-7b) 실호출 3턴 액션 파싱 3/3 성공. 프리뷰 자동 갱신까지 왕복 확인.

### 결정 21. UI 품질을 제도로 (사용자 상시 지시)
- docs/UI_PRINCIPLES.md 7항 — "구두수선공의 아이들부터 신긴다": 화면 구성을 심의하는 플랫폼의 콘솔이 평범하면 설득력이 죽는다.
- UI 변경 라운드마다 페르소나 design_review 심의로 스크린샷 심사 → Conditional 이하면 반영 후 재심사. 산출물과 동일 규율.

## 2026-07-29 — 배포 구조 확정 (다른 에이전트 작업 인수)

### 결정 22. 배포는 HEAXHub SIF 표준 빌드 (독립 서비스 아님)
- 경위: 처음엔 SIF 계획(§12.4) → chromium 646MB 때문에 자체 venv 독립 서비스로 전환 시도(HWAXPortal services.yaml 등록) → 최종적으로 **SIF 빌드 훅**으로 회귀·확정.
- 방법: `scripts/heaxhub-build.sh` 가 `fastapi.def` Stage2 opt-in 훅으로 붙어 playwright 1.61 + chromium(/opt/ms-playwright) + ffmpeg + 폰트를 컨테이너에 굽는다. 별도 SIF 를 따로 만들지 않는다.
- `serve.sh` 는 로컬 개발 편의용으로 격하, Drive 스크립트(browser/data/deploy-from-drive)는 제거.
- 실가동 확인 — 런처가 :9136 에 `--root-path /apps/web_design_agents` 로 기동, Caddy 경유 `/apps/web_design_agents/api/health` 200.
- 정본 문서는 docs/DEPLOY.md.

### 결정 23. manifest 함정 — health_check·restart_policy 는 launch: 아래
- 런처·서비스매니저가 `launch.health_check`/`launch.restart_policy` 만 읽는다. top-level 선언은 조용히 무시되고 스택 기본값 `/health` 로 프로브돼 404 만 쌓인다(재시작 정책도 미적용).
- 재시도 횟수 키는 `max_attempts` (≠ max_retries).

### 결정 24. wdmcp 이중 노출의 실체 — 웹 앱 /mcp 로도 서빙
- manifest `mcp:{expose:true, path:/mcp}` 선언만 있고 실체가 없어 게이트웨이가 "다운"으로 표시되던 문제 해소.
- `wdweb.app` 이 동일 FastMCP 서버를 `/mcp`(streamable_http)로 서빙. 도구 정의는 wdmcp 한 곳뿐.
- ⚠ `app.mount("/mcp", ...)` 금지 — Starlette Mount 정규식이 `/mcp/{path}` 라 뒤 슬래시 없는 정확 경로를 못 잡는다. 정확 경로 Route 로 등록해야 SPA 캐치올이 405 로 먹지 않는다.

### 진행 기록
- HEAXHub 쪽 부수 수정 6건(다른 에이전트) — '열기' 무반응 3중 결함(스택 오지정·extras 누락·launch.command 무시), 호스팅 앱 LLM 설정 상속(cae00 GLM), 스캐너 커밋 백필 제거, MCP 레지스트리가 실체 없는 앱 미노출, deploy rev 즉시 기록.
