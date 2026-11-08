# Tasks — 2026-11-08-feature-standalone-voice-endpoints

**Status:** done (2026-11-08, by Shubham Halder)

**Spec:** specs/002-standalone-voice-endpoints/spec.md
**Covers:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11

## Goal

Expose standalone REST endpoints for Speech-to-Text (`POST /stt/transcribe`), Text-to-Speech (`POST /tts/synthesize`), and LLM completions (`POST /llm/chat`) under FastAPI, supporting both direct parameters and assistant inheritance without breaking the control/agent image boundary.

## Success criteria

- `POST /stt/transcribe` accepts audio uploads up to 25 MB and returns text transcription, detected language, and duration.
- `POST /tts/synthesize` accepts text up to 5,000 characters and streams binary audio (`audio/wav` or `audio/mpeg`).
- `POST /llm/chat` returns JSON chat completions or SSE streams with token usage.
- All endpoints authenticate via standard bearer key, reject unowned assistants with 404, validate models against existing allowlists, and record usage in `UsageRecord`.
- Control image dependencies remain clean: no `livekit-agents` plugins imported in `src/api/` or `src/services/`.
- Full unit test suite passes: `uv run python -m unittest discover -s tests`.
- Ruff linting clean: `uvx ruff check src/api/routes/{stt,tts,llm}.py src/services/{stt,tts,llm}/`.
- Public documentation and OpenAPI schemas updated, passing `uv run mkdocs build --strict`.

## Skills applied

- core-be-workflow, core-be-specify, core-be-clarify, core-be-plan, core-be-tasks, core-be-constitution, core-be-analyze
- core-be-coding-standards, core-be-write-tests

## Steps

- [x] 1. `setup` Create test scaffolding in `tests/test_standalone_voice_endpoints.py` with mock HTTP servers/adapters and test fixtures. Verify: `uv run python -m unittest tests/test_standalone_voice_endpoints.py -v`.
- [x] 2. `AC-2` Test first: unauthenticated requests to `/stt/transcribe`, `/tts/synthesize`, `/llm/chat` return HTTP 401. Implement router skeletons and wire `get_current_user`.
- [x] 3. `AC-10` Test first: invalid or unsupported provider/model names return HTTP 422 using allowlists in `src/core/model_support/`. Create Pydantic schemas in `src/api/models/api_schemas/standalone/`.
- [x] 4. `AC-8` Test first: valid `assistant_id` loads stored STT/TTS/LLM config and allows explicit parameter overrides. Add helper `resolve_stage_config(assistant_id, explicit_config, current_user)` in `src/api/routes/standalone_helper.py`.
- [x] 5. `AC-9` Test first: non-existent or foreign user's `assistant_id` returns HTTP 404.
- [x] 6. `AC-3` Test first: audio payload > 25 MB returns HTTP 413; invalid audio returns HTTP 422. Implement upload validation in `/stt/transcribe`.
- [x] 7. `AC-1` Test first: valid audio file returns transcription, language, and duration. Implement `src/services/stt/client.py` using `httpx` and complete `src/api/routes/stt.py`.
- [x] 8. `AC-5` Test first: empty text or text > 5,000 characters returns HTTP 422 in `/tts/synthesize`.
- [x] 9. `AC-4` Test first: valid text returns audio binary stream with correct headers. Implement `src/services/tts/client.py` using `httpx` and complete `src/api/routes/tts.py`.
- [x] 10. `AC-6` Test first: valid chat messages with `stream=false` return JSON assistant message and token usage. Implement `src/services/llm/client.py` and non-streaming handler in `src/api/routes/llm.py`.
- [x] 11. `AC-7` Test first: chat request with `stream=true` returns `text/event-stream` SSE chunks ending with `[DONE]`. Implement streaming handler in `src/api/routes/llm.py`.
- [x] 12. `AC-11` Test first: successful STT, TTS, and LLM requests create a `UsageRecord` with `call_type="standalone_api"` and correct duration/token counts. Add usage logging helper.
- [x] 13. `setup` Register `/stt`, `/tts`, and `/llm` routers in `src/api/server.py`.
- [x] 14. `docs` Document new endpoints in `docs/api/stt.md`, `docs/api/tts.md`, `docs/api/llm.md`, update `mkdocs.yml` nav, and update `README.md`. Verify with `uv run mkdocs build --strict`.
- [x] 15. `converge` Run `core-be-converge` and verify the whole test suite: `uv run python -m unittest discover -s tests`.

## Files expected to change

| Path | Change |
|------|--------|
| `src/api/routes/stt.py` | New: `POST /stt/transcribe` route |
| `src/api/routes/tts.py` | New: `POST /tts/synthesize` route |
| `src/api/routes/llm.py` | New: `POST /llm/chat` route |
| `src/api/models/api_schemas/standalone/` | New: request and response schemas for STT, TTS, LLM |
| `src/services/stt/client.py` | New: async HTTP client for Sarvam, Cartesia, OpenAI STT |
| `src/services/tts/client.py` | New: async HTTP client for Cartesia, Sarvam, ElevenLabs TTS |
| `src/services/llm/client.py` | New: async HTTP client for OpenAI & Gemini chat completions/streams |
| `src/api/server.py` | Mount `/stt`, `/tts`, `/llm` routers |
| `tests/test_standalone_voice_endpoints.py` | New: unit and integration tests |
| `docs/api/{stt,tts,llm}.md` | New: user-facing endpoint documentation |
| `mkdocs.yml` | Add new doc pages to `nav:` |

## Design notes

- Direct HTTP client with connection pooling via `httpx.AsyncClient`.
- Pure async streaming for audio synthesis and LLM tokens.
- No LiveKit room or WebRTC session needed.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Memory exhaustion from large audio uploads | Read only up to `MAX_UPLOAD_BYTES + 1` (25 MB) and reject immediately before buffering into memory. |
| Slow upstream provider TTS blocking API server | Stream audio response directly from upstream provider via `StreamingResponse`. |
| Breaking control container isolation | Zero imports from `livekit.plugins.*`; rely strictly on standard HTTP endpoints and `httpx`. |

## Delivery and rollback

- **Blast radius:** New independent endpoints. No impact on existing live call or assistant CRUD endpoints.
- **Rollout:** Deploy updated API server image with new routes.
- **Rollback recipe:** Unmount the 3 routers in `src/api/server.py`.
