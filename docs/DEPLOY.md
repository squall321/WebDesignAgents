# 배포 — HEAX 연합(SIF) 등록 + 폐쇄망 Drive 파이프라인

WebDesignAgents 를 "통째로" 다른 서버(폐쇄망 cae00)로 옮겨 돌리는 방법. 다른 HEAX 앱과
**똑같이 HEAXHub 가 SIF 로 빌드·서빙**한다 — 자체 venv 독립 서비스가 아니다. 무거운 렌더
런타임(Playwright chromium·ffmpeg·폰트)은 SIF 빌드 훅이 컨테이너에 구워 넣으므로 SIF 하나로
자족한다.

## 어떻게 도는가 (SIF 경로)

1. **카탈로그 등록**: HEAXHub `integrations/web-design-agents/.portal/manifest.yaml`
   (id=web_design_agents, `build.stack: fastapi`, `build.extras: [web,render,mcp,llm]`,
   `launch.command: uvicorn wdweb.app:app …`, `mcp.expose: true`, source=git main).
2. **SIF 빌드**: HEAXHub 스캐너가 GitHub main 을 clone → `fastapi.def` 를 렌더해 빌드.
   - Stage1 `pip install -e .[web,render,mcp,llm]` (fastapi/uvicorn·playwright·pptx·mcp·openai).
   - Stage2 opt-in 훅 `scripts/heaxhub-build.sh` → **chromium(/opt/ms-playwright) + ffmpeg + 폰트**를
     컨테이너에 심는다(deploy/apptainer/wda-render.def 의 검증된 %post 재현).
   - 산출: `HEAXHub/var/sifs/web_design_agents.sif`.
3. **서빙**: `apptainer instance start` → Caddy 가 `/apps/web_design_agents/` → `127.0.0.1:$PORT`.
   런처가 3계약(127.0.0.1·$PORT·$ROOT_PATH)과 `/data` 볼륨(=`var/app_data/web_design_agents/`)을
   주입하고, manifest env 로 `WDA_DATA_DIR=/data`·`PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright`(+
   `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`) 를 넣는다.
4. **MCP**: `mcp.expose: true` → HWAX MCP Gateway 에 wdmcp 자동 노출(`/apps/web_design_agents/mcp`).

모델·LLM·TTS 는 자체 서빙하지 않는다 — vLLM(HWAXPortal 상속)·VoiceRecorder TTS API 를 소비.

## 통째 나르기 대상

| 요소 | 크기 | 이동 방법 |
|------|------|-----------|
| 코드 + web/vendor·web/fonts + frontend/dist | ~수 MB | **git**(github squall321/WebDesignAgents) |
| chromium·ffmpeg·폰트·venv | — | **SIF 에 내장**(빌드 훅) → per-app SIF 로 Drive |
| 운영 데이터 (data/: 회의·렌더·QA) | 가변 | **/data 볼륨** — HEAXHub `appdata-{to,from}-drive.sh` |

## 폐쇄망 배포 절차

```bash
# ── 온라인 박스(HEAXHub) ──
# 1) SIF 빌드 — 스캐너 자동, 또는 수동 강제 리빌드:
cd HEAXHub && deploy/apptainer/redeploy-app.sh web_design_agents --rebuild
# 2) per-app SIF + app-data 를 Drive 로:
deploy/apptainer/dist-to-drive.sh          # var/sifs/*.sif (HEAX_DRIVE_WITH_APP_SIFS=1 기본)
deploy/apptainer/appdata-to-drive.sh web_design_agents   # /data 스냅샷(선택)

# ── 폐쇄망 서버(cae00) ──
cd HEAXHub && deploy/apptainer/dist-from-drive.sh        # git·빌드 없이 SIF 수신
deploy/apptainer/appdata-from-drive.sh web_design_agents # /data 복원(선택)
# HEAXHub 가 인스턴스를 띄우면 /apps/web_design_agents/ 로 접속.
```

Drive remote 는 HEAXHub 와 공유(`HEAX_DRIVE_REMOTE`, 예: `ApptainerImages:HEAXHub/dist`).

## 레거시(독립 서비스 경로 — 폐기)

`scripts/serve.sh`·`scripts/browser-{to,from}-drive.sh`·`scripts/data-{to,from}-drive.sh` 는
예전의 "자체 venv 독립 서비스" 경로 잔재다. SIF 경로에서는 chromium 이 이미 SIF 에 있고
데이터는 HEAXHub `appdata-*-drive.sh` 가 다루므로 **불필요**하다. `serve.sh` 만 로컬 개발
편의용으로 남긴다(HEAX 연동/배포에는 안 쓴다).

## SIF 렌더 노드 (선택, M3)

egress-0 격리 렌더가 별도로 필요하면 `scripts/build-sif.sh`(`deploy/apptainer/wda-render.def`)로
독립 렌더 SIF 를 만들 수 있다. 위 HEAXHub 관리 SIF 와 별개의 옵션이다.
