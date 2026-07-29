#!/usr/bin/env bash
# SIF 렌더 노드로 egress 0 렌더를 돌리는 래퍼 — data/ 바인드 + 네트워크 네임스페이스 격리
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SIF="${WDA_SIF:-$REPO_ROOT/deploy/apptainer/wda-render.sif}"
DATA_DIR="${WDA_HOST_DATA_DIR:-$REPO_ROOT/data}"

usage() {
    cat >&2 <<'EOF'
사용법: scripts/render-offline.sh <slug> [wda render 추가 인자...]

  <slug>            data/build/<slug>/index.html 이 있어야 한다 (wda build 산출물)
환경변수
  WDA_SIF           SIF 경로 (기본 deploy/apptainer/wda-render.sif)
  WDA_HOST_DATA_DIR 호스트 data 디렉터리 (기본 <repo>/data)
  WDA_NET           net|none (기본 none — 네트워크 네임스페이스 격리로 egress 0 강제)
예시
  scripts/render-offline.sh delib_v2 --fps 24
  WDA_NET=net scripts/render-offline.sh delib_v2 --skip-video
EOF
    exit 2
}

[ "$#" -ge 1 ] || usage
SLUG="$1"; shift

command -v apptainer >/dev/null 2>&1 || { echo "[render-offline] apptainer 없음" >&2; exit 1; }
[ -f "$SIF" ] || { echo "[render-offline] SIF 없음: $SIF — scripts/build-sif.sh 를 먼저 실행" >&2; exit 1; }
[ -f "$DATA_DIR/build/$SLUG/index.html" ] || {
    echo "[render-offline] 빌드 없음: $DATA_DIR/build/$SLUG/index.html — wda build --run-id $SLUG 를 먼저" >&2; exit 1; }

mkdir -p "$DATA_DIR/renders/$SLUG"

# --cleanenv: 호스트 환경변수(프록시·PLAYWRIGHT_*)가 새어 들어와 오프라인 전제를 흐리는 것을 막는다.
# --net --network=none: 루프백만 있는 빈 네트워크 네임스페이스. 정적 서버는 127.0.0.1 바인드라 살아남고
#                       외부 egress 는 물리적으로 불가능해진다 (오프라인 실증의 핵심).
FLAGS=(--cleanenv --bind "$DATA_DIR:/data")
case "${WDA_NET:-none}" in
    none) FLAGS+=(--net --network=none) ;;
    net)  ;;
    *) echo "[render-offline] WDA_NET 은 none 또는 net" >&2; exit 2 ;;
esac

echo "[render-offline] SIF=$SIF"
echo "[render-offline] 바인드 $DATA_DIR → /data  (네트워크: ${WDA_NET:-none})"
set -x
exec apptainer run "${FLAGS[@]}" "$SIF" --slug "$SLUG" "$@"
