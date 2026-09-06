# Create Assistant

Create a new assistant configuration.

For the full model/provider inventory (model IDs, defaults, per-mode validity) see
[Models & Providers](../../reference/models.md).

- **URL**: `/assistant/create`
- **Method**: `POST`
- **Headers**: `Authorization: Bearer <your_api_key>`
- **Content-Type**: `application/json`

## Request Body (Common Fields)

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `assistant_name` | string | Yes | Assistant name (1-100 chars). |
| `assistant_description` | string | Yes | Assistant description. |
| `assistant_prompt` | string | Yes | System prompt. |
| `assistant_mode` | string | No | Runtime mode: `pipeline`, `realtime` or `cascade`. Default: `pipeline`. |
| `assistant_start_instruction` | string | No | Opening response text. Used when `assistant_interaction_config.speaks_first=true` (max 500 chars). |
| `assistant_interaction_config` | object | No | Interaction settings (see below). |
| `assistant_greeting_audio` | object | No | Prerecorded greeting reference: `{ "enabled": bool, "audio_id": string }`. `audio_id` must reference one of your active [audio assets](../../api/audio/index.md). When `enabled` and `speaks_first=true`, the clip plays instead of a model-generated greeting. |
| `assistant_end_call_enabled` | boolean | No | Enables built-in end-call tool. Default: `false`. |
| `assistant_end_call_trigger_phrase` | string | Conditional | Required if `assistant_end_call_enabled=true`. |
| `assistant_end_call_agent_message` | string | Conditional | Required if `assistant_end_call_enabled=true`. |
| `assistant_end_call_url` | string | No | Webhook URL for call-ended payload. |
| `assistant_end_call_webhook` | object | No | Delivery tuning for that webhook: `timeout_seconds` (1–120) and `attempts` (1–5). Each falls back to the server default when omitted or `null` (`END_CALL_WEBHOOK_TIMEOUT`, 30s; `END_CALL_WEBHOOK_ATTEMPTS`, 3). Raise the timeout when your endpoint stores the payload before replying. See [End-Call Webhook](../calls/webhook.md). |

---

## Mode Configuration

=== ":material-pipe: Pipeline"

    **Pipeline mode** (half-cascade): the LLM emits text and a separate TTS provider speaks it.
    The LLM vendor is `openai` only — `assistant_llm_config.provider: "gemini"` returns `422` here, because Google's Live API cannot run the text-only modality half-cascade needs on its native-audio models. Use `assistant_mode: "realtime"` for Gemini. See the [Compatibility Matrix](../../reference/compatibility.md#mode-llm-provider).
    If `assistant_interaction_config.speaks_first=true`, the opening response is spoken at session start.
    `assistant_llm_config` is optional in this mode (defaults to `provider="openai"`, `model="gpt-realtime-1.5"`). Send it to override the model — it must be an OpenAI **realtime** model ID — or to set an `api_key`; `voice` is ignored (TTS handles audio).

    **Required fields**

    | Field | Type | Required | Description |
    | :--- | :--- | :--- | :--- |
    | `assistant_tts_model` | string | Yes | One of `cartesia`, `sarvam`, `elevenlabs`, `mistral`. |
    | `assistant_tts_config` | object | Yes | TTS config for the selected provider (see tabs below). |

    **Optional pipeline LLM config** (`assistant_llm_config`)

    | Field | Type | Required | Description |
    | :--- | :--- | :--- | :--- |
    | `api_key` | string | No | Optional per-assistant OpenAI key. Overrides system `OPENAI_API_KEY`. |

    **STT configuration** (optional — defaults to Sarvam with the system key)

    | Field | Type | Required | Description |
    | :--- | :--- | :--- | :--- |
    | `assistant_stt_model` | string | No | User-transcription source: `sarvam` (default when unset) or `native`. `cartesia`, `deepgram`, `elevenlabs` and `openai` are cascade-only (`openai` collapses to `native` here). |
    | `assistant_stt_config` | object | No | Config for the selected STT provider (see tabs below). Requires `assistant_stt_model`. Omit for provider defaults. |

    === "Sarvam"

        Runs Sarvam Saras v3 as a parallel audio tap — native-script Indic transcripts, avoids the script-switching hallucinations of a generic model on code-switched speech. The LLM still consumes the audio directly for understanding.

        | Field | Type | Required | Description |
        | :--- | :--- | :--- | :--- |
        | `model` | string | No | Sarvam STT model: `saaras:v3` (default) or `saaras:v4`. |
        | `language` | string | No | BCP-47 code, or `unknown` to auto-detect. Default: `unknown`. |
        | `mode` | string | No | Transcription mode. Default: `codemix` (keeps code-switching intact). |
        | `api_key` | string | No | Optional Sarvam API key. Falls back to system `SARVAM_API_KEY`. **Distinct from `assistant_tts_config.api_key`**, which belongs to whichever TTS provider you selected — Sarvam STT rejects a Cartesia/ElevenLabs/Mistral key with `403`. Masked in `GET /assistant/details` and `GET /assistant/list`. |

        Allowed `model` and `mode` values: [Models & Providers](../../reference/models.md#stt).

    === "Native"

        The conversational LLM transcribes itself (OpenAI `gpt-4o-mini-transcribe`, or Gemini's own on a Gemini pipeline). No configuration fields — send `{}` or omit `assistant_stt_config`.

        Not valid in `cascade` mode — there is no realtime model to transcribe itself.

    Ignored in `realtime` (audio-out) mode, where the model always transcribes.

    **TTS provider configuration**

    === "Cartesia"

        | Field | Type | Required | Description |
        | :--- | :--- | :--- | :--- |
        | `voice_id` | string | Yes | Cartesia voice ID. |
        | `language` | string | No | BCP-47 code for the input text. Default: `en`. Affects pronunciation only. |
        | `speed` | number | No | Speaking speed as a numeric multiplier of normal (e.g. `1.5` = 50% faster), range `0`–`3`. Default: `1.0`. Preset strings (`slow`/`normal`/`fast`) are **not** accepted: they belong to Cartesia's older models, and `sonic-3` requires a float. |
        | `volume` | number | No | Output volume where `1.0` is the default. Range `0`–`3`. |
        | `emotion` | string | No | Emotion control string (Sonic 3 only), e.g. `excited`, `calm`, `sad`. See [Cartesia docs](https://docs.cartesia.ai/build-with-cartesia/sonic-3/volume-speed-emotion) for supported values. |
        | `pronunciation_dict_id` | string | No | ID of a Cartesia pronunciation dictionary to apply (Sonic 3 models only). |
        | `api_key` | string | No | Optional Cartesia API key. Falls back to system `CARTESIA_API_KEY`. |

    === "Sarvam"

        | Field | Type | Required | Description |
        | :--- | :--- | :--- | :--- |
        | `speaker` | string | Yes | Sarvam speaker identifier, from the **bulbul:v3** roster: `aayan`, `aditya`, `advait`, `amelia`, `amit`, `ashutosh`, `dev`, `ishita`, `kabir`, `kavitha`, `kavya`, `manan`, `neha`, `pooja`, `priya`, `rahul`, `ratan`, `ritu`, `rohan`, `roopa`, `rupali`, `shreya`, `shruti`, `shubh`, `simran`, `sophia`, `suhani`, `sumit`, `tanya`, `varun`. The older bulbul:v2 names (`anushka`, `manisha`, `vidya`, `arya`, `abhilash`, `karun`, `hitesh`) are rejected with a `422`: v2 and v3 share no speaker names, and the Sarvam plugin raises on a speaker its model cannot use, which used to end the call at start. |
        | `target_language_code` | string | No | BCP-47 code, and only one of the 11 Bulbul speaks: `bn-IN`, `en-IN`, `gu-IN`, `hi-IN`, `kn-IN`, `ml-IN`, `mr-IN`, `od-IN`, `pa-IN`, `ta-IN`, `te-IN`. Note `en-IN`, **not** `en-US` — anything outside the list is rejected and falls back to `en-IN`. Default: `en-IN`. |
        | `pace` | number | No | Speaking pace multiplier, `0.3`–`3.0`. Default: `1.0` (`>1.0` faster, `<1.0` slower). |
        | `speech_sample_rate` | number | No | Output sample rate in Hz. One of `8000`, `16000`, `22050`, `24000`, `32000`, `44100`, `48000` — other values are rejected. Default: `24000`; use `8000` only for narrowband telephony. |
        | `temperature` | number | No | TTS sampling temperature, `0.01`–`2.0`. Default: `0.3`. Lower = more stable. |
        | `api_key` | string | No | Optional Sarvam API key. Falls back to system `SARVAM_API_KEY`. |

    === "ElevenLabs"

        | Field | Type | Required | Description |
        | :--- | :--- | :--- | :--- |
        | `voice_id` | string | Yes | ElevenLabs voice ID. |
        | `model` | string | No | TTS model. Default: `eleven_v3`. Also `eleven_v3_conversational`, `eleven_multilingual_v2`, `eleven_turbo_v2_5`, `eleven_flash_v2_5`. |
        | `voice_settings` | object | No | Voice tuning: `{ "stability": 0–1, "similarity_boost": 0–1, "style": 0–1, "speed": 0.25–4.0, "use_speaker_boost": bool }`. **`speed` has no effect on `eleven_v3` or `eleven_v3_conversational`** (the first is the default model) — it is dropped before the call and logged; pick `eleven_multilingual_v2`, `eleven_turbo_v2_5` or `eleven_flash_v2_5` if you need to change the speaking rate. On the v3 models, `stability` reads as three modes: `0.0` creative, `0.5` natural, `1.0` robust. |
        | `api_key` | string | No | Optional ElevenLabs API key. Falls back to system `ELEVENLABS_API_KEY`. |

    === "Mistral"

        | Field | Type | Required | Description |
        | :--- | :--- | :--- | :--- |
        | `voice_id` | string | Yes | Mistral voice ID. |
        | `api_key` | string | No | Optional Mistral API key. Falls back to system `MISTRAL_API_KEY`. |

    **Example request**

    ```bash
    curl -X POST "https://api-livekit-vyom.indusnettechnologies.com/assistant/create" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer <your_api_key>" \
      -d '{
        "assistant_name": "Support Bot",
        "assistant_description": "First line support",
        "assistant_prompt": "You are a helpful customer support agent.",
        "assistant_mode": "pipeline",
        "assistant_llm_config": {
          "api_key": "sk-..."
        },
        "assistant_tts_model": "cartesia",
        "assistant_tts_config": {
          "voice_id": "a167e0f3-df7e-4277-976b-be2f952fa275"
        },
        "assistant_interaction_config": {
          "speaks_first": true,
          "filler_words": true,
          "silence_reprompts": true,
          "silence_reprompt_interval": 10.0,
          "silence_max_reprompts": 2,
          "background_sound_enabled": true,
          "thinking_sound_enabled": true,
          "preferred_languages": ["en-US", "hi-IN"],
          "max_call_duration_minutes": 30
        }
      }'
    ```

=== ":material-lightning-bolt: Realtime"

    **Realtime mode** uses a single model (e.g. Gemini Live API) that handles STT, LLM, and TTS in one stream.
    If `assistant_interaction_config.speaks_first=true`, the opening response is sent at session start through the realtime conversation path.
    `assistant_llm_config` is required in this mode, but its Gemini fields still have defaults.

    !!! note "Filler words are not available in realtime mode"
        Since there is no external TTS, `filler_words` is automatically disabled even if set to `true`.

    **Required fields**

    | Field | Type | Required | Description |
    | :--- | :--- | :--- | :--- |
    | `assistant_llm_config` | object | Yes | Realtime provider configuration (see table below). |

    **Realtime LLM config** (`assistant_llm_config`)

    | Field | Type | Required | Description |
    | :--- | :--- | :--- | :--- |
    | `provider` | string | No | LLM vendor for audio-out realtime. `gemini` (default) or `openai`. |
    | `model` | string | No | Provider model, **validated**. Gemini: one of `gemini-2.5-flash-native-audio-preview-12-2025` (default), `gemini-live-2.5-flash-native-audio`, `gemini-3.1-flash-live-preview` — a Gemini *chat* id such as `gemini-2.5-flash` is a `422`. OpenAI: a realtime id, default `gpt-realtime-1.5`. |
    | `voice` | string | No | Voice for the audio-out model. Gemini default: `Puck`; OpenAI default: `marin`. |
    | `api_key` | string | No | Optional per-assistant provider key. Falls back to system `GOOGLE_API_KEY` / `OPENAI_API_KEY`. |

    !!! tip "Sarvam parallel STT (pipeline mode)"
        In `pipeline` mode (either provider), user transcripts default to Sarvam Saras v3 (see `assistant_stt_model` in the Pipeline tab) — native-script Indic transcripts for code-switched calls. The LLM still consumes the audio directly for understanding. Realtime (audio-out) mode transcribes via the model itself.

    **Minimal realtime example**

    ```json
    {
      "assistant_mode": "realtime",
      "assistant_llm_config": {}
    }
    ```

    **Example request**

    ```bash
    curl -X POST "https://api-livekit-vyom.indusnettechnologies.com/assistant/create" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer <your_api_key>" \
      -d '{
        "assistant_name": "Gemini Assistant",
        "assistant_description": "Realtime voice assistant",
        "assistant_prompt": "You are a helpful assistant.",
        "assistant_mode": "realtime",
        "assistant_llm_config": {
          "provider": "gemini",
          "model": "gemini-2.5-flash-native-audio-preview-12-2025",
          "voice": "Puck"
        }
      }'
    ```

=== "Cascade Mode"

    A true three-stage pipeline: plugin STT → plain OpenAI chat model → plugin TTS. Each stage is
    separately metered, so this is the only mode that reports STT cost on its own. Full detail in
    [Cascade Pipeline](../../architecture/cascade-pipeline.md).

    **Required fields**

    | Field | Type | Required | Description |
    | :--- | :--- | :--- | :--- |
    | `assistant_tts_model` | string | Yes | One of `cartesia`, `sarvam`, `elevenlabs`, `mistral`. |
    | `assistant_tts_config` | object | Yes | TTS config for the selected provider (same tabs as the Pipeline tab). |

    **STT stage** (optional — defaults to Sarvam with the system key)

    | Field | Type | Required | Description |
    | :--- | :--- | :--- | :--- |
    | `assistant_stt_model` | string | No | `sarvam` (default when unset), `cartesia`, `deepgram`, `elevenlabs` or `openai`. **`native` is rejected** — there is no realtime model to transcribe itself. |
    | `assistant_stt_config` | object | No | Config for the selected STT provider — `sarvam`, `cartesia`, `deepgram`, `elevenlabs` or `openai` (see tabs below). Requires `assistant_stt_model`. Omit for provider defaults. |

    === "Sarvam (multilingual)"

        | Field | Type | Required | Description |
        | :--- | :--- | :--- | :--- |
        | `model` | string | No | Sarvam STT model: `saaras:v3` (default) or `saaras:v4`. |
        | `language` | string | No | `unknown` (default) auto-detects; or a fixed BCP-47 code. |
        | `mode` | string | No | Transcription mode. Default: `codemix`. |
        | `api_key` | string | No | Falls back to system `SARVAM_API_KEY`. |

        The default `saaras:v3` + `unknown` + `codemix` combination is the multilingual one: it
        auto-detects the language and keeps code-switching intact inside a single utterance.

    === "Cartesia (single language)"

        | Field | Type | Required | Description |
        | :--- | :--- | :--- | :--- |
        | `model` | string | No | Cartesia STT model. Default: `ink-whisper` (multilingual). |
        | `language` | string | No | Fixed BCP-47 code. Default: `en`. **No auto-detect** — use Sarvam if the caller may switch languages. |
        | `api_key` | string | No | Falls back to system `CARTESIA_API_KEY`. |

        Allowed `model`, `language` and `mode` values for the Sarvam and Cartesia tabs: [Models & Providers](../../reference/models.md#stt).

    === "Deepgram (multilingual)"

        | Field | Type | Required | Description |
        | :--- | :--- | :--- | :--- |
        | `model` | string | No | Deepgram STT model. Default: `nova-3` (multilingual, 45 languages). Also `nova-2`, `flux-general-en` (English only) and `flux-general-multi` (multilingual). |
        | `language` | string | No | BCP-47 code (`en-US`, `hi-IN`), or `multi` to auto-detect per segment. A 3-letter code such as `hin` is an ElevenLabs code and is rejected. When omitted: `multi` on `nova-3` / `flux-general-multi`, `en-US` on `nova-2` / `flux-general-en`, which cannot detect. `multi` bills at a higher per-minute rate. On the flux models this is sent as `language_hint` and only `flux-general-multi` reads it. |
        | `enable_diarization` | boolean | No | Labels each utterance with a speaker id. Default: `false`. When omitted, diarization stays off — it is never force-enabled. Nova models only. |
        | `keyterm` | string or array of strings | No | Boosts recognition of a term. When omitted it is not sent (no biasing). `nova-3` / `flux` only — `nova-2` does not take keyterm. |
        | `api_key` | string | No | Optional Deepgram API key. Falls back to system `DEEPGRAM_API_KEY`. |

    === "ElevenLabs (auto-detect)"

        | Field | Type | Required | Description |
        | :--- | :--- | :--- | :--- |
        | `model` | string | No | ElevenLabs STT model. Default: `scribe_v2_realtime` (auto-detects ~190 languages). Also `scribe_v2` and `scribe_v1`. |
        | `language_code` | string | No | **ISO 639-3** code (`eng`, `hin`, `ben`) — not BCP-47 and not ISO 639-1. Scribe rejects anything else with `1008 invalid_request` and closes the connection, so an unrecognized code is dropped here (logged) and the call auto-detects. Omit to auto-detect ~190 languages; setting a valid code pins it and disables auto-detection. |
        | `no_verbatim` | boolean | No | Strips filler words (`um`, `uh`) and false starts from the transcript. Default: `false`. |
        | `api_key` | string | No | Optional ElevenLabs key for the STT stage. Falls back to system `ELEVENLABS_API_KEY`, the same variable the ElevenLabs TTS provider uses. |

    === "OpenAI (same vendor as the LLM)"

        | Field | Type | Required | Description |
        | :--- | :--- | :--- | :--- |
        | `model` | string | No | OpenAI STT model. Default: `gpt-4o-mini-transcribe` (fast, cheap). Also `gpt-4o-transcribe` (more accurate) and `whisper-1` (legacy batch model — the only one that reads `prompt`). `gpt-realtime-whisper` is **rejected**: it has no server-side endpointing and needs a client-side VAD this runtime cannot supply. |
        | `language` | string | No | ISO 639-1 code (`en`, `hi`) — not BCP-47; `hi-IN` is rejected. Omitting it turns `detect_language` on rather than pinning English. Ignored when `detect_language` is `true`. |
        | `detect_language` | boolean | No | Auto-detect the spoken language instead of pinning one. Default: `false`. Overrides `language`. |
        | `prompt` | string | No | Biases spellings and jargon (names, product terms). **`whisper-1` only** — the gpt-4o transcribe models accept and ignore it. |
        | `noise_reduction_type` | string | No | Server-side noise reduction: `near_field` (headset) or `far_field` (speakerphone / room mic). Omitted applies none. |
        | `use_realtime` | boolean | No | Streams over OpenAI's realtime transcription WebSocket (interim results, low latency). Default: `true`. Set `false` for the batch REST API — cheaper, but adds a full utterance of latency per turn, and accepted **only with `model: "whisper-1"`**: the batch path reports no token usage, so a token-billed model on it would record zero STT spend for the call. |
        | `api_key` | string | No | Optional OpenAI key for the STT stage. Falls back to system `OPENAI_API_KEY`, the same variable the cascade LLM stage uses. |

    > **Don't assume all STT providers auto-detect when `language`/`language_code` is omitted.**
    > ElevenLabs auto-detects, but Deepgram and OpenAI fall back to `en` (not `multi`), and
    > `flux-general-en` is
    > English-only. `keyterm` is ignored on `nova-2`, `enable_diarization` is nova-only, OpenAI's
    > `prompt` works on `whisper-1` only, and a pinned
    > ElevenLabs `language_code` disables auto-detect. Full list:
    > [STT pitfalls & what not to combine](../../reference/models.md#stt-pitfalls-what-not-to-combine).

    **LLM stage** (`assistant_llm_config`)

    | Field | Type | Required | Description |
    | :--- | :--- | :--- | :--- |
    | `provider` | string | No | Must be `openai` (the default when unset). Any other value is rejected. |
    | `model` | string | No | One of the documented OpenAI models. Default: `gpt-4.1`. Full list and knobs: [Models & Providers](../../reference/models.md#cascade-llm-cascade-mode-only). |
    | `api_key` | string | No | Falls back to system `OPENAI_API_KEY`. |
    | `temperature` | number | No | Sampling temperature `0`–`2`. Higher = more random. **Chat models only** — sending it with a reasoning model (`gpt-5`, `gpt-5.x`) is a `422`. |
    | `max_output_tokens` | integer | No | Cap on the number of output tokens in the response. |
    | `reasoning_effort` | string | No | Reasoning depth: `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`. **Reasoning models only** — a `422` on `gpt-4.1`/`gpt-4o`. Which *values* a given reasoning model accepts is checked against OpenAI, not guessed: a value it refuses is also a `422`, quoting OpenAI's message. |
    | `service_tier` | string | No | OpenAI processing/billing tier: `auto`, `default`, `fast`, `flex`, `priority`. `auto`, `default`, `fast` and `priority` work on every model. **`flex` is gpt-5 generation only** — on `gpt-4.1`/`gpt-4.1-nano` it is a `422` here, because OpenAI refuses it with a `400` on every turn and on nano does not even name the parameter, which is how an assistant ends up answering calls in silence. `scale` is not an OpenAI tier and is no longer accepted. Leave unset unless you have a reason. Full measured table: [Compatibility Matrix](../../reference/compatibility.md#service_tier-measured). |
    | `verbosity` | string | No | Constrains response length: `low`, `medium`, `high`. **gpt-5 generation only**; a `422` on `gpt-4.1`/`gpt-4o`. |
    | `tool_choice` | string | No | Tool usage: `auto`, `required`, `none`. `required` needs at least one tool — with no `tool_ids` and `assistant_end_call_enabled: false` it is a `422`, because OpenAI rejects a forced tool choice with an empty tool list on every turn. |
    | `parallel_tool_calls` | boolean | No | Allow multiple tool calls in one response. |

    `voice` is ignored — the TTS provider owns the voice in this mode. Any unknown key in
    `assistant_llm_config` is rejected with `422`.

    !!! warning "The three model-gated knobs are checked against the model"
        `temperature`, `reasoning_effort` and `verbosity` are rejected with a `422` when the
        chosen `model` cannot read them (with no `model`, they are checked against the default
        `gpt-4.1`). This is deliberately strict: OpenAI answers such a request with a `400` on
        **every** LLM turn, which shows up as a call that connects and then stays completely
        silent. Full matrix:
        [Cascade LLM knobs](../../reference/compatibility.md#cascade-llm-knobs).

        ```json title="Rejected — temperature belongs to chat models"
        { "assistant_llm_config": { "model": "gpt-5-mini", "temperature": 0.3 } }
        ```

        ```json title="422 response"
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

        ```json title="Accepted — the same intent, expressed the way this model reads it"
        { "assistant_llm_config": { "model": "gpt-5-mini", "reasoning_effort": "low" } }
        ```

    !!! warning "The model is checked against OpenAI, not only against our list"
        Passing the allowlist is not enough. Create and update also ask OpenAI whether the
        account still serves the model, because a list cannot know about a retirement — three
        `*-chat-latest` aliases were retired on 2026-06-19 and every assistant holding one kept
        validating clean and then answered calls with silence.

        ```json title="422 — the account cannot serve this model"
        {
          "detail": "assistant_llm_config.model 'gpt-5.2-chat-latest' cannot be used — the OpenAI account for this key does not serve it. Either the model has been retired by OpenAI or this account has no access to it. Pick a model the account serves — `uv run python scripts/check_model_allowlist.py` lists them. Storing it would produce a call that connects and then stays silent, because OpenAI rejects every turn."
        }
        ```

        In cascade mode one further check runs: a single short Responses request carrying this
        exact model, these knobs and this assistant's tool schemas. If OpenAI refuses it, its
        own message comes back as the `422` — see
        [Cascade LLM knobs](../../reference/compatibility.md#cascade-llm-knobs). If OpenAI
        cannot be reached, both checks are skipped and the write proceeds.

    **Example request** (with the new LLM generation knobs and TTS speed settings; all are optional)

    ```bash
    curl -X POST "https://api-livekit-vyom.indusnettechnologies.com/assistant/create" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer <your_api_key>" \
      -d '{
        "assistant_name": "Cascade Assistant",
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
          "model": "gpt-5-mini",
          "reasoning_effort": "low",
          "max_output_tokens": 500,
          "verbosity": "medium",
          "service_tier": "default",
          "tool_choice": "auto",
          "parallel_tool_calls": true
        },
        "assistant_tts_model": "cartesia",
        "assistant_tts_config": {
          "voice_id": "a167e0f3-df7e-4277-976b-be2f952fa275",
          "speed": 1.1,
          "volume": 1.0,
          "emotion": "calm",
          "language": "en"
        }
      }'
    ```

    > **Note on the example above:** `gpt-5-mini` is a *reasoning* model, which rejects
    > `temperature` — so the example sends `reasoning_effort` instead. For a **chat** model
    > (like the default `gpt-4.1`), do the opposite: send `temperature` and drop
    > `reasoning_effort`; sending the wrong one for the family is a `422`. Both are optional —
    > omit whichever your model family does not use.

    **Example request — Deepgram STT**

    ```bash
    curl -X POST "https://api-livekit-vyom.indusnettechnologies.com/assistant/create" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer <your_api_key>" \
      -d '{
        "assistant_name": "Cascade Assistant",
        "assistant_description": "True STT -> LLM -> TTS pipeline",
        "assistant_prompt": "You are a helpful assistant.",
        "assistant_mode": "cascade",
        "assistant_stt_model": "deepgram",
        "assistant_stt_config": {
          "model": "nova-3",
          "language": "multi",
          "enable_diarization": true,
          "keyterm": "invoice",
          "api_key": "dg-..."
        },
        "assistant_llm_config": {
          "provider": "openai",
          "model": "gpt-5-mini",
          "max_output_tokens": 500,
          "reasoning_effort": "low",
          "verbosity": "medium",
          "service_tier": "default",
          "tool_choice": "auto",
          "parallel_tool_calls": true
        },
        "assistant_tts_model": "cartesia",
        "assistant_tts_config": {
          "voice_id": "a167e0f3-df7e-4277-976b-be2f952fa275",
          "speed": 1.1,
          "volume": 1.0,
          "emotion": "calm",
          "language": "en"
        }
      }'
    ```

    **Example request — ElevenLabs STT**

    ```bash
    curl -X POST "https://api-livekit-vyom.indusnettechnologies.com/assistant/create" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer <your_api_key>" \
      -d '{
        "assistant_name": "Cascade Assistant",
        "assistant_description": "True STT -> LLM -> TTS pipeline",
        "assistant_prompt": "You are a helpful assistant.",
        "assistant_mode": "cascade",
        "assistant_stt_model": "elevenlabs",
        "assistant_stt_config": {
          "model": "scribe_v2_realtime",
          "no_verbatim": true,
          "api_key": "el-stt-..."
        },
        "assistant_llm_config": {
          "provider": "openai",
          "model": "gpt-5-mini",
          "max_output_tokens": 500,
          "reasoning_effort": "low",
          "verbosity": "medium",
          "service_tier": "default",
          "tool_choice": "auto",
          "parallel_tool_calls": true
        },
        "assistant_tts_model": "cartesia",
        "assistant_tts_config": {
          "voice_id": "a167e0f3-df7e-4277-976b-be2f952fa275",
          "speed": 1.1,
          "volume": 1.0,
          "emotion": "calm",
          "language": "en"
        }
      }'
    ```

    **Example request — OpenAI STT** (one vendor and one key for both the STT and LLM stages)

    ```bash
    curl -X POST "https://api-livekit-vyom.indusnettechnologies.com/assistant/create" \
      -H "Content-Type: application/json" \
      -H "Authorization: Bearer <your_api_key>" \
      -d '{
        "assistant_name": "Cascade Assistant",
        "assistant_description": "True STT -> LLM -> TTS pipeline",
        "assistant_prompt": "You are a helpful assistant.",
        "assistant_mode": "cascade",
        "assistant_stt_model": "openai",
        "assistant_stt_config": {
          "model": "gpt-4o-mini-transcribe",
          "language": "en",
          "noise_reduction_type": "far_field",
          "use_realtime": true
        },
        "assistant_llm_config": {
          "provider": "openai",
          "model": "gpt-5-mini",
          "max_output_tokens": 500,
          "reasoning_effort": "low",
          "verbosity": "medium",
          "service_tier": "default",
          "tool_choice": "auto",
          "parallel_tool_calls": true
        },
        "assistant_tts_model": "cartesia",
        "assistant_tts_config": {
          "voice_id": "a167e0f3-df7e-4277-976b-be2f952fa275",
          "speed": 1.1,
          "volume": 1.0,
          "emotion": "calm",
          "language": "en"
        }
      }'
    ```

---

## Interaction Configuration

!!! warning "`user_stt_provider` and `stt_api_key` were moved"
    STT is now selected like TTS, through the top-level `assistant_stt_model` + `assistant_stt_config` pair (see the Pipeline tab above). Sending the old `assistant_interaction_config.user_stt_provider` or `.stt_api_key` keys now fails with `422` — silently ignoring them would have dropped per-assistant Sarvam keys. Existing assistants are migrated by `scripts/migrate_stt_config.py`; behavior is unchanged.

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `speaks_first` | boolean | No | If `true` (default), assistant sends an opening response first in all three modes. |
| `filler_words` | boolean | No | Enables filler words while user is speaking. Requires an external TTS — available in `pipeline` and `cascade`, not `realtime`. |
| `silence_reprompts` | boolean | No | Enables reprompts during prolonged user silence. |
| `silence_reprompt_interval` | number | No | Reprompt interval in seconds (1.0-60.0). Default: `10.0`. |
| `silence_max_reprompts` | number | No | Maximum reprompts before ending session (0-5). Default: `2`. |
| `background_sound_enabled` | boolean | No | Enables background ambience. Default: `true`. |
| `thinking_sound_enabled` | boolean | No | Enables the typing-style thinking sound. Default: `true`. |
| `allow_interruptions` | boolean | No | If `true`, users can interrupt the assistant's initial greeting. Default: `false` (greeting is uninterruptible). |
| `input_guard_window_sec` | number | No | Seconds at the start of **every** agent reply during which caller audio is blanked (0.0-10.0). Default: `3.0`. Blocks repeated "Hello? Hello?" and short filler sounds ("um", "uh") from cutting the agent off — the noise gate cannot filter those, since they are genuine speech. Raise it to reject more fillers; the caller also cannot genuinely interrupt within the window. `0` disables the guard. Unmutes early if the reply finishes first. |
| `preferred_languages` | array of strings | No | BCP-47 language codes the agent supports (e.g. `["hi-IN", "en-US", "ta-IN"]`). A hint for the `native` transcription prompt only — **never** sent to a speech provider as a language parameter, and it neither pins a language nor disables auto-detect. Pin a language on `assistant_stt_config` instead. |
| `max_call_duration_minutes` | number | No | Hard ceiling on active-call length in minutes (must be `> 0`). When the limit is reached, the assistant speaks a brief farewell and the call is torn down gracefully (recording, transcripts, usage and webhook all finalize cleanly). When unset or `null`, the platform default of **30 minutes** applies. Does not apply to passthrough calls (no AI agent). The call termination reason is reported as `max_duration_exceeded` in the end-of-call webhook payload and in the `CallRecord.call_end_reason` field. |

These sound settings are assistant defaults and apply to runtime sessions started through the call and web-call APIs. Those APIs do not expose per-call sound overrides.

!!! note "Text-only web calls override these flags"
    When `POST /web_call/get_token` is called with `"text_only": true`, the session has no audio I/O. Filler words, silence reprompts, background sound, thinking sound, and the per-utterance input guard are all force-disabled for that session regardless of the assistant's saved values — they require an audio channel that does not exist in text mode. The stored assistant config is not modified; voice web calls and phone calls for the same assistant still honor it.

## Response Schema

| Field | Type | Description |
| :--- | :--- | :--- |
| `success` | boolean | Operation status. |
| `message` | string | Human-readable message. |
| `data.assistant_id` | string | Created assistant UUID. |
| `data.assistant_name` | string | Created assistant name. |

## Example Response

```json
{
  "success": true,
  "message": "Assistant created successfully",
  "data": {
    "assistant_id": "550e8400-e29b-41d4-a716-446655440000",
    "assistant_name": "Support Bot"
  }
}
```

## HTTP Status Codes

| Code | Description |
| :--- | :--- |
| 200 | Assistant created successfully. |
| 400 | Validation or payload mismatch error. |
| 401 | Unauthorized. |
| 500 | Internal server error. |

## API Keys

Provider keys are stored as sent — they are not checked against the provider, so a wrong key first shows up as a failure during a call. Every `api_key` is returned masked by `GET /assistant/details` and `GET /assistant/list`, and sending a masked value back is rejected with `422`.
