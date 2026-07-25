## SUMMARY
VoiceRecorder는 내레이션 스크립트를 씬 단위로 분할해 한국어 음성을 합성하고 병합 mp3+SRT로 내보내는 FastAPI+React 웹앱이다. TTS는 전부 로컬 모델 3종으로, 주엔진 Chatterbox Multilingual(Resemble AI, MIT, GPU+CPU 폴백, 참조음성 3~10초 보이스클로닝), 사이드카 MeloTTS(CPU)와 CosyVoice3-0.5B(CPU, 별도 venv subprocess 워커)이며 셋 다 한국어를 지원한다. 속도 조절은 모델 재합성 없이 ffmpeg atempo(0.5~2.0)로 후처리하고, 화자는 업로드한 참조 wav(voice_id)로 지정한다. HTTP API는 이미 존재한다 — 개발 시 :8000, 운영은 scripts/serve.sh가 :8177(VOICEREC_PORT)로 상시 구동하며 HEAXHub 연합(HWAXPortal services.yaml)에 등록되어 재부팅 시 자동 기동된다. 인증·CORS는 전혀 없다(내부망 전제). 합성은 비동기 작업 큐(단일 워커 스레드)로 202+job_id를 받고 GET /api/jobs/{id}로 폴링한다. 합성 길이는 엔진이 초 단위로 반환해 씬별 raw_duration_sec/duration_sec으로 DB에 저장되고, GET /api/projects/{id} 응답에 씬별 duration_sec·start_sec·end_sec·drift_sec과 전체 total_sec이 포함되므로 영상 씬 동기화에 바로 쓸 수 있다. 스크립트에 (0:00–0:08) 타임코드를 넣으면 POST fit-timecode가 배속·무음으로 자동 정렬까지 해 준다. 단, 단발성 text→wav 엔드포인트는 없어 프로젝트/씬/잡 플로우를 타야 한다.

## KEY_FACTS
- TTS 엔진 3종 모두 로컬 실행(클라우드 API 없음): chatterbox(주엔진, GPU cuda/CPU 자동 폴백, 24kHz), melo(CPU 사이드카, 44.1kHz), cosyvoice(CPU 사이드카, 24kHz) — 레지스트리 /home/koopark/claude/VoiceRecorder/backend/app/tts/registry.py
- Chatterbox Multilingual: /home/koopark/claude/VoiceRecorder/backend/app/tts/chatterbox_engine.py — chatterbox-tts==0.1.7, 한국어 포함 23개 언어, 참조음성 3~10초 보이스클로닝, 합성 파라미터 exaggeration/cfg_weight/temperature, VRAM 부족 시 CPU 자동 폴백
- CosyVoice3: FunAudioLLM/Fun-CosyVoice3-0.5B-2512 가중치, /home/koopark/claude/VoiceRecorder/scripts/cosy_worker.py 상주 워커(stdin/stdout JSON), prompt_text가 있으면 add_zero_shot_spk로 화자 고정(씬 간 톤 일관성)
- 속도(0.5~2.0배)는 모델이 아니라 ffmpeg atempo 후처리 — /home/koopark/claude/VoiceRecorder/backend/app/audio.py, 원본 wav(raw/)를 보존하고 재렌더링만 하므로 속도 변경에 GPU 재합성 불필요
- 합성 길이(초): TTSEngine.synthesize()가 float 초를 반환(base.py), ffprobe probe_duration으로 실측, 씬별 raw_duration_sec(속도 적용 전)/duration_sec(적용 후)이 SQLite에 저장되고 GET /api/projects/{id} 응답에 씬별 duration_sec·start_sec·end_sec·drift_sec·total_sec 포함
- HTTP API 이미 존재: FastAPI, /home/koopark/claude/VoiceRecorder/backend/app/main.py — 인증·API키·CORS 미들웨어 전혀 없음(내부망 전제)
- 운영 포트 8177: /home/koopark/claude/VoiceRecorder/scripts/serve.sh 가 uvicorn --host 0.0.0.0 --port ${VOICEREC_PORT:-8177} 로 상시 구동, HWAXPortal/infra/services.yaml에 voice-recorder(tier 10, health http://localhost:8177/api/health)로 등록되어 재부팅 자동 기동
- 합성은 비동기: POST /api/projects/{id}/synthesize → 202 {job_id} → GET /api/jobs/{job_id} 폴링(status: queued/running/done/error, done/total 진행률) — 워커 스레드 1개(GPU 1장 전제)로 직렬 처리, /home/koopark/claude/VoiceRecorder/backend/app/jobs.py
- 출력 포맷: 씬별 wav(16bit PCM, GET /api/projects/{id}/scenes/{sid}/audio), 최종 병합은 mp3(기본 192k)+SRT(GET /api/projects/{id}/export/audio | /srt)
- 타임코드 자동 동기화: 스크립트에 '01 제목 (0:00–0:08) "본문"' 형식으로 넣으면 씬별 target_start/end_sec 파싱, POST /api/projects/{id}/fit-timecode {max_speed} 가 짧으면 무음·길면 배속으로 슬롯에 자동 정렬(synth.py fit_to_timecode)
- 한국어 품질 장치: 숫자 한국어 낭독(textnorm.py, read_numbers), 발음 사전 API(/api/dictionary, 예: HWAX→에이치왁스)
- 환경: Python 3.12 + Node 20 + ffmpeg 필수, venv 3개(backend/.venv torch-cu130+chatterbox, .venv-cosy, .venv-melo 합계 ~15GB), 모델 가중치 ~13GB는 var/models(HF 캐시), GPU는 선택(있으면 Chatterbox 가속, 없거나 OOM이면 CPU 폴백), 오프라인 구동 지원(HF_HUB_OFFLINE=1)
- 설정 상속 구조: 프로젝트 기본값(engine/language/voice_id/speed/gap_ms/exaggeration/cfg_weight/temperature) 위에 씬별 override, ScenePatch.reset 리스트로 기본값 복귀 — /home/koopark/claude/VoiceRecorder/backend/app/synth.py effective_params()
- 참조 음성 등록: POST /api/voices (multipart: name, transcript, file ≤20MB, 3초 이상) → voice_id, transcript는 CosyVoice 화자 고정에 필요

## INTEGRATION_CONTRACT
- 베이스 URL: http://localhost:8177 (운영, scripts/serve.sh · VOICEREC_PORT로 변경 가능) 또는 개발 :8000. 포탈 경유 시 /apps/voice_recorder 프리픽스(uvicorn --root-path). 인증 없음 — 서버 간 내부 호출 전제
- 합성 플로우: (1) POST /api/projects {title, raw_script, engine:"chatterbox", language:"ko", voice_id?, speed, gap_ms, exaggeration, cfg_weight, temperature} → 프로젝트+씬 목록 (2) POST /api/projects/{id}/synthesize {scene_ids?|force} → 202 {job_id, scene_count} (3) GET /api/jobs/{job_id} 를 status==done까지 폴링 (4) GET /api/projects/{id} 로 씬별 duration_sec 수신 (5) 씬별 wav: GET /api/projects/{id}/scenes/{sid}/audio
- 씬 길이 동기화: WebDesignAgents가 씬 원고를 '01 제목 (0:00–0:08) "본문"' 형식으로 raw_script를 구성해 넘기면 타임코드가 자동 파싱되고, POST /api/projects/{id}/fit-timecode {max_speed:2.0} 호출로 씬 오디오를 영상 씬 슬롯에 자동 정렬(부족분 무음, 초과분 배속, 불가능 씬은 over_budget 리포트로 반환)
- 길이 조회 계약: GET /api/projects/{id} 응답의 scenes[].duration_sec(최종)·raw_duration_sec(원속도)·start_sec/end_sec(타임라인 절대시각)·drift_sec(목표 대비 오차)와 total_sec — 영상 렌더러가 이 값으로 씬 컷 길이를 결정하면 된다
- 최종 산출물: POST /api/projects/{id}/export → job 완료 후 GET /api/projects/{id}/export/audio(병합 mp3, 씬 간 무음 gap 포함) + GET /api/projects/{id}/export/srt(자막, 씬 텍스트+타임코드) — SRT를 영상 자막 트랙으로 그대로 사용 가능
- 화자(내레이터) 설정: 사전에 POST /api/voices 로 참조 wav(3~10초)+전사(transcript)를 등록해 voice_id 획득 → 프로젝트 생성 시 voice_id로 지정. 씬별로 다른 화자도 PATCH /api/projects/{id}/scenes/{sid} {voice_id}로 가능
- 속도만 재조정 시 재합성 불필요: PATCH /api/projects/{id} {speed} 또는 씬별 PATCH {speed} — ffmpeg 재렌더링만 일어나 수 초 내 완료, duration_sec 즉시 갱신
- 엔진 가용성 사전 확인: GET /api/engines 로 engines[].available/detail/device를 확인 후 사용 가능한 engine id(chatterbox/melo/cosyvoice)를 선택. GET /api/health 로 생존 확인
- 텍스트만 미리 검증: POST /api/scripts/parse {raw_script} (저장 없음)로 씬 분할·타임코드 파싱 결과를 미리 확인 가능

## GAPS
- 단발성 stateless TTS 엔드포인트(text→wav 동기 반환) 부재 — 반드시 프로젝트 생성→합성 잡→폴링 플로우를 타야 한다. WebDesignAgents가 간단 호출을 원하면 VoiceRecorder 쪽에 POST /api/tts 같은 원샷 엔드포인트 추가가 필요
- 인증·API키 전무 — localhost/내부망 밖으로 노출하려면 네트워크 레벨 보호 또는 인증 미들웨어 추가 필요
- 잡 완료 웹훅/콜백 없음 — 폴링 전용. 대량 배치 연동 시 콜백 URL 파라미터 추가가 있으면 효율적
- 합성 워커 스레드 1개(GPU 1장 전제)로 전 요청 직렬 처리 — WebDesignAgents가 영상 여러 편을 동시 생성하면 대기열이 길어지며 우선순위 개념 없음
- CORS 미들웨어 없음 — 브라우저에서 타 오리진 직접 fetch 불가(서버-서버 호출은 무관)
- 씬별 오디오는 wav만 제공(mp3는 병합 익스포트 전용) — 씬 단위 mp3가 필요하면 WebDesignAgents 쪽에서 변환하거나 API 확장 필요
- 무거운 로컬 의존성: venv 3개(~15GB)+모델 ~13GB+ffmpeg가 같은 호스트에 설치되어 있어야 하며, 컨테이너/SIF 표준 패키징이 안 되는 앱이라 다른 서버로 이식하려면 setup-backend.sh/setup-cosy.sh/setup-melo.sh+Drive 모델 파이프라인을 그대로 재현해야 함
- 프로젝트/씬 데이터가 SQLite(var/data/voicerecorder.db)에 계속 쌓임 — 영상 생성 후 임시 프로젝트를 지우는 정리(DELETE /api/projects/{id}) 책임은 호출자 몫