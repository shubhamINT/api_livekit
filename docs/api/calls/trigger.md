# Trigger Outbound Call

Queue an outbound call from an assistant to a phone number.

- **URL**: `/call/outbound`
- **Method**: `POST`
- **Headers**: `Authorization: Bearer <your_api_key>`
- **Content-Type**: `application/json`

### Request Body

| Field          | Type   | Required | Description                                                                                 |
| :------------- | :----- | :------- | :------------------------------------------------------------------------------------------ |
| `assistant_id` | string | Yes      | The ID of the assistant to use (UUID format).                                               |
| `trunk_id`     | string | Yes      | The ID of the SIP trunk to use (format: `ST_...`).                                          |
| `to_number`    | string | Yes      | The phone number to call in E.164 format (e.g., `+15550100000`).                            |
| `call_service` | string | Yes      | The telephony provider. One of: `twilio`, `exotel`. Must match the selected trunk type.     |
| `metadata`     | object | No       | Optional metadata to pass to the call session. Any JSON object; its shape is the placeholder path in prompts. |

### Metadata and Placeholders

The `metadata` object can contain any key-value pairs. These values are used to replace placeholders in the assistant's prompt and start instruction.

**Example:**

If your assistant has:

```json
{
  "assistant_prompt": "Hello {{name}}, you're calling from {{company}}.",
  "assistant_start_instruction": "Hi {{name}}, this is {{agent_name}} speaking."
}
```

Then your metadata should be:

```json
{
  "metadata": {
    "name": "John Doe",
    "company": "Acme Corp",
    "agent_name": "Sarah"
  }
}
```

The rule is that **your payload's shape is the placeholder path.** Send a value flat and reference it flat; nest it and reference it with a dot. The word `metadata` is never part of a placeholder — it is only the field the values travel in.

**Nested example:**

```json
{
  "metadata": {
    "customer": { "name": "John Doe", "plan": "Enterprise" },
    "agent": { "name": "Sarah" }
  }
}
```

```json
{
  "assistant_prompt": "You are {{agent.name}}. The customer is {{customer.name}} on {{customer.plan}}."
}
```

Missing keys render as empty strings. Alongside your own keys, `{{call.to_number}}` and `{{call.call_service}}` are always available.

See [Using Placeholders](../assistant/placeholders.md) for the full reference — nesting, arrays, optional-text sections, and how the identical rule applies to inbound calls.

### Response Schema

| Field                 | Type    | Description                                |
| :-------------------- | :------ | :----------------------------------------- |
| `success`             | boolean | Indicates if the operation was successful. |
| `message`             | string  | Human-readable success message.            |
| `data`                | object  | Contains queue acknowledgement details.    |
| `data.queue_id`       | string  | Queue identifier for status polling.       |
| `data.status`         | string  | Initial queue state. Usually `queued`.     |

### HTTP Status Codes

| Code | Description                                                                                |
| :--- | :----------------------------------------------------------------------------------------- |
| 202  | Accepted - outbound call request queued successfully.                                      |
| 400  | Bad Request - Invalid input data, missing required fields, or trunk type and call service mismatch. |
| 401  | Unauthorized - Invalid or missing Bearer token.                                            |
| 404  | Not Found - Assistant or trunk not found.                                                  |
| 500  | Server Error - Internal server error during queue insertion or later dispatch.             |

### Example: Basic Outbound Call

```bash
curl -X POST "https://api-livekit-vyom.indusnettechnologies.com/call/outbound" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <your_api_key>" \
     -d '{
           "assistant_id": "550e8400-e29b-41d4-a716-446655440000",
           "trunk_id": "ST_a1b2c3d4e5f6...",
           "to_number": "+15550200000",
           "call_service": "twilio"
         }'
```

**Response:**

```json
{
  "success": true,
  "message": "Outbound call queued successfully",
  "data": {
    "queue_id": "8b7df5ea0fdc497ea4f44bd31954a387",
    "status": "queued"
  }
}
```

### Example: Exotel Outbound Call

```bash
curl -X POST "https://api-livekit-vyom.indusnettechnologies.com/call/outbound" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer <your_api_key>" \
     -d '{
           "assistant_id": "550e8400-e29b-41d4-a716-446655440000",
           "trunk_id": "ST_exotel_abc123",
           "to_number": "+918044319240",
           "call_service": "exotel"
         }'
```

**Response:**

```json
{
  "success": true,
  "message": "Outbound call queued successfully",
  "data": {
    "queue_id": "9c1ad10ef9b6484aad8e8d15a299f4b8",
    "status": "queued"
  }
}
```

After you receive the `queue_id`, poll [Queue Status](queue-status.md) if you need to know whether the dispatcher has picked up the job. Once the call is actually dispatched, use the end-call webhook payload (`data.call_status`) or assistant call logs for lifecycle updates and terminal outcomes.

### Queueing Notes

- `POST /call/outbound` no longer returns `room_name`, LiveKit dispatch metadata, or SIP participant details.
- The API validates assistant ownership and active trunk ownership before the queue item is inserted.
- Queue insertion is per-user; `GET /call/queue/{queue_id}` is also scoped to the authenticated user.
- Queue status tracks dispatch progress only. It does not replace final call outcome tracking.

### Exotel Async Lifecycle Notes

- `202 Accepted` means the request was queued successfully, not that provider setup has started or the user has answered.
- Dispatcher capacity determines when provider setup begins.
- Exotel setup outcomes (`busy`, `no_answer`, `rejected`, `cancelled`, `unreachable`, `timeout`, `failed`) are delivered through the end-call webhook.
- Assistant speech/transcript processing starts only after bridge readiness (`call_answered`), not merely after `202 Accepted`.
- The assistant starts Exotel outbound recording only after the bridge signals `call_answered` (post SIP `200 OK`).
- Speaking itself is bounded, not instant on answer: the assistant waits for `call_answered` (up to `60s`), then for recording to start (up to `12s`), then a short fixed RTP/egress warmup pause — all raced against the callee hanging up, so a call that ends right after answer never blocks on the rest of this sequence.
- If trunk type and `call_service` do not match (for example, Twilio trunk with `call_service="exotel"`), the API returns `400`.

### Exotel Outcome Mapping (SIP to Final `call_status`)

`POST /call/outbound` with `call_service="exotel"` returns `202 Accepted` once the queue insert succeeds. Final outcomes are asynchronous and delivered through the end-call webhook (`data.call_status`) after the dispatcher actually starts the call.

| SIP/Runtime Outcome | Final `call_status` | Meaning |
| :--- | :--- | :--- |
| `486 Busy Here`, `600 Busy Everywhere` | `busy` | Callee line is busy. |
| `408 Request Timeout`, `480 Temporarily Unavailable` | `no_answer` | Callee did not answer in time. |
| `403 Forbidden`, `603 Decline` | `rejected` | Call was explicitly rejected. |
| `487 Request Terminated` | `cancelled` | Call setup was cancelled/terminated before answer. |
| `404 Not Found`, `410 Gone`, `484 Address Incomplete` | `unreachable` | Destination number is unreachable or invalid. |
| Bridge/SIP timeout path | `timeout` | Setup timed out before successful answer flow. |
| Any other setup failure | `failed` | Generic setup failure; check `call_status_reason` and SIP fields if present. |
