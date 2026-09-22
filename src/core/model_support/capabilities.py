"""Which cascade LLM knobs each OpenAI model actually accepts.

One table, two readers: the API schema validator (`api_schemas/config/llm_config.py`)
rejects an impossible pairing at create/update time, and the runtime factory
(`agents/llm/factory.py`) drops one that a stored config still holds. It lives in
`core/agents/` rather than beside either of them because the two live in different
deployments — the control image has no `livekit-agents`, the agent image has no FastAPI —
and this module must import cleanly into both. Keep it dependency-free.

Membership is spelled out per model instead of matched by prefix. The families do not
follow the prefix: a `gpt-5.x-chat-latest` alias starts with "gpt-5" but is a chat model
that rejects `reasoning.effort`, and a prefix test silently sent it anyway. The cost of a
wrong answer here is the whole call: OpenAI replies 400, the Responses plugin raises a
non-retryable APIStatusError inside `_llm_inference_task`, and it does so on every turn —
the assistant answers, greets nobody and never speaks.

**Never edit a model set here from memory.** OpenAI retires models on its own schedule and
a stale entry is indistinguishable from a working one until a call goes silent. The only
supported way to change one of these sets is to run
`uv run python scripts/check_model_allowlist.py` against the production key and follow its
output. See docs/reference/troubleshooting.md.
"""

# What cascade runs when the assistant sets no model. Lives here so the API validator can
# check the knobs against the model the call will actually use, not against None.
DEFAULT_CASCADE_MODEL = "gpt-4.1"

# What pipeline and realtime mode run on OpenAI when the assistant sets no model. Same
# reason it lives here: the API has to validate the model the call will actually use, and
# `session.py` (agent image) and the route (control image) must not each keep their own copy.
DEFAULT_REALTIME_MODEL = "gpt-realtime-1.5"

# Reasoning models: they take `reasoning.effort` and reject `temperature` and the other
# sampling knobs. https://docs.livekit.io/reference/agents/inference-llm-parameters/
#
# `gpt-5.4-nano`, `gpt-5.5` and the three `gpt-5.6-*` ids are listed by LiveKit's OpenAI
# model table but are not in the installed plugin's `ChatModels` Literal. That is fine — the
# plugin types `model` as `str | ResponsesModel` and never checks membership — but it means
# the Literal cannot be used as a source of truth here either. check_model_allowlist.py is.
REASONING_MODELS = frozenset(
    {
        "gpt-5",
        "gpt-5-mini",
        "gpt-5-nano",
        "gpt-5.1",
        "gpt-5.2",
        "gpt-5.4",
        "gpt-5.4-mini",
        "gpt-5.4-nano",
        "gpt-5.5",
        "gpt-5.6-sol",
        "gpt-5.6-terra",
        "gpt-5.6-luna",
    }
)

# Non-reasoning chat models: temperature yes, reasoning.effort no.
#
# The `gpt-5.1-chat-latest` / `gpt-5.2-chat-latest` / `gpt-5.3-chat-latest` aliases used to
# sit here. They were RETIRED on 2026-06-19 and are no longer accessible
# (https://docs.livekit.io/agents/models/llm/openai/), which is fatal rather than
# cosmetic: a retired model 400s on every LLM turn, so the call connects and the assistant
# never speaks. `chat-latest` and `gpt-oss-120b` were here too and are equally unusable on
# this deployment — `openai/chat-latest` is a LiveKit Inference gateway id (Cloud
# credentials, which this platform does not have) and `gpt-oss-120b` is served by baseten
# and groq, not by api.openai.com.
#
# Do not restore any of them, and do not add a replacement from memory: run
# `uv run python scripts/check_model_allowlist.py` and add what the account actually serves.
CHAT_MODELS = frozenset(
    {
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-4o",
        "gpt-4o-mini",
    }
)

# Everything cascade mode will run. The API allowlist (OPENAI_CASCADE_MODELS) is this set.
CASCADE_MODELS = REASONING_MODELS | CHAT_MODELS

# `text.verbosity` is a gpt-5 generation parameter. Older models reject it. With the
# gpt-5.x chat aliases retired, the gpt-5 generation and the reasoning models are the same
# set — kept as its own name because the two answer different questions and OpenAI can ship
# a new non-reasoning gpt-5 chat model at any time.
GPT5_GENERATION = REASONING_MODELS

# These reasoning models reject `reasoning.effort` once function tools are attached —
# mirrors livekit.agents.inference.llm._REASONING_EFFORT_TOOL_INCOMPATIBLE_PREFIXES, which
# the Responses plugin never applies (it calls drop_unsupported_params without `tools`, and
# the filter matches the key "reasoning_effort" while the Responses payload key is
# "reasoning"). So the check has to happen on our side. See
# agents/llm/factory.py::create_llm, which also has to undo the plugin's *own* injected
# default for these models.
REASONING_TOOL_INCOMPATIBLE = frozenset({"gpt-5.2", "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano"})

# Models where openai.responses.LLM inserts a Reasoning object on its own when the caller
# passes none (plugins/openai/responses/llm.py, `_supports_reasoning_effort`). Filtering our
# own kwargs is not enough for these — the knob arrives even from an empty config.
PLUGIN_INJECTS_REASONING = frozenset(
    {"gpt-5", "gpt-5-mini", "gpt-5-nano", "gpt-5.1", "gpt-5.2", "gpt-5.4", "gpt-5.4-mini"}
)


# ── Realtime models (pipeline + realtime modes) ──────────────────────────────────────
# Two generations behind one API, and the split matters: `session.truncation`
# (retention_ratio + token_limits) arrived with the GA line and is not part of the beta
# session shape. An unknown session field comes back as an error event and the session never
# settles, so the field goes only to the GA models. Semantic VAD predates the split and goes
# to both.
#
# Cross-checked against `livekit.plugins.openai.models.RealtimeModels` in livekit-agents
# 1.6.7. The two `*-mini` ids are not in that Literal and are still accepted here: the plugin
# types `model` as a plain string and never checks, and both ids are real. Anything that turns
# out not to be real is caught by the live check at create/update time — which is why this
# list may be generous where the cascade list may not.
REALTIME_GA_MODELS = frozenset(
    {
        "gpt-realtime",
        "gpt-realtime-1.5",
        "gpt-realtime-2",
        "gpt-realtime-2025-08-28",
        "gpt-realtime-mini",
    }
)

# The older beta line, and **no longer allowlisted**: measured on 2026-08-13 with
# scripts/check_model_allowlist.py, the account does not serve either of them, so accepting one
# would store a config whose session cannot connect. They stay named here because
# `realtime_supports_truncation` is asked about *stored* rows too, and these two predate the
# GA `session.truncation` field — a row still holding one must not be sent it on top of
# everything else that is wrong with it.
REALTIME_BETA_MODELS = frozenset({"gpt-4o-realtime-preview", "gpt-4o-mini-realtime-preview"})

# What the API accepts in pipeline and realtime mode for provider 'openai'. GA line only.
REALTIME_MODELS = REALTIME_GA_MODELS

# Defined as the GA set rather than spelled out again, so it cannot list a model the API
# rejects. It used to: `gpt-realtime-2` and `gpt-realtime-2025-08-28` were named here while
# the API allowlist refused them, making both entries dead code that read like coverage.
REALTIME_TRUNCATION_MODELS = REALTIME_GA_MODELS


def realtime_supports_truncation(model: str) -> bool:
    """True when this realtime model takes the GA `session.truncation` field."""
    return model in REALTIME_TRUNCATION_MODELS


# ── Gemini realtime (realtime mode only) ─────────────────────────────────────────────
# There is no `/v1/models` equivalent to ask, so this list is the gate. Straight from
# `livekit.plugins.google.realtime.api_proto.LiveAPIModels` in livekit-agents 1.8.2 — the Live
# API is a small, slow-moving set, unlike the Gemini chat models.
#
# A non-Live Gemini id (`gemini-2.5-flash`, say) is not rejected by the plugin: it opens a
# WebSocket that the API closes, and the job ends with no audio. Hence the allowlist.
GEMINI_LIVE_MODELS = frozenset(
    {
        "gemini-3.8-live",
        "gemini-3.8-live-extended-thinking",
        "gemini-3.1-flash-live-preview",
        "gemini-2.5-flash-native-audio-preview-12-2025",
    }
)

# The plugin's Literal carries one more id than the set above: a Vertex-only model that raises
# while being built unless `vertexai=True`, which this GOOGLE_API_KEY deployment never sets. It
# is named here rather than allowed, so the API can say why. Together the two sets equal the
# plugin's Literal, which a test asserts — this module cannot import the plugin itself (the
# control image has no livekit-agents).
GEMINI_VERTEX_ONLY_MODELS = frozenset({"gemini-live-2.5-flash-native-audio"})

# The Gemini Live voice roster, from the same plugin module (`api_proto.Voice`). Closed set,
# 30 names, and worth enforcing for one specific reason: it shares a config field with the
# OpenAI realtime voices and the two rosters have nothing in common, so `voice: "Puck"` under
# provider 'openai' (or `voice: "marin"` under 'gemini') is an easy mistake that ends the
# session at connect time.
GEMINI_VOICES = frozenset(
    {
        "Achernar",
        "Achird",
        "Algenib",
        "Algieba",
        "Alnilam",
        "Aoede",
        "Autonoe",
        "Callirrhoe",
        "Charon",
        "Despina",
        "Enceladus",
        "Erinome",
        "Fenrir",
        "Gacrux",
        "Iapetus",
        "Kore",
        "Laomedeia",
        "Leda",
        "Orus",
        "Pulcherrima",
        "Puck",
        "Rasalgethi",
        "Sadachbia",
        "Sadaltager",
        "Schedar",
        "Sulafat",
        "Umbriel",
        "Vindemiatrix",
        "Zephyr",
        "Zubenelgenubi",
    }
)

# What Gemini realtime runs when the assistant names no model. Kept next to the sets above so
# the API validates the model the call will actually use.
DEFAULT_GEMINI_LIVE_MODEL = "gemini-3.8-live"

# What Gemini realtime speaks with when the assistant names no voice.
DEFAULT_GEMINI_VOICE = "Puck"


# Which `service_tier` values work, measured against the OpenAI API on 2026-08-13 rather than
# taken from any table — OpenAI documents flex availability on a pricing page and documents
# `fast` nowhere at all:
#
#   tier      gpt-4.1  gpt-4.1-nano  gpt-5-mini  chat-latest   notes
#   unset     ok       ok            ok          ok            what most assistants should use
#   auto      ok       ok            ok          ok
#   default   ok       ok            ok          ok
#   fast      ok       ok            ok          ok            undocumented, works everywhere
#   priority  ok       ok            ok          ok            account entitlement, held here
#   flex      400      400           ok          400           gpt-5 line only
#   scale     400      400           400         400           not a tier at all
#
# `scale` is gone from the accepted values entirely: OpenAI answers "Invalid value: 'scale'.
# Supported values are: 'auto', 'default', 'fast', 'flex', and 'priority'" for every model, so
# no assistant could ever have used it.
#
# `flex` is the one worth gating, and it is the knob that produced the outage this module was
# hardened for: on `gpt-4.1-nano` it is refused with the *generic* "There was an issue with your
# request" and no parameter name, so the call connected and the assistant never spoke. On
# `gpt-4.1` the same request says "Invalid service_tier argument" — same failure, different
# message, which is why guessing from error text does not work either.
SERVICE_TIER_ALWAYS_OK = frozenset({"auto", "default", "fast", "priority"})

# Only the gpt-5 generation takes `flex`. Re-measure with
# `scripts/check_model_allowlist.py --probe <model>` before widening this.
SERVICE_TIER_FLEX_MODELS = REASONING_MODELS


def unsupported_service_tier_reason(model: str, tier: str | None) -> str | None:
    """Why this model cannot use this processing tier, or None when it can.

    Unknown models are not second-guessed, same rule as the generation knobs: a row written
    before this check existed keeps whatever it holds.
    """
    if not tier or tier in SERVICE_TIER_ALWAYS_OK:
        return None
    if model not in CASCADE_MODELS:
        return None
    if tier == "flex" and model not in SERVICE_TIER_FLEX_MODELS:
        return (
            "'flex' is a gpt-5 generation tier — this model answers a flex request with a 400 "
            "on every turn, so the call would connect and the assistant would never speak. "
            "Use 'fast', 'priority', or leave the tier unset"
        )
    return None


def unsupported_knob_reason(
    model: str, knob: str, *, has_tools: bool = False, value=None
) -> str | None:
    """Why this generation knob cannot go to this model, or None when the model reads it.

    `has_tools` is whether the session will attach function tools (any `tool_ids` on the
    assistant, or the built-in `end_call`). Both callers can work it out: the API from the
    stored row, `create_llm` from the tool list it is handed. It changes the answer for
    `reasoning_effort` on the models in REASONING_TOOL_INCOMPATIBLE, and it is what makes
    `tool_choice: "required"` legal or not.

    `value` is only read for the knobs whose *value* is gated (`tool_choice`). Left None it
    means "the knob is set to something" and only the model-level rules apply.

    An unknown model — one outside CASCADE_MODELS, i.e. a row written before the allowlist
    or by a direct DB edit — gets None for every knob. The knobs are forwarded as-is rather
    than guessed at; guessing is what the prefix test used to do. A model that OpenAI has
    since retired lands here too, and nothing can be salvaged for it anyway: OpenAI rejects
    the turn on the model id alone, before it looks at a single knob.
    """
    if model not in CASCADE_MODELS:
        return None

    # The reasons name the parameter and the rule, never the model: every caller already
    # prints the model alongside, and repeating it reads as a stutter in the 422 body.
    #
    # Note this covers every gpt-5* model on the allowlist, not just the reasoning ones:
    # `livekit.agents.inference.llm._UNSUPPORTED_PARAMS` keys on the bare prefix "gpt-5", so
    # the SDK strips temperature for anything in that generation. Were a non-reasoning gpt-5
    # chat model ever allowlisted again, temperature on it would be accepted here, stored,
    # returned by GET — and never sent. Add it to REASONING_MODELS' temperature rule then.
    if knob == "temperature" and model in REASONING_MODELS:
        return "reasoning models reject temperature — set reasoning_effort instead"

    if knob == "reasoning_effort":
        if model not in REASONING_MODELS:
            return "reasoning.effort is a reasoning-model parameter, and this is a chat model"
        if has_tools and model in REASONING_TOOL_INCOMPATIBLE:
            return "this model rejects reasoning.effort while function tools are attached"

    if knob == "verbosity" and model not in GPT5_GENERATION:
        return "text.verbosity is a gpt-5 generation parameter"

    # tool_choice 'required' with nothing to choose from is a 400 from OpenAI on every turn,
    # which is the silent-call shape again. 'none' is left alone: it is the legitimate way to
    # say "do not call tools", and it is harmless with an empty tool list.
    if knob == "service_tier":
        return unsupported_service_tier_reason(model, value)

    if knob == "tool_choice" and value == "required" and not has_tools:
        return (
            "tool_choice 'required' needs at least one tool — attach a tool "
            "(POST /assistant/attach-tools) or enable assistant_end_call_enabled, or use "
            "'auto'"
        )

    return None
