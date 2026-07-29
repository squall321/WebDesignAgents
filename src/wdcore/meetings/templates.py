# 회의 유형별 라운드 템플릿 선언 — 서버가 진행을 강제하는 SSOT (PLAN §5.2)
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/meetings/templates.py
# (copy-adapt: dfmea/rca 템플릿 제거, scenario_build/module_review 신규 추가)
from __future__ import annotations

from wdcore.models.meeting import MeetingType, RoundSpec

MEETING_TEMPLATES: dict[MeetingType, list[RoundSpec]] = {
    # 컨셉 브레인스토밍: 발산 → 상호보완 → 수렴 (M1 — core_message·tone 후보 도출)
    MeetingType.brainstorm: [
        RoundSpec(
            name="diverge",
            instruction="자기 도메인 관점에서 아이디어를 1~3개 제시하라. 비판 금지.",
            speaker_order="round_robin", cycles=2,
            citation_required=False, allow_early_close=True,
        ),
        RoundSpec(
            name="build_on",
            instruction="타 참가자의 아이디어에 얹어(build-on) 보완·확장하라.",
            speaker_order="round_robin", cycles=1,
        ),
        RoundSpec(
            name="converge",
            instruction=(
                "모더레이터는 아이디어를 군집화·중복제거하고 Top 후보와 액션아이템을 정리하라. "
                "각 전문가는 상위 후보를 자기 도메인 리스크 관점에서 평가하라. 근거 인용 의무."
            ),
            speaker_order="moderator_pick", cycles=1, citation_required=True,
        ),
    ],
    # 시안 크리틱: 시안 발표(모더레이터 대독) → 관점별 리뷰 → 반론/응답 → 판정 (M3)
    MeetingType.design_review: [
        RoundSpec(
            name="present",
            instruction="모더레이터가 시안(렌더 결과·게이트 리포트)을 대독하고 리뷰 범위·전제조건을 선언하라.",
            speaker_order="fixed",
        ),
        RoundSpec(
            name="review",
            instruction="자기 도메인 체크리스트 관점에서 결함/리스크(Finding)를 심각도와 함께 지적하라. 근거 인용 의무.",
            speaker_order="round_robin", cycles=2,
            citation_required=True, allow_early_close=True,
        ),
        RoundSpec(
            name="rebuttal",
            instruction="제기된 Finding별로 수용/반박/조건부수용 입장을 밝혀라. 반박도 근거 인용 의무.",
            speaker_order="round_robin", citation_required=True,
        ),
        RoundSpec(
            name="verdict",
            instruction="Finding별 최종 상태를 확정하고 Go/Conditional-Go/No-Go를 판정하라. 조건은 액션아이템화하라.",
            speaker_order="fixed",
        ),
    ],
    # 시안 선정 트레이드오프: 옵션 입장 → 교차반박 → 가중평가 → 결정
    MeetingType.tradeoff: [
        RoundSpec(
            name="advocate",
            instruction="담당 시안의 장점을 정량 근거와 함께 옹호하라. 근거 인용 의무.",
            speaker_order="round_robin", citation_required=True,
        ),
        RoundSpec(
            name="attack",
            instruction="자기 담당이 아닌 시안의 약점을 근거와 함께 공격하라. 근거 인용 의무.",
            speaker_order="round_robin", citation_required=True,
        ),
        RoundSpec(
            name="score",
            instruction="기준×시안 매트릭스에 1~5점을 채점하고 각 점수에 한 줄 근거를 붙여라.",
            speaker_order="round_robin",
        ),
        RoundSpec(
            name="decide",
            instruction="가중합을 산출해 선택안을 결정하고, 기각안별 기각 사유와 재검토 트리거를 기록하라.",
            speaker_order="fixed",
        ),
    ],
    # 시나리오 빌드: 구조발산 → 교차반박 → 수렴타임라인 → 검증판정 (PLAN §5.2 신규, M2)
    MeetingType.scenario_build: [
        RoundSpec(
            name="structure_diverge",
            instruction=(
                "모더레이터는 조각 인벤토리와 발제자(ST)의 구조 초안을 대독하고, "
                "설득 골격·씬 후보를 scene_draft 산출물로 정리해 심의 범위를 선언하라."
            ),
            speaker_order="fixed",
        ),
        RoundSpec(
            name="cross_rebuttal",
            instruction=(
                "제시된 씬 구조를 자기 도메인 관점에서 교차 검증하라 — TD는 엔진 계약, AX는 접근성, "
                "AU는 인지 부하를 필수 점검한다. 이견은 stance=rebut으로 드러내라. 근거 인용 의무."
            ),
            speaker_order="round_robin", citation_required=True,
        ),
        RoundSpec(
            name="converge_timeline",
            instruction=(
                "모더레이터 정리 후 발제자(ST)는 scenario_patch로 타임라인을 통합하고, "
                "MO는 dur 배분, SL은 stills, NR은 narration 동기를 확정 제안하라."
            ),
            speaker_order="moderator_pick", cycles=2,
        ),
        RoundSpec(
            name="verdict",
            instruction=(
                "검증기 결과를 근거로 시나리오를 Go/Conditional-Go/No-Go 판정하고 decision 산출물로 기록하라. "
                "조건은 액션아이템화하고, 합의 안 된 취향 충돌은 open_issue로 남겨라."
            ),
            speaker_order="fixed", allow_early_close=True,
        ),
    ],
    # 모듈 승격 심사: design_review 파생 — 후보 발표 → 심사 → 반론 → 등록 판정 (PLAN §8, M4)
    MeetingType.module_review: [
        RoundSpec(
            name="present",
            instruction=(
                "모더레이터가 모듈 후보(module_candidate)의 용도·데이터 스키마·게이트 통과 결과를 대독하고 "
                "심사 범위를 선언하라."
            ),
            speaker_order="fixed",
        ),
        RoundSpec(
            name="review",
            instruction=(
                "재발명 여부(레지스트리 대조)·디자인 시스템 준수·스키마 품질·엔진 계약 관점에서 "
                "결함(Finding)을 심각도와 함께 지적하라. 근거 인용 의무."
            ),
            speaker_order="round_robin", cycles=2,
            citation_required=True, allow_early_close=True,
        ),
        RoundSpec(
            name="rebuttal",
            instruction="제기된 Finding별로 수용/반박/조건부수용 입장을 밝혀라. 반박도 근거 인용 의무.",
            speaker_order="round_robin", citation_required=True,
        ),
        RoundSpec(
            name="verdict",
            instruction="모듈 레지스트리 등록을 Go/Conditional-Go/No-Go로 판정하라. 조건은 액션아이템화하라.",
            speaker_order="fixed",
        ),
    ],
    # 포맷 승격 심사: design_review 파생 — 장르 발표 → 심사 → 반론 → 승격 판정 (PLAN §8.0, pilot→active)
    MeetingType.format_review: [
        RoundSpec(
            name="present",
            instruction=(
                "모더레이터가 포맷 후보(format_candidate)의 무대·골격·프리셋·골든 산출물과 "
                "누적 사용 실적(usage_count)을 대독하고 심사 범위를 선언하라."
            ),
            speaker_order="fixed",
        ),
        RoundSpec(
            name="review",
            instruction=(
                "이 장르가 재현 가능한 자산인지 심사하라 — 프리셋(참가자·의제·자수·구간 예산)이 "
                "실측 근거를 갖는지, 교훈이 다음 제작에 실행 가능한 형태인지, 골든이 회귀 기준으로 "
                "충분한지 결함(Finding)을 심각도와 함께 지적하라. 근거 인용 의무."
            ),
            speaker_order="round_robin", cycles=2,
            citation_required=True, allow_early_close=True,
        ),
        RoundSpec(
            name="rebuttal",
            instruction="제기된 Finding별로 수용/반박/조건부수용 입장을 밝혀라. 반박도 근거 인용 의무.",
            speaker_order="round_robin", citation_required=True,
        ),
        RoundSpec(
            name="verdict",
            instruction=(
                "포맷의 active 승격을 Go/Conditional-Go/No-Go로 판정하라. "
                "조건은 액션아이템화하고, 확정된 교훈은 format.yaml lessons 항목으로 적어라."
            ),
            speaker_order="fixed",
        ),
    ],
}


def rounds_for(meeting_type: MeetingType | str) -> list[RoundSpec]:
    """유형별 라운드 템플릿을 반환한다 (문자열 입력 허용)."""
    return MEETING_TEMPLATES[MeetingType(meeting_type)]
