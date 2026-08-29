# LiveKit Agent Service

FastAPI backend plus LiveKit worker for real-time voice assistants with `pipeline`, `realtime` and `cascade` modes.

## What This Project Does

- Manages assistants, tools, SIP trunks, API keys, and call workflows.
- Runs voice agents in LiveKit rooms.
- Supports web calls with both text (`lk.chat`) and voice input, plus an opt-in **text-only mode** (`text_only: true`) that disables mic/TTS/STT/recording for pure-chatbot use.
- Supports outbound calling and Exotel inbound routing.
- Queues outbound call requests and dispatches them in the background at a controlled rate.
- Supports three assistant runtime modes (mode = how many models are in the loop, `assistant_llm_config.provider` = vendor):
  - `pipeline` (half-cascade): a realtime model emits text + separate TTS provider. Vendor `openai` only.
  - `realtime`: LLM speaks its own audio. Vendor `gemini` (default) or `openai`.
  - `cascade`: a true STT → LLM → TTS pipeline — plugin STT, plain OpenAI chat model, plugin TTS, each separately metered and swappable.
- Supports start greetings in all modes when `assistant_interaction_config.speaks_first=true`.
- Stores transcripts and call records in MongoDB.
- Sends post-call webhook notifications.
- Sends post-call webhook notifications with both actual and billable call duration.
- Writes activity logs for tool calls, inbound context lookup, and end-call webhook delivery.
- Tracks per-call usage via SDK metrics: LLM tokens, TTS characters, and — in `cascade` mode — STT audio duration attributed to its own stage.
- Provides analytics endpoints for call duration, volume, and usage monitoring.
- Super-admin endpoints for cross-tenant analytics and token usage visibility.
- Protects worker capacity by buffering outbound requests and limiting new job intake under higher CPU load.

## Provider Support

- Outbound calls: `twilio` and `exotel`.
- Inbound calls: `exotel` only.
- Twilio inbound is not implemented.

## Provider API Keys

Per-assistant provider keys live in `assistant_tts_config`, `assistant_stt_config` and `assistant_llm_config`; each falls back to the matching system key when unset. Rules live in `src/core/providers/keys.py`:

- Keys are stored as sent — they are never validated against the provider, so a wrong key surfaces on the first call.
- `GET /assistant/details` and `GET /assistant/list` mask `api_key` in all three configs (`mask_assistant_keys`). Native STT has no key, so its config is returned untouched.
- Masked values (`sk-t...5678`, `****`, `Using System provided API Key`) are rejected on write with `422`; storing the mask would make it win over the system key and 401 mid-call.
- Free-form configs are masked by key name: `GET /tool/details` and the inbound-context strategies return `****` for `authorization` / `token` / `secret` / `api_key` / `password` entries (including inside `headers`) and leave the `url` readable. Writing a `****` value back is also a `422`.
- Filler words always call OpenAI, so an assistant's LLM key is reused there only when its LLM provider is `openai` — otherwise the system `OPENAI_API_KEY` is used (`provider_key_or_system`).

## Configuration Validation

The failure this platform guards hardest against has one shape: a configuration is accepted, the
call connects, the provider rejects **every** LLM turn, and the caller hears silence until they
hang up. Nothing looks wrong in the request, and the worker log only says
`There was an issue with your request. Please check your inputs and try again`
(`status_code=-1` — a WebSocket error frame with no detail).

Four gates run before an assistant is stored, cheapest first:

1. **Schema** (`src/api/models/api_schemas/`) — shape, ranges, enums, and the allowlisted model
   ids for every provider: LLM, STT, TTS, Gemini Live, realtime voices, Sarvam speakers. These
   used to be free strings, so a typo like `nova-9` stored fine and died at job start.
2. **Mode rule table** (`validate_mode_config`) — which provider/model/STT/voice/tool
   combinations can run in each mode. Re-checked against the **stored row** on every PATCH and
   on tool attach/detach, because most PATCHes do not resend the mode, and attaching a tool
   moves two of the rules.
3. **Live model check** — one cached `GET /v1/models`: does the account still serve this model?
   No static list can know about a retirement. Three `*-chat-latest` aliases were retired by
   OpenAI on 2026-06-19 and every assistant holding one kept validating clean.
4. **Config probe** (cascade only) — one 16-token Responses request carrying the exact model,
   knobs and tool schemas. This is what catches a `reasoning_effort` *value* a model refuses and
   a `service_tier` the account may not use. OpenAI's own message becomes the `422`.

Gates 3 and 4 fail **open** on a network error, `401`, `429` or `5xx` — a provider outage must
not make assistants un-editable. Results are cached per key and per knob combination
(`OPENAI_MODEL_CACHE_TTL`, default 1 h), so a hundred assistants sharing one config cost one
request.

What each model, tier, voice and speaker actually accepts lives in `src/core/model_support/` —
dependency-free, imported by both the API and the worker so the two halves cannot disagree.
Every set is measured, never copied from a doc page: `flex` is refused on `gpt-4.1*`, `scale` is
not an OpenAI tier at all, and `fast` works everywhere while being documented nowhere. Full
tables: [Compatibility Matrix](docs/reference/compatibility.md).

### Diagnostics

| Command | Answers |
|---|---|
| `uv run python scripts/replay_cascade_request.py <assistant_id>` | *Why* did the provider refuse this assistant's request? Replays the exact payload over HTTPS and, when no parameter is named, bisects the knobs automatically. |
| `uv run python scripts/check_model_allowlist.py` | Is every allowlisted model still servable by this key? Exits non-zero on drift, so it works as a pre-deploy gate. Add `--probe <model>` to test one id — `/v1/models` lists deprecated ids that answer `404`. |
| `uv run python scripts/audit_assistant_models.py` | Which stored assistants hold a model this deployment cannot run? `--apply` clears the field so they fall back to the default. |

All three are read-only unless `--apply` is passed, and none of them print an API key.
Symptom-by-symptom guide: [Troubleshooting](docs/reference/troubleshooting.md).

**Never edit a model list from memory.** OpenAI retires models on its own schedule and a stale
entry is indistinguishable from a working one until a call goes silent — run
`check_model_allowlist.py` first, and `--probe` anything you intend to add.

## Exotel Outbound Lifecycle

- Exotel outbound API calls are queued first and return `202 Accepted` with a `queue_id`.
- A background dispatcher starts with the API process and promotes queued calls into active LiveKit sessions when capacity is available.
- Final call outcomes are delivered through end-call webhook payloads (`completed`, `busy`, `no_answer`, `timeout`, `failed`, etc.).
- Exotel outbound recording starts only after the bridge signals `call_answered` and the worker confirms egress start.
- Exotel recordings are explicitly stopped on call end using the stored egress id.
- Exotel completed-call duration is measured from `answered_at` to `ended_at`.
- Trunk/provider mismatch is rejected at API level (`trunk_type` must match `call_service`).

## Outbound Queueing

- `POST /call/outbound` validates the assistant and trunk, inserts an `outbound_call_queue` record, and returns `202 Accepted`.
- `GET /call/queue/{queue_id}` returns queue state for the requesting user.
- Queue states are:
  - `pending`: waiting for dispatcher capacity
  - `dispatching`: reserved by dispatcher and being turned into a live call
  - `dispatched`: LiveKit room + provider dispatch created successfully
  - `failed`: permanently failed after retry exhaustion
- Current dispatcher defaults:
  - up to `12` concurrent active sessions (set by `MAX_CONCURRENT_JOBS`)
  - polls the queue every `2` seconds (fallback poll every `30s` when idle)
  - retries dispatch failures up to `3` times
- Active-session protection also uses the worker load threshold in `src/core/agents/session.py`: the worker counts its own active jobs and stops accepting new ones once it is running `MAX_CONCURRENT_SESSIONS`.
- Caps are per call type: `MAX_CONCURRENT_JOBS` (telephony), `MAX_CONCURRENT_WEB_CALLS` (web), and `MAX_CONCURRENT_SESSIONS` as a hard ceiling across both. Web calls return `503` when their cap is reached; inbound phone calls get SIP `486 Busy Here`.

## Passthrough Mode (Web ↔ SIP, No AI Agent)

Passthrough mode lets a human web user speak directly to a phone caller through SIP without any AI agent involved.

### How it works

1. Enable passthrough on a trunk: set `passthrough_mode: true` when creating the trunk via `POST /sip/create-outbound-trunk`.
2. Web client calls `POST /call/outbound_passthrough` with `trunk_id` and `to_number`.
3. API synchronously creates a LiveKit room and returns a `room_token` and `room_name` in the `202` response.
4. Web client connects to LiveKit using `room_token` and publishes mic audio.
5. The SIP call is dialled in the background (via the outbound dispatcher). Once answered, audio flows bidirectionally: web mic → SIP → mobile and mobile → SIP → web speaker.
6. No AI agent is dispatched. No STT/LLM/TTS runs.
7. Recording and end-of-call webhook (if `passthrough_webhook_url` is set on the trunk) are handled by the dispatcher monitor rather than session.py.

### Call error handling

All SIP error outcomes (busy, no-answer, timeout, rejection) are handled identically to normal outbound calls:
- `busy` — SIP 486 / 600
- `no_answer` — SIP 408 or RTP silence timeout
- `timeout` — SIP setup timeout (60 s)
- `failed` — any other SIP error or bridge crash

Use `GET /call/queue/{queue_id}` to poll queue state. Final call status is in the `CallRecord` (use analytics or direct DB query).

### Recording

Recording starts after SIP answers and stops when the bridge exits. The S3 URL is stored in `CallRecord.recording_path`. If `passthrough_webhook_url` is set on the trunk, a full call-details webhook (same shape as the AI call webhook) is POST'd on **all** terminal outcomes — completed, busy, no-answer, timeout, failed.

### Call logs

Use `GET /call/records?passthrough_only=true` to list all passthrough call records. Supports filtering by `call_status`, `to_number`, `start_date`, `end_date`, `limit`, `offset`. Each record includes `is_passthrough: true` so call type is always identifiable. Since passthrough calls have no assistant, they do not appear in `/analytics/calls/by-assistant`.

### Limitations

- No transcript is generated (no STT).
- Hold detection events are published to the LiveKit room but no one acts on them (no session.py).

## Hold Detection & Suppression

- Exotel calls: Hold is detected instantly via SIP re-INVITE (`a=sendonly` or `a=inactive` in SDP).
- When hold is detected, the agent enters hold mode:
  - Silence watchdog stops (no reprompts during hold music)
  - Filler word controller stops (no backchannel fillers)
  - In-progress agent speech is interrupted
  - Transcript processing is suppressed
- On resume, normal agent behavior is restored automatically.
- Twilio and other providers: Hold detection is not yet implemented — the agent may respond to hold music.

## Architecture

1. API service (`src/api/server.py`) exposes REST endpoints (multiple Gunicorn workers in production).
2. SIP dispatcher (`sip_dispatcher_run.py`) — dedicated process that owns the inbound SIP listener and outbound dispatcher loop. See `docs/architecture.md` for the single-container vs. multi-container deployment model.
3. Worker (`src/core/agents/session.py`) joins LiveKit rooms and runs the assistant.
4. MongoDB stores assistants, tools, trunks, queued outbound calls, call records, and logs.
5. LiveKit handles media transport and room orchestration.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- MongoDB
- LiveKit server (cloud or self-hosted)
- API keys for providers you use (OpenAI, Google Gemini, Cartesia/Sarvam/ElevenLabs/Mistral, LiveKit)

## Environment Variables

Create `.env` in the project root.

```ini
PORT=8000
BACKEND_URL=http://localhost:8000  # Worker callback URL for webhook routing

# Container role controls (default "true" keeps single-container / dev setups working)
ENABLE_SIP_LISTENER=true   # Set "false" on api container when sip_dispatcher container is used
ENABLE_DISPATCHER=true     # Set "false" on api container when sip_dispatcher container is used
GUNICORN_WORKERS=1
MAX_CONCURRENT_JOBS=12

# End-of-call webhook delivery (see docs/api/calls/webhook.md)
END_CALL_WEBHOOK_TIMEOUT=30   # Seconds to wait for your endpoint to answer
END_CALL_WEBHOOK_ATTEMPTS=3   # Retries on timeout / connection error / 429 / 5xx

MONGODB_URL=mongodb://admin:secretpassword@localhost:27017
DATABASE_NAME=livekit_db

LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

OPENAI_API_KEY=<your-openai-api-key>
GOOGLE_API_KEY=<your-google-api-key>
CARTESIA_API_KEY=<optional>
SARVAM_API_KEY=<optional>
ELEVENLABS_API_KEY=<optional>
MISTRAL_API_KEY=<optional>

# Email (optional — needed for email tool)
SMTP_HOST=smtp.sendgrid.net
SMTP_PORT=587
SMTP_USER=apikey
SMTP_PASSWORD=<your-sendgrid-api-key>
FROM_EMAIL=noreply@yourdomain.com
FROM_NAME=Your App Name

AWS_ACCESS_KEY_ID=<optional-for-recording-upload>
AWS_SECRET_ACCESS_KEY=<optional-for-recording-upload>
AWS_REGION=us-east-1
S3_BUCKET_NAME=<optional-for-recording-upload>
S3_RECORDINGS_PREFIX=recordings/
S3_GREETING_PREFIX=greeting_audio/

LOG_LEVEL=INFO
LOG_JSON_FORMAT=False
LOG_FILE=app.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=5
```

## Run Locally

Install dependencies:

```bash
uv sync
```

Start API server (also starts SIP listener + outbound dispatcher by default):

```bash
uv run server_run.py
```

Start the dedicated SIP dispatcher process (optional, for multi-worker / production setups):

```bash
uv run sip_dispatcher_run.py
```

Start worker in another terminal:

```bash
uv run -m src.core.agents.session dev
```

Optional Docker flow:

```bash
docker compose --profile control --profile agent up --build
```

Dockerfile selection by deployment mode:

- `control` mode builds with `Dockerfile.control`
- `agent` mode builds with `Dockerfile.agent`
- `full` mode builds all services with the original `Dockerfile`
- role-specific dependency manifests:
  - `docker/requirements-control.txt`
  - `docker/requirements-agent.txt`

Production dual-host deployment (recommended):

```bash
# Server A (control plane): api + sip_dispatcher
./deploy.sh control

# Server B (capacity node): agent only
./deploy.sh agent

# Single host full stack using original Dockerfile
./deploy.sh full
```

Optional: if Server A has spare CPU, also run agent there:

```bash
docker compose --profile control --profile agent up -d --build
```

Suggested first capacity step:

- Set `MAX_CONCURRENT_JOBS=20` in production `.env`.
- Keep only one `sip_dispatcher` running across all servers.
- Keep Exotel SIP/RTP public IP variables (`EXOTEL_CUSTOMER_IP`, `EXOTEL_MEDIA_IP`) pinned to the control-plane server.

Run unit tests:

```bash
uv run python -m unittest discover -s tests -v
```

Backfill existing call records with billable minutes:

```bash
uv run python -m scripts.backfill_billable_duration_minutes
```

## Documentation

- MkDocs source lives in `docs/`. The same markdown is served to coding agents over MCP at
  `/mcp` (`src/api/mcp_docs.py`), so a new page under `docs/` is discoverable by both humans and
  agents with no extra wiring.
- Start here for behaviour questions:
  - [Models & Providers](docs/reference/models.md) — every model, knob and default, and what
    changes if you change it
  - [Compatibility Matrix](docs/reference/compatibility.md) — which mode × provider × model ×
    voice × tier combinations are legal, with the measured tables
  - [Troubleshooting](docs/reference/troubleshooting.md) — symptom → cause → the command that
    proves it
- Build docs site:

```bash
mkdocs build --strict
```

- Serve docs locally:

```bash
mkdocs serve
```

## Webhook Contracts

Use these pages as the canonical payload contracts:

- Inbound context strategy webhook: `docs/api/inbound-context-strategy/index.md`
- Tool webhook payload and response handling: `docs/api/tools/webhook.md`
- End-call webhook payload: `docs/api/calls/webhook.md`

## API Areas

- `/auth`
- `/assistant`
- `/tool`
- `/sip`
- `/call`
- `/call/queue/{queue_id}`
- `/call/outbound_passthrough` — start a passthrough call (web ↔ SIP, no agent)
- `/call/records` — list call records with optional filters; `passthrough_only=true` for passthrough-only view
- `/inbound`
- `/inbound_context_strategy`
- `/logs`
- `/web_call/get_token` — supports `text_only: true` for chatbot mode (no audio, no recording; `pipeline` and `cascade` assistants, not `realtime`)
- `/analytics` — per-user call analytics (dashboard, by-assistant, by-phone-number, by-time, by-service)
- `/admin` — super-admin cross-tenant analytics and token usage (requires `is_super_admin` flag)

## Assistant Modes

Two axes: **mode** (`assistant_mode`) = how many models are in the loop, **provider** (`assistant_llm_config.provider`) = LLM vendor. `gemini` is valid in `realtime` mode only; `pipeline` and `cascade` are OpenAI-only and reject it with a `422`. Full table: `docs/reference/compatibility.md`.

- `pipeline` mode (default, half-cascade) — a realtime model emits text, separate TTS speaks it:
  - Requires `assistant_tts_model` and `assistant_tts_config`
  - `assistant_llm_config.provider` must be `openai` (the default) — Gemini cannot run the text-only modality half-cascade needs on its native-audio Live models
  - `assistant_llm_config` optional; `model`/`api_key` override defaults. `model` must be an OpenAI realtime ID (`gpt-realtime-1.5`, …), not a chat model
  - When `assistant_interaction_config.speaks_first=true`, the assistant sends the configured start instruction as the first response
- `realtime` mode — LLM speaks its own audio, no external TTS:
  - Requires `assistant_llm_config`
  - `assistant_llm_config.provider` defaults to `gemini`; set `openai` for OpenAI realtime audio
  - `voice`/`model`/`api_key` override defaults (Gemini `Puck`/`gemini-2.5-flash-native-audio-preview-12-2025`, OpenAI `marin`/`gpt-realtime-1.5`); both `model` and `voice` are validated per vendor
  - Ignores `assistant_tts_model` and `assistant_tts_config` at runtime
  - When `assistant_interaction_config.speaks_first=true`, the assistant also sends the configured start instruction as the first response through the realtime conversation path
- `cascade` mode — a true three-stage STT → LLM → TTS pipeline (`docs/architecture/cascade-pipeline.md`):
  - Requires `assistant_tts_model` and `assistant_tts_config`, same as pipeline
  - `assistant_stt_model` is the session's own STT stage: `sarvam` (default, multilingual), or `cartesia`, `deepgram`, `elevenlabs`, `openai` (all cascade-only). `native` is rejected — there is no realtime model to self-transcribe
  - `assistant_llm_config.provider` must be `openai` (the default); `model` defaults to `gpt-4.1`, so cheap text models like `gpt-4.1-mini` are available
  - The only mode reporting **per-component usage**: `stt_provider` / `stt_model` / `stt_audio_duration` land on `UsageRecord` and the end-of-call webhook alongside the LLM and TTS numbers
  - Does not use the Sarvam parallel tap; turn detection is local (in-process Silero VAD + a bundled audio end-of-utterance model), so nothing here needs LiveKit Cloud

Note: `assistant_start_instruction` is honored in all three modes whenever `assistant_interaction_config.speaks_first` is enabled.

## Audio Library & Prerecorded Greeting

Instead of generating the opening line with the model, an assistant can play a prerecorded greeting. This skips the LLM + TTS (pipeline and cascade) or the realtime audio generation (realtime) for the greeting, cutting token cost and latency. It works in all three modes.

The design is modular: audio files live in a reusable **library** (the `audio_assets` collection) and assistants reference one by id. Auth: `Authorization: Bearer <api_key>`.

**Audio library — `/audio`**
- `POST /audio/upload` — multipart upload. Fields: `file` (**any common audio format** — mp3, m4a, ogg, wav, …, **≤ 30 s**), `audio_name`, and `transcript` (the literal spoken words, added to the model's chat context so it knows it greeted). The server transcodes the upload to WAV 48 kHz mono in-process (PyAV / bundled ffmpeg — no system binary) and stores that in S3, returning an `audio_id`. Non-audio files or clips over 30 s are rejected with `400`.
- `GET /audio/list` — list the caller's audio assets (paginated).
- `GET /audio/{audio_id}` — metadata + the S3 object URL (same format as call recordings).
- `DELETE /audio/{audio_id}` — soft-delete (`is_active=false`). Assistants still referencing it fall back to the model greeting.

**Attach + toggle (on the assistant)**
Set `assistant_greeting_audio` via `POST /assistant/create` or `PATCH /assistant/update/{id}`:
```json
{ "assistant_greeting_audio": { "enabled": true, "audio_id": "<id>" } }
```
`enabled` is the on/off switch (recorded audio vs model `generate_reply`); `audio_id` attaches a library asset. The update validates the asset exists, is active, and is owned by the caller.

**Runtime behavior:** when `enabled` and `speaks_first=true`, the worker resolves `audio_id` → `AudioAsset`, downloads the WAV, and plays it via `session.say(audio=...)`. If the asset is missing/inactive or download/decode fails, it falls back to the normal model-generated greeting, so a bad reference never breaks the call. In realtime mode the greeting stays interruptible (server-side turn detection ignores non-interruptible). The S3 key prefix is `S3_GREETING_PREFIX` (default `greeting_audio/`).

## Max Call Duration

Each assistant can cap its own call length via `assistant_interaction_config.max_call_duration_minutes` (minutes, must be `> 0`). When unset or `null`, the platform default of **30 minutes** is applied.

- When the limit is reached, the assistant speaks a brief farewell and the call is torn down gracefully — recording, transcripts, usage, MongoDB CallRecord and the end-of-call webhook all finalize cleanly.
- The terminating reason is reported as `call_end_reason = "max_duration_exceeded"` in the webhook payload and in the `CallRecord` document. Normal hang-ups report `"natural"`.
- Passthrough calls (no AI agent) are not affected — the limit only applies to assistant-driven sessions.

## Project Structure

```text
api_livekit/
├── README.md
├── CLAUDE.md
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── docker-compose.yml
├── docker/
│   ├── Dockerfile.control
│   ├── Dockerfile.agent
│   ├── requirements-control.txt
│   └── requirements-agent.txt
├── mkdocs.yml
├── server_run.py
├── sip_dispatcher_run.py
├── deploy.sh
├── .agents/
│   ├── workflows/
│   └── skills/
├── assets/
│   └── audio/
├── docs/                  # MkDocs source
├── scripts/               # migration/backfill one-offs + the three diagnostics below
├── tests/
├── src/
│   ├── api/
│   │   ├── dependencies/
│   │   │   └── auth.py                # Bearer api-key auth (get_current_user / get_super_admin)
│   │   ├── models/
│   │   │   ├── api_schemas/           # Pydantic request/response schemas + validators, split by domain
│   │   │   └── response_models.py
│   │   ├── validation/
│   │   │   └── assistant_guard.py     # guards needing the stored row or a provider call
│   │   ├── routes/
│   │   │   ├── assistant.py
│   │   │   ├── call.py
│   │   │   ├── audio.py               # audio library upload/list/get/delete
│   │   │   ├── auth.py
│   │   │   ├── health.py
│   │   │   ├── inbound.py
│   │   │   ├── inbound_context_strategy.py
│   │   │   ├── logs.py
│   │   │   ├── sip.py
│   │   │   ├── tool.py
│   │   │   ├── web_call.py
│   │   │   ├── analytics.py
│   │   │   └── admin.py
│   │   ├── mcp_docs.py                # serves docs/ markdown as an MCP server
│   │   └── server.py                  # FastAPI app
│   ├── core/
│   │   ├── agents/
│   │   │   ├── session.py             # entrypoint / orchestrator
│   │   │   ├── dynamic_assistant.py   # Agent class
│   │   │   ├── session_lifecycle.py   # CallReadinessGate, RecordingManager
│   │   │   ├── inbound_context.py     # caller context resolution
│   │   │   ├── voice_features.py      # SilenceWatchdog / Filler / Hold controllers
│   │   │   ├── tool_builder.py        # DB-backed function tool loader
│   │   │   ├── usage.py               # session.usage → UsageRecord folding
│   │   │   ├── audio_denoise.py
│   │   │   ├── utils.py               # render_prompt
│   │   │   ├── llm/
│   │   │   │   └── factory.py         # cascade LLM (openai.responses.LLM)
│   │   │   ├── stt/
│   │   │   │   ├── factory.py         # STT resolver (pipeline) + cascade builder (create_stt)
│   │   │   │   ├── native_prompt.py   # transcription prompt + noise-reduction pick (native path)
│   │   │   │   └── sarvam_parallel.py # Sarvam Saras v3 parallel STT tap + fragment coalescer
│   │   │   ├── models/
│   │   │   │   └── silero_vad.onnx    # local VAD weights (livekit-local-inference)
│   │   │   └── tts/
│   │   │       └── factory.py         # TTS factory + Sarvam WS keepalive
│   │   ├── model_support/             # dependency-free: what each model/provider accepts
│   │   │   ├── capabilities.py        # LLM model sets + which knobs each one reads
│   │   │   ├── speech.py              # STT/TTS model sets + Sarvam speaker roster
│   │   │   ├── openai_live.py         # asks OpenAI what it serves / accepts (config time)
│   │   │   ├── payload.py             # the Responses request body the runtime sends
│   │   │   └── tool_schema.py         # one tool document → one OpenAI function schema
│   │   ├── providers/
│   │   │   ├── __init__.py
│   │   │   └── keys.py                # provider key registry + masking helpers
│   │   ├── billing.py                 # actual vs billable duration
│   │   ├── db/
│   │   │   ├── database.py
│   │   │   └── db_schemas.py          # Beanie documents
│   │   ├── config.py                  # Settings / env config
│   │   └── logger.py
│   └── services/
│       ├── outbound_dispatcher/
│       │   └── dispatcher.py          # outbound dispatch loop
│       ├── elevenlabs/
│       │   └── v3_nonstream.py        # eleven_v3 HTTP-chunked TTS
│       ├── mistral/
│       │   └── tts.py
│       ├── email/
│       │   └── smtp_service.py
│       ├── storage/
│       │   ├── audio_transcode.py     # upload → WAV 48 kHz mono (PyAV/ffmpeg)
│       │   └── s3_audio.py            # audio-asset S3 access (boto3)
│       ├── exotel/
│       │   └── custom_sip_reach/
│       │       ├── bridge.py
│       │       ├── rtp_bridge.py
│       │       ├── sip_client.py
│       │       ├── inbound_listener.py
│       │       ├── inbound_bridge.py
│       │       ├── digest_auth.py
│       │       ├── port_pool.py
│       │       └── config.py
│       └── livekit/
│           └── livekit_svc.py
```
