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

---

# 2차 빌드 부록 (wdmcp · wdpipeline · wdllm · wdqa)

## 1차 빌드 완료 자산 (자유롭게 import 하라 — 수정은 금지)

- `wdcore` — 회의 엔진·모델·레지스트리. 핵심 API: `wdcore.meetings.engine.MeetingEngine`, `wdcore.meetings.templates.MEETING_TEMPLATES`, `wdcore.meetings.store`, `wdcore.registry.registry.load_registry()` (→ .personas 14인 / .cards 8장 / .issues), `wdcore.models.scenario.ScenarioDoc`(+`om_scenes_json`·`check_om_scenes_budget`), `wdcore.config.get_settings()` (WDA_ 접두)
- `wdrender` — `server.py`(정적 서빙 컨텍스트 매니저), `page_session.py`(3단계 대기 + sync seek), `exporter_video.export_video(...)`, `exporter_pptx.export_pptx(...)`, `configs/render.toml`
- `web/templates/` — `window.OMX.templates` 7종(각각 `.schedule(data)`·`.nat`), `window.OMX.metaphors` 9종, `web/tokens/loader.jsx`(`OMX.themes.load`), 테마 `web/tokens/hwax-blue.json`
- `modules/scene-templates/{opening,problem,concept,process,differentiator,proof,closing}/` — `schema.json`(x-read·maxLength), `module.yaml`(id=`tpl.*`), `fixtures/{min,typical,max}.json`, `preview.html`
- `personas/` — 14인 + 카드 8장. 카드 sources는 평문 문자열 허용(모델이 승격), `related_experts`/`related_personas` 양쪽 표기 허용

## 엔트리 생성 규약 (P4 — 반드시 준수)

- 로드 순서: `runtime/animations-v2.jsx` → `tokens/loader.jsx` → `templates/omx-metaphors.jsx` → `templates/omx-templates.jsx` → 프로젝트 `scenes.jsx` (x-import 또는 script 순차)
- **const 충돌 규약**: babel standalone 전역 환경에서 엔진 최상위 선언과 이름이 겹치면 안 된다. 프로젝트 scenes.jsx 는 `const SceneRoot = window.SceneStage` 처럼 비충돌 별칭으로 참조 (preview.html 패턴 참조)
- `window.OM_SCENES` 는 vanilla 인라인 스크립트 JSON 문자열 리터럴, 주입 축약형(name/dur/nat/stills/tpl만, ≤16KB — `check_om_scenes_budget` 사용)
- vendor 오프라인 주입 지점: `wdrender.page_session` 이 `window.__resources` 로 web/vendor 사본을 주입한다

## 모듈 간 계약 (병렬 작업 — 이 시그니처를 벗어나지 마라)

```python
# wdpipeline (B2 소유)
wdpipeline.ingest.ingest_report_file(path: Path, assets_dir: Path | None = None) -> dict   # report.norm.json 딕셔너리
wdpipeline.fragmentize.fragmentize(norm: dict) -> list[dict]                               # fragments (frag_id/type/text/source/confidence)
wdpipeline.scenario.assemble_demo_scenario(norm: dict, fragments: list[dict]) -> ScenarioDoc  # 규칙 기반(LLM 무호출) 데모 조립
wdpipeline.scenario.validate_scenario(doc: ScenarioDoc, modules_root: Path = Path("modules")) -> list[str]  # 오류 목록(빈 리스트=통과)
wdpipeline.build.build_render_package(doc: ScenarioDoc, out_dir: Path) -> Path             # build/{slug}/ 생성, 엔트리 경로 반환

# wdqa (B4 소유)
wdqa.gates.run_gates(build_dir: Path, scenario: dict | None = None, gates: list[str] | None = None) -> dict
# 반환: {"passed": bool, "results": [{"gate", "rule", "scene", "severity", "detail"}]}
```

- wdmcp(B1)는 위 함수를 **지연 import** 로 호출한다(병렬 작업 중 미완성일 수 있음 — import 실패 시 해당 툴은 error 봉투로 응답하고 테스트는 skip).
- 파일 산출 규약: 파이프라인 단계 산출물은 `data/pipeline/{run_id}/` (report.norm.json, fragments.json, scenario.json), 빌드는 `data/build/{slug}/`, 렌더는 `data/renders/{slug}/`.
