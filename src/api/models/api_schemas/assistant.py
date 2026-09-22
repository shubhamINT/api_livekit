from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

from .config.interaction_config import (
    AssistantInteractionConfigSchema,
    EndCallWebhookSchema,
    GreetingAudioSchema,
    UpdateAssistantInteractionConfigSchema,
    UpdateEndCallWebhookSchema,
    UpdateGreetingAudioSchema,
)
from .config.llm_config import (
    AssistantLLMConfig,
    AssistantMode,
    reject_retired_mode_key,
    validate_mode_config,
)
from .config.stt_config import STTConfig
from .config.tts_config import TTSConfig


def inject_provider_type(data: dict, model_field: str, config_field: str) -> None:
    """Copy the provider name into config["type"] so the discriminated union resolves."""
    model = data.get(model_field)
    config = data.get(config_field)
    if model and isinstance(config, dict):
        config["type"] = model


def inject_stt_config(data: dict) -> None:
    """STT config is optional — a bare assistant_stt_model gets a defaults-only config.

    Keeps the stored pair consistent, so a sarvam→native switch cannot leave a stale
    sarvam config behind.
    """
    model = data.get("assistant_stt_model")
    if model and data.get("assistant_stt_config") is None:
        data["assistant_stt_config"] = {}
    inject_provider_type(data, "assistant_stt_model", "assistant_stt_config")


# For Assistant creation
class CreateAssistant(BaseModel):
    assistant_name: str = Field(..., min_length=1, max_length=100, description="Assistant's name (cannot be empty)")
    assistant_description: str = Field(..., description="Assistant's description (optional)")
    assistant_prompt: str = Field(..., description="Assistant's prompt (cannot be empty)")
    assistant_mode: AssistantMode = Field("pipeline", description="Runtime mode. 'pipeline' (default, half-cascade): a realtime model emits text, an external TTS speaks it. 'realtime': one model handles STT+LLM+TTS. 'cascade': a true three-stage pipeline — plugin STT, a plain LLM, plugin TTS, each billed and swappable on its own.")
    assistant_llm_config: Optional[AssistantLLMConfig] = Field(None, description="Shared LLM config. Optional in pipeline mode (supports api_key override). Required in realtime mode. In cascade mode the provider must be 'openai' (or omitted).")
    assistant_tts_model: Optional[Literal["cartesia", "sarvam", "elevenlabs", "mistral"]] = Field(None, description="TTS Provider (required for pipeline and cascade modes)")
    assistant_tts_config: Optional[TTSConfig] = Field(None, description="TTS Configuration object (required for pipeline and cascade modes)")
    assistant_stt_model: Optional[Literal["native", "sarvam", "cartesia", "deepgram", "elevenlabs", "openai"]] = Field(None, description="User-transcription source. In pipeline mode: 'sarvam' (the default when unset) runs Sarvam Saras v3 as a parallel audio tap, 'native' lets the conversational LLM transcribe itself. In cascade mode this is the session's own STT stage — 'sarvam' (multilingual, auto-detect + code-mixing), 'cartesia' (single fixed language), 'deepgram' (nova-3 multilingual), 'elevenlabs' (scribe v2 real-time, auto-detect) or 'openai' (gpt-4o-mini-transcribe over the realtime transcription socket); 'native' is rejected because there is no realtime model to self-transcribe. Ignored in realtime (audio-out) mode.")
    assistant_stt_config: Optional[STTConfig] = Field(None, description="STT configuration object. Optional — omit for provider defaults and the system API key.")
    assistant_start_instruction: Optional[str] = Field(None, max_length=500, description="Assistant's start instruction")
    assistant_interaction_config: AssistantInteractionConfigSchema = Field(default_factory=AssistantInteractionConfigSchema, description="Interaction settings for the assistant")
    assistant_greeting_audio: GreetingAudioSchema = Field(default_factory=GreetingAudioSchema, description="Optional prerecorded greeting (references an audio asset from /audio)")
    assistant_end_call_enabled: bool = Field(False, description="Enable built-in end_call tool")
    assistant_end_call_trigger_phrase: Optional[str] = Field(None, max_length=300, description="Example user phrase that should trigger end_call")
    assistant_end_call_agent_message: Optional[str] = Field(None, max_length=300, description="What assistant should say before ending the call")
    assistant_end_call_url: Optional[str] = Field(None, max_length=200, description="Assistant's end call url")
    assistant_end_call_webhook: EndCallWebhookSchema = Field(default_factory=EndCallWebhookSchema, description="Delivery tuning for the end-of-call webhook (timeout, attempts). Omit to use the server defaults — see docs/api/calls/webhook.md.")

    class Config:
        # Strip whitespace from string fields
        str_strip_whitespace = True
        # Example for API documentation
        json_schema_extra = {
            "examples": [
                {
                    "summary": "Pipeline mode (separate TTS)",
                    "value": {
                        "assistant_name": "Test Assistant",
                        "assistant_description": "Test Assistant Description(Optional)",
                        "assistant_prompt": "You are a helpful assistant.",
                        "assistant_mode": "pipeline",
                        "assistant_llm_config": {"api_key": "sk-..."},
                        "assistant_tts_model": "cartesia",
                        "assistant_tts_config": {
                            "voice_id": "a167e0f3-df7e-4277-976b-be2f952fa275"
                        },
                        "assistant_start_instruction": "Start instruction.",
                        "assistant_interaction_config": {
                            "speaks_first": True,
                            "filler_words": True,
                            "silence_reprompts": True,
                            "silence_reprompt_interval": 10.0,
                            "silence_max_reprompts": 2,
                            "background_sound_enabled": True,
                            "thinking_sound_enabled": True,
                        },
                        "assistant_end_call_enabled": True,
                        "assistant_end_call_trigger_phrase": "Thanks, that's all. You can end the call now.",
                        "assistant_end_call_agent_message": "Thank you for your time. Have a great day.",
                        "assistant_end_call_url": "End call url.",
                    },
                },
                {
                    "summary": "Realtime mode (Gemini handles STT+LLM+TTS)",
                    "value": {
                        "assistant_name": "Gemini Assistant",
                        "assistant_description": "Full realtime assistant",
                        "assistant_prompt": "You are a helpful assistant.",
                        "assistant_mode": "realtime",
                        "assistant_llm_config": {
                            "provider": "gemini",
                            "model": "gemini-3.8-live",
                            "voice": "Puck",
                        },
                    },
                },
            ]
        }

    @model_validator(mode="before")
    @classmethod
    def inject_tts_type(cls, data: dict):
        """Inject the `type` discriminator into tts_config/stt_config so Pydantic picks the right model."""
        reject_retired_mode_key(data)
        if isinstance(data, dict):
            inject_provider_type(data, "assistant_tts_model", "assistant_tts_config")
            inject_stt_config(data)
        return data

    @model_validator(mode="after")
    def validate_mode_fields(self):
        """Validate fields based on assistant_mode."""
        # pipeline and cascade both speak through an external TTS, so both require the pair.
        if self.assistant_mode in ("pipeline", "cascade"):
            mode = self.assistant_mode
            if not self.assistant_tts_model:
                raise ValueError(
                    f"assistant_tts_model is required when assistant_mode is '{mode}'"
                )
            if not self.assistant_tts_config:
                raise ValueError(
                    f"assistant_tts_config is required when assistant_mode is '{mode}'"
                )
        elif self.assistant_mode == "realtime":
            if not self.assistant_llm_config:
                raise ValueError(
                    "assistant_llm_config is required when assistant_mode is 'realtime'"
                )
        # Provider/model/STT rules for whichever mode this is. Runs for all three, so a
        # combination that cannot start (e.g. gemini in pipeline mode) is a 422 here
        # instead of a dead job later.
        #
        # `has_tools`: a fresh assistant has no `tool_ids` yet (tools are attached afterwards
        # through /assistant/attach-tools, which re-runs this check), so the built-in end_call
        # tool is the only one that can be present at creation.
        validate_mode_config(
            self.assistant_mode,
            self.assistant_llm_config,
            self.assistant_stt_model,
            has_tools=bool(self.assistant_end_call_enabled),
        )
        if self.assistant_stt_config and not self.assistant_stt_model:
            raise ValueError("`assistant_stt_config` requires `assistant_stt_model`.")
        if self.assistant_end_call_enabled:
            if not self.assistant_end_call_trigger_phrase:
                raise ValueError(
                    "assistant_end_call_trigger_phrase is required when assistant_end_call_enabled is True"
                )
            if not self.assistant_end_call_agent_message:
                raise ValueError(
                    "assistant_end_call_agent_message is required when assistant_end_call_enabled is True"
                )
        return self


# For Assistant update
class UpdateAssistant(BaseModel):
    assistant_name: Optional[str] = Field(None, min_length=1, max_length=100, description="Assistant's name (optional)")
    assistant_description: Optional[str] = Field(None, description="Assistant's description (optional)")
    assistant_prompt: Optional[str] = Field(None, description="Assistant's prompt (optional)")
    assistant_mode: Optional[AssistantMode] = Field(None, description="Runtime mode: pipeline, realtime or cascade. When switching to 'pipeline', any stored realtime llm_config is cleared automatically unless you provide a new one.")
    assistant_llm_config: Optional[AssistantLLMConfig] = Field(None, description="Shared LLM config. In pipeline mode only api_key is used (overrides system OPENAI_API_KEY); in realtime mode provider/model/voice/api_key are supported; in cascade mode provider must be 'openai' and model selects the chat model (e.g. gpt-4.1-mini).")
    assistant_tts_model: Optional[Literal["cartesia", "sarvam", "elevenlabs", "mistral"]] = Field(None, description="TTS Provider. Required when switching to pipeline or cascade mode only if no TTS config is already stored on the assistant.")
    assistant_tts_config: Optional[TTSConfig] = Field(None, description="TTS Configuration object (optional)")
    assistant_stt_model: Optional[Literal["native", "sarvam", "cartesia", "deepgram", "elevenlabs", "openai"]] = Field(None, description="Change the user-transcription source ('sarvam', 'cartesia', 'deepgram', 'elevenlabs', 'openai' or 'native'). Ignored in realtime mode. 'cartesia', 'deepgram', 'elevenlabs', 'openai' and 'native' are mutually exclusive with the wrong mode: 'native' is rejected in cascade, and the plugin providers degrade to native in pipeline. Sending it without assistant_stt_config resets the config to provider defaults.")
    assistant_stt_config: Optional[STTConfig] = Field(None, description="STT configuration object. Must be sent together with assistant_stt_model.")
    assistant_start_instruction: Optional[str] = Field(None, max_length=500, description="Assistant's start instruction (optional)")
    assistant_interaction_config: Optional[UpdateAssistantInteractionConfigSchema] = Field(None, description="Update interaction settings")
    assistant_greeting_audio: Optional[UpdateGreetingAudioSchema] = Field(None, description="Attach/detach a greeting audio asset or toggle it on/off")
    assistant_end_call_enabled: Optional[bool] = Field(None, description="Enable/disable built-in end_call tool")
    assistant_end_call_trigger_phrase: Optional[str] = Field(None, max_length=300, description="Example user phrase that should trigger end_call")
    assistant_end_call_agent_message: Optional[str] = Field(None, max_length=300, description="What assistant should say before ending the call")
    assistant_end_call_url: Optional[str] = Field(None, max_length=200, description="Assistant's end call url (optional)")
    assistant_end_call_webhook: Optional[UpdateEndCallWebhookSchema] = Field(None, description="Change the end-of-call webhook timeout or attempt count. Merged with what is stored, like assistant_interaction_config; send a field as null to fall back to the server default.")

    class Config:
        # Strip whitespace from string fields
        str_strip_whitespace = True
        # Example for API documentation
        json_schema_extra = {
            "example": {
                "assistant_name": "Updated Assistant Name",
                "assistant_interaction_config": {
                    "speaks_first": False,
                    "filler_words": True,
                    "silence_reprompts": False,
                    "background_sound_enabled": False,
                    "thinking_sound_enabled": True,
                },
                "assistant_end_call_enabled": True,
                "assistant_end_call_trigger_phrase": "Okay bye, please end the call.",
                "assistant_end_call_agent_message": "Goodbye, and thank you for speaking with us.",
            }
        }

    @model_validator(mode="before")
    @classmethod
    def inject_tts_type(cls, data: dict):
        """Same injection for updates."""
        reject_retired_mode_key(data)
        if isinstance(data, dict):
            inject_provider_type(data, "assistant_tts_model", "assistant_tts_config")
            inject_stt_config(data)
        return data

    @model_validator(mode="after")
    def validate_update_consistency(self):
        """Validate TTS, STT and LLM config consistency on update."""
        # TTS fields must come in pairs
        if bool(self.assistant_tts_model) != bool(self.assistant_tts_config):
            raise ValueError(
                "Provide both `assistant_tts_model` and `assistant_tts_config` together, or neither."
            )
        # An STT config with no model has no discriminator to resolve against.
        if self.assistant_stt_config and not self.assistant_stt_model:
            raise ValueError("`assistant_stt_config` requires `assistant_stt_model`.")
        # Switching to realtime requires llm_config
        if self.assistant_mode == "realtime" and not self.assistant_llm_config:
            raise ValueError(
                "assistant_llm_config is required when switching to realtime mode."
            )
        # Fires only when this request names the mode. A PATCH that omits it is caught by
        # enforce_stored_mode_constraints() in api/validation/assistant_guard.py, which can
        # see the stored row. Both paths are needed.
        #
        # `has_tools` is left at its default here even when the request enables end_call: this
        # validator cannot see the row's `tool_ids`, and guessing False would reject nothing
        # while guessing True would reject a knob that is legal for a toolless assistant. The
        # stored-row check has the real answer and runs on every PATCH.
        if self.assistant_mode:
            validate_mode_config(
                self.assistant_mode, self.assistant_llm_config, self.assistant_stt_model
            )
        return self
