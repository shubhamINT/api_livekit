# Cascade Pipeline (STT → LLM → TTS)

`assistant_mode="cascade"` runs a **true three-stage pipeline**: a plugin STT, a plain
(non-realtime) LLM, and a plugin TTS. Each stage is a separate model, separately billed and
independently swappable.

This is the mode to pick when you need per-component cost visibility, cheap text models, or a
specific STT provider. The other two modes are documented in [Runtime Modes](runtime-modes.md).
For the model IDs and config keys used below, see [Models & Providers](../reference/models.md).

## Why it exists

`pipeline` mode is really a *half*-cascade: a realtime model does STT **and** LLM in one
opaque billing unit, and only TTS is separate. That has three consequences:

1. **No cost breakdown.** A realtime model bills one audio-token stream. You cannot tell what
   transcription cost versus reasoning.
2. **No cheap models.** The LLM must be a realtime model; `gpt-4.1-mini` is unreachable.
3. **STT is a side channel.** The Sarvam tap opens its own audio stream outside the SDK's
   pipeline, because the `stt=` slot was never used.

Cascade fixes all three by giving the session a real STT stage.

```
pipeline (half-cascade)     realtime                cascade (true pipeline)
─────────────────────       ──────────────          ───────────────────────
 caller audio                caller audio            caller audio
      │                           │                       │
 ┌────▼─────┐  (+ Sarvam     ┌────▼─────┐            ┌────▼────┐
 │ realtime │   tap on the   │ realtime │            │   STT   │  sarvam | cartesia | deepgram | elevenlabs | openai
 │  model   │   side for     │  model   │            └────┬────┘
 │ STT+LLM  │   transcripts) │STT+LLM+  │            ┌────▼────┐
 └────┬─────┘                │   TTS    │            │   LLM   │  openai
 ┌────▼─────┐                └────┬─────┘            └────┬────┘
 │   TTS    │                     │                  ┌────▼────┐
 └────┬─────┘                     │                  │   TTS   │  4 providers
      ▼                           ▼                  └────┬────┘
  agent audio                agent audio                  ▼
                                                      agent audio
```

## Configuration

```json
{
  "assistant_name": "Cascade Agent",
  "assistant_description": "True STT -> LLM -> TTS pipeline",
  "assistant_prompt": "You are a helpful assistant.",
  "assistant_mode": "cascade",
  "assistant_stt_model": "sarvam",
  "assistant_stt_config": {
    "model": "saaras:v3",
    "language": "unknown",
    "mode": "codemix"
  },
  "assistant_llm_config": {
    "provider": "openai",
    "model": "gpt-4.1-mini"
  },
  "assistant_tts_model": "cartesia",
  "assistant_tts_config": {
    "voice_id": "a167e0f3-df7e-4277-976b-be2f952fa275"
  }
}
```

Validation rules specific to cascade:

| Rule | Why |
|---|---|
| `assistant_tts_model` + `assistant_tts_config` required | The LLM emits text only; something must speak it. |
| `assistant_stt_model` must be `sarvam`, `cartesia`, `deepgram`, `elevenlabs` or `openai` | `native` means "the realtime model transcribes itself" — cascade has no realtime model. |
| `assistant_llm_config.provider` must be `openai` or unset | Only OpenAI is wired up as a non-realtime LLM. |
| `assistant_llm_config.model` must be a documented OpenAI ID | Curated allowlist so users pick a tested model; unknown names are rejected with `422`. See [Models & Providers](../reference/models.md#cascade-llm-cascade-mode-only). |

These rules are re-checked against the **stored** assistant on update, not just against the request:
switching an existing assistant into cascade while it still holds `provider: "gemini"` or a realtime
`model` returns `400`, so send the corrected `assistant_llm_config` in the same PATCH. Every mode's
rules, and what happens when you get one wrong, are tabulated in the
[Compatibility Matrix](../reference/compatibility.md).

## STT stage

Built by `create_stt` in `src/core/agents/stt/factory.py`. All providers stream by default
(`openai` is the one that can be switched to batch — see `use_realtime` below).

The Sarvam stage is wrapped in `MeteredSarvamSTT` (`src/core/agents/stt/cascade_usage.py`).
Transcription is unchanged; only usage reporting is. The plugin reports the audio duration the
Sarvam server sent, a field that is missing on some responses and absent entirely for a turn
that transcribed to nothing, so the session counts the frames itself and the plugin's own
metrics are dropped before the SDK's collector sees them. The other four providers count their
own frames, or — for `openai` — report the billing tokens, and are used as they come.

**API keys and fallback.** Every STT provider accepts an `api_key` in
`assistant_stt_config`; a per-assistant value always beats the system key below.

| System key | Provider | Note |
|---|---|---|
| `SARVAM_API_KEY` | `sarvam` | Sarvam is STT **and** TTS — one key serves both |
| `CARTESIA_API_KEY` | `cartesia` | |
| `DEEPGRAM_API_KEY` | `deepgram` | |
| `ELEVENLABS_API_KEY` | `elevenlabs` | ElevenLabs is STT **and** TTS — one key serves both |
| `OPENAI_API_KEY` | `openai` | the same variable the cascade LLM stage reads |

If both the per-assistant `api_key` and the system key are missing, the assistant is **refused at
create/update** with a `422`/`400` naming the missing environment variable — the stage cannot
authenticate, so the call would connect to silence. Should a stored row still reach the runtime
without a key (written before this check existed), `create_stt` returns `None` and the cascade job
**aborts** with a logged error — it does **not** silently fall back or swap providers. (Separately, selecting a cascade-only provider — cartesia / deepgram /
elevenlabs — in `pipeline` mode runs no tap; the conversation LLM self-transcribes, the
provider is ignored and a warning is logged. `openai` collapses to the same self-transcription
without a warning, because there is nothing to lose: same vendor, same model.)

**Pitfalls & what not to combine.** Deepgram's `keyterm` is ignored on `nova-2` and
`enable_diarization` is nova-only; `flux-general-en` is English-only. Setting an ElevenLabs
`language_code` disables auto-detect. And the omission defaults differ: omitted `language` on
Deepgram falls back to `en` (not `multi`), whereas omitted `language_code` on ElevenLabs can
auto-detect. Full list: [STT pitfalls & what not to combine](../reference/models.md#stt-pitfalls-what-not-to-combine).

### sarvam — the multilingual default

| Config key | Default | Values |
|---|---|---|
| `model` | `saaras:v3` | see [Models & Providers](../reference/models.md#stt) |
| `language` | `unknown` | `unknown` = **auto-detect**, or a fixed BCP-47 code |
| `mode` | `codemix` | see [Models & Providers](../reference/models.md#stt) |
| `api_key` | system `SARVAM_API_KEY` | per-assistant override |

**This is the only genuinely multilingual option.** `language="unknown"` auto-detects, and
`mode="codemix"` keeps code-switching intact *inside a single utterance* — a caller who says a
Hindi sentence with English nouns is transcribed in both scripts correctly. Full list of the 24
`-IN` language codes: [Models & Providers](../reference/models.md#stt).

The other modes: `transcribe` gives a plain transcript, `translate` returns English,
`verbatim` keeps filler words and repetitions, `translit` romanises Indic script.

### cartesia — single fixed language

| Config key | Default | Values |
|---|---|---|
| `model` | `ink-whisper` | see [Models & Providers](../reference/models.md#stt) |
| `language` | `en` | one fixed code — **no auto-detect** |
| `api_key` | system `CARTESIA_API_KEY` | per-assistant override |

Cartesia STT cannot detect language: you pick one code and it transcribes that. Use Sarvam for
any call where the caller might switch languages.

`model` is pinned explicitly in the factory rather than left to the plugin default, because
that default flipped from `ink-whisper` to the English-only `ink-2` in `livekit-agents` 1.5.15.
`ink-whisper`'s 43 language codes: [Models & Providers](../reference/models.md#stt).

### deepgram — multilingual with `nova-3`

| Config key | Default | Values |
|---|---|---|
| `model` | `nova-3` | `nova-3` (multilingual, 45 languages), `nova-2`, `flux-general-en` (English), `flux-general-multi` — swapping changes the transcription family; omitted keeps the default |
| `language` | `multi` on `nova-3` / `flux-general-multi`, else `en-US` | a fixed BCP-47 code (`en-US`, `hi-IN`), or `multi` to **auto-detect** per segment. A 3-letter code such as `hin` belongs to ElevenLabs and is rejected here. On the flux models this becomes `language_hint`, which only `flux-general-multi` reads |
| `enable_diarization` | `false` | `bool` — label each utterance with its speaker (nova models) — `true` turns it on; **omitted stays `false`, never force-enabled** |
| `keyterm` | not sent | string or list of terms to bias recognition toward (`nova-3`/`flux` only) — set to bias; **omitted — the key is not sent, no biasing** |
| `api_key` | system `DEEPGRAM_API_KEY` | per-assistant override — wins over the env key |

`model="nova-3"` with `language="multi"` covers 45 languages and auto-detects, so it is the
Multilingual Deepgram option: a caller who switches languages mid-call is still transcribed
correctly without pinning a code.

**Omitted-knob summary:** `language` omitted → `multi` on the models that can detect (`nova-3`, `flux-general-multi`), `en-US` on the ones that cannot — `multi` bills at a higher per-minute rate, so pin a code to avoid it; `enable_diarization` omitted → stays off (never force-enabled); `keyterm` omitted → not sent (no biasing).

### elevenlabs — auto-detecting `scribe_v2_realtime`

| Config key | Default | Values |
|---|---|---|
| `model` | `scribe_v2_realtime` | `scribe_v2_realtime` (auto-detects ~190 languages), `scribe_v2`, `scribe_v1` — swapping changes the Scribe generation; omitted keeps the default |
| `language_code` | omitted → auto-detect | an **ISO 639-3** code (`eng`, `hin`, `ben`) — **not** BCP-47 and **not** ISO 639-1. Scribe answers anything else with `1008 invalid_request` and closes the socket, so an unrecognized code is rejected before it is sent and the call auto-detects. Setting a valid code **disables auto-detect** |
| `no_verbatim` | `false` | `bool` — strip filler words ("um", "uh") from the transcript — `true` strips them; **omitted stays `false`, fillers kept** |
| `api_key` | system `ELEVENLABS_API_KEY` | per-assistant override — wins over the env key; the same variable serves the ElevenLabs TTS stage |

`scribe_v2_realtime` auto-detects roughly 190 languages with no config needed, making it a
drop-in multilingual option alongside `sarvam` and `deepgram`. Authentication is the single
`ELEVENLABS_API_KEY` — the same variable the ElevenLabs TTS provider reads, so setting it once
covers both stages.

**Omitted-knob summary:** `language_code` omitted → auto-detect (~190 languages); `no_verbatim` omitted → `false` — fillers kept.

### openai — one vendor for STT and LLM

| Config key | Default | Values |
|---|---|---|
| `model` | `gpt-4o-mini-transcribe` | `gpt-4o-mini-transcribe` (fast, cheap), `gpt-4o-transcribe` (more accurate, dearer), `whisper-1` (legacy batch model — the only one that reads `prompt`). `gpt-realtime-whisper` is **rejected**; omitted keeps the default |
| `language` | omitted → `detect_language` turns on | one fixed ISO 639-1 code (`en`, `hi`) — **not** BCP-47; `hi-IN` is rejected. Ignored when `detect_language` is `true` |
| `detect_language` | `false`, or `true` when no valid `language` is set | `bool` — `true` auto-detects the spoken language and overrides `language` |
| `prompt` | not sent | string biasing spellings and jargon — **`whisper-1` only**, the gpt-4o transcribe models accept and ignore it; omitted sends nothing |
| `noise_reduction_type` | not sent | `near_field` (headset) or `far_field` (speakerphone / room mic); omitted applies none |
| `use_realtime` | `true` | `bool` — `true` streams over OpenAI's realtime transcription WebSocket (interim results, low latency); `false` uses the batch REST API — cheaper, but adds a full utterance of latency per turn, and is **accepted only for `whisper-1`** |
| `api_key` | system `OPENAI_API_KEY` | per-assistant override — wins over the env key; the same variable the cascade LLM stage reads |

Pick this when the assistant is already on OpenAI for the LLM and you want one vendor, one key
and one invoice for both stages. It is *not* the multilingual choice: OpenAI STT pins one
language unless you set `detect_language: true`, and even then Sarvam handles Indic
code-switching better inside a single utterance.

`use_realtime` **inverts the plugin's own default** (which is batch REST). A live phone call
needs interim results and per-utterance streaming, so the factory streams unless you say
otherwise. Setting it `false` is a 422 on every model except `whisper-1`: the batch path
reports no usage at all, and the other OpenAI STT models are billed per token, so the call
would transcribe normally and store zero STT spend. `whisper-1` is billed by audio duration,
which that path measures locally, so it is the one model the pairing is safe for. A row stored
before this gate existed is forced back to streaming at call time, with a warning in the worker
log — a stored config must not start failing calls over a metric. `gpt-realtime-whisper` is rejected outright: it has no server-side endpointing and
the plugin then demands a `livekit-plugins-silero` VAD instance, which this runtime does not
ship (the session's VAD is `inference.VAD` from `livekit-local-inference` and cannot be handed
to an STT plugin). Selecting it aborts the job with a logged error rather than crashing at
connect time.

**Omitted-knob summary:** `language` omitted → auto-detect (the factory turns `detect_language` on rather than letting the plugin's hardcoded `en` pin English); `detect_language` omitted → `false` when a valid `language` is pinned; `prompt` and `noise_reduction_type` omitted → not sent; `use_realtime` omitted → `true` (streaming).

Minimal — English assistant, everything defaulted:

```json
{
  "assistant_stt_model": "openai",
  "assistant_stt_config": {}
}
```

Auto-detecting, on a speakerphone-heavy inbound line:

```json
{
  "assistant_stt_model": "openai",
  "assistant_stt_config": {
    "model": "gpt-4o-transcribe",
    "detect_language": true,
    "noise_reduction_type": "far_field"
  }
}
```

Prompt-biased for domain jargon (needs `whisper-1`, and therefore batch):

```json
{
  "assistant_stt_model": "openai",
  "assistant_stt_config": {
    "model": "whisper-1",
    "language": "en",
    "prompt": "Vyom, LiveKit, Exotel, SIP trunk, Sarvam",
    "use_realtime": false
  }
}
```

## LLM stage

Built by `create_llm` in `src/core/agents/llm/factory.py`, using
`openai.responses.LLM` — the recommended surface for the direct OpenAI API (cheaper than
chat-completions, and the same `@function_tool` contract, so DB-backed tools work unchanged).

| Config key | Default | Notes |
|---|---|---|
| `provider` | `openai` | Only `openai` is supported in cascade |
| `model` | `gpt-4.1` | Must be one of the documented OpenAI models — validated at creation/update. List in [Models & Providers](../reference/models.md#cascade-llm-cascade-mode-only) |
| `api_key` | system `OPENAI_API_KEY` | per-assistant override |
| `temperature` | SDK default (`0.8`) | `0`–`2`. **Chat models only** — reasoning models reject it |
| `max_output_tokens` | model default | cap on output tokens |
| `reasoning_effort` | unset | `none`/`minimal`/`low`/`medium`/`high`/`xhigh`/`max`. **Reasoning models only**, and not on `gpt-5.2`/`gpt-5.4*` while tools are attached |
| `service_tier` | unset | `auto`/`default`/`fast`/`priority` on any model; `flex` on the gpt-5 line only. `scale` is not an OpenAI tier — [measured](../reference/compatibility.md#service_tier-measured) |
| `verbosity` | unset | `low`/`medium`/`high`. **gpt-5 generation only** (`text.verbosity`) |
| `tool_choice` | unset | `auto`/`required`/`none` |
| `parallel_tool_calls` | unset | allow multiple tool calls in one response |

The model list is a **curated allowlist** (`OPENAI_CASCADE_MODELS`, sourced from the model
table in `src/core/model_support/capabilities.py`), enforced by the mode validator. This replaced the old
free-form string: an unknown model now fails fast at assistant creation with a `422` listing the
supported IDs, instead of failing at the first API call. The realtime/pipeline modes have their
own separate lists (`REALTIME_MODELS`, `GEMINI_LIVE_MODELS`) — every mode's model field is
allowlisted now, they simply do not share a list because they talk to different APIs.

Passing the allowlist is necessary, not sufficient. Cascade creates and updates also ask OpenAI
two things no local list can answer: whether the account still serves the model, and whether it
accepts this exact request (model + knobs + tool schemas) — one 16-token probe whose refusal
becomes the `422`. See [Compatibility Matrix](../reference/compatibility.md#cascade-llm-knobs).

These knobs map onto `openai.responses.LLM` constructor args — they are the Responses-API param
surface, not the LiveKit Inference `extra_kwargs` surface. `temperature` and `top_p` are
mutually exclusive on the Responses API; only `temperature` is exposed.

### Model-gated knobs

The three marked above are not "supported everywhere, ignored where irrelevant". OpenAI
answers a knob the model cannot read with a `400`, the Responses plugin raises that as a
non-retryable `APIStatusError` inside `_llm_inference_task`, and it does so on every turn —
the assistant answers the call, greets nobody and never speaks. The only visible symptom over
the WebSocket transport is `There was an issue with your request. Please check your inputs and
try again`, with no mention of which parameter was at fault.

So the pairing is checked twice, from one table (`src/core/model_support/capabilities.py`):

- **at the API** — `validate_mode_config` rejects an impossible pairing with a `422`, so it
  is never stored;
- **at call time** — `create_llm` drops a knob the current model cannot read and logs which
  one and why. A stored config outlives the model it was written for: set `reasoning_effort`
  on `gpt-5`, later switch the assistant to `gpt-4.1`, and the effort stays on the row.

Two cases the table exists to get right, both of which a "starts with gpt-5" test gets wrong:

- **A `gpt-5.x-chat-latest` alias was a chat model.** It sat inside the gpt-5 generation, so it
  read `text.verbosity`, but it was not a reasoning model: `temperature` yes,
  `reasoning_effort` no. All three aliases were retired by OpenAI on 2026-06-19 and are off the
  allowlist now — the case is kept here because it is why membership is spelled out per model
  rather than matched by prefix, and OpenAI can ship another chat alias at any time.
- **`gpt-5.2` / `gpt-5.4*` reject reasoning effort once function tools are attached.** The
  OpenAI plugin injects a default `Reasoning(effort=...)` for those models when the caller
  passes none, so even an empty `assistant_llm_config` sent one; the SDK's own guard for this
  never fires on the Responses path (it filters the key `reasoning_effort`, while the
  Responses payload key is `reasoning`, and it is called without the tool list). `create_llm`
  therefore clears the option after construction when `has_tools=True` — `session.py` passes
  that from the fully-built tool list, DB tools plus the built-in `end_call`.

Every cascade session logs one `Cascade LLM built | assistant=… | model=… | has_tools=… |
knobs=…` line (never the API key). That line is what a Responses `400` should be read against.

## TTS stage

Unchanged from `pipeline` mode — all four providers work identically. See
[create](../api/assistant/create.md) for the per-provider config and
[Models & Providers](../reference/models.md#tts) for the fixed model IDs and synthesis params.

## Turn detection

Cascade has no realtime model, so there is no server-side VAD to defer to — endpointing and
interruption are the session's own job:

```python
AgentSession(
    stt=cascade_stt,
    llm=llm,
    tts=tts,
    vad=inference.VAD(model="silero", min_silence_duration=0.4),
    turn_handling=TurnHandlingOptions(
        turn_detection=inference.TurnDetector(version="v1-mini"),
        endpointing={"mode": "dynamic", "min_delay": 0.3, "max_delay": 1.0},
        interruption={"mode": "vad", "min_duration": 0.5,
                      "false_interruption_timeout": 2.0,
                      "resume_false_interruption": True},
    ),
)
```

**Everything here runs locally — this is a self-hosted deployment.**

- `inference.VAD(model="silero")` is an in-process native binding shipped in
  `livekit-local-inference`, a core SDK dependency. No API key, no network call, nothing to
  prewarm. `min_silence_duration` is raised from the `0.25` default to clear the turn
  detector's `0.25` floor with margin.
- `inference.TurnDetector(version="v1-mini")` is an audio end-of-utterance model whose weights
  ship inside the wheel. The version is **pinned** on purpose: left unpinned the SDK tries the
  Cloud-only `v1` first whenever `LIVEKIT_DEV_MODE` is set, then falls back with a warning.
  14 languages including Hindi.
- `interruption={"mode": "vad"}` — the `adaptive` mode is LiveKit Cloud-only and is silently
  disabled in production, with no local fallback.

Unlike the `pipeline` branch, these interruption knobs are **live**: there is no realtime-model
VAD short-circuiting them.

Note that `SpeechGate` ([Audio Pipeline](audio-pipeline.md#input-speech-gate)) already runs a
vendored Silero ONNX over the same audio for noise gating, so a cascade call runs VAD twice —
once to gate noise upstream, once to endpoint. Correct, but it costs some worker CPU.

## Per-component usage

The reason the mode exists. `src/core/agents/usage.py::summarize_usage` reads
`session.usage`, which reports one typed entry per `(provider, model)` pair, and folds it into
flat `UsageRecord` fields:

| Field | Populated in |
|---|---|
| `llm_model`, `llm_input_*`, `llm_output_*`, `llm_total_tokens` | all modes |
| `llm_input_cached_*`, `llm_input_cache_creation_tokens` | all modes, whenever the provider reports a cache hit |
| `tts_characters_count`, `tts_audio_duration` | `pipeline`, `cascade` |
| `tts_input_tokens`, `tts_output_tokens` | token-billed TTS only |
| `stt_provider`, `stt_model`, `stt_audio_duration` | `cascade`, plus `pipeline` when the Sarvam tap runs. Sarvam is self-measured in **both** modes; the other cascade providers report their own. See [Usage accounting](../reference/usage-accounting.md) |
| `stt_input_tokens`, `stt_output_tokens` | token-billed STT: `openai` in `cascade`, and the Realtime API's own ASR in `pipeline` / `realtime` |
| `stt_input_audio_tokens`, `stt_input_text_tokens` | subsets of `stt_input_tokens`, reported by the Realtime API's ASR only |
| `model_usage`, `usage_schema_version`, `sdk_version` | all modes |
| `usage_finalized` | all modes; `true` only on the write teardown makes — see [Usage accounting](../reference/usage-accounting.md#when-the-record-is-written) |

Only a Gemini `realtime` call leaves the STT fields empty, and nothing is missing there — its
input audio is already inside the LLM prompt tokens. The other two out-of-session paths (the
`pipeline` Sarvam tap, and the ASR the OpenAI Realtime API bills separately) are counted
outside the SDK's collector and handed to `summarize_usage` directly. `model_usage` is the raw per-`(provider, model)` list and is what pricing should
read — the flat columns sum across a mid-call model swap. See
[Usage accounting](../reference/usage-accounting.md).

These values are raw usage metrics, not costs. Apply your own provider rates downstream. They
reach you three ways: the [end-of-call webhook](../api/calls/webhook.md), the
`usage_records` collection, and the admin analytics endpoints
([summary](../api/admin/token-summary.md),
[by user](../api/admin/tokens-by-user.md),
[by assistant](../api/admin/tokens-by-assistant.md)).

All aggregation is in-process; no Cloud call is involved.

## Text-only cascade

`cascade` + `text_only: true` on a [web call](../api/calls/web-call.md) gives a pure text
chatbot on a plain chat model — no STT, no TTS, no VAD instantiated. Cheaper than the same
chatbot on a realtime model. `realtime` mode still rejects `text_only`.

## Feature compatibility

Every pre-existing runtime feature works in cascade. Three needed a cascade-specific
code path, because they were written against a realtime model:

| Feature | Cascade behaviour |
|---|---|
| Prerecorded greeting audio | Unchanged — `session.say(audio=...)` is provider-agnostic |
| Speaks-first / `assistant_start_instruction` | Unchanged — takes the same `generate_reply(instructions=...)` path as pipeline |
| `allow_interruptions=False` on the greeting | **Better than pipeline.** The knob is genuinely live here; pipeline mode's realtime VAD interrupts regardless |
| SpeechGate denoiser / noise cancellation | Unchanged — attached via `RoomOptions`, independent of mode |
| Input guard (blanking at reply start) | Unchanged — mutes through `SpeechGate` |
| Silence watchdog | Unchanged — takes the `session.say` path (`use_llm_for_speech=False`) |
| Filler words | Enabled, same as pipeline. Needs an external TTS, which cascade has |
| Hold / background sound / thinking sound | Unchanged. The thinking sound is *more* audible here, since a real LLM TTFT replaces a realtime model's instant stream |
| Recording (egress), call-readiness gate | Unchanged — mode-agnostic |
| Max call duration watchdog | Unchanged |
| DB-backed function tools | Unchanged — `openai.responses.LLM` honours the same `@function_tool` contract |
| Transcripts | Written exactly once, via `conversation_item_added`. The Sarvam tap is off, so there is no double-write |
| Sarvam TTS keepalive | Runs whenever the TTS is Sarvam, same as pipeline |
| **`end_call` tool** | **Cascade-specific path.** A non-realtime LLM continues in the *same* speech handle across tool steps, so the goodbye has already played by the time the done-callback fires. The `speech_created` wait that realtime needs is skipped — leaving it in burned 5 s of dead air before hangup |
| **Exotel pre-answer window** | **Cascade-specific path.** Pipeline disables the realtime model's server VAD so ring-tone RTP cannot open a spurious turn. Cascade has no such model, so the input is blanked through `SpeechGate.muted` for the duration of the gate wait instead |
| **`preferred_languages`** | **Not read by any cascade STT.** It is a BCP-47 hint for the `native` transcription prompt, and cascade has no native path. Feeding it to a provider both pinned a language nobody asked to pin and pushed BCP-47 into providers that speak ISO 639-1 or ISO 639-3 — pin on `assistant_stt_config` instead |

Two consequences worth knowing:

- The native STT prompt (`build_native_stt_prompt`) and `input_audio_noise_reduction` are
  **Realtime-API parameters and do not apply** in cascade. Transcription quality is the STT
  provider's own; noise handling is `SpeechGate`'s.
- `text_only: true` on a cascade assistant takes the no-audio branch, so no STT, TTS or VAD is
  constructed at all.

## What cascade does not use

- **The Sarvam parallel tap.** Its STT is a first-class session stage, so transcripts arrive
  through `conversation_item_added` like any other. The tap remains for `pipeline` mode.
- **`turn_detection="realtime_llm"`.** No realtime model to detect turns.
- **`input_audio_transcription` / native STT prompts.** Those are Realtime-API parameters.
