# 성장 지표 계산 — 게이트 1회차 통과율·모듈 재사용률·토큰 추이 (PLAN §6 효과, §11 우상향 장치 ③)
from __future__ import annotations

import json
import subprocess
from functools import lru_cache
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

__all__ = ["collect_metrics", "first_pass_rate", "module_reuse", "token_trend"]

REPO_ROOT = Path(__file__).resolve().parents[2]
REUSE_TARGET = 0.80   # PLAN §6 "모듈 재사용률 80% 목표선"


def _iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


# ── ① 게이트 1회차 통과율 ────────────────────────────────────────────────


def first_pass_rate(reports_dir: Path) -> dict:
    """빌드마다 **처음 돌린** QA 가 통과했는지의 비율.

    전체 통과율이 아니라 1회차를 보는 이유 — 고칠 때까지 다시 돌리면 결국 통과하므로
    전체 통과율은 항상 1 에 수렴한다. 품질이 오르고 있는지는 "처음에 맞았나" 가 말한다.
    """
    by_build: dict[str, list[tuple[datetime, bool, str]]] = {}
    unreadable = 0
    for path in sorted(Path(reports_dir).glob("*/qa.json")):
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            unreadable += 1
            continue
        build = str(d.get("build_dir") or "")
        at = _iso(d.get("created_at"))
        if not build or at is None:
            continue
        by_build.setdefault(build, []).append((at, bool(d.get("passed")), path.parent.name))

    firsts = []
    for build, rows in by_build.items():
        rows.sort(key=lambda r: r[0])
        at, passed, rid = rows[0]
        firsts.append({"build": build, "at": at.isoformat(), "passed": passed,
                       "report": rid, "attempts": len(rows)})
    n = len(firsts)
    ok = sum(1 for f in firsts if f["passed"])
    return {
        "builds": n,
        "first_pass": ok,
        "rate": round(ok / n, 4) if n else None,
        "reports_read": sum(len(v) for v in by_build.values()),
        "unreadable": unreadable,
        "recent": sorted(firsts, key=lambda f: f["at"], reverse=True)[:10],
    }


# ── ② 모듈 재사용률 ──────────────────────────────────────────────────────


@lru_cache(maxsize=512)
def _to_module_id(tpl_ref: str) -> str:
    """씬 tpl 참조 → 모듈 id. 변환 규칙은 wdpipeline.build 가 정본이다.

    캐시하는 이유 — 정본 변환기는 호출마다 registry.yaml 을 다시 읽는다. 씬 468개를
    돌리면 그것만 7.7초다(실측). 참조 문자열은 유한하므로 캐시가 정확히 맞는 도구다.
    """
    if not tpl_ref:
        return ""
    try:
        from wdpipeline.build import _tpl_id

        return _tpl_id(tpl_ref)
    except (ImportError, ValueError, KeyError):
        return tpl_ref


def _module_birthdays() -> dict[str, datetime]:
    """module.yaml 이 처음 추가된 시각을 **한 번의 git 호출**로 전부 받는다.

    모듈마다 git log 를 부르면 40종에 7.7초가 걸린다(실측) — 대시보드가 그만큼 늦다.
    `--name-only` 한 번이면 같은 답을 0.1초에 얻는다. module.yaml 에는 생성일 필드가
    없으므로 git 이 진실이다.
    """
    try:
        out = subprocess.run(
            ["git", "log", "--diff-filter=A", "--name-only", "--format=@%aI",
             "--", "modules"],
            cwd=REPO_ROOT, capture_output=True, text=True, timeout=60, check=False,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    born: dict[str, datetime] = {}
    when: datetime | None = None
    for line in out.splitlines():
        if line.startswith("@"):
            when = _iso(line[1:])
        elif line.endswith("/module.yaml") and when is not None:
            # 최신 커밋부터 나오므로 나중에 만나는 값(더 오래된 커밋)이 진짜 추가 시점이다
            born[str(Path(line).parent)] = when
    return born


def module_reuse(pipeline_dir: Path, modules_root: Path | None = None) -> dict:
    """실행마다 '이미 있던 모듈로 채운 씬' 의 비율 (PLAN §6 창작 모드 vs 재사용 모드).

    창작 모드는 그 실행을 위해 **새 모듈을 만든** 경우다. 그래서 기준은 씬이 쓴 tpl 이
    그 실행보다 **먼저** 레지스트리에 있었는가다. 모든 tpl 이 지금은 등록돼 있으므로
    "등록 여부" 로 재면 항상 100% 가 나온다 — 시점을 봐야 의미가 생긴다.

    ⚠ 시점의 근사 — 모듈 쪽은 git 커밋 시각, 실행 쪽은 scenario.json 수정 시각이다.
    둘 다 진짜 시점보다 늦거나 이를 수 있다(작성 후 몇 시간 뒤 커밋, 시나리오 재저장).
    같은 날 만든 모듈을 같은 날 쓴 실행은 경계에 걸린다. 추세를 보는 지표이지 감사
    증적이 아니다 — 한 실행의 수치로 무엇을 단정하지 마라.
    """
    import yaml

    root = Path(modules_root or REPO_ROOT / "modules")
    reg = yaml.safe_load((root / "registry.yaml").read_text(encoding="utf-8")) or {}
    born = _module_birthdays()
    added: dict[str, datetime | None] = {}
    for m in reg.get("modules", []):
        if m.get("type") != "scene-template":
            continue
        added[str(m["id"])] = born.get(str(m["path"]).rstrip("/"))

    runs = []
    for scen in sorted(Path(pipeline_dir).glob("*/scenario.json")):
        try:
            doc = json.loads(scen.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        scenes = doc.get("scenes") or []
        if not scenes:
            continue
        # 실행 시각은 시나리오 파일의 수정 시각을 쓴다 (시나리오에 시각 필드가 없다)
        at = datetime.fromtimestamp(scen.stat().st_mtime, tz=timezone.utc)
        reused, created, unknown = [], [], []
        for sc in scenes:
            # 씬의 tpl 은 "opening@1" 꼴 참조다 — 모듈 id 로 바꾸는 정본은 build 에 있다.
            # 여기서 다시 파싱하면 세로 포맷(vtpl.*) 규칙이 갈라진다.
            tpl = _to_module_id(str(sc.get("tpl") or ""))
            born = added.get(tpl)
            if born is None:
                unknown.append(tpl)
            elif born <= at:
                reused.append(tpl)
            else:
                created.append(tpl)
        known = len(reused) + len(created)
        runs.append({
            "run_id": scen.parent.name, "at": at.isoformat(), "scenes": len(scenes),
            "reused": len(reused), "created": len(created), "unknown": len(unknown),
            "rate": round(len(reused) / known, 4) if known else None,
        })

    rates = [r["rate"] for r in runs if r["rate"] is not None]
    total_reused = sum(r["reused"] for r in runs)
    total_known = sum(r["reused"] + r["created"] for r in runs)
    return {
        "runs": len(runs),
        "scenes": sum(r["scenes"] for r in runs),
        "rate": round(total_reused / total_known, 4) if total_known else None,
        "target": REUSE_TARGET,
        "meets_target": (total_reused / total_known >= REUSE_TARGET) if total_known else None,
        "runs_below_target": sum(1 for r in rates if r < REUSE_TARGET),
        "recent": sorted(runs, key=lambda r: r["at"], reverse=True)[:10],
    }


# ── ③ 토큰 추이 ─────────────────────────────────────────────────────────


def token_trend(meetings_dir: Path) -> dict:
    """심의 1건당 토큰. **vLLM 이 발언한 회의만** 잡힌다.

    MCP 경로는 클라이언트(Claude)가 페르소나를 연기하므로 서버가 LLM 을 부르지 않는다
    ("서버는 LLM을 호출하지 않는다"). 그 회의의 토큰은 이 서버가 알 수 없다 —
    분모를 전체 회의로 잡으면 추이가 거짓이 되므로 계측 범위를 함께 보고한다.
    """
    rows = []
    total_meetings = 0
    for meta in sorted(Path(meetings_dir).glob("*/meta.json")):
        total_meetings += 1
        usage = meta.parent / "usage.json"
        if not usage.is_file():
            continue
        try:
            u = json.loads(usage.read_text(encoding="utf-8"))
            m = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        tok = u.get("usage") if isinstance(u.get("usage"), dict) else u
        rows.append({
            "meeting_id": m.get("id"), "type": m.get("type"), "at": m.get("created_at"),
            "turns": u.get("turns_submitted") or u.get("turns"),
            "total_tokens": int(tok.get("total_tokens") or 0),
            "calls": int(tok.get("calls") or 0),
        })
    rows.sort(key=lambda r: str(r["at"]))
    toks = [r["total_tokens"] for r in rows if r["total_tokens"]]
    return {
        "meetings_total": total_meetings,
        "meetings_measured": len(rows),
        "coverage_note": "vLLM 무인 심의만 계측된다 — MCP 경로는 서버가 LLM 을 부르지 않는다",
        "avg_tokens": round(sum(toks) / len(toks)) if toks else None,
        "per_turn": (round(sum(toks) / sum(r["turns"] or 0 for r in rows))
                     if toks and sum(r["turns"] or 0 for r in rows) else None),
        "recent": rows[-10:],
    }


def collect_metrics(data_dir: Path | None = None) -> dict:
    """세 지표를 한 번에 모은다 (CLI·웹·MCP 가 같은 함수를 쓴다)."""
    d = Path(data_dir or REPO_ROOT / "data")
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gate_first_pass": first_pass_rate(d / "qa_reports"),
        "module_reuse": module_reuse(d / "pipeline"),
        "tokens": token_trend(d / "meetings"),
    }
