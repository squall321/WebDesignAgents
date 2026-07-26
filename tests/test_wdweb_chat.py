# wdweb 대화형 제작 패널 테스트 — FakeLLM 주입으로 액션 적용/취소/거부/이력/503 검증
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from wdcore.config import get_settings
from wdllm.client import ChatResult, LLMError

REPO_ROOT = Path(__file__).resolve().parents[1]
REPORT_SAMPLE = REPO_ROOT / "examples" / "reportarchive" / "report_sample.json"


class ScriptedLLM:
    """정해진 payload(dict)를 차례로 JSON 문자열로 돌려주는 결정적 챗 LLM."""

    def __init__(self, payloads: list[dict]) -> None:
        self.payloads = list(payloads)
        self.calls = 0

    def chat(self, messages, **kwargs) -> ChatResult:  # noqa: ARG002 — 인터페이스 호환
        self.calls += 1
        content = json.dumps(self.payloads.pop(0), ensure_ascii=False)
        return ChatResult(
            content=content, reasoning=None, model="scripted", usage=None,
            raw={"scripted": True}, finish_reason="stop",
        )


class DownLLM:
    """vLLM 다운 시뮬레이션 — chat 호출 즉시 LLMError."""

    def chat(self, messages, **kwargs) -> ChatResult:  # noqa: ARG002
        raise LLMError("openai 호환 호출 실패: connection refused (vLLM 다운)")


@pytest.fixture(scope="module")
def chat_env(tmp_path_factory: pytest.TempPathFactory):
    """모듈 공유 데이터 루트 — 파이프라인 1회 실행을 여러 테스트가 공유한다."""
    data = tmp_path_factory.mktemp("chat-data")
    old = os.environ.get("WDA_DATA_DIR")
    os.environ["WDA_DATA_DIR"] = str(data)
    get_settings.cache_clear()
    yield data
    if old is None:
        os.environ.pop("WDA_DATA_DIR", None)
    else:
        os.environ["WDA_DATA_DIR"] = old
    get_settings.cache_clear()


@pytest.fixture(scope="module")
def client(chat_env: Path) -> TestClient:
    from wdweb.app import app

    return TestClient(app)


@pytest.fixture(scope="module")
def built_run(client: TestClient) -> dict:
    """report_sample 로 파이프라인을 끝까지 돌린 실행 1건 (scenario+build 완료)."""
    report = json.loads(REPORT_SAMPLE.read_text(encoding="utf-8"))
    res = client.post("/api/runs", json={"report_json": report, "slug": "chat-e2e"})
    assert res.status_code == 202
    run_id = res.json()["data"]["run_id"]
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        run = client.get(f"/api/runs/{run_id}").json()["data"]
        if run["status"] in ("done", "failed"):
            break
        time.sleep(0.3)
    assert run["status"] == "done", f"파이프라인 실패: {run.get('error')}"
    return run


def _post_chat(client: TestClient, run_id: str, message: str):
    return client.post(f"/api/runs/{run_id}/chat", json={"message": message})


def _scenario(chat_env: Path, run_id: str) -> dict:
    path = chat_env / "pipeline" / run_id / "scenario.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _scene(doc: dict, name: str) -> dict:
    return next(s for s in doc["scenes"] if s["name"] == name)


# ── ① set_dur — 반영·검증·재빌드 ────────────────────────────────────────────


def test_set_dur_applies_and_rebuilds(
    client: TestClient, chat_env: Path, built_run: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wdweb import chat as chatmod

    monkeypatch.setattr(chatmod, "get_llm", lambda: ScriptedLLM([{
        "reply": "절차 씬 길이를 14초로 줄였습니다.",
        "actions": [{"type": "set_dur", "scene": "절차", "dur": 14}],
    }]))
    run_id = built_run["run_id"]
    build_dir = Path(built_run["build_dir"])
    old_dur = _scene(_scenario(chat_env, run_id), "절차")["dur"]
    assert old_dur == 18  # process nat_default

    res = _post_chat(client, run_id, "절차 씬 길이를 14초로 줄여줘")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["rebuilt"] is True
    assert any("dur" in a and "14" in a for a in data["applied"]), data["applied"]
    assert "14" in data["reply"]

    # scenario.json 반영 + stills 재클램프 (기존 17.0 은 14 초과)
    scene = _scene(_scenario(chat_env, run_id), "절차")
    assert scene["dur"] == 14
    assert scene["stills"] and all(t <= 14 for t in scene["stills"])

    # 빌드 산출물 갱신 — build/scene-data.json 과 index.html(OM_SCENES) 모두
    built_doc = json.loads((build_dir / "scene-data.json").read_text(encoding="utf-8"))
    assert _scene(built_doc, "절차")["dur"] == 14
    # OM_SCENES 는 JS 문자열 리터럴로 주입 — 내부 따옴표가 \" 로 이스케이프된다
    assert '\\"dur\\":14' in (build_dir / "index.html").read_text(encoding="utf-8")

    # 원장 요약 갱신
    run = client.get(f"/api/runs/{run_id}").json()["data"]
    total = round(sum(s["dur"] for s in _scenario(chat_env, run_id)["scenes"]), 3)
    assert run["scenario_summary"]["total_dur"] == pytest.approx(total)


# ── ② 스키마 위반(dur 400) — 적용 취소 + reply 오류 ─────────────────────────


def test_invalid_dur_reverts(
    client: TestClient, chat_env: Path, built_run: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wdweb import chat as chatmod

    monkeypatch.setattr(chatmod, "get_llm", lambda: ScriptedLLM([{
        "reply": "절차 씬을 400초로 늘립니다.",
        "actions": [{"type": "set_dur", "scene": "절차", "dur": 400}],
    }]))
    run_id = built_run["run_id"]
    before = json.dumps(_scenario(chat_env, run_id), sort_keys=True)

    res = _post_chat(client, run_id, "절차 씬을 400초로 늘려줘")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["applied"] == []
    assert data["rebuilt"] is False
    assert "취소" in data["reply"]  # 검증 실패 사유가 reply 에 병합된다

    # 시나리오는 그대로 (전체 취소)
    after = json.dumps(_scenario(chat_env, run_id), sort_keys=True)
    assert after == before


# ── ③ 존재하지 않는 tpl — 거부 ──────────────────────────────────────────────


def test_unknown_tpl_rejected(
    client: TestClient, chat_env: Path, built_run: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wdweb import chat as chatmod

    monkeypatch.setattr(chatmod, "get_llm", lambda: ScriptedLLM([{
        "reply": "템플릿을 교체합니다.",
        "actions": [{"type": "set_tpl", "scene": "절차", "tpl": "megachart@1"}],
    }]))
    run_id = built_run["run_id"]
    before = json.dumps(_scenario(chat_env, run_id), sort_keys=True)

    res = _post_chat(client, run_id, "절차 씬을 megachart 템플릿으로 바꿔줘")
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["applied"] == []
    assert data["rebuilt"] is False
    assert "megachart" in data["reply"]  # 거부 사유 병합
    assert json.dumps(_scenario(chat_env, run_id), sort_keys=True) == before


# ── ④ 이력 누적·복원 ────────────────────────────────────────────────────────


def test_history_accumulates_and_restores(
    client: TestClient, built_run: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wdweb import chat as chatmod

    run_id = built_run["run_id"]
    hist0 = client.get(f"/api/runs/{run_id}/chat").json()["data"]["chat"]
    assert len(hist0) >= 1  # 앞선 테스트들의 대화가 누적돼 있다

    monkeypatch.setattr(chatmod, "get_llm", lambda: ScriptedLLM([{
        "reply": "무엇을 도와드릴까요?", "actions": [],
    }]))
    res = _post_chat(client, run_id, "안녕")
    assert res.status_code == 200

    hist1 = client.get(f"/api/runs/{run_id}/chat").json()["data"]["chat"]
    assert len(hist1) == len(hist0) + 2  # user + assistant 1턴 누적
    assert hist1[-2]["role"] == "user" and hist1[-2]["content"] == "안녕"
    assert hist1[-1]["role"] == "assistant"
    assert "도와드릴까요" in hist1[-1]["content"]
    assert hist1[-1]["actions"] == [] and hist1[-1]["rebuilt"] is False
    assert hist1[: len(hist0)] == hist0  # 기존 이력 보존 (복원 계약)


# ── ⑤ LLM 불통 — 503 봉투 ──────────────────────────────────────────────────


def test_llm_down_503(
    client: TestClient, built_run: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    from wdweb import chat as chatmod

    run_id = built_run["run_id"]
    hist0 = client.get(f"/api/runs/{run_id}/chat").json()["data"]["chat"]

    monkeypatch.setattr(chatmod, "get_llm", lambda: DownLLM())
    res = _post_chat(client, run_id, "아무거나 바꿔줘")
    assert res.status_code == 503
    body = res.json()
    assert body["success"] is False
    assert "LLM" in body["message"] and "vLLM" in body["message"]

    # 실패한 턴은 이력에 남지 않는다
    hist1 = client.get(f"/api/runs/{run_id}/chat").json()["data"]["chat"]
    assert hist1 == hist0


# ── 전제 조건·요청 형식 ─────────────────────────────────────────────────────


def test_chat_requires_scenario_stage(client: TestClient, chat_env: Path) -> None:
    from wdweb import runs as runledger

    run_id = "wr-20260726-000000-chat"
    now = "2026-07-26T00:00:00+00:00"
    runledger.write_run({
        "run_id": run_id, "slug": run_id, "status": "failed",
        "stages": [
            {"stage": s, "status": "pending", "error": None, "output": None}
            for s in runledger.STAGES
        ],
        "scenario_summary": None, "build_dir": None, "entry": None,
        "render": None, "qa": None, "error": "ingest 실패",
        "created_at": now, "updated_at": now,
    })
    res = _post_chat(client, run_id, "고쳐줘")
    assert res.status_code == 409
    assert res.json()["success"] is False


def test_chat_bad_body(client: TestClient, built_run: dict) -> None:
    run_id = built_run["run_id"]
    assert client.post(f"/api/runs/{run_id}/chat", json={}).status_code == 400
    assert client.post(f"/api/runs/{run_id}/chat", json={"message": "  "}).status_code == 400
    # 미지의 run 은 404 봉투
    assert client.post("/api/runs/no-such/chat", json={"message": "x"}).status_code == 404
