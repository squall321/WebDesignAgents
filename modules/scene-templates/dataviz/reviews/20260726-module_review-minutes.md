# [회의록] tpl.dataviz module promotion review (수치 논증 씬 승격 심사)

- 회의 ID: 7a7db54e / 유형: 모듈 승격 심사 / 상태: closed
- 일시: 2026-07-26 14:43 ~ 2026-07-26 14:43 (17턴)

## 1. 참가자

| ID | 이름 |
|---|---|
| vis-dataviz | 데이터 시각화 전문가 |
| impl-technical-director | 테크니컬 디렉터 |
| qa-consistency | 품질 감사관 |
| mot-motion-director | 모션 디렉터 |
| vis-layout-grid | 레이아웃·그리드 전문가 |

## 2. 라운드별 발언 요약

### R1 present

| 턴 | 발언자 | 태도 | 요지 | 인용 |
|---|---|---|---|---|
| #1 | 모더레이터 | summarize | 개회한다. 심사 대상은 tpl.dataviz 1.0.0 draft — 창작 모드(2026-07-26, 외부 샘플 무참조) 신규 씬 템플릿, 발… | - |

### R2 review

| 턴 | 발언자 | 태도 | 요지 | 인용 |
|---|---|---|---|---|
| #2 | 데이터 시각화 전문가(vis-dataviz) | propose | 제안자로서 설계 근거 셋을 밝힌다. (1) **정직성의 스키마 강제** — 막대는 0 기준선에서만 자라고 축 하한 필드 자체가 존재하지 않는다… | schema:tpl.dataviz, calc:schedule_calc.json, snap:tpl.dataviz/typical, src:omx-templates-ext.jsx |
| #3 | 테크니컬 디렉터(impl-technical-director) | concern | 가/불가를 먼저 선언한다 — **가**. 검사 결과. (1) 순수성: 소스 전수 grep에서 Math.random·Date·setTimeout… | src:omx-templates-ext.jsx, TD-C-001, calc:schedule_calc.json, qa:20260726-094856-44c8bd |
| #4 | 품질 감사관(qa-consistency) | concern | 재발명 대조 결과 — **위반 아님**. tpl.problem은 out_of_scope에 '수치 비교 중심의 문제 제기(신규 은유 필요)', … | module:tpl.problem, module:tpl.differentiator, module:tpl.closing, qa:20260726-094825-2389df, qa:20260726-094856-44c8bd, theme:hwax-blue, calc:schedule_calc.json, fixture:tpl.dataviz/max |
| #5 | 모션 디렉터(mot-motion-director) | concern | 이징 배정 감사 — 등장은 theme.motion.rise(easeOutCubic), 강조 팝은 pop(easeOutBack), 막대 성장은 … | MO-C-001, calc:schedule_calc.json, theme:hwax-blue |
| #6 | 레이아웃·그리드 전문가(vis-layout-grid) | concern | 좌표 검증 — 패널 (140,330) 1120×590 우변 1260, 판독 칼럼 x1300 w480 우변 1780 = stageW−margin… | calc:schedule_calc.json, snap:tpl.dataviz/typical, qa:20260726-094856-44c8bd, schema:tpl.dataviz |
| #7 | 데이터 시각화 전문가(vis-dataviz) | support | QA ②·LG ① 지적을 제안자로서 수용한다. display는 '숫자+단위' 용도로 설계했으나 스키마 description 문서화만으로는 강제… | fixture:tpl.dataviz/max, schema:tpl.dataviz, calc:schedule_calc.json |
| #8 | 테크니컬 디렉터(impl-technical-director) | support | 2차 검사 — schedule과 렌더의 동기를 대조했다. bar-i-value 스케줄 at=barAt+barDur−0.15가 렌더 opacit… | src:omx-templates-ext.jsx, TD-C-001 |
| #9 | 품질 감사관(qa-consistency) | concern | 승격 전제 정리 — module:tpl.dataviz의 quality.gates_passed와 reviews가 빈 배열이다. 승격 시 클린 리… | module:tpl.dataviz, qa:20260726-094856-44c8bd, qa:20260726-094825-2389df |
| #10 | 모션 디렉터(mot-motion-director) | support | 잔여 예산 검증 — max에서도 마지막 착지 9.7s, tail 3.3s로 낭독 여백이 충분하다. 강조 막대의 입장 간격(마지막 비교군 3.3… | calc:schedule_calc.json, MO-C-001 |
| #11 | 레이아웃·그리드 전문가(vis-layout-grid) | support | max 픽스처 재실측 — 5행 rowH 84.8px에 barH 36, 라벨 9자×25px=225 ≤ 칼럼 230px 수용. 결론 상자 2행(2… | calc:schedule_calc.json, fixture:tpl.dataviz/max |

### R3 rebuttal

| 턴 | 발언자 | 태도 | 요지 | 인용 |
|---|---|---|---|---|
| #12 | 데이터 시각화 전문가(vis-dataviz) | accept | 지적 전건 수용. 액션 인수 — max 픽스처를 display 7자·value=axisMax로 재작성하고 게이트 5를 재실행한다(내 담당). … | fixture:tpl.dataviz/max, schema:tpl.dataviz |
| #13 | 테크니컬 디렉터(impl-technical-director) | accept | 계약 위반 0건 확정 — 거부권 비행사. 잔여 액션(픽스처·스태거 토큰 정렬)은 계약 무관 정비로 분류한다. | TD-C-001, src:omx-templates-ext.jsx |
| #14 | 품질 감사관(qa-consistency) | accept | 승인한다. 보류 사유 (a)~(c) 미해당 — 게이트 클린 리포트 첨부됨, 레지스트리 대조 완료, 색·이징 토큰 리터럴 위반 0건. 스태거 토… | qa:20260726-094856-44c8bd, theme:hwax-blue |
| #15 | 모션 디렉터(mot-motion-director) | accept | labels.stagger 0.12→토큰 micro 0.16 정렬을 발의 인수한다 — 수정 구간은 datavizPlan labels.stagg… | MO-C-001, calc:schedule_calc.json |
| #16 | 레이아웃·그리드 전문가(vis-layout-grid) | accept | 값 라벨 존 정비(display 용도 패턴 문서화 또는 valueW 140→170)를 액션 전제로 이견 없음. | calc:schedule_calc.json |

### R4 verdict

| 턴 | 발언자 | 태도 | 요지 | 인용 |
|---|---|---|---|---|
| #17 | 모더레이터 | summarize | 판정한다. 관점별 결과 — TD: 계약 위반 0건·거부권 비행사(순수성 grep 0건, frame-match 게이트 7 클린 2회). QA: … | - |

## 3. 결론

- Go — tpl.dataviz draft→pilot 승격. 계약 위반 0, 게이트 2차 클린(qa:20260726-094856-44c8bd), 재발명 아님. 비차단 후속 3건은 액션아이템. (턴 #17)

## 4. 액션아이템

| # | 내용 | 담당 | 제출 턴 |
|---|---|---|---|
| 1 | max 픽스처를 display 7자·value=axisMax 조합으로 재작성 후 게이트 5 재실행 | vis-dataviz | #17 |
| 2 | datavizPlan labels.stagger 0.12 → 토큰 micro 0.16 정렬 | mot-motion-director | #17 |
| 3 | 값 라벨 존 정비 — schema display 용도 패턴 문서화 또는 valueW 140→170 검토 | vis-layout-grid | #17 |

## 5. 인용 근거 목록

| # | 출처 ref | 인용 턴 |
|---|---|---|
| 1 | schema:tpl.dataviz | #2, #6, #7, #12 |
| 2 | calc:schedule_calc.json | #2, #3, #4, #5, #6, #7, #10, #11, #15, #16 |
| 3 | snap:tpl.dataviz/typical | #2, #6 |
| 4 | src:omx-templates-ext.jsx | #2, #3, #8, #13 |
| 5 | TD-C-001 | #3, #8, #13 |
| 6 | qa:20260726-094856-44c8bd | #3, #4, #6, #9, #14 |
| 7 | module:tpl.problem | #4 |
| 8 | module:tpl.differentiator | #4 |
| 9 | module:tpl.closing | #4 |
| 10 | qa:20260726-094825-2389df | #4, #9 |
| 11 | theme:hwax-blue | #4, #5, #14 |
| 12 | fixture:tpl.dataviz/max | #4, #7, #11, #12 |
| 13 | MO-C-001 | #5, #10, #15 |
| 14 | module:tpl.dataviz | #9 |

## 6. 미해결 쟁점

(없음)
