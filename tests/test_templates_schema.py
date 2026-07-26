# 씬 템플릿 모듈의 schema.json 유효성·fixtures 3종 스키마 통과·module.yaml/registry.yaml 정합성을 검증하는 테스트
import json
import re
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
TPL_DIR = ROOT / "modules" / "scene-templates"
EXPECTED = ["closing", "concept", "differentiator", "opening", "problem", "process", "proof"]
FIXTURES = ["min", "typical", "max"]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def load_schema(name: str) -> dict:
    return json.loads((TPL_DIR / name / "schema.json").read_text(encoding="utf-8"))


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


def test_seven_templates_present():
    names = sorted(p.name for p in TPL_DIR.iterdir() if p.is_dir())
    # 확장 템플릿(tpl.dataviz 등) 추가를 허용 — 1차 7종은 전부 존재해야 한다
    assert set(EXPECTED) <= set(names)


@pytest.mark.parametrize("name", EXPECTED)
def test_schema_is_valid_jsonschema(name):
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    assert schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema"
    assert schema.get("type") == "object"


@pytest.mark.parametrize("name", EXPECTED)
def test_schema_has_x_read_and_maxlength(name):
    schema = load_schema(name)
    assert walk_has_x_read(schema), f"{name}: x-read 낭독 필드가 하나도 없다"
    missing = walk_strings_have_maxlength(schema)
    assert not missing, f"{name}: maxLength 누락 문자열 선언 — {missing}"


@pytest.mark.parametrize("name", EXPECTED)
@pytest.mark.parametrize("fixture", FIXTURES)
def test_fixture_passes_schema(name, fixture):
    schema = load_schema(name)
    data = json.loads((TPL_DIR / name / "fixtures" / f"{fixture}.json").read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: list(e.path))
    msgs = [f"{'/'.join(map(str, e.path))}: {e.message}" for e in errors]
    assert not msgs, f"{name}/{fixture}: {msgs}"


@pytest.mark.parametrize("name", EXPECTED)
def test_module_yaml_contract(name):
    doc = yaml.safe_load((TPL_DIR / name / "module.yaml").read_text(encoding="utf-8"))
    assert doc["id"] == f"tpl.{name}"
    assert doc["type"] == "scene-template"
    assert doc["status"] == "draft"
    assert SEMVER.match(str(doc["version"]))
    assert doc["engine_compat"] == "animations-v2"
    assert doc["origin"].startswith("examples/hwax_intro/hwax-scenes.jsx#")
    assert isinstance(doc["nat_default"], (int, float)) and doc["nat_default"] > 0
    assert doc["in_scope"] and doc["out_of_scope"]
    entry = doc["entry"]
    assert (ROOT / entry["template"].split("#")[0]).exists()
    assert (TPL_DIR / name / entry["schema"]).exists()
    for fx in entry["fixtures"]:
        assert (TPL_DIR / name / fx).exists()
    assert (TPL_DIR / name / entry["preview"]).exists()


def test_registry_indexes_all_modules():
    reg = yaml.safe_load((ROOT / "modules" / "registry.yaml").read_text(encoding="utf-8"))
    ids = [m["id"] for m in reg["modules"]]
    assert len(ids) == len(set(ids)), "레지스트리 id 중복"
    for name in EXPECTED:
        assert f"tpl.{name}" in ids
    for mtp in ["frame-chrome", "dot-grid", "chatbot-mockup", "radial-network",
                "step-card-grid", "rebuttal-flow", "checkmark-converge", "stat-trio", "cta-pill"]:
        assert f"mtp.{mtp}" in ids
    assert "theme.hwax-blue" in ids
    for m in reg["modules"]:
        if m["type"] == "scene-template":
            assert (ROOT / m["path"] / "module.yaml").exists()


def test_theme_tokens_shape():
    theme = json.loads((ROOT / "web" / "tokens" / "hwax-blue.json").read_text(encoding="utf-8"))
    assert len(theme["raw"]["palette"]) == 16, "raw 팔레트는 원본 C 16색"
    assert theme["raw"]["font"]["base"]
    assert theme["raw"]["shadow"]["card"]
    motion = theme["semantic"]["motion"]
    for preset in ["rise", "pop", "tag", "exit", "stagger"]:
        assert preset in motion
    pairs = theme["semantic"]["contrastPairs"]
    assert len(pairs) >= 15
    ref = re.compile(r"^\{[A-Za-z0-9_.\-]+\}$")
    for p in pairs:
        assert ref.match(p["fg"]) and ref.match(p["bg"]), f"contrastPair 참조 문법 위반: {p}"
