# LiveKit Agent Service

A backend for real-time voice assistants. You configure an assistant (prompt, voice, models,
tools) through a REST API, and it answers or places phone calls, joins web calls and Google Meet
meetings, and reports every call back to you by webhook.

It is built on [LiveKit Agents](https://docs.livekit.io/agents/) `~=1.8.8`, FastAPI and MongoDB,
and runs fully self-hosted: no LiveKit Cloud features are required.

This README is for **developers of this repository**: what the system is made of, how to run it,
and where to look next. To *use* the hosted API, read the public docs at
<https://api-livekit-vyom.indusnettechnologies.com/documentation/>.

## Assistant modes

`assistant_mode` decides how many models are in the conversation loop.

| Mode | What runs | LLM vendor | Separate TTS? |
|---|---|---|---|
| `pipeline` (default) | Realtime model hears and thinks; a TTS provider speaks | OpenAI | Yes |
| `realtime` | One model hears, thinks and speaks | Gemini (default) or OpenAI | No |
| `cascade` | Separate STT → LLM → TTS, each swappable | OpenAI | Yes |
| `duplex` | OpenAI GPT-Live listens while it speaks; a reasoning model runs the tools | OpenAI | No |

Which models, voices and settings each mode accepts: [Compatibility Matrix](docs/reference/compatibility.md).

## Architecture

Three processes share one codebase and one MongoDB.

```mermaid
flowchart LR
    client["Your app / Phone caller"] --> api["API server<br/>FastAPI · server_run.py"]
    api --> mongo[("MongoDB")]
    mongo -- "outbound queue<br/>(Change Stream)" --> disp["SIP dispatcher<br/>sip_dispatcher_run.py"]
    disp -- "SIP / RTP" --> phone["Exotel / Twilio"]
    disp --> lk["LiveKit server"]
    api --> lk
    lk -- "dispatches job" --> worker["Agent worker<br/>agent_run.py"]
    worker --> ai["OpenAI · Gemini · STT/TTS providers"]
    worker --> mongo
```

| Process | Entry point | Job |
|---|---|---|
| API server | `server_run.py` | REST API, validation, queues outbound calls, serves the docs site and the docs MCP |
| SIP dispatcher | `sip_dispatcher_run.py` | Exotel inbound SIP listener + outbound dispatch loop. Exactly one per deployment. In development the API server runs it for you (`ENABLE_SIP_LISTENER` / `ENABLE_DISPATCHER`). |
| Agent worker | `agent_run.py` | Joins LiveKit rooms and runs the conversation (`src/core/agents/session.py`) |

How a call moves through these processes: [How it works](docs/concepts/index.md) for the user's view,
[developer architecture](dev-docs/architecture.md) for the code behind each box.

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Docker (for the local MongoDB below), or any MongoDB **replica set**: the dispatcher uses
  Change Streams, which a standalone `mongod` does not support
- [LiveKit server](https://docs.livekit.io/transport/self-hosting/local/) (`livekit-server`)
- An API key for at least one model provider. `OPENAI_API_KEY` alone covers the defaults of
  `pipeline`, `cascade` and `duplex`; `realtime` defaults to Gemini (`GOOGLE_API_KEY`)
- For phone calls only: an Exotel SIP trunk (inbound and outbound) or Twilio (outbound)

## Quickstart

1. **Start MongoDB as a single-node replica set.**

   ```bash
   docker run -d --name lvk-mongo -p 27017:27017 mongo:8 --replSet rs0 --bind_ip_all
   docker exec lvk-mongo mongosh --quiet --eval \
     'rs.initiate({_id: "rs0", members: [{_id: 0, host: "localhost:27017"}]})'
   ```

2. **Start LiveKit in dev mode** (API key `devkey`, secret `secret`, on `ws://127.0.0.1:7880`).
   Install it first with `brew install livekit` or `curl -sSL https://get.livekit.io | bash`.

   ```bash
   livekit-server --dev
   ```

3. **Configure.** Copy the example file, then set the values below in `.env`. Keep them in
   `.env` rather than exporting them in the shell: the worker loads `.env` over the
   environment.

   ```bash
   cp .env.example .env
   ```

   ```ini
   MONGODB_URL=mongodb://localhost:27017/?replicaSet=rs0
   LIVEKIT_URL=ws://127.0.0.1:7880
   LIVEKIT_API_KEY=devkey
   LIVEKIT_API_SECRET=secret
   OPENAI_API_KEY=sk-...
   ENABLE_SIP_LISTENER=false   # true only with a public IP and an Exotel trunk
   ```

4. **Install and run** the API and the worker, each in its own terminal.

   ```bash
   uv sync
   uv run server_run.py          # API on http://localhost:8000
   uv run agent_run.py dev       # agent worker
   ```

5. **Check it.** `status` should be `ok`, with MongoDB and LiveKit both `ok: true`.
   Then create your first API key.

   ```bash
   curl -s localhost:8000/health
   curl -s -X POST localhost:8000/auth/create-key \
     -H 'Content-Type: application/json' \
     -d '{"user_name": "Dev", "user_email": "dev@example.com"}'
   ```

From here, follow [Getting Started](docs/getting-started/index.md) to create an assistant and
make a web call. The interactive API explorer is at <http://localhost:8000/docs>.

## Environment variables

`.env.example` lists every variable. Most are read in `src/core/config.py`; the Exotel SIP/RTP
bridge reads its own in `src/services/exotel/custom_sip_reach/config.py` and `inbound_bridge.py`.
An empty default means unset. A provider key left empty disables that provider unless an
assistant supplies its own key.

| Variable | Default | Note |
|---|---|---|
| `PORT` | `8000` | API listen port |
| `GUNICORN_WORKERS` | `1` | API worker processes (`server_run.py`) |
| `BACKEND_URL` | `http://localhost:8000` | URL the worker calls back for webhook routing |
| `ENABLE_SIP_LISTENER` | `true` | `false` on the API container when the `sip_dispatcher` container runs |
| `ENABLE_DISPATCHER` | `true` | `false` on the API container when the `sip_dispatcher` container runs |
| `MONGODB_URL` | `mongodb://admin:secretpassword@localhost:27017` | Dev default only — always set in production |
| `DATABASE_NAME` | `livekit_db` | |
| `LIVEKIT_URL` | `ws://127.0.0.1:7880` | |
| `LIVEKIT_API_KEY` | `devkey` | Dev default only |
| `LIVEKIT_API_SECRET` | `secret` | Dev default only |
| `OPENAI_API_KEY` | — | Pipeline, cascade, duplex, OpenAI STT; also the config guards |
| `GOOGLE_API_KEY` | — | Gemini realtime |
| `CARTESIA_API_KEY` | — | Cartesia STT/TTS |
| `SARVAM_API_KEY` | — | Sarvam STT/TTS (default STT) |
| `DEEPGRAM_API_KEY` | — | Deepgram STT (cascade) |
| `ELEVENLABS_API_KEY` | — | ElevenLabs STT + TTS |
| `MISTRAL_API_KEY` | — | Mistral TTS |
| `HEALTH_PROBE_TIMEOUT_S` | `3` | Per-probe deadline for `GET /health` |
| `OPENAI_MODEL_CACHE_TTL` | `3600` | Seconds the `GET /v1/models` answer is cached by the config guard |
| `MAX_CONCURRENT_JOBS` | `12` | Live telephony calls (incl. passthrough) |
| `MAX_CONCURRENT_WEB_CALLS` | `40` | Live web calls — not load-tested, set from your own test |
| `MAX_CONCURRENT_MEETING_CALLS` | `4` | Live meeting calls |
| `MAX_CONCURRENT_SESSIONS` | `48` | Hard ceiling across all call types; the worker stops taking jobs here |
| `MAX_CONCURRENT_INVITE_SETUPS` | `24` | Inbound INVITEs in setup, not live calls |
| `MEETING_CONNECTOR_AGENT_NAME` | `meet-connector` | LiveKit dispatch name of the meeting connector worker |
| `MEETING_CONNECTOR_JOIN_TIMEOUT_SECONDS` | `120` | Connector must appear in the room by then |
| `MEETING_CONNECTOR_READY_TIMEOUT_SECONDS` | `360` | Time for a human to admit the bot |
| `END_CALL_WEBHOOK_TIMEOUT` | `30` | Read timeout in seconds (`docs/api/calls/webhook.md`) |
| `END_CALL_WEBHOOK_ATTEMPTS` | `3` | Retries on timeout / connection error / 429 / 5xx |
| `AWS_ACCESS_KEY_ID` | — | Recording + audio-library upload |
| `AWS_SECRET_ACCESS_KEY` | — | |
| `AWS_REGION` | `us-east-1` | |
| `S3_BUCKET_NAME` | — | |
| `S3_RECORDINGS_PREFIX` | `recordings/` | |
| `S3_GREETING_PREFIX` | `greeting_audio/` | |
| `SMTP_HOST` | `smtp.sendgrid.net` | Email tool only |
| `SMTP_PORT` | `587` | |
| `SMTP_USER` | `apikey` | |
| `SMTP_PASSWORD` | — | |
| `FROM_EMAIL` | `noreply@yourdomain.com` | |
| `FROM_NAME` | `Your App Name` | |
| `LOG_LEVEL` | `INFO` | |
| `LOG_JSON_FORMAT` | `False` | |
| `LOG_FILE` | `app.log` | |
| `LOG_MAX_BYTES` | `10485760` | |
| `LOG_BACKUP_COUNT` | `5` | |
| `EXOTEL_SIP_HOST` | `pstn.in1.exotel.com` | |
| `EXOTEL_SIP_PORT` | `5070` | |
| `EXOTEL_CUSTOMER_IP` | — | Public/Elastic IP of this host — never `0.0.0.0` or a private IP |
| `EXOTEL_CUSTOMER_SIP_PORT` | `5061` | |
| `EXOTEL_MEDIA_IP` | — | Public/Elastic IP Exotel sends RTP to |
| `EXOTEL_CALLER_ID` | `08044319240` | Default outbound caller ID |
| `EXOTEL_FROM_DOMAIN` | `lokaviveka1m.pstn.exotel.com` | |
| `EXOTEL_AUTH_USERNAME` | — | SIP digest auth |
| `EXOTEL_AUTH_PASSWORD` | — | SIP digest auth |
| `EXOTEL_SIP_ALLOWED_IPS` | — | Inbound INVITE source allowlist |
| `INBOUND_SIP_LISTEN` | `true` | |
| `INBOUND_RING_UNTIL_AGENT_READY` | `true` | Keep the caller ringing until the agent can speak |
| `INBOUND_MAX_RING_SECONDS` | `15` | Answered on expiry, never dropped |
| `INBOUND_MEDIA_READY_TIMEOUT` | `20` | Bridge must bind RTP and join the room by then |
| `SIP_BRIDGE_PORT_RANGE_START` | `41000` | Falls back to `RTP_PORT_START` |
| `SIP_BRIDGE_PORT_RANGE_END` | `42000` | Falls back to `RTP_PORT_END` |
| `NO_RTP_AFTER_ANSWER_SECONDS` | `60` | |
| `RTP_SILENCE_TIMEOUT_SECONDS` | `30` | |

## Tests, lint and docs

```bash
uv run python -m unittest discover -s tests          # full suite, runs offline
uv run python -m unittest tests/test_session_lifecycle.py -v   # one file
uvx ruff check <paths>                               # lint the files you touched
uv run mkdocs serve -a 127.0.0.1:8001              # docs site (8000 is the API)
uv run mkdocs build --strict                         # must pass before merging docs
uv run python scripts/check_mermaid.py               # the build cannot catch a broken diagram
```

## Deploy

Three images, chosen by `./deploy.sh <mode>` (Docker Compose profiles):

| Mode | Runs | Image |
|---|---|---|
| `control` | API + SIP dispatcher | `docker/Dockerfile.control` (`docker/requirements-control.txt`) |
| `agent` | Agent worker only; add hosts for capacity | `docker/Dockerfile.agent` (`docker/requirements-agent.txt`) |
| `full` | Everything on one host | `Dockerfile` |

On a multi-host setup, set `ENABLE_SIP_LISTENER=false` and `ENABLE_DISPATCHER=false` on the API,
run exactly **one** `sip_dispatcher`, and keep `EXOTEL_CUSTOMER_IP` / `EXOTEL_MEDIA_IP` on the
control-plane host. Set the `MAX_CONCURRENT_*` caps from a load test, not from the defaults.
Images, hosts and sizing: [Deployment](dev-docs/operations/deployment.md).

## API at a glance

Every endpoint needs `Authorization: Bearer <lvk_ api key>` unless noted; admin routes need a key
whose user has `is_super_admin`. Payloads and examples for each route are in [`docs/api/`](docs/api/).

| Prefix | Purpose | Docs |
|---|---|---|
| `GET /health` | No auth. Pings MongoDB and LiveKit; **always HTTP 200 — read `data.status`** (`ok` / `degraded`) | [health](docs/api/health.md) |
| `/auth` | Create (no auth) and check `lvk_` API keys | [authentication](docs/api/authentication.md) |
| `/assistant` | Create, update, list, delete assistants; per-assistant call logs | [assistant](docs/api/assistant/index.md) |
| `/tool` | Function tools; attach/detach to assistants | [tools](docs/api/tools/index.md) |
| `/audio` | Audio library for prerecorded greetings | [audio](docs/api/audio/index.md) |
| `/sip` | Outbound trunks (`twilio`, `exotel`) | [sip](docs/api/sip/create.md) |
| `/call` | Queue outbound calls, passthrough calls, call records and usage. `POST /call/end_call` is an unauthenticated echo for testing a webhook receiver | [calls](docs/api/calls/index.md) |
| `/web_call` | LiveKit token for a browser or app call | [web call](docs/api/calls/web-call.md) |
| `/meeting_call` | Send an assistant into a Google Meet | [meeting call](docs/api/calls/meeting-call.md) |
| `/inbound` | Map inbound numbers to assistants (Exotel) | [inbound](docs/api/inbound/index.md) |
| `/inbound_context_strategy` | Webhook that supplies caller context on inbound calls | [strategy](docs/api/inbound-context-strategy/index.md) |
| `/logs` | Activity log: tool calls, context lookups, webhook deliveries | [activity logs](docs/api/activity-logs.md) |
| `/stt` | Speech to text transcription (`POST /stt/transcribe`) | [speech to text](docs/api/stt.md) |
| `/tts` | Text to speech synthesis (`POST /tts/synthesize`) | [text to speech](docs/api/tts.md) |
| `/llm` | Chat completion & SSE streaming (`POST /llm/chat`) | [LLM](docs/api/llm.md) |
| `/analytics`, `/admin/analytics` | Call and token analytics; cross-tenant for super admins | [analytics](docs/api/analytics/index.md) |
| `/documentation`, `/mcp` | No auth. The docs site, and the same docs as an MCP server for AI agents | [MCP](docs/api/mcp.md) |

Every response, including errors, uses one envelope (`src/api/models/response_models.py`). On
failure `success` is `false` and `data` is `{}`, or the field errors for a `422`.

```json
{ "success": true, "message": "Human-readable result", "data": { } }
```

## Project structure

```text
server_run.py · sip_dispatcher_run.py · agent_run.py   # one entry point per process
src/
├── api/              # HTTP layer: routes/, request schemas, validation guards, auth
├── core/
│   ├── agents/       # LiveKit worker: session, agent class, llm/ stt/ tts/ factories
│   ├── model_support/# which models and settings each provider accepts (no framework imports)
│   ├── db/           # MongoDB documents (Beanie) and analytics pipelines
│   ├── pricing/      # provider rate tables and cost estimates
│   └── config.py     # the only place that reads environment variables
└── services/         # adapters: Exotel SIP/RTP bridge, outbound dispatcher, S3, SMTP, LiveKit
tests/                # stdlib unittest, one file per topic
scripts/              # migrations and diagnostics (check_model_allowlist.py, replay_cascade_request.py, …)
docs/                 # public MkDocs site, also served over MCP — what the platform does
dev-docs/             # developer docs, not published — how it is built and why
docker/ · deploy.sh   # container images and deployment
agent-tracking/       # coding-agent plans and reports (not published)
```

Layering rules and where new code goes: [`AGENTS.md`](AGENTS.md#project-structure).

## Data stores

MongoDB through Beanie (`src/core/db/db_schemas.py`); recordings and greeting audio in S3.

| Collection | Keyed by | Holds |
|---|---|---|
| `api_keys` | `api_key`, `user_email` (both unique) | API keys and the `is_super_admin` flag |
| `assistants` | `assistant_id` | Mode, prompts, LLM / STT / TTS config, greeting audio ref |
| `audio_assets` | `audio_id` | Audio-library metadata; the WAV lives in S3 |
| `tools` | `tool_id` | Function-tool definitions and their webhook |
| `outbound_sip` | `trunk_id` | Outbound trunks (`twilio` / `exotel`) |
| `inbound_sip` | `inbound_id` | Inbound number → assistant mappings |
| `inbound_context_strategies` | `strategy_id` | Caller-context webhook settings |
| `outbound_call_queue` | `queue_id` | Queued outbound calls and their dispatch state |
| `call_records` | `room_name` | One row per call: transcript, durations, end reason |
| `usage_records` | `room_name` (1:1 with `call_records`) | Per-component usage and estimated cost |
| `activity_logs` | `user_email` | Tool calls, context lookups, webhook deliveries |

## Stack

| Layer | Technology |
|---|---|
| Language / packaging | Python 3.12+, uv |
| HTTP API | FastAPI served by Gunicorn |
| Voice runtime | LiveKit Agents `~=1.8.8` (OpenAI, Google, Cartesia, Deepgram, ElevenLabs, Sarvam plugins), local Silero VAD |
| Telephony | Custom Exotel SIP/RTP bridge; Twilio via LiveKit SIP |
| Database / storage | MongoDB via Beanie; S3 via boto3; PyAV for audio transcoding |
| Docs | MkDocs Material, served to agents over MCP |
| Tests | stdlib `unittest` |

## Where to read next

| You want to… | Read |
|---|---|
| Use the API: payloads, webhooks, examples | [Public docs](docs/index.md) — hosted at `/documentation`, and over MCP at `/mcp` |
| Understand how a call flows through the system | [How it works](docs/concepts/index.md) (public), then [Architecture](dev-docs/architecture.md) |
| Change a subsystem, add a model, provider or endpoint | [Developer docs](dev-docs/index.md): subsystems, how-to recipes, decisions |
| Run a diagnostic or migration script | [Scripts](dev-docs/operations/scripts.md) |
| Know which models, voices and settings exist | [Models & Providers](docs/reference/models.md), [Compatibility Matrix](docs/reference/compatibility.md) |
| Debug a silent call, a busy tone or a missing webhook | [Troubleshooting](docs/reference/troubleshooting.md) |
| See what changed between versions | [Changelog](docs/changelog.md) |
| Change code in this repo (rules for people and coding agents) | [`AGENTS.md`](AGENTS.md) |

## Licence

No licence is declared: the repository has no `LICENSE` file and `pyproject.toml` has no
`license` field. Add one before distributing the code.
