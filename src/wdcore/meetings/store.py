# 회의 영속화 — meetings_dir 아래 meta.json/turns.jsonl/minutes.md 저장·복원 (파일이 진실)
# 원본: /home/koopark/claude/ExpertAgents/src/expertcore/meetings/store.py (copy-adapt: import 경로만 wdcore로)
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from wdcore.config import get_settings
from wdcore.models.meeting import MeetingMeta, MeetingTurn

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(topic: str, max_len: int = 40) -> str:
    """주제를 영문 소문자-하이픈 슬러그로 축약. 비ASCII는 제거하고 비면 'topic' 폴백."""
    ascii_text = unicodedata.normalize("NFKD", topic).encode("ascii", "ignore").decode()
    slug = _SLUG_RE.sub("-", ascii_text.lower()).strip("-")[:max_len].strip("-")
    return slug or "topic"


class MeetingStore:
    """회의 디렉터리 1개 = 회의 1건. 디렉터리명은 {YYYYMMDD-HHMMSS}_{type}_{slug}_{id4}."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or get_settings().meetings_dir

    # --- 경로 ---
    def dir_for(self, meta: MeetingMeta) -> Path:
        stamp = meta.created_at.strftime("%Y%m%d-%H%M%S")
        return self.root / f"{stamp}_{meta.type.value}_{_slugify(meta.topic)}_{meta.id[:4]}"

    def find_dir(self, meeting_id: str) -> Path:
        """회의 id로 디렉터리를 찾는다. 없으면 FileNotFoundError."""
        if self.root.is_dir():
            for d in sorted(self.root.iterdir()):
                meta_file = d / "meta.json"
                if d.is_dir() and d.name.endswith(f"_{meeting_id[:4]}") and meta_file.is_file():
                    meta = MeetingMeta.model_validate_json(meta_file.read_text(encoding="utf-8"))
                    if meta.id == meeting_id:
                        return d
        raise FileNotFoundError(f"회의를 찾을 수 없다: {meeting_id}")

    # --- 저장 ---
    def save_meta(self, meta: MeetingMeta) -> Path:
        d = self.dir_for(meta)
        d.mkdir(parents=True, exist_ok=True)
        (d / "meta.json").write_text(meta.model_dump_json(indent=2), encoding="utf-8")
        return d

    def append_turn(self, meta: MeetingMeta, turn: MeetingTurn) -> None:
        d = self.dir_for(meta)
        d.mkdir(parents=True, exist_ok=True)
        with (d / "turns.jsonl").open("a", encoding="utf-8") as f:
            f.write(turn.model_dump_json() + "\n")

    def save_minutes(self, meta: MeetingMeta, markdown: str) -> Path:
        d = self.dir_for(meta)
        d.mkdir(parents=True, exist_ok=True)
        path = d / "minutes.md"
        path.write_text(markdown, encoding="utf-8")
        return path

    # --- 복원 ---
    def load(self, meeting_id: str) -> tuple[MeetingMeta, list[MeetingTurn]]:
        """회의 id로 meta와 전체 턴을 복원한다 (resume 진입점)."""
        d = self.find_dir(meeting_id)
        meta = MeetingMeta.model_validate_json((d / "meta.json").read_text(encoding="utf-8"))
        turns: list[MeetingTurn] = []
        turns_file = d / "turns.jsonl"
        if turns_file.is_file():
            for line in turns_file.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    turns.append(MeetingTurn.model_validate_json(line))
        return meta, turns

    def list_meetings(self) -> list[MeetingMeta]:
        """저장 루트의 모든 회의 메타를 디렉터리명 순으로 반환한다."""
        metas: list[MeetingMeta] = []
        if self.root.is_dir():
            for d in sorted(self.root.iterdir()):
                meta_file = d / "meta.json"
                if d.is_dir() and meta_file.is_file():
                    metas.append(MeetingMeta.model_validate_json(meta_file.read_text(encoding="utf-8")))
        return metas
