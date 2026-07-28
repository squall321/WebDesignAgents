# 포맷 스펙 계층 테스트 — 무대 크기가 코드가 아닌 formats/{id}/format.yaml 에서 나오는지 검증
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

from wdcore.models.scenario import ScenarioDoc
from wdpipeline.build import build_render_package
from wdpipeline.format import (
    DEFAULT_FORMAT_ID,
    FormatError,
    check_format_templates,
    list_formats,
    load_format,
    module_dir,
    resolve_tpl_module_id,
    tpl_short,
)
from wdpipeline.scenario import assemble_demo_scenario, validate_scenario
from wdpipeline.fragmentize import fragmentize
from wdpipeline.ingest import ingest_report_file

REPO_ROOT = Path(__file__).resolve().parents[1]
MODULES = REPO_ROOT / "modules"
SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"


# ── 스펙 로드·검증 ──────────────────────────────────────────────────────


def test_list_formats_has_both():
    ids = list_formats()
    assert "wide-16x9" in ids and "short-9x16" in ids


def test_wide_describes_current_behaviour():
    """wide-16x9 는 현행 동작의 서술이어야 한다 — 이 값이 회귀 방지선이다."""
    spec = load_format("wide-16x9")
    assert (spec.stage.w, spec.stage.h) == (1920, 1080)
    assert spec.skeleton == [
        "opening", "problem", "concept", "process", "differentiator", "proof", "closing",
    ]
    assert [spec.primary_tpl(r) for r in spec.skeleton] == [f"tpl.{r}" for r in spec.skeleton]
    assert (spec.pptx.slide_w_in, spec.pptx.slide_h_in) == (13.333, 7.5)
    assert spec.narration.rate == 5.5
    assert DEFAULT_FORMAT_ID == "wide-16x9"


def test_short_9x16_loads_and_validates():
    spec = load_format("short-9x16")
    assert (spec.stage.w, spec.stage.h) == (1080, 1920)
    assert spec.skeleton == ["hook", "problem", "solution", "proof", "cta"]
    assert spec.tpl_ids() == ["vtpl.hook", "vtpl.stack", "vtpl.metric", "vtpl.cta"]
    assert (spec.pptx.slide_w_in, spec.pptx.slide_h_in) == (7.5, 13.333)
    assert spec.duration.min <= spec.duration.target <= spec.duration.max
    assert check_format_templates(spec) == []


def test_every_format_yaml_loads():
    """formats/ 에 있는 모든 스펙은 템플릿 실재 검사까지 통과해야 한다."""
    for fid in list_formats():
        assert load_format(fid).id == fid


def test_pool_templates_declare_the_format():
    """template_pool 의 tpl 은 module.yaml 에서 그 포맷을 지원한다고 선언해야 한다(미선언=wide)."""
    for fid in list_formats():
        spec = load_format(fid)
        for tid in spec.tpl_ids():
            module = yaml.safe_load((module_dir(tid) / "module.yaml").read_text(encoding="utf-8"))
            declared = module.get("formats") or [DEFAULT_FORMAT_ID]
            assert fid in declared, f"{tid} 가 {fid} 를 선언하지 않았다"


def test_unknown_format_id_message():
    with pytest.raises(FormatError) as e:
        load_format("tall-1x1")
    assert "포맷 스펙 없음" in str(e.value) and "wide-16x9" in str(e.value)


# ── 잘못된 스펙 거부 ────────────────────────────────────────────────────


def _write_format(root: Path, fid: str, spec: dict) -> Path:
    (root / fid).mkdir(parents=True, exist_ok=True)
    p = root / fid / "format.yaml"
    p.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
    return p


def _base_spec(fid: str = "t-fmt") -> dict:
    return {
        "id": fid,
        "name_ko": "테스트 포맷",
        "stage": {"w": 1920, "h": 1080},
        "duration": {"target": 90, "min": 20, "max": 600},
        "skeleton": ["opening"],
        "template_pool": {"opening": ["tpl.opening"]},
        "pptx": {"slide_w_in": 13.333, "slide_h_in": 7.5},
    }


def test_reject_nonpositive_stage(tmp_path: Path):
    spec = _base_spec()
    spec["stage"] = {"w": 0, "h": 1080}
    _write_format(tmp_path, "t-fmt", spec)
    with pytest.raises(FormatError, match="검증 실패"):
        load_format("t-fmt", formats_root=tmp_path)


def test_reject_empty_skeleton(tmp_path: Path):
    spec = _base_spec()
    spec["skeleton"] = []
    spec["template_pool"] = {}
    _write_format(tmp_path, "t-fmt", spec)
    with pytest.raises(FormatError, match="검증 실패"):
        load_format("t-fmt", formats_root=tmp_path)


def test_reject_duration_out_of_order(tmp_path: Path):
    spec = _base_spec()
    spec["duration"] = {"target": 90, "min": 100, "max": 600}
    _write_format(tmp_path, "t-fmt", spec)
    with pytest.raises(FormatError) as e:
        load_format("t-fmt", formats_root=tmp_path)
    assert "duration 범위 오류" in str(e.value)


def test_reject_missing_template(tmp_path: Path):
    """template_pool 의 tpl 이 레지스트리에 없으면 '템플릿 미비'로 명확히 거절한다."""
    spec = _base_spec()
    spec["template_pool"] = {"opening": ["tpl.nonexistent"]}
    _write_format(tmp_path, "t-fmt", spec)
    with pytest.raises(FormatError) as e:
        load_format("t-fmt", formats_root=tmp_path)
    assert "템플릿 미비" in str(e.value) and "tpl.nonexistent" in str(e.value)


def test_reject_template_not_declaring_format(tmp_path: Path):
    """가로 전용 템플릿(formats 미선언)을 세로 포맷 풀에 넣으면 거절한다."""
    spec = _base_spec("t-vert")
    spec["stage"] = {"w": 1080, "h": 1920}
    spec["template_pool"] = {"opening": ["tpl.opening"]}
    _write_format(tmp_path, "t-vert", spec)
    with pytest.raises(FormatError) as e:
        load_format("t-vert", formats_root=tmp_path)
    assert "지원한다고 선언하지 않았다" in str(e.value)


def test_reject_skeleton_pool_mismatch(tmp_path: Path):
    spec = _base_spec()
    spec["skeleton"] = ["opening", "closing"]
    _write_format(tmp_path, "t-fmt", spec)
    with pytest.raises(FormatError) as e:
        load_format("t-fmt", formats_root=tmp_path)
    assert "비어 있는 역할" in str(e.value)


def test_reject_id_directory_mismatch(tmp_path: Path):
    spec = _base_spec("other-id")
    _write_format(tmp_path, "t-fmt", spec)
    with pytest.raises(FormatError, match="포맷 id 불일치"):
        load_format("t-fmt", formats_root=tmp_path)


# ── tpl 식별자 해석 ─────────────────────────────────────────────────────


def test_tpl_short_and_resolution():
    assert tpl_short("opening@1") == "opening"
    assert tpl_short("vtpl.hook@1") == "hook"
    assert resolve_tpl_module_id("opening@1") == "tpl.opening"
    assert resolve_tpl_module_id("hook@1") == "vtpl.hook"
    # 레지스트리에 없는 이름은 기존 규약("tpl.{이름}")으로 떨어진다
    assert resolve_tpl_module_id("nope@1") == "tpl.nope"


# ── 시나리오 검증 연동 ──────────────────────────────────────────────────


@pytest.fixture(scope="module")
def wide_doc() -> ScenarioDoc:
    norm = ingest_report_file(SAMPLE)
    return assemble_demo_scenario(norm, fragmentize(norm))


def test_default_format_is_wide(wide_doc: ScenarioDoc):
    assert wide_doc.format == "wide-16x9"
    assert validate_scenario(wide_doc, modules_root=MODULES) == []


def test_legacy_scenario_without_format_field():
    """format 필드가 없는 기존 시나리오는 wide-16x9 로 읽히고 그대로 검증을 통과한다."""
    raw = json.loads((REPO_ROOT / "data" / "pipeline" / "delib_v1" / "scenario.json").read_text(
        encoding="utf-8"
    ))
    assert "format" not in raw
    doc = ScenarioDoc.model_validate(raw)
    assert doc.format == "wide-16x9"
    assert validate_scenario(doc, modules_root=MODULES) == []


def test_reject_duration_outside_format_band(wide_doc: ScenarioDoc):
    d = wide_doc.model_dump()
    d["scenes"] = d["scenes"][:1]
    d["scenes"][0]["dur"] = 5.0
    d["scenes"][0]["stills"] = []
    errors = validate_scenario(ScenarioDoc.model_validate(d), modules_root=MODULES)
    assert any("허용대" in e and "러닝타임" in e for e in errors)


def test_reject_tpl_outside_template_pool(wide_doc: ScenarioDoc):
    """세로 템플릿을 가로 시나리오에 쓰면 template_pool 위반으로 잡힌다."""
    d = wide_doc.model_dump()
    d["scenes"][0]["tpl"] = "hook@1"
    errors = validate_scenario(ScenarioDoc.model_validate(d), modules_root=MODULES)
    assert any("template_pool 에 없다" in e for e in errors)


def test_reject_unknown_format_in_doc(wide_doc: ScenarioDoc):
    d = wide_doc.model_dump()
    d["format"] = "tall-1x1"
    errors = validate_scenario(ScenarioDoc.model_validate(d), modules_root=MODULES)
    assert any("포맷 스펙 없음" in e for e in errors)


# ── 빌드 무대 주입 ──────────────────────────────────────────────────────


_STAGE_RE = re.compile(r"<SceneRoot width=\{(\d+)\} height=\{(\d+)\}")


def _stage_of(build_dir: Path) -> tuple[int, int]:
    m = _STAGE_RE.search((build_dir / "scenes.jsx").read_text(encoding="utf-8"))
    assert m, "scenes.jsx 에서 SceneRoot 무대 크기를 찾지 못했다"
    return int(m.group(1)), int(m.group(2))


def _injected_layout(build_dir: Path) -> dict:
    html = (build_dir / "index.html").read_text(encoding="utf-8")
    m = re.search(r"window\.OM_THEME = (\".*?\");", html, re.S)
    assert m, "index.html 에서 OM_THEME 주입을 찾지 못했다"
    return json.loads(json.loads(m.group(1)))["semantic"]["layout"]


def test_build_stage_is_1920x1080_for_wide(wide_doc: ScenarioDoc, tmp_path: Path):
    """회귀 방지선 — 포맷 미지정 경로의 빌드 무대는 1920×1080 그대로여야 한다."""
    out = tmp_path / "wide"
    build_render_package(wide_doc, out, modules_root=MODULES)
    assert _stage_of(out) == (1920, 1080)
    layout = _injected_layout(out)
    assert (layout["stageW"], layout["stageH"]) == (1920, 1080)


def test_entry_scripts_all_copied(wide_doc: ScenarioDoc, tmp_path: Path):
    """엔트리가 참조하는 templates/*.jsx 는 모두 패키지에 있어야 한다 (404 방지)."""
    out = tmp_path / "copies"
    build_render_package(wide_doc, out, modules_root=MODULES)
    html = (out / "index.html").read_text(encoding="utf-8")
    for src in re.findall(r'src="\./(templates/[^"]+)"', html):
        assert (out / src).is_file(), f"엔트리가 참조하는 {src} 사본이 없다"


def _vertical_doc() -> ScenarioDoc:
    """세로 포맷 껍데기 시나리오 — 각 역할 템플릿의 typical 픽스처를 그대로 얹는다."""
    spec = load_format("short-9x16")
    content: dict[str, dict] = {}
    scenes: list[dict] = []
    for role in spec.skeleton:
        tid = spec.primary_tpl(role)
        module = yaml.safe_load((module_dir(tid) / "module.yaml").read_text(encoding="utf-8"))
        fixture = json.loads(
            (module_dir(tid) / "fixtures" / "typical.json").read_text(encoding="utf-8")
        )
        content[role] = fixture
        dur = float(module["nat_default"])
        scenes.append({
            "name": role,
            "dur": dur,
            "nat": dur,
            "tpl": f"{tpl_short(tid)}@{str(module['version']).split('.')[0]}",
            "stills": [round(dur - 1.0, 2)],
            "data_ref": f"content.{role}",
        })
    # 자연 길이 합(48s)은 허용대(40~75) 안이다
    return ScenarioDoc.model_validate({
        "version": "1.0",
        "format": "short-9x16",
        "meta": {"core_message": "세로 껍데기", "duration_sec": sum(s["dur"] for s in scenes)},
        "content": content,
        "scenes": scenes,
    })


def test_vertical_shell_validates_and_builds(tmp_path: Path):
    """세로 포맷 껍데기 시나리오가 검증을 통과하고 1080×1920 무대로 빌드된다."""
    doc = _vertical_doc()
    assert validate_scenario(doc, modules_root=MODULES) == []
    out = tmp_path / "short"
    entry = build_render_package(doc, out, modules_root=MODULES)
    assert entry.is_file()
    assert _stage_of(out) == (1080, 1920)
    layout = _injected_layout(out)
    assert (layout["stageW"], layout["stageH"]) == (1080, 1920)
    # 세로 템플릿은 vtpl.* 모듈 id 로 바인딩되어야 한다
    scenes_jsx = (out / "scenes.jsx").read_text(encoding="utf-8")
    assert '"vtpl.hook"' in scenes_jsx and '"vtpl.cta"' in scenes_jsx


def test_assemble_rejects_format_without_builders():
    """세로 포맷은 규칙 기반 조립 휴리스틱이 아직 없다 — 조용히 깨지지 말고 명확히 거절한다."""
    norm = ingest_report_file(SAMPLE)
    with pytest.raises(NotImplementedError) as e:
        assemble_demo_scenario(norm, fragmentize(norm), format="short-9x16")
    assert "short-9x16" in str(e.value) and "hook" in str(e.value)


# ── 렌더 설정 연동 ──────────────────────────────────────────────────────


def test_render_config_takes_stage_from_format():
    from wdrender.config import apply_format, load_config

    base = load_config()
    assert (base.width, base.height) == (1920, 1080)  # render.toml 폴백

    wide = apply_format(base, "wide-16x9")
    assert (wide.width, wide.height) == (1920, 1080)
    assert (wide.slide_w_emu, wide.slide_h_emu) == (12_192_000, 6_858_000)  # 표준 16:9 EMU 보존

    short = apply_format(base, "short-9x16")
    assert (short.width, short.height) == (1080, 1920)
    assert (short.slide_w_emu, short.slide_h_emu) == (6_858_000, 12_192_000)  # 세로 슬라이드
    assert apply_format(base, None) == base


def test_stretch_to_target_is_identity_at_scale_one():
    from wdpipeline.scenario import _stretch_to_target

    nats = [8.0, 13.0, 11.0, 18.0, 13.0, 15.0, 12.0]
    assert _stretch_to_target(nats, 90) == nats  # 배율 1 → 원본 그대로 (wide 회귀 방지)
    assert sum(_stretch_to_target(nats, 45)) == 45.0
    assert _stretch_to_target(nats, 45)[0] == 4.0


def test_assemble_stretches_to_format_target(tmp_path: Path, monkeypatch):
    """duration.target 이 자연 길이 합과 다르면 균일 스케일된다 (nat 은 자연 길이 유지)."""
    src = yaml.safe_load(
        (REPO_ROOT / "formats" / "wide-16x9" / "format.yaml").read_text(encoding="utf-8")
    )
    src["duration"] = {"target": 45, "min": 20, "max": 600}
    (tmp_path / "wide-16x9").mkdir(parents=True)
    (tmp_path / "wide-16x9" / "format.yaml").write_text(
        yaml.safe_dump(src, allow_unicode=True), encoding="utf-8"
    )
    monkeypatch.setenv("WDA_FORMATS_ROOT", str(tmp_path))

    norm = ingest_report_file(SAMPLE)
    doc = assemble_demo_scenario(norm, fragmentize(norm))
    assert round(sum(s.dur for s in doc.scenes), 2) == 45.0
    assert doc.scenes[0].dur == 4.0 and doc.scenes[0].nat == 8.0  # nat 은 자연 길이 유지
