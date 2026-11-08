# Spec 002 — Standalone voice endpoints (STT, TTS, LLM)

- **Status:** implemented
- **Owner:** Shubham Halder, backend engineer
- **Last changed:** 2026-11-08

## Summary

The platform provides end-to-end voice sessions (WebRTC and telephony) combining STT, LLM, and TTS.
This feature exposes each of these three foundational stages as independent, standalone HTTP endpoints
under the FastAPI API server (`/stt`, `/tts`, `/llm`). Callers can transcribe audio files, synthesize
text into speech, or generate conversational LLM completions independently of live voice calls,
either by referencing an existing assistant configuration or by passing direct provider/model parameters.

## Users and stories

- As an API developer, I can send an audio recording to `POST /stt/transcribe` and receive a text
  transcription with detected language and duration, so that I can process voicemails or user speech outside calls.
- As an API developer, I can send text to `POST /tts/synthesize` and receive an audio stream (`audio/wav` or `audio/mpeg`),
  so that I can generate spoken announcements or UI speech without starting a live WebRTC session.
- As an API developer, I can send a list of chat messages to `POST /llm/chat` and receive a completion
  (or Server-Sent Events stream), so that I can run conversational reasoning using the platform's configured LLM providers.
- As an API developer, I can pass an `assistant_id` to any of these endpoints to reuse an assistant's pre-configured
  voice, model, prompt, or provider settings, or provide explicit parameters in the request payload to override them.
- As an operator, I can trace usage and token/audio consumption from these standalone endpoints in `usage_records`
  under the authenticated user's account.

## Acceptance criteria

Numbered, testable, never renumbered.

- **AC-1:** Given an authenticated request with a valid audio file (`wav`, `mp3`, `ogg`, `m4a`, `webm`) to `POST /stt/transcribe`,
  when processed, then the endpoint returns HTTP 200 with JSON payload containing `text` (transcription), `language` (detected or specified),
  and `duration_seconds`.
- **AC-2:** Given an unauthenticated or invalid API key request to `POST /stt/transcribe`, `POST /tts/synthesize`, or `POST /llm/chat`,
  then the server returns HTTP 401 with standard error envelope.
- **AC-3:** Given an audio file exceeding `MAX_UPLOAD_BYTES` (25 MB) or corrupted audio to `POST /stt/transcribe`,
  then the server returns HTTP 413 (Payload Too Large) or HTTP 422 (Unprocessable Content) without crashing or exhausting server memory.
- **AC-4:** Given a request to `POST /tts/synthesize` with valid `text` and voice/model configuration,
  when processed, then the server streams binary audio with appropriate `Content-Type` (`audio/wav` or `audio/mpeg`)
  and valid audio headers.
- **AC-5:** Given an empty or blank `text` string (or whitespace only) or `text` exceeding 5,000 characters to `POST /tts/synthesize`,
  then the server returns HTTP 422 with a clear descriptive message.
- **AC-6:** Given a request to `POST /llm/chat` with valid `messages` and model configuration,
  when `stream` is `false` (default), then the server returns HTTP 200 with JSON containing the assistant message and token usage.
- **AC-7:** Given a request to `POST /llm/chat` with `stream: true`,
  when processed, then the server returns HTTP 200 with `Content-Type: text/event-stream` delivering SSE chunks ending with `[DONE]`.
- **AC-8:** Given a request to any standalone endpoint specifying `assistant_id`,
  when the assistant exists and belongs to the authenticated user, then the endpoint inherits the corresponding stage configuration
  (`assistant_stt_model` / `assistant_stt_config` for STT; `assistant_tts_model` / `assistant_tts_config` for TTS;
  `assistant_llm_config` for LLM); explicit request parameters override assistant defaults.
- **AC-9:** Given a request specifying an `assistant_id` that does not exist or belongs to another user,
  then the server returns HTTP 404.
- **AC-10:** Given unsupported or retired provider/model names in direct parameters,
  then the server validates against the allowlists in `src/core/model_support/` and returns HTTP 422 before dispatching to external providers.
- **AC-11:** Given successful execution of `/stt/transcribe`, `/tts/synthesize`, or `/llm/chat`,
  then a usage record is logged to `UsageRecord` with `call_type="standalone_api"`, authenticated user email, component tag,
  and billed metrics (audio seconds or input/output tokens).

## Interfaces

### 1. STT (`POST /stt/transcribe`)
- **Headers:** `Authorization: Bearer <api_key>`
- **Content-Type:** `multipart/form-data`
- **Form fields:**
  - `file`: `UploadFile` (binary audio; max 25 MB; wav, mp3, ogg, webm, m4a)
  - `assistant_id`: `Optional[str]`
  - `provider`: `Optional[Literal["sarvam", "cartesia", "deepgram", "openai", "elevenlabs"]]`
  - `model`: `Optional[str]`
  - `language`: `Optional[str]` (e.g. `"en-US"`, `"hi-IN"`, `"auto"`)
- **Success Response (200 OK):**
  ```json
  {
    "status": "success",
    "data": {
      "text": "Hello world",
      "language": "en",
      "duration_seconds": 1.45,
      "provider": "sarvam",
      "model": "saaras:v3"
    }
  }
  ```
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid bearer key.
  - `404 Not Found`: `assistant_id` not found or unowned.
  - `413 Payload Too Large`: Audio file > 25 MB.
  - `422 Unprocessable Content`: Unrecognised provider/model or invalid audio file format.
  - `502 Bad Gateway`: Upstream provider error or timeout.

### 2. TTS (`POST /tts/synthesize`)
- **Headers:** `Authorization: Bearer <api_key>`
- **Content-Type:** `application/json`
- **Request Body:**
  ```json
  {
    "text": "Hello, how can I help you today?",
    "assistant_id": "optional-uuid",
    "provider": "cartesia",
    "model": "sonic-3",
    "voice": "optional-voice-id-or-name",
    "language": "en",
    "save_to_library": false
  }
  ```
- **Success Response (200 OK):**
  - Binary stream (`audio/wav` or `audio/mpeg`).
  - Response headers: `Content-Type: audio/wav`, `Content-Disposition: inline; filename="speech.wav"`, `X-Audio-Duration: 2.1`.
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid bearer key.
  - `404 Not Found`: `assistant_id` not found or unowned.
  - `422 Unprocessable Content`: Empty text, text > 5000 chars, or invalid voice/speaker for provider.
  - `502 Bad Gateway`: Upstream provider error.

### 3. LLM (`POST /llm/chat`)
- **Headers:** `Authorization: Bearer <api_key>`
- **Content-Type:** `application/json`
- **Request Body:**
  ```json
  {
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "What is LiveKit?"}
    ],
    "assistant_id": "optional-uuid",
    "provider": "openai",
    "model": "gpt-5.4",
    "temperature": 0.7,
    "max_tokens": 1000,
    "stream": false
  }
  ```
- **Success Response (200 OK, stream=false):**
  ```json
  {
    "status": "success",
    "data": {
      "message": {
        "role": "assistant",
        "content": "LiveKit is an open-source WebRTC stack..."
      },
      "usage": {
        "prompt_tokens": 25,
        "completion_tokens": 14,
        "total_tokens": 39
      },
      "provider": "openai",
      "model": "gpt-5.4"
    }
  }
  ```
- **Success Response (200 OK, stream=true):**
  - `Content-Type: text/event-stream`
  - Chunks: `data: {"choices": [{"delta": {"content": "..."}}]}\n\n` ending with `data: [DONE]\n\n`.
- **Error Responses:**
  - `401 Unauthorized`: Missing or invalid bearer key.
  - `404 Not Found`: `assistant_id` not found or unowned.
  - `422 Unprocessable Content`: Invalid model for provider or disallowed knob pairing per `capabilities.py`.

## Data

- Stored entity: `UsageRecord` (existing collection). Standalone calls add records with:
  - `call_type`: `"standalone_api"`
  - `call_id`: `None` (or synthetic `req_<uuid>`)
  - `component`: `"stt" | "tts" | "llm"`
  - `model`: resolved model name
  - `provider`: resolved provider name
  - Standard duration/token metrics matching current call accounting.

## Limits and non-functional

- **Authentication:** Standard `Authorization: Bearer <lvk_...>` key for all endpoints.
- **Upload size limit:** 25 MB max per audio file for STT (`MAX_UPLOAD_BYTES`).
- **Text length limit:** 5,000 characters max per TTS request.
- **Latency & Streaming:** TTS and LLM stream responses where supported to minimize Time-to-First-Byte (TTFB).
- **Isolation:** Standalone service adapters live in `src/services/` and run within the FastAPI control process using `httpx`. They MUST NOT import `livekit-agents` or `livekit.plugins.*` (Constitution Principle 8).

## Out of scope

- Real-time two-way duplex voice streaming over WebSockets (handled by LiveKit agent calls and Web Call endpoints).
- Tool/function calling execution loop on `/llm/chat` (can be added in future iterations).
- User-uploaded custom fine-tuned model hosting.

## Open questions

- None. (Draft resolved with standard REST contracts).

## Change log

| Date | Change | Task slug |
|------|--------|-----------|
| 2026-11-08 | Created | 2026-11-08-feature-standalone-voice-endpoints |
