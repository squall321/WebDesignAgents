#!/usr/bin/env bash
# HEAXHub SIF 빌드 훅 — fastapi.def Stage2 가 `pip install -e .[web,render,mcp,llm]` 뒤에 호출한다.
# pyproject 로는 못 담는 렌더 런타임(Playwright chromium 본체 + OS 라이브러리 + ffmpeg + 폰트)을
# 컨테이너에 심어 SIF 하나로 "통째로" 렌더가 되게 한다. deploy/apptainer/wda-render.def 의 검증된
# %post 를 HEAXHub 관리 SIF 규약(/app 앵커, system python)에 맞춰 재현한 것.
#
# 브라우저는 이미지 안 고정 경로 /opt/ms-playwright 에 굽는다 → 런타임 다운로드 시도가 없어야
# 폐쇄망(egress 0)에서 렌더가 재현된다. 매니페스트 launch.env 가 런타임에도 같은
# PLAYWRIGHT_BROWSERS_PATH 를 준다. 빌드 시점에 네트워크가 닿아야 하므로 온라인 박스에서
# fat SIF 를 빌드하고 dist-to-drive(per-app SIF)로 폐쇄망에 나른다.
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive
export PIP_ROOT_USER_ACTION=ignore
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright

apt-get update
# ffmpeg — PNG 시퀀스 → mp4 조립(wdrender.exporter_video 가 PATH 의 ffmpeg 호출).
# fonts-dejavu-core — 필수. 템플릿의 ✕(U+2715)·→(U+2192) 기호는 Pretendard 에 없어 시스템
#   폴백으로 넘어가는데, 개발 호스트가 DejaVu Sans 로 폴백하므로 이미지에도 같은 폰트를 넣어야
#   프레임이 픽셀 단위로 일치한다. fonts-liberation/fonts-nanum — 라틴·한글 폴백.
apt-get install -y --no-install-recommends \
    ffmpeg \
    ca-certificates \
    fontconfig \
    fonts-dejavu-core \
    fonts-liberation \
    fonts-nanum
update-ca-certificates || true

# playwright 를 1.61.0 으로 못 박는다 — 브라우저 리비전(chromium-1228)까지 고정돼야 오프라인
# 렌더가 재현된다. optional-dependencies.render 의 무제약 "playwright" 가 이미 최신판을 깔았을 수
# 있으므로 이 버전으로 덮어쓴다.
python -m pip install --no-cache-dir "playwright==1.61.0"

# chromium 의 OS 의존 라이브러리 + 브라우저 본체 사전 내장.
python -m playwright install-deps chromium
python -m playwright install chromium
chmod -R a+rX /opt/ms-playwright

# 기호 폴백 고정 — install-deps 가 딸려 넣는 fonts-unifont(비트맵)가 lang=ko 문맥에서 ✕ 를
# 가로채 계단현상 글리프를 그린다. chromium 의 문자 단위 폴백은 fontconfig sans-serif alias 를
# 따르지 않으므로 패키지 자체를 걷어내는 게 유일하게 확실하다.
apt-get purge -y fonts-unifont || true
apt-get autoremove -y || true
cat > /etc/fonts/local.conf <<'XML'
<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <!-- Pretendard 에 없는 기호(✕ → — 등)의 최종 폴백을 DejaVu Sans 로 못 박는다 -->
  <alias binding="same">
    <family>sans-serif</family>
    <prefer><family>DejaVu Sans</family></prefer>
  </alias>
</fontconfig>
XML
fc-cache -f >/dev/null 2>&1 || true
rm -rf /var/lib/apt/lists/*

# 검증 — 하나라도 없으면 빌드를 깨뜨린다(런타임에 "렌더 안 됨"으로 뜨는 것보다 낫다).
ffmpeg -version | head -1
python - <<'PY'
import shutil
from playwright.sync_api import sync_playwright  # noqa: F401
import wdrender.exporter_video  # noqa: F401
assert shutil.which("ffmpeg"), "ffmpeg 없음"
print("  ✓ playwright + wdrender + ffmpeg import ok")
PY
test -d /opt/ms-playwright || { echo "✗ chromium 미내장"; exit 1; }
echo "✓ [heaxhub-build] 렌더 런타임(chromium+ffmpeg+fonts) 설치 완료"
