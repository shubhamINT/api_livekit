# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working agreement (do this before touching anything)

Applies to any **non-trivial** request — one that touches 2+ files or needs 3+ steps. A one-line
fix, a rename, or a plain question skips all of it; do those directly.

1. **Check the skills first.** Before planning, see whether an available skill already covers the
   task (they are listed in the session context). If one fits, invoke it and follow it instead of
   improvising a workflow. The same goes for the `livekit-docs` MCP server: for anything about the
   LiveKit SDK, plugins, or model parameters, read the live docs — never work from memory, the
   SDK moves faster than any snapshot.
2. **Write the todo list before the first edit.** Use `TaskCreate` to lay out the steps, then
   `TaskUpdate` to mark exactly one `in_progress` at a time and `completed` as each lands. The
   list is the plan; write it while the work is still reversible, not as a summary afterwards.
3. **Ask when something is genuinely undecided.** Use `AskUserQuestion` when two readings of the
   request lead to materially different work, when the request contradicts what is already in
   the repo (a doc, a validation rule, a stored schema), or when a choice is the user's to make
   (defaults, naming, scope, whether to drop a provider). Ask *before* building on the guess.
   Do **not** ask about things with an obvious default — pick it, say which, and move on.
4. **Then work the list step by step**, verifying as you go rather than at the end.
5. **Finish the whole chain.** In this repo a change is not done until code, schemas, tests and
   docs agree. See [Definition of done](#definition-of-done).

Same block lives in `AGENTS.md` for non-Claude agents — edit both or neither.

## Definition of done

A change to models, providers or config knobs is finished only when all of these are true:

- **The model list came from the API, not from memory.** Run
  `uv run python scripts/check_model_allowlist.py` before touching any model set. OpenAI retires
  models on its own schedule and a stale entry is indistinguishable from a working one until a
  call goes silent — that is exactly how the three `*-chat-latest` aliases became an outage.
- Factory code, `src/api/models/api_schemas/`, `src/core/model_support/`, and the
  `validate_mode_config` rule table agree.
- Tests updated and green: `uv run python -m unittest discover -s tests`.
- Docs updated in **every** place that lists the thing you changed: `docs/reference/models.md`,
  `docs/reference/compatibility.md`, `docs/reference/troubleshooting.md`,
  `docs/architecture/cascade-pipeline.md`, `docs/api/assistant/{create,update,index,list}.md`,
  plus `README.md` / `docs/features.md` when the feature list changes. `grep` for a sibling
  provider's name to find them all.
- Docs build clean: `uv run mkdocs build --strict`, and diagrams parse:
  `uv run python scripts/check_mermaid.py`. The strict build cannot catch a broken Mermaid
  diagram — they render in the browser, so a bad one deploys clean and then shows an error box.
- Lint the files you touched: `uvx ruff check <paths>` (the repo has pre-existing violations
  elsewhere — don't reflow unrelated files).
- **Never `git commit` unless explicitly asked.**

## Commands

```bash
# Install dependencies
uv sync

# Run API server (includes SIP listener + outbound dispatcher by default)
uv run server_run.py

# Run dedicated SIP dispatcher process (for multi-worker setups)
uv run sip_dispatcher_run.py

# Run LiveKit worker (separate terminal)
uv run -m src.core.agents.session dev

# Run tests
uv run python -m unittest discover -s tests -v

# Run single test file
uv run python -m unittest tests/test_session_lifecycle.py -v

# Lint
# (ruff is not a project dependency — uvx fetches it on demand)
uvx ruff check .
uvx ruff format .

# Build docs
mkdocs build --strict

# Serve docs locally
mkdocs serve
```

## Architecture

Three concurrent processes form the runtime:

1. **API server** (`src/api/server.py`) — FastAPI app served by Gunicorn. Handles REST CRUD and dispatches calls via the outbound queue. On startup, optionally starts the SIP listener and outbound dispatcher (controlled by `ENABLE_SIP_LISTENER` / `ENABLE_DISPATCHER` env vars; both default `true` for dev).

2. **SIP dispatcher** (`sip_dispatcher_run.py`) — In production, a dedicated process that owns the Exotel inbound SIP listener (`src/services/exotel/custom_sip_reach/inbound_listener.py`) and the outbound dispatch loop (`src/services/outbound_dispatcher/dispatcher.py`). Only one instance should run across all servers.

3. **LiveKit worker** (`src/core/agents/session.py`) — Connects to LiveKit via the agents SDK. `entrypoint()` is the job handler; it resolves the assistant from MongoDB, builds TTS/STT, attaches voice features, and runs the session.

### Call flow (outbound)

`POST /call/outbound` → validates assistant + trunk (`trunk_type` must match `call_service`) → inserts `OutboundCallQueue` record → returns `202 Accepted` with `queue_id` → dispatcher wakes on a MongoDB Change Stream (30s safety-net poll) → creates LiveKit room + dispatches agent job → worker `entrypoint()` runs the session → end-of-call webhook + `CallRecord` finalized.

Queue states: `pending` → `dispatching` → `dispatched` (or `failed` after 3 retries). `GET /call/queue/{queue_id}` returns state.

### Concurrency / load control

- Concurrency caps are per call type (`src/core/config.py`): `MAX_CONCURRENT_JOBS` (default `12`)
  for telephony, `MAX_CONCURRENT_WEB_CALLS` (default `40`) for web calls, and
  `MAX_CONCURRENT_SESSIONS` (default `48`) as a hard ceiling across everything. Buckets come from
  `CallRecord.call_type` via `bucket_for_call_type`; passthrough counts as telephony because it
  holds a bridge and an RTP port. The web and global defaults are **not** measured — set them from
  a load test.
- `MAX_CONCURRENT_INVITE_SETUPS` (default `24`) bounds inbound INVITEs *in setup*, not live calls.
- The LiveKit worker stops accepting new jobs once it is already running `MAX_CONCURRENT_SESSIONS`,
  counted from its own active jobs (`_worker_load` + `load_threshold=1.0` in
  `src/core/agents/session.py`). It used to use the SDK default, which reads whole-machine CPU — so
  a busy SIP dispatcher on the same host silently stopped agent intake and calls connected with no
  agent behind them.
- Providers: outbound supports `twilio` + `exotel`; inbound supports `exotel` only (no Twilio inbound).

### Auth

REST routes require `Authorization: Bearer <api_key>` (keys are `lvk_`-prefixed, stored in `api_keys`). Dependency `get_current_user` validates; `get_super_admin` gates admin routes. See `src/api/dependencies/auth.py`.

### Key source locations

| Concern | Path |
|---|---|
| Agent session entrypoint | `src/core/agents/session.py` |
| Agent class (DynamicAssistant) | `src/core/agents/dynamic_assistant.py` |
| Session lifecycle (gate, recording) | `src/core/agents/session_lifecycle.py` |
| Voice features (silence watchdog, filler, hold) | `src/core/agents/voice_features.py` |
| TTS factory (cartesia/sarvam/elevenlabs/mistral) | `src/core/agents/tts/factory.py` |
| STT resolver (native/sarvam) + cascade STT builder (sarvam/cartesia/deepgram/elevenlabs/openai) | `src/core/agents/stt/factory.py` |
| LLM factory (cascade only, OpenAI) | `src/core/agents/llm/factory.py` |
| Model/provider support (dependency-free, both images) | `src/core/model_support/` |
| — LLM model sets + which knobs each accepts | `src/core/model_support/capabilities.py` |
| — STT/TTS model sets + Sarvam speaker roster | `src/core/model_support/speech.py` |
| — Asking OpenAI what it serves / accepts (config time) | `src/core/model_support/openai_live.py` |
| — The Responses request body the runtime sends | `src/core/model_support/payload.py` |
| — One tool document to one OpenAI function schema | `src/core/model_support/tool_schema.py` |
| Config guards needing the stored row or a network call | `src/api/validation/assistant_guard.py` |
| Per-component usage folding (`session.usage` → `UsageRecord`) | `src/core/agents/usage.py` |
| Sarvam parallel STT tap (pipeline mode only) | `src/core/agents/stt/sarvam_parallel.py` |
| Tool loader (DB-backed function tools) | `src/core/agents/tool_builder.py` |
| Outbound dispatcher loop | `src/services/outbound_dispatcher/dispatcher.py` |
| Exotel SIP/RTP bridge | `src/services/exotel/custom_sip_reach/` |
| — One inbound call's media half (own process) | `src/services/exotel/custom_sip_reach/inbound_worker.py` |
| — Multiprocessing context for all bridges | `src/services/outbound_dispatcher/dispatcher.py::get_bridge_context` |
| Provider key masking | `src/core/providers/` |
| MongoDB schemas (Beanie ODM) | `src/core/db/db_schemas.py` |
| Settings / env config | `src/core/config.py` |
| API routes | `src/api/routes/` |
| MCP docs server (`/mcp`) | `src/api/mcp_docs.py` |

### Assistant modes

Selected by the `assistant_mode` field (`pipeline` | `realtime` | `cascade`) on the `Assistant` document — it sets the session *shape*, not the LLM vendor (that is `assistant_llm_config.provider`).

- **`pipeline`** (default, half-cascade): OpenAI realtime for STT+LLM, separate TTS provider. Requires `assistant_tts_model` + `assistant_tts_config`. Provider must be `openai` — Gemini is rejected here (its Live API cannot do text-only modality on native-audio models); use `realtime` for Gemini.
- **`realtime`**: Gemini realtime handles STT+LLM+TTS in one model. `assistant_tts_model` / `assistant_tts_config` are ignored at runtime.
- **`cascade`**: a true three-stage pipeline — plugin STT + non-realtime `openai.responses.LLM` + plugin TTS, all passed to one `AgentSession(stt=, llm=, tts=, vad=)`. Requires TTS like pipeline; `assistant_stt_model` must be `sarvam`, `cartesia`, `deepgram`, `elevenlabs` or `openai` (`native` rejected); provider must be `openai`. Docs: `docs/architecture/cascade-pipeline.md`.

TTS providers: `cartesia`, `sarvam`, `elevenlabs`, `mistral`. Per-provider config lives in `assistant_tts_config` dict on the `Assistant` document; factory is `src/core/agents/tts/factory.py`.

STT providers: `sarvam` (default — Saras v3), `native` (the conversational LLM transcribes itself), and `cartesia`, `deepgram`, `elevenlabs`, `openai` (all cascade only; `openai` collapses back to `native` in pipeline mode). Same shape as TTS: `assistant_stt_model` + `assistant_stt_config` on the `Assistant` document. **Two resolvers, don't mix them:** `resolve_stt` returns a `(provider, config)` tuple for the pipeline-mode parallel tap; `create_stt` builds an actual plugin STT object for cascade. Both in `src/core/agents/stt/factory.py`. Unset means `sarvam`. Ignored in realtime mode.

LLM: `src/core/agents/llm/factory.py::create_llm` — cascade only. The other two modes build a `RealtimeModel` inline in `session.py`.

**Config validation is four gates, cheapest first.** All of them exist to prevent one failure: a
configuration that is accepted, then rejected by the provider on *every* LLM turn, so the call
connects and the assistant never speaks. See `src/api/validation/assistant_guard.py` for the
full account and `docs/reference/troubleshooting.md` for the operator-facing version.

1. **Pydantic** (`src/api/models/api_schemas/`) — shape, ranges, enums, plus the STT/TTS model
   and Sarvam speaker sets.
2. **`validate_mode_config`** (`api_schemas/config/llm_config.py`) — one rule table for all
   three modes (`REALTIME_MODELS` / `GEMINI_LIVE_MODELS` for pipeline+realtime,
   `OPENAI_CASCADE_MODELS` for cascade, plus voices and the tool_choice rule). Called from the
   Create/Update validators, and re-run by `enforce_stored_mode_constraints` against the stored
   row merged with the PATCH — most PATCHes do not resend the mode.
3. **`unavailable_model_reason`** — one cached `GET /v1/models`: does the account still serve
   this model? No static list can know about a retirement (three `*-chat-latest` aliases went
   on 2026-06-19 and every assistant holding one kept validating clean).
4. **`rejected_config_reason`** — one short Responses probe carrying the real model, knobs and
   tool schemas: catches a `reasoning_effort` value the model refuses, a `service_tier` the
   account may not use, and a tool schema the API rejects. OpenAI's own message becomes the 422.

Gates 3 and 4 fail **open** on anything that is not a clear refusal (network error, 401, 429,
5xx) — an OpenAI outage must not make assistants un-editable. `POST /tool/attach` and
`/tool/detach` run the same guards: attaching or detaching a tool moves the `tool_choice` and
`reasoning_effort` rules. User-facing matrix: `docs/reference/compatibility.md`.

**Never edit a model list from memory.** `uv run python scripts/check_model_allowlist.py` diffs
every list against what the account actually serves. `scripts/audit_assistant_models.py` finds
stored rows that have gone stale. `scripts/replay_cascade_request.py <assistant_id> --bisect`
replays a failing assistant's request over HTTPS, where OpenAI's error has detail — over the
WebSocket the runtime uses, a rejection is `status_code=-1` with no parameter name at all.

**Cascade LLM knobs are model-gated.** `temperature`, `reasoning_effort` and `verbosity` are only accepted by some models, and OpenAI answers a wrong pairing with a 400 on *every* LLM turn (the call connects and stays silent). The families and the rule live in `src/core/model_support/capabilities.py` — spelled out per model, never matched by prefix, because `gpt-5.2-chat-latest` was a chat model (now retired and off the allowlist). That module is imported by both the API validator (422 at create/update) and `create_llm` (drops a stale knob at call time), so it must stay dependency-free: the control image has no `livekit-agents`, the agent image has no FastAPI. `create_llm` also clears the reasoning effort the OpenAI plugin injects by itself on `gpt-5.2`/`gpt-5.4*` when function tools are attached — hence `create_llm(assistant, has_tools=...)`.

**Self-hosted constraint:** `inference.STT/LLM/TTS` (the LiveKit Inference gateway), `inference.TurnDetector(version="v1")` and `interruption={"mode":"adaptive"}` all require LiveKit Cloud credentials and must not be used. `inference.VAD(model="silero")` and `inference.TurnDetector(version="v1-mini")` are fully local (weights ship in `livekit-local-inference`, a core SDK dep) and are what cascade uses.

### MongoDB collections (Beanie documents)

`api_keys`, `assistants`, `audio_assets`, `outbound_sip`, `inbound_sip`, `tools`, `call_records`, `outbound_call_queue`, `inbound_context_strategies`, `usage_records`, `activity_logs` — all defined in `src/core/db/db_schemas.py`.

### Deployment modes

Controlled by `./deploy.sh <mode>` and Docker profiles:
- `control` — API + SIP dispatcher (`Dockerfile.control`, `docker/requirements-control.txt`)
- `agent` — LiveKit worker only (`Dockerfile.agent`, `docker/requirements-agent.txt`)
- `full` — all services on one host (`Dockerfile`)

In multi-host production: set `ENABLE_SIP_LISTENER=false` and `ENABLE_DISPATCHER=false` on the API container; run the dedicated `sip_dispatcher` container instead.

### Key env vars

All read in `src/core/config.py` (`Settings`). Beyond `ENABLE_SIP_LISTENER` / `ENABLE_DISPATCHER` / `MAX_CONCURRENT_JOBS`:
- DB: `MONGODB_URL`, `DATABASE_NAME`
- LiveKit: `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`
- Providers: `OPENAI_API_KEY`, `GOOGLE_API_KEY`, `CARTESIA_API_KEY`, `SARVAM_API_KEY`, `ELEVENLABS_API_KEY` (STT + TTS), `MISTRAL_API_KEY`, `DEEPGRAM_API_KEY` (STT)
- Recordings (S3): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`, `S3_RECORDINGS_PREFIX`, `S3_GREETING_PREFIX`
- Webhooks/email: `BACKEND_URL`, `SMTP_*`, `FROM_EMAIL`, `END_CALL_WEBHOOK_TIMEOUT` (read timeout in
  seconds, default `30`), `END_CALL_WEBHOOK_ATTEMPTS` (default `3`)
- Server: `PORT`, `GUNICORN_WORKERS`

## Runtime behaviors (see README.md for full detail)

- **Web call modes**: voice + text (`lk.chat`), plus opt-in `text_only: true` (disables mic/TTS/STT/recording for pure chatbot). `docs/api/calls/web-call.md`.
- **Passthrough mode**: human web user ↔ SIP phone caller, no AI agent. `docs/api/calls/passthrough.md`.
- **Greetings**: both modes greet first when `assistant_interaction_config.speaks_first=true`.
- **Audio library + prerecorded greeting**: reusable audio assets live in the `audio_assets` collection, managed via the `/audio` router (`upload` accepts any audio format, transcodes to WAV 48 kHz mono via PyAV/bundled-ffmpeg in `src/services/storage/audio_transcode.py`, enforces ≤ 30 s; `list`/`get`/`delete` soft-deletes). Assistants reference one by id through `assistant_greeting_audio = {enabled, audio_id}` (set via `/assistant/create` or `/assistant/update`). When enabled, the worker resolves `audio_id` → `AudioAsset` and plays the S3 WAV via `session.say(audio=...)` instead of model-generating the greeting — saves tokens in both modes. S3 access in `src/services/storage/s3_audio.py` (boto3, direct — not LiveKit egress). Any missing/inactive asset or download/decode failure falls back to the model greeting.
- **Billing**: webhook reports both actual and billable duration; Exotel completed duration measured `answered_at`→`ended_at`. `src/core/billing.py`.

## One-off scripts

`scripts/` holds migration/backfill jobs (e.g. `migrate_assistants.py`, `migrate_stt_config.py`, `backfill_call_records.py`, `backfill_billable_duration_minutes.py`, `migrate_llm_knobs.py`). Run with `uv run python scripts/<name>.py`.

**Diagnostics** (read-only unless noted; details in `docs/reference/troubleshooting.md`):

| Script | Answers |
|---|---|
| `check_model_allowlist.py` | Does every allowlisted model still exist for this key? Exits 1 on drift, so it doubles as a pre-deploy gate. **Run it before editing any model list.** |
| `audit_assistant_models.py` | Which stored assistants hold a model this deployment cannot run? `--apply` clears the model field so they fall back to the default. |
| `check_mermaid.py` | Does every Mermaid diagram in the docs actually render? Catches both parse errors and diagrams that parse but draw wrong (a literal `\n` in a label). Exits 1 on failure. |
| `replay_cascade_request.py <assistant_id>` | *Why* did OpenAI refuse this assistant's request? Replays the exact payload over HTTPS, where the error has detail; `--bisect` names every offending knob. |

`migrate_stt_config.py` runs in two passes: default copies the legacy `assistant_interaction_config.user_stt_provider` / `.stt_api_key` into `assistant_stt_model` / `assistant_stt_config` (safe before deploy), `--unset` removes the old keys (after deploy is verified).

## Webhook contracts

Canonical payload docs (not code):
- End-call webhook: `docs/api/calls/webhook.md`
- Tool webhook: `docs/api/tools/webhook.md`
- Inbound context strategy: `docs/api/inbound-context-strategy/index.md`
