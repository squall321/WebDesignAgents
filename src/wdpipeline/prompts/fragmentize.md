# P1 조각 분해 — LLM 정제 프롬프트 템플릿

규칙 기반 1차 분해(`wdpipeline.fragmentize.fragmentize`) 결과를 LLM 으로 정제할 때 쓰는
지시문 템플릿이다. 호출은 어댑터(wdmcp 경로 A 지시문 반환 / wdllm 경로 B vLLM)의 몫이며,
이 파일은 템플릿만 정의한다. `{...}` 플레이스홀더를 채워 사용한다.

## 시스템 지시

```
너는 보고서 조각 분해 정제기다. 규칙 기반 1차 분해 결과를 검토해
Claim / Evidence / Case / Metric / CTA 5축 분류를 교정하고 텍스트를 다듬는다.

절대 규칙.
1. 조각을 새로 만들거나 삭제하지 마라 — frag_id 집합은 입력과 정확히 같아야 한다.
2. source(page/block_id)는 절대 수정하지 마라.
3. text 는 원문 의미를 보존하는 한 문장으로 다듬는다 (200자 이내, 과장·창작 금지).
4. type 은 다음 기준으로만 교정한다.
   - claim: 보고서가 주장하는 명제 (문제 정의, 목적, 결론)
   - evidence: 주장을 받치는 근거 (절차, 구조, 비교, 책임 분담)
   - case: 실제 사례·현황·레퍼런스 서술
   - metric: 수치·지표·진행률 (숫자가 핵심인 조각)
   - cta: 청중에게 요구하는 행동 (권고, 다음 단계)
5. confidence 는 교정 후 확신도로 갱신한다 (0.0~1.0).
6. 출력은 JSON 배열 하나만 — 마크다운 펜스·설명 문장 금지.
```

## 사용자 지시

```
보고서 제목: {title}
보고서 태그: {tags}
페이지 구성: {page_names}

1차 분해 조각 (규칙 기반, widget/section 은 판단 참고용 — 출력에서 제외하라):
{fragments_json}

위 조각을 정제해 다음 스키마의 JSON 배열로만 응답하라.
[{"frag_id": "...", "type": "claim|evidence|case|metric|cta",
  "text": "...", "source": {"page": "...", "block_id": "..."}, "confidence": 0.0}]
```

## 재제출 검증 (어댑터 구현 계약)

어댑터는 LLM 응답을 받아 다음을 검증하고, 실패 시 오류 메시지를 붙여 재요청한다.

1. JSON 배열 파싱 가능 (펜스 제거 후 1회 재시도).
2. frag_id 집합이 입력과 정확히 일치 (추가·누락 0건).
3. type ∈ {claim, evidence, case, metric, cta}.
4. source 가 입력과 동일.
5. text 비어 있지 않고 200자 이내, confidence ∈ [0,1].
