# W-4 — MCP 는 주인 있는 run 에 닿지 않는다
#
# MCP 의 신원은 확인할 수 없다. 게이트웨이는 백엔드마다 상주 세션 하나로 허브 서비스 토큰을
# 싣고, /mcp 로 오는 X-Heax-User-Email 은 그 토큰의 주인(허브 첫 관리자)으로 **접힌다**.
# 그래서 주인은 REST 에서만 정하고(W-1), MCP 는 주인 있는 run 을 **없는 것으로** 본다.
# MCP 와 웹 run 은 같은 pipeline/ 을 쓰므로 막지 않으면 남의 보고서에 닿는다.
#
# W-18 — 확인된 주인에게만 연다. 게이트웨이 사람별 위임이 켜진 박스에서는 서명된 단언으로 호출자가
# 확인된다(wdmcp.delegation). 그때만 '그 사람이 주인인 run' 을 연다 — 판정은 closed_to 한 곳이다.
from __future__ import annotations

from pathlib import Path

__all__ = ["owned_run_ids", "owned_slugs", "is_owned_run", "is_owned_path", "closed_to"]


def _runs() -> list[dict]:
    try:
        from wdweb.runs import list_runs

        return list_runs()
    except Exception:  # noqa: BLE001 — 웹 원장을 못 읽으면 막을 근거가 없다(종전대로 연다)
        return []


def owned_run_ids() -> set[str]:
    return {str(r["run_id"]) for r in _runs() if r.get("owner")}


def owned_slugs() -> set[str]:
    """주인 있는 run 의 build·renders 디렉터리 이름 — 경로로 들어오는 도구를 막는다."""
    return {str(r["slug"]) for r in _runs() if r.get("owner") and r.get("slug")}


def is_owned_run(run_id: str | None) -> bool:
    return bool(run_id) and str(run_id) in owned_run_ids()


def is_owned_path(path: str | Path | None) -> bool:
    """경로가 주인 있는 run 의 pipeline/ · build/ · renders/ 아래인가.

    경로 문자열을 그대로 비교하지 않고 **조각**으로 본다 — `/a/pipeline/<id>/x` 든
    `pipeline/<id>` 든 같은 판정을 내려야 한다.
    """
    if not path:
        return False
    parts = Path(str(path)).parts
    ids, slugs = owned_run_ids(), owned_slugs()
    for i, seg in enumerate(parts):
        nxt = parts[i + 1] if i + 1 < len(parts) else None
        if nxt is None:
            continue
        if seg == "pipeline" and nxt in ids:
            return True
        if seg in ("build", "renders") and nxt in slugs:
            return True
    return False


def closed_to(who: str | None, *, run_ids=(), paths=()) -> bool:
    """이 run id · 서버 경로들이 가리키는 주인 있는 run 가운데 **who 의 것이 아닌 것**이 하나라도 있는가.

    who 는 확인된 신원(없으면 None — 그때는 주인 있는 run 전부가 닫힌다, W-4 그대로)이다. 주인 없는 run 은
    누구에게도 닫히지 않는다. 지운 실행(deleted_at — 묘비)은 주인에게도 닫힌다. build · renders 의 slug 가
    겹친 두 실행은 **둘 다** 그 사람 것일 때만 열린다 — 한 사람의 신원으로 다른 주인의 조각에 닿지 않게.
    """
    owned = [r for r in _runs() if r.get("owner")]
    by_id = {str(r.get("run_id")): r for r in owned}
    by_slug: dict[str, list[dict]] = {}
    for r in owned:
        if r.get("slug"):
            by_slug.setdefault(str(r["slug"]), []).append(r)
    hits: list[dict] = [by_id[str(x)] for x in run_ids if x and str(x) in by_id]
    for path in paths:
        if not path:
            continue
        parts = Path(str(path)).parts
        for seg, nxt in zip(parts, parts[1:]):
            if seg == "pipeline" and nxt in by_id:
                hits.append(by_id[nxt])
            elif seg in ("build", "renders"):
                hits.extend(by_slug.get(nxt, ()))
    return any(r.get("owner") != who or r.get("deleted_at") for r in hits)
