# Research — 2026-11-08-feature-standalone-voice-endpoints

Detailed read of `src/` to design standalone endpoints for STT, TTS, and LLM that operate in the FastAPI control image without violating Constitution Principle 8. Citations are `file:line` as of 2026-11-08.

## 1. Image Separation & Architecture Boundary

- **Principle 8 & Deployment constraint (`AGENTS.md:144-152`, `specs/constitution.md:22`):**
  - Control image runs FastAPI (`src/api/server.py`) and outbound SIP dispatcher. It imports dependencies from `docker/requirements-control.txt` which has **no** `livekit-agents` and **no** `livekit.plugins.*`.
  - Agent image (`agent_run.py`) runs the LiveKit worker and imports `livekit-agents`.
  - Therefore, any endpoint defined in FastAPI routes (`src/api/routes/`) must **not** import `livekit.plugins.*` (e.g., `from livekit.plugins import cartesia` in `src/core/agents/tts/factory.py:6` is illegal in control image).
- **Solution:**
  - Standalone endpoints execute HTTP calls to vendor REST APIs directly using `httpx.AsyncClient` from the API server.
  - Placed under `src/services/stt/`, `src/services/tts/`, and `src/services/llm/`.

## 2. Existing Provider Configurations & Keys

- `src/core/config.py:34-45`:
  - `OPENAI_API_KEY`: OpenAI for LLM (`/v1/chat/completions` or `/v1/responses`) and STT (`/v1/audio/transcriptions`).
  - `GOOGLE_API_KEY`: Gemini for LLM (`https://generativelanguage.googleapis.com/v1beta/...`).
  - `SARVAM_API_KEY`: Sarvam for STT (`https://api.sarvam.ai/speech-to-text`) and TTS (`https://api.sarvam.ai/text-to-speech`).
  - `CARTESIA_API_KEY`: Cartesia for TTS (`https://api.cartesia.ai/tts/bytes`) and STT (`https://api.cartesia.ai/stt/transcribe`).
  - `ELEVENLABS_API_KEY`: ElevenLabs for TTS (`https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`) and STT (`https://api.elevenlabs.io/v1/speech-to-text`).
  - `DEEPGRAM_API_KEY`: Deepgram for STT (`https://api.deepgram.com/v1/listen`).
  - `MISTRAL_API_KEY`: Mistral for TTS (`https://api.mistral.ai/v1/tts`).
- API keys can also be overridden per-assistant in `assistant.assistant_tts_config["api_key"]` or `assistant.assistant_stt_config["api_key"]`.

## 3. Audio Handling & Constraints

- `src/services/storage/audio_transcode.py:17`:
  - `MAX_UPLOAD_BYTES = 25 * 1024 * 1024` (25 MB cap).
  - Handles upload stream safely: reading at most `MAX_UPLOAD_BYTES + 1` to reject oversized payloads before buffering.
  - PyAV is available in `requirements-control.txt:16` (`av>=12.0.0`) if audio inspection or format transcoding is required.

## 4. Usage Accounting

- `src/core/db/db_schemas.py:165-185` (`UsageRecord`):
  - Fields: `user_email`, `call_id`, `call_type`, `model`, `provider`, `duration_seconds`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `cost_breakdown`.
  - For standalone API requests:
    - `call_type = "standalone_api"`
    - `call_id = f"req_{uuid.uuid4().hex[:12]}"`
    - `meta = {"endpoint": "/stt" | "/tts" | "/llm"}`

## 5. Security & Error Handling

- Standard auth dependency: `src/api/dependencies/auth.py:28` (`get_current_user`).
- Standard response envelope: `src/api/models/response_models.py:11` (`apiResponse(data=..., message=..., status_code=...)`).
- Allowlist validation: `src/core/model_support/capabilities.py` and `src/core/model_support/speech.py` already define the legal models and knob rules for OpenAI, Gemini, Sarvam, Cartesia, ElevenLabs, Deepgram.

