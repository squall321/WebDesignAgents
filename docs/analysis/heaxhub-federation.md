## SUMMARY
HEAXHub는 사내 자동화 도구·웹앱·외부 사이트를 한 포탈에서 검색·실행·관리하는 통합 카탈로그다. 프론트는 React+Vite+TS+shadcn/ui(TanStack Router/Query), 백엔드는 FastAPI+Celery+PostgreSQL+Redis이며 운영은 Apptainer SIF 인스턴스+Caddy로 돌린다. 통합 진입점은 Caddy :4180, 백엔드 API :4040, 앱 포트 풀은 9100–9999다. 산하 프로젝트 등록은 `integrations/<slug>/.portal/manifest.yaml`(schema v2) 하나로 끝나며, 스캐너가 uvicorn 기동 시와 5분 주기 Celery beat로 자동 발견해 clone→SIF 빌드→`/apps/<slug>/` 서브경로 서빙까지 처리한다. 서비스형 앱은 `$PORT`(127.0.0.1 바인드)·`$ROOT_PATH`(=/apps/<slug>)·`$HEAX_DATA_DIR`(영구 볼륨 /data) 3계약만 지키면 되고, Caddy forward_auth가 모든 `/apps/*` 요청을 `GET /api/v1/authz`로 게이트한다(쿠키 JWT 또는 Bearer PAT). VoiceRecorder는 이미 `voice_recorder`(fastapi_react 스택, source=github VoiceRecorder.git, status=draft)로 등록돼 있어 실제 저장소가 스택 규약을 따르게 만드는 일만 남았다. WebDesignAgents는 같은 패턴으로 thin 디렉터리+manifest만 추가하면 되고, `mcp: {expose: true}` 블록을 선언하면 HWAX MCP Gateway에 자동 흡수된다. 상위에는 HWAX Portal(hwax.sec.samsung.net)이 있어 `/heax-hub/` 서브패스 연방 및 RS256 launch JWT 기반 SSO를 제공한다.

## KEY_FACTS
- 등록 단위: integrations/<slug>/.portal/manifest.yaml (schema_version: 2). 스캐너는 backend/app/services/integrations_scanner.py — uvicorn 기동 시 + Celery beat 5분 주기 upsert(삭제 안 함).
- 포트 구성: Caddy 통합 진입점 :4180, FastAPI 백엔드 :4040, Vite dev :4173, PostgreSQL :5732, Redis :6479, MailHog :8125/:8126, Caddy Admin API 127.0.0.1:2019, 앱 리버스프록시 포트 풀 9100–9999 (.env의 APP_PORT_RANGE_LOW/HIGH).
- 스택 카탈로그: config/stacks.yaml (22종, fastapi/fastapi_react/streamlit/nextjs/static_html/external_proxy 등). manifest의 build.stack 값으로 선택하며 backend/app/services/stack_resolver.py가 해석.
- 서비스 실행 계약: backend/app/services/integration_launcher.py가 PORT·HOST(127.0.0.1)·ROOT_PATH(=/apps/<slug>)·HEAX_DATA_DIR을 주입. 영구 데이터는 var/app_data/<id>/ ↔ 컨테이너 /data 바인드(SIF rootfs는 read-only). manifest launch.env는 앱 고유 env로 먼저 깔리고 HEAXHub 제어 변수가 덮음.
- 프록시: backend/app/services/proxy_manager.py가 Caddy Admin API로 라우트 @id=app-<slug>를 등록 — /apps/<slug>/* → 127.0.0.1:<port>. prefix-aware 스택(streamlit/nextjs/dash/shiny/flask)은 prefix 미제거, 나머지는 strip.
- 인증: forward_auth 게이트 → GET /api/v1/authz (backend/app/api/v1/authz.py). heax_access_token 쿠키(JWT HS256) 또는 Authorization: Bearer(JWT/PAT) 인정. visibility=company + status=stable 앱은 무인증 통과. 헤드리스(MCP/CI)는 PAT(pat_service).
- SSO: backend/app/api/v1/portal_sso.py — HWAX Portal이 RS256 launch JWT(aud=heax-hub)를 /api/v1/auth/portal-callback에 POST, JWKS 검증 후 JIT 계정 생성·HEAX 자체 세션 발급. portal_jwks_url 미설정 시 404(독립 배포 무영향).
- MCP 게이트웨이 연동: manifest에 mcp: {expose: true, path: /mcp, transport: streamable_http} 선언 → GET /api/v1/mcp/servers (backend/app/api/v1/mcp.py)가 HWAX MCP Gateway에 노출. BETA/STABLE 상태만 노출됨.
- VoiceRecorder 기등록: integrations/voice-recorder/.portal/manifest.yaml — id=voice_recorder, stack=fastapi_react, launch.mode=service, health_check.path=/api/health, source=https://github.com/squall321/VoiceRecorder.git, status=draft, resources.gpu=true, HF_HUB_OFFLINE=1(폐쇄망 가중치는 Drive 선배포).
- 기존 연계 사례: integrations/materialtwin-web(.portal/manifest.yaml만 있는 thin 디렉터리 + source.git 패턴, mcp.expose=true), laminate-analyzer-mcp, thermal-shock-mcp, heax-demo-* 17종.
- 등록 스크립트: scripts/register-repo.sh <slug> <git-url> <stack> [ref], scripts/register-url.sh <slug> <주소> [url|proxy|iframe], scripts/register-from-csv.sh. 온보딩 문서는 docs/DEVELOPER_GUIDE.md, 필드 스펙은 docs/MANIFEST_SPEC.md + schemas/manifest.schema.v2.json.
- Apptainer 배포: deploy/apptainer/ — start.sh/stop.sh/install_all.sh, caddy.def/postgres.def/redis.def/mailhog.def, toolchain_{python312,nodejs20,go122,polyglot}.def, caddy_bootstrap.json(:4180 라우팅), redeploy-app.sh. 폐쇄망(cae00)은 npm 불가 → dist-to-drive.sh/dist-from-drive.sh + HEAX_NO_BUILD=1.
- 운영 확인 지점: 서비스 로그 var/logs/integration_<slug>.log, SIF 빌드 로그 var/logs/sif_build_<slug>.log, 상태 파일 var/integration_state/<slug>.json, 강제 스캔 POST /api/v1/admin/integrations/sync, 프록시 복구 POST /api/v1/admin/integrations/proxy-sync.
- HWAX Portal 연방: https://hwax.sec.samsung.net/heax-hub/ → 127.0.0.1:4180 (prefix strip). SPA는 HEAX_BASE_PATH=/heax-hub/ 빌드타임 env로 대응 (docs/HWAX-PORTAL-INTEGRATION.md).

## INTEGRATION_CONTRACT
- WebDesignAgents 등록: integrations/web_design_agents/.portal/manifest.yaml 생성 (schema_version: 2, id: web_design_agents, app_type: web_app, execution_target: linux_runner, build.stack: fastapi 또는 fastapi_react, launch.mode: service, health_check.path: /api/health, source: {type: git, url: <저장소 URL>, ref: main}, permissions.visibility: company). 또는 scripts/register-repo.sh web_design_agents <git-url> fastapi_react 한 줄로 대체 가능.
- 런타임 규약: 앱은 127.0.0.1:$PORT로만 listen(0.0.0.0 금지 — 인증 게이트 우회 차단), uvicorn --root-path $ROOT_PATH로 서브패스 대응, 쓰기 데이터는 $HEAX_DATA_DIR(/data) 아래에만. health_check.path에 200을 줘야 서빙 시작.
- 접근 URL: http://<host>:4180/apps/web_design_agents/ (HWAX Portal 경유 시 https://hwax.sec.samsung.net/heax-hub/apps/web_design_agents/). 브라우저는 heax_access_token 쿠키로, 헤드리스 호출은 Authorization: Bearer <PAT>로 forward_auth 통과.
- WebDesignAgents → VoiceRecorder TTS 호출: Caddy 경유 http://127.0.0.1:4180/apps/voice_recorder/api/... + PAT Bearer 헤더가 정석(포트 직타는 인증 우회라 금지). VoiceRecorder 쪽 API 경로는 fastapi_react 스택 규약상 /api/* 프리픽스.
- 앱별 설정 상속: manifest launch.env로 앱 고유 env 선언(예: WDA_DATA_DIR: /data). 비밀값은 manifest env_required 배열 + secret_manager(Fernet, .env의 SECRET_ENCRYPTION_KEY)로 주입. PORT/HOST/ROOT_PATH/HEAX_DATA_DIR은 HEAXHub가 항상 덮어쓰므로 앱이 override 불가.
- MCP 노출(경로 A — wdmcp): manifest에 mcp: {expose: true, path: /mcp, transport: streamable_http} 선언하고 status를 beta 이상으로 올리면 GET /api/v1/mcp/servers를 폴링하는 HWAX MCP Gateway가 자동 흡수 — 포탈 챗과 개인 Claude에서 즉시 사용 가능.
- 카탈로그 반영 확인: 즉시 반영은 backend에서 scan_integrations_periodic() 1회 실행 또는 POST /api/v1/admin/integrations/sync, 확인은 curl http://localhost:4180/apps/<slug>/ 200 여부. 실패 시 var/logs/sif_build_<slug>.log와 var/logs/integration_<slug>.log 확인.

## GAPS
- WebDesignAgents는 현재 계획 문서만 존재(PLAN.md/checklist.md) — source.git에 넣을 실제 저장소가 아직 없어 저장소 생성·push가 선행되어야 한다.
- 사설(private) git 저장소 토큰 인증 미지원(DEVELOPER_GUIDE 명시) — 공개 repo 또는 사내 미러 필요. schema v2에 source.auth.secret_key 필드는 있으나 실제 fetch 경로는 미구현으로 안내됨.
- voice_recorder는 status: draft — 무인증 공개 통과(company+stable)와 MCP 게이트웨이 노출(beta/stable) 모두 막혀 있어, 서비스 확정 시 status 승격이 필요하다.
- WebDesignAgents 계획은 Python 3.13 전용 venv(uv)를 전제하지만 config/stacks.yaml의 python 스택은 python_version 3.12 고정 — 스택 정의 확장 또는 커스텀 SIF(apptainer_sif 스택) 경로 결정이 필요하다.
- GPU: manifest resources.gpu 필드는 받지만 integration_launcher.py의 서비스 기동 경로에서 apptainer --nv 전달 여부가 코드상 확인되지 않음(gpu_manager.py는 job 경로용) — VoiceRecorder GPU 사용 시 실측 검증 필요.
- 장시간 TTS/영상 렌더 작업은 service 모드의 동기 HTTP로는 타임아웃 위험 — 앱 내부 비동기 잡 큐로 처리하거나 HEAXHub job_runner 모드 병행 설계가 필요하다.
- 폐쇄망(cae00) 배포 시 HuggingFace/npm 접근 불가 — TTS 모델 가중치는 Drive(rclone)로 선배포(HF_HUB_OFFLINE=1 패턴), 프론트 dist는 dist-to-drive.sh 경로를 따라야 한다.
- 서비스 간 인증용 PAT 발급·관리 절차(pat_service)는 있으나 앱→앱 호출에 쓸 서비스 계정 PAT의 공식 발급 플로우 문서가 docs/app-base-and-pat/에 산재 — 연동 설계 시 PAT 수명·권한 범위 확정 필요.