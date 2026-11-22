# W-4 — MCP 는 주인 있는 run 에 닿지 않는다
#
# MCP 의 신원은 확인할 수 없다. 게이트웨이는 백엔드마다 상주 세션 하나로 허브 서비스 토큰을
# 싣고, /mcp 로 오는 X-Heax-User-Email 은 그 토큰의 주인(허브 첫 관리자)으로 **접힌다**.
# 그래서 주인은 REST 에서만 정하고(W-1), MCP 는 주인 있는 run 을 **없는 것으로** 본다.
# MCP 와 웹 run 은 같은 pipeline/ 을 쓰므로 막지 않으면 남의 보고서에 닿는다.
#
# W-18 — 확인된 주인에게만 연다. 게이트웨이 사람별 위임이 켜진 박스에서는 서명된 단언으로 호출자가
# 확인된다(wdmcp.delegation). 그때만 '그 사람이 주인인 run' 을 연다 — 판정은 closed_to 한 곳이다.
#
# M3(사용자 결정 2026-11-22) — 회의에 주인 칸(meta.owner)을 두고, 주인 있는 회의는 그 주인에게만 보인다(OwnedMeetingStore).
# 경로는 실제 자리로 판정한다(resolve) — `pipeline/<남>/../<주인 있는 run>` 처럼 돌아 들어가는 경로가 조각 비교를 비켜 가지 않게.
from __future__ import annotations

from pathlib import Path

from wdcore.meetings.store import MeetingStore
from wdcore.models.meeting import MeetingMeta

__all__ = ["owned_run_ids", "owned_slugs", "is_owned_run", "is_owned_path", "closed_to", "owned_runs_at",
           "run_owner", "OwnedMeetingStore"]


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


def _owned_hits(run_ids=(), paths=()) -> list[dict]:
    """이 run id · 서버 경로들이 가리키는 주인 있는 run 들(경로는 실제 자리로 — resolve)."""
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
        try:
            real = Path(str(path)).expanduser().resolve(strict=False)
        except (OSError, RuntimeError, ValueError):
            real = Path(str(path))
        for parts in {Path(str(path)).parts, real.parts}:
            for seg, nxt in zip(parts, parts[1:]):
                if seg == "pipeline" and nxt in by_id:
                    hits.append(by_id[nxt])
                elif seg in ("build", "renders"):
                    hits.extend(by_slug.get(nxt, ()))
    return hits


def closed_to(who: str | None, *, run_ids=(), paths=()) -> bool:
    """이 run id · 서버 경로들이 가리키는 주인 있는 run 가운데 **who 의 것이 아닌 것**이 하나라도 있는가.

    who 는 확인된 신원(없으면 None — 그때는 주인 있는 run 전부가 닫힌다, W-4 그대로)이다. 주인 없는 run 은
    누구에게도 닫히지 않는다. 지운 실행(deleted_at — 묘비)은 주인에게도 닫힌다. build · renders 의 slug 가
    겹친 두 실행은 **둘 다** 그 사람 것일 때만 열린다 — 한 사람의 신원으로 다른 주인의 조각에 닿지 않게.
    """
    return any(r.get("owner") != who or r.get("deleted_at") for r in _owned_hits(run_ids, paths))


def owned_runs_at(paths=()) -> set[str]:
    """이 경로들이 놓인 주인 있는 run 의 id — 그 원본을 주인 없는 실행으로 옮기는지 볼 때 쓴다."""
    return {str(r["run_id"]) for r in _owned_hits((), paths)}


def run_owner(run_id: str | None) -> str | None:
    """웹 원장의 그 run 의 주인(없거나 주인 없는 run 이면 None)."""
    if not run_id:
        return None
    for r in _runs():
        if str(r.get("run_id")) == str(run_id):
            return r.get("owner") or None
    return None


def _meeting_visible(meta: MeetingMeta) -> bool:
    from .delegation import caller

    return meta.owner is None or meta.owner == caller()


class OwnedMeetingStore(MeetingStore):
    """회의 저장소 — 주인 있는 회의(meta.owner)는 그 주인(확인된 신원)에게만 보인다. 남 · 신원 없음에게는 **없는 회의와 같다**
    (find_dir 이 같은 FileNotFoundError 를 낸다 — load · 원장 되살리기 · 회의록 모두 이 문을 지난다). 목록에서도 빠진다.
    주인 없는 회의는 지금 그대로 모두에게 열려 있다. 쓰기(save_meta · append_turn)는 load 를 지난 뒤라 따로 막지 않는다."""

    def find_dir(self, meeting_id: str) -> Path:
        d = super().find_dir(meeting_id)
        meta = MeetingMeta.model_validate_json((d / "meta.json").read_text(encoding="utf-8"))
        if not _meeting_visible(meta):
            raise FileNotFoundError(f"회의를 찾을 수 없다: {meeting_id}")
        return d

    def list_meetings(self) -> list[MeetingMeta]:
        return [m for m in super().list_meetings() if _meeting_visible(m)]
