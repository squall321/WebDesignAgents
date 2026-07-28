# 포맷 스펙 계층 — formats/{id}/format.yaml 을 FormatSpec 으로 로드·검증하고 무대(stage)·골격의 단일 정본을 제공
from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import Field, model_validator

from wdcore.models.common import StrictModel

# repo 루트 (src/wdpipeline/format.py → 두 단계 위)
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FORMATS_ROOT = _REPO_ROOT / "formats"
DEFAULT_MODULES_ROOT = _REPO_ROOT / "modules"

# 포맷 미지정 시 적용되는 기존 가로 무대 — 이 값이 곧 회귀 방지선이다.
DEFAULT_FORMAT_ID = "wide-16x9"

FORMAT_FILE = "format.yaml"
REGISTRY_FILE = "registry.yaml"


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
