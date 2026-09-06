# Compatibility Matrix

Which combinations of `assistant_mode`, LLM provider, STT provider and TTS provider actually run —
and what happens when you pick one that doesn't. [Models & Providers](models.md) documents *what each
knob does*; this page documents *what you are allowed to combine*.

Sourced from the validators in `src/api/models/api_schemas/config/llm_config.py` and
`src/api/routes/assistant.py`, and from the runtime in `src/core/agents/session.py` plus the three
factories under `src/core/agents/`. If this page and any other doc disagree, check the code — and
then fix whichever doc is wrong.

## Legend

| Symbol | Meaning |
|---|---|
| :white_check_mark: | Supported. Validated at create/update, works at call time. |
| :warning: | Accepted and stored, but the field has no effect in this mode. Not an error. |
| :recycle: | Accepted, then degraded at call time to something else, with a warning in the logs. |
| :no_entry: | Rejected by the API with `422` (create / mode-naming update) or `400` (update against stored state). |

---

## Mode × LLM provider

`assistant_llm_config.provider`.

| Provider | `pipeline` | `realtime` | `cascade` |
|---|---|---|---|
| `openai` | :white_check_mark: `gpt-realtime-1.5` in text-only modality, external TTS speaks | :white_check_mark: `gpt-realtime-1.5` speaks its own audio | :white_check_mark: `openai.responses.LLM` (a plain chat model) |
| `gemini` | :no_entry: rejected | :white_check_mark: `gemini-2.5-flash-native-audio-preview-12-2025` (default), handles STT+LLM+TTS | :no_entry: rejected |
| omitted | :white_check_mark: defaults to `openai` | :white_check_mark: defaults to `gemini` | :white_check_mark: defaults to `openai` |

!!! warning "Gemini is realtime-only"
    Gemini used to be selectable in `pipeline` mode and is now rejected at the API. Pipeline mode is
    a [half-cascade](https://docs.livekit.io/agents/models/pipelines.md#half-cascade): the realtime
    model must run in a **text-only response modality** so an external TTS can speak the result.
    Google's Live API only supports that on **non-native-audio** models
    ([googleapis/python-genai#1780](https://github.com/googleapis/python-genai/issues/1780)), and the
    Live models this platform targets are native-audio. The 3.1 Live line additionally ignores
    `generate_reply()`, `update_instructions()` and `update_chat_ctx()`, which the greeting and
    agent-handoff paths depend on.

    **Use Gemini with `assistant_mode: "realtime"`**, where it is fully supported, or use
    `provider: "openai"` in pipeline mode.

### Model IDs

`assistant_llm_config.model` is validated against a different list in each mode, because each mode
talks to a different API.

| Mode | Accepted models | On anything else |
|---|---|---|
| `pipeline` | `REALTIME_MODELS` — `gpt-realtime`, `gpt-realtime-1.5`, `gpt-realtime-2`, `gpt-realtime-2025-08-28`, `gpt-realtime-mini` | `422`. A chat model such as `gpt-4.1` belongs to cascade mode. |
| `realtime` + `openai` | same `REALTIME_MODELS` list | `422` |
| `realtime` + `gemini` | `GEMINI_LIVE_MODELS` — `gemini-2.5-flash-native-audio-preview-12-2025` (default), `gemini-live-2.5-flash-native-audio`, `gemini-3.1-flash-live-preview` | `422` |
| `cascade` | `OPENAI_CASCADE_MODELS` — the chat and reasoning models listed in [Models & Providers](models.md#cascade-llm-cascade-mode-only) | `422` |

Gemini Live model IDs **are** validated, against the installed plugin's own list. The Live API
is a much smaller and slower-moving set than the Gemini chat models, and a chat id such as
`gemini-2.5-flash` is not refused by the plugin — it opens a socket the API then closes, and the
job ends with no audio and nothing naming the cause.

The older `gpt-4o-realtime-preview` / `gpt-4o-mini-realtime-preview` pair is **no longer
accepted**: measured on 2026-08-13, the account does not serve either, so storing one produced a
session that could not connect. They are still named in the code, because the
`session.truncation` rule is asked about stored rows too and those two predate that field.

Every list lives in `src/core/model_support/capabilities.py`. `REALTIME_TRUNCATION_MODELS` is
*derived* from the realtime list rather than restated, because a restated copy drifted: it named
two models the API allowlist rejected, making both entries unreachable.

Beyond these lists, create/update asks OpenAI whether the account still serves the model —
see [Models & Providers → On the allowlist](models.md#on-the-allowlist).

### Realtime voices

`assistant_llm_config.voice` is one field shared by two providers whose rosters have nothing in
common, so the mistake it catches is switching provider and leaving the voice behind.

| Provider | Accepted | On anything else |
|---|---|---|
| `gemini` | the 30 Gemini Live voices (`Puck` (default), `Kore`, `Zephyr`, `Charon`, …) | `422` — closed set in the installed plugin |
| `openai` | any name that is **not** a Gemini voice (`marin` (default), `cedar`, `alloy`, …) | `422` only for a Gemini name |

Asymmetric on purpose: Gemini's roster is a closed `Literal` in the SDK, so a name outside it
cannot work. OpenAI ships realtime voices without a corresponding SDK list, so an unrecognised
name is allowed through rather than blocking a voice released this morning.

### Cascade LLM knobs

Three of the `assistant_llm_config` generation knobs are model-gated. This is not the
"stored but ignored" kind of mismatch further down the page: OpenAI answers a knob the model
cannot read with a `400`, and the Responses plugin raises it as a non-retryable error inside
the LLM turn — **on every turn**. The call connects, the caller hears silence, and the only
log line is `There was an issue with your request. Please check your inputs and try again`.

| Knob | Chat models (`gpt-4.1*`, `gpt-4o*`) | Reasoning models (`gpt-5`, `gpt-5-mini/nano`, `gpt-5.1`, `gpt-5.2`, `gpt-5.4*`, `gpt-5.5`, `gpt-5.6-*`) |
|---|---|---|
| `temperature` | :white_check_mark: | :no_entry: `422` — use `reasoning_effort` |
| `reasoning_effort` | :no_entry: `422` | :white_check_mark: — except `gpt-5.2` / `gpt-5.4*` with tools, see below |
| `verbosity` | :no_entry: `422` — a gpt-5 generation parameter | :white_check_mark: |
| `max_output_tokens`, `parallel_tool_calls` | :white_check_mark: | :white_check_mark: |
| `tool_choice` | :white_check_mark:, but `"required"` needs at least one tool | same |
| `service_tier` | `auto`/`default`/`fast`/`priority` :white_check_mark:; `flex` :no_entry: `422` (gpt-5 only) | all five :white_check_mark: |


### `service_tier`, measured

Not copied from a doc page — probed against the API on 2026-08-13
(`scripts/check_model_allowlist.py --probe <model>` runs the same request):

| Tier | `gpt-4.1` | `gpt-4.1-nano` | `gpt-5-mini` | `chat-latest` | Verdict |
|---|---|---|---|---|---|
| unset | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | **what most assistants should use** |
| `auto` | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | accepted |
| `default` | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | accepted |
| `fast` | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | accepted — undocumented by OpenAI, works everywhere |
| `priority` | :white_check_mark: | :white_check_mark: | :white_check_mark: | :white_check_mark: | accepted (account entitlement) |
| `flex` | :no_entry: `400` | :no_entry: `400` | :white_check_mark: | :no_entry: `400` | **gpt-5 generation only → `422`** |
| `scale` | :no_entry: `400` | :no_entry: `400` | :no_entry: `400` | :no_entry: `400` | **not an OpenAI tier — removed from the API** |

`flex` on a non-gpt-5 model is now a `422` at create/update. It is the exact config that produced
the silent calls this documentation exists for, and it is nastier than it looks: on `gpt-4.1` the
refusal says `Invalid service_tier argument`, but on `gpt-4.1-nano` it says only
`There was an issue with your request. Please check your inputs and try again` — no parameter
name. Same fault, two messages, one of them useless.

`scale` was in this platform's accepted values and can never have worked: OpenAI answers
`Invalid value: 'scale'. Supported values are: 'auto', 'default', 'fast', 'flex', and 'priority'`
for every model.

One thing still cannot be settled by any table, and is checked by asking OpenAI once when the
assistant is saved: which `reasoning_effort` **values** a model takes. OpenAI's own docs say only
that "some models support only a subset" of `none`, `minimal`, `low`, `medium`, `high`, `xhigh`,
`max` — and `chat-latest`, for example, accepts `medium` and nothing else.

The check is one short Responses request (16 output tokens, `store: false`) carrying the exact
model, knobs and tool schemas, cached per (key, model, knob combination). A refusal is returned
verbatim, so the `422` says what OpenAI said:

```json
{
  "detail": "OpenAI rejected this configuration for model 'gpt-5-mini': Unsupported value: 'reasoning.effort' does not support 'none' with this model. (param: reasoning.effort). Stored as-is it would fail on every LLM turn, so the call would connect and the assistant would never speak. See docs/reference/troubleshooting.md."
}
```

If OpenAI cannot be reached, or answers `401`/`429`/`5xx`, the write is **allowed**: none of
those say anything about the configuration.

!!! warning "`tool_choice: \"required\"` needs something to choose from"
    A forced tool choice with an empty tool list is a `400` from OpenAI on every turn. An
    assistant has tools when it has `tool_ids` or `assistant_end_call_enabled`, so this is
    checked at create, at update, **and** on `POST /tool/attach/...` and
    `POST /tool/detach/...` — detaching the last tool can break a stored config just as easily
    as attaching the first.

!!! warning "`gpt-5.2` and `gpt-5.4*` reject reasoning effort when tools are attached"
    Those models refuse `reasoning.effort` in any request carrying function tools — and an
    assistant has tools whenever it has `tool_ids` or `assistant_end_call_enabled`. Worse,
    the OpenAI plugin sets a default effort **by itself** on those models, so an assistant
    with an empty `assistant_llm_config` hit this too. `create_llm` now clears it before the
    call (`src/core/agents/llm/factory.py`) and logs one line when it does. Nothing to
    configure; a `reasoning_effort` you set explicitly is dropped with a warning instead.

!!! danger "The `*-chat-latest` aliases are retired"
    `gpt-5.1-chat-latest`, `gpt-5.2-chat-latest` and `gpt-5.3-chat-latest` were retired by
    OpenAI on **2026-06-19** and are off the allowlist, together with `chat-latest` (a LiveKit
    Inference gateway id needing Cloud credentials) and `gpt-oss-120b` (served by baseten and
    groq, not by `api.openai.com`). An assistant still holding one answers calls with silence.
    See [Models & Providers](models.md#documented-models) and
    [Troubleshooting](troubleshooting.md).

A model outside the allowlist (a row written before it existed, or by a direct Mongo edit)
has no known family, so its knobs are forwarded untouched rather than guessed at.

Assistants written *before* this gate existed can still hold a knob their model rejects. Calls
run — `create_llm` drops it and logs which one — but every PATCH to that assistant is refused
with a `400` until the knob is cleared, because the rules are re-checked against the merged row.
`uv run python scripts/migrate_llm_knobs.py` lists them (`--apply` to clear them).

#### Worked examples

Same intent, two families. Pick the knob the family reads:

```json title="Reasoning model — reasoning_effort, no temperature"
{
  "assistant_llm_config": {
    "model": "gpt-5-mini",
    "reasoning_effort": "low",
    "verbosity": "medium",
    "max_output_tokens": 500
  }
}
```

```json title="Chat model — temperature, no reasoning_effort"
{
  "assistant_llm_config": {
    "model": "gpt-4.1",
    "temperature": 0.3,
    "max_output_tokens": 500
  }
}
```

Send the wrong one and the assistant is never created:

```json title="422 — temperature on a reasoning model"
{
  "detail": [
    {
      "type": "value_error",
      "loc": ["body", "assistant_llm_config"],
      "msg": "Value error, assistant_llm_config.temperature is not supported by model 'gpt-5-mini' — reasoning models reject temperature — set reasoning_effort instead. See docs/reference/compatibility.md."
    }
  ]
}
```

The other two read the same way:

```text
assistant_llm_config.reasoning_effort is not supported by model 'gpt-4.1' — reasoning.effort is a reasoning-model parameter, and this is a chat model.
assistant_llm_config.verbosity is not supported by model 'gpt-4o' — text.verbosity is a gpt-5 generation parameter.
```

An assistant created **before** these rules can still hold a mismatched knob. Nothing breaks;
the knob is dropped at call time and the worker log says exactly what it dropped:

```text
WARNING  Dropping reasoning_effort='low' for cascade assistant asst_9f2: reasoning.effort is
         a reasoning-model parameter, and this is a chat model. Sending it to gpt-4.1 fails
         the LLM turn, so the call would connect and stay silent. Update the assistant to
         clear the stale value.
INFO     Cascade LLM built | assistant=asst_9f2 | model=gpt-4.1 | has_tools=False | knobs={'temperature': 0.4}
```

The `Cascade LLM built` line is logged for every cascade session — it is the ground truth for
what was sent (never the API key). On a tool-incompatible model it is preceded by:

```text
INFO  Cascade assistant asst_9f2: clearing the reasoning effort the OpenAI plugin injects for
      gpt-5.2 — that model rejects reasoning.effort while function tools are attached.
INFO  Cascade LLM built | assistant=asst_9f2 | model=gpt-5.2 | has_tools=True | knobs=defaults
```

---

## Mode × STT provider

`assistant_stt_model`. Unset means `sarvam`.

| Provider | `pipeline` | `realtime` | `cascade` |
|---|---|---|---|
| `sarvam` (default) | :white_check_mark: parallel Saras v3 audio tap alongside the realtime model | :warning: ignored — the realtime model transcribes | :white_check_mark: the session's own STT stage |
| `native` | :white_check_mark: the conversational LLM transcribes itself | :warning: ignored (this is effectively what realtime does anyway) | :no_entry: rejected — there is no realtime model to self-transcribe |
| `cartesia` | :recycle: degrades to `native` with a warning | :warning: ignored | :white_check_mark: |
| `deepgram` | :recycle: degrades to `native` with a warning | :warning: ignored | :white_check_mark: |
| `elevenlabs` | :recycle: degrades to `native` with a warning | :warning: ignored | :white_check_mark: |
| `openai` | :recycle: collapses to `native`, silently | :warning: ignored | :white_check_mark: |

**Why `openai` collapses silently.** In pipeline mode the realtime model already transcribes with
the same vendor and the same `gpt-4o-mini-transcribe`, so a separate OpenAI STT connection would add
cost and nothing else. No warning is logged because nothing is lost. (This also keeps pre-migration
rows working, where `assistant_stt_model="openai"` *meant* native transcription.)

**Why the degrade.** `cartesia`, `deepgram` and `elevenlabs` are plugin STTs with no parallel-tap
implementation for pipeline mode. Rather than start a call with no transcripts at all, `resolve_stt`
logs a warning and falls back to native transcription, so the caller still leaves with a transcript.
The selection is *stored* — switch the assistant to `cascade` and it takes effect with no further
edit. Same fallback applies in pipeline mode when a plugin provider is selected but no API key is
available.

**Cascade does not degrade.** In cascade mode a missing API key is fatal: `create_stt` returns `None`
and the job ends before the call connects. See [Failure modes](#failure-modes).

**`openai` STT: `use_realtime: false` needs `whisper-1`.** The batch REST path reports no usage at
all, and every OpenAI STT model except `whisper-1` is billed per token — the call would transcribe
normally and store zero STT spend. That pairing is a 422 at create/update. `whisper-1` is billed by
audio duration, which the batch path measures locally, so it is the one model allowed on it. A row
stored before this gate is forced back to streaming at call time with a warning; it never fails the
call.

**`sarvam` STT is metered by this runtime, not by the plugin, in both modes.** The plugin reports the
duration the Sarvam server sent, which is missing on some responses and absent entirely for a turn
that transcribed to nothing. Pipeline counts the frames its tap pushes; cascade counts them in
`stt_node` and suppresses the plugin's own metrics. See
[Usage accounting](usage-accounting.md#sarvam-stt-is-measured-not-reported).

### Language codes are NOT portable between providers

The same spoken language is written differently per provider, and the standards do not overlap.
A code from the wrong standard is rejected at build time — logged, dropped, and the provider's
default applies — so a mis-set code degrades the call instead of breaking it.

| Provider | Standard | English | Hindi | Auto-detect |
|---|---|---|---|---|
| `sarvam` | BCP-47 Indic | `en-IN` | `hi-IN` | `unknown` (the default) |
| `cartesia` | ISO 639-1 | `en` | `hi` | :no_entry: none — unset means `en` |
| `deepgram` | BCP-47 | `en-US` | `hi-IN` | `multi`, and the default on `nova-3` / `flux-general-multi` |
| `elevenlabs` | **ISO 639-3** | `eng` | `hin` | omit the code (the default) — ~190 languages |
| `openai` | ISO 639-1 | `en` | `hi` | `detect_language`, turned on automatically when no code is set |

ElevenLabs is the one that bites. It is the only ISO 639-3 surface here, and upstream it does not
degrade: Scribe answers a BCP-47 code with `1008 invalid_request` and closes the socket, so the
agent retries the same failure for the length of the call and transcribes nothing.

Deepgram's `multi` is billed at a higher per-minute rate than a pinned language, so leaving the
field unset on `nova-3` costs more than setting it.

---

## Mode × TTS provider

`assistant_tts_model` + `assistant_tts_config`.

| Provider | `pipeline` | `realtime` | `cascade` |
|---|---|---|---|
| `cartesia` | :white_check_mark: | :warning: stored, never used | :white_check_mark: |
| `sarvam` | :white_check_mark: | :warning: stored, never used | :white_check_mark: |
| `elevenlabs` | :white_check_mark: | :warning: stored, never used | :white_check_mark: |
| `mistral` | :white_check_mark: | :warning: stored, never used | :white_check_mark: |
| omitted | :no_entry: `422` — both `assistant_tts_model` and `assistant_tts_config` are required | :white_check_mark: the model speaks its own audio | :no_entry: `422` — same requirement |

In `realtime` mode the model produces audio itself, so no TTS is built at all. Sending a TTS block
there is accepted (it is kept for the day you switch modes) but changes nothing about the call.

---

## Config keys ignored per mode

Accepted by validation, stored on the assistant, and read by nobody in that mode. None of these are
errors — they are the fields to stop debugging when a setting appears to have no effect.

| Field | Ignored in | Read in | Why |
|---|---|---|---|
| `assistant_llm_config.voice` | `pipeline`, `cascade` | `realtime` | Only the realtime model speaks its own audio; elsewhere the voice comes from the TTS provider. |
| `assistant_llm_config.temperature`, `max_output_tokens`, `reasoning_effort`, `service_tier`, `verbosity`, `tool_choice`, `parallel_tool_calls` | `pipeline`, `realtime` | `cascade` | These are `openai.responses.LLM` parameters, built only by `create_llm` in cascade mode. |
| `assistant_tts_model`, `assistant_tts_config` | `realtime` | `pipeline`, `cascade` | No TTS stage exists in realtime mode. |
| `assistant_stt_model`, `assistant_stt_config` | `realtime` | `pipeline`, `cascade` | The realtime model transcribes; there is no separate STT stage. |
| `assistant_stt_config.language` (Cartesia/Deepgram) | `pipeline` | `cascade` | The provider itself is cascade-only, so its whole config block is inert in pipeline mode. |
| `assistant_interaction_config.preferred_languages` | `cascade` | `pipeline`, `realtime` | It hints the *native* transcription prompt, and cascade has no native path. It is never sent to a speech provider as a language parameter in any mode — pin a language on `assistant_stt_config` instead. |

`assistant_stt_config.mode` (Sarvam) is **not** on this list: it is honoured in both pipeline and
cascade, and defaults to `codemix` in both.

---

## Failure modes

What a wrong combination actually looks like, in order of how early you find out.

| Symptom | Cause | Where |
|---|---|---|
| `422 Unprocessable Entity` at create, or at update when the request names `assistant_mode` | The rule table in `validate_mode_config` — bad provider, bad model for the mode, `native` STT in cascade, missing TTS pair, or a generation knob the cascade model cannot read | `src/api/models/api_schemas/config/llm_config.py` |
| `400 Bad Request` at update | The request is well-formed, but merged with what is already stored it produces an unrunnable assistant — e.g. `{"assistant_mode": "cascade"}` on a row holding `provider: "gemini"` or a non-allowlisted model | `enforce_stored_mode_constraints` in `src/api/routes/assistant.py` |
| Call connects, transcripts appear, but a knob you set does nothing | The field is ignored in this mode | [Config keys ignored per mode](#config-keys-ignored-per-mode) |
| Call connects, transcripts appear, but from a different engine than you chose | Cascade-only STT in pipeline mode, or a plugin STT with no API key — both degrade to `native` and log a warning | `resolve_stt`, `src/core/agents/stt/factory.py` |
| Call never starts. No error to the caller, one `ERROR` line in the worker log | A factory returned `None` and `entrypoint()` returned early: missing STT key in cascade, missing TTS key, unsupported TTS model, unsupported cascade LLM provider | `create_stt` / `create_tts` / `create_llm` |
| Call runs but produces no user transcripts | `pipeline` + Sarvam tap whose key fails to authenticate — the tap disables the model's own transcription, so nothing writes transcripts. (`realtime` + `gemini` is **not** on this list any more: the Google plugin turns on `input_audio_transcription` by default, so leaving it unset is what enables it.) | `resolve_stt`, `src/core/agents/stt/factory.py` |
| Cascade call connects, then total silence. Worker log repeats `Error in _llm_inference_task ... APIStatusError: 'There was an issue with your request'` on every turn | OpenAI rejected the request shape. A knob the model cannot read (see [Cascade LLM knobs](#cascade-llm-knobs)) or a tool schema it refuses. The WebSocket error frame carries no detail, so read the `Cascade LLM built \| ... \| knobs=` line logged at session start to see exactly what was sent | `src/core/agents/llm/factory.py`, `src/core/agents/tool_builder.py` |
| Worker log: `Unknown assistant_mode '<x>' — treating as 'pipeline'` | `assistant_mode` was written outside the API (migration, direct Mongo edit). The DB field is a plain string with no enum. | `src/core/agents/session.py` |

Everything above the last two rows is caught at the API. The remaining two are a provider
limitation and a hand-edited database row, not configuration errors.

---

## API keys

Per-assistant `api_key` fields always win; the environment variable is the fallback.

| Stage | Provider | `api_key` field | Environment fallback |
|---|---|---|---|
| LLM | openai | `assistant_llm_config.api_key` | `OPENAI_API_KEY` |
| LLM | gemini (realtime only) | `assistant_llm_config.api_key` | `GOOGLE_API_KEY` |
| STT | sarvam | `assistant_stt_config.api_key` | `SARVAM_API_KEY` |
| STT | cartesia | `assistant_stt_config.api_key` | `CARTESIA_API_KEY` |
| STT | deepgram | `assistant_stt_config.api_key` | `DEEPGRAM_API_KEY` |
| STT | elevenlabs | `assistant_stt_config.api_key` | `ELEVENLABS_API_KEY` |
| STT | openai (cascade) | `assistant_stt_config.api_key` | `OPENAI_API_KEY` |
| TTS | cartesia | `assistant_tts_config.api_key` | `CARTESIA_API_KEY` |
| TTS | sarvam | `assistant_tts_config.api_key` | `SARVAM_API_KEY` |
| TTS | elevenlabs | `assistant_tts_config.api_key` | `ELEVENLABS_API_KEY` |
| TTS | mistral | `assistant_tts_config.api_key` | `MISTRAL_API_KEY` |

!!! note "One key per vendor, two config fields"
    `ELEVENLABS_API_KEY` covers **both** ElevenLabs stages, STT and TTS — one variable, set it once.
    `SARVAM_API_KEY` and `CARTESIA_API_KEY` work the same way.

    The per-assistant fields are still separate, though: `assistant_stt_config.api_key` and
    `assistant_tts_config.api_key` are scoped to the provider selected for *that stage*. On an
    assistant with Sarvam STT and Cartesia TTS they hold two different vendors' keys, and crossing
    them fails auth — Sarvam answers `403` to a Cartesia key. Override a stage only when that stage's
    provider needs a different key from the system one.

Missing keys are now detected before the plugin is constructed, in both the STT and TTS factories, so
they always produce the "call never starts, one log line" failure above rather than an unhandled
exception.

---

## Unknown keys

Every provider config block is strict: an unrecognised key is a `422`, not a silent drop. This covers
`assistant_llm_config`, all four `assistant_tts_config` shapes (including `voice_settings`) and all
five `assistant_stt_config` shapes. A typo like `enable_diarisation` fails at create time instead of
quietly disabling the feature you thought you turned on.

The one thing that is *not* strict is the discriminator: `assistant_stt_config` may be omitted
entirely when `assistant_stt_model` is set, and the API fills in a defaults-only config for you.

---

## See also

- [Models & Providers](models.md) — every provider, model ID and config default.
- [Runtime Modes](../architecture/runtime-modes.md) — what each mode is and how to pick one.
- [Cascade Pipeline](../architecture/cascade-pipeline.md) — the three-stage mode in depth.
- [Create Assistant](../api/assistant/create.md) — request shape and per-mode examples.
