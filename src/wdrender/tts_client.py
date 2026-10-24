# VoiceRecorder(:8177) 프로젝트/씬 플로우로 시나리오 내레이션을 합성하는 HTTP 클라이언트
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "http://localhost:8177"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "tts_check"
# 측정 프로젝트의 자리표시 문단 — 첫 씬은 곧바로 원문으로 PATCH 한다 (대본 파서 우회, 결정 57)
_PLACEHOLDER_SCRIPT = "측정 준비"


def _env(key: str) -> str | None:
    """환경변수 → .env 순으로 읽는다.

    WDA_TTS_* 는 Settings 필드가 아니라 pydantic-settings 가 .env 에서 가져가지 않는다 —
    결정 47 의 LLM_* 와 같은 함정이라 같은 덧대기를 쓴다.
    """
    from wdllm.config import _env_with_dotenv

    value = (_env_with_dotenv().get(key) or "").strip()
    return value or None


def resolve_base_url(base_url: str | None = None) -> str:
    """인자 → WDA_TTS_BASE_URL(환경변수·.env) → 기본 localhost:8177 순으로 결정한다."""
    return (base_url or _env("WDA_TTS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _client(
    base_url: str | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    timeout: float = 60.0,
) -> httpx.Client:
    """VoiceRecorder 호출용 클라이언트.

    포털(Caddy forward_auth) 경유면 WDA_TTS_PAT 를 Bearer 로 붙인다 (PLAN §10.2 경로 규약).
    trust_env=False — 사내 프록시 환경변수가 localhost·포털 호출을 프록시로 돌리지 않게 (wdllm 과 같다).
    """
    pat = _env("WDA_TTS_PAT")
    return httpx.Client(
        base_url=resolve_base_url(base_url),
        headers={"Authorization": f"Bearer {pat}"} if pat else None,
        timeout=timeout,
        trust_env=False,
        transport=transport,
    )


def format_timecode(seconds: float) -> str:
    """절대 초 → 'M:SS' (1시간 이상이면 'H:MM:SS', 소수부는 '.5'처럼 유지)."""
    seconds = max(0.0, float(seconds))
    total_ms = int(round(seconds * 1000))
    frac_ms = total_ms % 1000
    total_s = total_ms // 1000
    h, rem = divmod(total_s, 3600)
    m, s = divmod(rem, 60)
    base = f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"
    if frac_ms:
        base += ("." + f"{frac_ms:03d}".rstrip("0"))
    return base


def build_raw_script(scenario: dict) -> str:
    """scenario.scenes 의 name/dur/narration 으로 타임코드 스크립트를 조립한다.

    한 씬 = 한 블록(빈 줄 구분), `NN 제목 (M:SS-M:SS) "내레이션"` 형식.
    타임코드는 dur 누적의 절대 시각이라 내레이션 없는 씬을 건너뛰어도 슬롯이 어긋나지 않는다.
    """
    scenes = scenario.get("scenes") or []
    if not scenes:
        raise ValueError("scenario 에 scenes 가 없습니다")

    blocks: list[str] = []
    names: list[str] = []
    cursor = 0.0
    for scene in scenes:
        dur = float(scene.get("dur") or 0.0)
        start, end = cursor, cursor + dur
        cursor = end
        narration = (scene.get("narration") or "").strip()
        if not narration:
            continue
        num = len(blocks) + 1
        name = (scene.get("name") or f"씬{num}").strip()
        blocks.append(
            f'{num:02d} {name} ({format_timecode(start)}-{format_timecode(end)}) "{narration}"'
        )
        names.append(name)
    if not blocks:
        raise ValueError("내레이션이 있는 씬이 없습니다")
    return "\n\n".join(blocks)


def _narrated_scene_names(scenario: dict) -> list[str]:
    """스크립트에 포함되는(내레이션이 있는) 씬 이름을 순서대로 반환한다."""
    names = []
    for scene in scenario.get("scenes") or []:
        if (scene.get("narration") or "").strip():
            names.append((scene.get("name") or f"씬{len(names) + 1}").strip())
    return names


def _pick_engine(client: httpx.Client, requested: str | None, log: Callable[[str], None]) -> str:
    """GET /api/engines 로 가용 엔진을 확인한다 — 요청 엔진이 불가면 첫 available 로 폴백."""
    r = client.get("/api/engines")
    r.raise_for_status()
    data = r.json()
    engines = data.get("engines") or []
    available = [e["id"] for e in engines if e.get("available")]
    if not available:
        raise RuntimeError("VoiceRecorder 에 사용 가능한 TTS 엔진이 없습니다")
    if requested and requested in available:
        return requested
    default = data.get("default")
    chosen = default if default in available else available[0]
    if requested:
        log(f"[tts] 엔진 {requested!r} 불가 → {chosen!r} 폴백")
    return chosen


def _poll_job(
    client: httpx.Client,
    job_id: str,
    *,
    label: str,
    timeout_sec: float,
    poll_interval_sec: float,
    log: Callable[[str], None],
) -> dict:
    """GET /api/jobs/{id} 를 done/error 까지 폴링한다. 진행 변화가 있을 때만 로그."""
    t0 = time.monotonic()
    last_snap = None
    while True:
        r = client.get(f"/api/jobs/{job_id}")
        r.raise_for_status()
        job = r.json()
        status = job.get("status")
        snap = (status, job.get("done"), job.get("total"), job.get("current"))
        if snap != last_snap:
            cur = job.get("current") or ""
            log(
                f"[tts] {label} job={job_id[:8]} {status} "
                f"{job.get('done')}/{job.get('total')} {cur} "
                f"(경과 {time.monotonic() - t0:.0f}s)"
            )
            last_snap = snap
        if status == "done":
            return job
        if status == "error":
            raise RuntimeError(f"{label} 작업 실패: {job.get('error')}")
        if time.monotonic() - t0 > timeout_sec:
            raise TimeoutError(
                f"{label} 작업 타임아웃 ({timeout_sec:.0f}s 초과, job={job_id}, 마지막 상태={snap})"
            )
        time.sleep(poll_interval_sec)


def _download(client: httpx.Client, url: str, dest: Path) -> Path:
    r = client.get(url)
    r.raise_for_status()
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(r.content)
    return dest


def oneshot_tts(
    text: str,
    *,
    engine: str | None = None,
    voice_id: str | None = None,
    speed: float = 1.0,
    out_path: str | Path | None = None,
    base_url: str | None = None,
    timeout_sec: float = 120.0,
    poll_interval_sec: float = 1.0,
    log: Callable[[str], None] = print,
) -> dict:
    """원샷 stateless TTS (POST /api/tts) — 프로젝트 없이 문장 단위 길이 실측/미리듣기.

    잡 완료 후 out_path 를 주면 wav 를 내려받고, 서버의 임시 산출물은 항상 정리한다.
    반환: {duration_sec, raw_duration_sec, char_count, audio_path(요청 시), tts_id}
    """
    with _client(base_url) as client:
        body: dict = {"text": text, "speed": speed}
        if engine:
            body["engine"] = engine
        if voice_id:
            body["voice_id"] = voice_id
        r = client.post("/api/tts", json=body)
        r.raise_for_status()
        ids = r.json()  # {job_id, tts_id}
        job = _poll_job(
            client,
            ids["job_id"],
            label="원샷 TTS",
            timeout_sec=timeout_sec,
            poll_interval_sec=poll_interval_sec,
            log=log,
        )
        result = job.get("result") or {}
        audio_path = None
        if out_path:
            audio_path = _download(client, f"/api/tts/{ids['tts_id']}/audio", Path(out_path))
        client.delete(f"/api/tts/{ids['tts_id']}")
    return {
        "duration_sec": result.get("duration_sec"),
        "raw_duration_sec": result.get("raw_duration_sec"),
        "char_count": result.get("char_count"),
        "audio_path": str(audio_path) if audio_path else None,
        "tts_id": ids["tts_id"],
    }


def synthesize_scenario(
    scenario: dict,
    *,
    engine: str | None = None,
    voice_id: str | None = None,
    max_speed: float = 2.0,
    base_url: str | None = None,
    out_dir: str | Path | None = None,
    scene_timeout_sec: float = 120.0,
    poll_interval_sec: float = 2.0,
    log: Callable[[str], None] = print,
) -> dict:
    """시나리오 내레이션 전체를 VoiceRecorder 로 합성해 병합 mp3+SRT 를 받아온다.

    절차: 스크립트 조립 → 프로젝트 생성 → 합성 잡 폴링 → fit-timecode(무음/배속 정렬)
    → 씬별 duration/drift 수신 → export 잡 폴링 → mp3/SRT 다운로드 → 프로젝트 삭제.
    over_budget(max_speed 로도 슬롯에 안 들어가는 씬)은 수정 없이 그대로 반환한다.

    반환: {audio_path, srt_path, total_sec, scenes: [{name, duration_sec, drift_sec}],
           over_budget: [...], engine, project_title}
    """
    raw_script = build_raw_script(scenario)
    names = _narrated_scene_names(scenario)
    out_dir = Path(out_dir) if out_dir else DEFAULT_OUT_DIR
    title = "WDA " + (scenario.get("meta", {}).get("core_message") or "scenario")[:80]

    with _client(base_url) as client:
        # ③ 가용 엔진 확인 (스크립트 조립 ① 은 위에서 완료)
        chosen_engine = _pick_engine(client, engine, log)
        log(f"[tts] 엔진={chosen_engine} 씬={len(names)}개 스크립트 {len(raw_script)}자")

        # ② 프로젝트 생성
        body = {"title": title, "raw_script": raw_script, "engine": chosen_engine, "language": "ko"}
        if voice_id:
            body["voice_id"] = voice_id
        r = client.post("/api/projects", json=body)
        r.raise_for_status()
        payload = r.json()
        project_id = payload["project"]["id"]
        parsed_count = len(payload["scenes"])
        log(f"[tts] 프로젝트 생성 id={project_id} 파싱 씬={parsed_count}")
        if parsed_count != len(names):
            raise RuntimeError(
                f"씬 수 불일치: 스크립트 {len(names)}개 vs 서버 파싱 {parsed_count}개 "
                f"(project={project_id} 는 진단을 위해 남겨둠)"
            )

        # ④ 합성 잡 → 폴링
        r = client.post(f"/api/projects/{project_id}/synthesize", json={})
        r.raise_for_status()
        synth_job = r.json()
        _poll_job(
            client,
            synth_job["job_id"],
            label="합성",
            timeout_sec=scene_timeout_sec * max(1, synth_job.get("scene_count", parsed_count)),
            poll_interval_sec=poll_interval_sec,
            log=log,
        )

        # ⑤ fit-timecode — 씬 슬롯 자동 정렬(부족분 무음·초과분 배속)
        r = client.post(f"/api/projects/{project_id}/fit-timecode", json={"max_speed": max_speed})
        r.raise_for_status()
        fit_report = r.json().get("fit_report") or {}
        over_budget = fit_report.get("over_budget") or []
        if over_budget:
            log(f"[tts] over_budget {len(over_budget)}건: {over_budget}")

        # ⑥ 씬별 duration/drift 수신
        r = client.get(f"/api/projects/{project_id}")
        r.raise_for_status()
        payload = r.json()
        scenes_out = [
            {
                "name": names[i] if i < len(names) else s.get("title"),
                "duration_sec": s.get("duration_sec"),
                "drift_sec": s.get("drift_sec"),
            }
            for i, s in enumerate(payload["scenes"])
        ]
        total_sec = payload.get("total_sec")

        # ⑦ export 잡 → mp3/SRT 다운로드
        r = client.post(f"/api/projects/{project_id}/export")
        r.raise_for_status()
        _poll_job(
            client,
            r.json()["job_id"],
            label="익스포트",
            timeout_sec=scene_timeout_sec * max(1, parsed_count),
            poll_interval_sec=poll_interval_sec,
            log=log,
        )
        audio_path = _download(client, f"/api/projects/{project_id}/export/audio", out_dir / "narration.mp3")
        srt_path = _download(client, f"/api/projects/{project_id}/export/srt", out_dir / "narration.srt")
        log(f"[tts] 다운로드 완료 {audio_path} ({audio_path.stat().st_size} bytes)")

        # ⑧ 성공 시 프로젝트 정리 (실패 시엔 진단용으로 서버에 남는다)
        client.delete(f"/api/projects/{project_id}").raise_for_status()
        log(f"[tts] 프로젝트 삭제 id={project_id}")

    return {
        "audio_path": str(audio_path),
        "srt_path": str(srt_path),
        "total_sec": total_sec,
        "scenes": scenes_out,
        "over_budget": over_budget,
        "engine": chosen_engine,
        "project_title": title,
    }


def measure_scenes(
    scenes: list[tuple[str, str]],
    *,
    out_dir: str | Path,
    engine: str | None = None,
    voice_id: str | None = None,
    speed: float | None = None,
    base_url: str | None = None,
    title: str = "WDA 내레이션",
    scene_timeout_sec: float = 120.0,
    poll_interval_sec: float = 1.0,
    transport: httpx.BaseTransport | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """(씬 이름, 내레이션) 목록을 원문 그대로 합성해 씬별 실측 길이와 음성 파일을 받는다.

    대본 파서를 거치지 않는다(결정 57) — 자리표시 문단 하나로 프로젝트를 만들고 첫 씬은 PATCH,
    나머지는 씬 추가로 원문을 넣는다. 엔진·화자·속도를 안 주면 WDA_TTS_ENGINE/VOICE_ID/SPEED,
    그것도 없으면 서버 기본(MeloTTS 1.2배)을 쓴다. 성공하든 실패하든 서버 프로젝트는 지운다.

    반환: {engine, speed, voice_id, scenes: [{name, text, duration_sec, raw_duration_sec,
           audio_path, unread_latin, misread_hints}]}
    """
    if not scenes:
        raise ValueError("측정할 내레이션이 없다")
    engine = engine or _env("WDA_TTS_ENGINE")
    voice_id = voice_id or _env("WDA_TTS_VOICE_ID")
    if speed is None and _env("WDA_TTS_SPEED"):
        speed = float(_env("WDA_TTS_SPEED"))
    out_dir = Path(out_dir)

    with _client(base_url, transport=transport) as client:
        chosen = _pick_engine(client, engine, log)
        body: dict = {
            "title": title[:200], "raw_script": _PLACEHOLDER_SCRIPT,
            "engine": chosen, "language": "ko",
        }
        if voice_id:
            body["voice_id"] = voice_id
        if speed is not None:
            body["speed"] = speed
        r = client.post("/api/projects", json=body)
        r.raise_for_status()
        payload = r.json()
        project_id = payload["project"]["id"]
        try:
            name, text = scenes[0]
            first_id = payload["scenes"][0]["id"]
            client.patch(
                f"/api/projects/{project_id}/scenes/{first_id}", json={"text": text, "title": name}
            ).raise_for_status()
            for name, text in scenes[1:]:
                client.post(
                    f"/api/projects/{project_id}/scenes", json={"text": text, "title": name}
                ).raise_for_status()

            r = client.post(f"/api/projects/{project_id}/synthesize", json={})
            r.raise_for_status()
            log(f"[tts] 엔진={chosen} 씬={len(scenes)}개 합성 시작 (project={project_id})")
            _poll_job(
                client, r.json()["job_id"], label="내레이션 합성",
                timeout_sec=scene_timeout_sec * len(scenes),
                poll_interval_sec=poll_interval_sec, log=log,
            )

            r = client.get(f"/api/projects/{project_id}")
            r.raise_for_status()
            payload = r.json()
            got = payload["scenes"]
            # 씬별 결과를 순서로 짝짓는다 — 넣은 원문과 다르면 짝이 어긋난 것이다
            if [s.get("text") for s in got] != [t for _, t in scenes]:
                raise RuntimeError("VoiceRecorder 에 넣은 씬과 돌려받은 씬의 개수·순서·원문이 다르다")
            # 합성 잡은 일부 씬이 실패해도 done 이 된다 — 씬마다 확인한다
            failed = [
                f"{n}: {s.get('error') or s.get('status')}"
                for (n, _), s in zip(scenes, got) if s.get("status") != "ready"
            ]
            if failed:
                raise RuntimeError("내레이션 합성 실패 — " + "; ".join(failed))

            measured = []
            for i, ((name, text), s) in enumerate(zip(scenes, got), start=1):
                audio = _download(
                    client, f"/api/projects/{project_id}/scenes/{s['id']}/audio", out_dir / f"{i:02d}.wav"
                )
                measured.append({
                    "name": name,
                    "text": text,
                    "duration_sec": float(s["duration_sec"]),
                    "raw_duration_sec": s.get("raw_duration_sec"),
                    "audio_path": str(audio),
                    "unread_latin": list(s.get("unread_latin") or []),
                    "misread_hints": [h.get("word") for h in s.get("misread_hints") or []],
                })
            project = payload.get("project") or {}
            return {
                "engine": chosen,
                "speed": project.get("speed"),
                "voice_id": project.get("voice_id"),
                "scenes": measured,
            }
        finally:
            try:
                client.delete(f"/api/projects/{project_id}")
            except httpx.HTTPError as exc:
                log(f"[tts] 프로젝트 정리 실패 project={project_id}: {exc}")
