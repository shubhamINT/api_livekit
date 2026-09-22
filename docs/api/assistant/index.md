# Assistants

## Overview

Assistants define voice agent behavior, prompt/instructions, interaction settings, optional tools, and optional end-call behavior.

Assistant execution supports three runtime modes, selected by `assistant_mode` (not to be confused
with `assistant_llm_config.provider`, the LLM vendor):

- `pipeline` (default, half-cascade): a realtime model emits text, a separate TTS provider speaks it.
  LLM vendor is `openai` only.
- `realtime`: one model handles STT + LLM + TTS and speaks its own audio. Vendor `gemini` (default) or
  `openai`.
- `cascade`: a true three-stage pipeline — plugin STT, a plain (non-realtime) LLM, plugin TTS, each a
  separate metered stage. LLM vendor is `openai` only. See [Cascade Pipeline](../../architecture/cascade-pipeline.md).

TTS providers (`pipeline` and `cascade` modes): `cartesia`, `sarvam`, `elevenlabs`, `mistral`. Full model
IDs and defaults live in [Models & Providers](../../reference/models.md); which combinations of mode,
LLM, STT and TTS are actually valid lives in the
[Compatibility Matrix](../../reference/compatibility.md).

## Mode Rules

- `assistant_mode="pipeline"` requires both `assistant_tts_model` and `assistant_tts_config`.
- In `pipeline` mode, `assistant_llm_config` is optional and defaults to `provider="openai"`, `model="gpt-realtime-1.5"`. `api_key` overrides the system `OPENAI_API_KEY`; `voice` is ignored.
- `provider="gemini"` is **rejected with `422`** in `pipeline` and `cascade` mode — Google's Live API cannot run the text-only modality half-cascade requires on its native-audio models. Gemini is fully supported in `realtime` mode. See the [Compatibility Matrix](../../reference/compatibility.md#mode-llm-provider).
- In `pipeline` and `realtime` mode, `assistant_llm_config.model` must be an OpenAI **realtime** model ID (`gpt-realtime-1.5` and friends); chat models such as `gpt-4.1` belong to `cascade` mode and are rejected with `422`.
- `assistant_mode="realtime"` requires `assistant_llm_config`.
- In `realtime` mode, Gemini fields still have defaults: `provider="gemini"`, `model="gemini-3.8-live"`, `voice="Puck"`. `assistant_llm_config.api_key` overrides the system `GOOGLE_API_KEY`. Both `model` and `voice` are validated against the Live model list and the Gemini voice roster — see [Compatibility Matrix](../../reference/compatibility.md#model-ids).
- In `realtime` mode, `assistant_tts_model` and `assistant_tts_config` are ignored by runtime.
- `assistant_mode="cascade"` requires `assistant_tts_model` + `assistant_tts_config`; `assistant_stt_model` must be `sarvam`, `cartesia`, `deepgram`, `elevenlabs` or `openai` (`native` rejected); `assistant_llm_config.provider` must be `openai` or unset.
- In `cascade` mode, `temperature`, `reasoning_effort` and `verbosity` are only accepted on models that read them (reasoning models take `reasoning_effort`, chat models take `temperature`, `verbosity` is gpt-5 generation only) — a mismatch is a `422`, because OpenAI rejects such a request on every LLM turn and the call goes silent. [Cascade LLM knobs](../../reference/compatibility.md#cascade-llm-knobs).
- `assistant_start_instruction` is used as the opening response when `assistant_interaction_config.speaks_first=true`.
- `assistant_interaction_config.speaks_first` works in all three modes.
- Unknown keys inside `assistant_llm_config`, `assistant_tts_config` or `assistant_stt_config` are rejected with `422` rather than ignored.
- `assistant_interaction_config.background_sound_enabled` and `assistant_interaction_config.thinking_sound_enabled` default to `true`.
- Background/thinking sound is configured at the assistant level only; call-trigger APIs do not override it per session.

## Endpoints

- [Create Assistant](create.md)
- [List Assistants](list.md)
- [Get Assistant Details](get.md)
- [Update Assistant](update.md)
- [Delete Assistant](delete.md)
- [Get Call Logs](logs.md)
- [Using Placeholders](placeholders.md)
- [TTS Humanization Prompting Guide](tts-humanization.md)
- [Sarvam Prompt (Exact)](humanization/tts_humanification_sarvam.md)
- [Cartesia Prompt (Exact)](humanization/tts_humanification_cartesia.md)
- [ElevenLabs Prompt (Exact)](humanization/tts_humanification_elevenlabs.md)
