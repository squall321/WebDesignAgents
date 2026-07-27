# 빌드 엔트리의 스크립트 로드 순서가 modules/registry.yaml 계약과 일치하는지 — 템플릿 누락 사고 재발 방지
from pathlib import Path

import yaml

from wdpipeline.build import load_order

REPO = Path(__file__).resolve().parents[1]


def test_load_order_matches_registry_contract():
    contract = yaml.safe_load((REPO / "modules" / "registry.yaml").read_text(encoding="utf-8"))[
        "load_order_contract"
    ]
    order = load_order()
    assert len(order) == len(contract), f"계약 {len(contract)}개 vs 로드 {len(order)}개"
    for src, got in zip(contract, order):
        if str(src).startswith("<"):
            assert got == "./scenes.jsx"
        else:
            assert got.endswith(Path(str(src)).name), f"{src} ↔ {got} 불일치"


def test_every_template_file_is_loaded():
    """web/templates 의 모든 omx-*.jsx 가 엔트리에 실린다 (창작 모드 승격 시 누락 방지)."""
    files = {p.name for p in (REPO / "web" / "templates").glob("omx-*.jsx")}
    loaded = {Path(s).name for s in load_order()}
    missing = files - loaded
    assert not missing, f"엔트리에 안 실리는 템플릿 파일: {sorted(missing)} — registry.yaml 계약에 추가하라"
