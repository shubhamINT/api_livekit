from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.core.model_support.capabilities import (
    CASCADE_MODELS,
    DEFAULT_CASCADE_MODEL,
    DEFAULT_GEMINI_LIVE_MODEL,
    GEMINI_LIVE_MODELS,
    GEMINI_VERTEX_ONLY_MODELS,
    GEMINI_VOICES,
    REALTIME_MODELS,
    unsupported_knob_reason,
)
from src.core.providers.keys import ProviderApiKey

# ── Runtime mode ────────────────────────────────────
# Selects the shape of the whole session (which stages exist, plugin vs. one realtime
# model) — not an LLM choice. That lives in AssistantLLMConfig.provider/model below.
AssistantMode = Literal["pipeline", "realtime", "cascade"]

_RETIRED_MODE_KEY_ERROR = (
    "`assistant_llm_mode` has been renamed to `assistant_mode`. Update your request."
)


def reject_retired_mode_key(data: dict) -> None:
    if isinstance(data, dict) and "assistant_llm_mode" in data:
        raise ValueError(_RETIRED_MODE_KEY_ERROR)


# ── OpenAI cascade LLM models ────────────────────────
# The non-realtime OpenAI chat/test models accepted in cascade mode. The `model`
# field is shared with the realtime/pipeline modes (which use realtime model IDs
# like "gpt-realtime-1.5" or Gemini), so the allowlist is enforced only inside the
# cascade validator rather than as a Literal on the shared field — that would
# reject realtime model names.
#
# The list itself lives in core/model_support/capabilities.py, split by family, because the
# same split decides which generation knobs each model accepts. Adding a model there is
# what adds it here. Keep both in sync with docs/architecture/cascade-pipeline.md and
# docs/reference/compatibility.md when OpenAI ships new models.
OPENAI_CASCADE_MODELS = CASCADE_MODELS

# ── OpenAI realtime models (pipeline + realtime modes) ──
# Pipeline and realtime both build an `openai.realtime.RealtimeModel`, which only speaks
# to the Realtime API. Passing a chat model such as "gpt-4.1" there used to be accepted at
# create time and then failed to connect at call time, so the two allowlists are kept
# separate and each mode checks its own.
#
# The set itself lives in core/model_support/capabilities.py next to
# REALTIME_TRUNCATION_MODELS, which is derived from it. Keeping a second copy here is how the
# truncation set ended up naming two models this list rejected.
OPENAI_REALTIME_MODELS = REALTIME_MODELS

# Reasoning models take reasoning_effort and reject temperature, top_p and the penalties.
# Which models those are lives in core/model_support/capabilities.py. Values match
# openai.types.Reasoning.effort.
#
# The value set here is model-independent; the pairing with the selected model is checked
# below by _validate_cascade_knobs, and again at call time by the factory — a stored config
# outlives the model it was written for.
REASONING_EFFORT = Literal["none", "minimal", "low", "medium", "high", "xhigh", "max"]
# Measured against the API, not copied from a doc page: "scale" is refused for every model
# ("Invalid value: 'scale'. Supported values are: 'auto', 'default', 'fast', 'flex', and
# 'priority'"), so it is gone; "fast" is accepted by every model tested and was missing.
# Which models accept "flex" is a separate question — see
# model_support.capabilities.unsupported_service_tier_reason.
_SERVICE_TIERS = Literal["auto", "default", "fast", "flex", "priority"]
_VERBOSITY = Literal["low", "medium", "high"]
_RESPONSES_TOOL_CHOICE = Literal["auto", "required", "none"]


# ── Assistant LLM Config sub-model ───────────────────
class AssistantLLMConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: Optional[Literal["gemini", "openai"]] = Field(None, description="LLM vendor. 'openai' in pipeline and cascade mode (the only value accepted there); 'gemini' (default) or 'openai' in realtime mode. Defaults to openai in pipeline/cascade and gemini in realtime.")
    model: Optional[str] = Field(None, description="Model override for the selected provider. Validated per mode: an OpenAI realtime ID in pipeline/realtime mode, an allowlisted OpenAI chat model in cascade mode. Gemini realtime model IDs are not validated.")
    voice: Optional[str] = Field(None, description="Voice override. Used when the model speaks its own audio (realtime mode).")
    api_key: ProviderApiKey = Field(None, min_length=1, max_length=500, description="Provider API key override for the selected provider (openai or gemini).")

    # Generation knobs. These are applied to the cascade LLM (openai.responses.LLM);
    # they are harmless (ignored) in the realtime/pipeline modes. See
    # docs/api/assistant/index.md and the OpenAI LLM docs for valid values.
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Sampling temperature (0–2). Higher is more random. Reasoning models (gpt-5.x) reject it, so it is dropped before the call on those; set reasoning_effort instead. Only one of temperature or top_p may be set (responses API uses temperature).")
    max_output_tokens: Optional[int] = Field(None, gt=0, description="Cap on output tokens for the response (responses API `max_output_tokens`).")
    reasoning_effort: Optional[REASONING_EFFORT] = Field(None, description="Reasoning depth. A gpt-5 parameter: older models reject it, so it is dropped before the call on anything outside the gpt-5 line rather than sent and failed.")
    service_tier: Optional[_SERVICE_TIERS] = Field(None, description="OpenAI processing/billing tier: auto, default, fast, flex or priority. 'flex' is gpt-5 generation only — measured: on gpt-4.1/gpt-4.1-nano it is refused with a 400 on every turn (and on nano OpenAI names no parameter at all, so the call just goes silent), so it is rejected here with a 422. 'scale' is not an OpenAI tier and is no longer accepted. Leave unset unless you have a reason: auto, default and fast all work everywhere.")
    verbosity: Optional[_VERBOSITY] = Field(None, description="Constrains response verbosity: low, medium, high. A gpt-5 parameter (`text.verbosity`), dropped before the call on older models — chat-latest counts as gpt-5 here.")
    tool_choice: Optional[_RESPONSES_TOOL_CHOICE] = Field(None, description="How the model uses tools in cascade mode: auto, required or none.")
    parallel_tool_calls: Optional[bool] = Field(None, description="Allow the model to make multiple tool calls in a single response.")


# Rejecting Gemini in pipeline mode: LiveKit's half-cascade pattern needs the realtime
# model in a text-only modality, and Google's Live API only supports that on
# non-native-audio models (https://github.com/googleapis/python-genai/issues/1780). The
# Live models we would actually want are native-audio, and the 3.1 line additionally
# ignores generate_reply()/update_instructions(), which the greeting and agent-handoff
# paths depend on. Gemini remains fully supported in realtime mode.
PIPELINE_GEMINI_ERROR = (
    "assistant_llm_config.provider 'gemini' is not supported in pipeline mode — "
    "Google's Live API cannot run the text-only (half-cascade) modality on its "
    "native-audio models. Use assistant_mode 'realtime' for Gemini, or provider "
    "'openai' in pipeline mode. See docs/reference/compatibility.md."
)


def _validate_cascade_knobs(llm_config, model, has_tools: bool = False) -> None:
    """Reject a generation knob the chosen cascade model cannot read.

    Without this the knob was accepted, stored, and then dropped (or worse, sent and 400'd)
    at call time — the operator saw a config field that did nothing.

    `has_tools` is whether the session will attach function tools, which the assistant
    declares (`tool_ids`, plus the built-in `end_call`). It decides two rules: whether
    `tool_choice: "required"` has anything to choose from, and whether `gpt-5.2`/`gpt-5.4*`
    still accept `reasoning.effort`. The create/update schema knows only what the request
    says; `enforce_stored_mode_constraints` re-runs this against the stored row, which is
    where the full answer lives.
    """
    for knob in ("temperature", "reasoning_effort", "verbosity", "tool_choice", "service_tier"):
        value = getattr(llm_config, knob, None)
        if value is None:
            continue
        reason = unsupported_knob_reason(model, knob, has_tools=has_tools, value=value)
        if reason:
            raise ValueError(
                f"assistant_llm_config.{knob} is not supported by model '{model}' — {reason}. "
                "See docs/reference/compatibility.md."
            )


def _validate_realtime_voice(provider, voice) -> None:
    """Reject a voice from the wrong vendor's roster.

    `voice` is one field shared by two providers whose rosters have nothing in common —
    Gemini's are star names (`Puck`, `Kore`, `Zephyr`), OpenAI's are ordinary words (`marin`,
    `cedar`, `alloy`). Sending one vendor's name to the other ends the session at connect
    time, and it is an easy mistake to make when switching provider on an existing assistant.

    Only the mistake is rejected, not the unknown: Gemini's roster is a closed Literal in the
    installed plugin, so a name outside it cannot work and is refused. OpenAI ships realtime
    voices without a corresponding Literal in the SDK, so anything that is not recognisably a
    Gemini name is allowed through rather than blocking a voice released this morning.
    """
    if not voice:
        return

    if provider == "openai":
        if voice in GEMINI_VOICES:
            raise ValueError(
                f"assistant_llm_config.voice '{voice}' is a Gemini Live voice and cannot be "
                "used with provider 'openai' — use an OpenAI realtime voice such as 'marin' "
                "or 'cedar', or switch the provider to 'gemini'."
            )
        return

    # Gemini (explicit or by default in realtime mode).
    if voice not in GEMINI_VOICES:
        raise ValueError(
            f"assistant_llm_config.voice '{voice}' is not a Gemini Live voice — must be one "
            f"of: {', '.join(sorted(GEMINI_VOICES))}. OpenAI realtime voice names such as "
            "'marin' belong to provider 'openai'."
        )


def validate_mode_config(mode, llm_config, stt_model, *, has_tools: bool = False) -> None:
    """Reject provider/model/STT combinations the runtime cannot actually run.

    One rule table for all three modes, shared by the create and update validators so a
    combination is rejected with a 422 at the API rather than accepted and then failing at
    job start with only a log line. The runtime counterparts are
    src/core/agents/session.py (pipeline/realtime) and src/core/agents/llm/factory.py
    plus src/core/agents/stt/factory.py (cascade). Keep both in sync, and keep
    docs/reference/compatibility.md in sync with both.

    This is the offline half of the guard. It cannot know which `reasoning_effort` *values* a
    model takes, whether the account may use a given `service_tier`, or whether a tool schema
    is strict-valid — OpenAI is asked those at create/update time instead, in
    `api/validation/assistant_guard.py`.
    """
    provider = getattr(llm_config, "provider", None)
    model = getattr(llm_config, "model", None)

    if mode == "cascade":
        # Cascade runs a plain LLM, so there is no realtime model to speak its own audio
        # or transcribe itself: 'native' STT is meaningless, and only OpenAI is wired up
        # as a non-realtime LLM (see src/core/agents/llm/factory.py).
        if stt_model == "native":
            raise ValueError(
                "assistant_stt_model 'native' is not valid in cascade mode — "
                "choose 'sarvam' (multilingual), 'cartesia', 'deepgram', 'elevenlabs' or 'openai'."
            )
        if provider and provider != "openai":
            raise ValueError(
                f"assistant_llm_config.provider '{provider}' is not supported in cascade mode — "
                "cascade supports 'openai' only."
            )
        if model and model not in OPENAI_CASCADE_MODELS:
            raise ValueError(
                f"assistant_llm_config.model '{model}' is not supported in cascade mode — "
                "must be one of the documented OpenAI models: "
                f"{', '.join(sorted(OPENAI_CASCADE_MODELS))}."
            )
        if llm_config is not None:
            _validate_cascade_knobs(
                llm_config, model or DEFAULT_CASCADE_MODEL, has_tools=has_tools
            )
        return

    if mode == "pipeline":
        if provider and provider != "openai":
            raise ValueError(PIPELINE_GEMINI_ERROR)
        if model and model not in OPENAI_REALTIME_MODELS:
            raise ValueError(
                f"assistant_llm_config.model '{model}' is not a realtime model — "
                "pipeline mode drives the OpenAI Realtime API, so the model must be one "
                f"of: {', '.join(sorted(OPENAI_REALTIME_MODELS))}. Chat models such as "
                "'gpt-4.1' belong to cascade mode."
            )
        return

    if mode == "realtime":
        # Both vendors work here, and each has its own model set and its own voice roster.
        # Gemini's are checked against the installed plugin's own Literals: there is no
        # `/v1/models` to ask and no cheap probe, so this list is the only gate. A non-Live
        # Gemini id is not refused by the plugin — it opens a socket the API closes, and the
        # job ends with no audio and nothing that names the cause.
        if provider == "gemini" or provider is None:
            if model and model in GEMINI_VERTEX_ONLY_MODELS:
                raise ValueError(
                    f"assistant_llm_config.model '{model}' runs on Vertex AI only, and this "
                    "deployment authenticates with a GOOGLE_API_KEY. The worker would refuse "
                    "it at job start, after the call connects. Use "
                    f"'{DEFAULT_GEMINI_LIVE_MODEL}' or another Gemini API Live model: "
                    f"{', '.join(sorted(GEMINI_LIVE_MODELS))}."
                )
            if model and model not in GEMINI_LIVE_MODELS:
                raise ValueError(
                    f"assistant_llm_config.model '{model}' is not a Gemini Live model — "
                    f"must be one of: {', '.join(sorted(GEMINI_LIVE_MODELS))}. The Live API "
                    "is a separate, much smaller set than the Gemini chat models: "
                    "'gemini-2.5-flash' and friends cannot hold a realtime session."
                )
        elif provider == "openai" and model and model not in OPENAI_REALTIME_MODELS:
            raise ValueError(
                f"assistant_llm_config.model '{model}' is not an OpenAI realtime model — "
                f"must be one of: {', '.join(sorted(OPENAI_REALTIME_MODELS))}."
            )

        _validate_realtime_voice(provider, getattr(llm_config, "voice", None))
