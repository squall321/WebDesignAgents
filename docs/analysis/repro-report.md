# 템플릿 재현력 리포트 — "같은 데이터·같은 템플릿 = 같은 화면"의 제도화

작성 2026-07-28. 하네스 `src/wdqa/repro.py` · CLI `wda repro` · 회귀 `tests/test_repro_templates.py`.
사용자 확정 요구("핀포인트 수정이 가능하려면 규정된 템플릿은 재현력이 높아야 한다")의 실측 근거 문서.

## 1. 재현력의 정의 — 3층

| 층 | 질문 | 검사 방법 | 소유 |
| --- | --- | --- | --- |
| 세션 간 | 브라우저를 새로 열어도 같은 화면인가 | 모듈 fixtures 3종(min/typical/max)을 preview 로 **독립 컨텍스트 2회** 렌더 → 스틸 시각 seek → perceptual diff + 스케줄 시각(still/nat/duration) 동일성 | `verify_template` |
| 빌드 간 | 같은 scenario 를 다시 빌드해도 같은 산출물인가 | 같은 scene-data.json 으로 `build_render_package` 2회 → scene-data.json·scenes.jsx·index.html **sha256 바이트 동일성** | `verify_build` |
| 골든 대비 | 지금 코드가 승인된 화면과 같은가 | typical 스틸 vs `fixtures/snapshots/typical.png` perceptual diff | `verify_template` |

- perceptual diff 임계는 **게이트 7(frame-match)과 동일값 재사용** — `QAConfig.frame_match_max_ratio = 0.02`, `frame_diff_channel_tol = 8` (실측 근거: 2026-07-25 demo_sample 2160프레임 2회 독립 렌더 max_diff_ratio 0.000002).
- "독립 세션" = 같은 크로미엄 프로세스의 **새 브라우저 컨텍스트**(별도 JS 렐름·별도 페이지). 프로세스 단위 완전 격리는 `verify_template` 를 개별 호출하면 얻는다(공유는 속도 최적화일 뿐 결과는 동일 — 아래 실측에서 두 방식 모두 diff 0).
- 구 프리뷰 10종(가로 7+ext 3)은 `?fixture=` 를 읽지 않으므로 하네스가 `fixtures/*.json` 요청을 **라우트 인터셉트**해 목표 픽스처 바이트로 응답한다(프리뷰 파일 무수정). 주입 실증: tpl.opening min vs typical 스틸 diff **0.0347** (음성 대조 — 측정계가 공허하지 않음).

## 2. 실측 결과 (2026-07-28, `uv run wda repro` 전 모듈)

17종 × 픽스처 3종 × 독립 세션 2회 = 102 렌더. 리포트 `data/qa_reports/repro-20260728-021438.json`.

| 모듈 | 판정 | 세션 간 max_diff | 골든 diff | 스케줄 결정성 |
| --- | --- | --- | --- | --- |
| tpl.opening | PASS | 0.0 | 0.0 | ✓ |
| tpl.problem | PASS | 0.0 | 0.0 | ✓ |
| tpl.concept | PASS | 0.0 | 0.0 | ✓ |
| tpl.process | PASS | 0.0 | 0.0 | ✓ |
| tpl.differentiator | PASS | 0.0 | 0.0 | ✓ |
| tpl.proof | PASS | 0.0 | 0.0 | ✓ |
| tpl.closing | PASS | 0.0 | 0.0 | ✓ |
| tpl.dataviz | PASS | 0.0 | 0.0 | ✓ |
| tpl.timeline | PASS | 0.0 | 0.0 | ✓ |
| tpl.compare | PASS | 0.0 | 0.0 | ✓ |
| tpl.d-matrix | PASS | 0.0 | 0.0 | ✓ |
| tpl.d-media | PASS | 0.0 | 0.0 | ✓ |
| tpl.d-multi | PASS | 0.0 | 0.0 | ✓ |
| vtpl.hook | PASS | 0.0 | 0.0 | ✓ |
| vtpl.stack | PASS | 0.0 | 0.0 | ✓ |
| vtpl.metric | PASS | 0.0 | 0.0 | ✓ |
| vtpl.cta | PASS | 0.0 | 0.0 | ✓ |

세션 간 diff 는 전 모듈 **0.0(비트 동일 스틸)** — 임계 0.02 대비 여유가 절대적이다.
빌드 간(2층)은 `tests/test_repro_templates.py::test_verify_build_deterministic` 로 상시 회귀 —
report_sample 시나리오 2회 빌드 3파일 sha256 동일 확인.

판정·max_diff_ratio·일시는 각 `module.yaml` 의 `quality.reproducibility` 에 기록된다(서지컬
텍스트 편집 — 주석·기존 키 보존, 재실행 시 자기 블록만 교체).

## 3. 골든 스냅샷 최신화 — 기존 골든과의 diff 원인 분석

`wda repro --update-golden` 으로 17종 typical 골든 재생성 (2026-07-28, 리포트
`data/qa_reports/repro-20260728-013727.json`). 갱신 전 diff 실측.

| 그룹 | 모듈 | 기존 대비 diff | 판정 |
| --- | --- | --- | --- |
| 가로 기본 7종 (opening~closing) | 7종 전부 | 1.0 (크기 불일치 1984×1117 → 1920×1080) | **캡처 규약 차이 — 회귀 아님** |
| ext·data·vertical 10종 | 10종 전부 | **0.0** | 현 코드 = 커밋 골든, 무회귀 |

- 구 7종 골든은 1차 빌드 시 **뷰포트 여백 포함 전면 캡처**(1984×1117)였고, 이후 세대(ext·data·vertical)와 이번 하네스는 **무대 원척 클립**(1920×1080 / 1080×1920)이다. 구/신 골든을 시각 대조한 결과 씬 콘텐츠·스틸 시점은 동일하고 프레임 규약만 다르다 — 코드 회귀가 아니라 **캡처 규약 통일(의도 변경)** 로 판정.
- 나머지 10종은 diff 0.0 — 골든이 커밋된 이후의 코드 변경(위젯 충실도·로드 순서 재편 등)이 화면을 바꾸지 않았음을 실증.
- 이후 골든은 전 17종이 같은 규약(무대 원척·still 시각·export CSS)이므로 `test_golden_matches_stage_dims` 가 규약 이탈을 상시 차단한다.

## 4. 재현력을 깨는 안티패턴 (게이트 6과의 관계)

씬은 **localTime 의 순수 함수**여야 한다(엔진 계약). 이를 깨는 패턴과 검출 층.

| 안티패턴 | 왜 깨지나 | 검출 |
| --- | --- | --- |
| `Math.random` | 세션마다 다른 배치·지터 | 게이트 6 정적(금지 식별자) + repro 세션 간 diff |
| `Date.now`·`new Date` | 렌더 시각이 화면에 새어듦 | 게이트 6 정적 + repro |
| `setTimeout`/`setInterval`/`requestAnimationFrame`/`useEffect` | wall-clock 전이 상태 — seek 로 재현 불가 | 게이트 6 정적 + 게이트 6 런타임(이중 seek 해시) |
| 전이 의존(CSS transition, 이전 프레임 상태 누적) | t 로 점프하면 다른 화면 | 게이트 6 런타임 + repro(스틸은 seek 산물) |
| CDN 폰트/이미지 로드 타이밍 의존 | 네트워크 상태가 화면을 바꿈 | 빌드는 로컬 woff2 인라인·`document.fonts.ready`+`fonts-inlined`+`images.complete` 대기로 통제, 잔여는 repro diff |
| schedule 이 데이터 외 입력(현재 시각·난수) 참조 | still/nat 이 세션마다 다름 | repro **스케줄 시각 결정성**(still/nat/duration 동일성) |
| 비직렬화 빌드 입력(dict 순서·환경 경로 삽입) | 빌드 산출물 바이트가 흔들림 | repro 2층 `verify_build` sha256 |

관계 정리 — **게이트 6은 "한 세션 안에서 같은 t = 같은 프레임"** 을(정적 근사 + 런타임 재-seek),
**repro 는 "세션·빌드·시점을 갈아끼워도 같은 화면"** 을 검사한다. 게이트 6을 통과해도 CDN
의존이나 빌드 비직렬성은 남을 수 있고, 그 잔여를 repro 3층이 막는다. 둘 다 임계·diff 함수는
게이트 7(frame-match)의 실측 보정값을 공유한다.

## 5. 운용

```
uv run wda repro                     # 전 모듈 3픽스처×2세션 — 표 출력, data/qa_reports 저장, module.yaml 기록
uv run wda repro --module tpl.proof  # 단일 모듈
uv run wda repro --update-golden     # 골든 재생성 (기존 대비 diff 를 리포트에 기록 후 교체)
uv run wda repro --build demo_sample # + 빌드 간 바이트 동일성
uv run pytest tests/test_repro_templates.py -q   # 회귀 (대표 6종 전체 픽스처 + 11종 typical)
```

회귀 계층화 근거 — 재현력 위험은 템플릿 파일 계열 단위(같은 파일 = 같은 코딩 규약·스케줄 유틸)로
갈리므로, 대표 6종(tpl.opening/dataviz/d-matrix/d-media/vtpl.hook/stack)이 4계열 × 무대 2종 ×
고위험 경로(이미지 자산·데이터 민감 스케줄)를 덮고 나머지 11종은 typical 만 검사한다.
