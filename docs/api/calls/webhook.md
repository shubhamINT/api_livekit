# End Call Webhook

A POST request is sent when a call reaches a terminal state:

- **AI calls**: if the assistant has `assistant_end_call_url` configured
- **Passthrough calls**: if the trunk has `passthrough_webhook_url` configured (fires on **all** terminal outcomes — completed, busy, no_answer, timeout, failed)

### Webhook Request

```http
POST /your-webhook-endpoint HTTP/1.1
Content-Type: application/json

{
  "success": true,
  "message": "Call details fetched successfully",
  "data": {
    "room_name": "550e8400-e29b-41d4-a716-446655440000_abc123",
    "queue_id": "8b7df5ea0fdc497ea4f44bd31954a387",
    "assistant_id": "550e8400-e29b-41d4-a716-446655440000",
    "assistant_name": "Support Agent",
    "to_number": "+15550200000",
    "call_status": "completed",
    "call_status_reason": null,
    "sip_status_code": null,
    "sip_status_text": null,
    "answered_at": "2024-01-15T10:00:02.000Z",
    "agent_ready_at": "2024-01-15T10:00:03.500Z",
    "call_end_reason": "natural",
    "recording_path": "https://your-bucket.s3.us-east-1.amazonaws.com/recordings/call_abc123.ogg",
    "transcripts": [
      {
        "speaker": "agent",
        "text": "Hello John, how can I help you today?",
        "timestamp": "2024-01-15T10:00:01.000Z"
      },
      {
        "speaker": "user",
        "text": "I need help with my order.",
        "timestamp": "2024-01-15T10:00:05.000Z"
      },
      {
        "speaker": "agent",
        "text": "I'd be happy to help. What's your order number?",
        "timestamp": "2024-01-15T10:00:08.000Z"
      }
    ],
    "started_at": "2024-01-15T10:00:00.000Z",
    "ended_at": "2024-01-15T10:05:30.000Z",
    "call_duration_minutes": 5.5,
    "billable_duration_minutes": 6,
    "created_by_email": "user@example.com",
    "call_type": "outbound",
    "call_service": "exotel",
    "platform_number": "08044319240",
    "usage": {
      "mode": "cascade",
      "llm_model": "gpt-4.1-mini",
      "llm_input_audio_tokens": 0,
      "llm_input_text_tokens": 850,
      "llm_input_image_tokens": 0,
      "llm_output_audio_tokens": 0,
      "llm_output_text_tokens": 1230,
      "llm_total_tokens": 2080,
      "llm_input_cached_tokens": 512,
      "llm_input_cached_audio_tokens": 0,
      "llm_input_cached_text_tokens": 512,
      "llm_input_cached_image_tokens": 0,
      "llm_input_cache_creation_tokens": 0,
      "llm_session_duration": 0.0,
      "tts_characters_count": 485,
      "tts_audio_duration": 32.5,
      "tts_input_tokens": 0,
      "tts_output_tokens": 0,
      "stt_provider": "sarvam",
      "stt_model": "saaras:v3",
      "stt_audio_duration": 41.75,
      "stt_input_tokens": 0,
      "stt_output_tokens": 0,
      "usage_schema_version": 2
    }
  }
}
```

### Webhook Payload Schema

| Field                          | Type    | Description                                |
| :----------------------------- | :------ | :----------------------------------------- |
| `success`                      | boolean | Always `true` for webhook notifications.   |
| `message`                      | string  | Status message.                            |
| `data`                         | object  | Complete call details.                     |
| `data.room_name`               | string  | The LiveKit room name.                     |
| `data.queue_id`                | string  | The queue ID from `POST /call/outbound`. Present for outbound calls, `null` for inbound/web. Use this to correlate the webhook with the original trigger response. |
| `data.assistant_id`            | string  | ID of the assistant used. `null` for passthrough calls. |
| `data.assistant_name`          | string  | Name of the assistant. `null` for passthrough calls.    |
| `data.is_passthrough`          | boolean | `true` for passthrough (no AI agent) calls, `false` for AI calls. |
| `data.to_number`               | string  | Phone number that was called.              |
| `data.call_status`             | string  | Call lifecycle status (`initiated`, `answered`, `completed`) or terminal SIP outcome (`busy`, `no_answer`, `rejected`, `cancelled`, `unreachable`, `timeout`, `failed`). |
| `data.call_status_reason`      | string  | Optional detailed reason for non-success outcomes. |
| `data.sip_status_code`         | number  | SIP response code when available for SIP-driven setup outcomes. May be `null` for generic failures/timeouts. |
| `data.sip_status_text`         | string  | SIP reason text when available for SIP-driven setup outcomes. May be `null` for generic failures/timeouts. |
| `data.answered_at`             | string  | Timestamp when the user answered (if answered). |
| `data.agent_ready_at`          | string  | Timestamp when the AI agent actually joined the room and started running (`session.start()` succeeded). Internal diagnostic signal — used by the dispatcher to detect a call that was answered but never got a live agent (crash, provider outage, worker overload) and end it instead of leaving it silent. `null` if the agent never became ready, or for passthrough/legacy calls (no AI agent). Not part of the stable contract — do not build required logic on it. |
| `data.call_end_reason`         | string  | Reason the call ended. `natural` for normal user/agent hang-up, `max_duration_exceeded` when the assistant's `max_call_duration_minutes` ceiling was hit. May be `null` for legacy records created before this field existed. |
| `data.recording_path`          | string  | S3 URL of the call recording (if enabled). |
| `data.transcripts`             | array   | List of conversation messages, ordered by `timestamp` (speaking order). Always `[]` for passthrough calls (no STT). |
| `data.transcripts[].speaker`   | string  | Who spoke (`agent` or `user`).             |
| `data.transcripts[].text`      | string  | The transcribed text. One entry per utterance — user fragments split by Sarvam's endpointing are rejoined before storage. |
| `data.transcripts[].timestamp` | string  | ISO 8601 timestamp of when the utterance was **captured**, not when it was written. User entries are stamped at the start of the utterance. |
| `data.started_at`              | string  | Call start time (ISO 8601).                |
| `data.ended_at`                | string  | Call end time (ISO 8601).                  |
| `data.call_duration_minutes`   | number  | Actual measured call duration in minutes.  |
| `data.billable_duration_minutes` | integer | Chargeable duration in whole minutes, rounded up for connected calls and `0` for non-connected terminal outcomes. |
| `data.created_by_email`        | string  | Email of the user who owns this call.      |
| `data.call_type`               | string  | Call direction: `outbound`, `inbound`, or `web`. |
| `data.call_service`            | string  | Telephony provider: `exotel`, `twilio`, or `web`. |
| `data.platform_number`         | string  | Platform's own phone number used for this call. |
| `data.usage`                   | object  | Per-component usage metrics (if available). Raw counts, not costs. |
| `data.usage.mode`                   | string | Runtime mode for this call: `pipeline`, `realtime` or `cascade`. See [Models & Providers](../../reference/models.md). |
| `data.usage.llm_model`              | string | LLM model(s) used, comma-separated if more than one. |
| `data.usage.llm_input_audio_tokens` | number | LLM audio input tokens (`0` in cascade — the LLM receives text). |
| `data.usage.llm_input_text_tokens`  | number | LLM text input tokens.                |
| `data.usage.llm_input_image_tokens` | number | LLM image input tokens. `0` unless the conversation carried images. |
| `data.usage.llm_output_audio_tokens`| number | LLM audio output tokens (`0` outside realtime). |
| `data.usage.llm_output_text_tokens` | number | LLM text output tokens.               |
| `data.usage.llm_total_tokens`       | number | Total LLM tokens for this call.       |
| `data.usage.llm_input_cached_tokens`| number | Input tokens served from the provider's prompt cache. **A subset of the input counts above, not an addition to them** — see the warning below. |
| `data.usage.llm_input_cached_audio_tokens` | number | The audio part of `llm_input_cached_tokens`. |
| `data.usage.llm_input_cached_text_tokens`  | number | The text part of `llm_input_cached_tokens`. |
| `data.usage.llm_input_cached_image_tokens` | number | The image part of `llm_input_cached_tokens`. |
| `data.usage.llm_input_cache_creation_tokens` | number | Input tokens written *into* the cache. Unlike the cached counts, providers that report this bill it on top of the read. `0` on OpenAI, which does not charge for cache writes. |
| `data.usage.llm_session_duration`   | number | Connection seconds, for providers that bill a realtime session by time rather than by token. `0` otherwise. |
| `data.usage.tts_characters_count`   | number | Characters sent to TTS provider.      |
| `data.usage.tts_audio_duration`     | number | TTS audio duration in seconds.        |
| `data.usage.tts_input_tokens`       | number | TTS input tokens. Token-billed TTS only; `0` for character-billed providers. |
| `data.usage.tts_output_tokens`      | number | TTS output (audio) tokens. Token-billed TTS only. |
| `data.usage.stt_provider`           | string | STT provider. **`cascade` mode only**, `null` otherwise. |
| `data.usage.stt_model`              | string | STT model. **`cascade` mode only**, `null` otherwise. |
| `data.usage.stt_audio_duration`     | number | Seconds of audio transcribed. **`cascade` mode only**, `0` otherwise. |
| `data.usage.stt_input_tokens`       | number | STT input (audio) tokens. Token-billed STT (`openai`) only; `0` for duration-billed providers. |
| `data.usage.stt_output_tokens`      | number | STT output (text) tokens. Token-billed STT only. |
| `data.usage.usage_schema_version`   | number | `2` for calls recorded from 2026-09 onwards. `1` marks an older record that carries only the non-cached LLM and TTS counts; treat its missing fields as unknown, not as zero. |

!!! warning "Cached token counts are subsets"
    `llm_input_cached_tokens` is part of `llm_total_tokens` already, and each cached
    per-modality count is part of its matching input count. To price a call, split the input
    into cached and uncached (`llm_input_text_tokens - llm_input_cached_text_tokens` is the
    uncached text) and apply the two rates. Adding the cached fields to the input fields
    charges those tokens twice.

!!! note "Why STT fields are empty in realtime mode"
    Only [`cascade`](../../architecture/cascade-pipeline.md) has an STT stage the agent session
    itself owns. In `pipeline` mode with the default Sarvam provider the transcription runs on a
    parallel tap outside the session, which measures its own audio and reports it — the seconds
    are the audio the tap sent, so expect a small difference from Sarvam's invoice. In
    `realtime` mode the LLM transcribes internally and that spend is still not counted at all —
    see [Usage accounting](../../reference/usage-accounting.md).

!!! warning "Breaking change: `usage.llm_mode` → `usage.mode`"
    The old `usage.llm_mode` key was renamed to `usage.mode` (the field never selected an LLM — it
    records which runtime mode the call ran in). Consumers reading `data.usage.llm_mode` will now see
    `undefined`; read `data.usage.mode` instead. This is a hard break: the old key is not emitted.
    See [Models & Providers](../../reference/models.md) for what each mode value means.

### Call Status Glossary (Authoritative)

Lifecycle statuses:

- `initiated`: Call record created and setup started.
- `answered`: Bridge signaled call answer and media path became ready.
- `completed`: Call ended after an answered/active session.

Terminal setup outcomes:

- `busy`: Callee line is busy.
- `no_answer`: Callee did not answer in time.
- `rejected`: Callee/provider explicitly rejected the call.
- `cancelled`: Setup was cancelled or terminated before answer.
- `unreachable`: Destination number is unreachable/invalid for routing.
- `timeout`: Setup timed out before completion.
- `failed`: Generic setup/runtime failure not represented by the above outcomes.

## Current Runtime Payload Shape

The webhook payload is generated from the stored call record and currently includes:

- `room_name`
- `queue_id` (outbound calls only — matches the `queue_id` from `POST /call/outbound`)
- `assistant_id`
- `assistant_name`
- `to_number`
- `call_status`
- `call_status_reason`
- `sip_status_code`
- `sip_status_text`
- `answered_at`
- `agent_ready_at` (internal diagnostic — see schema note above)
- `call_end_reason`
- `recording_path`
- `transcripts`
- `started_at`
- `ended_at`
- `call_duration_minutes`
- `billable_duration_minutes`
- `created_by_email`
- `call_type`
- `call_service`
- `platform_number`
- `usage` (object with per-component LLM / TTS / STT metrics, included when available)

### Quick Test with curl

```bash
curl -X POST "https://your-webhook-url" \
  -H "Content-Type: application/json" \
  -d '{
    "success": true,
    "message": "Call details fetched successfully",
    "data": {
      "room_name": "550e8400-e29b-41d4-a716-446655440000_abc123",
      "assistant_id": "550e8400-e29b-41d4-a716-446655440000",
      "assistant_name": "Support Agent",
      "to_number": "+15550200000",
      "recording_path": "https://your-bucket.s3.us-east-1.amazonaws.com/recordings/call_abc123.ogg",
      "transcripts": [
        {
          "speaker": "agent",
          "text": "Hello John, how can I help you today?",
          "timestamp": "2024-01-15T10:00:01.000Z"
        },
        {
          "speaker": "user",
          "text": "I need help with my order.",
          "timestamp": "2024-01-15T10:00:05.000Z"
        }
      ],
      "started_at": "2024-01-15T10:00:00.000Z",
      "ended_at": "2024-01-15T10:05:30.000Z",
      "call_duration_minutes": 5.5,
      "billable_duration_minutes": 6,
      "call_type": "outbound",
      "call_service": "exotel",
      "platform_number": "08044319240"
    }
  }'
```

### Webhook Response

Your webhook endpoint should return a `200 OK` response. The response body is not processed.

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"received": true}
```

!!! warning "Important"

    - Webhooks are sent when call status becomes terminal (for example `completed`, `busy`, `no_answer`, `failed`)
    - Delivery is retried: up to `END_CALL_WEBHOOK_ATTEMPTS` attempts (default `3`) with a 1s/2s backoff between them
    - Each attempt allows 10s to connect and `END_CALL_WEBHOOK_TIMEOUT` seconds to answer (default `30`)
    - Retried: connection errors, read timeouts, `429` and any `5xx`. **Not** retried: any other `4xx` — your endpoint has read the payload and rejected it, so re-sending it cannot help
    - Because a failed attempt is retried, your endpoint must be **idempotent** — key on `data.room_name` (or `data.queue_id` for outbound) and ignore a payload you have already stored
    - Current runtime treats non-2xx HTTP status as failed delivery in runtime logging
    - Current runtime does not parse webhook response body, but records the status code and the first 500 characters of the body in the `end_call_webhook` activity log (`GET /logs?log_type=end_call_webhook&room_name=<room_name>`) for troubleshooting
    - `recording_path` can be empty/null when recording fails after runtime retries
    - Empty `recording_path` does not block terminal webhook delivery
    - A slow endpoint is tolerated, not free: every retry holds the worker's teardown path open, so answer `2xx` first and do your own processing afterwards

### Per-assistant delivery settings

The right timeout belongs to your endpoint, not to the platform — one endpoint answers in 80 ms,
another writes the payload to its own database first and needs 45 seconds. Rather than moving
the global default for everyone, set it on the assistant:

```json title="POST /assistant/create or PATCH /assistant/update/{assistant_id}"
{
  "assistant_end_call_url": "https://your-app.example.com/hooks/lvk-call-ended",
  "assistant_end_call_webhook": {
    "timeout_seconds": 45,
    "attempts": 5
  }
}
```

| Field | Range | Unset / `null` |
| :--- | :--- | :--- |
| `timeout_seconds` | `1`–`120` | server default `END_CALL_WEBHOOK_TIMEOUT` (`30`) |
| `attempts` | `1`–`5` | server default `END_CALL_WEBHOOK_ATTEMPTS` (`3`) |

On `PATCH` the object is merged with what is stored, like `assistant_interaction_config`: naming
only `attempts` keeps your stored timeout, and sending a field as `null` returns it to the
server default.

A `webhook_url` passed directly (the passthrough-trunk path) has no assistant behind it and uses
the server defaults.

Diagnosing a webhook that did not arrive:
[Troubleshooting](../../reference/troubleshooting.md#the-end-of-call-webhook-does-not-arrive).
    - For outbound calls, use `data.queue_id` to correlate the webhook with the original `POST /call/outbound` response. For inbound/web calls, use `data.room_name`.
    - `billable_duration_minutes` is calculated by the backend using the platform billing rule, so clients should not recompute rounding locally

### Exotel Terminal Mapping Notes

- Exotel outbound setup can complete asynchronously after the initial `202 Accepted` API response.
- If SIP returns `200 OK` but no RTP arrives (`no_rtp_after_answer`), runtime surfaces final `call_status` as `failed`.
- Final status is emitted once per call lifecycle in webhook delivery flow.

### How to Read Outbound Outcomes

- Outbound API response status (`200`/`202`/`4xx`/`5xx`) indicates request validation/acceptance at API time.
- For asynchronous Exotel setup, webhook `data.call_status` is authoritative for lifecycle updates and terminal outcomes.
- Treat terminal statuses (`completed`, `busy`, `no_answer`, `rejected`, `cancelled`, `unreachable`, `timeout`, `failed`) as final outcomes.
- Use `data.call_duration_minutes` for actual elapsed time and `data.billable_duration_minutes` for billing/charge display.

### Public Payload vs Internal Tracking

Internal delivery-tracking fields (for example webhook claim/inflight timestamps) are runtime internals and are not part of the public webhook payload contract.

`agent_ready_at` does appear in the payload (it's a plain field on the stored call record, not filtered out), but it exists for the dispatcher's own silent-agent detection, not as a feature for webhook consumers. Treat it as informational only.
