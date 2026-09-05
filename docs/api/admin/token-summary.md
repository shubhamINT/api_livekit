# Token Usage Summary

## Overview

Returns aggregated LLM token and TTS usage metrics across all users. Optionally filter by user or assistant.

## Endpoint

- **URL**: `/admin/analytics/tokens/summary`
- **Method**: `GET`
- **Authentication**: Super-admin required

## Request

### Query Parameters

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `start_date` | datetime | No | 30 days ago | ISO 8601 start of range. |
| `end_date` | datetime | No | Now | ISO 8601 end of range. |
| `user_email` | string | No | -- | Narrow results to a specific user. |
| `assistant_id` | string | No | -- | Narrow results to a specific assistant. |

## Response Schema

| Field | Type | Description |
| :--- | :--- | :--- |
| `success` | boolean | Operation status. |
| `message` | string | Result message. |
| `data.total_records` | integer | Number of usage records matched. |
| `data.total_llm_input_audio_tokens` | integer | Total LLM input audio tokens. |
| `data.total_llm_input_text_tokens` | integer | Total LLM input text tokens. |
| `data.total_llm_input_image_tokens` | integer | Total LLM input image tokens. |
| `data.total_llm_input_cached_tokens` | integer | Total input tokens served from the provider's prompt cache. A subset of the input totals above, not an addition to them. |
| `data.total_llm_input_cached_audio_tokens` | integer | Total cached audio input tokens. |
| `data.total_llm_input_cached_text_tokens` | integer | Total cached text input tokens. |
| `data.total_llm_input_cached_image_tokens` | integer | Total cached image input tokens. |
| `data.total_llm_input_cache_creation_tokens` | integer | Total input tokens written into the prompt cache. Billed on top of the read by providers that report it; `0` on OpenAI. |
| `data.total_llm_output_audio_tokens` | integer | Total LLM output audio tokens. |
| `data.total_llm_output_text_tokens` | integer | Total LLM output text tokens. |
| `data.total_llm_tokens` | integer | Grand total of all LLM tokens. |
| `data.total_tts_characters` | integer | Total TTS characters synthesized. |
| `data.total_tts_audio_duration` | float | Total TTS audio duration in seconds. |
| `data.total_tts_tokens` | integer | Total TTS input + output tokens. Token-billed TTS only; `0` for character-billed providers. |
| `data.total_stt_tokens` | integer | Total STT input + output tokens. Token-billed STT (`openai`) only. |
| `data.total_stt_audio_duration` | float | Total seconds of audio transcribed by a standalone STT stage (`cascade` only). |
| `data.total_call_duration_minutes` | float | Total call duration in minutes. |

## HTTP Status Codes

| Code | Description |
| :--- | :--- |
| 200 | Data returned successfully. |
| 401 | Unauthorized (invalid or missing API key). |
| 403 | Forbidden (API key is not a super-admin). |
| 500 | Internal server error. |

## Example Request

```bash
curl -X GET "https://api-livekit-vyom.indusnettechnologies.com/admin/analytics/tokens/summary?user_email=alice@example.com" \
  -H "Authorization: Bearer YOUR_SUPER_ADMIN_API_KEY"
```

## Example Response

```json
{
  "success": true,
  "message": "Token usage summary fetched successfully",
  "data": {
    "total_records": 450,
    "total_llm_input_audio_tokens": 1250000,
    "total_llm_input_text_tokens": 850000,
    "total_llm_input_image_tokens": 0,
    "total_llm_input_cached_tokens": 500000,
    "total_llm_input_cached_audio_tokens": 320000,
    "total_llm_input_cached_text_tokens": 180000,
    "total_llm_input_cached_image_tokens": 0,
    "total_llm_input_cache_creation_tokens": 0,
    "total_llm_output_audio_tokens": 620000,
    "total_llm_output_text_tokens": 410000,
    "total_llm_tokens": 3630000,
    "total_tts_characters": 2150000,
    "total_tts_audio_duration": 18500.75,
    "total_tts_tokens": 0,
    "total_stt_tokens": 0,
    "total_stt_audio_duration": 9100.25,
    "total_call_duration_minutes": 2025.00
  }
}
```

## Notes

- Token data is sourced from the `UsageRecord` collection, which is populated per-call by the worker process.
- Cached token counts reflect OpenAI prompt caching and reduce effective input cost. They are
  a **subset** of the input totals, not an addition to them: the uncached text input is
  `total_llm_input_text_tokens - total_llm_input_cached_text_tokens`.
- `total_llm_tokens` is the sum of all input and output token fields (including cached).
- Records written before 2026-09 (`usage_schema_version` 1) contribute `0` to every field added
  since. See [Usage accounting](../../reference/usage-accounting.md).
