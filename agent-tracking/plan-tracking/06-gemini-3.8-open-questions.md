# Open questions left by the Gemini 3.8 Live work (2026-09-22)

Plan `agent-tracking/plan/05-gemini-3.8-live-models.md` is implemented. Three things were
found while auditing that implementation and deliberately **not** changed. Each one needs a
live call to settle, which is why none of them is a code change yet.

## 1. Tool behaviour on the 3.8 line is the model's default, not ours

Google's model card for `gemini-3.8-live-extended-thinking` says: "Only asynchronous
non-blocking execution (`behavior: NON_BLOCKING`) is supported. Synchronous blocking mode is
not supported and returns a hard error."
(`ai.google.dev/gemini-api/docs/models/gemini-3.8-live-extended-thinking`, read 2026-09-22.)
The card for `gemini-3.8-live` says async "is now the default function calling mode".

`src/core/agents/session.py:872` builds the model without `tool_behavior`, and the plugin then
omits the field entirely. Verified against the installed plugin — with `tool_behavior` unset,
`create_tools_config` emits:

```json
{"function_declarations": [{"description": "Hang up.", "name": "end_call"}]}
```

No `behavior` key, so Gemini applies its own per-model default. That should be correct on both
3.8 ids, and it is the reason nothing was changed. What is unverified is whether the API
really treats "no field" as NON_BLOCKING on the extended-thinking model, or whether it applies
the account-wide legacy default and answers with the hard error the card describes. Every
realtime session here carries at least the `end_call` tool, so if it is the latter, every
extended-thinking call fails at tool declaration.

**What to do:** place one call on `gemini-3.8-live-extended-thinking` with a tool attached and
watch whether the tool is declared and called. If it errors, pass
`tool_behavior=types.Behavior.NON_BLOCKING` for the 3.8 ids in `session.py`.

A second, smaller consequence of leaving it unset: `_RealtimeOptions.tool_behavior` stays
`NOT_GIVEN`, so the plugin's `supports_silent_scheduling` is False
(`realtime_api.py:708-724`) and a tool result that asks for no reply is spoken over anyway,
with a warning in the worker log. Setting the option explicitly would also fix that.

Note for anyone re-reading plan 05: its research section claims the plugin carries
`MODELS_DEFAULT_NON_BLOCKING = ("3.8",)`. **That symbol does not exist** in
`livekit-plugins-google` 1.8.2. Only `MODELS_WITHOUT_REPLY_PLACEHOLDER = ("3.1", "3.8")` is
there (`realtime_api.py:87`). The plan's conclusion (no factory change needed) still holds,
but not for the reason it gives.

## 2. Thinking tokens are not metered, so extended-thinking under-bills

The Google plugin builds its usage metrics from `usage_metadata.prompt_token_count`,
`response_token_count` and the three modality detail maps (`realtime_api.py:1612-1640`). It
never reads `usage_metadata.thoughts_token_count` or `tool_use_prompt_token_count`, both of
which the `google-genai` SDK exposes.

Google bills thinking tokens as output text. On `gemini-3.8-live-extended-thinking`, where
reasoning is the point of the model, the stored `estimated_cost_usd` is therefore low by
however much the model thought. `GEMINI_LIVE_RATES` cannot fix this — the tokens never reach
the usage record.

**What to do:** measure the gap on a real call (compare the stored record against the Google
console for the same session), then either upstream a plugin fix or fold
`thoughts_token_count` in ourselves through the same `extra_usage` route the Sarvam STT tap
uses (`src/core/agents/usage.py`).

## 3. The Cartesia rate is derived, not quoted

`CARTESIA_TTS_RATES` / `CARTESIA_STT_RATES` in `src/core/pricing/rates.py` come from the
published Startup tier ($49/month → 1.25M credits → ~1,667 minutes of sonic-3, ~115h44m of
ink-2), because Cartesia publishes no per-unit price. If this deployment has a contract rate,
replace both numbers with it; the comment beside them says the same thing.
