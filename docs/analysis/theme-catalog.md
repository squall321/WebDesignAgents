# 테마 카탈로그 — 색·그림자·모션 성격 5종

레이아웃 템플릿은 17종이 도착했지만 테마는 `hwax-blue` 1종뿐이었다. 레이아웃을 아무리 늘려도
색 체계가 하나면 전부 "같은 시리즈"로 읽힌다. 이 라운드는 그 병목을 푸는 테마 4종을 추가한다.

기준 테마 `hwax-blue` 는 읽기 전용이며, 4종 모두 그 3층 구조(raw / semantic / component)를
값만 바꿔 계승한다.

---

## 1. 무엇을 바꾸고 무엇을 고정했나

| 층 | 키 | 테마별 교체 | 이유 |
| --- | --- | --- | --- |
| raw | `palette`(16키)·`extra`(4키) | **교체** | 테마의 정체성 |
| raw | `shadow`(5키) | **교체** | 그림자 깊이·색조도 성격이다 (얕음=격식, 깊음=따뜻함, 글로우=다크) |
| raw | `font.base` | 고정 | 5종 모두 Pretendard. 폰트 교체는 글리프 폭이 바뀌어 `maxLength` 실측 역산을 무효화한다 |
| semantic | `motion`(프리셋 6 + 스태거 7) | **교체** | **색만 바꾸면 다양해 보이지 않는다** — 이징·지속시간·스태거가 성격의 절반 |
| semantic | `contrastPairs`(17쌍) | **재계산** | 값이 바뀌면 대비도 다시 증명해야 한다 |
| semantic | `type`·`layout`·`radius` | **고정** | 좌표 체계는 공용. 여기가 흔들리면 17종 레이아웃이 전부 재검증 대상이 된다 |
| component | 별칭(참조 문자열) | 구조 고정 | 참조만 유지하면 palette 교체가 자동 전파된다 |
| component | 기하 수치(`network.r`, `stepGrid.cardW` …) | **고정** | 위와 같은 이유 |

키 경로 집합이 기준과 정확히 일치해야 한다 — 하나라도 빠지면 로더의 참조 해석이 던지고
템플릿이 깨진다. `tests/test_themes_tokens.py::test_key_set_identical_to_base` 가 누락·잉여를
0으로 강제한다.

---

## 2. 5종 요약

| 테마 | 지면 | 카드 | 강조 | 그림자 | 모션 성격 | 쓰는 자리 |
| --- | --- | --- | --- | --- | --- | --- |
| `hwax-blue` (기준) | `#F6F7FA` | `#FFFFFF` | `#1428A0` 로열 블루 | 중간 | easeOutCubic + pop easeOutBack, 0.7s | 플랫폼 기본 |
| `neutral-slate` | `#F1F1F3` 무채색 | `#FFFFFF` | `#26334D` 딥 슬레이트 | **가장 얕게** 0 10px 24px | 절제 — 전 구간 easeOutCubic(팝도 오버슈트 없음), 0.6s, 스태거 −15% | 재무·감사·규정 |
| `warm-amber` | `#F8F0E4` 크림 | `#FFFDF9` 웜 화이트 | `#9A4A12` 테라코타 | **가장 크게** 0 20px 48px, 갈색 | 부드럽게 — easeOutSine, 0.85s(+21%) | 인사·조직문화·교육 |
| `deep-dark` | `#0B1220` 딥 네이비 | `#141C2E` | `#4CD9E5` 시안 / `#B6E86A` 라임 | 검정 0.55 + 시안 글로우 | 무게감 — easeOutQuart, 1.0s(+43%) | 기술·데이터·대형 스크린 |
| `fresh-teal` | `#E4F5F0` 민트 | `#FFFFFF` | `#0B7168` 딥 틸 | 중간 0 16px 40px, 틸 | 탄력 — 등장 전 구간 easeOutBack 오버슈트, 0.62s | 신사업·혁신 제안 |

### 모션 프리셋 실값

| 프리셋 | hwax-blue | neutral-slate | warm-amber | deep-dark | fresh-teal |
| --- | --- | --- | --- | --- | --- |
| `rise` | 0.70s / 26px / easeOutCubic | 0.60 / 20 / easeOutCubic | 0.85 / 24 / easeOutSine | 1.00 / 32 / easeOutQuart | 0.62 / 28 / easeOutBack |
| `riseSm` | 0.60 / 18 / easeOutCubic | 0.50 / 14 / easeOutCubic | 0.72 / 16 / easeOutSine | 0.85 / 22 / easeOutQuart | 0.52 / 18 / easeOutBack |
| `pop` | 0.45 / easeOutBack | 0.38 / easeOutCubic | 0.55 / easeOutBack | 0.62 / easeOutCubic | 0.42 / easeOutBack |
| `tag` | 0.50 / easeOutCubic | 0.42 / easeOutCubic | 0.60 / easeOutSine | 0.70 / easeOutQuart | 0.46 / easeOutBack |
| `exit` | 0.70 / easeInCubic | 0.60 / easeInCubic | 0.85 / easeInSine | 1.00 / easeInCubic | 0.60 / easeInCubic |
| `stagger.step` | 2.35 | 2.10 | 2.35 | 2.35 | 2.20 |

이징 이름은 엔진 `web/runtime/animations-v2.jsx` 의 `Easing` 실제 키만 쓴다. 로더가
`validateEasing` 으로 전수 검사하고 어긋나면 예외를 던진다 — 테스트가 같은 검사를 파이썬에서
선행 실행한다.

**스태거 상한 규약**: `stagger.icon`·`stagger.bar`·`stagger.step` 은 템플릿이 명시 `at` 을 주지
않을 때만 쓰이는 폴백이다. 이 셋을 기준보다 키우면 스틸 시각(마지막 settle + 0.8s)에
마지막 요소가 아직 등장 중일 수 있다. 그래서 4종 모두 이 셋을 기준값 이하로만 두고,
"무게감"은 지속시간으로만 표현했다.

---

## 3. 대비 실계산 (전수)

WCAG 2.1 상대 휘도로 `contrastPairs` 17쌍을 테마마다 전부 계산했다. 반투명 배경
(`extra.badgeBg`)은 `palette.bg` 위로 합성한 뒤 계산한다.

| 테마 | 검사 쌍 | 최소 | 중앙값 | 최대 | AA(4.5:1) |
| --- | --- | --- | --- | --- | --- |
| `hwax-blue` | 17 | 4.61 | 6.25 | 16.82 | 17/17 |
| `neutral-slate` | 17 | 4.75 | 7.36 | 15.53 | 17/17 |
| `warm-amber` | 17 | 4.81 | 6.03 | 14.92 | 17/17 |
| `deep-dark` | 17 | 5.76 | 10.01 | 15.95 | 17/17 |
| `fresh-teal` | 17 | 4.58 | 5.58 | 15.10 | 17/17 |

합계 68쌍(신규 4종) 전부 4.5:1 이상 — 대형 텍스트 완화(3:1)를 쓴 항목은 하나도 없다.
전체 표는 `uv run python tests/test_themes_tokens.py` 로 출력된다.

설계 중 실제로 미달이 나서 색을 고친 사례.

- `warm-amber` `blue2` `#B26A2A` → 소프트 앰버 위 4.07:1 미달 → `#A85417`(4.66) → 지면을
  더 깊은 크림으로 바꾸면서 다시 `#9E5218`(4.88)로 조정.
- `fresh-teal` `blue2` `#14887F` → 소프트 민트 위 3.79:1 미달 → 색상까지 옮겨
  `#0E6E86`(틸 블루, 4.95)로 교체. 강조색과 보조색이 서로 구별되면서 둘 다 통과하는 지점.

### 다크에서의 반전

`deep-dark` 는 명암이 뒤집히므로 17쌍을 값만 갈아끼울 수 없다. 특히 `extra.white` 는
"흰색"이 아니라 **"액센트 채움 위 전경색"** 으로 의미를 뒤집어 `#0A1420`(짙은 잉크)을 넣었다.
고채도 시안(`#4CD9E5`) 채움 위에 흰 글씨를 얹으면 1.9:1 로 결격이지만, 짙은 잉크를 얹으면
10.90:1 이 된다.

이 키는 `component` 에서 `chip.activeFg`·`tag.successFg`·`network.centerFg`·`converge.checkFg`·
`decision.fg` 로만 소비되고 흰 면(surface)으로는 쓰이지 않는다는 것을 코드에서 확인한 뒤
뒤집었다(`grep -o "theme\.color\.[A-Za-z]*" web/templates/*.jsx` 에 `white` 없음).
키 이름은 계약이라 유지한다.

---

## 4. 실렌더 검증 (OM_THEME 주입)

기존 템플릿 3종(`tpl.process`·`tpl.proof`·`tpl.closing`)의 프리뷰는 `hwax-blue` 경로를
하드코딩하고 있다(다른 워크플로 소유 파일이라 수정 불가). 그래서 `page.add_init_script` 로
`window.OM_THEME` 을 심고, 로더가 `window.OMX` 에 `themes` 를 노출하는 순간 세터가 걸려
`loadUrl` 을 `fromGlobal()` 로 감싸도록 훅을 걸었다. 페이지에서 되읽은 테마 `id` 가
주입값과 같은지도 검사한다(`test_injected_theme_is_the_one_consumed`).

- 12조합(4 테마 × 3 템플릿) 전부 **콘솔·페이지 오류 0**, 스테이지 1920×1080 원척 마운트.
- 스냅샷 → `web/tokens/_previews/{테마}/{템플릿}.png`.

### 육안 확인 — 4종이 실제로 달라 보이는가

1차 렌더에서는 **밝은 3종이 서로 구분되지 않았다.** 지면 색을 hwax-blue 수준으로 옅게 잡으니
화면 대부분이 흰 카드라 색조 차이가 큰 면에서 드러나지 않았다. 강조색만 다른 "같은 시리즈"였다.
채널 차 24 초과 픽셀 비율로 `neutral-slate` vs `fresh-teal` 이 **2.3%**(process),
**0.27%**(proof)에 그쳤다.

수정한 것.

- 지면 색조를 세 방향으로 확실히 벌렸다 — 무채색(`#F1F1F3`) / 크림(`#F8F0E4`) / 민트(`#E4F5F0`).
- `neutral-slate` 는 잉크·보조·라인까지 전부 무채색으로 돌려 파란 기를 제거하고, 강조색도
  로열 블루에서 저채도 딥 슬레이트(`#26334D`)로 내렸다.
- `warm-amber` 는 카드까지 웜 화이트(`#FFFDF9`)로, 도트 텍스처를 진한 베이지로.
- `fresh-teal` 은 카드를 순백으로 남겨 지면-카드 대비를 4종 중 가장 크게.

수정 뒤 육안 판정: **4종이 한눈에 구분된다.** 무채색+짙은 슬레이트 / 크림+테라코타 /
민트+틸 / 암전+시안. 같은 템플릿을 네 장 나란히 두면 색 체계뿐 아니라 카드가 뜨는 높이
(그림자)와 모션 리듬까지 다르게 읽힌다.

수치로 다시 확인한 두 축.

| 축 | 측정 | 결과 |
| --- | --- | --- |
| 면의 색조 분리 | 채널 차 6 초과 픽셀 비율 (평면에서는 6도 색조로 읽힌다) | 전 18쌍 **64.7~100%** (임계 50%) |
| 강조색 정체성 | `palette.blue` RGB 유클리드 거리 (기준 테마 포함 10쌍) | 최소 **72.8** (임계 60) |
| 다크 분리 | 스냅샷 평균 밝기 | deep-dark 20~36 vs 밝은 3종 231~239 |

채널 차 24 기준(도형·텍스트 색이 확실히 교체된 픽셀)으로는 밝은 3종끼리 0.3~26%,
다크 대 밝은 테마는 99.8% 이상이다. 밝은 테마끼리의 낮은 값은 결함이 아니라
"카드·텍스트 좌표는 공용이고 색조만 바뀐다"는 설계의 결과다 — 그래서 면 분리(6)와
강조색 거리, 두 축으로 나눠 검사한다.

---

## 5. 소비 방법

```js
// 빌드 산출물 — src/wdpipeline/build.py 가 window.OM_THEME 에 JSON 문자열을 주입
const theme = window.OMX.themes.fromGlobal();

// 프리뷰 단독 구동 — 동기 XHR 로드
const theme = window.OMX.themes.loadUrl('../../../web/tokens/fresh-teal.json');

// 사전 등록 후 id 로
window.OMX.themes.register('deep-dark', doc);
const theme = window.OMX.themes.load('deep-dark');
```

시나리오 문서의 `tokens_theme` 필드에 테마 id 를 쓰면 끝이다 — `build_render_package` 가
`web/tokens/{id}.json` 을 찾아 복사하고 `OM_THEME` 로 주입하므로 **파이프라인 코드 변경은 없다.**
4종으로 실제 빌드해 확인한 값.

| 테마 | 주입된 `OM_THEME.id` | 주입 페이로드 | 빌드 `tokens/` |
| --- | --- | --- | --- |
| `neutral-slate` | neutral-slate | 7,002 B | loader.jsx + neutral-slate.json |
| `warm-amber` | warm-amber | 6,964 B | loader.jsx + warm-amber.json |
| `deep-dark` | deep-dark | 7,128 B | loader.jsx + deep-dark.json |
| `fresh-teal` | fresh-teal | 6,981 B | loader.jsx + fresh-teal.json |

로더의 `MAX_THEME_BYTES`(64KB) 대비 11% 수준이다. 다만 파이프라인이 **테마를 스스로 고르는
규칙은 아직 없다** — 현재 규칙 기반 조립은 `hwax-blue` 를 고정으로 쓴다.

---

## 6. 다음 라운드에 남긴 것

- **오프닝·클로징 연출 다양화** — 이번 라운드는 색·모션 성격만 다뤘다. 영상 앞 8초/뒤 12초의
  구성 자체(`tpl.opening`·`tpl.closing`)는 여전히 각 1종이다.
- **테마 자동 추천** — 보고서 장르(재무/인사/기술/제안)에서 테마를 고르는 규칙은 각 module.yaml
  의 `in_scope`/`use_when` 에 문장으로만 남겼다. 파이프라인이 읽어 쓰는 코드는 아직 없다.
- **폰트 축** — 5종이 같은 Pretendard 를 쓴다. 폰트를 바꾸려면 글리프 폭 변화 때문에 각
  scene-template 의 `maxLength` 실측 역산을 다시 돌려야 한다. 별도 라운드가 필요하다.
- **문서형·세로 포맷 교차 검증** — 실렌더는 가로 16:9 템플릿 3종으로만 했다. `short-9x16`·
  `deck-doc-16x9`·`print-a4` 에서의 테마 적용은 확인하지 않았다.
