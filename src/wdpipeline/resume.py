# 파이프라인 재개 지점 판정 — 실패한 단계부터 다시 돈다 (PLAN M3 검증 ④ 단계 재시도·재개)
from __future__ import annotations

import json
from pathlib import Path

__all__ = ["STAGES", "STAGE_OUTPUTS", "stage_state", "resume_point"]

STAGES: tuple[str, ...] = ("ingest", "fragmentize", "scenario", "build")

# 단계 → 그 단계가 끝났음을 증명하는 산출물. **파일이 진실이다** — 원장은 쓰다 만 채로
# 프로세스가 죽을 수 있지만, 산출물은 쓰였거나 안 쓰였거나 둘 중 하나다.
STAGE_OUTPUTS: dict[str, str] = {
    "ingest": "report.norm.json",
    "fragmentize": "fragments.json",
    "scenario": "scenario.json",
    # build 는 파이프라인 디렉터리가 아니라 build/{slug}/ 에 쓴다 — 아래에서 따로 본다
    "build": "",
}


def _valid_json(path: Path) -> bool:
    """존재만으로는 모자라다 — 쓰다 만 파일이 남을 수 있다."""
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return True


def stage_state(pipeline_dir: Path, build_dir: Path | None = None) -> dict[str, bool]:
    """단계별 '산출물이 쓸 만한가'. 원장이 아니라 디스크를 본다."""
    pipe = Path(pipeline_dir)
    out: dict[str, bool] = {}
    for stage in STAGES:
        if stage == "build":
            entry = Path(build_dir) / "index.html" if build_dir else None
            out[stage] = bool(entry and entry.is_file()
                              and _valid_json(Path(build_dir) / "scene-data.json"))
        else:
            out[stage] = _valid_json(pipe / STAGE_OUTPUTS[stage])
    return out


def resume_point(pipeline_dir: Path, build_dir: Path | None = None) -> str | None:
    """다시 시작할 첫 단계. 전부 끝났으면 None.

    **앞 단계가 비면 뒤는 건너뛰지 않는다** — 중간 산출물이 남아 있어도 그 앞이 깨졌으면
    뒤의 것은 옛 입력으로 만들어진 것이라 믿을 수 없다. 끊긴 지점부터 끝까지 다시 돈다.
    """
    state = stage_state(pipeline_dir, build_dir)
    for stage in STAGES:
        if not state[stage]:
            return stage
    return None


def stages_from(stage: str | None) -> tuple[str, ...]:
    """재개 지점부터 끝까지의 단계 목록."""
    if stage is None:
        return ()
    if stage not in STAGES:
        raise ValueError(f"알 수 없는 단계: {stage} — {', '.join(STAGES)} 중 하나여야 한다")
    return STAGES[STAGES.index(stage):]
