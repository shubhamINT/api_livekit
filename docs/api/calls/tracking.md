# Call Status Tracking

Outbound and web calls now have different primary tracking identifiers:

- Outbound queued calls: `queue_id` from `POST /call/outbound`
- Web calls: `room_name` from `/web_call/get_token`

---

## How to Track a Call

### Option 1 — Queue Status for Dispatch Progress

Use `GET /call/queue/{queue_id}` to track whether an outbound request is still waiting for capacity or has already been handed off for dialing.

```bash
curl -X GET "https://api-livekit-vyom.indusnettechnologies.com/call/queue/QUEUE_ID" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

This endpoint is only for outbound queued calls and only reports queue lifecycle state.

### Option 2 — End-Call Webhook (recommended for final outcome)

Configure `assistant_end_call_url` on the assistant. When a call reaches a terminal state, the platform POSTs the full call record, including both actual duration and backend-calculated billable duration, to that URL.

The webhook payload includes `data.queue_id` for outbound calls — this matches the `queue_id` returned by `POST /call/outbound`, so you can correlate the webhook to the original trigger without polling.

See [End Call Webhook](webhook.md) for the complete payload contract.

### Option 3 — Query Call Logs (by assistant)

Use `GET /assistant/call-logs/{assistant_id}` to look up past and current call records for a specific assistant.

```bash
curl -X GET "https://api-livekit-vyom.indusnettechnologies.com/assistant/call-logs/ASSISTANT_ID?page=1&limit=10" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Full query parameters (pagination, date range, sort) are documented in [Call Logs](../assistant/logs.md).

### Option 4 — Query All Call Records (cross-assistant)

Use `GET /call/records` to query across all calls for your account — including passthrough calls (which have no assistant).

Use `GET /call/records/{room_name}/usage` to retrieve the complete usage record for one of your
calls, including per-model attribution.

```bash
# All calls, newest first
curl -X GET "https://api-livekit-vyom.indusnettechnologies.com/call/records?page=1&limit=10" \
  -H "Authorization: Bearer YOUR_API_KEY"

# Passthrough calls only
curl -X GET "https://api-livekit-vyom.indusnettechnologies.com/call/records?passthrough_only=true" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Supports `passthrough_only`, `to_number`, `call_status`, `start_date`, `end_date`, `sort_by`, `sort_order`, `page`, and `limit`. See [Passthrough Calls](passthrough.md#get-call-records) for full parameter reference.

---

## Queue Status Values

| Status | Meaning |
| :--- | :--- |
| `pending` | Request accepted and waiting for dispatcher capacity |
| `dispatching` | Dispatcher is actively creating the room/provider call |
| `dispatched` | Queue handoff succeeded; use webhook or call logs for call lifecycle |
| `failed` | Queue item permanently failed after retries |

---

## Call Status Values

| Status | Meaning |
| :--- | :--- |
| `initiated` | Call setup started |
| `answered` | Call was answered and media path is ready |
| `completed` | Call ended after an active session |
| `busy` | Callee line was busy |
| `no_answer` | Callee did not answer in time |
| `rejected` | Call was explicitly rejected |
| `cancelled` | Setup cancelled before answer |
| `unreachable` | Destination number unreachable |
| `timeout` | Setup timed out |
| `failed` | Generic setup or runtime failure |

!!! info "Exotel async calls"

    For queued outbound calls, `202 Accepted` means the queue insert succeeded.
    Once the dispatcher starts the call, the call record begins as `initiated`.
    The terminal status (`completed`, `busy`, `no_answer`, etc.) is set only after the bridge resolves the outcome.
    Use the webhook or poll call logs to detect the final state.
