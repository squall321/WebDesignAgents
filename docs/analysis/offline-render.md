# 오프라인 렌더 노드 — egress 0 실증 (PLAN §12.4)

**결론 — 폐쇄망 렌더는 이미 가능하다.** Apptainer SIF 를 실제로 빌드하고, 네트워크 네임스페이스를
비운 상태(`--net --network=none`)에서 `data/build/delib_v2` 를 렌더해 1920×1080 h264 mp4(78.000s /
1872프레임) + PPTX 8장을 얻었다. 개발 호스트가 만든 프레임과 **픽셀 단위로 같다**.

측정 환경 — Ubuntu 22.04 호스트, apptainer 1.3.3, 2026-07-28.

---

## 1. 전제 조건 체크리스트

렌더 1회가 외부로 나가지 않으려면 아래 다섯 가지가 전부 로컬이어야 한다. 하나라도 비면
헤드리스 크로미엄이 조용히 CDN 을 때리고, 폐쇄망에서는 그 자리에서 렌더가 멈춘다.

| # | 자산 | 어디에 있어야 하나 | 현재 상태 | 근거 |
| --- | --- | --- | --- | --- |
| 1 | React / ReactDOM / Babel UMD | 빌드 패키지 `vendor/` 사본 | ✅ | `build.py:246` 이 `web/vendor/` 3종을 복사, 엔트리가 `./vendor/*` 상대경로로 로드 |
| 2 | Pretendard woff2 | 빌드 패키지 `fonts/` + `@font-face src:url('./fonts/...')` | ✅ | `build.py:69` `_PRETENDARD_FACE` — jsdelivr Pretendard CDN 링크를 대체 |
| 3 | chromium 바이너리 | SIF 내부 `/opt/ms-playwright` (`PLAYWRIGHT_BROWSERS_PATH` 고정) | ✅ | `%post` 의 `playwright install chromium`, 리비전 1228 / 149.0.7827.55 |
| 4 | ffmpeg | SIF 내부 `PATH` | ✅ | Debian bookworm ffmpeg 5.1.9 |
| 5 | 기호 폴백 폰트 | SIF 내부 DejaVu Sans | ✅ | §4 참조 — 이게 빠지면 렌더는 되지만 글리프가 달라진다 |

부수 조건.

- **정적 서버는 루프백**이다. `wdrender.server.StaticServer` 가 `127.0.0.1:0` 에 바인드하므로
  빈 네트워크 네임스페이스(로 인터페이스만 존재)에서도 살아남는다. 실측으로 확인했다.
- **`web/runtime/support.js` 는 빌드 산출물에 복사되지 않는다.** unpkg URL 3종을 들고 있는
  CDN 부트스트랩 경로인데, P4 엔트리는 이 경로를 쓰지 않는다(`index.html` 주석 "support.js 무사용 경로").
  `wdrender.page_session.vendor_resources()` 의 `window.__resources` 폴백은 support.js 경로를
  쓰는 레거시 엔트리용 안전망으로 남아 있고, 현행 빌드에서는 애초에 발동하지 않는다.
- **쓰기는 바인드 마운트에만.** SIF rootfs 는 읽기 전용이라 `WDA_DATA_DIR=/data` 로 산출물 경로를
  돌려놓았다(HEAXHub 런타임 3계약 ③과 동일 규약).

---

## 2. 실측 결과

### 2.1 SIF 빌드

| 항목 | 값 |
| --- | --- |
| 명령 | `scripts/build-sif.sh` |
| 권한 | `--fakeroot` (sudo 불필요 — `/etc/subuid`·`/etc/subgid` 에 `koopark:100000:65536` 매핑 존재) |
| 소요 | 108–119s (3회 빌드 실측) |
| 크기 | 603 MiB (`ls` 기준 631,930,880 B) |
| 베이스 | `docker://python:3.12-slim-bookworm` — HEAXHub 파이썬 스택 3.12 고정과 정합 |
| 내장 | python 3.12.13 · playwright 1.61.0 + chromium 1228 · ffmpeg 5.1.9 · DejaVu/Liberation/Nanum |

`%post` 끝의 sanity 블록이 repo 루트 앵커(`/opt/wda`)와 5개 필수 자산 존재를 검사하므로
자산 누락은 빌드 단계에서 깨진다. 런타임에 발견되지 않는다.

### 2.2 오프라인 렌더 (핵심)

```bash
scripts/render-offline.sh delib_v2
  → apptainer run --cleanenv --net --network=none --bind ./data:/data wda-render.sif --slug delib_v2
```

| 항목 | 값 |
| --- | --- |
| 네트워크 | 빈 네임스페이스. `connect(1.1.1.1:443)` → `OSError 101 Network is unreachable`, DNS → `gaierror` |
| 루프백 | 살아 있음 — `127.0.0.1` 바인드 후 자기 자신 GET 200 확인 |
| mp4 | 1920×1080 · h264 · yuv420p · 24fps · **nb_frames 1872** · **duration 78.000000s** · 2,834,987 B |
| Σdur 대조 | 시나리오 7씬 합 78.0s = mp4 78.000s (오차 0) |
| pptx | 8장 / 7씬 (클로징 stills 2개) |
| 벽시계 | 188s (mp4 1872프레임 + pptx 8장 전체) |

세로 포맷도 같은 조건에서 성공했다 — `short_v1`(short-9x16, 1080×1920) 46.000s / 1104프레임 /
pptx 5장, 벽시계 117s. 즉 두 포맷 모두 오프라인에서 완주한다.

`--no-home` 을 추가해 호스트 홈(=`~/.cache/ms-playwright`)을 아예 안 보이게 한 상태에서도
렌더가 성공했다. 즉 내장 chromium 만으로 도는 것이 증명됐다.

```text
executable: /opt/ms-playwright/chromium-1228/chrome-linux64/chrome
version:    149.0.7827.55
```

### 2.3 호스트 대비 프레임 동일성

같은 빌드를 호스트(네트워크 켜짐)와 SIF(네임스페이스 비움)에서 각각 렌더하고 프레임 PNG 를
sha256 으로 비교했다. 이게 "오프라인이라 화질이 깎였다"를 배제하는 유일한 방법이다.

| 빌드 | 포맷 | 표본 시각 | PNG sha256 일치 |
| --- | --- | --- | --- |
| `delib_v2` | wide-16x9 (1920×1080) | 0.5 / 5 / 12 / 25 / 40s | **5/5 완전 일치** |
| `short_v1` | short-9x16 (1080×1920) | 0.5 / 5 / 12 / 25 / 40s | 4/5 일치, t=12 만 잔차 |

t=12 잔차의 정체는 §4. 최종 이미지 기준 잔차는 **전체 2,073,600px 중 30px, 최대 채널차 5/255**
(diff_ratio 0.000014, 채널 허용오차 8 이상에서는 0.000000). 육안 식별 불가.

mp4 바이트는 호스트/SIF 가 다르다 — ffmpeg 4.4.2(호스트) vs 5.1.9(SIF) 의 인코더 차이다.
디코드 후 프레임 비교로는 frame 10·40 이 완전 일치, frame 80 이 diff_ratio 0.0013 이었다.
**픽셀 결정성의 정본은 PNG 캡처 단계**이고 거기서는 위 표대로 일치한다.

### 2.4 외부 참조 정적 검사

`tests/test_offline_assets.py` — 6 항목, 전부 통과 (0.43s).

- 현행 `build.py` 로 새로 조립한 패키지에서 **외부 스킴 로드 참조 0건**
  (`src=`/`href=`/`url()`/`@import`/`fetch()`/`import()` 를 스캔).
- CDN 금지 도메인 11종(unpkg·jsdelivr·cdnjs·googleapis·gstatic·esm.sh·skypack·tailwind·
  raw.githubusercontent) **스킴 포함 0건**.
- `@font-face src` 가 전부 `./fonts/` 로컬 참조.
- 필수 로컬 자산 9종 존재.
- `web/{runtime,templates,tokens,vendor}` 원본에도 CDN 참조 0건.
- SIF 정의가 `PLAYWRIGHT_BROWSERS_PATH`·`PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD`·`WDA_DATA_DIR` 를 선언.

검사 설계에서 걸러낸 오탐 2종을 남겨 둔다. 다음 사람이 같은 함정을 밟지 않도록.

1. **문서 문자열 URL 은 대상이 아니다.** `vendor/babel.min.js` 안에는 babeljs.io·github.com
   안내 URL 이 수십 개 있지만 네트워크를 타지 않는다. 그래서 "http 문자열 금지"가 아니라
   "**로드 참조** 금지"로 규칙을 세웠다.
2. **스킴 없는 도메인 언급도 대상이 아니다.** `web/runtime/animations-v2.jsx:467` 의
   `fonts.googleapis.com <link>` 는 주석이다. 금지 목록은 `https?://` 가 붙은 형태만 잡는다.

한편 `data/build/` 에는 폰트 로컬화(2026-07-25) 이전에 만들어진 산출물 3개
(`demo_sample`·`fix_check`·`adv_check`)가 남아 있고 jsdelivr Pretendard 링크를 물고 있다.
그래서 이 테스트는 **디스크의 옛 산출물을 검사하지 않고** 현행 `build.py` 로 새로 조립한
패키지를 검사한다. 옛 빌드는 재빌드하면 사라진다.

---

## 3. 사용법

```bash
# 1) 빌드 (네트워크 필요, 약 2분)
scripts/build-sif.sh                       # → deploy/apptainer/wda-render.sif

# 2) 오프라인 렌더 (네트워크 네임스페이스 격리가 기본)
scripts/render-offline.sh delib_v2
scripts/render-offline.sh delib_v2 --fps 12 --skip-video
WDA_NET=net scripts/render-offline.sh delib_v2      # 격리 해제(디버그용)

# 3) 렌더 외 하위 명령도 같은 SIF 로
apptainer run --bind ./data:/data wda-render.sif build --run-id delib_v2
apptainer run --bind ./data:/data wda-render.sif formats
```

산출은 `data/renders/{slug}/{slug}.mp4` · `{slug}.pptx`.

바인드는 `data/` 하나면 족하다. 빌드 산출물이 `data/build/` 아래에 있어 읽기·쓰기가 같은
트리에서 끝나기 때문이다. 읽기 전용 분리가 필요하면
`--bind ./data/build:/data/build:ro --bind ./data/renders:/data/renders` 로 쪼개면 된다.

---

## 4. 함정 하나 — 기호 폴백 폰트가 렌더를 바꾼다

씬 템플릿은 `✕`(U+2715)·`→`(U+2192)·`—`(U+2014) 같은 기호를 텍스트로 쓴다. Pretendard 에는
이 글리프가 없어서 **시스템 폰트 폴백**으로 넘어간다. 즉 SIF 에 어떤 폰트가 깔려 있느냐가
출력 픽셀을 바꾼다. woff2 를 내장했다고 끝이 아니다.

발견 경로와 처방.

1. 초기 이미지에서 `short_v1` t=12 프레임만 호스트와 달랐다(diff_ratio 0.00053).
   확대해 보니 `✕` 가 계단현상 나는 비트맵 글리프로 그려져 있었다.
2. CDP `CSS.getPlatformFontsForNode` 로 확인 — 호스트는 `DejaVu Sans`,
   SIF 는 `Unifont`(비트맵 폰트)를 골랐다. `playwright install-deps chromium` 이
   `fonts-unifont` 를 딸려 넣기 때문이다.
3. **fontconfig 의 `sans-serif` alias 를 고쳐도 소용없었다.** `fc-match` 는 DejaVu 를
   반환하는데 chromium 은 여전히 Unifont 를 썼다 — Skia 의 문자 단위 폴백은
   generic alias 를 따르지 않고 자체 정렬을 쓴다. `69-unifont.conf` 를 무력화해도 마찬가지였다.
4. 처방은 **패키지 제거**뿐이었다. `%post` 에서 `apt-get purge -y fonts-unifont` 하고
   `fonts-dejavu-core` 를 명시 설치한다. 그 뒤 diff_ratio 0.00053 → 0.000014 (38배 감소).

남은 0.000014 는 DejaVuSans.ttf 파일 자체가 다르기 때문이다(Ubuntu 22.04 vs Debian bookworm,
md5 `3e926c44…` vs `4cc160d1…`). 완전 일치를 원하면 호스트 ttf 를 `%files` 로 박아 넣으면 되지만,
최대 채널차 5/255 · 30px 규모라 그 대가(라이선스 파일 관리·이미지-호스트 결합)가 더 크다고 봤다.

**교훈** — 폰트 목록은 렌더 노드의 암묵적 입력이다. `apt-get install` 목록을 건드릴 때마다
프레임 해시 비교를 다시 돌려야 한다. `docs/analysis/offline-render.md` 의 §2.3 절차가 그 회귀 테스트다.

---

## 5. HEAXHub SIF 배포와의 관계

| 축 | HEAXHub 앱 SIF (`web_design_agents`) | 이 렌더 노드 SIF |
| --- | --- | --- |
| 만드는 주체 | HEAXHub 스캐너가 manifest(`build.stack: fastapi_react`)를 보고 자동 빌드 | 이 저장소의 `scripts/build-sif.sh` |
| 역할 | 웹 콘솔 서비스(`wdweb`, uvicorn `--root-path`, `/api/health`) | 배치 렌더 워커 (`wda render` 1회 실행 후 종료) |
| 기동 | `launch.mode: service`, `127.0.0.1:$PORT` | `apptainer run` 일회성 |
| 데이터 | `$HEAX_DATA_DIR` → `WDA_DATA_DIR` | `--bind ./data:/data` → `WDA_DATA_DIR=/data` |
| 네트워크 | Caddy 리버스 프록시 뒤 | 없음(`--network=none`) |

**두 이미지는 같은 규약을 공유한다** — python 3.12 고정(`requires-python >= 3.12`),
쓰기는 `WDA_DATA_DIR` 아래에만, 소스 트리는 repo 루트 모양 그대로. 그래서 HEAXHub 가
앱 SIF 를 자동 빌드하기 시작해도 이 def 파일은 렌더 워커 전용으로 그대로 살아남는다.

`%environment` 의 `WDA_DATA_DIR=/data` 는 HEAXHub 3계약 ③(SIF rootfs 읽기 전용,
쓰기는 `$HEAX_DATA_DIR` 아래)과 같은 값을 쓴다. 렌더 노드를 HEAXHub job_runner 로
올릴 때(§12.5 M3 검토 항목) 바인드만 `$HEAX_DATA_DIR:/data` 로 바꾸면 된다.

기존 참조 정의는 `HEAXHub/deploy/apptainer/{caddy,postgres,redis,toolchain_*}.def` 이고,
`%post` 프록시 포워딩·`%labels org.heaxhub.*`·`%help` 바인드 안내 관례를 여기서도 따랐다.

---

## 6. 재현 명령 모음

```bash
# 빌드 (fakeroot 가능 여부 자동 판정)
scripts/build-sif.sh

# egress 차단 확인
apptainer exec --cleanenv --net --network=none deploy/apptainer/wda-render.sif \
  python -c "import socket; s=socket.socket(); s.settimeout(4); s.connect(('1.1.1.1',443))"
#   → OSError: [Errno 101] Network is unreachable

# 오프라인 렌더
scripts/render-offline.sh delib_v2
ffprobe -v error -show_entries format=duration -show_entries stream=nb_frames \
  -of default=noprint_wrappers=1 data/renders/delib_v2/delib_v2.mp4

# 정적 검사
uv run pytest tests/test_offline_assets.py -q
```
