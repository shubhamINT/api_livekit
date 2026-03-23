# Trigger Outbound Call

Initiate a call from an assistant to a phone number.

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
| `metadata`     | object | No       | Optional metadata to pass to the call session. Used for placeholder replacement in prompts. |

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

### Response Schema

| Field                 | Type    | Description                                |
| :-------------------- | :------ | :----------------------------------------- |
| `success`             | boolean | Indicates if the operation was successful. |
| `message`             | string  | Human-readable success message.            |
| `data`                | object  | Contains call initiation details.          |
| `data.room_name`      | string  | The LiveKit room name for this call.       |
| `data.agent_dispatch` | object  | LiveKit agent dispatch details.            |
| `data.participant`    | object  | LiveKit participant details.               |

### HTTP Status Codes

| Code | Description                                                                                |
| :--- | :----------------------------------------------------------------------------------------- |
| 200  | Success - Twilio call triggered successfully.                                              |
| 202  | Accepted - Exotel call accepted for asynchronous setup; final outcome is delivered later. |
| 400  | Bad Request - Invalid input data, missing required fields, or trunk type and call service mismatch. |
| 401  | Unauthorized - Invalid or missing Bearer token.                                            |
| 404  | Not Found - Assistant or trunk not found.                                                  |
| 500  | Server Error - Internal server error during call initiation.                               |

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
  "message": "Outbound call triggered successfully",
  "data": {
    "room_name": "550e8400-e29b-41d4-a716-446655440000_abc123",
    "agent_dispatch": {
      "id": "agent_123",
      "state": "JOINING"
    },
    "participant": {
      "sid": "PA_xxx",
      "identity": "phone-+15550200000"
    }
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
  "message": "Outbound call accepted via Exotel bridge",
  "data": {
    "room_name": "exotel-+918044319240-abc123",
    "agent_dispatch": {
      "id": "agent_123",
      "state": "JOINING"
    },
    "status": "initiated"
  }
}
```

For Exotel calls, SIP answer/failure is processed asynchronously. Use the end-call webhook payload for final status (`answered`, `busy`, `no_answer`, `rejected`, etc.).

### Exotel Async Lifecycle Notes

- `202 Accepted` means call setup has started, not that the user has answered.
- Exotel setup outcomes (`busy`, `no_answer`, `rejected`, `cancelled`, `unreachable`, `timeout`, `failed`) are delivered through the end-call webhook.
- The assistant starts Exotel outbound recording only after the bridge signals `call_answered` (post SIP `200 OK`).
- If trunk type and `call_service` do not match (for example, Twilio trunk with `call_service="exotel"`), the API returns `400`.
