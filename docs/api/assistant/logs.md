# Get Call Logs

Retrieve call logs for a specific assistant with support for pagination, sorting, date filtering,
and per-call AI usage and estimated provider cost.

Each log contains a nested `usage` object. This avoids a second request to
`GET /call/records/{room_name}/usage` when displaying an assistant's call history.

- **URL**: `/assistant/call-logs/{assistant_id}`
- **Method**: `GET`
- **Headers**: `Authorization: Bearer <your_api_key>`

### Path Parameters

| Parameter      | Type   | Description                |
| :------------- | :----- | :------------------------- |
| `assistant_id` | string | The UUID of the assistant. |

### Query Parameters

| Parameter    | Type    | Required | Default      | Description                                                                              |
| :----------- | :------ | :------- | :----------- | :--------------------------------------------------------------------------------------- |
| `page`       | integer | No       | `1`          | Page number for pagination (minimum: 1).                                                 |
| `limit`      | integer | No       | `10`         | Number of items per page (minimum: 1, maximum: 100).                                     |
| `start_date` | string  | No       | -            | Start date for filtering (ISO 8601 format).                                              |
| `end_date`   | string  | No       | -            | End date for filtering (ISO 8601 format).                                                |
| `sort_by`    | string  | No       | `started_at` | Field to sort by (e.g., `started_at`, `ended_at`, `call_duration_minutes`, `billable_duration_minutes`). |
| `sort_order` | string  | No       | `desc`       | Sort order: `asc` or `desc`.                                                             |

### Response Schema

| Field                               | Type    | Description                                              |
| :---------------------------------- | :------ | :------------------------------------------------------- |
| `success`                           | boolean | Indicates if the operation was successful.               |
| `message`                           | string  | Human-readable success message.                          |
| `data`                              | object  | Contains the call logs and pagination metadata.          |
| `data.logs`                         | array   | List of call record objects.                             |
| `data.logs[].room_name`             | string  | Unique identifier for the call (LiveKit room name).      |
| `data.logs[].assistant_id`          | string  | ID of the assistant involved in the call.                |
| `data.logs[].assistant_name`        | string  | Name of the assistant at the time of the call.           |
| `data.logs[].to_number`             | string  | Destination phone number.                                |
| `data.logs[].call_status`           | string  | Call status (`initiated`, `answered`, `completed`, `busy`, `no_answer`, `rejected`, `cancelled`, `unreachable`, `timeout`, `failed`). |
| `data.logs[].call_status_reason`    | string  | Optional status detail for terminal non-completed calls. |
| `data.logs[].sip_status_code`       | integer | SIP status code when available.                          |
| `data.logs[].sip_status_text`       | string  | SIP status text when available.                          |
| `data.logs[].answered_at`           | string  | ISO 8601 timestamp when the call was answered.           |
| `data.logs[].started_at`            | string  | ISO 8601 timestamp of when the call started.             |
| `data.logs[].ended_at`              | string  | ISO 8601 timestamp of when the call ended.               |
| `data.logs[].call_duration_minutes` | float   | Actual measured call duration in minutes.                |
| `data.logs[].billable_duration_minutes` | integer | Chargeable duration in whole minutes, rounded up for connected calls and `0` for non-connected terminal outcomes. |
| `data.logs[].recording_path`        | string  | URL/Path to the call recording (if available).           |
| `data.logs[].transcripts`           | array   | List of transcript objects `{speaker, text, timestamp}`. |
| `data.logs[].usage`                 | object/null | Usage and estimated AI-provider cost for this call; `null` when no usage row exists. |
| `data.pagination`                   | object  | Pagination metadata.                                     |
| `data.pagination.total`             | integer | Total number of call logs matching the query.            |
| `data.pagination.page`              | integer | Current page number.                                     |
| `data.pagination.limit`             | integer | Number of items per page.                                |
| `data.pagination.total_pages`       | integer | Total number of pages available.                         |

### Nested Usage Fields

When `data.logs[].usage` is not `null`, it contains the complete persisted
`UsageRecord` payload, excluding its database `id`. Important fields include:

| Field | Type | Description |
| :---- | :--- | :---------- |
| `usage.room_name` | string | LiveKit room associated with the usage record. |
| `usage.mode` | string/null | Assistant mode: `pipeline`, `realtime`, or `cascade`. |
| `usage.llm_input_tokens` | integer | Total LLM input tokens. |
| `usage.llm_output_tokens` | integer | Total LLM output tokens. |
| `usage.llm_total_tokens` | integer | Total LLM tokens reported for the call. |
| `usage.tts_characters_count` | integer | TTS characters used by character-billed providers. |
| `usage.tts_audio_duration` | number | TTS audio duration in seconds. |
| `usage.stt_audio_duration` | number | STT audio duration in seconds. |
| `usage.model_usage` | array | Per-provider/model billable usage entries and their estimated costs. |
| `usage.estimated_cost_usd` | string/null | Estimated AI-provider cost in USD. Serialized as a decimal string. |
| `usage.pricing_schema_version` | integer/null | Pricing table schema version used for calculation. |
| `usage.pricing_complete` | boolean | `true` only when all billable usage has a known rate. |
| `usage.unpriced_model_usage` | array | Usage entries that could not be priced. Empty when pricing is complete. |
| `usage.usage_finalized` | boolean | `true` when the final teardown usage write completed. |

The usage row is updated during the call and once at teardown. For an active
call, values are a current snapshot and may be lower than the final totals.
Calls that fail before an agent session creates usage data, including
passthrough calls, can have `usage: null`.

### HTTP Status Codes

| Code | Description                                     |
| :--- | :---------------------------------------------- |
| 200  | Success - Call logs retrieved successfully.     |
| 401  | Unauthorized - Invalid or missing Bearer token. |
| 404  | Not Found - Assistant does not exist.           |
| 500  | Server Error - Internal server error.           |

### Example Request

```bash
curl -X GET "https://api-livekit-vyom.indusnettechnologies.com/assistant/call-logs/550e8400-e29b-41d4-a716-446655440000?page=1&limit=5" \
     -H "Authorization: Bearer <your_api_key>"
```

**Response:**

```json
{
  "success": true,
  "message": "Call logs retrieved successfully",
  "data": {
    "logs": [
      {
        "room_name": "550e8400-e29b-41d4-a716-446655440000_abc123",
        "assistant_id": "550e8400-e29b-41d4-a716-446655440000",
        "assistant_name": "Support Bot",
        "to_number": "+1234567890",
        "call_status": "completed",
        "call_status_reason": null,
        "sip_status_code": null,
        "sip_status_text": null,
        "answered_at": "2024-01-20T14:30:02.000Z",
        "started_at": "2024-01-20T14:30:00.000Z",
        "ended_at": "2024-01-20T14:35:00.000Z",
        "call_duration_minutes": 5.0,
        "billable_duration_minutes": 5,
        "recording_path": "https://bucket.s3.amazonaws.com/recordings/550e8400...abc123.ogg",
        "transcripts": [
          {
            "speaker": "agent",
            "text": "Hello, how can I help you?",
            "timestamp": "2024-01-20T14:30:05.000Z"
          }
        ],
        "usage": {
          "room_name": "550e8400-e29b-41d4-a716-446655440000_abc123",
          "assistant_id": "550e8400-e29b-41d4-a716-446655440000",
          "user_email": "owner@example.com",
          "mode": "cascade",
          "llm_realtime_provider": "openai",
          "llm_model": "gpt-4.1",
          "llm_input_tokens": 1500,
          "llm_output_tokens": 300,
          "llm_total_tokens": 1800,
          "tts_characters_count": 4500,
          "tts_audio_duration": 125.5,
          "stt_provider": "deepgram",
          "stt_model": "nova-3",
          "stt_audio_duration": 300.0,
          "model_usage": [
            {
              "provider": "openai",
              "model": "gpt-4.1",
              "input_tokens": 1500,
              "output_tokens": 300,
              "estimated_cost_usd": "0.0120"
            }
          ],
          "estimated_cost_usd": "0.0234",
          "pricing_schema_version": 1,
          "pricing_complete": true,
          "unpriced_model_usage": [],
          "usage_finalized": true
        }
      }
    ],
    "pagination": {
      "total": 25,
      "page": 1,
      "limit": 5,
      "total_pages": 5
    }
  }
}
```

### Status Interpretation

- Completed calls usually have `call_status="completed"` and non-null `answered_at`.
- Calls not answered or failed during setup can end with terminal statuses like `busy`, `no_answer`, `timeout`, or `failed`.
- For SIP-driven failures, `sip_status_code` and `sip_status_text` help explain provider-level outcomes.
- Use `call_duration_minutes` when you need actual elapsed time and `billable_duration_minutes` when you need the amount that will be charged.
