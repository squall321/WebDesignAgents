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
- 운영 base_url=http://<사내-GLM>:10000/v1, model=GLM-5-2, 키 정본은 ReportArchive backend/.env. 상속은 env-kits @FROM_RA 마커(webdesignagents.env 킷 + MAP 1줄).
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

## 2026-08-25 — 문서 3형식을 호출 경로에 붙임

### 결정 25. 문서(html/pdf/docx)는 렌더 잡과 같은 큐를 탄다
- 경위: 문서 조립·export 는 이미 있었는데(`wdpipeline.document` + `wdrender.exporter_doc`) 호출 경로가 CLI 뿐이었다. MCP·웹 모두 `RENDER_TARGETS = ("video","pptx")` 라 요청 자체가 걸러졌다.
- 별도 큐를 만들지 않은 이유 — 워커가 스레드라 PDF 의 sync Playwright 가 그대로 안전하고, 폴링(`render_status`)·열람 URL 배관을 재사용할 수 있다.
- **포맷 outputs 필터는 면제**한다. 영상·PPT 는 무대 규격(16:9 등)의 산출물이지만 문서는 무대와 무관하게 심의 산출물에서 나온다 — 포맷이 `outputs: [pptx]` 여도 문서는 나와야 한다.
- 삽화는 `_capture_doc_stills` 가 즉석에서 굽는다. 렌더 패키지에는 스틸 PNG 가 없다(영상·PPT 는 캡처 후 버린다).
  - 파일명은 `document.py::_still_filename` 규약 — **전역 시각**이다. 로컬 시각으로 쓰면 다단 페이즈 씬(클로징)의 두 스틸이 한 파일로 겹쳐 그림 수가 모자란다(실측).
  - `run_dir` 은 `resolve()` 로 절대화한다. 상대경로면 exporter 가 `assets_root` 아래로 붙여 그림이 0개가 된다(실측).

### 결정 26. 검사기가 잡는 구어체는 변환기가 없앨 수 있어야 한다
- `SPOKEN_RESIDUE` 는 하세요·해요·이에요·예요·시죠 를 잡는데 `SPOKEN_RULES` 에 대응 규칙이 없었다 → 그 말이 든 원고는 `to_written` 을 거쳐도 남아 `validate_document` 가 **영구** 차단. 웹 데모 시나리오의 "확인하세요" 가 실제로 그랬다.
- 해요체 청유(-세요/-으세요/-시죠)는 십시오 규칙과 같은 꼴로 권고형(`~는 것을 권한다`)으로 보낸다.
- 검사기도 `하세요` → `세요` 로 넓혔다. '읽으세요' 같은 비-하 어간을 놓치면 검사기가 통과시켜 구어체가 보고서에 실린다.
- 표본 11종으로 불변식 회귀 고정 (`test_every_residue_pattern_has_a_converting_rule`).

## 2026-08-28 — MCP·웹 기능 대칭

### 결정 27. 웹은 심의 로직을 복제하지 않고 MCP 도구 본체를 호출한다
- 웹에는 심의가 아예 없었다(규칙기반 데모 조립뿐). 두 창구가 서로 다른 품질의 자료를 냈다.
- 브리핑 조립·인용 화이트리스트·차례 검증을 웹에 다시 쓰면 그 순간 두 창구의 심의 규칙이 갈라진다 → `wdweb.deliberation.call_tool` 이 `wdmcp.server` 의 함수를 **그대로** 부른다. FastMCP 의 `@mcp.tool()` 은 원함수를 반환하므로 가능하다.
- 그러려면 세션을 호출자가 실을 수 있어야 한다 → `wdmcp.session.use_session` (contextvar 오버라이드).

### 결정 28. 회의 원장(known_refs)의 진짜 집은 회의 디렉터리다
- stdio 는 프로세스 = 회의라 메모리 원장으로 충분했다. 웹은 요청마다 이어지지 않는다.
- 원장이 사라지면 브리핑으로 전달한 ref 가 잊히고, **정당한 인용이 환각으로 거부**된다.
- `MeetingLedger.to_dict/from_dict` + `{회의dir}/web_ledger.json`. 실측 검증은 "2회차 브리핑에서 모듈 전달이 full→recall 로 바뀌는가" 로 했다.
- 회의 루트는 직접 계산하지 않고 `wdmcp.server._engine().store.root` 를 쓴다 — wdweb 은 repo 루트, wdmcp 는 CWD 기준이라 따로 풀면 원장이 회의와 다른 곳에 떨어진다.

### 결정 29. 자율 실행(autorun)은 웹에만 있는 경로다 — 대칭의 예외
- MCP 는 클라이언트(Claude)가 페르소나를 연기한다. 브라우저에는 그 주체가 없다.
- 같은 엔진·같은 검증 위에 발언자만 LLM 으로 바꾼 `wdllm.orchestrator` 를 웹에서 연다(PLAN 경로 B). 기능이 한쪽에만 있는 게 아니라 **연기 주체가 다르므로 진입점이 다른** 것이다.

### 실측으로 잡은 결함
- 열람 URL 은 주는데 받을 수 없던 문서 — `render_status` 가 html·pdf·docx URL 을 돌려주면서 `_JOB_DOWNLOAD_META` 에는 video·pptx 만 있어 3종 전부 404. 대칭 테스트가 이 부류를 통째로 막는다.
- 콘솔 상태판이 `round_no`·`turn_count` 를 읽어 전 항목이 `-` — 실제 스키마는 `round_index`·`turns_total` 이다.

### 결정 30. 심의 시나리오는 재빌드까지가 한 동작이다
- `scenario_build` 는 `scenario.json` 만 쓴다. 웹에서 그대로 두면 실행의 `build/` 는 옛 시나리오라 렌더·문서에 심의 결과가 **반영되지 않는다** — 심의 화면이 장식이 된다.
- 핀포인트 패치가 이미 쓰던 마무리(`검증 → build_render_package → 원장 갱신`)를 `scenes.rebuild_run` 으로 뽑아 두 경로가 같은 끝을 쓴다.
- 콘솔 개회 폼에 **대상 실행 선택**을 넣었다. 조각([F#] 근거)의 출처이자 시나리오가 돌아갈 자리다 — 연결하지 않으면 `scenario_build` 가 쓸 run 이 없다.

### 결정 31. 자율 심의는 백그라운드 잡 (동기 요청 금지)
- 전 라운드 완주는 LLM 턴이 수십 번이고 GLM 타임아웃이 120~600s 다. 동기 POST 는 프록시·브라우저 타임아웃에 먼저 걸린다.
- 렌더 잡과 같은 규약 — 파일이 진실(`{회의dir}/autorun.json`), POST 202 즉시 반환, GET 폴링, 중복 시작 409, 실패는 사유째 기록.
- 이 형태 덕에 배선 결함 2건이 **사유와 함께** 드러났다. 동기였다면 502 하나로 뭉개져 "LLM 미설정" 으로 오독했을 것이다.
  - `Orchestrator` → 실제 클래스명은 `AutoOrchestrator`.
  - `RunResult` 는 데이터클래스이고 `minutes_path` 는 `Path` — `dict()` 도 `asdict()` 만으로도 JSON 이 안 된다.

### 결정 32. 골든 임계는 frame_match 와 분리한다 (0.02 → 0.002)
- 골든 대조는 원래 있었다(`verify_all` 이 픽셀 비교 후 실패시킨다). 문제는 임계를 `frame_match_max_ratio`(0.02)로 함께 쓴 것이다 — 그건 **애니메이션 프레임 정합용 여유**다.
- 실측 — 배지 패딩 14→22px·32→56px 라는 눈에 띄는 변경이 0.0251 로 겨우 임계를 넘었다. 1px 변경(14→15px)은 0.0072 로 **조용히 통과**했다. 반면 잡음 바닥은 40종 전부 정확히 0.0 이다. 잡음 0 인 자리에 2% 를 준 셈이었다.
- `golden_max_ratio = 0.002` 분리. 1920×1080 기준 약 4100px 여유 — 다른 크로미움 빌드의 AA 요동은 흡수하되 레이아웃·색 변화는 잡는다. 교차 플랫폼 탈출구는 `WDA_GOLDEN_MAX_RATIO`.

### 결정 33. 골든 실패는 원인을 구분해서 말해야 한다
- 환경 차이와 코드 회귀는 **고치는 방법이 정반대**인데 diff 숫자만으로는 구분되지 않는다. 잘못 읽으면 멀쩡한 코드를 뒤지거나, 진짜 회귀를 허용치로 덮는다.
- `wda repro` 실패에 판정 한 줄 — 거의 전 모듈이 함께 어긋나고 세션 간 diff 가 0 이면 **환경**(허용치·기준선 재설정), 몇 종만이면 **회귀**(그 템플릿), 세션 간 diff 가 있으면 **비결정성**(골든보다 그게 먼저).
- 교차 환경(다른 머신) 골든 안정성은 여기서 검증하지 못했다 — 컨테이너 파이썬이 달라 venv 가 안 돈다. 첫 CI 실행이 곧 그 검증이며, 실패해도 판정 문구가 환경 차이임을 말해 준다.

### 결정 34. CI 는 재현력을 별도 잡으로 한 번 더 돌린다
- 전체 테스트가 다른 이유로 깨져도 재현력 상태는 읽혀야 한다. 크로미움은 playwright 핀이 곧 빌드 핀이다 — 다른 빌드는 AA 가 달라 골든이 흔들린다.

### 결정 35. 포맷은 심의가 인용할 수 있는 근거여야 한다
- `format_presets_briefing()` 은 "다음 심의가 인용할 수 있는 형태로 요약한다" 고 적혀 있었지만 **쓰이는 곳이 테스트뿐**이었다. 심의로 전달되는 경로가 없었다.
- 그래서 `format_review` 는 사실상 열 수 없는 회의였다 — review 라운드는 인용이 필수인데, 지식카드가 없는 페르소나(크리에이티브 디렉터·품질 감사관)는 인용할 ref 가 0건이라 발언이 거부된다.
- `meeting_start(format_id=...)` → 명세·상태·프리셋·교훈이 `FMT:{id}#lesson-1` 꼴 ref 로 실린다. PLAN §8.0 승격 루프의 "노하우 재사용" 은 이 배선 없이는 성립하지 않는다.

### 결정 36. 승격 근거는 명세에 남긴다 (회의록은 data/ 라 사라진다)
- 회의록은 `data/meetings`(gitignore)에 있어 다른 사람 체크아웃에 없다. 승격이 검증 가능하려면 무엇이 근거였는지가 명세와 함께 남아야 한다 → `promotions: [{to, meeting_id, verdict, date, note}]`.

### 결정 37. 명세-게이트 관계는 등호가 아니라 부등호다
- `constraints.min_font >= QAConfig.min_font_px`. 게이트 값은 WCAG 근거의 하한선이고 명세는 장르 편의 문서다. 등호로 적으면 **명세를 낮추는 방향의 '일치'** 를 막지 못한다(AX 요구, format_review 2026-08-28).
- 이 검사가 즉시 deck-4x3·deck-doc-16x9 에서 근거 없는 min_font 21 을 찾아냈다.

### 결정 38. 테스트 픽스처는 gitignore 밖에 둔다
- CI 를 넣자마자 드러난 것 — 새 체크아웃에서 6 실패 + 33 에러. 픽스처가 `data/` 안에 갇혀 있어 **로컬에서만 통과하는 테스트**였다.
- `data/` → `data/*` + 예외 사슬 (git 은 부모가 제외되면 자식을 되살리지 못한다). JSON·YAML·소형 자산 34개(776K)만 추적.
- 복사본을 `tests/` 로 옮기지 않았다 — 이 파일들은 실제 심의 산출물이고 `format.yaml` 의 골든이 같은 경로를 가리킨다. 복사하면 원본과 갈라진다.
- 큰 바이너리(스틸 15M·회의록·렌더)가 필요한 검사는 **사유를 적어** 건너뛴다. 조용한 통과는 검사 없는 것보다 나쁘다.

### 결정 39. 등폭 숫자(tnum)는 본문에 걸지 않는다 — PDF 에서 숫자가 사라진다
- `body { font-feature-settings:'tnum' 1 }` 이 12쪽 문서에 PUA 문자 109자를 만들었다. 등폭 숫자 대체 글리프는 서브셋 폰트에 유니코드 매핑이 없어 Chromium 이 ToUnicode 를 PUA 로 떨어뜨린다. **화면은 멀쩡한데 검색·복사가 안 된다** — 렌더 결과만 보면 절대 안 잡히는 부류다.
- 자동 리스트 마커(CSS 생성 콘텐츠)도 같은 이유로 깨진다. 번호를 본문 텍스트로 적어야 한다.
- 정렬은 **숫자 열 우측 정렬**로 대신한다. tnum 은 애초에 표의 장치이지 산문의 것이 아니었고, 우측 정렬은 단위 자리를 맞추므로 등폭보다 오히려 읽기 쉽다. 열 단위 과반 판정 — 셀마다 정렬이 달라지면 표가 흔들린다.
- 회귀 테스트는 PDF 를 실제로 구워 추출한다. CSS 문자열만 검사하면 다음 원인(다른 생성 콘텐츠)을 놓친다.

### 결정 40. 하이브리드 PPTX 를 기본으로 승격 (PLAN §9.1 ③)
- 하이브리드는 이미 구현·테스트돼 있었는데 **호출부가 하나도 없었다**. CLI·MCP·웹 셋 다 기본값 `image` 를 그대로 썼다 — 문서 3형식·`format_presets_briefing` 과 같은 부류다. 이 프로젝트에서 반복되는 실패 유형: **능력은 만들고 도달 경로를 안 만든다.**
- 승격 조건 둘 중 폰트 대체 표는 있었고 **좌표 허용 오차 기준이 없었다.**
- 기준 정의 — 숨기기로 지워진 픽셀 중 텍스트박스에 덮이지 않은 비율. 덮이지 않은 픽셀은 "배경에서 지웠는데 다시 그리지 않은 글자" 이므로 곧 사라진 글자다. 이 정의는 좌표·크기·누락을 한 숫자로 잡는다.
- 실측 0.027%(delib_v2 7씬 91/341,506, 전부 안티에일리어싱) → 임계 0.5%. 가드 검증은 텍스트박스 하나를 일부러 떨어뜨려 40.5% 검출을 확인했다.
- 기본값을 올린 근거 — 배경은 그대로이고 그 위에 원 좌표 텍스트가 얹히므로 보이는 것은 같고 받는 사람이 고칠 수 있다. 용량도 1599KB→1223KB 로 준다(배경에서 글리프가 빠진다).
- ⚠ 미검증 — 맑은 고딕 대체 시의 글자 폭 차이는 리눅스에서 잴 수 없다. 한 줄 텍스트는 줄바꿈을 꺼 접히지 않게 했고, 배경에 같은 글자가 없어 겹쳐 보이지는 않는다.

### 결정 41. 지표는 "1회차" 를 본다 — 전체 통과율은 항상 1 에 수렴한다
- 고칠 때까지 다시 돌리면 어떤 빌드든 결국 통과한다. 그래서 전체 통과율은 품질이 오르는지 말해 주지 않는다. **빌드마다 처음 돌린 QA 가 통과했는가**만 센다 — 94.7%(180/190, 리포트 332건).
- 표본이 없을 때 0% 가 아니라 `None` 을 낸다. 0% 는 "품질이 나쁘다" 로 읽힌다.
- 읽지 못한 리포트 수를 함께 낸다. 숨기면 분모가 조용히 줄어든다.

### 결정 42. 모듈 재사용률의 기준은 "등록 여부" 가 아니라 "시점"
- 모든 tpl 이 지금은 등록돼 있으므로 등록 여부로 재면 항상 100% 다. 창작 모드는 **그 실행을 위해 새 모듈을 만든** 경우이므로, 기준은 씬이 쓴 tpl 이 그 실행보다 먼저 있었는가다 — 87.4%(목표 80% 충족).
- ⚠ 시점은 근사다. 모듈은 git 커밋 시각, 실행은 scenario.json 수정 시각 — 둘 다 진짜 시점보다 늦거나 이를 수 있다. 추세 지표이지 감사 증적이 아니다.
- tpl 참조→모듈 id 변환은 `wdpipeline.build` 정본을 쓴다. 다시 파싱하면 세로 포맷(vtpl.*) 규칙이 갈라진다. 그 변환기가 호출마다 registry.yaml 을 읽어 씬 468개에 7.7초가 걸렸다 → `lru_cache` + git 일괄 조회로 0.42초. **대시보드가 늦으면 아무도 안 본다.**

### 결정 43. 계측 범위를 지표와 함께 낸다
- 심의 토큰은 vLLM 무인 심의만 잡힌다 — MCP 경로는 클라이언트가 페르소나를 연기하므로 서버가 LLM 을 부르지 않는다("서버는 LLM을 호출하지 않는다"). 분모를 전체 회의로 잡으면 평균이 거짓이 된다. 2/35 라는 사실을 숫자 옆에 붙인다.

### 결정 44. HITL 은 "그 승인이 없으면 무엇이 잘못되는가" 로 정의한다
- 지점 이름만 적으면(참가자 확정·시나리오 확정…) 왜 필요한지 잊히고, 결국 아무도 안 누르는 형식이 된다. `HITL_POINTS` 의 값은 전부 결과 문장이다.
- 승인에 `reason` 을 강제한다. 이유 없는 승인은 나중에 되짚을 수 없으므로 기록으로서 가치가 0 이다.
- 이력을 누적한다. 마지막 결정만 남기면 언제 무엇이 뒤집혔는지 알 수 없다.

### 결정 45. 무인 모드는 근거가 있을 때만 대신 누른다 — 골든은 예외 없이 사람
- `WDA_UNATTENDED` 는 사람을 없애는 스위치가 아니라 **규칙이 근거를 확인하고 대신 누르는** 모드다. 규칙마다 필요한 근거 키를 선언하고 없으면 막는다.
- **골든에는 무인 규칙을 두지 않았다.** 회귀 기준선을 무인으로 지우면 가드가 조용히 사라지고 아무도 눈치채지 못한다. 자동화의 신뢰도는 "무엇을 근거로 대신 누르는가" 로 정해지고, 골든에는 그 근거가 존재할 수 없다.
- ⚠ 근거 검사는 **존재 여부**로 한다. truthy 로 보면 `gate_errors: 0`·`validation_errors: []` 처럼 좋은 값이 0/빈값인 근거를 "없음" 으로 취급해 **깨끗한 빌드일수록 거절**된다(구현 중 실제로 난 버그).

### 결정 46. 골든 갱신 이유는 골든 옆에 남긴다
- `--update-golden` 이 이유·승인·기록 없이 기준선을 덮어쓰고 있었다. `--reason` 필수로 바꾸고 `fixtures/snapshots/golden.json` 에 이력을 쌓는다.
- 리포트(data/, gitignore)에 남기면 다른 체크아웃에 없고, `git log` 는 "PNG 가 바뀌었다" 까지만 말한다. 의도된 시각 변경인지 사고인지는 골든 옆 파일이 판별한다.
- 픽셀이 같으면 쓰지 않는다 — PNG 인코딩은 같은 화면에서도 바이트가 다르다(실측 207015→207013). 매번 덮으면 리포지터리가 흔들리고 이력에 "바뀐 것 없음" 이 쌓여 진짜 변경이 묻힌다.

## 2026-10-24 — cae00 실연결 준비 (env-kits 상속)

### 결정 47. `.env` 의 LLM_* 는 pydantic-settings 가 가져가지 않는다
- env-kits 는 `.env` 에 `LLM_BASE_URL/LLM_MODEL/LLM_API_KEY` 를 적는데, 이 키들은 `WDA_` 접두가 없어 `wdcore.config`(pydantic-settings)가 읽지 않는다. 그 결과 `.env` 가 있어도 `os.environ` 에는 없고 `load_llm_config` 는 **dev 기본값으로 조용히 떨어진다**(실측).
- cae00 에서 그 폴백은 곧 Errno 111 이다. apply-envs.sh 주석이 경고하는 바로 그 증상인데, **설정이 틀린 게 아니라 안 읽힌 것**이라 원인을 찾기 어렵다. 킷만 썼으면 연결이 안 됐을 것이다.
- `load_llm_config` 가 `os.environ` 에 `.env` 를 덧대 읽는다. 실제 환경변수가 파일을 이긴다 — 컨테이너는 `APPTAINERENV_` 로 진짜 환경변수를 넣기 때문이다. 경로는 `WDA_ENV_FILE` 로 바꿀 수 있다(컨테이너 작업 디렉터리가 리포 루트가 아닐 수 있다).

### 결정 48. 공개 리포에 사내 주소를 적지 않는다 (HWAXPortal 10-17 결정 1 준용)
- 이 리포는 공개(github.com/squall321/WebDesignAgents)인데 사내 GLM 주소가 추적 파일 6개에 있었고, 그중 `.env.example` 은 사람이 복사해 쓰는 견본이었다.
- 주소 리터럴만 중립 표기로 바꾼다. **정본이 ReportArchive `backend/.env` 라는 사실은 보존한다** — 주소를 지우는 게 목적이지 경로를 잊는 게 목적이 아니다.
- 킷의 NO_PROXY 는 `@NO_PROXY@` 마커를 쓴다. PLAN §10.1 의 하드코딩 지시는 낡았으므로 갱신했다.
- ⚠ **이미 푸시된 커밋(6d6abb6)에는 주소가 남아 있다.** HEAD 정리는 앞으로를 막을 뿐 과거를 지우지 않는다 — 이력 재작성은 사용자 판단 사항.

### env-kits 상속 절차 (cae00에서 실행)
```bash
cd ~/claude/HWAXPortal && bash infra/env-kits/apply-envs.sh webdesignagents
```
- dev 박스에서는 RA 에 LLM_* 가 없어 3키가 설계대로 건너뛰어진다(확인 완료). cae00 에서는 RA 값이 있으므로 6키 전부 들어간다.
- `.env` 는 WDA 쪽에서 gitignore 다 — 비밀값이 커밋되지 않는다(확인 완료).

## 2026-10-24 — short-9x16 active 승격 (제작 2회차 + format_review)

### 결정 49. 포맷은 자수를 담고 스키마는 개수를 담는다 — 브리핑이 둘 다 들어야 한다
- short_v2 제작 심의에서 AU 가 "세로 숏폼은 카드 2장이 상한" 이라 주장했고 **아무도 반박하지 못했다.** 1·2회차 모두 실제로는 3장이었고 `v-stack` 은 `minItems: 3` 이다. 빌드 단계에서야 막혔다.
- 원인은 AU 의 부주의가 아니다. `copy_guide` 는 **글자수**만 담는데 개수는 스키마에만 있었다. 손에 숫자가 없으면 사람은 직관으로 말하고, **직관이 실측을 이긴다.**
- 같은 뿌리로 MO 는 낭독 예산을 **화면 카피** 글자수로 계산했다. 게이트2 가 재는 것은 `x-read` 필드(내레이션)다 — 훅 씬이 38자/6.0s 로 걸려 7.0s 가 됐다.
- → `ModuleIndexEntry.structure`·`read_fields` 를 schema.json 에서 **읽어서** 싣는다.

### 결정 50. 장르 자산은 베껴 적지 말고 가리켜라
- 처음 안은 `copy_guide` 에 개수를 추가하는 것이었으나 AU 가 "스키마가 정본이므로 포맷이 베껴 적으면 또 어긋난다" 고 반박했고 제안자(CD)가 철회했다.
- 스키마는 템플릿과 함께 버전이 오른다. 포맷에 복사하면 두 개의 진실이 생기고, 틀어지는 쪽은 언제나 복사본이다.

### 결정 51. 2회차는 "장르를 쓰기만 한" 첫 회차다
- 1회차 19턴 → 2회차 19턴. **턴 수는 같지만 논의 대상이 다르다** — 1회차는 장르를 만들었고 2회차는 콘텐츠만 정했다. 턴 수로만 비교하면 이 차이가 안 보인다(wide-16x9 때는 19→7 이었는데, 그건 같은 보고서의 재심의였기 때문이다).
- `dur_plan` 46.0 은 1회차 값이고 2회차는 47.6 이다. 실제 대역은 46~48 — **물려받을 것은 숫자가 아니라 재는 방법**(lesson-5 의 `max(낭독 예산, 정착+판독)` 공식)이다.
