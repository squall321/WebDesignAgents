# 심의 산출물(시나리오·조각·회의록)을 읽는 글로 조립하는 문서 조립기 — 영상·PPT와 같은 심의에서 나오는 세 번째 표현
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from wdcore.models.scenario import ScenarioDoc

from .format import module_dir, resolve_modules_root, resolve_tpl_module_id
from .widgets import extract_structured

__all__ = [
    "REF_CATEGORIES",
    "STYLE_BUDGETS",
    "SPOKEN_RULES",
    "SPOKEN_RESIDUE",
    "assemble_document",
    "validate_document",
    "to_written",
]

# ── 참조 범주 (ReportArchive REF_CATEGORIES 관례) ─────────────────────────
# 범주 → (본문 접두어, 앵커 접두어). 그림/표 번호는 문서 전역 1부터 순서대로 매긴다.
REF_CATEGORIES: dict[str, tuple[str, str]] = {
    "figure": ("그림", "fig"),
    "table": ("표", "tbl"),
}

# ── 문체 예산 ────────────────────────────────────────────────────────────
# report 정식 보고서 / brief 2~3쪽 요약본 / memo 1쪽.
# sections: 씬을 몇 개 절로 병합할지(None = 씬당 1절). sent: 문단당 (최소, 최대) 문장 수.
STYLE_BUDGETS: dict[str, dict[str, Any]] = {
    "report": {
        "sections": None, "headings": None, "sent": (3, 6), "paras": 2,
        "figs_per_section": None, "tables_total": None, "table_rows": 12,
        "bullets": 5, "sources": None,
    },
    "brief": {
        "sections": 3, "headings": ("배경과 문제", "해법과 작동 방식", "실증과 결론"),
        "sent": (2, 4), "paras": 2,
        "figs_per_section": 1, "tables_total": 2, "table_rows": 6,
        "bullets": 4, "sources": 12,
    },
    "memo": {
        "sections": 1, "headings": ("요지",), "sent": (2, 3), "paras": 3,
        "figs_per_section": 1, "tables_total": 0, "table_rows": 0,
        "bullets": 3, "sources": 6,
    },
}

# ── 구어체 → 문어체 ──────────────────────────────────────────────────────
# 종성 ㅂ(받침 index 17)을 가진 음절 전체. "합니다/입니다/습니다/받칩니다"가 모두 여기 걸린다.
# "아니다"처럼 정상 문어체는 종성 ㅂ이 없으므로 오검출되지 않는다.
_BIEUP_SYLLABLES = "".join(
    chr(c) for c in range(0xAC00, 0xD7A4) if (c - 0xAC00) % 28 == 17
)
_BIEUP_CLASS = f"[{_BIEUP_SYLLABLES}]"

# 영상 대본에만 있는 구어 표지 — 문서에 남으면 안 된다.
SPOKEN_RESIDUE = re.compile(
    rf"{_BIEUP_CLASS}니다|{_BIEUP_CLASS}니까|십시오|시죠|보시다시피|보시는|하세요|해요|이에요|예요"
)

# (정규식, 치환, 근거). 순서가 곧 적용 순서다 — 좁은 규칙이 먼저다.
SPOKEN_RULES: tuple[tuple[str, str, str], ...] = (
    (r"보시다시피", "그림에서 보듯", "영상 지시(화면 가리키기) → 문서 지시(그림 참조)"),
    (r"보시는 것처럼", "그림에서 보듯", "위와 같음"),
    (r"지금 보시는 ", "이 ", "발표 시점 지시어 제거 — 문서는 시점이 없다"),
    (r"여러분[,]?\s*", "", "청중 호칭은 문서에 수신자가 없어 삭제"),
    (r"([가-힣]+)하겠습니다", r"\1한다", "의지형 종결 → 평서형 (발표자 선언이 사라진다)"),
    (r"([가-힣]+)드리겠습니다", r"\1한다", "겸양 의지형 → 평서형"),
    (r"([가-힣]+?)으십시오", r"\1는 것을 권한다", "청유 명령 → 권고 — 문서는 청중에게 명령하지 않는다"),
    (r"([가-힣]+?)십시오", r"\1는 것을 권한다", "위와 같음"),
    (r"습니까", "는가", "합쇼체 의문 → 평서체 의문"),
    (r"습니다", "다", "합쇼체 → 해라체(한다체) — 보고서 기본 문체"),
    (r"(섞|보|놓|쌓|쓰|덮|묶|깎|먹|죽|높|붙|모|줄|늘|속|기울)입니다", r"\1인다",
     "‘이’로 끝나는 피동·사동 어간(뒤섞이다·보이다…)은 계사가 아니다 — 일반규칙(ㅂ→ㄴ)을 적용"),
    (r"입니까", "인가", "계사 의문 특례 (‘인다’가 아니다)"),
    (r"입니다", "이다", "계사 특례 — 종성 ㅂ→ㄴ 일반규칙의 예외"),
)
_SPOKEN_COMPILED = tuple((re.compile(p), r) for p, r, _ in SPOKEN_RULES)

# 문장 종결로 인정하는 어미 (이미 문어체 절)
_CLAUSE_TAIL = re.compile(r"(다|까|는가|인가|자|라)$")
# 연결어미로 끝난 조각 — 뒤 조각과 이어야 문장이 된다
_CONNECTIVE = re.compile(r"(고|며|면서|지만|거나|어서|아서|하여|되어|되고|이며|이고)$")
# 대시로 시작하는 후치 수식 — 앞 문장에 붙인다
_APPOSITIVE = re.compile(r"^\s*[—–\-]")
# 의문형 종결 — 마침표가 아니라 물음표로 닫는다
_INTERROGATIVE = re.compile(r"(까|는가|인가)$")
# 명사형 어미 → 평서형. 명사(플랫폼·포함·처음)를 잘라먹지 않도록 닫힌 목록만 쓴다.
_NOMINAL_TAILS = {"없음": "없다", "있음": "있다", "됨": "된다"}


def _bieup_to_nieun(ch: str) -> str:
    """종성 ㅂ(17) → ㄴ(4). 합→한, 됩→된, 칩→친."""
    return chr(ord(ch) - 13)


def to_written(text: str) -> str:
    """영상 내레이션(합쇼체)을 보고서 문체(한다체)로 바꾼다.

    치환 근거는 SPOKEN_RULES 에 규칙별로 적혀 있다. 표에 없는 합쇼체는
    마지막 일반 규칙(종성 ㅂ + 니다 → 종성 ㄴ + 다)이 받는다.
    """
    if not text:
        return ""
    out = text
    for pattern, repl in _SPOKEN_COMPILED:
        out = pattern.sub(repl, out)
    out = re.sub(f"({_BIEUP_CLASS})니다", lambda m: _bieup_to_nieun(m.group(1)) + "다", out)
    out = re.sub(f"({_BIEUP_CLASS})니까", lambda m: _bieup_to_nieun(m.group(1)) + "가", out)
    return re.sub(r"\s{2,}", " ", out).strip()


def _as_sentence(text: str) -> str:
    """조각 문구를 문장으로 닫는다. 명사구는 계사(이다/다)를, 명사형은 평서형을 붙인다."""
    body = to_written(text).strip().rstrip(" .!?…")
    if not body:
        return ""
    if _CLAUSE_TAIL.search(body):
        return body + ("?" if _INTERROGATIVE.search(body) else ".")
    # "… 남았다 — 지금까지는" 처럼 대시 뒤 후치 수식이 붙은 꼴은 앞 절이 종결을 결정한다
    head, sep, _tail = body.rpartition(" — ")
    if sep and _CLAUSE_TAIL.search(head):
        return body + "."
    for nominal, plain in _NOMINAL_TAILS.items():  # "…알 수 없음" → "…알 수 없다"
        if body.endswith(nominal):
            return body[: -len(nominal)] + plain + "."
    last = body[-1]
    has_batchim = "가" <= last <= "힣" and (ord(last) - 0xAC00) % 28 != 0
    return body + ("이다." if has_batchim else "다.")


def _compose(readables: list[str]) -> list[str]:
    """읽는 조각들을 문장 단위로 합친다 — 연결어미로 끊긴 조각과 후치 수식을 붙인다."""
    out: list[str] = []
    for raw in readables:
        text = raw.strip()
        if not text:
            continue
        if out and _APPOSITIVE.match(raw):
            out[-1] = f"{out[-1]} {text}"
            continue
        if out and _CONNECTIVE.search(out[-1].rstrip(" .")):
            out[-1] = f"{out[-1]} {text}"
            continue
        out.append(text)
    return out


_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list[str]:
    """내레이션을 문장 단위로 쪼개고 문어체로 바꾼다."""
    out: list[str] = []
    for raw in _SENT_SPLIT.split(text or ""):
        s = to_written(raw).strip()
        if not s:
            continue
        if not s.endswith((".", "!", "?")):
            s += "."
        out.append(s)
    return out


# ── x-read 수집 ─────────────────────────────────────────────────────────


def _join_item(values: list[str]) -> str:
    """항목 하나: 첫 값이 이름, 나머지가 설명."""
    if len(values) == 1:
        return values[0]
    return f"{values[0]} — {' · '.join(values[1:])}"


def _render_value(schema: dict, value: Any) -> str:
    """x-read 로 표시된 노드 하나를 읽는 문구로 편다."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        props = schema.get("properties") or {}
        order = list(props) or list(value)
        return "".join(str(value[k]) for k in order if isinstance(value.get(k), str))
    if isinstance(value, list):
        items = schema.get("items") or {}
        props = list((items.get("properties") or {}))
        parts: list[str] = []
        for it in value:
            if isinstance(it, str) and it.strip():
                parts.append(it.strip())
            elif isinstance(it, dict):
                vals = [str(it[k]).strip() for k in props if isinstance(it.get(k), str) and it[k].strip()]
                if vals:
                    parts.append(_join_item(vals))
        return "; ".join(parts)
    return ""


def _readables(schema: dict, data: dict) -> list[tuple[str, str]]:
    """스키마의 x-read 표시를 따라 씬 데이터에서 (경로, 읽는 문구)를 뽑는다."""
    out: list[tuple[str, str]] = []

    def walk(sch: dict, val: dict, path: str) -> None:
        for key, sub in (sch.get("properties") or {}).items():
            if not isinstance(sub, dict) or key not in val:
                continue
            v = val[key]
            if v in (None, "", [], {}):
                continue
            p = f"{path}.{key}" if path else key
            if sub.get("x-read") is True:
                text = _render_value(sub, v)
                if text:
                    out.append((p, text))
                continue  # 표시된 노드 아래는 통째로 읽었다 — 중복 방지
            if isinstance(v, dict):
                walk(sub, v, p)
            elif isinstance(v, list) and isinstance(sub.get("items"), dict):
                items = sub["items"]
                leaves = [
                    n for n, s2 in (items.get("properties") or {}).items()
                    if isinstance(s2, dict) and s2.get("x-read") is True
                ]
                if not leaves:
                    continue
                parts = []
                for it in v:
                    if not isinstance(it, dict):
                        continue
                    vals = [str(it[n]).strip() for n in leaves if str(it.get(n) or "").strip()]
                    if vals:
                        parts.append(_join_item(vals))
                if parts:
                    out.append((f"{p}[]", "; ".join(parts)))

    walk(schema, data, "")
    return out


# 화면에서만 뜻이 있는 표지 라벨 — 절 제목과 역할이 겹쳐 본문 문장으로 쓰지 않는다.
_LABEL_PATHS = {"kicker"}


def _scene_schema(tpl: str, modules_root: Path) -> dict:
    """씬 tpl → schema.json. 모듈을 못 찾으면 빈 스키마 (본문은 내레이션만으로 간다)."""
    try:
        module_id = resolve_tpl_module_id(tpl, modules_root=modules_root)
        path = module_dir(module_id, modules_root) / "schema.json"
        return json.loads(path.read_text("utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


# ── 조각 매칭 (본문 ↔ 출처 추적) ─────────────────────────────────────────

_NON_WORD = re.compile(r"[^0-9A-Za-z가-힣]")


def _grams(text: str) -> set[str]:
    """한글 형태소 분석기 없이 쓰는 문자 바이그램 — 어미 변화를 넘어 겹침을 잰다."""
    s = _NON_WORD.sub("", (text or "").lower())
    if len(s) < 2:
        return {s} if s else set()
    return {s[i:i + 2] for i in range(len(s) - 1)}


# 절-조각 매칭 하한. 이 아래는 우연한 어휘 겹침이라 출처로 달지 않는다.
_SOURCE_MIN = 0.10


def _overlap(a: set[str], b: set[str]) -> float:
    """집합 코사인 — min() 정규화는 짧은 쪽(오프닝 같은 짧은 절)에 몰리는 쏠림을 만든다."""
    if not a or not b:
        return 0.0
    return len(a & b) / ((len(a) * len(b)) ** 0.5)


# ── 조각 → 표 ───────────────────────────────────────────────────────────


def _block_index(norm: dict) -> dict[tuple[str, str], dict]:
    """(page.name, block.id) → block. 구조 payload 가 없는 옛 조각의 보정 경로."""
    idx: dict[tuple[str, str], dict] = {}
    for page in norm.get("pages") or []:
        name = str(page.get("name") or "")
        for block in page.get("blocks") or []:
            bid = str(block.get("id") or "")
            if bid:
                idx[(name, bid)] = block
    return idx


def _payload_table(payload: dict, caption_fallback: str) -> dict | None:
    """구조 payload(kind=table|pairs) → {caption, columns, rows}."""
    kind = payload.get("kind")
    if kind == "table":
        cols = payload.get("columns") or []
        labels = [str(c.get("label") or c.get("key") or "") for c in cols]
        keys = [c.get("key") for c in cols]
        rows = [[str(r.get(k, "") or "") for k in keys] for r in payload.get("rows") or []]
    elif kind == "pairs":
        labels = ["항목", "내용"]
        rows = [
            [str(p.get("label") or p.get("key") or ""), str(p.get("value") or "")]
            for p in payload.get("pairs") or []
        ]
    else:
        return None
    if not labels or not rows:
        return None
    return {
        "caption": str(payload.get("caption") or caption_fallback or "표"),
        "columns": labels,
        "rows": rows,
    }


def _collect_tables(fragments: list[dict], norm: dict) -> list[dict]:
    """조각의 structured(없으면 원문 블록에서 재추출)에서 표를 모은다."""
    blocks = _block_index(norm)
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for frag in fragments:
        src = frag.get("source") or {}
        key = (str(src.get("page") or ""), str(src.get("block_id") or ""))
        if key in seen:
            continue
        payload = frag.get("structured")
        if not isinstance(payload, dict):
            block = blocks.get(key)
            payload = extract_structured(block) if block else None
        if not isinstance(payload, dict):
            continue
        table = _payload_table(payload, frag.get("text", ""))
        if table is None:
            continue
        seen.add(key)
        table["source"] = {"ref": frag.get("frag_id", ""), "page": key[0], "block_id": key[1]}
        out.append(table)
    return out


# ── 회의록 파싱 ─────────────────────────────────────────────────────────

_TURN_RE = re.compile(r"\(턴 #(\d+)\)\s*$")


def _md_sections(md: str) -> dict[str, list[str]]:
    """'## 3. 결론' 같은 절 제목 → 본문 줄 목록."""
    out: dict[str, list[str]] = {}
    title = ""
    for line in md.splitlines():
        if line.startswith("## "):
            title = line[3:].strip()
            out[title] = []
        elif title:
            out[title].append(line)
    return out


def _find_section(sections: dict[str, list[str]], keyword: str) -> list[str]:
    for title, lines in sections.items():
        if keyword in title:
            return lines
    return []


def _table_rows(lines: list[str]) -> list[list[str]]:
    """마크다운 표 → 셀 목록(헤더·구분선 제외)."""
    rows: list[list[str]] = []
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if all(set(c) <= {"-", ":"} and c for c in cells):
            continue
        rows.append(cells)
    return rows[1:] if rows else []


def _bullets(lines: list[str]) -> list[dict]:
    out: list[dict] = []
    for line in lines:
        s = line.strip()
        if not s.startswith("- "):
            continue
        text = s[2:].strip()
        if not text or text in ("(없음)", "(기록된 결정 없음)"):
            continue
        m = _TURN_RE.search(text)
        turn = int(m.group(1)) if m else None
        out.append({"text": _TURN_RE.sub("", text).strip(), "turn": turn})
    return out


def _parse_minutes(md: str) -> dict:
    """minutes.md → 결정·액션아이템·미해결 쟁점·라운드 요약 구조체."""
    sections = _md_sections(md)
    participants = [
        {"id": r[0], "name": r[1] if len(r) > 1 else r[0]}
        for r in _table_rows(_find_section(sections, "참가자"))
        if r and r[0] and r[0] != "-"
    ]
    actions = []
    for r in _table_rows(_find_section(sections, "액션아이템")):
        if len(r) < 4 or r[0] == "-":
            continue
        actions.append({"no": r[0], "text": r[1], "owner": r[2], "turn": r[3].lstrip("#")})

    rounds: list[dict] = []
    label = ""
    for line in _find_section(sections, "라운드별"):
        s = line.strip()
        if s.startswith("### "):
            head = s[4:].strip().split(" ", 1)
            label = head[0]
            rounds.append({
                "round": label,
                "label": head[1] if len(head) > 1 else "",
                "turns": 0,
                "speakers": [],
            })
        elif rounds and s.startswith("|"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) < 2 or cells[0] in ("턴",) or all(set(c) <= {"-", ":"} for c in cells):
                continue
            rounds[-1]["turns"] += 1
            if cells[1] not in rounds[-1]["speakers"]:
                rounds[-1]["speakers"].append(cells[1])

    meeting_id = ""
    m = re.search(r"회의 ID: ([0-9a-f]+)", md)
    if m:
        meeting_id = m.group(1)
    topic = ""
    for line in md.splitlines():
        if line.startswith("# "):
            topic = line[2:].strip()
            break

    return {
        "meeting_id": meeting_id,
        "topic": topic,
        "participants": participants,
        "decisions": _bullets(_find_section(sections, "결론")),
        "action_items": actions,
        "open_issues": _bullets(_find_section(sections, "미해결")),
        "rounds": rounds,
    }


def _find_meeting_dir(root: Path, meeting_id: str | None) -> Path | None:
    """data/meetings/ 에서 meta.json 의 회의 ID 로 심의 폴더를 찾는다."""
    if not meeting_id or not root.is_dir():
        return None
    short = meeting_id.split("-")[0]
    for path in sorted(root.iterdir()):
        meta = path / "meta.json"
        if not meta.is_file():
            continue
        try:
            data = json.loads(meta.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(data.get("id", "")).startswith(short):
            return path
    return None


# ── 조립 ────────────────────────────────────────────────────────────────


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text("utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"{path} 를 읽을 수 없다 — {e}") from e


def _still_filename(idx: int, name: str, t: float) -> str:
    """스틸 파일 이름 규약 — 캡처 드라이버(capture_stills.py)와 같은 형식."""
    return f"{idx:02d}_{name}_{t:.1f}s.png"


_STILL_TIME = re.compile(r"_(\d+(?:\.\d+)?)s\.png$")


def _find_still(dirs: list[Path], filename: str, prefix: str, t: float) -> str | None:
    """스틸 파일 찾기 — 이름이 정확히 맞지 않으면 같은 씬에서 시각이 가장 가까운 것."""
    for d in dirs:
        if not d.is_dir():
            continue
        exact = d / filename
        if exact.is_file():
            return str(exact)
        cands = sorted(d.glob(f"{prefix}*.png"))
        if cands:
            def gap(p: Path) -> float:
                m = _STILL_TIME.search(p.name)
                return abs(float(m.group(1)) - t) if m else 1e9
            return str(min(cands, key=gap))
    return None


def assemble_document(
    run_dir: str | Path,
    *,
    build_dir: str | Path | None = None,
    meeting_dir: str | Path | None = None,
    style: str = "report",
) -> dict:
    """심의 산출물(run_dir)을 읽는 문서 트리(DocumentDoc)로 조립한다.

    run_dir      — data/pipeline/{run_id}/ (scenario.json 필수, fragments.json·report.norm.json 선택)
    build_dir    — 빌드 패키지 경로. 씬 스틸(PNG)을 여기서 찾는다. 미지정 시 data/build/{run_id}.
    meeting_dir  — 심의 폴더(minutes.md·meta.json). 미지정 시 meta.meeting_id 로 data/meetings/ 에서 찾는다.
    style        — "report"(정식) | "brief"(2~3쪽) | "memo"(1쪽). 절 병합·본문 길이 예산이 달라진다.
    """
    if style not in STYLE_BUDGETS:
        raise ValueError(f"style 은 {sorted(STYLE_BUDGETS)} 중 하나여야 한다 — 받은 값 {style!r}")
    run = Path(run_dir)
    if not run.is_dir():
        raise ValueError(f"run_dir 이 디렉터리가 아니다: {run}")

    raw = _load_json(run / "scenario.json")
    if not isinstance(raw, dict):
        raise ValueError(f"{run}/scenario.json 이 없다 — 심의 산출 시나리오가 있어야 문서를 만든다")
    doc = ScenarioDoc.model_validate(raw)
    if not doc.scenes:
        raise ValueError(f"{run}/scenario.json 에 씬이 없다 — 빈 시나리오로는 문서를 만들 수 없다")

    fragments = _load_json(run / "fragments.json") or []
    if not isinstance(fragments, list):
        raise ValueError(f"{run}/fragments.json 은 조각 목록이어야 한다")
    norm = _load_json(run / "report.norm.json") or {}

    budget = STYLE_BUDGETS[style]
    modules_root = resolve_modules_root()
    data_root = run.parent.parent  # data/pipeline/{run_id} → data/
    build = Path(build_dir) if build_dir is not None else data_root / "build" / run.name
    still_dirs = [run / "stills", build / "stills", build]

    # ── 1. 씬 → 절 후보 ──────────────────────────────────────────────
    units: list[dict] = []
    cursor = 0.0
    for i, scene in enumerate(doc.scenes, start=1):
        schema = _scene_schema(scene.tpl, modules_root)
        key = scene.data_ref.split(".", 1)[1] if scene.data_ref.startswith("content.") else ""
        data = doc.content.get(key) or {}
        reads = _readables(schema, data) if data else []
        heading = ""
        rest: list[str] = []
        for path, text in reads:
            if path == "title" and not heading:
                heading = to_written(text).rstrip(" .")
                continue
            if path in _LABEL_PATHS:  # 절 표지 라벨 — 제목과 겹쳐 본문에 넣지 않는다
                continue
            rest.append(text)
        heading = heading or scene.name
        rest = _compose(rest)

        figures = []
        for still in scene.stills:
            t = round(cursor + float(still), 3)
            fname = _still_filename(i, scene.name, t)
            figures.append({
                "src": f"stills/{fname}",
                "caption": f"{heading} (재생 {t:.1f}초)",
                "scene": scene.name,
                "t": t,
                "source_path": _find_still(still_dirs, fname, f"{i:02d}_{scene.name}_", t),
            })
        cursor += float(scene.dur)

        units.append({
            "scene": scene.name,
            "heading": heading,
            "narration": scene.narration,
            "readables": rest,
            "figures": figures,
            "grams": _grams(" ".join([heading, scene.narration, *rest])),
        })

    # ── 2. 조각 매칭 — 절 ↔ 출처 ─────────────────────────────────────
    frag_grams = [(f, _grams(f.get("text", ""))) for f in fragments if f.get("text")]
    for unit in units:
        scored = sorted(
            ((_overlap(unit["grams"], g), f) for f, g in frag_grams),
            key=lambda x: (-x[0], x[1].get("frag_id", "")),
        )
        unit["sources"] = [f for s, f in scored[:3] if s >= _SOURCE_MIN]

    # ── 3. 표 배치 ───────────────────────────────────────────────────
    # 1순위는 원문 쪽(page) 일치 — 그 절이 인용한 조각과 같은 쪽에서 온 표를 싣는다.
    # 어느 절도 그 쪽을 인용하지 않았으면 어휘 겹침으로 정한다.
    tables = _collect_tables(fragments, norm)
    for table in tables:
        page = table["source"]["page"]
        text = " ".join([table["caption"], *table["columns"]] + [c for r in table["rows"][:3] for c in r])
        g = _grams(text)

        def rank(i: int, page: str = page, g: set[str] = g) -> tuple[int, float]:
            unit = units[i]
            hits = sum(
                1 for f in unit.get("sources", [])
                if (f.get("source") or {}).get("page") == page
            )
            return (hits, _overlap(unit["grams"], g))

        units[max(range(len(units)), key=rank)].setdefault("tables", []).append(table)

    # ── 4. 절 병합 ───────────────────────────────────────────────────
    groups = _merge_units(units, budget)

    # ── 5. 본문·번호·참조 ────────────────────────────────────────────
    sections: list[dict] = []
    fig_no = tbl_no = 0
    for n, group in enumerate(groups, start=1):
        paras: list[str] = []
        notes: list[str] = []
        seen_src: set[str] = set()
        picked = _pick(group["units"], budget["paras"])
        allow = max(1, budget["paras"] // len(picked))
        for unit in picked:
            paras.extend(_paragraphs(unit, budget, allow))
            for frag in unit.get("sources", []):
                ref = frag.get("frag_id", "")
                if ref and ref not in seen_src:
                    seen_src.add(ref)
                    src = frag.get("source") or {}
                    notes.append(f"[{ref}] {src.get('page', '')} · {src.get('block_id', '')}")
        paras = paras[: budget["paras"]] or [_as_sentence(group["heading"])]

        figures = []
        per = budget["figs_per_section"]
        for unit in group["units"]:
            take = unit["figures"] if per is None else unit["figures"][:per]
            figures.extend(take)
            if per is not None and len(figures) >= per:
                figures = figures[:per]
                break
        sec_tables = [t for unit in group["units"] for t in unit.get("tables", [])]

        refs: list[dict] = []
        for fig in figures:
            fig_no += 1
            word, anchor = REF_CATEGORIES["figure"]
            fig.update({"no": fig_no, "ref": f"{word} {fig_no}", "anchor": f"{anchor}-{fig_no}"})
            slot = min(len(refs), len(paras) - 1)
            paras[slot] = paras[slot].rstrip() + f" ({fig['ref']})"
            refs.append({"ref": fig["ref"], "anchor": fig["anchor"], "kind": "figure", "paragraph": slot})
        placed: list[dict] = []
        for table in sec_tables:
            if budget["tables_total"] is not None and tbl_no >= budget["tables_total"]:
                break
            tbl_no += 1
            word, anchor = REF_CATEGORIES["table"]
            total = len(table["rows"])
            limit = budget["table_rows"]
            table.update({
                "no": tbl_no, "ref": f"{word} {tbl_no}", "anchor": f"{anchor}-{tbl_no}",
                "rows_total": total, "rows": table["rows"][:limit],
            })
            slot = min(len(refs), len(paras) - 1)
            paras[slot] = paras[slot].rstrip() + f" ({table['ref']})"
            refs.append({"ref": table["ref"], "anchor": table["anchor"], "kind": "table", "paragraph": slot})
            src = table.pop("source", {})
            ref_id = src.get("ref", "")
            if ref_id and ref_id not in seen_src:
                seen_src.add(ref_id)
                notes.append(f"[{ref_id}] {src.get('page', '')} · {src.get('block_id', '')}")
            placed.append(table)

        sections.append({
            "no": n,
            "heading": group["heading"],
            "anchor": f"sec-{n}",
            "body": paras,
            "figures": figures,
            "tables": placed,
            "figure_ref": refs,
            "notes": notes,
        })

    # ── 6. 부록 ──────────────────────────────────────────────────────
    minutes_dir = Path(meeting_dir) if meeting_dir is not None else _find_meeting_dir(
        data_root / "meetings", doc.meta.meeting_id
    )
    delib = {
        "meeting_id": doc.meta.meeting_id or "",
        "topic": "", "participants": [], "decisions": [],
        "action_items": [], "open_issues": [], "rounds": [],
        "minutes_path": str(minutes_dir / "minutes.md") if minutes_dir else "",
    }
    if minutes_dir and (minutes_dir / "minutes.md").is_file():
        parsed = _parse_minutes((minutes_dir / "minutes.md").read_text("utf-8"))
        parsed["meeting_id"] = doc.meta.meeting_id or parsed["meeting_id"]
        parsed["minutes_path"] = delib["minutes_path"]
        delib = parsed

    cited = {ref for sec in sections for ref in _refs_in_notes(sec["notes"])}
    by_id = {f.get("frag_id"): f for f in fragments}
    sources = []
    for ref in sorted(cited):
        frag = by_id.get(ref) or {}
        src = frag.get("source") or {}
        sources.append({
            "ref": ref,
            "page": src.get("page", ""),
            "block_id": src.get("block_id", ""),
            "text": frag.get("text", ""),
        })
    if budget["sources"] is not None and len(sources) > budget["sources"]:
        sources = sources[: budget["sources"]]
        kept = {s["ref"] for s in sources}
        for sec in sections:  # 각주는 언제나 부록 출처의 부분집합이어야 한다
            sec["notes"] = [n for n in sec["notes"] if set(_refs_in_notes([n])) <= kept]

    # ── 7. 머리말 ────────────────────────────────────────────────────
    title = units[0]["heading"] if units else doc.meta.core_message
    return {
        "meta": {
            "title": title,
            "core_message": to_written(doc.meta.core_message),
            "date": str(norm.get("report_date") or ""),
            "source_report": str(norm.get("title") or ""),
            "run_id": run.name,
            "format": doc.format,
            "style": style,
            "audience": doc.meta.audience,
        },
        "summary": _summary(doc, units, budget),
        "sections": sections,
        "appendix": {"deliberation": delib, "sources": sources},
        "toc": [{"no": s["no"], "heading": s["heading"], "anchor": s["anchor"]} for s in sections],
    }


_REF_IN_NOTE = re.compile(r"^\[([^\]]+)\]")


def _refs_in_notes(notes: list[str]) -> list[str]:
    out = []
    for note in notes:
        m = _REF_IN_NOTE.match(note)
        if m:
            out.append(m.group(1))
    return out


def _merge_units(units: list[dict], budget: dict) -> list[dict]:
    """씬 절을 문체 예산의 절 수로 병합한다 (연속 구간 균등 분할)."""
    k = budget["sections"]
    if k is None or k >= len(units):
        return [{"heading": u["heading"], "units": [u]} for u in units]
    headings = budget["headings"] or ()
    groups: list[dict] = []
    n = len(units)
    for i in range(k):
        lo = i * n // k
        hi = (i + 1) * n // k
        chunk = units[lo:hi]
        if not chunk:
            continue
        heading = headings[i] if i < len(headings) else chunk[0]["heading"]
        groups.append({"heading": heading, "units": chunk})
    return groups


def _pick(items: list[dict], k: int) -> list[dict]:
    """예산이 모자라면 앞에서 자르지 않고 균등 간격으로 고른다 (첫·끝 절을 살린다)."""
    if k >= len(items):
        return items
    if k == 1:
        return [items[0]]
    step = (len(items) - 1) / (k - 1)
    return [items[round(i * step)] for i in range(k)]


def _paragraphs(unit: dict, budget: dict, allow: int = 2) -> list[str]:
    """씬 1개 → 문단 목록. 내레이션을 뼈대로 쓰고 x-read 문구로 호흡을 채운다."""
    lo, hi = budget["sent"]
    sents = _sentences(unit["narration"])
    seen = {_NON_WORD.sub("", s) for s in sents}
    heading_key = _NON_WORD.sub("", unit["heading"])
    for text in unit["readables"]:
        s = _as_sentence(text)
        key = _NON_WORD.sub("", s)
        if not s or key == heading_key or any(key in k or k in key for k in seen if k):
            continue
        seen.add(key)
        sents.append(s)
    if not sents:
        return []
    first, rest = sents[:hi], sents[hi:]
    if len(first) < lo and rest:  # 최소 호흡을 못 채우면 다음 문장을 끌어온다
        need = lo - len(first)
        first, rest = first + rest[:need], rest[need:]
    paras = [" ".join(first)]
    if rest and allow > 1:
        paras.append(" ".join(rest[:hi]))
    return paras


def _summary(doc: ScenarioDoc, units: list[dict], budget: dict) -> dict:
    """핵심 메시지 한 문단 + 절 제목에서 뽑은 요지 3~5줄."""
    lead_parts = [_as_sentence(doc.meta.core_message)]
    if len(units) > 1:  # 도입 다음 절의 첫 문장이 문제 제기, 마지막 절의 끝 문장이 요청이다
        lead_parts.extend(_sentences(units[1]["narration"])[:1])
        lead_parts.extend(_sentences(units[-1]["narration"])[-1:])
    elif units:
        lead_parts.extend(_sentences(units[0]["narration"])[:2])
    if doc.meta.audience:
        lead_parts.append(_as_sentence(f"이 문서는 {doc.meta.audience}을 수신자로 한다"))
    seen: set[str] = set()
    lead: list[str] = []
    for s in lead_parts:
        key = _NON_WORD.sub("", s)
        if key and key not in seen:
            seen.add(key)
            lead.append(s)

    middle = [u["heading"] for u in units[1:-1]] or [u["heading"] for u in units]
    bullets = [_as_sentence(h).rstrip(".") for h in middle][: budget["bullets"]]
    if len(bullets) < 3:
        extra = [_as_sentence(u["heading"]).rstrip(".") for u in units]
        for b in extra:
            if b not in bullets and len(bullets) < budget["bullets"]:
                bullets.append(b)
    return {"lead": " ".join(lead), "bullets": bullets}


# ── 검증 ────────────────────────────────────────────────────────────────

_REF_TOKEN = re.compile(r"\((그림|표) (\d+)\)")


def validate_document(doc: dict) -> list[str]:
    """문서 트리 검증 — 오류 문자열 목록(빈 리스트 = 통과)."""
    errors: list[str] = []
    meta = doc.get("meta") or {}
    for key in ("title", "core_message", "run_id"):
        if not str(meta.get(key) or "").strip():
            errors.append(f"meta.{key} 가 비었다")

    summary = doc.get("summary") or {}
    if not str(summary.get("lead") or "").strip():
        errors.append("summary.lead 가 비었다 — 요약 문단이 없다")
    bullets = summary.get("bullets") or []
    if not bullets:
        errors.append("summary.bullets 가 비었다")
    elif len(bullets) > 5:
        errors.append(f"summary.bullets 가 {len(bullets)}개 — 5개를 넘을 수 없다")

    sections = doc.get("sections") or []
    if not sections:
        errors.append("sections 가 비었다 — 본문 없는 문서는 만들 수 없다")

    seen_no: set[int] = set()
    fig_nos: dict[int, str] = {}
    tbl_nos: dict[int, str] = {}
    declared: set[str] = set()
    referenced: set[str] = set()
    for sec in sections:
        no = sec.get("no")
        if no in seen_no:
            errors.append(f"절 번호 중복: {no}")
        seen_no.add(no)
        body = [p for p in (sec.get("body") or []) if str(p).strip()]
        if not body:
            errors.append(f"절 {no}({sec.get('heading')}) 의 본문이 비었다")
        if not str(sec.get("heading") or "").strip():
            errors.append(f"절 {no} 의 제목이 비었다")
        for para in body:
            if SPOKEN_RESIDUE.search(para):
                errors.append(f"절 {no} 본문에 구어체가 남았다: {SPOKEN_RESIDUE.search(para).group(0)}")
            for word, num in _REF_TOKEN.findall(para):
                referenced.add(f"{word} {num}")
        for fig in sec.get("figures") or []:
            n = fig.get("no")
            if n in fig_nos:
                errors.append(f"그림 번호 중복: {n}")
            fig_nos[n] = sec.get("heading", "")
            declared.add(fig.get("ref", ""))
            if not str(fig.get("src") or "").strip():
                errors.append(f"그림 {n} 의 src 가 비었다")
        for tbl in sec.get("tables") or []:
            n = tbl.get("no")
            if n in tbl_nos:
                errors.append(f"표 번호 중복: {n}")
            tbl_nos[n] = sec.get("heading", "")
            declared.add(tbl.get("ref", ""))
            if not (tbl.get("columns") and tbl.get("rows")):
                errors.append(f"표 {n} 에 열 또는 행이 없다")

    for ref in sorted(referenced - declared):
        errors.append(f"본문이 참조한 {ref} 가 문서에 없다")
    for ref in sorted(declared - referenced):
        if ref:
            errors.append(f"{ref} 가 본문 어디에서도 참조되지 않는다")

    toc = doc.get("toc") or []
    if len(toc) != len(sections):
        errors.append(f"toc 항목 수({len(toc)})가 절 수({len(sections)})와 다르다")

    delib = (doc.get("appendix") or {}).get("deliberation") or {}
    if "open_issues" not in delib:
        errors.append("부록에 미해결 쟁점 항목이 없다 — 합의 연출 방지 원칙 위반")
    return errors
