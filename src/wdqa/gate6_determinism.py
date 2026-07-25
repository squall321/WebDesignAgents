# 게이트 6 — localTime 결정성: 정적(금지 식별자 정규식, web/runtime 제외) + 런타임(이중 seek 해시 비교)
from __future__ import annotations

import re

from wdrender.exporter_video import verify_seek_determinism

from .config import QAConfig
from .entry import StaticContext, strip_js_comments
from .report import row

GATE = 6

# 결정성 파괴 식별자 (PLAN §7 게이트 6 — 정적 근사)
_BANNED_RE = re.compile(
    r"\b(Date\s*\.\s*now|Math\s*\.\s*random|setTimeout|setInterval"
    r"|requestAnimationFrame|useEffect)\b"
)


def run_static(ctx: StaticContext) -> list[dict]:
    """프로젝트 scenes.jsx·템플릿 파일에서 금지 식별자를 검출한다 (주석 제거 후 정규식)."""
    results: list[dict] = []
    for src in ctx.sources:
        text = strip_js_comments(src.text)
        for m in _BANNED_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            ident = re.sub(r"\s+", "", m.group(1))
            key = (src.label, ident)
            if any(r["path"] == src.label and ident in r["detail"] for r in results):
                continue
            results.append(
                row(GATE, "banned-identifier", "error",
                    f"결정성 파괴 식별자 {ident} 검출 (line~{line}) — "
                    "씬은 localTime 의 순수 함수여야 한다",
                    path=src.label)
            )
    return results


def run_runtime(qs, cfg: QAConfig) -> list[dict]:
    """표본 시각 seek→캡처→이탈→재-seek→재캡처 해시 비교 (wdrender 하네스 재사용)."""
    results: list[dict] = []
    dur = qs.duration
    times = [max(0.0, min(dur * f, dur - 0.01)) for f in cfg.determinism_fractions]
    checks = verify_seek_determinism(qs.sess, times)
    for c in checks:
        if not c["match"]:
            results.append(
                row(GATE, "seek-nondeterministic", "error",
                    f"t={c['time']:.2f}s 재-seek 프레임 해시 불일치 "
                    f"({c['hash1'][:10]}… ≠ {c['hash2'][:10]}…)")
            )
    return results
