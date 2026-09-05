# Tokens by User

## Overview

Returns LLM token and TTS usage metrics grouped by user email. Use this to compare resource consumption across users.

## Endpoint

- **URL**: `/admin/analytics/tokens/by-user`
- **Method**: `GET`
- **Authentication**: Super-admin required

## Request

### Query Parameters

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `start_date` | datetime | No | 30 days ago | ISO 8601 start of range. |
| `end_date` | datetime | No | Now | ISO 8601 end of range. |

## Response Schema

| Field | Type | Description |
| :--- | :--- | :--- |
| `success` | boolean | Operation status. |
| `message` | string | Result message. |
| `data.users` | array | List of per-user usage metrics. |
| `data.users[].user_email` | string | User email address. |
| `data.users[].total_calls` | integer | Number of calls with usage data. |
| `data.users[].total_llm_tokens` | integer | Total LLM tokens consumed. |
| `data.users[].total_llm_input_audio_tokens` | integer | Total LLM input audio tokens. |
| `data.users[].total_llm_input_cached_tokens` | integer | Input tokens served from the provider's prompt cache. A subset of the input totals, not an addition to them. |
| `data.users[].total_llm_input_cache_creation_tokens` | integer | Input tokens written into the prompt cache. `0` on OpenAI, which does not charge for cache writes. |
| `data.users[].total_llm_output_text_tokens` | integer | Total LLM output text tokens. |
| `data.users[].total_tts_characters` | integer | Total TTS characters synthesized. |
| `data.users[].total_tts_audio_duration` | float | Total TTS audio duration in seconds. |
| `data.users[].total_call_duration_minutes` | float | Total call duration in minutes. |
| `data.users[].total_call_duration_hours` | float | Total call duration in hours. |

## HTTP Status Codes

| Code | Description |
| :--- | :--- |
| 200 | Data returned successfully. |
| 401 | Unauthorized (invalid or missing API key). |
| 403 | Forbidden (API key is not a super-admin). |
| 500 | Internal server error. |

## Example Request

```bash
curl -X GET "https://api-livekit-vyom.indusnettechnologies.com/admin/analytics/tokens/by-user" \
  -H "Authorization: Bearer YOUR_SUPER_ADMIN_API_KEY"
```

## Example Response

```json
{
  "success": true,
  "message": "Token usage by user fetched successfully",
  "data": {
    "users": [
      {
        "user_email": "alice@example.com",
        "total_calls": 450,
        "total_llm_tokens": 2100000,
        "total_llm_input_audio_tokens": 750000,
        "total_llm_input_cached_tokens": 150000,
        "total_llm_input_cache_creation_tokens": 0,
        "total_llm_output_text_tokens": 280000,
        "total_tts_characters": 1200000,
        "total_tts_audio_duration": 10200.50,
        "total_call_duration_minutes": 2025.00,
        "total_call_duration_hours": 33.75
      },
      {
        "user_email": "bob@example.com",
        "total_calls": 280,
        "total_llm_tokens": 1530000,
        "total_llm_input_audio_tokens": 500000,
        "total_llm_input_cached_tokens": 100000,
        "total_llm_input_cache_creation_tokens": 0,
        "total_llm_output_text_tokens": 190000,
        "total_tts_characters": 950000,
        "total_tts_audio_duration": 8300.25,
        "total_call_duration_minutes": 1260.00,
        "total_call_duration_hours": 21.00
      }
    ]
  }
}
```

## Notes

- Results are sorted by total LLM tokens in descending order.
- Only users with at least one usage record in the date range are included.
