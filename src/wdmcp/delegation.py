# 게이트웨이 사람별 위임(W-18) — 공유 비밀로 발급한 단기 단언(wdsso_)을 검증해 이 MCP 요청의 확인된 신원을 준다
#
# MCP 길에서 '누구인가' 를 말해 주는 머리는 원래 없다.
#   · X-Heax-User-Email — /mcp 로 오는 것은 게이트웨이 서비스 토큰의 주인(허브 첫 관리자)으로 **접힌다**.
#   · x-hwax-user — Caddy 가 지우지 않아 자기 PAT 로 직접 붙은 누구나 남의 이메일을 적어 보낸다.
# 그래서 믿는 것은 머리의 자리가 아니라 **서명**이다(HWAXRisk 와 같은 꼴 — 포털 요청서 §9 W-18).
#   1. 게이트웨이가 POST /api/auth/sso 에 공유 비밀(X-Heax-Gateway-Secret)과 확인한 호출자
#      (X-Hwax-Delegate-Email)를 보낸다 → 그 사람의 단기 단언을 받는다.
#   2. 게이트웨이가 그 사람의 MCP 호출에 단언을 X-Heax-Sso-Assertion 으로 싣는다
#      (heax_registry.per_user_sso.web_design_agents.token_header).
#   3. 도구는 서명 · 만료를 보고 그 이메일을 **확인된 신원**으로 쓴다(주인 있는 실행을 그 주인에게만 연다).
# 비밀이 없으면(기본) 전부 꺼진다 — 창구는 404, 단언 머리는 무시, 주인 있는 실행은 MCP 에 없다(W-4 그대로).
from __future__ import annotations

import base64
import contextlib
import contextvars
import hashlib
import hmac
import json
import os
import time
from pathlib import Path

__all__ = ["ASSERTION_HEADER", "TTL_S", "gateway_secret", "mint", "verify", "caller", "use_identity"]

ASSERTION_HEADER = "x-heax-sso-assertion"
PREFIX = "wdsso_"
# 단언 수명(초). 게이트웨이는 발급자의 수명이 호출 한도(GATEWAY_CALL_TIMEOUT, 600초)보다 길기를 바란다 —
# 짧으면 발급 때마다 경고하고 캐시가 사실상 꺼진다. 도구는 단언을 요청이 도착할 때만 본다.
TTL_S = 3600
# 이보다 짧은 비밀은 없는 것으로 본다 — 짧은 열쇠의 HMAC 은 지어낼 수 있다.
SECRET_MIN = 16
SECRET_ENV = "WDA_GATEWAY_SECRET"
SECRETS_FILE = "secrets.env"


def _data_dir() -> Path | None:
    try:
        from wdweb.runs import data_dir

        return data_dir()
    except Exception:  # noqa: BLE001 — 웹 모듈 없이 도는 stdio 에서는 환경변수만 본다
        return None


def gateway_secret() -> str:
    """게이트웨이와만 나눠 갖는 비밀. 없거나 짧으면 빈 글(= 위임 꺼짐).

    데이터 디렉터리의 secrets.env(`WDA_GATEWAY_SECRET=...`)가 먼저, 없으면 환경변수다. 허브 앱의
    환경변수는 매니페스트(git)에서 오므로 박스마다 다른 비밀은 앱 데이터 디렉터리에 둔다.
    """
    val = ""
    root = _data_dir()
    path = root / SECRETS_FILE if root is not None else None
    if path is not None and path.is_file():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                key, sep, raw = line.strip().partition("=")
                if sep and key.strip() == SECRET_ENV:
                    val = raw.strip().strip("\"'")
        except OSError:
            val = ""
    val = val or (os.environ.get(SECRET_ENV) or "").strip()
    return val if len(val) >= SECRET_MIN else ""


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64u(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: str, body: str) -> bytes:
    return hmac.new(secret.encode("utf-8"), body.encode("ascii"), hashlib.sha256).digest()


def mint(email: str, *, secret: str, now: float | None = None, ttl_s: int = TTL_S) -> str:
    """`wdsso_<b64u JSON {e, x, d}>.<서명>` — 이메일과 만료를 HMAC-SHA256 으로 봉인한다(저장하지 않는다).

    d 는 '위임 머리로 발급했다' 는 표지다(이 앱은 그 길로만 발급한다 — HWAXRisk 단언과 같은 칸).
    """
    exp = int((time.time() if now is None else now) + ttl_s)
    body = _b64u(json.dumps({"e": email.strip().lower(), "x": exp, "d": 1}, separators=(",", ":")).encode("utf-8"))
    return f"{PREFIX}{body}.{_b64u(_sign(secret, body))}"


def verify(token: object, *, now: float | None = None) -> str | None:
    """단언이 이 박스의 비밀로 서명됐고 만료 전이면 그 이메일(소문자), 아니면 None. 까닭은 남기지 않는다."""
    secret = gateway_secret()
    if not secret or not isinstance(token, str) or not token.startswith(PREFIX):
        return None
    body, _, sig = token[len(PREFIX):].partition(".")
    if not body or not sig:
        return None
    try:
        got = _unb64u(sig)
        if not hmac.compare_digest(_sign(secret, body), got):
            return None
        claims = json.loads(_unb64u(body))
    except (ValueError, TypeError):
        return None
    if not isinstance(claims, dict):
        return None
    email = str(claims.get("e") or "").strip().lower()
    exp = claims.get("x")
    if not isinstance(exp, int) or isinstance(exp, bool) or exp <= (time.time() if now is None else now):
        return None
    return email if "@" in email else None


def _request_headers():
    """이 MCP 요청(streamable HTTP)의 머리. stdio · 요청 밖(웹이 도구 본체를 직접 부를 때)이면 None."""
    try:
        from .server import mcp

        req = getattr(mcp.get_context().request_context, "request", None)
        return getattr(req, "headers", None)
    except Exception:  # noqa: BLE001 — 신원을 못 읽으면 '확인된 신원 없음' 이다(닫힌 쪽)
        return None


# 웹(REST) 길의 확인된 신원 — 웹 콘솔은 MCP 도구 **본체**를 같은 프로세스에서 부른다(wdweb.deliberation.call_tool). 그 길의
# 신원은 허브 Caddy 가 실은 X-Heax-User-Email 이고(W-1 과 같은 근거) 라우트가 use_identity 로 싣는다. 값이 None 이어도 '웹 길이고
# 신원이 없다' 는 뜻이라 MCP 단언으로 내려가지 않는다 — 웹 길에는 MCP 요청이 없다.
_UNSET = object()
_web_identity: contextvars.ContextVar = contextvars.ContextVar("wda_web_identity", default=_UNSET)


@contextlib.contextmanager
def use_identity(email: str | None):
    """이 블록 안의 caller() 가 웹 길의 확인된 신원(email — 없으면 None)을 돌려주게 한다."""
    token = _web_identity.set((email or "").strip().lower() or None)
    try:
        yield
    finally:
        _web_identity.reset(token)


def caller() -> str | None:
    """이 요청의 **확인된** 신원 — 웹 길이면 라우트가 실은 신원(use_identity), MCP 길이면 게이트웨이가 실은 단언의 서명이
    맞을 때만. 그 밖은 전부 None(X-Heax-User-Email · x-hwax-user 는 MCP 길에서 신원이 아니다)."""
    web = _web_identity.get()
    if web is not _UNSET:
        return web
    headers = _request_headers()
    if not headers:
        return None
    token = headers.get(ASSERTION_HEADER)
    return verify(token) if token else None
