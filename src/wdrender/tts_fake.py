# 테스트·오프라인 시연용 가짜 VoiceRecorder — measure_scenes 가 쓰는 API 만 httpx.MockTransport 로 흉내 낸다
from __future__ import annotations

import array
import io
import json
import math
import re
import uuid
import wave

import httpx

_WS_RE = re.compile(r"\s+")
# 정규화 뒤에도 남는 영문(소문자가 섞인 낱말) — 실제 서버는 대문자 약어를 철자로 읽는다
_LATIN_RE = re.compile(r"[A-Za-z]*[a-z][A-Za-z]*")


def tone_wav(seconds: float, *, rate: int = 24000, channels: int = 1, freq: float = 220.0) -> bytes:
    """seconds 길이의 16비트 사인파 wav 바이트 — 낭독 자리에 들어갈 소리."""
    n = int(round(seconds * rate))
    samples = array.array("h", (int(6000 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n)))
    if channels > 1:
        samples = array.array("h", (v for v in samples for _ in range(channels)))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(samples.tobytes())
    return buf.getvalue()


class FakeVoiceRecorder:
    """VoiceRecorder 프로젝트 API 의 최소 흉내.

    낭독 길이 = 공백 뺀 글자수 ÷ cps (기본 7자/초 — MeloTTS 1.2배 실측 근처).
    fail_scenes 에 씬 제목을 넣으면 그 씬은 합성 오류로 돌려준다.
    requests·auth·deleted 로 무엇이 불렸는지 확인할 수 있다.
    """

    def __init__(
        self,
        *,
        cps: float = 7.0,
        speed: float = 1.2,
        engines: tuple[str, ...] = ("melo",),
        default: str = "melo",
        rate: int = 24000,
        fail_scenes: set[str] | None = None,
    ) -> None:
        self.cps, self.speed, self.rate = cps, speed, rate
        self.engines, self.default = engines, default
        self.fail_scenes = fail_scenes or set()
        self.projects: dict[str, dict] = {}
        self.deleted: list[str] = []
        self.requests: list[tuple[str, str]] = []
        self.auth: list[str | None] = []

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def seconds_for(self, text: str) -> float:
        return round(len(_WS_RE.sub("", text)) / self.cps, 3)

    # ── 내부 ──

    def _scene(self, text: str, title: str | None) -> dict:
        return {
            "id": uuid.uuid4().hex[:12], "title": title, "text": text, "status": "pending",
            "duration_sec": None, "raw_duration_sec": None, "error": None,
            "unread_latin": _LATIN_RE.findall(text), "misread_hints": [],
        }

    def _payload(self, pid: str) -> dict:
        proj = self.projects[pid]
        scenes = [{k: v for k, v in s.items() if not k.startswith("_")} for s in proj["scenes"]]
        for i, s in enumerate(scenes):
            s["position"] = i
        return {"project": dict(proj["project"]), "scenes": scenes}

    def _handle(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        self.requests.append((method, path))
        self.auth.append(request.headers.get("authorization"))
        body = json.loads(request.content) if request.content else {}
        parts = path.strip("/").split("/")

        if path == "/api/engines":
            return httpx.Response(200, json={
                "engines": [{"id": e, "available": True} for e in self.engines],
                "default": self.default, "default_speed": self.speed, "ffmpeg": True,
            })
        if path == "/api/projects" and method == "POST":
            pid = uuid.uuid4().hex[:12]
            self.projects[pid] = {
                "project": {
                    "id": pid, "title": body.get("title"), "engine": body.get("engine"),
                    "speed": body.get("speed", self.speed), "voice_id": body.get("voice_id"),
                },
                "scenes": [self._scene(body["raw_script"], None)],
            }
            return httpx.Response(201, json=self._payload(pid))
        if parts[:2] == ["api", "jobs"]:
            return httpx.Response(200, json={"id": parts[2], "status": "done", "done": 1, "total": 1})
        if len(parts) >= 3 and parts[:2] == ["api", "projects"]:
            pid = parts[2]
            proj = self.projects.get(pid)
            if proj is None:
                return httpx.Response(404, json={"detail": "프로젝트가 없습니다"})
            if len(parts) == 3 and method == "GET":
                return httpx.Response(200, json=self._payload(pid))
            if len(parts) == 3 and method == "DELETE":
                del self.projects[pid]
                self.deleted.append(pid)
                return httpx.Response(204)
            if parts[3] == "synthesize" and method == "POST":
                for sc in proj["scenes"]:
                    if sc["title"] in self.fail_scenes:
                        sc.update(status="error", error="가짜 합성 오류")
                        continue
                    sec = self.seconds_for(sc["text"])
                    sc.update(status="ready", duration_sec=sec, raw_duration_sec=round(sec * self.speed, 3))
                    sc["_wav"] = tone_wav(sec, rate=self.rate)
                return httpx.Response(202, json={"job_id": f"job-{pid}", "scene_count": len(proj["scenes"])})
            if parts[3] == "scenes" and len(parts) == 4 and method == "POST":
                proj["scenes"].append(self._scene(body["text"], body.get("title")))
                return httpx.Response(201, json=self._payload(pid))
            if parts[3] == "scenes" and len(parts) >= 5:
                scene = next((s for s in proj["scenes"] if s["id"] == parts[4]), None)
                if scene is None:
                    return httpx.Response(404, json={"detail": "씬이 없습니다"})
                if len(parts) == 5 and method == "PATCH":
                    for key in ("text", "title"):
                        if key in body:
                            scene[key] = body[key]
                    scene["unread_latin"] = _LATIN_RE.findall(scene["text"])
                    return httpx.Response(200, json=self._payload(pid))
                if len(parts) == 6 and parts[5] == "audio" and "_wav" in scene:
                    return httpx.Response(200, content=scene["_wav"], headers={"content-type": "audio/wav"})
        return httpx.Response(404, json={"detail": f"가짜 VoiceRecorder 에 없는 경로: {method} {path}"})
