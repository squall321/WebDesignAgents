

# 검사기(SPOKEN_RESIDUE)가 잡는 구어체는 변환기(to_written)가 전부 없앨 수 있어야 한다.
# 둘이 어긋나면 그 구어체가 든 원고는 문서 산출이 영구 실패한다 — 웹 데모 시나리오의
# "확인하세요" 가 실제로 그렇게 막혔다(2026-08-25). 규칙을 늘릴 때 이 표도 함께 늘린다.
RESIDUE_SAMPLES = [
    "결과를 정리했습니다.",
    "정말 그렇습니까?",
    "부록을 확인하십시오.",
    "함께 검토하시죠.",
    "보시다시피 값이 튄다.",
    "보시는 지표가 핵심입니다.",
    "자세한 내용은 부록을 확인하세요.",
    "이 값을 꼭 읽으세요.",
    "우리는 매일 점검해요.",
    "원인은 과열이에요.",
    "이건 설계 문제예요.",
]


def test_every_residue_pattern_has_a_converting_rule():
    from wdpipeline.document import SPOKEN_RESIDUE, to_written

    for raw in RESIDUE_SAMPLES:
        assert SPOKEN_RESIDUE.search(raw), f"표본이 구어체가 아니다: {raw}"
        written = to_written(raw)
        left = SPOKEN_RESIDUE.search(written)
        assert left is None, f"{raw!r} → {written!r} 에 구어체가 남았다: {left and left.group(0)}"
