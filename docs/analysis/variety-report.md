# 조합 다양성 실증 보고 — 테마 5 × 오프닝 4 × 클로징 4

레이아웃 템플릿 17종이 도착했지만 그것만으로 자료가 달라 보이지 않았다. 병목은 **색 체계와
앞뒤 연출**이었다 — 테마 `hwax-blue` 1종, 오프닝 1종, 클로징 1종. 영상은 첫 8초와 마지막
12초가 인상을 정하는데 그 자리가 고정이면 무엇을 만들어도 같은 시리즈로 읽힌다.

이 문서는 이번 라운드에 추가된 테마 4종·오프닝 3종·클로징 3종을 **실제로 렌더해서** 다양성이
생겼는지 확인한 결과와, 언제 무엇을 고를지의 가이드다.

- 심의 회의록 — `data/meetings/20260729-033918_design_review_5-4-2_2417/minutes.md` (판정 **Conditional-Go**)
- 실측 원본 — `data/variety_check/{matrix_metrics,ax_contrast,motion_reach,full_result,accent_contrast}.json`
- 육안 대조표 — `data/variety_check/matrix/_contact_sheet.png` (20셀) · `data/variety_check/full/_compare_sheet.png` (3편 × 7씬)

---

## 1. 무엇을 어떻게 쟀나

세 축을 따로 쟀다. 색만 바뀐 것과 성격이 바뀐 것을 한 숫자로 뭉뚱그리면 답이 나오지 않기
때문이다.

| 축 | 지표 | 무엇을 가리나 |
| --- | --- | --- |
| 색 | **면 색조 분리율** — 채널 최대차 > 6 인 픽셀 비율 | 넓은 지면이 다른 색으로 칠해졌는가 |
| 성격 | **잉크 배치 분리율** = 1 − IoU — 색을 버리고 이진화한 잉크 마스크의 대칭차 ÷ 합집합 | 글자·도형이 **다른 자리**에 서는가 |
| 모션 | translateY 궤적 50ms 간격 실측 — 관측 dy · 이동 구간 · 오버슈트 최저점 | 등장이 실제로 다르게 움직이는가 |

잉크 지표를 정규화(1−IoU)한 이유. 잉크는 화면의 3~4%뿐이라 면적비로 보면 최대 7%대에서
포화한다. 합집합으로 나누면 "겹치는 잉크가 하나도 없다 = 1" 이 되어 배치 차이가 그대로 읽힌다.

---

## 2. 조합 매트릭스 — 전수 20장

`data/variety_check/matrix/` · 테마 5종 × 오프닝 4종을 같은 무대(1920×1080)·각 템플릿의 스틸
시각(4.80 / 5.40 / 5.75 / 6.60s)에 캡처. 콘솔·페이지 오류 **0건**, 씬 DOM 노드 10~18개.

대표 8~10 조합을 고르지 않고 전수를 뽑았다 — 표본을 고르는 순간 "어떤 조합이 안 달라
보이는가"라는 이 라운드의 질문을 표본이 미리 답해버린다. 실제로 결격 1건(§2.3)은 전수라서
드러났다.

### 2.1 색 축 (같은 오프닝 · 다른 테마 40쌍)

면 색조 분리율 **96.21 ~ 100.00%**. 최저는 `o-question`의 hwax-blue vs neutral-slate 96.21%.

| 오프닝 | 최소 | 중앙 | 최대 |
| --- | --- | --- | --- |
| `tpl.opening` | 99.00% | 99.76% | 100.00% |
| `tpl.o-statement` | 99.98% | 100.00% | 100.00% |
| `tpl.o-metric` | 99.98% | 100.00% | 100.00% |
| `tpl.o-question` | 96.21% | 96.83% | 100.00% |

### 2.2 성격 축 (같은 테마 · 다른 오프닝 30쌍) + 대조군

| 비교 | 잉크 1−IoU |
| --- | --- |
| 같은 테마 · **오프닝** 교체 (30쌍) | **85.73 ~ 99.51%** |
| 같은 오프닝 · **테마** 교체 (40쌍, 대조군) | **0.06 ~ 2.11%** |

40배 이상 차이다. **테마는 색과 모션을 칠하고, 오프닝이 구조를 바꾼다** — 이 분업이 픽셀에서
성립한다. 테마를 갈아도 글자는 같은 자리에 선다.

### 2.3 육안 판정

`_contact_sheet.png` 를 원척으로 본 결과다.

- **색은 확실히 갈렸다.** 무채(#F1F1F3) · 크림(#F8F0E4) · 딥네이비(#0B1220) · 민트(#E4F5F0)
  네 방향이 축소판에서도 즉시 구분된다. deep-dark 는 지면 극성 자체가 반대라 별개 브랜드로 읽힌다.
- **성격도 갈렸다.** 행을 세로로 훑으면 tpl.opening(중앙 정렬·배지·도트 장식) → o-statement
  (좌측 정렬 대형 문장·장식 0) → o-metric(초대형 숫자가 주인공, 제목은 킥커로 강등) →
  o-question(상단 질문 + 빈 원 + 하단 칩)로 화면의 무게중심이 매번 옮겨간다. 같은 자료의
  다른 옵션이 아니라 다른 자료로 보인다.
- **한 칸이 결격이다.** `neutral-slate` 의 강조어는 강조로 읽히지 않는다. `o-statement` 2행의
  "반박하지 않은"이 본문과 같은 색조로 보인다(`_accent_probe.png` 5테마 crop 대조).
  수치로는 강조 `#26334D` 대 잉크 `#21242B` 의 상호 대비 **1.23:1 · ΔRGB 37.5** — 나머지 넷은
  ΔRGB 91.8~158.3 이다. 지면 대비는 둘 다 AA 를 넘으므로(13.77 / 11.19) 게이트가 잡지 못한다.

---

## 3. 대비 실측 — 토큰 신고가 아니라 렌더 결과로

토큰의 `contrastPairs` 는 테마가 **스스로 신고한** 17쌍이다. 그걸 믿지 않고 20조합의 실제
그려진 텍스트 노드 **125개**를 DOM 에서 되읽어(computed color + 조상 추적 유효 배경)
WCAG 2.1 을 다시 계산했다. `data/variety_check/ax_probe.py` · `ax_contrast.json`.

| 테마 | 검사 노드 | 최소 대비 | AA 미달 |
| --- | --- | --- | --- |
| `hwax-blue` | 25 | 4.64:1 | 0 |
| `neutral-slate` | 25 | 4.75:1 | 0 |
| `warm-amber` | 25 | 4.81:1 | 0 |
| **`deep-dark`** | 25 | **6.35:1** | 0 |
| `fresh-teal` | 25 | 4.67:1 | 0 |

**다크 테마가 5종 중 하한이 가장 높다.** deep-dark 상세 — 92px 질문 15.95:1, 168px 시안
물음표 10.01:1(fill `#141C2E`), 34px 칩 8.84:1(fg `#4CD9E5` on `#162838`), 24px 각주 6.35:1.
검사 노드가 전부 24px 이상이라 대형 완화(3:1)만 넘으면 되는데도 **본문 기준 4.5:1 을 전부
넘겼다** — 완화에 기댄 항목 0건.

> 검증 범위는 오프닝 4종이다. 본문·클로징 템플릿까지의 확대는 심의 액션아이템으로 남았다.

---

## 4. 모션 성격은 절반만 도달한다

`data/variety_check/motion_probe.py` · `motion_reach.json`. 같은 요소의 translateY 를 50ms
간격으로 4초간 추적했다.

| 추적 대상 | 관측 dy (5테마) | 이동 구간 | 오버슈트 |
| --- | --- | --- | --- |
| `tpl.opening` 배지 — `rise(theme,t,at)` 무인자 | **20 / 24 / 26 / 28 / 32px (5종)** | 0.45~0.75s (폭 0.30s) | fresh-teal −2.79px |
| `tpl.o-question` promise — `enter(…,p.promise.dur,18)` | 18px **고정** | 0.45~0.60s (폭 0.15s) | fresh-teal −1.8px |
| `tpl.o-metric` title — `enter(…,p.title.dur,14)` | 14px **고정** | 0.40~0.50s (폭 0.10s) | fresh-teal −1.4px |

원인은 소스에 있다. `enter()` 정의는 `dur == null` 일 때만 `theme.motion.rise.dur/dy` 를
쓰는데, `omx-openings.jsx` 의 호출 4곳과 `omx-closings.jsx` 의 14곳이 **전부 명시 인자**를
넘긴다. 신규 6종이 테마에서 가져가는 모션 성격은 `ease` 하나뿐이다 — 탄력(오버슈트)은
살아남았고 무게감(지속시간·이동거리)은 닿지 않는다.

**정착 시각은 지속시간 순서와 어긋난다.** deep-dark(토큰 1.00s)가 1.1s 에 멈추고
warm-amber(토큰 0.85s)가 1.2s 에 멈춘다 — easeOutQuart 는 꼬리가 빨리 붙고 easeOutSine 은
늦게 붙기 때문이다. 프리셋을 고를 때는 선언 지속시간이 아니라 아래 관측 정착 시각을 보라.

| 테마 | 토큰 rise | 관측 정착 |
| --- | --- | --- |
| `neutral-slate` | 0.60s / 20px / easeOutCubic | **0.9s** |
| `hwax-blue` | 0.70s / 26px / easeOutCubic | 1.0s |
| `fresh-teal` | 0.62s / 28px / easeOutBack | 1.0s (−2.79px 오버슈트) |
| `deep-dark` | 1.00s / 32px / easeOutQuart | 1.1s |
| `warm-amber` | 0.85s / 24px / easeOutSine | **1.2s** |

---

## 5. 완주 영상 — 같은 보고서, 세 편

입력 `examples/reportarchive/report_sample.json`(구조 12블록). 씬 순서·씬 길이·가운데 5씬은
통제 변인으로 고정하고 **테마·오프닝·클로징만** 바꿨다. 셋 다 7씬 · 90.0s · pageerror 0 ·
QA passed.

| 편 | 조합 | 산출 |
| --- | --- | --- |
| **base** (대조군) | hwax-blue + `tpl.opening` + `tpl.closing` | `data/variety_check/full/base/` |
| **A** 기술 서사 | deep-dark + `tpl.o-question` + `tpl.x-summary` | `data/renders/variety_A/variety_A.mp4` |
| **B** 재무·규정 | neutral-slate + `tpl.o-metric` + `tpl.x-next` | `data/renders/variety_B/variety_B.mp4` |

### 5.1 나란히 놓으면 다른 자료로 보이는가 — 절반만

씬별 잉크 배치 1−IoU.

| 비교 | 1씬(오프닝) | 7씬(클로징) | 가운데 5씬 |
| --- | --- | --- | --- |
| A vs B | 98.01% | 93.36% | **1.59 ~ 3.44%** |
| base vs A | 98.94% | 99.99% | 1.86 ~ 3.92% |
| base vs B | 91.37% | 95.56% | **0.30 ~ 0.57%** |

**앞뒤 두 씬은 확실히 다른 자료다. 가운데 다섯 씬은 같은 자리에 같은 글자가 선다.**
자산 탓이 아니라 배선 탓이다 — `formats/wide-16x9` 의 `template_pool` 에서 problem·concept 은
후보가 1종, process·differentiator·proof 도 2종뿐이라 레이아웃 17종이 본문 역할에 닿지 못한다.

### 5.2 밝은 테마끼리는 본문에서 덜 벌어진다

base(hwax-blue) vs B(neutral-slate) 의 본문 씬 면 분리율 — proof 57.51% · process 63.56% ·
differentiator 73.95% · problem 87.50% · concept 92.29%. 이번 실측 전체(매트릭스 40쌍
96~100%, 완주 A/B 99.95~100%)에서 가장 낮은 대역이다. 흰 카드가 화면을 덮는 씬에서는
지면 색조의 차이가 가려진다.

### 5.3 게이트 회귀 없음

3편의 게이트 결과가 **동일**하다 — info 1(게이트 3 `undeclared-pair`, 개념 씬) +
warning 1(게이트 5 `text-overflow`, `'종합보고 (Compo…'` scroll 196x29 > client 192x29).
대조군 hwax-blue 에도 같은 2건이 뜬다. 신규 테마·오프닝·클로징이 만든 문제가 아니다.

---

## 6. 카탈로그

### 6.1 테마 5종

| 테마 | 지면 | 강조 | 그림자 | 모션 성격 | 최소 대비(렌더) |
| --- | --- | --- | --- | --- | --- |
| `hwax-blue` (기준) | `#F6F7FA` 차가운 흰 | `#1428A0` 로열 블루 | 중간 | easeOutCubic + pop easeOutBack, 정착 1.0s | 4.64:1 |
| `neutral-slate` | `#F1F1F3` 무채색 | `#26334D` 딥 슬레이트 | 가장 얕게 | 절제 — 팝도 오버슈트 없음, 정착 0.9s(최속) | 4.75:1 |
| `warm-amber` | `#F8F0E4` 크림 | `#9A4A12` 테라코타 | 가장 크게, 갈색 | 부드럽게 — easeOutSine, 정착 1.2s(최지연) | 4.81:1 |
| `deep-dark` | `#0B1220` 딥 네이비 | `#4CD9E5` 시안 / `#B6E86A` 라임 | 검정 + 시안 글로우 | 무게감 — easeOutQuart, 정착 1.1s | **6.35:1** |
| `fresh-teal` | `#E4F5F0` 민트 | `#0B7168` 딥 틸 | 중간, 틸 | 탄력 — 전 구간 easeOutBack 오버슈트(−2.79px) | 4.67:1 |

토큰 3층 구조·`contrastPairs` 85쌍 자체 신고·프리셋 실값은 `docs/analysis/theme-catalog.md`.

### 6.2 오프닝 4종

| 템플릿 | nat | 각인 장치 | 데이터 상한 |
| --- | --- | --- | --- |
| `tpl.opening` | 8s | 배지 → 112px 타이틀 → 서브 → 도트 라인 순차 등장. 장식이 있는 정공법 | title 3분할(pre 14 / accent 12 / post 14), subtitle 40 |
| `tpl.o-statement` | 8s | **문장이 곧 화면.** 실루엣(opacity 0.16)으로 놓인 96~120px 문장이 단어 단위 좌→우 점등. 장식 0, 강조어는 **색만** 다름 | lines 2~3행 × 18자, accent 12, source 30 |
| `tpl.o-metric` | 8s | **숫자를 먼저 던진다.** 220px 수치 카운트업(localTime 순수 함수) → 의미 36px → 제목 26px 킥커. 크기 위계 역전 | value 0~999999, suffix 3, meaning 34, title 24 |
| `tpl.o-question` | 9s | **답을 비워 둔다.** 92px 질문 → Ø300 빈 원 + 168px 물음표 → 예고 + 항목 칩 3개 | question 1~2행 × 18자, promise 24, topics 3개 고정 × 10자 |

### 6.3 클로징 4종

| 템플릿 | nat | 마무리 전략 | 마지막에 남는 것 |
| --- | --- | --- | --- |
| `tpl.closing` | 12s | 2페이즈 전환 — 통계 트리오가 **퇴장한 뒤** 타이틀 + CTA 필 | 슬로건과 행동 유도 (주체·시점 없음) |
| `tpl.x-summary` | 14s | **누적** — 퇴장이 없다. [번호 + 회수 문장 + 근거 수치] 3~5행이 쌓임 | 다룬 근거 전부 · 질의응답 대기 화면 겸용 |
| `tpl.x-quote` | 10s | **삭감** — 킥커·타이틀·푸터 필드가 스키마에 아예 없다 | 92px 한 문장. `tpl.o-statement`(96~120px)와 수미상관 |
| `tpl.x-next` | 14s | **이관** — `when`·`owner`·`what` 을 스키마가 required 로 요구 | 결정 1건 + 액션아이템 3~4건 표 |

---

## 7. 언제 무엇을 쓰나 — 추천 조합

완주 2편은 이 표의 두 행(재무·기술)을 **그대로 실행해서 검증**한 것이다.

| 보고서 성격 | 테마 | 오프닝 | 클로징 | 왜 |
| --- | --- | --- | --- | --- |
| **재무 · 감사 · 규정** | `neutral-slate` | `tpl.o-metric` | `tpl.x-next` | 브랜드 색을 드러내지 않는 무채 지면. 숫자가 먼저 서고, 마무리는 주체·시점이 박힌 액션아이템 표. 정착 0.9s 의 절제된 모션 |
| **기술 · 데이터 서사** | `deep-dark` | `tpl.o-question` | `tpl.x-summary` | 암전 대형 스크린·부스 루프에 맞고 대비 하한이 가장 높다(6.35:1). 질문에서 출발해 근거를 쌓고, 마지막 화면이 그대로 질의응답 대기표 |
| **경영 브리핑 · 의사결정 요청** | `hwax-blue` | `tpl.o-statement` | `tpl.x-quote` | 선언으로 열고 한 문장으로 닫는 수미상관. 96~120px ↔ 92px 로 타이포 층위가 한 계단 대응 |
| **인사 · 조직문화 · 교육** | `warm-amber` | `tpl.opening` | `tpl.closing` | 크림 지면 + 큰 갈색 그림자. 사람이 주인공인 서사에 장식 있는 정공법 오프닝과 CTA 마무리 |
| **신사업 · 혁신 제안 · 파일럿 성과** | `fresh-teal` | `tpl.o-metric` | `tpl.x-next` | 오버슈트 탄력 모션 + 순백 카드가 뜨는 민트 지면. 성과 수치로 열고 다음 6주로 닫는다 |
| **조사 · 진단 · 감사 보고** | `hwax-blue` 또는 `deep-dark` | `tpl.o-question` | `tpl.x-summary` | 질문에서 출발하는 서사. 결론이 한 문장으로 압축되지 않는 다항 결론에 적합 |

### 조합 금기 (실측 근거)

1. **`neutral-slate` + `tpl.o-statement` 금지.** 이 오프닝의 강조는 색이 유일한 신호인데
   neutral-slate 에서 강조색과 잉크가 1.23:1(ΔRGB 37.5)로 분리되지 않는다. 강조가 사라진다.
   `tpl.o-metric` 처럼 강조색을 한 덩어리에만 쓰는 오프닝은 지금도 읽힌다.
2. **`hwax-blue` 와 `neutral-slate` 를 연속 상영하지 말 것.** 본문 씬 면 분리율이
   57.51~92.29% 로 5종 중 가장 낮다. 카드가 넓은 씬에서 두 지면이 구분되지 않는다.
3. **짧은 씬(nat ≤ 8s)에 `deep-dark` + 스태거 큰 템플릿 조합 주의.** 관측 정착이 1.1s 로
   가장 늦은 축이라 마지막 요소가 스틸 시각까지 등장을 못 끝낼 여지가 있다. 현행 자산에서는
   발생하지 않았으나 dur 개방(심의 액션아이템 F2) 시 재검증 대상이다.
4. **`tpl.x-quote` 는 결론이 한 문장으로 압축될 때만.** 다항 결론을 억지로 한 문장에 넣으면
   근거가 사라진 슬로건이 된다. 그 경우 `tpl.x-summary`.

### 오프닝↔클로징 수미상관 짝

| 오프닝 | 짝 | 대응 방식 |
| --- | --- | --- |
| `tpl.o-statement` (96~120px 선언) | `tpl.x-quote` (92px 한 문장) | 같은 타이포 층위 한 계단 아래. 여는 문장과 닫는 문장 |
| `tpl.o-question` (답을 비움) | `tpl.x-summary` (근거를 쌓음) | 비운 자리를 마지막에 채운다 |
| `tpl.o-metric` (수치를 던짐) | `tpl.x-next` (수치를 일정으로) | 던진 숫자가 담당·시점으로 착지 |
| `tpl.opening` (정공법) | `tpl.closing` (CTA) | 현행 기본 쌍 |

---

## 8. 심의 판정 — Conditional-Go

`data/meetings/20260729-033918_design_review_5-4-2_2417/` · 14턴 · 인용 52건 ·
참가 vis-color-brand / vis-typographer / mot-motion-director / ux-accessibility + 모더레이터.

| 질문 | 판정 |
| --- | --- |
| ① 각 테마가 고유한 성격을 갖는가 | **부분 성립 (4종 중 3종)** — 색·그림자·이징은 갈렸으나 neutral-slate 은 강조 정체성 결격 |
| ② 다크 테마의 대비가 실제로 안전한가 | **예** — 렌더 노드 125개 AA 미달 0, deep-dark 하한 6.35:1 로 5종 최고 |
| ③ 오프닝 3종의 각인 전략이 정말 다른가 | **예** — 오프닝 교체 85.73~99.51% vs 테마 교체 0.06~2.11% |
| ④ 모션 성격 차이가 체감되는가 | **기존 씬에서만** — 신규 6종은 dy 고정·이동 폭 절반 이하, ease 만 살아남음 |

**Finding 5건 · 액션아이템 6건 · 미해결 쟁점 2건.**

| ID | 심각도 | 내용 |
| --- | --- | --- |
| F1 | **blocking** | `neutral-slate` 강조색이 본문 잉크와 분리되지 않는다 (1.23:1 · ΔRGB 37.5) — 이 테마만 승격 보류 |
| F2 | major | 테마 모션의 dur·dy 가 신규 오프닝·클로징 6종에 닿지 않는다 (`enter()` 호출 18곳 전부 명시 인자) |
| F3 | minor | "무게감 = 지속시간" 서술과 관측 정착 순서가 역전 (deep-dark 1.00s→1.1s vs warm-amber 0.85s→1.2s) |
| F4 | major | 완주 2편의 본문 5씬 배치가 사실상 동일 (1−IoU 0.30~3.44%) — 다음 병목은 `wide-16x9` 본문 역할 풀 |
| F5 | minor | `hwax-blue` × `neutral-slate` 는 본문 씬 면 분리 57.51~92.29% 로 최저 — 조합 금기 필요(§7에 반영) |

미해결 — 테마 `contrastPairs` 17쌍 목록이 템플릿 증가에 확장 취약(게이트 3 `undeclared-pair`가
대조군 포함 3편 전부에 발생, 이번엔 7.99~9.59:1 로 안전) / 대비 실측 범위를 본문·클로징
템플릿까지 확대.

> 이 라운드는 첫 8초와 마지막 12초를 다양화했고 그 목표는 달성했다. 가운데 70초는 아직
> 한 종류다.

---

## 9. 재현

```bash
uv run python data/variety_check/matrix_driver.py        # 20조합 스냅샷 + 색/성격/모션 집계
uv run python data/variety_check/ax_probe.py             # 렌더 텍스트 노드 125개 WCAG 재계산
uv run python data/variety_check/motion_probe.py         # translateY 궤적 50ms 실측
uv run python data/variety_check/full_driver.py          # 완주 3편 빌드·렌더·게이트·mp4
uv run python data/variety_check/review_driver.py        # design_review 실구동
```

`full_driver.py` 는 `formats/wide-16x9` 를 수정하지 않는다 — `data/variety_check/formats/` 의
실증 전용 사본에서 `template_pool` 의 opening·closing 풀만 넓혀 `WDA_FORMATS_ROOT` 로 주입한다
(본 포맷은 타 워크플로 소유).
