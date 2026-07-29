# 문서형 템플릿 5종(tpl.doc-cover/toc/section/body/summary)의 스키마·픽스처·module.yaml·registry·밀도 계약 검증
import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
DOC_FILE = ROOT / "web" / "templates" / "omx-templates-doc.jsx"
ORIGIN = "창작 모드 문서형 2026-07-29"
FORMATS = ["deck-doc-16x9", "deck-4x3", "print-a4"]
STAGES = {
    "deck-doc-16x9": {"w": 1920, "h": 1080},
    "deck-4x3": {"w": 1440, "h": 1080},
    "print-a4": {"w": 1240, "h": 1754},
}
GOLDEN_STAGE = STAGES["deck-doc-16x9"]

# 디렉터리 → 템플릿 id (가로 tpl.* 와 같은 이름공간이지만 doc- 접두로 갈린다)
DOC = {
    "doc-cover": "tpl.doc-cover",
    "doc-toc": "tpl.doc-toc",
    "doc-section": "tpl.doc-section",
    "doc-body": "tpl.doc-body",
    "doc-summary": "tpl.doc-summary",
}
FIXTURES = ["min", "typical", "max"]
EXTRA_FIXTURES = {"doc-body": ["chart", "image"]}  # 근거 슬롯 3종을 전부 실렌더하기 위한 추가 픽스처
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
CAPTION_CPS = 9.0  # wdqa QAConfig.caption_cps — 문서형은 낭독이 아니라 자막/훑기 속도 기준
# 밀도 비교 기준 — 영상 가로 1차 7종
VIDEO_7 = ["opening", "problem", "concept", "process", "differentiator", "proof", "closing"]
OTHER_TEMPLATE_FILES = [
    "omx-templates.jsx", "omx-templates-ext.jsx", "omx-templates-data.jsx",
    "omx-templates-vertical.jsx", "omx-metaphors.jsx",
]


def load_schema(name: str) -> dict:
    return json.loads((TPL_DIR / name / "schema.json").read_text(encoding="utf-8"))


def load_fixture(name: str, fixture: str) -> dict:
    return json.loads((TPL_DIR / name / "fixtures" / f"{fixture}.json").read_text(encoding="utf-8"))


def load_module(name: str) -> dict:
    return yaml.safe_load((TPL_DIR / name / "module.yaml").read_text(encoding="utf-8"))


def fixtures_of(name: str) -> list[str]:
    return FIXTURES + EXTRA_FIXTURES.get(name, [])


def walk_has_x_read(node) -> bool:
    if isinstance(node, dict):
        if node.get("x-read") is True:
            return True
        return any(walk_has_x_read(v) for v in node.values())
    if isinstance(node, list):
        return any(walk_has_x_read(v) for v in node)
    return False


def walk_strings_have_maxlength(node, path="") -> list:
    """문자열 타입 선언 중 maxLength 가 빠진 경로 목록."""
    missing = []
    if isinstance(node, dict):
        if node.get("type") == "string" and "maxLength" not in node:
            missing.append(path)
        for k, v in node.items():
            if k in ("enum", "const"):
                continue
            missing += walk_strings_have_maxlength(v, f"{path}/{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            missing += walk_strings_have_maxlength(v, f"{path}/{i}")
    return missing


def capacity(schema) -> int:
    """스키마가 허용하는 최악 문자 수용량 — 문자열 maxLength 합, 배열은 maxItems 배."""
    if not isinstance(schema, dict):
        return 0
    t = schema.get("type")
    if t == "string":
        return int(schema.get("maxLength", 0))
    if t == "object":
        return sum(capacity(v) for v in (schema.get("properties") or {}).values())
    if t == "array":
        items = schema.get("items")
        return capacity(items) * int(schema.get("maxItems", 1)) if isinstance(items, dict) else 0
    return 0


def nonspace(node) -> int:
    if isinstance(node, str):
        return len(re.sub(r"\s+", "", node))
    if isinstance(node, dict):
        return sum(nonspace(v) for v in node.values())
    if isinstance(node, list):
        return sum(nonspace(v) for v in node)
    return 0


def test_doc_modules_present():
    for name in DOC:
        assert (TPL_DIR / name).is_dir(), f"{name} 모듈 디렉터리가 없다"
    assert DOC_FILE.exists()


@pytest.mark.parametrize("name", DOC)
def test_schema_is_valid_jsonschema(name):
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema.get("type") == "object"
    assert schema["$id"].startswith(f"wda:{DOC[name]}/")
    assert schema.get("additionalProperties") is False


@pytest.mark.parametrize("name", DOC)
def test_schema_has_x_read_and_maxlength(name):
    schema = load_schema(name)
    assert walk_has_x_read(schema), f"{name}: x-read 낭독 필드가 하나도 없다"
    missing = walk_strings_have_maxlength(schema)
    assert not missing, f"{name}: maxLength 누락 문자열 선언 — {missing}"


@pytest.mark.parametrize("name", DOC)
def test_schema_documents_three_stage_derivation(name):
    """maxLength 는 3무대 실측 역산 — 근거가 스키마 설명에 남아 있어야 한다."""
    text = json.dumps(load_schema(name), ensure_ascii=False)
    for fmt in FORMATS:
        assert fmt in text, f"{name}: 지원 무대 {fmt} 가 스키마 설명에 없다"
    assert "재사용 없음" in text, f"{name}: 영상 값 재사용 금지 선언이 없다"
    # 가장 좁은 본문 폭(A4 1240 - 좌우 여백 84×2 = 1072) 이 역산의 바닥이라는 근거
    assert "1072" in text, f"{name}: 최소 본문 폭 1072px 역산 근거가 없다"


@pytest.mark.parametrize("name", DOC)
def test_fixtures_listed_and_valid(name):
    schema = load_schema(name)
    for fixture in fixtures_of(name):
        data = load_fixture(name, fixture)
        errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
        msgs = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors]
        assert not msgs, f"{name}/{fixture}: {msgs}"


@pytest.mark.parametrize("name", DOC)
def test_max_fixture_uses_max_counts(name):
    """max 픽스처는 배열 maxItems 를 채운다 — 행 수 상한이 무대 높이에 드는지가 역산의 증명."""
    schema = load_schema(name)
    data = load_fixture(name, "max")
    for key, sub in (schema.get("properties") or {}).items():
        if sub.get("type") == "array" and "maxItems" in sub and key in data:
            assert len(data[key]) == sub["maxItems"], (
                f"{name}/max: {key} 가 {len(data[key])}개 — maxItems {sub['maxItems']} 를 채워야 한다"
            )


def test_doc_body_density_is_2_to_3x_video():
    """문서형 본체의 문자 수용량은 영상 가로 7종 평균의 2~3배여야 한다 (창작 원칙의 정량 조건)."""
    video_avg = sum(capacity(load_schema(v)) for v in VIDEO_7) / len(VIDEO_7)
    doc_body = capacity(load_schema("doc-body"))
    ratio = doc_body / video_avg
    assert 2.0 <= ratio <= 3.0, (
        f"doc-body 수용량 {doc_body}자 / 영상 7종 평균 {video_avg:.0f}자 = {ratio:.2f}배 (2~3배 계약 위반)"
    )


def test_doc_body_typical_denser_than_video_narrative_scene():
    """대표 구성끼리 비교해도 2배 이상 — 상한만 크고 실제 데이터가 성긴 것을 막는다."""
    doc = nonspace(load_fixture("doc-body", "typical"))
    video = nonspace(load_fixture("problem", "typical"))
    assert doc >= 2 * video, f"doc-body typical {doc}자 < problem typical {video}자의 2배"


@pytest.mark.parametrize("name", DOC)
def test_font_scale_is_smaller_than_video(name):
    """문서형 타입 스케일은 24px 하한을 지키되 영상보다 작다 (jsx 상수 계약)."""
    src = DOC_FILE.read_text(encoding="utf-8")
    scale = dict(re.findall(r"^\s{6}(\w+): (\d+),", src, re.M))
    assert scale, "문서형 타입 스케일 상수를 찾지 못했다"
    sizes = {k: int(v) for k, v in scale.items()}
    assert min(sizes.values()) >= 24, f"24px 하한 위반 — {sizes}"
    assert sizes["body"] < 31, f"본문 {sizes['body']}px 가 영상 item 31px 보다 작지 않다"
    assert sizes["title"] < 56, f"제목 {sizes['title']}px 가 영상 sectionTitle 56px 보다 작지 않다"
    assert sizes["display"] < 112, f"표지 제목 {sizes['display']}px 가 영상 hero 112px 보다 작지 않다"


@pytest.mark.parametrize("name", DOC)
def test_module_yaml_contract(name):
    doc = load_module(name)
    assert doc["id"] == DOC[name]
    assert doc["type"] == "scene-template"
    assert doc["status"] == "draft"
    assert SEMVER.match(str(doc["version"]))
    assert doc["engine_compat"] == "animations-v2"
    assert doc["origin"] == ORIGIN
    assert doc["formats"] == FORMATS, "문서형 템플릿은 3무대 포맷을 선언한다"
    assert doc["stage"] == GOLDEN_STAGE, "골든 기준 무대는 deck-doc-16x9"
    assert doc["stages"] == STAGES, "3무대 크기 선언이 어긋난다"
    assert isinstance(doc["nat_default"], (int, float)) and doc["nat_default"] > 0
    assert doc["in_scope"] and doc["out_of_scope"]
    assert doc["metaphors"] == ["doc-page", "doc-rule"], "문서 크롬은 문서형 전용 2종뿐"
    entry = doc["entry"]
    tpl_file = ROOT / entry["template"].split("#")[0]
    assert tpl_file == DOC_FILE and tpl_file.exists()
    assert (TPL_DIR / name / entry["schema"]).exists()
    listed = [Path(fx).stem for fx in entry["fixtures"]]
    assert listed == fixtures_of(name), f"{name}: entry.fixtures 목록 불일치 — {listed}"
    for fx in entry["fixtures"]:
        assert (TPL_DIR / name / fx).exists()
    assert (TPL_DIR / name / entry["preview"]).exists()
    assert (TPL_DIR / name / "fixtures" / "snapshots" / "typical.png").exists()


@pytest.mark.parametrize("name", DOC)
def test_component_registered_in_jsx(name):
    src = DOC_FILE.read_text(encoding="utf-8")
    assert f"'{DOC[name]}'" in src, f"{DOC[name]} 이 templateIndex 에 등록되지 않았다"
    comp = load_module(name)["entry"]["template"].split("#")[1]
    assert f"function {comp}(" in src and f"{comp}.nat" in src and f"{comp}.schedule" in src, (
        f"{comp}: .nat/.schedule 정적 계약 누락"
    )


def test_doc_jsx_is_self_contained_and_multistage():
    """문서 크롬은 가로/세로 은유를 재사용하지 않고, 무대는 좌표 상수가 아니라 3종 선언이다."""
    src = DOC_FILE.read_text(encoding="utf-8")
    assert "OMX.metaphors[" not in src, "가로 은유 재사용 — 문서 크롬은 신규 저작이어야 한다"
    assert "OMX.vertical" not in src, "세로 자산 재사용 — 문서형은 자립해야 한다"
    assert "function DocPage(" in src and "function DocRule(" in src
    assert "OMX.doc" in src
    for fmt, st in STAGES.items():
        assert f"'{fmt}': {{ w: {st['w']}, h: {st['h']} }}" in src, f"{fmt} 무대 선언 누락"
    # 결정성 — 엔진 계약상 금지 식별자
    banned = re.compile(r"\b(Date\s*\.\s*now|Math\s*\.\s*random|setTimeout|setInterval"
                        r"|requestAnimationFrame|useEffect)\b")
    assert not banned.search(src), "결정성 파괴 식별자 검출"


@pytest.mark.parametrize("name", DOC)
def test_preview_supports_three_stages(name):
    html = (TPL_DIR / name / "preview.html").read_text(encoding="utf-8")
    assert "omx-templates-doc.jsx" in html
    for other in OTHER_TEMPLATE_FILES:
        assert other not in html, f"{name}: 프리뷰가 다른 계열 자산({other})을 로드한다"
    assert f"templateIndex['{DOC[name]}']" in html
    assert "stage.w" in html and "stage.h" in html, f"{name}: 무대가 고정 상수로 박혀 있다"
    for key in ("16x9", "4x3", "a4"):
        assert key in html, f"{name}: 프리뷰가 무대 {key} 를 지원하지 않는다"


def test_registry_indexes_doc_modules():
    reg = yaml.safe_load((ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    ids = [m["id"] for m in reg["modules"]]
    assert len(ids) == len(set(ids)), "레지스트리 id 중복"
    for name, tid in DOC.items():
        assert tid in ids
        entry = next(m for m in reg["modules"] if m["id"] == tid)
        assert entry["type"] == "scene-template"
        assert Path(entry["path"]) == Path("modules/scene-templates") / name
        assert entry["formats"] == FORMATS
        assert entry["stage"] == GOLDEN_STAGE
        mod = load_module(name)
        assert entry["nat_default"] == mod["nat_default"], f"{name}: nat_default 불일치"
        assert entry["status"] == mod["status"]
    order = reg["load_order_contract"]
    assert "web/templates/omx-templates-doc.jsx" in order
    assert order.index("web/templates/omx-templates-doc.jsx") < order.index("<project scenes.jsx>")


@pytest.mark.parametrize("name", DOC)
def test_x_read_fits_caption_budget(name):
    """x-read 는 낭독 대상만 표시한다 — 자막 속도 9자/초로 nat 안에 들어야 한다."""
    from wdqa.gate2_length import collect_read_chars

    chars = collect_read_chars(load_schema(name), load_fixture(name, "max"))
    nat = load_module(name)["nat_default"]
    assert chars > 0, f"{name}: max 에 x-read 글자가 없다"
    need = chars / CAPTION_CPS
    assert need <= nat, f"{name}: x-read {chars}자 ÷ {CAPTION_CPS}자/초 = {need:.1f}s > nat {nat}s"


def test_evidence_slot_is_exclusive():
    """근거 슬롯은 택1 — kind 와 다른 블록이 함께 오면 스키마가 거절한다."""
    schema = load_schema("doc-body")
    data = load_fixture("doc-body", "typical")
    bad = json.loads(json.dumps(data, ensure_ascii=False))
    bad["evidence"]["chart"] = {"bars": [{"label": "가", "value": 1}, {"label": "나", "value": 2}]}
    errors = list(Draft202012Validator(schema).iter_errors(bad))
    assert errors, "kind=table 인데 chart 가 함께 와도 통과한다 — 택1 강제가 깨졌다"

    missing = json.loads(json.dumps(data, ensure_ascii=False))
    missing["evidence"].pop("table")
    assert list(Draft202012Validator(schema).iter_errors(missing)), "kind=table 인데 table 이 없어도 통과한다"


def test_format_declaration_matches_format_yaml():
    """formats/{id}/format.yaml 이 생기면 stage·template_pool 과 정합해야 한다 (없으면 skip)."""
    checked = 0
    for fmt in FORMATS:
        fmt_path = ROOT / "formats" / fmt / "format.yaml"
        if not fmt_path.exists():
            continue
        checked += 1
        spec = yaml.safe_load(fmt_path.read_text(encoding="utf-8"))
        assert spec["stage"] == STAGES[fmt], f"{fmt}: format.yaml stage 가 템플릿 선언과 다르다"
        pool = {tid for ids in (spec.get("template_pool") or {}).values() for tid in ids}
        unknown = {t for t in pool if t.startswith("tpl.doc-")} - set(DOC.values())
        assert not unknown, f"{fmt}: 없는 문서형 템플릿을 참조한다 — {unknown}"
    if checked == 0:
        pytest.skip("문서형 formats/*/format.yaml 미생성 — 포맷 정의 작업 완료 후 검증")
