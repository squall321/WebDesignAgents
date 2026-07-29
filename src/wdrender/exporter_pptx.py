# 정적 슬라이드 exporter — 씬별 stills 시각으로 seek 캡처해 python-pptx 슬라이드로 조립 (image=풀블리드 캡처 / hybrid=배경 캡처+네이티브 텍스트박스)
from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Callable

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Pt

from .config import RenderConfig, apply_format, load_config
from .page_session import RenderSession
from .pptx_text import EMU_PER_POINT, extract_text_boxes, map_font_family, parse_css_color
from .server import StaticServer

_ALIGN = {
    "left": PP_ALIGN.LEFT,
    "start": PP_ALIGN.LEFT,
    "center": PP_ALIGN.CENTER,
    "right": PP_ALIGN.RIGHT,
    "end": PP_ALIGN.RIGHT,
    "justify": PP_ALIGN.JUSTIFY,
}


def _set_font_name(font, name: str) -> None:
    """latin 과 함께 동아시아(ea) 타입페이스도 지정 — 한글이 대체 폰트로 흘러가지 않게."""
    font.name = name
    rPr = font._element
    latin = rPr.find(qn("a:latin"))
    ea = rPr.find(qn("a:ea"))
    if ea is None:
        ea = rPr.makeelement(qn("a:ea"), {})
        latin.addnext(ea)
    ea.set("typeface", name)


def _add_text_box(slide, box: dict[str, Any], epx: float, epy: float, idx: int) -> None:
    """스테이지 px 좌표의 텍스트 상자 하나를 슬라이드 위 네이티브 텍스트박스로 얹는다."""
    tb = slide.shapes.add_textbox(
        Emu(int(round(box["x"] * epx))),
        Emu(int(round(box["y"] * epy))),
        Emu(max(1, int(round(box["w"] * epx)))),
        Emu(max(1, int(round(box["h"] * epy)))),
    )
    tb.name = f"wda-{box['role']}-{idx}"
    tf = tb.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.auto_size = MSO_AUTO_SIZE.NONE
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    # 한 줄짜리 설계 텍스트는 폰트 대체로 폭이 늘어나도 접히지 않게 줄바꿈을 끈다.
    # 원래 여러 줄인 텍스트만 설계 폭 안에서 접는다.
    tf.word_wrap = box["lines"] > 1

    p = tf.paragraphs[0]
    p.alignment = _ALIGN.get(box["text_align"], PP_ALIGN.LEFT)
    if box.get("line_height_px"):
        p.line_spacing = Pt(box["line_height_px"] * epy / EMU_PER_POINT)
    font_name = map_font_family(box["font_family"])
    size_pt = box["font_size_px"] * epx / EMU_PER_POINT
    for run in box["runs"]:
        if run.get("br"):
            p.add_line_break()  # <br>·pre 개행 → a:br (python-pptx 의 text 로는 '\v')
            continue
        r = p.add_run()
        r.text = run["text"]
        r.font.size = Pt(size_pt)
        r.font.bold = int(run.get("weight") or 400) >= 600
        r.font.italic = bool(run.get("italic"))
        _set_font_name(r.font, font_name)
        rgb = parse_css_color(run.get("color") or box["color"])
        if rgb:
            r.font.color.rgb = RGBColor(*rgb)


def export_pptx(
    root_dir: str | Path,
    page_relpath: str | Path,
    out_path: str | Path,
    *,
    config: RenderConfig | None = None,
    format_id: str | None = None,
    resources: dict[str, str] | None = None,
    stills: dict[str, list[float]] | None = None,
    notes: dict[str, str] | None = None,
    mode: str = "image",
    log: Callable[[str], None] = print,
) -> dict:
    """씬별 정지 화면을 캡처해 PPTX로 조립한다.

    format_id — 포맷 id. 주면 무대 크기와 슬라이드 크기(세로 포맷이면 세로 슬라이드)를
                포맷 스펙에서 가져온다. 미지정 시 render.toml 기본(16:9).
    stills — {씬 name: [씬 로컬 시각(초), ...]} 오버라이드. 미지정 씬은
             progress = default_still_progress(기본 0.9) 시점 1장.
    notes  — {씬 name: 발표자 노트 텍스트}. 씬의 모든 슬라이드에 동일 삽입.
    mode   — "image"(기본, 종전 동작): 화면 그대로 풀블리드 그림 1장.
             "hybrid": 텍스트를 숨긴 배경 캡처 위에 원 좌표의 네이티브 텍스트박스를 얹어
             파워포인트에서 글자를 편집할 수 있게 한다.
    반환: {slides, scenes, out, mode} 요약 dict (hybrid 는 text_boxes·skipped 추가).
    """
    if mode not in ("image", "hybrid"):
        raise ValueError(f"mode 는 'image' 또는 'hybrid' — 받은 값 {mode!r}")
    cfg = apply_format(config or load_config(), format_id)
    stills = stills or {}
    notes = notes or {}
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    prs = Presentation()
    prs.slide_width = Emu(cfg.slide_w_emu)
    prs.slide_height = Emu(cfg.slide_h_emu)
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
            # 스테이지 px → 슬라이드 EMU 비례 상수 (RenderSession 이 원척 고정을 보장)
            epx = prs.slide_width / cfg.width
            epy = prs.slide_height / cfg.height
            n_slides = 0
            n_boxes = 0
            skipped: list[dict] = []
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
                    boxes: list[dict] = []
                    if mode == "hybrid":
                        # seek 은 extract 안에서 — 뽑기와 숨기기를 같은 통과에서 확정한다
                        boxes = extract_text_boxes(sess, start + lt, hide=True)
                        skipped.extend(
                            dict(s, scene=name, t=round(start + lt, 3))
                            for s in sess.last_text_skips
                        )
                    else:
                        sess.seek(start + lt)
                    png = sess.capture()
                    slide = prs.slides.add_slide(blank_layout)
                    slide.shapes.add_picture(
                        io.BytesIO(png), 0, 0,
                        width=prs.slide_width, height=prs.slide_height,
                    )
                    for i, box in enumerate(boxes):
                        _add_text_box(slide, box, epx, epy, i)
                    n_boxes += len(boxes)
                    if name in notes:
                        slide.notes_slide.notes_text_frame.text = notes[name]
                    n_slides += 1
                    tail = f" 텍스트 {len(boxes)}개" if mode == "hybrid" else ""
                    log(
                        f"[export_pptx] 씬 '{name}' t={start + lt:.2f}s "
                        f"→ 슬라이드 {n_slides}{tail}"
                    )
                start += dur

    prs.save(out_path)
    log(f"[export_pptx] 완료 {out_path} ({n_slides}장, mode={mode})")
    info = {"slides": n_slides, "scenes": len(scenes), "out": str(out_path), "mode": mode}
    if mode == "hybrid":
        info["text_boxes"] = n_boxes
        info["skipped"] = skipped
    return info
