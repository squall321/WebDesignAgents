#!/usr/bin/env bash
# 로컬 개발용 편의 실행 스크립트 — 호스트 venv 로 wdweb 웹 콘솔을 기동한다.
#
# ⚠ HEAX 연동/배포는 이 스크립트가 아니다. 다른 HEAX 앱과 똑같이 HEAXHub 가 SIF 로 빌드·서빙한다
# (integrations/web-design-agents/, /apps/web_design_agents/). Playwright chromium·ffmpeg·폰트는
# fastapi.def Stage2 훅(scripts/heaxhub-build.sh)이 컨테이너 /opt/ms-playwright 에 굽는다. 이 파일은
# SIF 없이 로컬에서 빠르게 돌려볼 때만 쓴다.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Playwright chromium 을 프로젝트 내 var/ms-playwright 에 둔다 → Drive 전송에 포함되고
# 폐쇄망에서 playwright install(네트워크)이 필요 없다. 홈 캐시(~/.cache/ms-playwright)를 안 탄다.
export PLAYWRIGHT_BROWSERS_PATH="${PLAYWRIGHT_BROWSERS_PATH:-$ROOT/var/ms-playwright}"
# 운영 데이터(회의·렌더·QA 산출)는 프로젝트 data/ 아래. HEAXHub SIF 배포에서만 manifest env 로
# WDA_DATA_DIR=/data 를 명시 오버라이드한다 (여기서 HEAX_DATA_DIR 을 자동 상속하면 독립 서비스가
# 오케스트레이터 전역 /data 를 잘못 집어 기존 산출물을 못 본다 — 실측 버그).
export WDA_DATA_DIR="${WDA_DATA_DIR:-$ROOT/data}"

PORT="${WDWEB_PORT:-${PORT:-8340}}"
# 오케스트레이터가 detach 한다. HEAXHub 3계약: 127.0.0.1 바인드·$PORT·--root-path $ROOT_PATH.
exec .venv/bin/python -m uvicorn wdweb.app:app \
  --host "${HOST:-0.0.0.0}" --port "$PORT" ${ROOT_PATH:+--root-path "$ROOT_PATH"}
