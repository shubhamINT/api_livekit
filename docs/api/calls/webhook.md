# End Call Webhook

If the assistant has `assistant_end_call_url` configured, a POST request is sent when the call reaches a terminal state.

### Webhook Request

```http
POST /your-webhook-endpoint HTTP/1.1
Content-Type: application/json

{
  "success": true,
  "message": "Call details fetched successfully",
  "data": {
    "room_name": "550e8400-e29b-41d4-a716-446655440000_abc123",
    "assistant_id": "550e8400-e29b-41d4-a716-446655440000",
    "assistant_name": "Support Agent",
    "to_number": "+15550200000",
    "call_status": "completed",
    "call_status_reason": null,
    "sip_status_code": null,
    "sip_status_text": null,
    "answered_at": "2024-01-15T10:00:02.000Z",
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
    "call_duration_minutes": 5.5
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
| `data.assistant_id`            | string  | ID of the assistant used.                  |
| `data.assistant_name`          | string  | Name of the assistant.                     |
| `data.to_number`               | string  | Phone number that was called.              |
| `data.call_status`             | string  | Call lifecycle status (`initiated`, `answered`, `completed`) or terminal SIP outcome (`busy`, `no_answer`, `rejected`, `cancelled`, `unreachable`, `timeout`, `failed`). |
| `data.call_status_reason`      | string  | Optional detailed reason for non-success outcomes. |
| `data.sip_status_code`         | number  | SIP response code for failed/not-answered outcomes (if available). |
| `data.sip_status_text`         | string  | SIP response reason text for failed/not-answered outcomes (if available). |
| `data.answered_at`             | string  | Timestamp when the user answered (if answered). |
| `data.recording_path`          | string  | S3 URL of the call recording (if enabled). |
| `data.transcripts`             | array   | List of conversation messages.             |
| `data.transcripts[].speaker`   | string  | Who spoke (`agent` or `user`).             |
| `data.transcripts[].text`      | string  | The transcribed text.                      |
| `data.transcripts[].timestamp` | string  | ISO 8601 timestamp.                        |
| `data.started_at`              | string  | Call start time (ISO 8601).                |
| `data.ended_at`                | string  | Call end time (ISO 8601).                  |
| `data.call_duration_minutes`   | number  | Total call duration in minutes.            |

## Current Runtime Payload Shape

The webhook payload is generated from the stored call record and currently includes:

- `room_name`
- `assistant_id`
- `assistant_name`
- `to_number`
- `call_status`
- `call_status_reason`
- `sip_status_code`
- `sip_status_text`
- `answered_at`
- `recording_path`
- `transcripts`
- `started_at`
- `ended_at`
- `call_duration_minutes`

Fields like `from_number` or custom `metadata` are not currently included by runtime unless they are persisted into the call record model.

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
      "call_duration_minutes": 5.5
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
    - Current runtime sends a single webhook request with a 10s timeout
    - Current runtime treats non-2xx HTTP status as failed delivery in runtime logging
    - Current runtime does not parse webhook response body
    - Ensure your webhook endpoint responds quickly (< 10 seconds)
    - Store the `room_name` to correlate with call initiation

### Exotel Terminal Mapping Notes

- Exotel outbound setup can complete asynchronously after the initial `202 Accepted` API response.
- If SIP returns `200 OK` but no RTP arrives (`no_rtp_after_answer`), runtime surfaces final `call_status` as `failed`.
- Final status is emitted once per call lifecycle in webhook delivery flow.

### Public Payload vs Internal Tracking

Internal delivery-tracking fields (for example webhook claim/inflight timestamps) are runtime internals and are not part of the public webhook payload contract.
