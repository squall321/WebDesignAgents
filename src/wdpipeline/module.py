# 모듈 승격 판정 — 창작물이 재사용 자산이 되는 관문 (PLAN §6 창작 모드 → 재사용 모드)
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

__all__ = ["MODULE_PROMOTION_PATH", "module_status", "promote_module", "count_module_usage"]

_REPO_ROOT = Path(__file__).resolve().parents[2]

# 포맷과 같은 사다리. draft 는 "만들었다", pilot 은 "한 번 써 봤다", active 는 "기본으로 집어 쓴다".
MODULE_PROMOTION_PATH: dict[str, str] = {"draft": "pilot", "pilot": "active"}

# pilot 은 창작물이 계약을 지키는지만 본다. active 는 **다른 제작이 실제로 집어 썼는가**를
# 추가로 본다 — 쓰이지 않은 모듈을 기본값으로 올리면 재사용률이 숫자만 오른다.
ACTIVE_MIN_USAGE = 2


def _registry(modules_root: Path | None = None) -> tuple[Path, dict]:
    path = Path(modules_root or _REPO_ROOT / "modules") / "registry.yaml"
    return path, (yaml.safe_load(path.read_text(encoding="utf-8")) or {})


def _entry(module_id: str, modules_root: Path | None = None) -> dict:
    _, reg = _registry(modules_root)
    for m in reg.get("modules", []):
        if str(m.get("id")) == module_id:
            return m
    raise KeyError(f"레지스트리에 없는 모듈: {module_id}")


def module_status(module_id: str, modules_root: Path | None = None) -> str:
    return str(_entry(module_id, modules_root).get("status", "draft"))


def count_module_usage(module_id: str, pipeline_dir: Path | None = None) -> list[str]:
    """이 모듈을 실제로 쓴 실행 id 목록.

    씬의 tpl 참조("opening@1")를 모듈 id 로 바꾸는 정본은 build 다 — 여기서 다시 파싱하면
    세로 포맷(vtpl.*) 규칙이 갈라진다.
    """
    from wdpipeline.build import _tpl_id

    root = Path(pipeline_dir or _REPO_ROOT / "data" / "pipeline")
    runs: list[str] = []
    for scen in sorted(root.glob("*/scenario.json")):
        try:
            doc = json.loads(scen.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for sc in doc.get("scenes") or []:
            try:
                if _tpl_id(str(sc.get("tpl") or "")) == module_id:
                    runs.append(scen.parent.name)
                    break
            except (ValueError, KeyError):
                continue
    return runs


def _check(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _verdict_ok(verdicts: list[dict], module_id: str) -> tuple[bool, str]:
    """module_review 판정이 있는가. Go·Conditional-Go 만 통과로 본다."""
    for v in verdicts:
        if str(v.get("type")) != "module_review":
            continue
        if str(v.get("module_id") or module_id) != module_id:
            continue
        verdict = str(v.get("verdict") or "")
        if verdict in ("Go", "Conditional-Go"):
            return True, f"module_review 판정 {verdict} (회의 {v.get('meeting_id')})"
        return False, f"module_review 판정이 {verdict} 다 — 승격할 수 없다"
    return False, "module_review 없음 — 심의를 열고 판정을 evidence.verdicts 로 제출하라"


def promote_module(
    module_id: str,
    *,
    evidence: dict | None = None,
    modules_root: Path | None = None,
    pipeline_dir: Path | None = None,
    apply: bool = True,
) -> dict:
    """모듈 승격을 판정하고(조건 충족 시) module.yaml·registry.yaml 의 status 를 올린다.

    evidence = {"verdicts": [{"meeting_id", "type": "module_review", "verdict", "module_id"?}]}
    반환 = {module, status, target, promoted, applied, checks[], missing[]}
    """
    entry = _entry(module_id, modules_root)
    status = str(entry.get("status", "draft"))
    target = MODULE_PROMOTION_PATH.get(status)
    verdicts = list((evidence or {}).get("verdicts") or [])

    if target is None:
        return {"module": module_id, "status": status, "target": None, "promoted": False,
                "applied": False, "checks": [],
                "missing": [f"status={status} 는 마지막 단계다 — 더 올릴 곳이 없다"]}

    # entry["path"] 는 "modules/scene-templates/x" 꼴(리포 루트 상대)이다.
    # 샌드박스는 modules_root 가 tmp/modules 이므로 그 부모를 앵커로 쓴다.
    mod_dir = Path(modules_root or _REPO_ROOT / "modules").parent / entry["path"]
    my = yaml.safe_load((mod_dir / "module.yaml").read_text(encoding="utf-8")) or {}
    quality = my.get("quality") or {}
    repro = quality.get("reproducibility") or {}

    checks: list[dict] = []

    # 1) 재현력 — 같은 코드가 같은 그림을 내는가. 이게 아니면 재사용 자산이 아니다.
    verdict = str(repro.get("verdict") or "")
    checks.append(_check(
        "재현력", verdict == "pass",
        f"verdict={verdict or '(미검증)'} · max_diff={repro.get('max_diff_ratio', '?')}"
        + ("" if verdict == "pass" else " — `wda repro --module {0}` 로 검증하라".format(module_id)),
    ))

    # 2) 골든 — 회귀 기준선이 있어야 다음 변경을 잡는다.
    golden = mod_dir / "fixtures" / "snapshots" / "typical.png"
    # 샌드박스(tmp) 경로에서도 돌아야 한다 — relative_to 는 리포 밖이면 던진다
    try:
        shown: Any = golden.relative_to(_REPO_ROOT)
    except ValueError:
        shown = golden
    checks.append(_check("골든", golden.is_file(),
                         f"{shown}" + ("" if golden.is_file() else " 없음 — 스냅샷을 먼저 만들어라")))

    # 3) 게이트 — PLAN §6 "창작물은 게이트 1~7 통과 + module_review 심의를 거쳐"
    gates = list(quality.get("gates_passed") or [])
    checks.append(_check("게이트", bool(gates),
                         f"통과 기록 {len(gates)}건" + ("" if gates else
                         " — 게이트 7종을 돌리고 리포트 id 를 quality.gates_passed 에 적어라")))

    # 4) active 는 실사용을 추가로 본다 — 안 쓰인 모듈을 기본값으로 올리지 않는다.
    if target == "active":
        runs = count_module_usage(module_id, pipeline_dir)
        checks.append(_check(
            "실사용", len(runs) >= ACTIVE_MIN_USAGE,
            f"{len(runs)}개 실행에서 사용 / 필요 {ACTIVE_MIN_USAGE}개"
            + (f" ({', '.join(runs[:4])})" if runs else " — 아직 아무 제작도 집어 쓰지 않았다"),
        ))

    ok, detail = _verdict_ok(verdicts, module_id)
    checks.append(_check("module_review", ok, detail))

    missing = [c["detail"] for c in checks if not c["ok"]]
    promoted = not missing
    applied = False
    if promoted and apply:
        _set_status(mod_dir / "module.yaml", target)
        _set_registry_status(module_id, target, modules_root)
        _append_review(mod_dir / "module.yaml", verdicts, module_id, target)
        applied = True
    return {"module": module_id, "status": target if applied else status, "target": target,
            "promoted": promoted, "applied": applied, "checks": checks, "missing": missing}


def _set_status(path: Path, value: str) -> None:
    """status 한 줄만 갈아 끼운다 — YAML 재직렬화는 주석을 지운다."""
    import re

    text = path.read_text(encoding="utf-8")
    new, n = re.subn(r"^status:[ \t]*\S+[ \t]*$", f"status: {value}", text,
                     count=1, flags=re.MULTILINE)
    if n == 0:
        raise ValueError(f"status 줄을 찾지 못했다: {path}")
    path.write_text(new, encoding="utf-8")


def _set_registry_status(module_id: str, value: str, modules_root: Path | None = None) -> None:
    """registry.yaml 의 해당 모듈 블록 status 만 바꾼다 (주석·순서 보존)."""
    import re

    path, _ = _registry(modules_root)
    text = path.read_text(encoding="utf-8")
    # `- id: tpl.x` 블록 안의 첫 status 줄
    pattern = re.compile(
        rf"(^[ \t]*-[ \t]+id:[ \t]*{re.escape(module_id)}[ \t]*$.*?^([ \t]*)status:[ \t]*)\S+",
        re.MULTILINE | re.DOTALL,
    )
    new, n = pattern.subn(lambda m: m.group(1) + value, text, count=1)
    if n == 0:
        raise ValueError(f"registry.yaml 에서 {module_id} 의 status 를 찾지 못했다")
    path.write_text(new, encoding="utf-8")


def _append_review(path: Path, verdicts: list[dict], module_id: str, target: str) -> None:
    """승격 근거를 module.yaml 에 남긴다 — 회의록은 data/(gitignore)라 사라진다."""
    v = next((x for x in verdicts
              if str(x.get("type")) == "module_review"
              and str(x.get("module_id") or module_id) == module_id), None)
    if v is None:
        return
    line = (f'    - {{ to: {target}, meeting_id: "{v.get("meeting_id", "")}", '
            f'verdict: "{v.get("verdict", "")}", '
            f'date: "{datetime.now(timezone.utc).date().isoformat()}" }}\n')
    text = path.read_text(encoding="utf-8")
    if "  reviews:" not in text:
        return
    out: list[str] = []
    for ln in text.splitlines(keepends=True):
        if ln.rstrip() == "  reviews: []":
            out.append("  reviews:\n"); out.append(line)
        else:
            out.append(ln)
            if ln.rstrip() == "  reviews:":
                out.append(line)
    path.write_text("".join(out), encoding="utf-8")
