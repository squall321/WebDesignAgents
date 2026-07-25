# 구현 에이전트 공용 브리프

모든 구현 에이전트는 작업 전에 이 문서와 `PLAN.md`(자기 담당 절)를 읽는다.

## 절대 규칙

1. **소유 영역 밖의 파일을 쓰지 마라.** 병렬 에이전트가 동시에 작업 중이다. 읽기는 자유.
2. **가상환경** — 파이썬 실행은 반드시 `uv run ...` 또는 `.venv/bin/python`. 전역 pip 금지. 의존성 추가 필요 시 pyproject.toml을 고치지 말고 known_issues로 보고.
3. **파일 헤더** — 새 소스 파일 첫 줄(디렉티브 제외)에 역할을 한 줄 한국어 주석으로.
4. **git 커밋 금지** — 커밋은 오케스트레이터가 리뷰 후 수행.
5. **검증 필수** — 만든 것은 실행해서 확인한다. 테스트는 `tests/test_<담당영역>*.py`로 작성하고 `uv run pytest tests/test_<담당영역>* -x -q`로 통과 확인.
6. **엔진 불가침** — `web/runtime/`의 support.js·animations-v2.jsx는 절대 수정 금지. window 전역 계약만 소비.
7. PLAN.md·checklist.md·context-notes.md·pyproject.toml 수정 금지.

## 핵심 참조 자료

| 자료 | 경로 |
| --- | --- |
| 전체 계획 | `PLAN.md` |
| 렌더 엔진 계약 분석 (seek 프로토콜·export 조건·모듈 후보) | `docs/analysis/engine-analysis.md` |
| ExpertAgents 구조 분석 (expert.yaml 포맷·회의 엔진·MCP 봉투) | `docs/analysis/expertagents-analysis.md` |
| 씬 작성 실물 예제 | `examples/hwax_intro/hwax-scenes.jsx` |
| 시나리오 방법론 (씬 타입·스키마·시각 은유) | `examples/hwax_intro/시나리오-구성-방법론.md` |
| ExpertAgents 원본 코드 | `/home/koopark/claude/ExpertAgents/src/` |
| VoiceRecorder API 계약 | `docs/analysis/voicerecorder-api.md` |
| GLM-5-2 호출 규약 | `docs/analysis/glm-client-rules.md` |

## 환경 (검증 완료)

- Python 3.13.11 (.venv, uv). 설치됨: pydantic v2, pydantic-settings, structlog, PyYAML, typer, httpx, playwright(1.61)+chromium 149, python-pptx, pillow, mcp, pytest.
- ffmpeg 4.4.2 (`ffmpeg` 시스템 명령).
- `web/vendor/` — react 18.3.1 UMD·react-dom 18.3.1 UMD·babel standalone 7.29.0 로컬 사본.
- 네트워크 가용 (unpkg·jsdelivr 접근 가능). 오프라인 대비는 `window.__resources` 주입 지점만 남겨두면 됨.

## 최종 출력 (구조화)

각 에이전트는 {summary, files, verification, known_issues}를 반환한다. verification에는 실제 실행한 명령과 결과 수치를 쓴다. 실행 안 한 것을 했다고 쓰지 마라.
