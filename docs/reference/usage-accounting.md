# Usage accounting

Every call writes one `UsageRecord`, keyed by `room_name`, holding the raw usage each
provider will bill for. These are counts, not costs — no rate is stored anywhere, and
nothing in the platform converts usage to money.

The record reaches you three ways: the [end-of-call webhook](../api/calls/webhook.md), the
`usage_records` collection directly, and the admin analytics endpoints
([summary](../api/admin/token-summary.md), [by user](../api/admin/tokens-by-user.md),
[by assistant](../api/admin/tokens-by-assistant.md)).

## Where the numbers come from

`src/core/agents/usage.py::summarize_usage` reads `session.usage.model_usage` at teardown.
The LiveKit agents SDK collects that itself from the plugin metrics of every component the
`AgentSession` owns, so nothing here makes an extra provider call, and a self-hosted worker
needs no Cloud credentials.

The SDK reports **one entry per `(provider, model)` pair**. Those entries are both stored
raw in `model_usage` and summed into the flat columns.

## Read `model_usage` for pricing

The flat columns exist for the dashboards that already aggregate on them. They sum across
models, so a call that swapped LLM mid-session reports one blended row and cannot be priced
correctly from those columns alone.

`model_usage` is the list the SDK produced, one dict per component instance:

```json
[
  {
    "type": "llm_usage",
    "provider": "openai",
    "model": "gpt-4.1-mini",
    "input_tokens": 8400,
    "input_cached_tokens": 6144,
    "input_text_tokens": 8400,
    "input_cached_text_tokens": 6144,
    "input_cache_creation_tokens": 0,
    "output_tokens": 1230,
    "output_text_tokens": 1230,
    "session_duration": 0.0
  },
  {
    "type": "tts_usage",
    "provider": "cartesia",
    "model": "sonic-3",
    "characters_count": 485,
    "audio_duration": 32.5
  }
]
```

Every key is present even when zero, so a missing key means a schema change, never a zero.
Entries are limited to the billable components — `llm_usage`, `tts_usage`, `stt_usage`. The
SDK also reports `eot_usage` for the turn detector; this deployment runs
`inference.TurnDetector(version="v1-mini")` locally, so it costs nothing and is not stored.

## Cached tokens are a subset

This is the easiest thing to get wrong, and it overcharges silently:

```text
input_cached_text_tokens  ⊆  input_text_tokens  ⊆  input_tokens
llm_total_tokens = input_tokens + output_tokens      # already contains the cached tokens
```

To price the input, split it:

```text
uncached_text = input_text_tokens - input_cached_text_tokens
cost = uncached_text * full_rate + input_cached_text_tokens * cached_rate
```

`input_cache_creation_tokens` is the exception. It counts tokens written *into* the cache,
which some providers bill on top of the read, so it is additive. OpenAI does not charge for
cache writes and reports `0`.

## What each mode records

| | `cascade` | `pipeline` | `realtime` |
|---|---|---|---|
| LLM tokens, including cached | yes | yes | yes |
| Modality split (audio/text/image) | text only | yes | yes |
| TTS characters or tokens | yes | yes | not applicable — the model speaks |
| STT | yes | **not yet** | **not yet** |

## Known gaps

Two sources of transcription spend are not recorded yet. Both show as `0`, which is
indistinguishable from "not used" — do not price a `pipeline` or `realtime` call as if its
transcription were free.

- **Pipeline-mode Sarvam.** The parallel tap
  (`src/core/agents/stt/sarvam_parallel.py`) builds its own plugin STT that is never handed
  to the `AgentSession`, so its usage events reach no collector.
- **Realtime native transcription.** The OpenAI realtime plugin receives usage on
  `conversation.item.input_audio_transcription.completed` and keeps only the transcript.

## Schema versions

`usage_schema_version` says how much of the record to trust:

| Version | Meaning |
|---|---|
| `1` | Written before 2026-09. Flat LLM and TTS counts only; no cached totals, no token-billed STT/TTS fields, no `model_usage`. Every field added since reads `0` because it was never captured — treat it as unknown, not as zero. |
| `2` | Everything on this page, except the two gaps above. |

There is no backfill. The data was never collected, so it cannot be recovered.

`sdk_version` records the `livekit-agents` version that produced the numbers, because what
the SDK reports changes between releases — `input_cache_creation_tokens`, for instance,
arrived in 1.6.10.

## When a record is all zeros

See [Troubleshooting](troubleshooting.md#usage-record-is-all-zeros).
