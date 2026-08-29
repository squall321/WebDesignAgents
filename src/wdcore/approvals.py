# 사람 개입 지점(HITL 5종) 승인 원장 — 누가 무엇을 왜 통과시켰나를 파일로 남긴다
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

__all__ = [
    "HITL_POINTS", "Approval", "ApprovalStore",
    "unattended_mode", "UnattendedRule",
]

# PLAN §11 — 사람이 반드시 보아야 하는 다섯 자리.
# 값은 "그 승인이 없을 때 무엇이 잘못되는가" 다. 이름만으로는 왜 필요한지 잊힌다.
HITL_POINTS: dict[str, str] = {
    "participants": "참가자 확정 — 확정 순서가 곧 발언 순서다. 잘못 고르면 심의 전체가 헛돈다",
    "scenario": "시나리오 확정 — 여기서 통과한 것이 영상·PPT·문서 전부의 원본이 된다",
    "shipping": "출하 승인 — 게이트를 통과했어도 내보낼지는 사람이 정한다",
    "action_items": "Conditional-Go 액션아이템 이행 확인 — 조건이 이행됐는지 보고 재심의를 연다",
    "golden": "골든 갱신 승인 — 회귀 기준선을 지우는 일이다. 이유 없이 지우면 가드가 사라진다",
}

_UNSAFE = re.compile(r"[^A-Za-z0-9._가-힣-]+")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Approval:
    """승인 1건. subject 는 대상 식별자(run_id·module id·format id…)다."""

    point: str
    subject: str
    decision: str = "approve"      # approve | reject
    reason: str = ""
    by: str = ""                   # 사람 이름/계정. 무인 모드면 규칙 이름이 들어간다
    mode: str = "manual"           # manual | unattended
    evidence: dict = field(default_factory=dict)   # 회의 id·QA 리포트·diff 등
    at: str = field(default_factory=_now)

    def __post_init__(self) -> None:
        if self.point not in HITL_POINTS:
            raise ValueError(
                f"알 수 없는 개입 지점: {self.point} — {', '.join(HITL_POINTS)} 중 하나여야 한다"
            )
        if self.decision not in ("approve", "reject"):
            raise ValueError(f"decision 은 approve|reject — 받은 값 {self.decision!r}")
        if not str(self.subject).strip():
            raise ValueError("subject 가 비었다 — 무엇을 승인하는지 없이는 기록이 무의미하다")
        if self.decision == "approve" and not self.reason.strip():
            # 이유 없는 승인은 나중에 아무도 되짚을 수 없다. 무인 모드도 규칙 이름을 낸다.
            raise ValueError("승인에는 reason 이 필요하다 — 왜 통과시켰는지가 기록의 전부다")


@dataclass
class UnattendedRule:
    """무인 모드에서 자동 확정을 허용하는 규칙 (PLAN §11 ② 검증기 통과 시 자동 확정)."""

    name: str
    point: str
    requires: tuple[str, ...] = ()   # evidence 에 반드시 있어야 하는 키

    def check(self, evidence: dict) -> str | None:
        """통과하면 None, 막히면 사유 문자열.

        ⚠ 존재 여부로 본다. truthy 로 보면 `gate_errors: 0`·`validation_errors: []` 처럼
        **좋은 값이 0/빈값인 근거**가 없는 것으로 취급돼, 깨끗한 빌드일수록 거절된다.
        """
        missing = [k for k in self.requires
                   if k not in evidence or evidence[k] is None]
        if missing:
            return f"무인 자동 확정 조건 미충족 — {', '.join(missing)} 근거가 없다"
        return None


# 자동 확정이 허용되는 지점과 그 조건. **골든은 없다** — 회귀 기준선을 무인으로 지우면
# 가드가 조용히 사라지고 아무도 눈치채지 못한다. 사람이 봐야 하는 자리를 규칙으로 대체할 때
# 무엇을 근거로 삼는지가 곧 그 자동화의 신뢰도다.
UNATTENDED_RULES: dict[str, UnattendedRule] = {
    "participants": UnattendedRule("roster-fixed", "participants", ("participants",)),
    "scenario": UnattendedRule("validator-clean", "scenario", ("validation_errors",)),
    "shipping": UnattendedRule("gates-clean", "shipping", ("qa_report", "gate_errors")),
    "action_items": UnattendedRule("all-items-closed", "action_items", ("closed", "total")),
}


def unattended_mode(env: dict | None = None) -> bool:
    """무인 모드 여부. 기본은 꺼짐 — 켜는 것은 명시적 선택이어야 한다."""
    src = env if env is not None else os.environ
    return str(src.get("WDA_UNATTENDED", "")).strip().lower() in ("1", "true", "yes", "on")


class ApprovalStore:
    """승인 원장 — 파일이 진실이다. 지점/대상별 최신 결정을 조회한다."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, point: str, subject: str) -> Path:
        key = _UNSAFE.sub("-", str(subject)).strip("-")[:120] or "unnamed"
        return self.root / point / f"{key}.json"

    def record(self, approval: Approval) -> Path:
        path = self._path(approval.point, approval.subject)
        path.parent.mkdir(parents=True, exist_ok=True)
        history = []
        if path.is_file():
            try:
                history = json.loads(path.read_text(encoding="utf-8")).get("history") or []
            except ValueError:
                history = []
        history.append(asdict(approval))
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps({"point": approval.point, "subject": approval.subject,
                        "latest": asdict(approval), "history": history},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(path)
        return path

    def latest(self, point: str, subject: str) -> Approval | None:
        path = self._path(point, subject)
        if not path.is_file():
            return None
        try:
            d = json.loads(path.read_text(encoding="utf-8")).get("latest") or {}
        except ValueError:
            return None
        try:
            return Approval(**d)
        except (TypeError, ValueError):
            return None

    def is_approved(self, point: str, subject: str) -> bool:
        a = self.latest(point, subject)
        return bool(a and a.decision == "approve")

    def pending(self, point: str | None = None) -> list[dict]:
        """거절됐거나 아직 승인되지 않은 기록. 승인 없는 대상은 파일 자체가 없으므로
        여기서는 '거절로 막힌 것' 만 나온다 — 대기 목록은 호출자가 대상 목록과 대조한다."""
        out = []
        points = [point] if point else list(HITL_POINTS)
        for p in points:
            for f in sorted((self.root / p).glob("*.json")):
                try:
                    d = json.loads(f.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                latest = d.get("latest") or {}
                if latest.get("decision") != "approve":
                    out.append(latest)
        return out

    def require(self, point: str, subject: str, *, evidence: dict | None = None,
                env: dict | None = None) -> Approval:
        """승인이 있어야 진행한다. 없으면 무인 규칙을 시도하고, 그것도 안 되면 막는다.

        무인 모드는 사람을 없애는 게 아니라 **근거가 충분할 때만** 대신 눌러 준다.
        규칙이 없는 지점(골든)은 무인 모드여도 통과하지 않는다.
        """
        existing = self.latest(point, subject)
        if existing and existing.decision == "approve":
            return existing
        if existing and existing.decision == "reject":
            raise PermissionError(
                f"{HITL_POINTS[point]} — '{subject}' 는 거절됐다: {existing.reason}"
            )
        if unattended_mode(env):
            rule = UNATTENDED_RULES.get(point)
            if rule is None:
                raise PermissionError(
                    f"{HITL_POINTS[point]} — 이 지점은 무인 자동 확정이 없다. "
                    "사람이 승인해야 한다"
                )
            blocked = rule.check(evidence or {})
            if blocked:
                raise PermissionError(f"{HITL_POINTS[point]} — {blocked}")
            auto = Approval(point=point, subject=subject, mode="unattended",
                            by=f"rule:{rule.name}", reason=f"무인 자동 확정 규칙 {rule.name}",
                            evidence=dict(evidence or {}))
            self.record(auto)
            return auto
        raise PermissionError(
            f"{HITL_POINTS[point]} — '{subject}' 승인이 없다. "
            f"승인하려면 이유와 함께 기록하라 (wda approve {point} {subject} --reason ...)"
        )
