# Plan 002 — Standalone voice endpoints (STT, TTS, LLM)

- **Spec:** [spec.md](spec.md)
- **Last changed:** 2026-11-08

## Technical context

- **Language & Runtime:** Python >=3.12 (`pyproject.toml:6`).
- **Framework:** FastAPI >=0.128.6 (`pyproject.toml:8`), Gunicorn >=25.0.3.
- **Datastore:** MongoDB via Motor >=3.3.2 and Beanie ODM >=1.26.0 (`pyproject.toml:10-11`).
- **HTTP Client:** `httpx` >=0.28.0 (`docker/requirements-control.txt:7`).
- **Audio Processing:** PyAV (`av` >=12.0.0, `pyproject.toml:22`).
- **Test Runner:** Python stdlib `unittest` (`AGENTS.md:126`, `uv run python -m unittest discover -s tests`).
- **Deployment Images:** Control image (`docker/Dockerfile.control`) without `livekit-agents` plugins; Agent worker image (`docker/Dockerfile.agent`).

## Constitution check

| # | Principle | Gate question | Answer | Note |
|---|-----------|---------------|--------|------|
| 1 | Test-first | Does every `AC-n` have a test step that runs before its code step? | Yes | Test suite in `tests/test_standalone_voice_endpoints.py` covers AC-1 through AC-11. |
| 2 | Simplicity | Does each new layer or moving part name the risk it removes? | Yes | Uses lightweight direct HTTP service adapters in `src/services/{stt,tts,llm}/` via `httpx`; avoids introducing WebRTC/worker overhead for simple stateless REST operations. |
| 3 | Reuse first | Does the plan list what it reuses and why nothing existing fits for each new piece? | Yes | Reuses `get_current_user` auth, `apiResponse` envelope, `UsageRecord` collection, `MAX_UPLOAD_BYTES` audio size check, and `src/core/model_support/` allowlists. |
| 4 | Security at trust boundaries | Is the control stated for every trust boundary the feature crosses? | Yes | Bearer token auth on every route; 25 MB max upload cap enforced before buffering; text length limit (5,000 chars); provider API keys retrieved from secure settings or encrypted/masked DB fields, never echoed. |
| 5 | Explicit contracts | Does the plan state request, response, every error status, and limits? | Yes | Exact request/response schemas, status codes (200, 401, 404, 413, 422, 502), and size caps detailed in Contracts section. |
| 6 | Observable and reversible | Does the plan name what is logged and give a rollback recipe? | Yes | Request correlation id logged with redacting logger; every transaction records metrics in `UsageRecord`; rollback is a single router unmount. |
| 7 | Docs agree with code | Does the plan list each doc, schema and test that must change with the code? | Yes | Lists `docs/api/`, `README.md`, OpenAPI routes, and `mkdocs.yml`. |
| 8 | Dependency-free model support | Does the plan keep `livekit` and `fastapi` imports out of `src/core/model_support/`? | Yes | All new services and models live in `src/api/` and `src/services/`; `src/core/model_support/` remains dependency-free. |

## Design

### Placement per `AGENTS.md` Project Structure
- Routes:
  - `src/api/routes/stt.py` (mounts `/stt`)
  - `src/api/routes/tts.py` (mounts `/tts`)
  - `src/api/routes/llm.py` (mounts `/llm`)
- Schemas:
  - `src/api/models/api_schemas/standalone/stt_schemas.py`
  - `src/api/models/api_schemas/standalone/tts_schemas.py`
  - `src/api/models/api_schemas/standalone/llm_schemas.py`
- Service Clients:
  - `src/services/stt/client.py` (direct async HTTP client for Sarvam, Cartesia, OpenAI, Deepgram, ElevenLabs)
  - `src/services/tts/client.py` (direct async HTTP client for Cartesia, Sarvam, ElevenLabs, Mistral)
  - `src/services/llm/client.py` (direct async HTTP client for OpenAI and Gemini completions and SSE streams)

### System Design Analysis
1. **Numbers & Latency:**
   - STT: File upload up to 25 MB. Typical 5-second audio processes in <800ms upstream.
   - TTS: Text up to 5,000 characters. Audio streamed back to client via `StreamingResponse` for fast time-to-first-byte.
   - LLM: Streaming SSE token-by-token or buffered JSON response.
2. **Data & Invariants:**
   - Assistant resolution: If `assistant_id` is passed, it MUST belong to `current_user.user_email`. Cross-tenant assistant access returns HTTP 404.
   - Key resolution: If caller's assistant has custom `api_key` in config, use it; otherwise fallback to platform `settings.<PROVIDER>_API_KEY`. Missing key returns HTTP 422 ("Provider API key not configured").
3. **Concurrency & Limits:**
   - Handled concurrently by async FastAPI event loop. No worker lock or SIP concurrency limit consumed.
4. **Failure Modes & Retries:**
   - Upstream timeouts or 5xx from vendor APIs return HTTP 502 with structured message.
   - Upstream 4xx authentication/quota errors logged with redacted credentials and returned as HTTP 502.
5. **Observability:**
   - Structured logs with `logger.info` / `logger.error` using `redact_text`.
   - On completion, an entry is added to `UsageRecord` with duration, tokens, and model details.

## Data model

Reuses existing `UsageRecord` collection (`src/core/db/db_schemas.py`):
- `call_type`: `"standalone_api"`
- `call_id`: `f"req_{uuid.uuid4().hex[:12]}"`
- `user_email`: caller's authenticated email
- `provider`: resolved provider string
- `model`: resolved model string
- `duration_seconds`: audio duration (STT/TTS)
- `prompt_tokens`, `completion_tokens`, `total_tokens`: token counts (LLM)

No new MongoDB collection required (Principle 2: Simplicity).

## Contracts

### STT: `POST /stt/transcribe` (AC-1, AC-2, AC-3, AC-8, AC-9, AC-10)
- Request: `multipart/form-data`
  - `file`: `UploadFile` (required, max 25 MB)
  - `assistant_id`: `Optional[str]`
  - `provider`: `Optional[str]` (default: `"sarvam"`)
  - `model`: `Optional[str]` (default: `"saaras:v3"`)
  - `language`: `Optional[str]` (default: `"en-US"`)
- Response: 200 OK
  ```json
  {
    "status": "success",
    "data": {
      "text": "Transcription result",
      "language": "en",
      "duration_seconds": 2.4,
      "provider": "sarvam",
      "model": "saaras:v3"
    }
  }
  ```

### TTS: `POST /tts/synthesize` (AC-2, AC-4, AC-5, AC-8, AC-9, AC-10)
- Request: `application/json`
  ```json
  {
    "text": "Hello world",
    "assistant_id": "optional-uuid",
    "provider": "cartesia",
    "model": "sonic-3",
    "voice": "optional-voice-id",
    "language": "en"
  }
  ```
- Response: 200 OK (`StreamingResponse`, media type `audio/wav` or `audio/mpeg`)

### LLM: `POST /llm/chat` (AC-2, AC-6, AC-7, AC-8, AC-9, AC-10)
- Request: `application/json`
  ```json
  {
    "messages": [{"role": "user", "content": "Hello"}],
    "assistant_id": "optional-uuid",
    "provider": "openai",
    "model": "gpt-5.4",
    "temperature": 0.7,
    "stream": false
  }
  ```
- Response: 200 OK (JSON when `stream=false`; `text/event-stream` when `stream=true`)

## Research decisions

| Choice | Options compared | Picked | Why |
|--------|------------------|--------|-----|
| Execution layer | Direct `httpx` in API server vs Dispatch to LiveKit worker | Direct `httpx` in API server | Preserves separation of control container from LiveKit plugins (Principle 8); zero worker queue latency; stateless. |
| Parameter resolution | Pure direct params vs Pure assistant reference vs Hybrid | Hybrid | Maximizes convenience: callers with configured assistants don't repeat voice/model IDs, while one-off scripts can run without an assistant. |
| Billing & Accounting | Separate `ApiUsage` collection vs Unified `UsageRecord` | Unified `UsageRecord` | Existing analytics, billing aggregation, and dashboards already read `UsageRecord`. Setting `call_type="standalone_api"` keeps everything unified. |

## Complexity tracking

| Violation or extra moving part | Why needed | Simpler option rejected, and why |
|--------------------------------|------------|-----------------------------------|
| Direct REST service clients in `src/services/` | LiveKit plugins cannot be imported into the control image (`requirements-control.txt`) | Importing `livekit.plugins` in FastAPI would break the lean control container and violate Principle 8. |

## Rollout and rollback

- **Blast radius:** Zero impact on existing `/assistant`, `/call`, SIP dispatchers, or LiveKit workers. These are three new additive endpoint routers.
- **Rollout:** Add routers to `src/api/server.py`.
- **Rollback recipe:** Comment out `app.include_router(stt_router)`, `app.include_router(tts_router)`, and `app.include_router(llm_router)` in `src/api/server.py` and redeploy.

## Change log

| Date | Change | Caused by |
|------|--------|-----------|
| 2026-11-08 | Created | AC-1 through AC-11 |


## Change log (delta) — 2026-11-08

- Provider API key placement changed from request body/form field to `X-Provider-API-Key` HTTP header. AC-10 related.

## Delta — Provider API key placement

- Read via FastAPI `Header(default=None, alias="X-Provider-API-Key")` on `/stt/transcribe`, `/tts/synthesize`, `/llm/chat`.
- Thread as `explicit_api_key` into `resolve_stage_config` (already supported).
- Remove `api_key` from `SynthesizeRequest`, `ChatCompletionRequest`, and STT form params.
- Precedence: header > assistant stored key > system env default.
- Validation: reject masked (`****`) and empty/whitespace with 422.
