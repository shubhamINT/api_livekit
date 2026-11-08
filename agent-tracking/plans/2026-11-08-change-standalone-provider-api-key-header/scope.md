# Scope — 2026-11-08-change-standalone-provider-api-key-header

## Request (verbatim)

"Move the provider API key from request body/form field to an X-Provider-API-Key HTTP header."

## Decisions

- Provider API key for standalone endpoints moves from body/form to HTTP header `X-Provider-API-Key`.
- Body/form `api_key` field removed to avoid duplicate/confusing inputs.
- Precedence unchanged: header key > assistant stored key > system env default.
- Masked values (e.g. `****`) rejected with 422; empty/whitespace rejected.

## Out of scope

- No change to platform Bearer auth.
- No change to assistant create/update api_key handling.