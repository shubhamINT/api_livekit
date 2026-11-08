# Speech to Text (`POST /stt/transcribe`)

Transcribes an audio file into text using direct provider parameters or inherited assistant configurations. Provides real-time transcription, language detection, audio duration, and estimated pricing in USD.

## Endpoint

```http
POST /stt/transcribe
Content-Type: multipart/form-data
Authorization: Bearer <api_key>
```

## Form Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file` | Binary | Yes | Audio file (`wav`, `mp3`, `ogg`, `webm`, `m4a`). Maximum 25 MB (`MAX_UPLOAD_BYTES`). |
| `assistant_id` | String | No | Optional assistant ID to inherit STT model, language, and custom API key. |
| `provider` | String | No | STT Provider: `sarvam`, `cartesia`, `deepgram`, `openai`, `elevenlabs`. Default: `sarvam`. |
| `model` | String | No | Provider model (e.g. `saaras:v3`, `saaras:v4`, `ink-whisper`, `nova-3`, `whisper-1`, `scribe_v1`). |
| `language` | String | No | Language code (e.g. `en-US`, `hi-IN`, `auto`). |

## Response Payload

```json
{
  "success": true,
  "message": "Audio transcribed successfully",
  "data": {
    "text": "Hello world, this is a transcribed message.",
    "language": "en",
    "duration_seconds": 2.4,
    "provider": "sarvam",
    "model": "saaras:v3",
    "usage": {
      "audio_duration_seconds": 2.4,
      "estimated_cost_usd": 0.000239,
      "pricing_complete": true,
      "provider": "sarvam",
      "model": "saaras:v3"
    }
  }
}
```

### Usage & Costing Breakdown

| Field | Type | Description |
|-------|------|-------------|
| `audio_duration_seconds` | Float | Measured length of the uploaded audio file in seconds. |
| `estimated_cost_usd` | Float | Calculated cost in USD based on standard PAYG rates for the chosen model. |
| `pricing_complete` | Boolean | `true` when standard list rates exist for the provider/model combination. |
| `provider` | String | Resolved STT provider. |
| `model` | String | Resolved STT model identifier. |

## Errors

* `401 Unauthorized`: Missing or invalid bearer key.
* `404 Not Found`: `assistant_id` not found or unowned.
* `413 Payload Too Large`: Audio file exceeds the 25 MB limit.
* `422 Unprocessable Content`: Empty audio file or unsupported model/provider.
* `502 Bad Gateway`: Upstream provider failure or network error.
