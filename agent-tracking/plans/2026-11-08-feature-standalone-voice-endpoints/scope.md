# Scope — 2026-11-08-feature-standalone-voice-endpoints

- **Type:** feature
- **Requested by:** User
- **Date:** 2026-11-08

## Original request (verbatim)

> We have the total voice thing, the calling thing, and everything. Now we need to have simple stuff that the users are requesting: endpoints for separate parts. We have the voice, which consists of STT, TS, and an LLM. The users are requesting separate endpoints for STT, TS, and the LLM.
>
> They will do an API request to the STT and they're going to get the transcription and those kinds of things. Then they can get the output. For TS they're going to get the voice outputs and those kinds of things. If the user likes they can use those things separately along with the voice calls and everything.
>
> For building this we need to think about it. Tell me what things might be needed or need discussion between us. Use the skills properly, take a look, and tell me.  /core-be-plan

## Proposed Scope & Discussion Items

| Area | Topic | Proposed Baseline / Options |
|------|-------|-----------------------------|
| Architecture | Direct HTTP vs LiveKit Worker | Execute in FastAPI control container using `httpx` to vendor REST APIs directly, preserving Principle 8 (dependency-free control image without `livekit-agents` plugins). |
| Configuration | Assistant-backed vs Explicit params | Hybrid: Allow callers to either provide `assistant_id` (inheriting stored provider/voice/prompt/key), OR explicit payload params (`provider`, `model`, `voice`, etc.), with explicit params taking precedence. |
| STT endpoint | Audio transcription | `POST /stt/transcribe` taking `multipart/form-data` audio file + optional model/language params, returning JSON `{ "text": "...", "language": "...", "duration": ... }`. |
| TTS endpoint | Speech synthesis | `POST /tts/synthesize` taking JSON payload `{ "text": "...", "provider": "...", "voice": "...", ... }`, returning `audio/wav` or `audio/mpeg` binary audio. |
| LLM endpoint | Text / Chat completion | `POST /llm/chat` taking messages list + model parameters, returning JSON response with optional Server-Sent Events (SSE) streaming support. |
| Auth & Usage | Auth and accounting | Standard `Bearer lvk_...` auth; record token/audio usage in `UsageRecord` tagged with component type (`stt`, `tts`, `llm`). |

