# 관용 입력(REST/pages 조각/마크다운)·자산 픽스처 생성기 — report_sample.json 을 변형해 만든다
from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SAMPLE = REPO / "examples" / "reportarchive" / "report_sample.json"


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}")


def make_rest_envelope(sample: dict) -> None:
    """② REST 응답 원형 — {success, data:{...}} 봉투 + ReportRead 메타 키 + 인라인 content."""
    pages = []
    for i, page in enumerate(sample["pages"]):
        content = dict(page.get("content") or {})
        extra = []
        for b in page["extra_blocks"]:
            eb = {"id": b["id"], "type": b["type"], "props": b.get("props") or {}}
            if i == 0 and b["id"] in content:      # 1페이지는 ai-draft 형태(인라인 content)
                eb["content"] = content.pop(b["id"])
            extra.append(eb)
        out = {
            "name": page["name"],
            "extra_blocks": extra,
            "content": content,
            "blocks": {},
            "blocks_order": page.get("blocks_order") or [],
            "block_sections": page.get("block_sections") or {},
        }
        if i == 1:  # 2페이지에 정의 없는 템플릿 슬롯 하나 — 타입 추정 경로
            out["blocks"] = {"tpl_slot_note": {"markdown": "템플릿 슬롯에만 담긴 문단."}}
        pages.append(out)

    _write(HERE / "rest_envelope.json", {
        "success": True,
        "message": "ok",
        "data": {
            "id": 578,
            "title": sample["title"],
            "created_at": f"{sample['report_date']}T09:12:33Z",
            "tags": [{"name": t} for t in sample["tags"]],
            "search_text": "서버가 만들어 준 평탄화 평문",
            "ai_summary": {"core_message": "보고서를 발표 영상으로 바꾼다"},
            "pages": pages,
        },
    })


def make_pages_only(sample: dict) -> None:
    """③ pages 배열만 있는 조각 JSON — 메타 없음(제목은 첫 heading 에서 승격)."""
    _write(HERE / "pages_only.json", sample["pages"][:2])


def make_markdown() -> None:
    """④ 사람이 구두 정리한 마크다운 초안."""
    md = """# 심의 플랫폼 도입 검토

현행 보고서 검토는 담당자 개인의 감에 의존한다.

## 문제

- 검토 기준이 문서마다 다르다
- 근거 인용이 사후에 추적되지 않는다
- 결론까지 평균 9일이 걸린다

## 지표

| 항목 | 현행 | 목표 |
| --- | --- | --- |
| 검토 소요 | 9일 | 2일 |
| 인용 추적률 | 31% | 95% |

```python
run("wda ingest --file report.json")
```

# 결론

파일럿을 3개 부서에 먼저 적용한다.

1. 1분기 파일럿
2. 2분기 확대
"""
    path = HERE / "human_notes.md"
    path.write_text(md, encoding="utf-8")
    print(f"wrote {path.relative_to(REPO)}")


def make_assets() -> None:
    """자산 픽스처 — 합성 이미지 3장 + 매핑 파일. img_wide 는 1920 초과(리사이즈 대상)."""
    from PIL import Image

    adir = HERE / "assets"
    adir.mkdir(parents=True, exist_ok=True)
    specs = [
        ("f-hero.png", (2400, 1350), (28, 64, 140)),      # 리사이즈 대상
        ("f-diagram.png", (800, 600), (240, 240, 245)),   # 그대로
        ("brand-logo.jpg", (512, 512), (200, 60, 60)),    # 매핑 파일로만 찾히는 이름
    ]
    for name, size, color in specs:
        img = Image.new("RGB", size, color)
        for x in range(0, size[0], 40):  # 리사이즈 확인용 줄무늬
            for y in range(size[1]):
                img.putpixel((x, y), (255, 255, 255))
        img.save(adir / name)
        print(f"wrote {(adir / name).relative_to(REPO)}")
    _write(adir / "assets.json", {"f-logo": "brand-logo.jpg"})


def make_image_report() -> None:
    """자산 참조가 있는 복붙 draft — 해결 2건 + 미해결 1건."""
    _write(HERE / "report_with_images.json", {
        "_type": "report_archive_draft_v1",
        "title": "자산 참조 보고서",
        "report_date": "2026-07-01",
        "tags": ["자산"],
        "pages": [{
            "name": "1. 화면",
            "extra_blocks": [
                {"id": "h1", "type": "heading", "props": {"level": 1}},
                {"id": "img_hero", "type": "image", "props": {"file_id": "f-hero"}},
                {"id": "img_diagram", "type": "image", "props": {"file_id": "f-diagram"}},
                {"id": "img_logo", "type": "image", "props": {"file_id": "f-logo"}},
                {"id": "img_missing", "type": "image", "props": {"file_id": "f-nowhere"}},
            ],
            "content": {
                "h1": {"text": "자산 참조 보고서"},
                "img_hero": {"caption": "히어로 이미지"},
                "img_diagram": {"caption": "구조도"},
                "img_logo": {"caption": "로고"},
                "img_missing": {"caption": "빠진 그림"},
            },
            "blocks_order": [],
            "block_sections": {},
        }],
    })


def main() -> None:
    sample = json.loads(SAMPLE.read_text(encoding="utf-8"))
    make_rest_envelope(sample)
    make_pages_only(sample)
    make_markdown()
    make_assets()
    make_image_report()


if __name__ == "__main__":
    main()
