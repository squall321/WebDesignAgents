# 잔여 마감 통합 실증 — 포맷 재사용 · 하이브리드 PPTX · 오프라인 렌더

세 건의 완료 주장을 **읽기·실행만으로** 재현·검증한 기록이다. 소스는 한 줄도 고치지 않았다.
모든 산출물은 `data/closure_check/` 아래에 있고, 이 문서의 모든 수치는 그 파일에서 나온다.

| 항목 | 결과 | 근거 파일 |
| --- | --- | --- |
| 포맷 재사용 (2차 세로 제작) | **성립** — 19턴 → 7턴, 재결정 필요 도메인 값 0건 | `data/closure_check/format_reuse/` |
| 하이브리드 PPTX 편집 가능성 | **성립** — 텍스트박스 55/125개, 왕복 편집 6/6 반영·서식·좌표 보존 | `data/closure_check/pptx/` |
| 오프라인 렌더 (egress 0) | **성립** — 슬라이드 이미지 5/5 바이트 일치, 프레임 923/1104 완전 일치 | `data/closure_check/offline/` |
| 외부 참조 정적 검사 (전 빌드) | 현행 빌드 위반 0건 · **옛 빌드 잔재 3건** | `data/closure_check/offline/external_refs_scan.json` |
| 전체 회귀 | (본문 §5) | `data/closure_check/pytest_full.log` |

---

## 1. 포맷 재사용 실증 — 같은 포맷, 다른 보고서

### 1.1 무엇을 물었나

승격된 `short-9x16` 포맷으로 **새 제작을 시작할 때 실제로 쉬워지는가.**
쉬워짐을 주장하려면 "무엇이 줄었는가"를 말할 수 있어야 하므로, 먼저 **줄일 수 없는 것부터** 확정했다.

### 1.2 먼저 확인한 사실 — 턴 수는 프리셋이 못 줄인다

`scenario_build` 회의의 턴 수는 라운드 템플릿 형상 × 참가자 수로 **결정론적으로 고정**된다
(`MeetingEngine._expected_turns`, `MEETING_TEMPLATES[scenario_build]`).

| 참가자 | structure_diverge | cross_rebuttal | converge_timeline | verdict | 합계 |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 1인 | 1 | 1 | 4 | 1 | **7** |
| 2인 | 1 | 2 | 6 | 1 | 10 |
| 3인 | 1 | 3 | 8 | 1 | 13 |
| 5인 | 1 | 5 | 12 | 1 | **19** |
| 7인 | 1 | 7 | 16 | 1 | 25 |

`cross_rebuttal`·`converge_timeline` 은 `allow_early_close=False` 라 조기 종료도 불가능하다.
**1차 심의의 19턴은 "논의가 많아서"가 아니라 "참가자가 5인이어서" 나온 수다.**
따라서 프리셋이 줄일 수 있는 것은 **참가자 수와 라운드당 결정 부하**이지 라운드 형상이 아니다.
이 구분을 세우지 않으면 "프리셋 덕에 턴이 줄었다"는 말이 인과를 잘못 짚는다.

### 1.3 프리셋이 흡수한 결정 — 17건, 1차 19턴 중 16턴이 관여

`format_presets_briefing("short-9x16")` 출력(2,050자 / 21줄, `format_reuse/briefing_used.md`)을
1차 심의 전문(17,461자, `format_reuse/short_v1_turns.md`)과 대조했다.
1차가 확정한 도메인 결정 **17건이 전부 프리셋·골든·교훈 칸에 정본화**되어 있고,
그 결정들이 소비한 1차 턴은 19턴 중 **16턴**이다 (`format_reuse/turn_cost.json`).

| 1차가 결정한 것 | 지금 어디에 있나 | 1차에서 쓴 턴 |
| --- | --- | --- |
| 심의 참가자 5인 구성 · 의제 4건 | `presets.deliberation` | T01 |
| 청중 재정의 / tone 재정의 | `lessons#2` | T04, T07 |
| 가로 7역할 → 세로 5역할 흡수·폐기 | `lessons#4` | T02 |
| 카피 자수 상한 19종 (vtpl 4종 schema 역산) | `presets.copy_guide` | T03, T09, T15 |
| 가로본 축약 금지 · 복붙 대조 방법 | `lessons#3` | T01, T15, T19 |
| 씬별 등장 정착 시각(브라우저 실측) | 골든 `schedule_probe.json` | T05 |
| dur 하한 공식 max(낭독 예산, 정착+판독) | `lessons#5` | T05, T11 |
| 씬별 확정 dur 5값 · Σ46.0초 | `presets.dur_plan` | T05, T07, T11, T17 |
| 총 길이는 목표 60을 채우지 않는다 | `lessons#1` | T04, T05, T07 |
| stills '정착+0.8' 규칙과 5값 | 골든 `scenario.json` | T05, T11, T17 |
| 낭독 예산 vs 실측 격차 → 무음 구조적 하한 | `lessons#6` + `presets.narration` | T06, T12, T18, T19 |
| 씬별 무음 상한 3.6초 | `presets.narration.max_silence` | T12, T16 |
| 하단 1700px 금지대 | `lessons#7` | T04 |
| 전 씬 cut · frame-match | 골든 `scenario.json` | T05, T17 |
| content 키를 역할명으로 잡는 규약 | 골든 `scenario.json` | T08 |

**프리셋이 흡수하지 못하는 것** — core_message, 5역할에 어느 조각을 앉히는가, 씬 이름,
문안 27~48필드 전문, 대본 5편. 원천이 바뀌면 매번 새로 해야 하는 일이고, 그것이 정상이다.

특히 값이 컸던 세 자리를 짚는다.

- **T03(CP)** 은 vtpl 4종 `schema.json` 을 열어 96px·본문폭 912px 같은 역산 근거까지 되짚으며 상한을 재선언했다. 2차는 `presets.copy_guide` 19키를 그대로 적용해 **27필드를 자동 검사**로 대체했다.
- **T05(MO)** 는 브라우저에서 세로 템플릿 4종의 등장 스케줄을 실측했다. 2차는 **템플릿이 같으므로 정착 시각이 같다**는 근거로 stills 5값을 재사용했다 — 브라우저 재실측 0회.
- **T06+T12(NR)** 는 대본 5편을 합성해 재고, CTA 교체 후 재합성까지 했다. 2차는 예산·무음 상한을 인용한 뒤 **검증 목적으로만** 1회 실합성했다.

### 1.4 2차 제작 — 새 원천, 7턴, 완주

원천을 바꿨다. `data/pipeline/wc_md/report.norm.json` = **「심의 플랫폼 도입 검토」**(조각 12건).
1차와 같은 보고서를 다시 쓰면 "쉬워졌다"가 아니라 "베꼈다"가 되므로, 완전히 다른 문서를 골랐다.

- 회의 `80d5f0d1-a44d-4e0a-88c3-147042e75deb` — `scenario_build`, 참가자 **ST 1인**, **7턴**, 판정 **Go**
  (`format_reuse/meetings/20260729-003904_.../minutes.md`)
- 참가자를 1인으로 줄인 근거는 "CP·AU·MO·NR 의 도메인 결정이 전부 프리셋에 있어 재소집 사유가 없다"이며,
  개회 선언에 **"프리셋에서 벗어나는 값을 쓰려면 그 소유자를 다시 부른다"** 를 못박아 두었다.

| | 1차 short_v1 | 2차 short_v2 |
| --- | ---: | ---: |
| 참가자 | 5인 | 1인 |
| 턴 | 19 | **7** (−63%) |
| 발언량(공백 제외) | 17,461자 | **4,521자** (−74%) |
| 잠정 조건 | 5건 (사이클 2에서 폐쇄) | **0건** |
| 판정 | Conditional-Go | **Go** |

### 1.5 프리셋 값이 다른 원천에서도 성립하는가 — 실측

프리셋을 **인용만 하고 검증을 건너뛰면** 재사용이 아니라 태만이다. 세 축 모두 실측했다.

| 축 | 프리셋 값 | 2차 실제 | 판정 |
| --- | --- | --- | --- |
| 자수 상한 | `copy_guide` 19키 | 27필드 검사, 초과 **0건**, 최고 사용률 **75%**, 말줄임 **0건** | 성립 |
| 구간 예산 | 6.2/11.2/11.6/9.6/7.4 (Σ46.0) | 전 구간 차이 **0.0초** | 성립 |
| 낭독 예산 | 5.5자/초, 무음 상한 3.6초 | 예산 위반 0건, 씬 최대 무음 **3.40초** | 성립 |

**TTS 실합성**(`chatterbox`, VoiceRecorder :8177, `format_reuse/tts_probe_v2.json`) —

| 씬 | 자수 | 예산(자/5.5) | dur | 실낭독 | 실측 속도 | 무음 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 후킹 | 29 | 5.27 | 6.2 | 4.08 | 7.11 | 2.12 |
| 문제 | 57 | 10.36 | 11.2 | 7.80 | 7.31 | 3.40 |
| 계획 | 59 | 10.73 | 11.6 | 8.28 | 7.13 | 3.32 |
| 목표 | 51 | 9.27 | 9.6 | 6.76 | 7.54 | 2.84 |
| 시작 | 36 | 6.55 | 7.4 | 6.20 | 5.81 | 1.20 |
| 합계 | 232 | — | **46.0** | **33.12** | 7.00 | **12.88 (28.0%)** |

1차는 249자 / 33.40초 / **27.4%** 였다. **원천이 완전히 다른데 무음률이 0.6pt 안에 들어왔다** —
`presets.dur_plan` 이 원천 독립적으로 성립한다는 뜻이다.

### 1.6 산출물

`validate_scenario` **0건** → 빌드 → 렌더 → QA 게이트.

- mp4 46.0s / 24fps / **1,104프레임** (1080×1920)
- pptx **5장** — image 1,176,771B · hybrid 947,057B (텍스트박스 55, 제외 0)
- QA 게이트 **error 0 / warning 0 / info 1** — info 1건은 게이트 3 `undeclared-pair`
  (`#3D53C6 / #F6F7FA`, 대비 6.03:1)로, **골든 short_v1 의 QA 리포트와 완전히 같은 1건**이다.
- 승격 원장(샌드박스 `format_reuse/formats_sandbox/`) — `record_usage("short-9x16","short_v2")` →
  usage_count **1 → 2**, 같은 run_id 재기록은 `recorded=false` 로 무시. 실제 `formats/` 는 건드리지 않았다.

### 1.7 이 실증이 잡아낸 결함 3건

**(1) 2차 심의의 자기 보고가 틀렸다 — 대본 재활용 1건.**
ST 는 R1에서 "1차와 완전히 겹치는 문자열은 0건"이라고 보고했으나, 폐회 후 자동 대조(`format_reuse/copy_overlap.json`)
결과 **목표 씬 대본 도입부 "숫자 하나만 보십시오."가 1차 근거 씬 대본과 그대로 같다.**
나머지 겹침은 스키마 열거값(`primary`/`solution`/`up`/`%`), 역할 유래 씬 이름(후킹·문제·시작),
프리셋 상속값(tone "숏폼 직설", audience "…실무자 (모바일 피드)")으로 전부 설명된다.
1차 심의는 이 대조를 CP 에게 한 턴을 통째로 시켰는데(T15), 2차는 사람을 뺐으면서 **그 검사를 자동화로 대체하지 않았다.**
→ `copy_guide` 준수 검사에 **직전 산출물 대조**를 편입해야 한다. 지금은 프리셋 재사용이 문안 재사용으로 새는 구멍이 있다.

**(2) `lessons#5` 의 dur 하한 공식에 항이 빠져 있다.**
교훈은 `dur ≥ max(낭독 예산, 정착+판독)` 이라고 적혀 있다. 그러나 게이트 2는 `|dur − nat| / nat ≤ 0.15`
(스트레치 한계)를 함께 본다. 대본이 가벼운 원천에서는 이 항이 지배한다 — 예컨대 문제 씬 대본이 47자면
낭독 예산 8.55초·정착+판독 8.10초라 교훈의 공식은 8.6초를 허용하지만, nat 12초의 −28%라 게이트가 깨진다.
**실제 하한은 `max(낭독 예산, 정착+판독, nat×0.85)`** 이다. 2차는 `dur_plan` 을 그대로 써서 부딪히지 않았다.

**(3) `lessons#6` 의 "대본 증량은 역효과"가 조건부다.**
교훈은 예산(5.5자/초)이 실측(7.2자/초)보다 느려서 자수를 늘리면 무음이 자당 +0.043초 늘어난다고 적었다.
이는 **낭독 예산이 dur 하한을 지배할 때만** 참이다. 스트레치 하한(nat×0.85)이 지배하면 dur 이 고정되므로
자수를 늘릴수록 무음은 **줄어든다.** 어느 항이 지배하는지를 먼저 판정하지 않으면 교훈이 반대 방향으로 작동한다.

---

## 2. 하이브리드 PPTX 편집 가능성 실증

### 2.1 image / hybrid 대조표

같은 빌드를 두 모드로 내보냈다 (`pptx/export_both_modes.py`, `pptx/export_summary.json`).

| 산출물 | 모드 | 슬라이드 | 텍스트 프레임 | 그림 | 파일 크기 | 소요 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| short_v1 (1080×1920) | image | 5 | **0** | 5 | 1,200,621 B | 1.8 s |
| short_v1 | hybrid | 5 | **55** | 5 | **945,834 B** (−21.2%) | 1.6 s |
| delib_v2 (1920×1080) | image | 8 | **0** | 8 | 1,825,555 B | 1.6 s |
| delib_v2 | hybrid | 8 | **125** | 8 | **1,414,647 B** (−22.5%) | 1.6 s |
| short_v2 (1080×1920) | image | 5 | 0 | 5 | 1,176,771 B | — |
| short_v2 | hybrid | 5 | 55 | 5 | 947,057 B (−19.5%) | — |

**슬라이드 수는 동일**하고 **파일은 오히려 20% 작아진다** — 배경에서 글자를 뺀 만큼 PNG 가 잘 압축된다.
소요 시간 차이도 없다(±0.2s). 즉 hybrid 를 쓰는 데 드는 비용이 없다.

### 2.2 왕복 편집 — python-pptx 로 열고 고치고 저장하고 다시 열기

세로 3건 · 가로 3건, 총 6건을 편집했다 (`pptx/dump_and_roundtrip.py`, `pptx/roundtrip.json`).

| 문서 | 슬라이드 | 도형 | 편집 | 재개봉 반영 | 서식 보존 | 좌표 보존 |
| --- | ---: | --- | --- | :-: | :-: | :-: |
| short_v1 | 1 | `wda-title-1` | 최신본 → 원본만 | ✅ | ✅ 48pt/bold/#1428A0 | ✅ |
| short_v1 | 2 | `wda-subtitle-3` | 최신본이 메일함에 숨는다 → 최신본이 어디에도 없다 | ✅ | ✅ 23pt/bold/#101B3E | ✅ |
| short_v1 | 4 | `wda-title-3` | 100 → 97 | ✅ | ✅ 160pt/bold/#1428A0 | ✅ |
| delib_v2 | 1 | `wda-title-1` | 한 번만 → 딱 한 번 | ✅ | ✅ 56pt/bold/#1428A0 | ✅ |
| delib_v2 | 2 | `wda-label-9` | 게시판마다 따로 도는 사본 → …흩어지는 사본 | ✅ | ✅ 15.5pt/bold/#101B3E | ✅ |
| delib_v2 | 3 | `wda-body-15` | 모든 보고서가 여기서 태어난다 → …시작한다 | ✅ | ✅ 12.5pt/#57607A | ✅ |

- **편집 전 문자열 잔존 0건** — 배경 이미지에도 원문이 남아 있지 않다(§2.3).
- **형제 run 보존** — 슬라이드 1 제목의 강조 run 하나만 고쳤을 때 나머지 두 run 의 색이 유지된다.
  `보고서는 (#101B3E) / 딱 한 번 (#1428A0) / 작성한다 (#101B3E)` — 강조 색 구조가 살아 있다.
- **발표자 노트 13/13 슬라이드 일치** — 편집·재저장 후에도 내레이션 노트가 그대로다.
- **image 모드 대조군** — 같은 편집 6건 중 **적용 0건**. 텍스트 프레임이 아예 없으므로 고칠 대상이 없다.
  이것이 hybrid 의 존재 이유를 가르는 대조다.

### 2.3 배경에 글자가 이중 인쇄되지 않았는가

텍스트가 상자로 올라왔는데 배경에도 남아 있으면 편집 시 글자가 겹쳐 보인다.
각 텍스트 상자 영역의 배경 밝기 표준편차를 두 모드에서 비교했다 (`pptx/background_ink_check.py`).

| 문서 | 상자 수 | hybrid 배경 std 평균 | image 배경 std 평균 | 잉크가 줄지 않은 상자 |
| --- | ---: | ---: | ---: | ---: |
| short_v1 | 55 | **1.51** | 59.16 | **0** |
| delib_v2 | 125 | **5.43** | 59.47 | **0** |

잔여값이 큰 상자는 전부 **채움·테두리를 가진 상자**다 — CTA 필("내 공간에서 써보기", hyb 29.16),
절차 단계 배지("01"~"06", hyb ≈46.8). 글리프는 사라지고 필·배지는 남았다.
`visibility:hidden` 대신 글자색만 투명으로 내린 설계 결정이 실제로 그렇게 동작한다는 확인이다.

### 2.4 텍스트 채택률

| 문서 | 채택 | 제외 | 제외 사유 | 눈에 보이는데 제외된 것 |
| --- | ---: | ---: | --- | ---: |
| short_v1 | 55 | 0 | — | 0 |
| short_v2 | 55 | 0 | — | 0 |
| delib_v2 | 125 | 14 | 전부 `opacity` | **1** |

delib_v2 의 제외 14건 중 13건은 **불투명도 0**(해당 still 시각에 아직 등장하지 않았거나 사라진 요소)이라
배경에도 없고 잃은 것이 없다. 나머지 1건만이 실제 손실이다 —
개념 씬 27.6초의 `"복사가 아니라 연결로 보고가 흐른다"`(opacity **0.85**).
누적 불투명도 임계 0.95 에 걸려 상자가 되지 못했고, 배경 이미지에만 남는다.
**세로 무대(short_v1·short_v2)는 손실 0**이다.

---

## 3. 오프라인 렌더 실증 — 독립 재현

C 는 가로(`delib_v2`)를 오프라인 렌더했다. 여기서는 **세로(`short_v1`)** 를 골라 독립 재현했다.
같은 것을 다시 돌리면 재현이 아니라 반복이므로, 무대가 다른 쪽을 택했다.

### 3.1 격리 확인

```text
apptainer exec --cleanenv --net --network=none deploy/apptainer/wda-render.sif …
  1.1.1.1:443          → 차단 (OSError: Network is unreachable)
  cdn.jsdelivr.net:443 → 차단 (gaierror: Temporary failure in name resolution)
  8.8.8.8:53           → 차단 (OSError: Network is unreachable)
  127.0.0.1 바인드      → OK (('127.0.0.1', 37601))
```

빈 네트워크 네임스페이스에서 egress 는 물리적으로 불가능하고, 정적 서버가 쓰는 루프백은 살아 있다.

### 3.2 렌더 결과

`WDA_HOST_DATA_DIR=data/closure_check/offline/data scripts/render-offline.sh short_v1` — exit 0.
(골든을 덮어쓰지 않도록 빌드 사본을 별도 data 루트에 두고 바인드했다.)

- mp4 2,210,376 B / 1,104프레임 · pptx 1,199,799 B / 5장

### 3.3 호스트 렌더와 대조

**PPTX — 내용 완전 일치.**
zip 멤버 64개 전부 sha256 동일. 슬라이드 배경 이미지 **5/5 바이트 일치**.
파일 전체 sha256 은 다르지만 이는 zip 메타데이터(타임스탬프) 차이이며 내용 차이가 아니다.

**MP4 — 렌더는 동일, 인코딩만 다르다.**
`ffmpeg psnr` 전 프레임 비교 (`offline/psnr_stats.txt`):

| 항목 | 값 |
| --- | ---: |
| 총 프레임 | 1,104 |
| 완전 동일 (psnr = inf) | **923** |
| 차이 있는 프레임 | 181 |
| 차이 프레임 psnr_avg 최소 / 중앙 / 최대 | 53.86 / 54.00 / 69.70 dB |
| 50 dB 미만 프레임 | **0** |

원인은 렌더가 아니라 인코더다 — 호스트 ffmpeg **4.4.2**, 컨테이너 ffmpeg **5.1.9**.
같은 브라우저 캡처에서 나온 PPTX 배경 이미지가 바이트 단위로 같으므로 **픽셀 생성 단계는 동일**하고,
차이는 x264 경로에서만 발생했다. 53.86 dB 는 육안 구분 불가 영역이다.

### 3.4 외부 참조 정적 검사 — 전 빌드 디렉터리

`tests/test_offline_assets.py` 의 판정 규칙을 그대로 import 해 `data/build/*` **전수**에 돌렸다
(`data/closure_check/scan_external_refs.py`).

| 항목 | 값 |
| --- | ---: |
| 스캔한 빌드 디렉터리 | 36 |
| 스캔한 텍스트 파일 | 425 |
| 외부 로드 참조 | **3** |
| CDN URL | **3** |
| 필수 로컬 자산 누락 디렉터리 | 5 |

**위반 3건은 전부 옛 빌드 잔재다.** `adv_check`·`demo_sample`·`fix_check` — 셋 다 2026-07-25 빌드로,
로컬 폰트 사본이 들어오기(07-26) 전 산출물이며 같은 한 줄을 갖고 있다.

```text
index.html:8 → https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/…/pretendardvariable-dynamic-subset.min.css
```

현행 결함인지 잔재인지 가르기 위해 **세 디렉터리의 `scene-data.json` 을 현행 `build.py` 로 재조립**했다
(`data/closure_check/rebuild_stale_check.py`).

| 슬러그 | 옛 빌드 외부참조 | 재조립 외부참조 | CDN | 자산 누락 |
| --- | ---: | ---: | ---: | ---: |
| adv_check | 1 | **0** | 0 | 0 |
| demo_sample | 1 | **0** | 0 | 0 |
| fix_check | 1 | **0** | 0 | 0 |

**현행 파이프라인은 깨끗하다.** 나머지 2건(`widget_check_assets`·`widget_e2e`)은 렌더 패키지가 아니라
위젯 검사용 중첩 디렉터리라 `_REQUIRED_LOCAL` 대상이 아니다.
2차 제작 산출물 `short_v2` 빌드도 별도로 검사했다 — 텍스트 파일 14개, 외부참조 0, CDN 0, 자산 누락 0.

---

## 4. 남은 격차

### 4.1 사용자·소유자 결정이 필요한 항목

| # | 사안 | 현황 | 결정할 것 |
| --- | --- | --- | --- |
| D1 | **short-9x16 의 active 승격** | 산출물 2/2 ✅ · 골든 등록 ✅ · `format_review` 심의 ❌ | `format_review` 회의를 열 것인가. 판정 없이는 `promote_format` 이 정상적으로 거절한다(`format_reuse/promotion_sandbox.json`). |
| D2 | **usage 원장 실기록** | 샌드박스에서만 1→2 확인 | 실제 `formats/short-9x16/` 에 `short_v2` 를 기록할 것인가 (이번 작업은 소유 밖이라 손대지 않았다). |
| D3 | **게이트 낭독 rate 보정** | 예산 5.5자/초 vs 실측 7.0~7.3자/초 | 1차가 이관한 미해결 쟁점. 세로에 6.5~7.0 을 적용하면 무음률이 28% → 약 10%대로 내려가지만, 가로 회귀 영향이 있다. |
| D4 | **`dur_plan` 의 표현 형식** | 절대 초 5값 | 원천의 대본 질량이 크게 다르면 그대로 못 쓴다. 역할별 비율 + 질량 계수로 바꿀 것인가. |
| D5 | **PPTX 기본 모드** | CLI 기본 `image` | `wda render` 에 모드 선택지가 없다(§4.2 G1). 기본을 hybrid 로 바꿀 것인가, 플래그를 추가할 것인가. |

### 4.2 구현 격차 (소유 밖이라 보고만)

| # | 격차 | 영향 |
| --- | --- | --- |
| G1 | `wda render` CLI 에 `--mode` 가 없다 — hybrid 는 `export_pptx(..., mode="hybrid")` 파이썬 호출로만 도달 가능 | CLI·SIF 사용자는 하이브리드 PPTX 를 못 받는다. `scripts/render-offline.sh` 도 마찬가지. |
| G2 | `ScenarioDoc.meta.source_report_id` 가 `int` — 인제스트 `doc_id` 는 hex 문자열(`350b20b8`) | 원천 추적을 위해 이 필드를 채우면 검증이 깨진다. 2차 제작에서 실제로 걸려 `None` 으로 비웠다. |
| G3 | 프리셋 준수 검사에 **직전 산출물 문안 대조가 없다** | §1.7(1) — 사람을 빼면 복붙 검사가 함께 사라진다. |
| G4 | `lessons#5` 에 스트레치 하한 항 누락, `lessons#6` 의 조건 미명시 | §1.7(2)(3) — 가벼운 대본 원천에서 교훈이 반대로 작동한다. |
| G5 | 하이브리드 제외 임계(불투명도 0.95)가 **보이는 텍스트를 떨군다** | delib_v2 개념 씬 1건(opacity 0.85). 임계를 낮추면 페이드 중간 텍스트가 완전 불투명으로 인쇄되는 반대 문제가 생긴다 — 임계값이 아니라 still 시각 선택으로 풀 문제다. |

| G6 | `.gitignore` 가 `data/` 를 통째로 제외한다 | 이 문서의 근거 파일 전부(`data/closure_check/**`)가 버전 관리 밖이다. 리포트만 커밋되고 증거는 로컬에만 남는다 — 재현 스크립트(`*.py`)만이라도 추적 대상으로 옮길지 결정이 필요하다. |

### 4.3 이번 작업에서 검증하지 못한 것

- **하이브리드 PPTX 의 실제 렌더 모양.** 이 환경의 LibreOffice 가 깨져 있다
  (`soffice.bin: error while loading shared libraries: libreglo.so`). 검증은 python-pptx 구조 수준까지이며,
  파워포인트/LibreOffice 가 실제로 그리는 줄바꿈·폰트 대체 결과는 **확인하지 못했다.**
  덤프상 폰트는 전부 `맑은 고딕`(Pretendard 폴백)이므로, 맑은 고딕이 없는 macOS·Linux 에서는 2차 폴백이 일어난다.
- **2차 제작의 TTS 먹싱·drift_report.** 1차와 달리 실합성 길이만 쟀고 mp4 먹싱·SRT 임베드까지는 하지 않았다.
- **오프라인 SIF 재빌드.** 기존 SIF(631 MB, 07-28 빌드)를 그대로 썼다. `scripts/build-sif.sh` 재실행은 하지 않았다.

---

## 5. 전체 회귀

```console
uv run pytest -q
695 passed, 4 skipped, 1 warning in 240.31s (0:04:00)   # exit 0
```

실패 0건. skip 4건은 종전과 같은 조건부 건이다 (`data/closure_check/pytest_full.log`).
이번 작업은 소스를 수정하지 않았으므로 이 수치는 **작업 전 상태의 확인**이지 변경의 검증이 아니다.

---

## 부록 — 산출물 색인

```text
data/closure_check/
├── scan_external_refs.py          전 빌드 외부참조 스캐너 (판정 규칙은 tests/ 것을 import)
├── rebuild_stale_check.py         위반 빌드 재조립 검증
├── format_briefing_short.md       format_presets_briefing 출력 원본
├── pytest_full.log                전체 회귀 로그
├── format_reuse/
│   ├── short_v1_turns.md          1차 심의 19턴 전문 (분석 입력)
│   ├── briefing_used.md           2차 심의가 실제로 인용한 프리셋 브리핑
│   ├── scenario_short_v2.json     2차 시나리오 (validate 0건)
│   ├── check_against_presets.py / preset_compliance.json
│   ├── tts_probe_v2.json          TTS 실합성 실측
│   ├── run_short_deliberation.py  7턴 심의 구동기
│   ├── meetings/…/minutes.md      2차 회의록
│   ├── turn_cost_analysis.py / turn_cost.json
│   ├── copy_overlap.json          1차·2차 문안 중복 대조 (§1.7-1 근거)
│   ├── build/short_v2/ · renders/short_v2/ · qa_short_v2.json
│   ├── formats_sandbox/ · promotion_sandbox.json
│   └── render_v2.py / render_v2_summary.json / render_v2.log
├── pptx/
│   ├── export_both_modes.py / export_summary.json
│   ├── dump_and_roundtrip.py / roundtrip.json / dump_*.json
│   ├── background_ink_check.py / background_ink.json
│   └── {short_v1,delib_v2}_{image,hybrid}[_edited].pptx
└── offline/
    ├── render_offline.log · psnr_stats.txt
    ├── external_refs_scan.json · rebuild_stale.json
    └── data/renders/short_v1/{short_v1.mp4,short_v1.pptx}
```
