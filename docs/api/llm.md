# Large Language Model (`POST /llm/chat`)

Executes conversational completions using configured OpenAI or Gemini models, supporting both standard JSON responses and Server-Sent Events (SSE) token streaming. Every response includes exact token consumption and estimated cost in USD.

## Endpoint

```http
POST /llm/chat
Content-Type: application/json
Authorization: Bearer <api_key>
```

## Request Payload

```json
{
  "messages": [
    {"role": "system", "content": "You are a helpful customer assistant."},
    {"role": "user", "content": "What services do you offer?"}
  ],
  "assistant_id": "optional-uuid",
  "provider": "openai",
  "model": "gpt-5.4",
  "temperature": 0.7,
  "max_tokens": 1000,
  "stream": false
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `messages` | Array | Yes | List of message objects with `role` (`system`, `user`, `assistant`) and `content`. |
| `assistant_id` | String | No | Optional assistant ID to inherit LLM provider, model, and custom API key. |
| `provider` | String | No | Provider: `openai` or `gemini`. Default: `openai`. |
| `model` | String | No | Model name (e.g. `gpt-5.4`, `gpt-4.1`, `gemini-2.5-flash`). |
| `temperature` | Float | No | Temperature between 0.0 and 2.0. |
| `max_tokens` | Integer | No | Maximum tokens to generate. |
| `stream` | Boolean | No | If true, streams responses via SSE (`text/event-stream`). Default: `false`. |

## Response (Non-Streaming)

```json
{
  "success": true,
  "message": "Chat completion successful",
  "data": {
    "message": {
      "role": "assistant",
      "content": "We offer voice AI calling, speech-to-text, and conversational agents."
    },
    "provider": "openai",
    "model": "gpt-5.4",
    "usage": {
      "prompt_tokens": 24,
      "completion_tokens": 16,
      "total_tokens": 40,
      "estimated_cost_usd": 0.000190,
      "pricing_complete": true,
      "provider": "openai",
      "model": "gpt-5.4"
    }
  }
}
```

### Usage & Costing Breakdown

| Field | Type | Description |
|-------|------|-------------|
| `prompt_tokens` | Integer | Number of input / prompt tokens processed. |
| `completion_tokens` | Integer | Number of generated completion tokens. |
| `total_tokens` | Integer | Total tokens (`prompt_tokens + completion_tokens`). |
| `estimated_cost_usd` | Float | Estimated cost in USD based on published prompt and completion rates. |
| `pricing_complete` | Boolean | `true` when standard list rates exist for the model. |

## Response (Streaming)

When `stream: true`, the response returns `Content-Type: text/event-stream` with delta chunks:

```text
data: {"choices": [{"delta": {"content": "We"}}]}

data: {"choices": [{"delta": {"content": " offer"}}]}

data: [DONE]
```

## Errors

* `401 Unauthorized`: Missing or invalid bearer key.
* `404 Not Found`: `assistant_id` not found or unowned.
* `422 Unprocessable Content`: Empty messages list or invalid model/provider.
* `502 Bad Gateway`: Upstream provider failure or network timeout.
