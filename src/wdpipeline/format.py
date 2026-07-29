# 포맷 스펙 계층 — formats/{id}/format.yaml 을 FormatSpec 으로 로드·검증하고 무대(stage)·골격의 단일 정본을 제공
from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field, field_validator, model_validator

from wdcore.models.common import StrictModel

# repo 루트 (src/wdpipeline/format.py → 두 단계 위)
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FORMATS_ROOT = _REPO_ROOT / "formats"
DEFAULT_MODULES_ROOT = _REPO_ROOT / "modules"

# 포맷 미지정 시 적용되는 기존 가로 무대 — 이 값이 곧 회귀 방지선이다.
DEFAULT_FORMAT_ID = "wide-16x9"

FORMAT_FILE = "format.yaml"
REGISTRY_FILE = "registry.yaml"
USAGE_FILE = "usage.jsonl"

# 포맷 수명주기 — 템플릿 승격과 동형 (PLAN §8.0)
FormatStatus = Literal["draft", "pilot", "active"]

# status 전이표. 여기 없는 status 는 다음 전이가 없다.
PROMOTION_PATH: dict[str, str] = {"draft": "pilot", "pilot": "active"}

# 제작 심의로 인정되는 회의 유형 (draft→pilot 의 정성 조건)
PRODUCTION_MEETING_TYPES = frozenset({"scenario_build", "design_review"})
GO_VERDICTS = frozenset({"Go", "Conditional-Go"})


class FormatError(ValueError):
    """포맷 스펙 로드·검증 실패. 메시지는 원인 + 다음 행동을 담는다."""


# ── 경로 해석 ───────────────────────────────────────────────────────────


def resolve_modules_root(modules_root: str | Path | None = None) -> Path:
    """WDA_MODULES_ROOT 환경변수 우선 — wdmcp 의 modules_root() 와 같은 규칙."""
    if modules_root is not None:
        return Path(modules_root)
    env = os.environ.get("WDA_MODULES_ROOT")
    return Path(env) if env else DEFAULT_MODULES_ROOT


def resolve_formats_root(formats_root: str | Path | None = None) -> Path:
    """WDA_FORMATS_ROOT 환경변수 우선 — 기본은 repo 루트의 formats/."""
    if formats_root is not None:
        return Path(formats_root)
    env = os.environ.get("WDA_FORMATS_ROOT")
    return Path(env) if env else DEFAULT_FORMATS_ROOT


# ── 스펙 모델 ───────────────────────────────────────────────────────────


class FormatStage(StrictModel):
    """렌더 무대 픽셀 — 엔트리 SceneStage width/height 와 캡처 클립의 원천."""

    w: int = Field(gt=0, le=8192)
    h: int = Field(gt=0, le=8192)


class FormatDuration(StrictModel):
    """총 러닝타임 규격. target 은 조립 기준, min~max 는 검증 허용대."""

    target: float = Field(gt=0)
    min: float = Field(gt=0)
    max: float = Field(gt=0)

    @model_validator(mode="after")
    def _ordered(self) -> "FormatDuration":
        if not (self.min <= self.target <= self.max):
            raise ValueError(
                f"duration 범위 오류 — min({self.min}) ≤ target({self.target}) ≤ max({self.max}) 이어야 한다"
            )
        return self


class FormatNarration(StrictModel):
    """내레이션 규격. rate 는 초당 낭독 글자수(공백 제외) 예산."""

    enabled: bool = True
    rate: float = Field(default=5.5, gt=0)


class FormatPptx(StrictModel):
    """PPTX 슬라이드 크기(인치) — 세로 포맷이면 세로 슬라이드."""

    slide_w_in: float = Field(gt=0)
    slide_h_in: float = Field(gt=0)


class FormatConstraints(StrictModel):
    """무대 공통 제약 — QA 게이트/템플릿 설계의 하한선(서술값)."""

    min_font: int = Field(default=0, ge=0)
    safe_margin: int = Field(default=0, ge=0)


class FormatOrigin(StrictModel):
    """이 포맷이 태어난 자리 — 어느 심의가 장르를 정의했나."""

    meeting_id: str = ""
    created: str = Field(default="", description="YYYY-MM-DD")

    @field_validator("created", mode="before")
    @classmethod
    def _stringify_date(cls, v: object) -> object:
        """YAML 이 2026-07-27 을 date 로 파싱해도 문자열로 받는다."""
        return v.isoformat() if isinstance(v, (date, datetime)) else v


class FormatDeliberation(StrictModel):
    """이 장르를 심의할 때의 회의 프리셋 — 다음 회의가 그대로 재소집할 수 있게."""

    type: str = ""
    participants: list[str] = Field(default_factory=list)
    agenda: list[str] = Field(default_factory=list)


class FormatNarrationPreset(StrictModel):
    """실측으로 검증된 낭독 값. rate 는 게이트 예산, max_silence 는 씬별 무음 상한(초)."""

    rate: float = Field(default=5.5, gt=0)
    max_silence: float = Field(default=0.0, ge=0)


class FormatPresets(StrictModel):
    """한 번의 제작 경험이 남긴 재사용 프리셋 묶음."""

    deliberation: FormatDeliberation = Field(default_factory=FormatDeliberation)
    copy_guide: dict[str, int] = Field(
        default_factory=dict, description="문안 필드 경로 → 실측 자수 상한"
    )
    dur_plan: dict[str, float] = Field(default_factory=dict, description="역할 → 확정 초")
    narration: FormatNarrationPreset = Field(default_factory=FormatNarrationPreset)


class FormatGolden(StrictModel):
    """검증된 레퍼런스 산출물 — 회귀 기준선."""

    run_id: str = ""
    artifacts: list[str] = Field(default_factory=list)
    qa_report: str = ""

    def registered(self) -> bool:
        """골든 등록 완료 판정 — run_id 와 산출물 경로가 둘 다 있어야 한다."""
        return bool(self.run_id and self.artifacts)


class FormatSpec(StrictModel):
    """포맷 정본 — 무대 크기·씬 골격·템플릿 풀·출력 규격의 단일 소유자."""

    id: str = Field(min_length=1, pattern=r"^[a-z][a-z0-9-]*$")
    name_ko: str = Field(min_length=1)
    stage: FormatStage
    duration: FormatDuration
    skeleton: list[str] = Field(min_length=1, description="씬 역할 순서 (템플릿 id 아님)")
    template_pool: dict[str, list[str]] = Field(description="역할 → 사용 가능한 tpl id (우선순위 순)")
    narration: FormatNarration = Field(default_factory=FormatNarration)
    outputs: list[str] = Field(default_factory=lambda: ["video", "pptx"])
    pptx: FormatPptx
    constraints: FormatConstraints = Field(default_factory=FormatConstraints)
    theme: str = Field(default="hwax-blue", min_length=1)

    # ── 승격 루프 필드 (PLAN §8.0) — 전부 기본값이라 기존 스펙은 그대로 로드된다 ──
    status: FormatStatus = "draft"
    origin: FormatOrigin = Field(default_factory=FormatOrigin)
    usage_count: int = Field(default=0, ge=0, description="이 포맷으로 완주한 산출물 수 (record_usage 집계)")
    presets: FormatPresets = Field(default_factory=FormatPresets)
    golden: FormatGolden = Field(default_factory=FormatGolden)
    lessons: list[str] = Field(default_factory=list, description="심의가 남긴 교훈 — 다음 회의가 인용한다")

    @model_validator(mode="after")
    def _presets_match_skeleton(self) -> "FormatSpec":
        """프리셋 키가 골격 역할을 벗어나면 거절한다 — 역할 개명 후 방치된 프리셋을 잡는다."""
        roles = set(self.skeleton)
        stray_dur = sorted(set(self.presets.dur_plan) - roles)
        if stray_dur:
            raise ValueError(
                f"presets.dur_plan 에 골격 밖 역할 {stray_dur} — skeleton {self.skeleton} 의 이름과 맞춰라"
            )
        stray_copy = sorted({k.split(".", 1)[0] for k in self.presets.copy_guide} - roles)
        if stray_copy:
            raise ValueError(
                f"presets.copy_guide 에 골격 밖 역할 {stray_copy} — 키를 '역할.필드' 로 쓰고 "
                f"skeleton {self.skeleton} 의 이름과 맞춰라"
            )
        return self

    @model_validator(mode="after")
    def _skeleton_pool_agree(self) -> "FormatSpec":
        missing = [r for r in self.skeleton if not self.template_pool.get(r)]
        if missing:
            raise ValueError(
                f"template_pool 에 비어 있는 역할 {missing} — skeleton 의 모든 역할에 tpl 을 1개 이상 선언하라"
            )
        orphans = sorted(set(self.template_pool) - set(self.skeleton))
        if orphans:
            raise ValueError(
                f"skeleton 에 없는 template_pool 역할 {orphans} — 역할명을 맞추거나 skeleton 에 추가하라"
            )
        return self

    # ── 파생 조회 ──────────────────────────────────────────────────────

    def tpl_ids(self) -> list[str]:
        """template_pool 전체 tpl id (skeleton 순서, 중복 제거)."""
        out: list[str] = []
        for role in self.skeleton:
            for tid in self.template_pool[role]:
                if tid not in out:
                    out.append(tid)
        return out

    def allows_tpl(self, tpl_ref: str) -> bool:
        """씬의 tpl 참조("opening@1"·"vtpl.hook@1")가 이 포맷의 풀에 있는지."""
        return tpl_short(tpl_ref) in {tpl_short(t) for t in self.tpl_ids()}

    def primary_tpl(self, role: str) -> str:
        """역할의 우선순위 1번 tpl id."""
        return self.template_pool[role][0]


# ── tpl 식별자 유틸 ─────────────────────────────────────────────────────


def tpl_short(x: str) -> str:
    """tpl 참조/모듈 id → 짧은 이름. "opening@1"·"tpl.opening"·"vtpl.hook@1" → "opening"/"hook"."""
    return x.split("@", 1)[0].rsplit(".", 1)[-1]


def tpl_major(tpl_ref: str) -> str | None:
    """tpl 참조의 메이저 버전 문자열. "@major" 가 없으면 None."""
    if "@" not in tpl_ref:
        return None
    return tpl_ref.split("@", 1)[1]


# ── 모듈 레지스트리 조회 ────────────────────────────────────────────────


def load_module_registry(modules_root: str | Path | None = None) -> dict[str, dict]:
    """modules/registry.yaml 의 모듈 인덱스를 {id: entry} 로 로드한다 (없으면 빈 dict)."""
    root = resolve_modules_root(modules_root)
    path = root / REGISTRY_FILE
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    out: dict[str, dict] = {}
    for entry in raw.get("modules", []) or []:
        if isinstance(entry, dict) and entry.get("id"):
            out[str(entry["id"])] = entry
    return out


def scene_template_ids(modules_root: str | Path | None = None) -> dict[str, str]:
    """레지스트리의 scene-template 모듈을 {짧은 이름: 모듈 id} 로 색인한다.

    "tpl.opening" → {"opening": "tpl.opening"}, "vtpl.hook" → {"hook": "vtpl.hook"}.
    짧은 이름이 겹치면 먼저 선언된 쪽을 남긴다(레지스트리 선언 순서 = 우선순위).
    """
    out: dict[str, str] = {}
    for mid, entry in load_module_registry(modules_root).items():
        if entry.get("type") != "scene-template":
            continue
        out.setdefault(tpl_short(mid), mid)
    return out


def resolve_tpl_module_id(
    tpl_ref: str,
    *,
    spec: FormatSpec | None = None,
    modules_root: str | Path | None = None,
) -> str:
    """씬 tpl 참조 → 레지스트리 모듈 id.

    해석 순서. ① 포맷 풀에서 짧은 이름 일치 ② 레지스트리 scene-template 색인
    ③ 실패 시 기존 규약대로 "tpl.{짧은 이름}" (레지스트리 부재 환경 호환).
    """
    short = tpl_short(tpl_ref)
    if spec is not None:
        for tid in spec.tpl_ids():
            if tpl_short(tid) == short:
                return tid
    found = scene_template_ids(modules_root).get(short)
    return found or f"tpl.{short}"


def module_dir(
    module_id: str, modules_root: str | Path | None = None
) -> Path:
    """모듈 id → module.yaml 이 있는 디렉터리.

    기본 규약(modules_root/scene-templates/{짧은 이름})을 먼저 보고, 없으면
    registry.yaml 의 path 선언을 따른다 — vtpl.* 처럼 디렉터리명이 다를 수 있다.
    """
    root = resolve_modules_root(modules_root)
    direct = root / "scene-templates" / tpl_short(module_id)
    if (direct / "module.yaml").is_file():
        return direct
    entry = load_module_registry(root).get(module_id) or {}
    declared = entry.get("path")
    if declared:
        rel = Path(str(declared))
        # registry 의 path 는 repo 루트 기준 "modules/..." 표기다.
        if rel.parts and rel.parts[0] == root.name:
            cand = root.parent / rel
            if (cand / "module.yaml").is_file():
                return cand
        cand = _REPO_ROOT / rel
        if (cand / "module.yaml").is_file():
            return cand
    return direct


def load_module_yaml(module_id: str, modules_root: str | Path | None = None) -> dict | None:
    """모듈 id → module.yaml 딕셔너리 (없거나 깨지면 None)."""
    path = module_dir(module_id, modules_root) / "module.yaml"
    if not path.is_file():
        return None
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 검증기는 수집만 한다
        return None
    return loaded if isinstance(loaded, dict) else None


def module_formats(module: dict) -> list[str]:
    """module.yaml 의 formats 선언. 미선언 = 기존 가로 무대(wide-16x9)."""
    declared = module.get("formats")
    if not declared:
        return [DEFAULT_FORMAT_ID]
    return [str(f) for f in declared]


# ── 로드 ────────────────────────────────────────────────────────────────


def format_path(format_id: str, formats_root: str | Path | None = None) -> Path:
    return resolve_formats_root(formats_root) / format_id / FORMAT_FILE


def list_formats(formats_root: str | Path | None = None) -> list[str]:
    """formats/ 아래 format.yaml 을 가진 디렉터리 id 목록 (사전순)."""
    root = resolve_formats_root(formats_root)
    if not root.is_dir():
        return []
    return sorted(d.name for d in root.iterdir() if (d / FORMAT_FILE).is_file())


def load_format(
    format_id: str,
    *,
    formats_root: str | Path | None = None,
    modules_root: str | Path | None = None,
    check_templates: bool = True,
) -> FormatSpec:
    """formats/{id}/format.yaml → 검증된 FormatSpec. 실패 시 FormatError.

    check_templates=True 면 template_pool 의 tpl 이 modules/registry.yaml 에 실재하고
    해당 모듈이 이 포맷을 지원한다고 선언했는지(module.yaml formats, 미선언=wide-16x9)까지 본다.
    """
    path = format_path(format_id, formats_root)
    if not path.is_file():
        known = list_formats(formats_root)
        raise FormatError(
            f"포맷 스펙 없음: {path} — 알려진 포맷은 {known or '(없음)'} 이다. "
            f"format 값을 고치거나 formats/{format_id}/{FORMAT_FILE} 을 작성하라"
        )
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        raise FormatError(f"포맷 스펙 파싱 실패: {path} — {e}") from None
    if not isinstance(raw, dict):
        raise FormatError(f"포맷 스펙이 매핑이 아니다: {path} — 최상위를 key: value 로 작성하라")
    try:
        spec = FormatSpec.model_validate(raw)
    except Exception as e:  # pydantic ValidationError 포함
        raise FormatError(f"포맷 스펙 검증 실패: {path}\n{e}") from None
    if spec.id != format_id:
        raise FormatError(
            f"포맷 id 불일치: 디렉터리 {format_id!r} ≠ 스펙 id {spec.id!r} — 둘을 같게 맞춰라"
        )
    if check_templates:
        problems = check_format_templates(spec, modules_root=modules_root)
        if problems:
            raise FormatError(
                f"포맷 {spec.id} 템플릿 미비 ({path})\n  - " + "\n  - ".join(problems)
            )
    return spec


def check_format_templates(
    spec: FormatSpec, *, modules_root: str | Path | None = None
) -> list[str]:
    """template_pool 의 tpl 실재·포맷 지원 선언을 검사해 문제 목록을 반환한다 (빈 목록=통과)."""
    registry = load_module_registry(modules_root)
    problems: list[str] = []
    for role in spec.skeleton:
        for tid in spec.template_pool[role]:
            entry = registry.get(tid)
            if entry is None:
                problems.append(
                    f"역할 {role!r}: 레지스트리에 없는 템플릿 {tid!r} — "
                    f"modules/{REGISTRY_FILE} 에 등록하거나 template_pool 에서 빼라"
                )
                continue
            if entry.get("type") != "scene-template":
                problems.append(
                    f"역할 {role!r}: {tid!r} 는 scene-template 이 아니다 (type={entry.get('type')!r})"
                )
                continue
            module = load_module_yaml(tid, modules_root)
            if module is None:
                problems.append(
                    f"역할 {role!r}: {tid!r} 의 module.yaml 을 찾지 못했다 "
                    f"({module_dir(tid, modules_root)})"
                )
                continue
            if spec.id not in module_formats(module):
                problems.append(
                    f"역할 {role!r}: {tid!r} 가 포맷 {spec.id!r} 를 지원한다고 선언하지 않았다 — "
                    f"module.yaml 에 formats: [{spec.id}] 를 추가하라"
                )
    return problems


# ── 사용 원장 (usage_count 자동 집계) ───────────────────────────────────


def usage_path(format_id: str, formats_root: str | Path | None = None) -> Path:
    return resolve_formats_root(formats_root) / format_id / USAGE_FILE


def load_usage(format_id: str, *, formats_root: str | Path | None = None) -> list[dict]:
    """formats/{id}/usage.jsonl 을 읽어 산출물 기록 목록으로 돌려준다 (없으면 빈 목록)."""
    path = usage_path(format_id, formats_root)
    if not path.is_file():
        return []
    runs: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("run_id"):
            runs.append(row)
    return runs


def record_usage(
    format_id: str,
    run_id: str,
    *,
    gate_errors: int = 0,
    qa_report: str = "",
    formats_root: str | Path | None = None,
) -> dict:
    """산출물 1건을 포맷 사용 원장에 기록하고 format.yaml 의 usage_count 를 재집계한다.

    같은 run_id 재기록은 무시한다(recorded=False) — 재렌더가 건수를 부풀리지 않게 한다.
    """
    path = usage_path(format_id, formats_root)
    if not path.parent.is_dir():
        raise FormatError(
            f"포맷 디렉터리 없음: {path.parent} — 알려진 포맷은 {list_formats(formats_root) or '(없음)'} 이다"
        )
    runs = load_usage(format_id, formats_root=formats_root)
    recorded = not any(r["run_id"] == run_id for r in runs)
    if recorded:
        row = {
            "run_id": run_id,
            "gate_errors": int(gate_errors),
            "qa_report": qa_report,
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        runs.append(row)
    count = len({r["run_id"] for r in runs})
    _set_top_level_scalar(format_path(format_id, formats_root), "usage_count", count)
    return {"format": format_id, "run_id": run_id, "recorded": recorded, "usage_count": count,
            "runs": [r["run_id"] for r in runs]}


def _set_top_level_scalar(path: Path, key: str, value: object) -> None:
    """format.yaml 의 최상위 스칼라 한 줄만 교체한다 — 주석·필드 순서를 보존하려고 재직렬화하지 않는다."""
    text = path.read_text(encoding="utf-8")
    line = f"{key}: {value}"
    pattern = re.compile(rf"^{re.escape(key)}:[^\n]*$", re.MULTILINE)
    if pattern.search(text):
        text = pattern.sub(line, text, count=1)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    path.write_text(text, encoding="utf-8")


# ── 승격 판정 ───────────────────────────────────────────────────────────


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def _verdict_check(verdicts: list[dict], *, meeting_types: frozenset[str], label: str) -> dict:
    """해당 유형의 심의 판정이 Go/Conditional-Go 인지 본다."""
    hits = [v for v in verdicts if str(v.get("type")) in meeting_types]
    passing = [v for v in hits if str(v.get("verdict")) in GO_VERDICTS]
    if passing:
        v = passing[-1]
        return _check(label, True, f"{v.get('type')} 판정 {v.get('verdict')} (회의 {v.get('meeting_id', '?')})")
    if hits:
        got = ", ".join(f"{v.get('type')}={v.get('verdict')}" for v in hits)
        return _check(label, False, f"{label} 미충족 — 제출된 판정은 [{got}], 필요한 것은 Go/Conditional-Go 다")
    need = "/".join(sorted(meeting_types))
    return _check(label, False, f"{label} 없음 — {need} 심의를 열고 판정을 evidence.verdicts 로 제출하라")


def promote_format(
    format_id: str,
    *,
    evidence: dict,
    formats_root: str | Path | None = None,
    modules_root: str | Path | None = None,
    apply: bool = True,
) -> dict:
    """포맷 승격을 판정하고(조건 충족 시) format.yaml 의 status 를 올린다.

    evidence = {
        "runs":     [{"run_id": ..., "gate_errors": 0, "qa_report": ...}],  # 생략 시 usage.jsonl
        "verdicts": [{"meeting_id": ..., "type": "scenario_build", "verdict": "Conditional-Go"}],
    }
    반환 = {format, status, target, promoted, applied, checks[], missing[]} — 미충족은 missing 에
    무엇이 얼마나 부족한지 수치로 적힌다.
    """
    spec = load_format(format_id, formats_root=formats_root, modules_root=modules_root)
    runs = list(evidence.get("runs") or load_usage(format_id, formats_root=formats_root))
    verdicts = list(evidence.get("verdicts") or [])
    target = PROMOTION_PATH.get(spec.status)

    if target is None:
        return {
            "format": format_id, "status": spec.status, "target": None,
            "promoted": False, "applied": False, "checks": [],
            "missing": [f"status={spec.status} 는 마지막 단계다 — 더 올릴 곳이 없다"],
        }

    n = len({str(r.get("run_id")) for r in runs if r.get("run_id")})
    need = 1 if target == "pilot" else 2
    checks = [_check("산출물", n >= need, f"산출물 {n}건 / 필요 {need}건" + (
        "" if n >= need else f" — {need - n}건 더 완주하고 record_usage 로 기록하라"))]

    if target == "pilot":
        unknown = [str(r.get("run_id")) for r in runs if r.get("gate_errors") is None]
        total_err = sum(int(r.get("gate_errors") or 0) for r in runs)
        if unknown:
            checks.append(_check("게이트", False, f"게이트 결과 미기록 {unknown} — qa_run 결과를 gate_errors 로 넣어라"))
        else:
            checks.append(_check("게이트", total_err == 0,
                                 f"게이트 error 합계 {total_err}건 / 허용 0건 (산출물 {n}건 집계)"))
        checks.append(_verdict_check(verdicts, meeting_types=PRODUCTION_MEETING_TYPES, label="제작 심의"))
    else:
        checks.append(_check("골든", spec.golden.registered(),
                             f"골든 run_id={spec.golden.run_id or '(미등록)'} · 산출물 {len(spec.golden.artifacts)}건"
                             + ("" if spec.golden.registered() else " — golden.run_id 와 artifacts 를 채워라")))
        checks.append(_verdict_check(verdicts, meeting_types=frozenset({"format_review"}), label="format_review"))

    missing = [c["detail"] for c in checks if not c["ok"]]
    promoted = not missing
    applied = False
    if promoted and apply:
        _set_top_level_scalar(format_path(format_id, formats_root), "status", target)
        applied = True
    return {
        "format": format_id, "status": target if applied else spec.status, "target": target,
        "promoted": promoted, "applied": applied, "checks": checks, "missing": missing,
    }


# ── 심의 브리핑용 프리셋 요약 ───────────────────────────────────────────


def format_presets_briefing(
    format_id: str,
    *,
    formats_root: str | Path | None = None,
    modules_root: str | Path | None = None,
) -> str:
    """이 장르의 노하우를 다음 심의가 인용할 수 있는 형태로 요약한다 (마크다운 문자열)."""
    spec = load_format(format_id, formats_root=formats_root, modules_root=modules_root)
    p = spec.presets
    L: list[str] = [
        f"## 포맷 {spec.id} — {spec.name_ko} ({spec.status} · 산출물 {spec.usage_count}건)",
        f"- 무대 {spec.stage.w}×{spec.stage.h} · 목표 {spec.duration.target:g}초 "
        f"(허용 {spec.duration.min:g}~{spec.duration.max:g}) · 최소 폰트 {spec.constraints.min_font} "
        f"· safe margin {spec.constraints.safe_margin}",
        "- 골격 " + " → ".join(
            f"{r}({spec.primary_tpl(r)})" for r in spec.skeleton
        ),
    ]
    if p.deliberation.type or p.deliberation.participants:
        L.append(
            f"- 심의 프리셋 — 유형 {p.deliberation.type or '(미정)'} · "
            f"참가자 {', '.join(p.deliberation.participants) or '(미정)'}"
        )
        for i, a in enumerate(p.deliberation.agenda, 1):
            L.append(f"  {i}. {a}")
    if p.dur_plan:
        total = sum(p.dur_plan.values())
        L.append("- 구간 예산(초) — " + " · ".join(
            f"{r} {p.dur_plan[r]:g}" for r in spec.skeleton if r in p.dur_plan
        ) + f" (합계 {total:g})")
    if p.copy_guide:
        L.append("- 카피 자수 상한 — " + " · ".join(
            f"{k} {v}자" for k, v in p.copy_guide.items()
        ))
    L.append(
        f"- 낭독 — 예산 {p.narration.rate:g}자/초"
        + (f" · 씬별 무음 상한 {p.narration.max_silence:g}초" if p.narration.max_silence else "")
    )
    if spec.golden.registered():
        L.append(
            f"- 골든 — run {spec.golden.run_id} · "
            + ", ".join(spec.golden.artifacts)
            + (f" · QA {spec.golden.qa_report}" if spec.golden.qa_report else "")
        )
    if spec.origin.meeting_id:
        L.append(f"- 출처 심의 — {spec.origin.meeting_id} ({spec.origin.created or '날짜 미상'})")
    if spec.lessons:
        L.append("- 교훈 (이전 심의가 남긴 것 — 재발명 대신 인용하라)")
        L.extend(f"  {i}. {t}" for i, t in enumerate(spec.lessons, 1))
    return "\n".join(L)
