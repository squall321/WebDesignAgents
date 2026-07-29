# 포맷 레지스트리 운영 — 겪어본 장르를 자산으로 (PLAN §8.0)

축적은 두 층위에서 일어난다. **씬 템플릿**(`modules/scene-templates/{id}/`)은 화면 구성 1개를 쌓고,
**포맷**(`formats/{id}/`)은 장르 1개를 **제작 노하우째로** 쌓는다. 템플릿만 쌓이면 매번 장르를 처음부터
설계해야 한다. 이 문서는 포맷 쪽 축적 장치의 운영 규약이다.

한 줄 요약 — **첫 제작은 장르 설계 + 콘텐츠 심의, 두 번째부터는 콘텐츠 심의만.**

구현 소유자는 `src/wdpipeline/format.py`, 검증은 `tests/test_format_promotion.py`(26건)·`tests/test_format_spec.py`(26건)이다.

---

## 1. format.yaml 스키마

기본 4블록(무대·길이·골격·산출)은 기존 그대로이고, 그 위에 승격 루프 블록이 얹힌다.
**승격 루프 필드는 전부 기본값이 있다** — 옛 스펙은 손대지 않아도 그대로 로드된다(`status: draft`, `usage_count: 0`).

| 필드 | 타입 | 뜻 | 누가 채우나 |
| --- | --- | --- | --- |
| `status` | `draft \| pilot \| active` | 수명주기. 템플릿 승격과 동형 | `promote_format` (자동) |
| `origin.meeting_id` / `origin.created` | str / "YYYY-MM-DD" | 이 장르를 정의한 심의 | 사람 (첫 제작 후) |
| `usage_count` | int | 완주한 산출물 수 | `record_usage` (자동) |
| `presets.deliberation` | `{type, participants[], agenda[]}` | 다시 소집할 회의 프리셋 | 사람 (회의록에서 옮김) |
| `presets.copy_guide` | `{"역할.필드": 자수}` | 실측 자수 상한 | 사람 (schema.json maxLength 사본) |
| `presets.dur_plan` | `{역할: 초}` | 확정 구간 예산 | 사람 (심의 확정값) |
| `presets.narration` | `{rate, max_silence}` | 낭독 예산·씬별 무음 상한(초) | 사람 (TTS 실측) |
| `golden` | `{run_id, artifacts[], qa_report}` | 회귀 기준선 | 사람 (게이트 통과 산출물) |
| `lessons` | str[] | 심의가 남긴 교훈 | 사람 (회의록 결론·미해결 쟁점) |

**키 규약.** `copy_guide` 키는 `역할.필드경로`(예: `hook.line.accent`), `dur_plan` 키는 역할이다.
둘 다 첫 세그먼트가 `skeleton` 안에 없으면 **로드가 실패한다** — 역할을 개명한 뒤 방치된 프리셋을 잡기 위한 것이다.

```text
FormatError: 포맷 스펙 검증 실패 ...
  presets.dur_plan 에 골격 밖 역할 ['closing'] — skeleton [...] 의 이름과 맞춰라
```

`origin.created`는 따옴표 없이 `2026-07-27`로 써도 된다 (YAML `date` → 문자열 변환).

---

## 2. 사용 원장 — usage_count 는 손으로 세지 않는다

`formats/{id}/usage.jsonl` 이 산출물 원장이다. 한 줄 = 완주한 산출물 1건.

```jsonl
{"run_id": "short_v1", "gate_errors": 0, "qa_report": "data/qa_reports/20260727-223243-f1e865/qa.json", "at": "..."}
```

```python
record_usage("short-9x16", "short_v1", gate_errors=0, qa_report=".../qa.json")
# → {"recorded": True, "usage_count": 1, "runs": ["short_v1"]}
```

- 같은 `run_id` 재기록은 무시된다(`recorded: False`) — 재렌더가 건수를 부풀리지 않는다.
- 기록 후 `format.yaml` 의 `usage_count:` **한 줄만** 교체한다. 재직렬화하지 않으므로 주석·필드 순서가 보존된다.
- 이 원장이 곧 승격 증거다 — `promote_format` 에 `evidence.runs` 를 안 주면 원장을 읽는다.

---

## 3. 승격 루프

| 전이 | 정량 조건 | 정성 조건 |
| --- | --- | --- |
| 등록(draft) | `load_format` 통과 (template_pool 이 실재하고 그 모듈이 이 포맷을 선언) | 불필요 |
| draft → pilot | 산출물 1건 + 게이트 error 0 | 제작 심의(`scenario_build`·`design_review`) Go/Conditional-Go |
| pilot → active | 산출물 2건 + 골든 등록 | `format_review` 심의 Go |

```python
promote_format("short-9x16", evidence={
    "verdicts": [{"meeting_id": "67bd5d0d-...", "type": "scenario_build", "verdict": "Conditional-Go"}],
})
```

반환은 `{format, status, target, promoted, applied, checks[], missing[]}` 이다.
**미충족은 무엇이 얼마나 부족한지 수치로 적힌다** — 판정을 사람이 재해석할 필요가 없게.

```text
promote → target=active promoted=False applied=False
  [O] 산출물: 산출물 2건 / 필요 2건
  [O] 골든: 골든 run_id=delib_v2 · 산출물 6건
  [X] format_review: format_review 없음 — format_review 심의를 열고 판정을 evidence.verdicts 로 제출하라
```

규칙 몇 가지.

- 게이트 결과가 **미기록**인 산출물이 하나라도 있으면 통과가 아니라 거절이다(`게이트 결과 미기록 ['r1']`). 침묵을 0으로 읽지 않는다.
- 승격 성공 시 `status:` 한 줄이 교체된다. 판정만 하려면 `apply=False`.
- `active` 는 마지막 단계다. `deprecated` 전이는 정기 심의 의결 사항이라 아직 자동화하지 않았다.

### format_review 회의 유형

`design_review` 파생 — `present → review → rebuttal → verdict`, review·rebuttal 은 인용 의무.
심사 관점은 "이 장르가 재현 가능한 자산인가" — 프리셋이 실측 근거를 갖는지, 교훈이 실행 가능한
형태인지, 골든이 회귀 기준으로 충분한지. 후보 산출물 타입은 `format_candidate` 다.

---

## 4. 재사용 흐름 — 두 번째 제작

```text
포맷 선택 → format_presets_briefing() → 심의(프리셋 재소집) → 조립·검증 → 렌더·QA
   → record_usage() → promote_format()
```

`format_presets_briefing(format_id)` 는 브리핑에 그대로 실을 마크다운을 만든다.
프리셋이 비어 있는 신규 draft 포맷이면 빈 항목을 늘어놓지 않고 기본 정보만 낸다.

```text
## 포맷 short-9x16 — 세로 숏폼 브리핑 (pilot · 산출물 1건)
- 무대 1080×1920 · 목표 60초 (허용 40~75) · 최소 폰트 32 · safe margin 72
- 골격 hook(vtpl.hook) → problem(vtpl.stack) → solution(vtpl.stack) → proof(vtpl.metric) → cta(vtpl.cta)
- 심의 프리셋 — 유형 scenario_build · 참가자 narr-story-architect, narr-copywriter, ...
  1. 청중 — 세로 피드에서 소리 없이 넘기는 사람은 누구인가. 바뀌면 core_message·tone·CTA가 전부 바뀐다
  ...
- 구간 예산(초) — hook 6.2 · problem 11.2 · solution 11.6 · proof 9.6 · cta 7.4 (합계 46)
- 카피 자수 상한 — hook.line.accent 10자 · hook.focus.word 8자 · ...
- 낭독 — 예산 5.5자/초 · 씬별 무음 상한 3.6초
- 골든 — run short_v1 · data/renders/short_v1/short_v1_voiced.mp4, ... · QA data/qa_reports/...
- 출처 심의 — 67bd5d0d-e44f-47f1-bc80-d9fa1c10e5ea (2026-07-27)
- 교훈 (이전 심의가 남긴 것 — 재발명 대신 인용하라)
  1. 목표 60초를 채우지 않는다 — TTS·스케줄 실측이 46초를 가리키면 46초로 확정한다 (Σdur 46.0s, 허용대 40~75s)
  ...
```

핵심은 마지막 블록이다. 다음 심의의 페르소나는 "세로는 몇 초가 좋을까"를 **다시 논의하지 않고**
`lessons` 를 인용해 반박하거나 갱신한다. 노하우가 회의 밖으로 새지 않게 하는 장치다.

---

## 5. 현재 레지스트리 (2026-07-28)

| 포맷 | status | usage | 골든 | 다음 전이에 부족한 것 |
| --- | --- | --- | --- | --- |
| `wide-16x9` 가로 브리핑 영상 | pilot | 2 (delib_v1·delib_v2) | delib_v2 | `format_review` Go 하나 |
| `short-9x16` 세로 숏폼 브리핑 | pilot | 1 (short_v1) | short_v1 | 산출물 1건 + `format_review` Go |

두 포맷 모두 draft→pilot 을 **실제 증거로** 통과했다 — 게이트 error 합계 0건, 제작 심의 판정
(delib_v1 Go / delib_v2 Conditional-Go / short_v1 Conditional-Go).

### 프리셋의 출처 (사후 창작이 아님을 남긴다)

| 값 | 출처 |
| --- | --- |
| short `dur_plan` Σ46.0s | 심의 67bd5d0d 턴 #11 확정 — TTS 실측(`tts_probe.json`)·스케줄 실측(`schedule_probe.json`) 기반 |
| short `max_silence` 3.6s | `data/renders/short_v1/drift_report.json` 씬별 무음 최대(문제 3.56s) |
| short `copy_guide` | `modules/scene-templates/v-*/schema.json` 의 maxLength (세로 무대 역산값) |
| wide `dur_plan` Σ78.0s | 심의 339e3bac 최종 ScenarioDoc — v1 90s 대비 -12s |
| wide `max_silence` 4.1s | `data/renders/delib_v2/drift_report.json` 씬별 무음 최대(절차 4.10s) |

테스트가 이 대응을 강제한다 — `copy_guide` 는 스키마 maxLength 와 대조되고(`test_short_9x16_copy_guide_matches_vertical_schemas`),
`dur_plan` 은 골든 시나리오의 씬별 `dur` 과 대조된다(`test_short_v1_scenario_obeys_its_own_presets`).
프리셋이 실물과 어긋나면 테스트가 깨진다.

---

## 6. 알려진 어긋남

- **wide `duration.target` 90 vs `dur_plan` Σ78.** 90은 씬 7종 `nat_default` 합의 잔재이고, 실측 확정은 78이다.
  `target` 은 조립 시 균일 스케일 기준이라 바꾸면 기존 시나리오 회귀가 걸리므로 이번엔 손대지 않았다.
  `duration.target` 을 78로 내리는 것은 회귀 영향 확인 후 별도로 판단할 일이다.
- **낭독 예산 5.5자/초 vs 실측 6.0~8.4자/초.** 게이트 상수와 Chatterbox 실측의 상시 격차다.
  예산을 지키는 한 무음 25% 이상이 구조적으로 발생한다 (short_v1 25.7% · delib_v2 25.2%).
  short-9x16 심의 미해결 쟁점으로 이관되어 있다.
- **`minutes.py` 의 `_TYPE_LABELS` 에 `format_review` 한국어 라벨이 없다.** 회의록 헤더에 원문
  `format_review` 가 찍힌다(`.get(v, v)` 폴백이라 깨지지는 않는다). 해당 파일은 이 작업의 소유 밖이다.
