# Text to Speech (`POST /tts/synthesize`)

Synthesizes input text into speech audio and streams binary audio or returns base64 JSON, including usage metrics and estimated cost in USD.

## Endpoint

```http
POST /tts/synthesize
Content-Type: application/json
Authorization: Bearer <api_key>
```

## Request Payload

```json
{
  "text": "Hello! Welcome to our platform.",
  "assistant_id": "optional-uuid",
  "provider": "cartesia",
  "model": "sonic-3",
  "voice": "a0e99841-438c-4a64-b679-ae501e7d6091",
  "language": "en",
  "save_to_library": false,
  "response_format": "audio"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | String | Yes | Text to synthesize. 1 to 5,000 characters. |
| `assistant_id` | String | No | Optional assistant ID to inherit voice, model, and custom API key. |
| `provider` | String | No | Provider: `cartesia`, `sarvam`, `elevenlabs`, `mistral`. Default: `cartesia`. |
| `model` | String | No | Provider model (e.g. `sonic-3`, `bulbul:v3`, `eleven_multilingual_v2`, `mistral-tts-1`). |
| `voice` | String | No | Voice ID or Sarvam speaker name (e.g. `meera`). |
| `language` | String | No | Language code. |
| `save_to_library` | Boolean | No | If true, stores the synthesized audio in the user's audio assets library. Default: `false`. |
| `response_format` | String | No | `"audio"` (default binary stream) or `"json"` (base64 audio with full usage object). |

## Response Formats

### 1. Binary Audio Stream (`response_format: "audio"`)

Streams the generated audio with detailed usage and costing headers:

```http
HTTP/1.1 200 OK
Content-Type: audio/wav
Content-Disposition: inline; filename="speech.wav"
Content-Length: 96044
X-TTS-Characters: 31
X-Audio-Duration: 2.000
X-Estimated-Cost-USD: 0.000157
X-Pricing-Complete: true
X-Provider: cartesia
X-Model: sonic-3
```

### 2. JSON Response (`response_format: "json"`)

Returns base64-encoded audio and full usage accounting in the JSON body:

```json
{
  "success": true,
  "message": "Speech synthesized successfully",
  "data": {
    "audio_base64": "UklGRiQAAABXQVZFZm10IBAAAAABAAEA...",
    "media_type": "audio/wav",
    "provider": "cartesia",
    "model": "sonic-3",
    "usage": {
      "characters_count": 31,
      "audio_duration_seconds": 2.0,
      "estimated_cost_usd": 0.000157,
      "pricing_complete": true,
      "provider": "cartesia",
      "model": "sonic-3"
    }
  }
}
```

### Usage & Costing Breakdown

| Field / Header | Type | Description |
|----------------|------|-------------|
| `characters_count` / `X-TTS-Characters` | Integer | Total characters synthesized. |
| `audio_duration_seconds` / `X-Audio-Duration` | Float | Measured length of generated audio in seconds. |
| `estimated_cost_usd` / `X-Estimated-Cost-USD` | Float | Estimated cost in USD calculated from provider character or duration rates. |
| `pricing_complete` / `X-Pricing-Complete` | Boolean | `true` when standard list rates exist for the provider/model combination. |

## Errors

* `401 Unauthorized`: Missing or invalid bearer key.
* `404 Not Found`: `assistant_id` not found or unowned.
* `422 Unprocessable Content`: Empty text, text > 5,000 characters, or invalid speaker for model.
* `502 Bad Gateway`: Upstream provider failure.
