# LiveKit Agent Service

FastAPI backend plus LiveKit worker for real-time voice assistants with OpenAI Realtime and multiple TTS providers.

## What This Project Does

- Manages assistants, tools, SIP trunks, API keys, and call workflows.
- Runs voice agents in LiveKit rooms.
- Supports web calls with both text (`lk.chat`) and voice input.
- Supports outbound calling and Exotel inbound routing.
- Stores transcripts and call records in MongoDB.
- Sends post-call webhook notifications.
- Writes activity logs for tool calls, inbound context lookup, and end-call webhook delivery.

## Provider Support

- Outbound calls: `twilio` and `exotel`.
- Inbound calls: `exotel` only.
- Twilio inbound is not implemented.

## Exotel Outbound Lifecycle

- Exotel outbound API calls return `202 Accepted` while SIP setup continues asynchronously.
- Final call outcomes are delivered through end-call webhook payloads (`completed`, `busy`, `no_answer`, `timeout`, `failed`, etc.).
- Exotel outbound recording starts only after the bridge signals `call_answered` (after successful answer path).
- Trunk/provider mismatch is rejected at API level (`trunk_type` must match `call_service`).

## Architecture

1. API service (`src/api/server.py`) exposes REST endpoints.
2. Worker (`src/core/agents/session.py`) joins LiveKit rooms and runs the assistant.
3. MongoDB stores assistants, tools, trunks, call records, and logs.
4. LiveKit handles media transport and room orchestration.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- MongoDB
- LiveKit server (cloud or self-hosted)
- API keys for providers you use (OpenAI, Cartesia/Sarvam/ElevenLabs, LiveKit)

## Environment Variables

Create `.env` in the project root.

```ini
PORT=8000
BACKEND_URL=http://localhost:8000

MONGODB_URL=mongodb://admin:secretpassword@localhost:27017
DATABASE_NAME=livekit_db

LIVEKIT_URL=ws://127.0.0.1:7880
LIVEKIT_API_KEY=devkey
LIVEKIT_API_SECRET=secret

OPENAI_API_KEY=<your-openai-api-key>
CARTESIA_API_KEY=<optional>
SARVAM_API_KEY=<optional>
ELEVENLABS_API_KEY=<optional>

AWS_ACCESS_KEY_ID=<optional-for-recording-upload>
AWS_SECRET_ACCESS_KEY=<optional-for-recording-upload>
AWS_REGION=us-east-1
S3_BUCKET_NAME=<optional-for-recording-upload>
S3_RECORDINGS_PREFIX=recordings/

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

Start API server:

```bash
uv run server_run.py
```

Start worker in another terminal:

```bash
uv run -m src.core.agents.session dev
```

Optional Docker flow:

```bash
docker-compose up --build
```

Run unit tests:

```bash
uv run python -m unittest discover -s tests -v
```

## Documentation

- MkDocs source lives in `docs/`.
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
- `/inbound`
- `/inbound_context_strategy`
- `/logs`
- `/web_call/get_token`

## Project Structure

```text
api_livekit/
├── README.md
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── docker-compose.yml
├── mkdocs.yml
├── server_run.py
├── assets/
│   └── audio/
├── docs/
├── tests/
├── src/
│   ├── api/
│   │   ├── dependencies/
│   │   ├── models/
│   │   ├── routes/
│   │   └── server.py
│   ├── core/
│   │   ├── agents/
│   │   ├── db/
│   │   ├── config.py
│   │   └── logger.py
│   └── services/
│       ├── elevenlabs/
│       ├── email/
│       ├── exotel/
│       └── livekit/
└── scripts/
```
