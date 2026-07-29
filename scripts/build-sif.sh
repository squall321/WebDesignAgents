#!/usr/bin/env bash
# 오프라인 렌더 노드 SIF(deploy/apptainer/wda-render.def)를 빌드하는 스크립트 — fakeroot 판정·소요·산출 경로 안내
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEF="$REPO_ROOT/deploy/apptainer/wda-render.def"
OUT="${1:-$REPO_ROOT/deploy/apptainer/wda-render.sif}"

die() { echo "[build-sif] 오류: $*" >&2; exit 1; }

command -v apptainer >/dev/null 2>&1 || die "apptainer 가 PATH 에 없다. HEAXHub/deploy/apptainer/install-apptainer.sh 참조."
[ -f "$DEF" ] || die "정의 파일 없음: $DEF"

# %files 는 이 def 파일 기준 상대경로를 쓰므로 repo 루트에서 빌드해야 한다.
cd "$REPO_ROOT"

# 빌드 권한 판정 — ① root ② --fakeroot(subuid/subgid 매핑 필요) ③ 둘 다 없으면 중단
BUILD_FLAGS=()
if [ "$(id -u)" -eq 0 ]; then
    MODE="root"
elif grep -q "^$(id -un):" /etc/subuid 2>/dev/null && grep -q "^$(id -un):" /etc/subgid 2>/dev/null; then
    MODE="fakeroot"
    BUILD_FLAGS+=(--fakeroot)
else
    die "root 도 아니고 /etc/subuid·/etc/subgid 에 $(id -un) 매핑도 없다.
    다음 중 하나가 필요하다.
      (a) sudo apptainer build ...
      (b) sudo usermod --add-subuids 100000-165535 --add-subgids 100000-165535 $(id -un) 후 재시도
      (c) 다른 호스트에서 빌드한 .sif 를 복사"
fi

echo "[build-sif] 모드=$MODE  정의=$DEF"
echo "[build-sif] 산출=$OUT"
echo "[build-sif] chromium·ffmpeg 내장 — 최초 빌드는 네트워크가 필요하고 수 분 걸린다."

START=$(date +%s)
apptainer build "${BUILD_FLAGS[@]}" --force "$OUT" "$DEF"
ELAPSED=$(( $(date +%s) - START ))

SIZE=$(du -h "$OUT" | cut -f1)
echo "[build-sif] 완료 — ${ELAPSED}s, ${SIZE}, $OUT"
echo "[build-sif] 다음: scripts/render-offline.sh <slug>   (예: scripts/render-offline.sh delib_v2)"
