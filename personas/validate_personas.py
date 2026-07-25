# 페르소나 14인 persona.yaml + 지식카드 frontmatter를 PyYAML로 파싱하고 필수 키·표기 규칙을 검사하는 검증 스크립트
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent

# PLAN §5.1 로스터 — id: (abbr, category)
ROSTER: dict[str, tuple[str, str]] = {
    "dir-creative-director": ("CD", "dir"),
    "narr-story-architect": ("ST", "narr"),
    "narr-copywriter": ("CP", "narr"),
    "vis-typographer": ("TY", "vis"),
    "vis-color-brand": ("CB", "vis"),
    "vis-layout-grid": ("LG", "vis"),
    "vis-dataviz": ("DV", "vis"),
    "mot-motion-director": ("MO", "mot"),
    "ux-accessibility": ("AX", "ux"),
    "ux-audience-advocate": ("AU", "ux"),
    "impl-technical-director": ("TD", "impl"),
    "impl-slide-editor": ("SL", "impl"),
    "av-narration": ("NR", "av"),
    "qa-consistency": ("QA", "qa"),
}

CATEGORIES = {"dir", "narr", "vis", "mot", "ux", "impl", "av", "qa"}

TOP_KEYS = ["id", "abbr", "name_ko", "name_en", "category", "status",
            "persona", "expertise", "routing", "related_experts", "meeting"]
PERSONA_KEYS = ["title", "career_background", "speaking_style", "system_prompt"]
EXPERTISE_KEYS = ["in_scope", "out_of_scope", "boundary_statement"]
ROUTING_KEYS = ["keywords_ko", "keywords_en", "example_questions", "anti_examples"]
MEETING_KEYS = ["default_role", "stance"]

CARD_KEYS = ["id", "expert_id", "title", "type", "confidence", "tier", "sources", "version"]
# 담당 전문가별 기대 카드 수
EXPECTED_CARDS = {"mot-motion-director": 2, "impl-technical-director": 2,
                  "ux-accessibility": 1, "narr-story-architect": 2,
                  "impl-slide-editor": 1}


def check_persona(path: Path) -> list[str]:
    errs: list[str] = []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return [f"{path}: 최상위가 매핑이 아님"]

    for k in TOP_KEYS:
        if k not in data:
            errs.append(f"최상위 필수 키 누락: {k}")
    if errs:
        return errs

    expert_id = data["id"]
    dir_name = path.parent.name
    if expert_id != dir_name:
        errs.append(f"id({expert_id})와 디렉터리명({dir_name}) 불일치")
    if expert_id not in ROSTER:
        errs.append(f"PLAN §5.1 로스터에 없는 id: {expert_id}")
    else:
        abbr, cat = ROSTER[expert_id]
        if data["abbr"] != abbr:
            errs.append(f"abbr({data['abbr']}) != 로스터({abbr})")
        if data["category"] != cat:
            errs.append(f"category({data['category']}) != 로스터({cat})")
    if not re.fullmatch(r"[A-Z]{2,4}", str(data["abbr"])):
        errs.append(f"abbr 형식 위반: {data['abbr']}")
    if data["category"] not in CATEGORIES:
        errs.append(f"허용 밖 category: {data['category']}")
    if data["id"].split("-", 1)[0] != data["category"]:
        errs.append(f"id 접두어와 category 불일치: {data['id']} / {data['category']}")
    if data["status"] != "active":
        errs.append(f"status가 active가 아님: {data['status']}")

    for k in PERSONA_KEYS:
        v = data["persona"].get(k)
        if not (isinstance(v, str) and v.strip()):
            errs.append(f"persona.{k} 누락 또는 빈 값")

    exp = data["expertise"]
    for k in EXPERTISE_KEYS:
        if k not in exp:
            errs.append(f"expertise.{k} 누락")
    in_scope = exp.get("in_scope") or []
    if not (5 <= len(in_scope) <= 10):
        errs.append(f"in_scope 개수 {len(in_scope)} (요구: 5~10)")
    out_scope = exp.get("out_of_scope") or []
    if not out_scope:
        errs.append("out_of_scope가 비어 있음")
    for item in out_scope:
        if "→" not in str(item):
            errs.append(f"out_of_scope '→ 위임대상' 표기 누락: {item}")

    rt = data["routing"]
    for k in ROUTING_KEYS:
        if not rt.get(k):
            errs.append(f"routing.{k} 누락 또는 빈 값")
    if len(rt.get("example_questions") or []) < 3:
        errs.append(f"example_questions {len(rt.get('example_questions') or [])}개 (요구: 3 이상)")
    if len(rt.get("anti_examples") or []) < 2:
        errs.append(f"anti_examples {len(rt.get('anti_examples') or [])}개 (요구: 2 이상)")
    for p in rt.get("patterns") or []:
        try:
            re.compile(p)
        except re.error as e:
            errs.append(f"컴파일 불가 routing 패턴 {p!r}: {e}")

    rel = data["related_experts"]
    if not isinstance(rel, list) or not rel:
        errs.append("related_experts가 비어 있음")
    else:
        for r in rel:
            for k in ("id", "relation", "when_to_refer"):
                if k not in r:
                    errs.append(f"related_experts 항목 키 누락: {k}")
            if r.get("id") not in ROSTER:
                errs.append(f"related_experts에 로스터 밖 id: {r.get('id')}")

    mt = data["meeting"]
    for k in MEETING_KEYS:
        if not mt.get(k):
            errs.append(f"meeting.{k} 누락 또는 빈 값")

    return errs


def check_card(path: Path, owner_id: str) -> list[str]:
    errs: list[str] = []
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.DOTALL)
    if not m:
        return [f"{path.name}: frontmatter 블록 없음"]
    fm = yaml.safe_load(m.group(1))
    if not isinstance(fm, dict):
        return [f"{path.name}: frontmatter가 매핑이 아님"]
    for k in CARD_KEYS:
        if k not in fm:
            errs.append(f"{path.name}: frontmatter 키 누락: {k}")
    if errs:
        return errs
    abbr = ROSTER[owner_id][0]
    if not re.fullmatch(rf"{abbr}-C-\d{{3}}", str(fm["id"])):
        errs.append(f"{path.name}: 카드 ID 형식 위반({fm['id']}, 기대 {abbr}-C-###)")
    if fm["id"] != path.stem:
        errs.append(f"{path.name}: 카드 ID({fm['id']})와 파일명 불일치")
    eid = fm["expert_id"]
    if not (isinstance(eid, list) and owner_id in eid):
        errs.append(f"{path.name}: expert_id에 {owner_id} 없음: {eid}")
    if not m.group(2).strip():
        errs.append(f"{path.name}: 마크다운 본문이 비어 있음")
    return errs


def main() -> int:
    failures: dict[str, list[str]] = {}
    passed = 0

    for expert_id in sorted(ROSTER):
        ppath = ROOT / expert_id / "persona.yaml"
        if not ppath.exists():
            failures[expert_id] = ["persona.yaml 없음"]
            continue
        errs = check_persona(ppath)

        expected_cards = EXPECTED_CARDS.get(expert_id, 0)
        cards = sorted((ROOT / expert_id / "cards").glob("*.md")) if expected_cards else []
        if expected_cards and len(cards) != expected_cards:
            errs.append(f"카드 수 {len(cards)}장 (기대: {expected_cards}장)")
        for card in cards:
            errs.extend(check_card(card, expert_id))

        if errs:
            failures[expert_id] = errs
        else:
            passed += 1
            n_cards = f" (+카드 {len(cards)}장)" if cards else ""
            print(f"PASS {expert_id}{n_cards}")

    for expert_id, errs in failures.items():
        print(f"FAIL {expert_id}")
        for e in errs:
            print(f"  - {e}")

    total = len(ROSTER)
    print(f"\n결과: {passed}/{total} 통과")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
