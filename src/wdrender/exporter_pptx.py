# 정적 슬라이드 exporter — 씬별 stills 시각으로 seek 캡처해 python-pptx 16:9 풀블리드 조립
from __future__ import annotations

import io
from pathlib import Path
from typing import Callable

from pptx import Presentation
from pptx.util import Emu

from .config import RenderConfig, load_config
from .page_session import RenderSession
from .server import StaticServer

# PowerPoint 표준 16:9 (13.333in × 7.5in)
_SLIDE_W_EMU = 12_192_000
_SLIDE_H_EMU = 6_858_000


def export_pptx(
    root_dir: str | Path,
    page_relpath: str | Path,
    out_path: str | Path,
    *,
    config: RenderConfig | None = None,
    resources: dict[str, str] | None = None,
    stills: dict[str, list[float]] | None = None,
    notes: dict[str, str] | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """씬별 정지 화면을 캡처해 16:9 PPTX로 조립한다.

    stills — {씬 name: [씬 로컬 시각(초), ...]} 오버라이드. 미지정 씬은
             progress = default_still_progress(기본 0.9) 시점 1장.
    notes  — {씬 name: 발표자 노트 텍스트}. 씬의 모든 슬라이드에 동일 삽입.
    반환: {slides, scenes, out} 요약 dict.
    """
    cfg = config or load_config()
    stills = stills or {}
    notes = notes or {}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    prs = Presentation()
    prs.slide_width = Emu(_SLIDE_W_EMU)
    prs.slide_height = Emu(_SLIDE_H_EMU)
    blank_layout = prs.slide_layouts[6]

    with StaticServer(root_dir) as srv:
        url = srv.url_for(page_relpath)
        log(f"[export_pptx] 페이지 로드 {url}")
        with RenderSession(
            url,
            width=cfg.width,
            height=cfg.height,
            viewport_margin=cfg.viewport_margin,
            resources=resources,
        ) as sess:
            scenes = sess.scenes()
            if not scenes:
                raise RuntimeError("window.OM_SCENES 를 읽을 수 없음 — dc 엔트리가 아님?")
            n_slides = 0
            start = 0.0
            for sc in scenes:
                name = sc["name"]
                dur = float(sc["dur"])
                local_times = stills.get(name) or [dur * cfg.default_still_progress]
                for lt in local_times:
                    if not (0.0 <= lt <= dur):
                        raise ValueError(
                            f"씬 '{name}' still {lt}s 가 [0, {dur}] 범위 밖"
                        )
                    sess.seek(start + lt)
                    png = sess.capture()
                    slide = prs.slides.add_slide(blank_layout)
                    slide.shapes.add_picture(
                        io.BytesIO(png), 0, 0,
                        width=prs.slide_width, height=prs.slide_height,
                    )
                    if name in notes:
                        slide.notes_slide.notes_text_frame.text = notes[name]
                    n_slides += 1
                    log(f"[export_pptx] 씬 '{name}' t={start + lt:.2f}s → 슬라이드 {n_slides}")
                start += dur

    prs.save(out_path)
    log(f"[export_pptx] 완료 {out_path} ({n_slides}장)")
    return {"slides": n_slides, "scenes": len(scenes), "out": str(out_path)}
