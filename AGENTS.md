# AGENTS.md

The one instruction file for every coding agent in this repo (Claude Code, Codex, Cursor,
opencode). `CLAUDE.md` only imports it, so edit this file — never add content to `CLAUDE.md`.

It holds the working agreement, the commands, the architecture, the system-of-record for each
topic, and the **guardrails** that keep past regressions from coming back. The
`core-be` block near the end is managed by the skill pack; the `## Project structure` section
after it belongs to this repo.

## Working agreement (do this before touching anything)

Applies to any **non-trivial** request — one that touches 2+ files or needs 3+ steps. A one-line
fix, a rename, or a plain question skips all of it; do those directly.

1. **Check the skills first.** Before planning, see whether an available skill already covers the
   task. If one fits, invoke it and follow it instead of improvising a workflow. The same goes for
   the `livekit-docs` MCP server: for anything about the LiveKit SDK, plugins, or model parameters,
   read the live docs — never work from memory, the SDK moves faster than any snapshot.
2. **Write the todo list before the first edit.** Lay out the steps, keep exactly one in progress,
   mark each done as it lands. The list is the plan; write it while the work is still reversible,
   not as a summary afterwards.
3. **Ask when something is genuinely undecided.** Ask the user when two readings of the request
   lead to materially different work, when the request contradicts what is already in the repo (a
   doc, a validation rule, a stored schema), or when a choice is theirs to make (defaults, naming,
   scope, whether to drop a provider). Ask *before* building on the guess. Do **not** ask about
   things with an obvious default — pick it, say which, and move on.
4. **Then work the list step by step**, verifying as you go rather than at the end.
5. **Finish the whole chain.** A change is not done until code, schemas, tests and docs agree —
   see [Definition of done](#definition-of-done).

## Agent working files (`agent-tracking/`)

Everything an agent produces that is **not** shipped code or product documentation goes under
`agent-tracking/`, never in the repo root and never in `docs/`. `docs/` is the published MkDocs
site and is for users of the API; `dev-docs/` explains how the system is built, for developers of
this repo; `agent-tracking/` is for us.

One folder per task, named by a slug `YYYY-MM-DD-<type>-<topic>` (type is `feature`, `debug`,
`refactor`, `audit`, `security`, `test`, `structure` or `health`). The same slug is used in every
directory below, so a task's plan, research and report find each other by name.

| Path | Holds |
|---|---|
| `agent-tracking/INDEX.md` | One row per task with its status and report link — start here |
| `agent-tracking/plans/<slug>/` | `scope.md` (the request, verbatim), `tasks.md` (the approved checklist), `progress.md`; older tasks keep the plan and its progress log together in `plan.md` |
| `agent-tracking/research/<slug>.md` | Research write-ups and findings, including their unverified claims |
| `agent-tracking/reports/<slug>.html` | The finished report for the task |
| `agent-tracking/demo-code/` | Spikes and prototypes that are not wired into the app |

Tasks from before this layout were numbered plans (`plan 01` … `plan 08`); `INDEX.md` maps each
old number to its slug, so prose that still says "plan 03" resolves.

Three rules:

- **Do not add these to `mkdocs.yml`.** They are working notes, not the product's docs, and a
  strict build must not depend on them.
- **Write them in normal prose**, with `file:line` citations for every claim about the code. They
  are read by people who are not in the conversation that produced them.
- **Supersede in place.** When a plan is replaced, rewrite or delete the old file rather than
  leaving two documents that contradict each other.

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
  `docs/concepts/` (the mode or flow you changed), `docs/api/assistant/{create,update,index,list}.md`,
  plus `README.md` / `docs/features.md` when the feature list changes. `grep` for a sibling
  provider's name to find them all. A change to a contract an *external* worker implements also
  belongs in `docs/guides/`, and anything under `docs/` must be added to `nav:` in `mkdocs.yml` or
  the strict build fails.
- How it is built changed: update the matching `dev-docs/subsystems/` page. A decision made or
  reversed: add a record to `dev-docs/decisions/`. Public `docs/` pages name no source files —
  code pointers go in `dev-docs/`, and `dev-docs/` links to `docs/`, never the other way.
- Docs build clean: `uv run mkdocs build --strict`, and diagrams parse:
  `uv run python scripts/check_mermaid.py`. The strict build cannot catch a broken Mermaid
  diagram — they render in the browser, so a bad one deploys clean and then shows an error box.
- Lint the files you touched: `uvx ruff check <paths>` — pre-existing violations live outside
  them; don't reflow unrelated files.
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
# Production runs `python -m livekit.agents start agent_run.py`; `dev` goes through the
# SDK's deprecated Python CLI, which warns but needs no extra binary.
uv run agent_run.py dev

# Run tests
uv run python -m unittest discover -s tests -v

# Run single test file
uv run python -m unittest tests/test_session_lifecycle.py -v

# Lint
# (ruff is not a project dependency — uvx fetches it on demand)
uvx ruff check .
uvx ruff format .

# Build docs
uv run mkdocs build --strict

# Serve docs locally
uv run mkdocs serve
```

Tests use stdlib `unittest`, not pytest; this overrides the pack's language baseline below.

## Architecture

Three concurrent processes form the runtime:

1. **API server** (`src/api/server.py`) — FastAPI app served by Gunicorn. Handles REST CRUD and dispatches calls via the outbound queue. On startup, optionally starts the SIP listener and outbound dispatcher (controlled by `ENABLE_SIP_LISTENER` / `ENABLE_DISPATCHER` env vars; both default `true` for dev).

2. **SIP dispatcher** (`sip_dispatcher_run.py`) — In production, a dedicated process that owns the Exotel inbound SIP listener (`src/services/exotel/custom_sip_reach/inbound_listener.py`) and the outbound dispatch loop (`src/services/outbound_dispatcher/dispatcher.py`). Only one instance should run across all servers.

3. **LiveKit worker** (`agent_run.py` → `src/core/agents/session.py`) — Launched by `python -m livekit.agents start agent_run.py`, which discovers the `AgentServer` that `agent_run.py` builds from `WorkerOptions`. Connects to LiveKit via the agents SDK. `entrypoint()` is the job handler; it resolves the assistant from MongoDB, builds TTS/STT, attaches voice features, and runs the session.

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
  `agent_run.py`). It used to use the SDK default, which reads whole-machine CPU — so
  a busy SIP dispatcher on the same host silently stopped agent intake and calls connected with no
  agent behind them.
- Providers: outbound supports `twilio` + `exotel`; inbound supports `exotel` only (no Twilio inbound).

### Auth

REST routes require `Authorization: Bearer <api_key>` (keys are `lvk_`-prefixed, stored in `api_keys`). Dependency `get_current_user` validates; `get_super_admin` gates admin routes. See `src/api/dependencies/auth.py`.

### Key source locations

| Concern | Path |
|---|---|
| Worker launch + `WorkerOptions` | `agent_run.py` |
| Agent session entrypoint | `src/core/agents/session.py` |
| Agent class (DynamicAssistant) | `src/core/agents/dynamic_assistant.py` |
| Built-in prompts (XML tags + Markdown inside) | `src/core/agents/prompts.py` |
| Session lifecycle (gate, recording) | `src/core/agents/session_lifecycle.py` |
| Voice features (silence watchdog, filler, hold) | `src/core/agents/voice_features.py` |
| TTS factory (cartesia/sarvam/elevenlabs/mistral) | `src/core/agents/tts/factory.py` |
| STT resolver (native/sarvam) + cascade STT builder (sarvam/cartesia/deepgram/elevenlabs/openai) | `src/core/agents/stt/factory.py` |
| LLM factory (cascade `create_llm` + duplex `create_gpt_live`, OpenAI) | `src/core/agents/llm/factory.py` |
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

Selected by the `assistant_mode` field (`pipeline` | `realtime` | `cascade` | `duplex`) on the `Assistant` document — it sets the session *shape*, not the LLM vendor (that is `assistant_llm_config.provider`).

- **`pipeline`** (default, half-cascade): OpenAI realtime for STT+LLM, separate TTS provider. Requires `assistant_tts_model` + `assistant_tts_config`. Provider must be `openai` — Gemini is rejected here (its Live API cannot do text-only modality on native-audio models); use `realtime` for Gemini.
- **`realtime`**: Gemini realtime handles STT+LLM+TTS in one model. `assistant_tts_model` / `assistant_tts_config` are ignored at runtime.
- **`cascade`**: a true three-stage pipeline — plugin STT + non-realtime `openai.responses.LLM` + plugin TTS, all passed to one `AgentSession(stt=, llm=, tts=, vad=)`. Requires TTS like pipeline; `assistant_stt_model` must be `sarvam`, `cartesia`, `deepgram`, `elevenlabs` or `openai` (`native` rejected); provider must be `openai`. Docs: `docs/concepts/cascade.md` (behaviour), `dev-docs/subsystems/speech-and-llm-stages.md` (build).
- **`duplex`**: OpenAI GPT-Live (`openai.realtime.GPTLiveModel`, a `DuplexModel` — not a `RealtimeModel`) on our own key, built by `create_gpt_live`. Listens while it speaks and decides its own turns; hands reasoning and tools to `assistant_llm_config.backend_model` (a reasoning model, default `gpt-5.6-luna`), so the generation knobs are judged against the backend. No TTS, no STT, explicit local Silero VAD for barge-in. `session.say()` raises without a TTS, so greeting audio, filler words and `text_only` are rejected at the API. Voice and both instruction sets are fixed for the session. Switching into or out of duplex clears the stored `assistant_llm_config`.

TTS providers: `cartesia`, `sarvam`, `elevenlabs`, `mistral`. Per-provider config lives in `assistant_tts_config` dict on the `Assistant` document; factory is `src/core/agents/tts/factory.py`.

STT providers: `sarvam` (default — Saras v3), `native` (the conversational LLM transcribes itself), and `cartesia`, `deepgram`, `elevenlabs`, `openai` (all cascade only; `openai` collapses back to `native` in pipeline mode). Same shape as TTS: `assistant_stt_model` + `assistant_stt_config` on the `Assistant` document. **Two resolvers, don't mix them:** `resolve_stt` returns a `(provider, config)` tuple for the pipeline-mode parallel tap; `create_stt` builds an actual plugin STT object for cascade. Both in `src/core/agents/stt/factory.py`. Unset means `sarvam`. Ignored in realtime and duplex mode.

LLM: `src/core/agents/llm/factory.py` — `create_llm` (cascade) and `create_gpt_live` (duplex). Pipeline and realtime build a `RealtimeModel` inline in `session.py`.

**Config validation is four gates, cheapest first.** All of them exist to prevent one failure: a
configuration that is accepted, then rejected by the provider on *every* LLM turn, so the call
connects and the assistant never speaks. See `src/api/validation/assistant_guard.py` for the
full account and `docs/reference/troubleshooting.md` for the operator-facing version.

1. **Pydantic** (`src/api/models/api_schemas/`) — shape, ranges, enums, plus the STT/TTS model
   and Sarvam speaker sets.
2. **`validate_mode_config`** (`api_schemas/config/llm_config.py`) — one rule table for all
   four modes (`REALTIME_MODELS` / `GEMINI_LIVE_MODELS` for pipeline+realtime,
   `OPENAI_CASCADE_MODELS` for cascade, `GPT_LIVE_MODELS` + a reasoning `backend_model` for
   duplex, plus voices and the tool_choice rule). Called from the
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
- `control` — API + SIP dispatcher (`docker/Dockerfile.control`, `docker/requirements-control.txt`)
- `agent` — LiveKit worker only (`docker/Dockerfile.agent`, `docker/requirements-agent.txt`)
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

## Runtime behaviors (user-facing detail: `docs/concepts/`)

- **Web call modes**: voice + text (`lk.chat`), plus opt-in `text_only: true` (disables mic/TTS/STT/recording for pure chatbot). `docs/api/calls/web-call.md`.
- **Passthrough mode**: human web user ↔ SIP phone caller, no AI agent. `docs/api/calls/passthrough.md`.
- **Greetings**: every mode greets first when `assistant_interaction_config.speaks_first=true`. In duplex GPT-Live phrases the greeting itself and may decline.
- **Audio library + prerecorded greeting**: reusable audio assets live in the `audio_assets` collection, managed via the `/audio` router (`upload` accepts any audio format, transcodes to WAV 48 kHz mono via PyAV/bundled-ffmpeg in `src/services/storage/audio_transcode.py`, enforces ≤ 30 s; `list`/`get`/`delete` soft-deletes). Assistants reference one by id through `assistant_greeting_audio = {enabled, audio_id}` (set via `/assistant/create` or `/assistant/update`). When enabled, the worker resolves `audio_id` → `AudioAsset` and plays the S3 WAV via `session.say(audio=...)` instead of model-generating the greeting — saves tokens in both modes. S3 access in `src/services/storage/s3_audio.py` (boto3, direct — not LiveKit egress). Any missing/inactive asset or download/decode failure falls back to the model greeting.
- **Billing**: webhook reports both actual and billable duration; Exotel completed duration measured `answered_at`→`ended_at`. `src/core/billing.py`.

## One-off scripts

`scripts/` holds diagnostics and migrations. Every script, its exact command, and whether it
writes: `dev-docs/operations/scripts.md`. Run migrations as a dry run first; they change data
only with `--apply` (or `--unset` for `migrate_stt_config.py`). Run
`uv run python scripts/check_model_allowlist.py` before editing any model list.

## Webhook contracts

Canonical payload docs (not code):
- End-call webhook: `docs/api/calls/webhook.md`
- Tool webhook: `docs/api/tools/webhook.md`
- Inbound context strategy: `docs/api/inbound-context-strategy/index.md`

## Rule of thumb: where truth lives

| Topic | Source of truth |
|---|---|
| Models, providers, config defaults, values, change-effects | `docs/reference/models.md` (auto-doc'd from the factories) |
| Every config knob for create/update, examples, defaults | `docs/api/assistant/create.md`, `docs/api/assistant/update.md` |
| Cascade mode specifics + validation rules | `docs/concepts/cascade.md`, `dev-docs/subsystems/validation-and-models.md` |
| How the system is built, and why | `dev-docs/` (`architecture.md`, `subsystems/`, `decisions/`) |
| Which mode × LLM × STT × TTS combinations are legal | `docs/reference/compatibility.md` |
| What a failure looks like and which command diagnoses it | `docs/reference/troubleshooting.md` |
| What an external worker must implement to plug into the platform | `docs/guides/` (currently the meeting connector contract) |
| Which models/knobs/speakers exist at all | `src/core/model_support/` (dependency-free; imported by both images) |
| Runtime configuration schemas + the per-mode rule table | `src/api/models/api_schemas/` (`config/llm_config.py`) |
| Guards that need the stored row or a network call | `src/api/validation/assistant_guard.py` |
| LLM / TTS / STT build logic | `src/core/agents/{llm,tts,stt}/factory.py` |

If a doc disagrees with the factory code, **the factory code wins** — fix the doc.

## Guardrails

Each rule below prevents a regression this repo has already shipped once. The full context and
reasoning are in `dev-docs/decisions/` (record number in brackets); read the record before
changing a rule.

- **Model lists come from the API.** Edit any allowlist only after
  `scripts/check_model_allowlist.py`. The retired `gpt-5.1-chat-latest`, `gpt-5.2-chat-latest`,
  `gpt-5.3-chat-latest`, `gpt-5.1`, `gpt-5.4-nano`, the gateway id `chat-latest` and
  `gpt-oss-120b` stay off the cascade allowlist. [0001, 0006]
- **Config is validated four ways before it is stored**, and gates 3–4 fail open on anything that
  is not a clear refusal. `POST /tool/{attach,detach}` re-runs the whole guard. [0001]
- **An omitted optional knob keeps the SDK default.** Factories forward a knob only when it is
  set. ElevenLabs `voice_settings` absent → pass `NOT_GIVEN`, never `None`. Knobs a model ignores
  are a `422` at the API and dropped at call time. [0002, 0006]
- **Error bodies go through `redact_text`**; every provider `api_key` field caps at 500
  characters. [0003]
- **One rule table for every mode.** A new mode or provider extends `validate_mode_config`;
  `enforce_stored_mode_constraints` (`src/api/validation/assistant_guard.py`) re-runs it against
  the stored row. Every provider config is `extra="forbid"`. [0004]
- **Provider plugin quirks are pinned in the factories**: `CartesiaTTSConfig.speed` is float-only
  while `sonic-3` is pinned; Deepgram `nova-*` and `flux-*` are different plugin classes; OpenAI STT
  streams only with `use_realtime`; `gpt-realtime-whisper` is refused. [0004]
- **Gemini runs in `realtime` only.** Mid-session updates are fixed by the plugin pin, so
  `generate_reply()`/`update_instructions()` work on every Live model; `GEMINI_VERTEX_ONLY_MODELS`
  is refused. [0004, 0005]
- **Every accepted speech model has a price.** The Deepgram allowlist is a priced subset of the
  plugin's, and a rated model missing from `docs/reference/pricing.md` fails a test. [0005, 0006]
- **`livekit-agents` is pinned twice**, `~=1.8.8` in `pyproject.toml` and
  `docker/requirements-agent.txt`; bump both together. [0006]

<!-- core-be:start -->
# AGENTS.md — Backend Engineering Rules

<!-- Managed by the core-backend skill pack (core-be-workflow, "Register the
pack"). Agents refresh the text between the core-be markers; edit the pack, not
this block. Repo-specific notes go outside the markers. -->

These rules apply to every agent working in this repository. They cover backend
services written in **Python** (FastAPI, async, uv) and **Node.js** (TypeScript,
Express / Fastify). Skills are installed as a Claude Code plugin, with
`npx skills`, or by copying `.agents/skills/`, so find each one by name. Read
the ones named here before you act.

> Talk first, plan first, then build. Simple, clean, verified code beats clever
> code. Tools enforce style; you enforce correctness, security, and scope.

## Load the skills before you act

This repo uses the `core-be-*` skills. Before any code change, load
`core-be-coding-standards`. For any non-trivial task, load `core-be-workflow`
first; it routes to the other skills. Find them by name (Claude Code plugin
skills appear as `core-backend:core-be-<skill>`).

Skills not installed? Tell the user and suggest one of:

```
/plugin marketplace add shubhamINT/agent_rules
/plugin install core-backend@int-agent-rules
```

```bash
npx skills add shubhamINT/agent_rules      # pick every core-be-* skill
```

Until they are installed, follow the rules in this file.

---

## 1. Always on — every task, however small

These apply to everything, including trivial edits and questions.

| Always-on skill | What it guarantees |
|-----------------|--------------------|
| `core-be-coding-standards` | Clean code, style, module design, the self-review for AI-generated code, and the **bug and smell radar** |
| `core-be-workflow` | Non-trivial work is recorded, scoped with the user, planned, and approved before any code changes |

Always-on behaviour:

1. **Converse before acting.** Understand what the user wants. If the request is
   ambiguous, ask — offer concrete options with a recommended default. Never
   guess scope.
2. **Plan before code** for anything non-trivial (§2). No source edits before
   the user approves the plan.
3. **Bug and smell radar.** While reading code for any reason, watch for bugs,
   security holes, and bad code. Explain each one to the user in plain terms —
   what, where (`file:line`), why it matters, how to fix it (name the fix or
   refactoring). Record it. Do not silently fix anything outside the agreed
   scope; offer a follow-up task. Report security holes immediately.
4. **Structure first.** Before placing or moving code, read the
   the Project structure section at the end of this file. If it is empty, run
   `core-be-structure-service`: detect the current structure, confirm it with the user,
   and record it there.
5. **Help the user understand.** Explain decisions and findings so a developer
   new to the code could follow and apply them. Prefer showing the fix over
   describing it.
6. **Spend tokens on evidence, not words.** Search before reading, read a
   file once, run one test file while iterating, filter logs before reading.
   Chat replies short; files in normal prose. Never skip a check to save
   tokens (`core-be-workflow/references/TOKEN-ECONOMY.md`).

## 2. Classify the task

| Task type | Examples | Skills |
|-----------|----------|--------|
| **Trivial** | answer a question, fix a typo, rename one variable, explain code | Just do it (always-on rules still apply, radar included). No tracking. |
| **Feature** | "add an endpoint", "support X", "integrate Y" | `core-be-workflow` → [`core-be-constitution` once] → `core-be-specify` → `core-be-clarify` → `core-be-plan` → `core-be-tasks` → `core-be-analyze` → approval → `core-be-implement` → `core-be-converge` |
| **Change** | "limit it to 10k rows", "change how X works", "drop support for Y" | `core-be-workflow` → `core-be-change` (edit the spec first) → `core-be-clarify` → `core-be-plan` (delta) → `core-be-tasks` → `core-be-analyze` → approval → `core-be-implement` → `core-be-converge` |
| **Assess** | "should we build X", "is this worth it", a vague idea | `core-be-workflow` → `core-be-assess` → `go` / `needs-clarification` / `kill` |
| **Explain** | "how does X work", "walk me through this flow", "I am new to this code" | `core-be-workflow` → `core-be-explain` |
| **Init** | "set up this repo", "onboard this project", "start a new project", messy `AGENTS.md` / `CLAUDE.md` | `core-be-workflow` → `core-be-init` → first feature through `core-be-specify` |
| **Constitution** | "set up SDD", "project principles" | `core-be-workflow` → `core-be-constitution` |
| **Refactor** | "clean this up", "this code is a mess", "restructure", "reduce duplication" | `core-be-workflow` → `core-be-refactor-code` |
| **Code audit** | "review this code", "check for bad code", "find bugs", "review what the AI wrote" | `core-be-workflow` → `core-be-audit-code` |
| **Security audit** | "security audit", "find vulnerabilities", "is this safe", "OWASP check" | `core-be-workflow` → `core-be-audit-security` |
| **Tests** | "add tests", "raise coverage", "fix the failing suite" | `core-be-workflow` → `core-be-write-tests` |
| **Debug** | "this returns 500", "flaky test", "worked yesterday", "users see wrong data", "it's slow", a pasted stack trace | `core-be-workflow` → `core-be-debug` |
| **Structure** | "structure this repo", "where should this go", "which architecture" | `core-be-workflow` → `core-be-structure-service` |
| **Health endpoint** | "add a health check", "readiness probe" | `core-be-workflow` → `core-be-add-health-endpoint` |

Unsure whether a task is trivial? Treat it as non-trivial. A change that touches
more than one file, any trust boundary (auth, input parsing, external calls,
secrets), or any public interface is never trivial.

### Specs (spec-driven development)

`feature` and `change` tasks are spec-driven. Files, all committed with the code:

- `specs/constitution.md` — project principles, each with a yes/no gate question
  (`core-be-constitution`).
- `specs/<NNN-topic>/spec.md` — what and why, numbered acceptance criteria
  (`core-be-specify`, edited first by `core-be-change`).
- `specs/<NNN-topic>/plan.md` — the durable design (`core-be-plan`).

Order: spec, then plan, then tasks, then analysis, then user approval, then
code, then converge. Edit the spec first, never the code first. Done means
`core-be-converge` returned `Converged`. Refactors, audits, security reviews,
debugging, and test work change no behaviour and need no spec.

### Guard

An edit guard (a command hook that Claude Code, Codex, Cursor, Copilot, Gemini CLI, and
Windsurf can run: `core-be-workflow/scripts/sdd-hook.sh`) and a validator
(`core-be-workflow/scripts/sdd-check.sh`) back these rules. A source edit needs an approved
task row in `agent-tracking/INDEX.md`; a `feature` or `change` task also needs its
spec first. You may not stop mid-implementation before `Verdict: Converged` is in
`progress.md`. When the guard says no, do what its message says. Never edit the
hook, its config, or the scripts, and never set `SDD_GUARD`. CI runs
`sdd-check.sh ci` on the committed files, so a skipped step fails the build.

## 3. The non-trivial workflow (mandatory)

Follow the `core-be-workflow` skill. In short:

1. **Record first.** Create `agent-tracking/` if missing and write the user's
   request verbatim to `agent-tracking/plans/<slug>/scope.md`, plus a row in
   `agent-tracking/INDEX.md`. Everything after — questions, answers, research,
   plan, progress, report — lands in the same folder.
2. **Scope with the user.** Ask until it is unambiguous: which paths, how deep,
   what is out of scope, constraints, success criteria, and the report format
   (**HTML by default, or Markdown**). Log questions and answers in `scope.md`.
   Reports are visual: a Current → Target diagram for every change
   (`core-be-workflow/references/VISUAL-REPORT.md`). Audit and security reports load no
   external scripts.
3. **Research**, then **plan**: write `tasks.md`, show it, and wait for explicit
   approval.
4. **Execute the approved plan only.** Log each step in `progress.md`. New scope
   found mid-task: stop, record it, ask.
5. **Report** into `agent-tracking/reports/` and update `INDEX.md`.

**Think like the senior engineer on call for it.** Features get a system design
pass (`core-be-build-feature/references/system-design.md`): concurrency,
idempotency, failure modes, limits, compatibility — sized to the real risk.
Every code change ships in small reversible steps with a concrete rollback
(`core-be-workflow/references/SAFE-DELIVERY.md`).

**Use subagents where they add independence or parallelism**
(`core-be-workflow/references/SUBAGENTS.md`): read-only `investigator`s for
audit fan-out and debugging hypotheses, a `test-writer` that writes tests from
the contract, and a fresh-context `reviewer` before every report (a separate
pass when the host has no subagents; a self-pass is enough for a diff under
about 50 lines). Brief a
general-purpose subagent with the role text from `SUBAGENTS.md`. Verify what
they return.

`agent-tracking/` belongs in version control, but the user commits it — see rule 12.

## 4. Coding rules

1. **Read before you change.** Never edit code you have not read. Follow the
   repo's existing patterns and recorded structure.
2. **Simplest thing that works.** No speculative abstractions, config options, or
   layers "for later". Delete dead code; never leave commented-out blocks.
3. **Never invent an API.** Every import, package, function, method, flag, and
   config key must exist in the installed version. Verify in the lockfile and
   the package source or official docs. Never add a dependency you have not
   confirmed exists under that exact name.
4. **Handle errors explicitly.** No bare `except:` / empty `catch {}`. Fail
   closed at trust boundaries; degrade gracefully only where the contract says so.
5. **Validate all external input** (bodies, headers, query params, files, env,
   upstream responses) with a schema: pydantic (Python) or zod (Node).
6. **No secrets in code, logs, errors, or tests.** One settings module reads the
   environment; `.env.example` lists every variable with safe placeholders.
7. **Every outbound call has a timeout. Every query is parameterised. Every
   resource-scoped read checks ownership.**
8. **Tests ship with the change** and pass offline. Coverage floor 80%; never
   lower it, never loosen an assertion to go green.
9. **Docs stay true.** README endpoint, env, and structure sections change in
   the same change as the code.
10. **Do not reformat code you did not otherwise change.** Keep diffs reviewable.
11. **No git side effects unless asked.** Do not commit, branch, push, or delete
    lockfiles. Leave changes in the working tree for the user to review.
12. **Parallel agents share one board.** When other agents work here too, join
    `agent-tracking/board/` with `core-be-workflow/scripts/board.sh`: claim a
    task and lock its files before editing, never wait by re-reading code, and
    `leave` when done. The last agent out removes the board
    (`core-be-workflow/references/PARALLEL-AGENTS.md`).

## 5. Language baselines

| | Python | Node.js |
|--|--------|---------|
| Runtime | Python 3.12+, `uv` | Node 24 LTS, TypeScript `strict` |
| Style guide | Google Python Style Guide | Google TypeScript Style Guide |
| Format + lint | Ruff (`ruff format`, `ruff check`) | Prettier + ESLint 9 flat config + typescript-eslint |
| Types | mypy or pyright, strict on new code | `tsc --noEmit`, no `any` |
| Security lint | Ruff `S` rules, Semgrep | eslint-plugin-security, Semgrep |
| Dependencies | `pip-audit` | `npm audit` / `pnpm audit` |
| Secrets | gitleaks | gitleaks |
| Complexity | Ruff `C901`, max 10 | ESLint `complexity`, max 10 |
| Tests | pytest (`core-be-write-tests`) | vitest (`core-be-write-tests`) |

Every section of the Google Python, TypeScript and JavaScript style guides is
indexed (enforced by tool / rule / override) in
`references/{python,typescript,javascript}-style.md` of the
`core-be-coding-standards` skill; the full guides are bundled in its
`references/google/`.

## 6. Skill index

| Skill | Kind | Use when |
|-------|------|----------|
| `core-be-coding-standards` | always on | Writing, changing, or judging any code |
| `core-be-workflow` | always on | Any non-trivial task: record, scope, plan, approve, report |
| `core-be-constitution` | task | Creating or amending `specs/constitution.md` |
| `core-be-assess` | task | Deciding go / needs-clarification / kill for an idea before any spec |
| `core-be-explain` | task | Explaining how existing code works: read-only trace, HTML page |
| `core-be-init` | task | Setting up or repairing a repo for the pack; fixing `AGENTS.md` and `CLAUDE.md`; the project brief |
| `core-be-specify` | task | Writing the spec for a new feature |
| `core-be-change` | task | Changing an existing feature: spec first |
| `core-be-clarify` | task | Resolving open questions in a spec |
| `core-be-plan` | task | Writing the durable design plan for a spec |
| `core-be-tasks` | task | Turning spec and plan into the test-first checklist |
| `core-be-analyze` | task | Read-only consistency check before approval |
| `core-be-implement` | task | Building from the approved checklist |
| `core-be-converge` | task | Checking code against the spec; verdict `Converged` |
| `core-be-build-feature` | task | Building new behaviour |
| `core-be-refactor-code` | task | Changing structure without changing behaviour; architecture review |
| `core-be-audit-code` | task | Finding bugs, bad code, weak tests, AI-generated-code failures |
| `core-be-audit-security` | task | Finding vulnerabilities (OWASP, ASVS, CWE) |
| `core-be-write-tests` | task | Writing or fixing tests; coverage |
| `core-be-debug` | task | Reproducing, root-causing, and fixing bugs, flaky tests, slowness |
| `core-be-structure-service` | task | Detecting, choosing, recording, applying the project structure |
| `core-be-add-health-endpoint` | task | Adding or fixing `GET /health` |
<!-- core-be:end -->

## Project structure

<!-- Repo-owned. Recorded from the layout that already exists (detected, not
redesigned); change it only through `core-be-structure-service` with the user. -->

**Pattern: layered, split by process.** Three runtimes share one package: the FastAPI control
plane (`src/api/`), the LiveKit worker (`src/core/agents/`), and the SIP/RTP bridge plus outbound
dispatcher (`src/services/`). `src/core/` holds what more than one of them needs.

```text
agent_run.py / server_run.py / sip_dispatcher_run.py   # one entry point per process
src/
├── api/                    # HTTP layer — control image only
│   ├── routes/             # one router per resource, mounted in server.py
│   ├── models/api_schemas/ # Pydantic request schemas + validators, split by domain
│   ├── validation/         # guards that need the stored row or a provider call
│   └── dependencies/       # auth (get_current_user / get_super_admin)
├── core/                   # shared by every process
│   ├── agents/             # LiveKit worker: session, agent class, llm/ stt/ tts/ factories
│   ├── model_support/      # dependency-free model/provider rules (imported by both images)
│   ├── db/                 # Beanie documents + aggregations
│   ├── pricing/ providers/ # rate tables, provider key masking
│   └── config.py           # the only module that reads settings from the environment
└── services/               # adapters to external systems (Exotel SIP, S3, SMTP, LiveKit, vendors)
tests/                      # flat, test_<topic>.py, stdlib unittest
scripts/                    # one-off migrations + diagnostics
docs/                       # published MkDocs site (every page in mkdocs.yml nav)
agent-tracking/             # agent plans, research, reports — never in mkdocs.yml
```

**Dependency rules.** `api/` may import `core/` and `services/`; `core/agents/` may import
`services/` but never `api/`; `core/model_support/` imports only the stdlib, `httpx`,
`src.core.config` and `src.core.logger` — never `livekit` or `fastapi`, because the control image
has no `livekit-agents` and the agent image has no FastAPI.

| New thing | Goes in |
|---|---|
| Endpoint | `src/api/routes/<resource>.py`, schema in `src/api/models/api_schemas/` |
| Rule about which model accepts which knob | `src/core/model_support/` |
| Provider plugin construction (STT/TTS/LLM) | `src/core/agents/{stt,tts,llm}/factory.py` |
| Client for a third-party system | `src/services/<vendor>/` |
| Collection | `src/core/db/db_schemas.py` (+ register in `database.py`) |
| Env variable | `src/core/config.py`, README environment table |
| Several new related files | a purpose-named package, decided before writing them |
