# Progress — 2026-11-08-change-standalone-provider-api-key-header

## Change

Moved provider API key from request body/form field to `X-Provider-API-Key` HTTP header on all three standalone endpoints.

## Implementation log

- Removed `api_key` field from `SynthesizeRequest`, `ChatCompletionRequest`, and STT form params.
- Added `X-Provider-API-Key` header param to `/stt/transcribe`, `/tts/synthesize`, `/llm/chat`.
- Threaded header value as `explicit_api_key` into `resolve_stage_config` (already supported).
- Updated docs to document the header.

## Verification

- Full suite: 724 tests OK.
- mkdocs build --strict: clean (pre-existing changelog anchor warnings only).

Verdict: Converged