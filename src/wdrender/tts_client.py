# VoiceRecorder(:8177) 프로젝트/씬 플로우로 시나리오 내레이션을 합성하는 HTTP 클라이언트
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASE_URL = "http://localhost:8177"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "tts_check"


def resolve_base_url(base_url: str | None = None) -> str:
    """WDA_TTS_BASE_URL 환경변수 → 인자 → 기본 localhost:8177 순으로 결정한다."""
    return (base_url or os.environ.get("WDA_TTS_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


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
    with httpx.Client(base_url=resolve_base_url(base_url), timeout=60.0) as client:
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

    with httpx.Client(base_url=resolve_base_url(base_url), timeout=60.0) as client:
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
