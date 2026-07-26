# QA 게이트 공용 설정 — 낭독 속도·대비 임계·프레임 diff 임계 등 (PLAN §7)
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# repo 루트 = src/wdqa/config.py 기준 두 단계 위
REPO_ROOT = Path(__file__).resolve().parents[2]

# 게이트 번호 ↔ 정식 이름 (gates 파라미터는 번호·이름 둘 다 허용)
GATE_NAMES: dict[int, str] = {
    1: "mapping",
    2: "length",
    3: "contrast",
    4: "font",
    5: "overflow",
    6: "determinism",
    7: "frame_match",
}


@dataclass
class QAConfig:
    """게이트 실행 파라미터. 기본값은 PLAN §7 + 실측 보정."""

    # 게이트 2 — 낭독/자막 속도 (한국어 초당 글자수, 공백 제외)
    narration_cps: float = 5.5
    caption_cps: float = 9.0
    stretch_limit: float = 0.15          # dur/nat 타임 스트레치 허용 한계 (±15%)

    # 게이트 3 — WCAG 2.1 대비 임계
    contrast_normal: float = 4.5         # 일반 텍스트
    contrast_large: float = 3.0          # 대형 텍스트 (≥24px 또는 ≥18.66px bold)
    pair_match_tol: int = 4              # 선언 페어 매칭 채널 허용 오차 (0~255)

    # 게이트 4 — 최소 폰트
    min_font_px: float = 24.0

    # 게이트 5 — 오버플로
    overflow_tol_px: float = 2.0         # scrollWidth/Height 라운딩 허용
    stage_tol_px: float = 2.0            # 스테이지 이탈 허용
    safe_margin_px: float = 16.0         # 텍스트 safe margin (위반 시 경고)

    # 런타임 스캔 공통
    min_visible_opacity: float = 0.1     # 누적 opacity 미만 요소는 스캔 제외
    seek_probe_offset: float = 0.1       # 게이트 1 런타임 — 씬 시작 + offset seek

    # 게이트 6 — 결정성
    determinism_fractions: tuple[float, ...] = (0.2, 0.5, 0.8)  # duration 비율 표본 3개

    # 게이트 7 — frame-match
    # 임계값 실측 근거 (2026-07-25, demo_sample 2160프레임/90초 2회 독립 렌더, verify_render_determinism):
    #   2146/2160 프레임 비트 동일, 14프레임만 서브픽셀 차. max_diff_ratio=0.000002(200만 픽셀 중 최대 4개).
    #   → 0.02(2%)는 실측 대비 1만 배 여유. 안전한 보수값으로 확정. 상세는 context-notes.md.
    fps: int | None = None               # None이면 configs/render.toml 의 fps
    frame_diff_channel_tol: int = 8      # 채널 diff가 이 값 초과면 '변한 픽셀'
    frame_match_max_ratio: float = 0.02  # 변한 픽셀 비율 임계 (실측 0.000002 ≪ 0.02)

    # 단계 게이팅 — PLAN §7: S→D→R→V, 앞 단계 실패(error) 시 뒤 생략
    # 기본 False — 앞 단계(정적) 실패 1건이 나머지 게이트 전체를 가리는 단락을 막는다.
    # 대량 배치에서 실패 빌드의 런타임 비용을 아끼려면 True 로 켠다.
    skip_on_phase_failure: bool = False

    # 경로
    modules_root: Path = field(default_factory=lambda: REPO_ROOT / "modules")
    tokens_dirs: tuple[Path, ...] = field(
        default_factory=lambda: (REPO_ROOT / "web" / "tokens",)
    )
    reports_root: Path | None = None     # None이면 {WDA_DATA_DIR|data}/qa_reports

    def resolved_fps(self) -> int:
        if self.fps is not None:
            return self.fps
        try:
            from wdrender.config import load_config

            return load_config().fps
        except Exception:
            return 24
