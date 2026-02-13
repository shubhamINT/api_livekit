# LiveKit Agent Service

A production-ready service for deploying real-time AI voice agents using LiveKit, OpenAI Realtime API, and Cartesia/Sarvam TTS. This service provides a REST API for managing assistants, SIP trunks, and triggering outbound calls, along with a robust agent worker for handling real-time interactions.

## 🚀 Features

- **Real-time AI Agents**: Powered by OpenAI Realtime API (GPT-4o) and Cartesia/Sarvam TTS.
- **SIP Support**: Create and manage SIP outbound trunks (Twilio/Exotel) for telephony integration.
- **Outbound Calls**: Trigger programmatic outbound calls to phone numbers (currently supporting Twilio).
- **Dynamic Assistants**: Create and configure assistants with custom prompts, voices (Cartesia), speakers (Sarvam), and start instructions.
- **Call Recording**: Automatic call recording with LiveKit Egress.
- **Transcripts**: Real-time transcription storage in MongoDB.
- **Webhooks**: Automatic webhook notifications for call completion with detailed analytics.
- **Secure API**: API Key authentication for all management endpoints.

## 🛠️ Tech Stack

- **Framework**: FastAPI (Python 3.12+)
- **Real-time Communication**: LiveKit
- **Database**: MongoDB (with Beanie ODM)
- **AI/LLM**: OpenAI Realtime API
- **TTS**: Cartesia (Sonic-3) & Sarvam (Bulbul:v3)
- **Deployment**: Docker & Docker Compose

## 🏗️ Architecture

1. **API Service**: Manages resources (Assistants, API Keys, Trunks) and triggers calls.
2. **Agent Worker**: Connects to LiveKit rooms to handle AI logic (STT, LLM, TTS).
3. **LiveKit Server**: Handles real-time audio/video transport.
4. **MongoDB**: Stores configuration, call records, and transcripts.
5. **Webhooks**: Pushes call data to external services upon completion.

## 📋 Prerequisites

- Docker & Docker Compose
- LiveKit Server (Cloud or Self-hosted)
- MongoDB Instance
- API Keys:
  - OpenAI API Key
  - Cartesia API Key
  - Sarvam API Key
  - LiveKit API Key & Secret
  - AWS S3 Credentials (for recordings)

## 🔧 Installation & Setup

1. **Clone the repository**:

   ```bash
   git clone <repository-url>
   cd api_livekit
   ```

2. **Configure Environment Variables**:
   Create a `.env` file in the root directory:

   ```ini
   # Server Configuration
   PORT=8000

   # MongoDB
   MONGODB_URL=mongodb://admin:secretpassword@localhost:27017
   DATABASE_NAME=livekit_db

   # LiveKit
   LIVEKIT_URL=wss://<your-livekit-domain>
   LIVEKIT_API_KEY=<your-api-key>
   LIVEKIT_API_SECRET=<your-api-secret>

   # AI Providers
   OPENAI_API_KEY=<your-openai-key>
   CARTESIA_API_KEY=<your-cartesia-key>
   SARVAM_API_KEY=<your-sarvam-key>

   # SMTP Configuration (for emails)
   SMTP_HOST=smtp.sendgrid.net
   SMTP_PORT=587
   SMTP_USER=apikey
   SMTP_PASSWORD=<your-smtp-password>
   FROM_EMAIL=noreply@yourdomain.com
   FROM_NAME="Your App Name"

   # AWS S3 (for recordings)
   AWS_ACCESS_KEY_ID=<your-access-key>
   AWS_SECRET_ACCESS_KEY=<your-secret-key>
   AWS_REGION=us-east-1
   S3_BUCKET_NAME=<your-bucket-name>

   # Backend Configuration
   BACKEND_URL=http://localhost:8000
   ```

3. **Run with Docker Compose**:

   ```bash
   docker-compose up --build
   ```

   This will start both the API service and the Agent Worker.

## 📖 API Documentation

The API runs on port `8000` by default. Swagger UI is available at `http://localhost:8000/docs`.

### Authentication

All endpoints require a valid API Key.
First, create an initial API Key (public endpoint):

**POST** `/auth/create-key`

```json
{
  "user_name": "Admin User",
  "org_name": "My Org",
  "user_email": "admin@example.com"
}
```

Response:

```json
{
  "success": true,
  "data": {
    "api_key": "lvk_..."
  }
}
```

**Use this `api_key` in the `x-api-key` header for all subsequent requests.**

### Assistants

**POST** `/assistant/create`
Create a new AI assistant configuration.

```json
{
  "assistant_name": "Support Agent",
  "assistant_description": "Customer support bot",
  "assistant_prompt": "You are a helpful assistant. User name is {{name}}.",
  "assistant_tts_model": "cartesia",
  "assistant_tts_voice_id": "248be419-3632-4f38-9500-05f963499d7e",
  "assistant_start_instruction": "Hello {{name}}, how can I help?",
  "assistant_end_call_url": "https://your-webhook.com/call-end"
}
```

_For Sarvam TTS:_

```json
{
  ...
  "assistant_tts_model": "sarvam",
  "assistant_tts_speaker": "meera",
  ...
}
```

_Note: `{{key}}` placeholders in `assistant_prompt` and `assistant_start_instruction` are dynamically replaced with values from the `metadata` passed during outbound calls. The placeholders must match keys in the metadata dictionary._

**GET** `/assistant/list`
List all active assistants created by the current user. Returns a list of objects with `assistant_id`, `assistant_name`, `assistant_tts_model`, and `assistant_created_by_email`.

### Update Assistant

**PATCH** `/assistant/update/{assistant_id}`
Update an existing assistant's configuration. Only provide the fields you want to update.

```json
{
  "assistant_name": "Updated Name",
  "assistant_prompt": "You are an updated assistant."
}
```

### SIP Trunks

**POST** `/sip/create-outbound-trunk`
Configure a SIP trunk for outbound calls.

```json
{
  "trunk_name": "Twilio Trunk",
  "trunk_address": "example.sip.twilio.com",
  "trunk_numbers": ["+1234567890"],
  "trunk_auth_username": "user",
  "trunk_auth_password": "password",
  "trunk_type": "twilio"
}
```

### Outbound Calls

**POST** `/call/outbound`
Trigger a call to a phone number.

```json
{
  "assistant_id": "<assistant_id>",
  "trunk_id": "<trunk_id>",
  "to_number": "+15550000000",
  "call_service": "twilio",
  "metadata": {
    "name": "John Doe",
    "customer_id": "12345"
  }
}
```

_Currently, `call_service` only supports `twilio`. The `metadata` fields are used to replace placeholders in the assistant's prompt and start instruction._

## 🪝 Webhooks

When a call ends, if `assistant_end_call_url` was configured for the assistant, a POST request is sent with the call details.

### End Call Payload

```json
{
  "success": true,
  "message": "Call details fetched successfully",
  "data": {
    "room_name": "assistant-id_unique-suffix",
    "assistant_id": "...",
    "assistant_name": "Support Agent",
    "to_number": "+15550000000",
    "recording_path": "https://bucket.s3.region.amazonaws.com/path/to/recording.ogg",
    "transcripts": [
      {
        "speaker": "agent",
        "text": "Hello John, how can I help?",
        "timestamp": "2024-03-20T10:00:01.000Z"
      },
      {
        "speaker": "user",
        "text": "I need help with my order.",
        "timestamp": "2024-03-20T10:00:05.000Z"
      }
    ],
    "started_at": "2024-03-20T10:00:00.000Z",
    "ended_at": "2024-03-20T10:05:00.000Z",
    "call_duration_minutes": 5.0
  }
}
```

## 🧩 Agent Logic

The agent (`src/core/agents/session.py`):

1. Connects to the LiveKit room.
2. Fetches the assistant configuration from MongoDB using the `assistant_id` (derived from room name).
3. Injects `metadata` values into the prompt and start instruction.
4. Initializes OpenAI Realtime API and Cartesia/Sarvam TTS.
5. Listens for `transcription` events and saves them to MongoDB.
6. Triggers the `end_call` webhook upon participant disconnection.

## 🤝 Contributing

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/amazing-feature`).
3. Commit your changes (`git commit -m 'Add amazing feature'`).
4. Push to the branch (`git push origin feature/amazing-feature`).
5. Open a Pull Request.

## 📄 License

[MIT License](LICENSE)
