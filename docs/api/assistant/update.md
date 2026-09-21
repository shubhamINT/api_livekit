# Update Assistant

Update an existing assistant. Only send fields you want to change.

- **URL**: `/assistant/update/{assistant_id}`
- **Method**: `PATCH`
- **Headers**: `Authorization: Bearer <your_api_key>`
- **Content-Type**: `application/json`

## Path Parameters

| Parameter | Type | Description |
| :--- | :--- | :--- |
| `assistant_id` | string | Assistant UUID. |

## Request Body (Common Fields)

| Field | Type | Description |
| :--- | :--- | :--- |
| `assistant_name` | string | New assistant name. |
| `assistant_description` | string | New assistant description. |
| `assistant_prompt` | string | New system prompt. |
| `assistant_mode` | string | Target mode: `pipeline`, `realtime` or `cascade`. |
| `assistant_start_instruction` | string | New opening response text used when `assistant_interaction_config.speaks_first=true`. |
| `assistant_interaction_config` | object | Partial interaction-config update. |
| `assistant_greeting_audio` | object | Partial greeting-audio update: `{ "enabled": bool, "audio_id": string }`. Toggle the recorded greeting on/off with `enabled`; attach a different [audio asset](../../api/audio/index.md) with `audio_id` (or `null` to detach). Merged with existing values. A non-null `audio_id` must reference one of your active assets. |
| `assistant_end_call_enabled` | boolean | Enable or disable end-call tool. |
| `assistant_end_call_trigger_phrase` | string | End-call trigger phrase. |
| `assistant_end_call_agent_message` | string | End-call agent message. |
| `assistant_end_call_url` | string | End-call webhook URL. |
| `assistant_end_call_webhook` | object | Delivery tuning for that webhook: `timeout_seconds` (1–120), `attempts` (1–5). Merged with what is stored, like `assistant_interaction_config` — send a field as `null` to fall back to the server default. |

---

## LLM Config Rules

- In `pipeline` mode, `assistant_llm_config` is optional and defaults to `provider="openai"`. Send it to override `model` or set `api_key`; `voice` is ignored (external TTS handles audio).
- `provider="gemini"` is rejected in `pipeline` and `cascade` mode — it is supported in `realtime` mode only. See the [Compatibility Matrix](../../reference/compatibility.md#mode-llm-provider).
- `assistant_llm_config.api_key` overrides the system key for the selected provider (`OPENAI_API_KEY` or `GOOGLE_API_KEY`). Omit `assistant_llm_config` to use system keys + mode default provider.
- You can update `assistant_llm_config` alone (without re-sending `assistant_mode` or TTS fields) and the existing TTS config is preserved.
- In `realtime` mode, `assistant_llm_config` is required only when switching into realtime; it defaults to `provider="gemini"`.
- Defaults when fields are omitted — Gemini: `model="gemini-2.5-flash-native-audio-preview-12-2025"`, `voice="Puck"`; OpenAI realtime: `model="gpt-realtime-1.5"`, `voice="marin"`.

## Switching Modes

=== ":material-pipe: Switch to Pipeline"

    When switching to `pipeline` mode, TTS fields are **only required if no TTS config is already stored on the assistant** (e.g. this assistant was created in pipeline mode before being switched to realtime — the original TTS config is preserved in the DB and reused automatically).

    If the assistant has never had a TTS config (e.g. it was originally created in realtime mode), you must provide both TTS fields in the same request.

    **Fields**

    | Field | Type | Required | Description |
    | :--- | :--- | :--- | :--- |
    | `assistant_mode` | string | Yes | Set to `pipeline`. |
    | `assistant_tts_model` | string | Conditional | Required only if no TTS config exists in DB. |
    | `assistant_tts_config` | object | Conditional | Required if `assistant_tts_model` is provided. Must be sent together. |
    | `assistant_stt_model` | string | No | `sarvam` (default when never set) or `native`. `cartesia`, `deepgram`, `elevenlabs` and `openai` are cascade-only. |
    | `assistant_stt_config` | object | No | Config for the selected STT provider. Requires `assistant_stt_model`; omit it to reset that provider's defaults. |

    !!! note "Stale realtime LLM config is cleared automatically"
        When switching back to pipeline mode, any Gemini/realtime `assistant_llm_config` stored from the previous realtime session is automatically cleared. The assistant will fall back to the system `OPENAI_API_KEY` unless you explicitly provide a new `assistant_llm_config.api_key`.

    **Example — switching back when TTS already exists in DB**

    ```bash
    curl -X PATCH "https://api-livekit-vyom.indusnettechnologies.com/assistant/update/550e8400-e29b-41d4-a716-446655440000" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer <your_api_key>" \
      -d '{
        "assistant_mode": "pipeline"
      }'
    ```

    **Example — switching when no TTS exists in DB**

    ```bash
    curl -X PATCH "https://api-livekit-vyom.indusnettechnologies.com/assistant/update/550e8400-e29b-41d4-a716-446655440000" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer <your_api_key>" \
      -d '{
        "assistant_mode": "pipeline",
        "assistant_tts_model": "elevenlabs",
        "assistant_tts_config": {
          "voice_id": "JBFqnCBv7z4s9ByuOnH"
        }
      }'
    ```

=== ":material-lightning-bolt: Switch to Realtime"

    When switching to `realtime` mode, you **must** provide the LLM config.

    **Required fields**

    | Field | Type | Required | Description |
    | :--- | :--- | :--- | :--- |
    | `assistant_mode` | string | Yes | Set to `realtime`. |
    | `assistant_llm_config` | object | Yes | Realtime provider config. The object is required, but `provider`, `model`, and `voice` may be omitted to use defaults. |

    **Example request**

    ```bash
    curl -X PATCH "https://api-livekit-vyom.indusnettechnologies.com/assistant/update/550e8400-e29b-41d4-a716-446655440000" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer <your_api_key>" \
      -d '{
        "assistant_mode": "realtime",
        "assistant_llm_config": {}
      }'
    ```

=== "Switch to Cascade"

    Moves the assistant to the true STT → LLM → TTS pipeline. See
    [Cascade Pipeline](../../architecture/cascade-pipeline.md).

    **Required fields**

    | Field | Type | Required | Description |
    | :--- | :--- | :--- | :--- |
    | `assistant_mode` | string | Yes | Set to `cascade`. |
    | `assistant_tts_model` + `assistant_tts_config` | | Conditional | Required only if no TTS config is already stored on the assistant. |
    | `assistant_stt_model` | string | Conditional | Required in this same request if the stored value is `native`, which cascade rejects. `sarvam`, `cartesia`, `deepgram`, `elevenlabs` or `openai`. Per-provider `assistant_stt_config` fields: see the Cascade STT tabs in [create.md](create.md). |
    | `assistant_llm_config` | object | No | If sent, `provider` must be `openai`. Any stored Gemini config is cleared automatically when leaving realtime mode. |

    !!! warning "A stored `native` STT blocks the switch"
        `native` means "the realtime model transcribes itself", which cascade has no model for.
        If the assistant currently has `assistant_stt_model: "native"`, send a replacement in the
        same request or the update fails with `400`.

    - Changing `assistant_stt_model` to `deepgram`, `elevenlabs` or `openai` requires the matching `assistant_stt_config` in the same request if the stored value is `native`. All of their config fields (`model`, `language` / `language_code`, `keyterm`, `enable_diarization`, `no_verbatim`, `detect_language`, `use_realtime`) are optional — sending `assistant_stt_model` without a config resets that provider's config to its defaults. Per-provider fields: see the Cascade STT tabs in [create.md](create.md).

    **Example request**

    ```bash
    curl -X PATCH "https://api-livekit-vyom.indusnettechnologies.com/assistant/update/550e8400-e29b-41d4-a716-446655440000" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer <your_api_key>" \
      -d '{
        "assistant_mode": "cascade",
        "assistant_stt_model": "sarvam",
        "assistant_llm_config": {
          "provider": "openai",
          "model": "gpt-4.1-mini"
        }
      }'
    ```

    **Example — switch the STT stage to OpenAI** (assistant already in cascade)

    ```bash
    curl -X PATCH "https://api-livekit-vyom.indusnettechnologies.com/assistant/update/550e8400-e29b-41d4-a716-446655440000" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer <your_api_key>" \
      -d '{
        "assistant_stt_model": "openai",
        "assistant_stt_config": {
          "model": "gpt-4o-transcribe",
          "detect_language": true
        }
      }'
    ```

    Sending `{"assistant_stt_model": "openai"}` alone is also valid — it resets the config to
    OpenAI's defaults (`gpt-4o-mini-transcribe`, streaming, auto-detected language).

---

## Validation Rules

- TTS fields must come in pairs: send both `assistant_tts_model` and `assistant_tts_config`, or neither.
- STT is looser: `assistant_stt_model` alone resets the config to that provider's defaults; `assistant_stt_config` alone is rejected (no discriminator to resolve against).
- In `pipeline` mode, `assistant_llm_config` may be omitted entirely.
- In `pipeline` mode, only `assistant_llm_config.api_key` affects runtime behavior.
- Switching to `realtime` requires `assistant_llm_config`.
- Switching to `pipeline` or `cascade` requires TTS fields **only if no TTS config exists in DB**. If the assistant previously had a TTS config, it is preserved and reused — you do not need to re-send it.
- In `cascade` mode, `assistant_stt_model` must be `sarvam`, `cartesia`, `deepgram`, `elevenlabs` or `openai` (`native` returns `400`/`422`), and `assistant_llm_config.provider` must be `openai` or omitted.
- The mode rules are re-checked against the **stored** assistant, not just the request. A PATCH that switches mode is judged on the merged result, so `{"assistant_mode": "cascade"}` against a row that still holds `provider: "gemini"` or a non-allowlisted `model` returns `400` — send the corrected `assistant_llm_config` in the same request.
- `assistant_llm_config.model` is validated per mode: an OpenAI realtime ID in `pipeline`/`realtime`, an allowlisted chat model in `cascade`, one of the three Gemini **Live** IDs for `provider: "gemini"`. `assistant_llm_config.voice` is validated per vendor. In cascade mode the model is additionally checked against what your OpenAI account still serves.
- In `cascade` mode, `temperature`, `reasoning_effort` and `verbosity` are validated **against the model** — including the model already stored, so a PATCH that changes only the model is rejected (`400`) when a knob on the row does not fit the new one. Clear the knob in the same request. Which model reads which: [Cascade LLM knobs](../../reference/compatibility.md#cascade-llm-knobs).

    ```json title="Stored assistant"
    { "assistant_llm_config": { "model": "gpt-5-mini", "reasoning_effort": "low" } }
    ```

    ```json title="Rejected 400 — the new model cannot read the stored reasoning_effort"
    { "assistant_llm_config": { "model": "gpt-4.1" } }
    ```

    ```json title="Accepted — clear the knob in the same request"
    { "assistant_llm_config": { "model": "gpt-4.1", "reasoning_effort": null, "temperature": 0.3 } }
    ```

    Sending `null` clears a knob; omitting it keeps whatever the row already holds, which is
    why the second example above fails and the third does not.
- `assistant_llm_config` is **merged** with the stored one, key by key — the same partial-update
  contract as `assistant_interaction_config`. A PATCH naming only `model` keeps the stored
  `provider`, `api_key` and knobs; it does not replace the object. `null` on a key removes it.
  Leaving `realtime` mode is the one exception: the stored Gemini config is replaced outright, not
  merged, so a Gemini `voice` or key cannot survive under `provider: "openai"`.
- To clear a knob left on many assistants at once (e.g. a `temperature` stored before the
  model gate existed), run `uv run python scripts/migrate_llm_knobs.py` — dry run by default,
  `--apply` to write.
- Unknown keys in `assistant_llm_config`, `assistant_tts_config` (including `voice_settings`) or `assistant_stt_config` return `422`.
- When switching to `pipeline`, any stored realtime `assistant_llm_config` (e.g. Gemini keys) is automatically cleared unless you explicitly provide a new one.

## Runtime Behavior Notes

- `assistant_interaction_config.speaks_first` is supported in all three modes.
- When `speaks_first=true`, `assistant_start_instruction` is used as the opening response — unless `assistant_greeting_audio.enabled=true`, in which case the referenced audio asset is played instead (no LLM/TTS for the greeting). On any failure (missing/inactive asset, download error) it falls back to the model greeting.
- `assistant_interaction_config.background_sound_enabled` controls background ambience for all sessions using the assistant.
- `assistant_interaction_config.thinking_sound_enabled` controls the typing-style thinking sound for all sessions using the assistant.
- `assistant_interaction_config.allow_interruptions` controls whether users can interrupt the assistant's initial greeting. Default: `false`.
- `assistant_interaction_config.input_guard_window_sec` sets how many seconds of **every** agent reply have caller audio blanked (0.0-10.0, default `3.0`). This is what blocks repeated "Hello? Hello?" and short filler sounds ("um", "uh") from cutting the agent off — the input speech gate cannot, because those are genuine speech. Raising it rejects more fillers but also prevents genuine interruptions for that long; `0` disables the guard entirely. The window is a ceiling, not a fixed cost: it releases early when the reply finishes. Applies in both `pipeline` and `realtime` modes.
- `assistant_interaction_config.preferred_languages` accepts a list of BCP-47 codes (e.g. `["hi-IN", "en-US"]`). It hints the `native` transcription prompt only — it is never sent to a speech provider and never disables auto-detection. Pass an empty list `[]` to clear it.
- `assistant_interaction_config.max_call_duration_minutes` sets a hard ceiling on active-call length in minutes (must be `> 0`). When the limit is reached the assistant speaks a brief farewell and the call is torn down gracefully. Unset or `null` falls back to the platform default of **30 minutes**. Does not apply to passthrough calls. The end-of-call webhook payload and `CallRecord.call_end_reason` are set to `max_duration_exceeded` for cuts triggered by this limit.
- `assistant_interaction_config.silence_max_reprompts` sets how many re-prompts a silent caller hears before the call is ended. The call is torn down through the same graceful path, and `CallRecord.call_end_reason` is set to `silence_timeout`.
- `assistant_stt_config.api_key` is the Sarvam key for the parallel STT tap (`assistant_stt_model="sarvam"`). It is **not** the same field as `assistant_tts_config.api_key`, which belongs to the selected TTS provider — sending a Cartesia/ElevenLabs/Mistral key to Sarvam fails with `403`. Unset falls back to the system `SARVAM_API_KEY`.
- The retired `assistant_interaction_config.user_stt_provider` / `.stt_api_key` keys now return `422`. Use `assistant_stt_model` + `assistant_stt_config` instead.
- Masked keys are rejected. `GET /assistant/details` returns keys as `sk-t...5678`, `****`, or `Using System provided API Key`; PATCHing any of those back returns `422`. Send the real key or omit the field.
- Partial `assistant_interaction_config` updates are merged with the stored config; omitted fields are preserved.
- Call-trigger APIs do not provide per-call overrides for these sound settings.

## Response Schema

| Field | Type | Description |
| :--- | :--- | :--- |
| `success` | boolean | Operation status. |
| `message` | string | Human-readable message. |
| `data.assistant_id` | string | Updated assistant UUID. |

## Example Response

```json
{
  "success": true,
  "message": "Assistant updated successfully",
  "data": {
    "assistant_id": "550e8400-e29b-41d4-a716-446655440000"
  }
}
```

## HTTP Status Codes

| Code | Description |
| :--- | :--- |
| 200 | Assistant updated successfully. |
| 400 | Validation or payload mismatch error. |
| 401 | Unauthorized. |
| 404 | Assistant not found. |
| 500 | Internal server error. |
