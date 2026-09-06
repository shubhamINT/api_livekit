"""Record what the OpenAI Realtime API's own transcription costs.

Both `realtime` mode and `pipeline` mode with native STT ask the Realtime API to transcribe
the caller (`input_audio_transcription`). OpenAI bills that on the ASR model's pricing, not
the realtime model's, and reports it on every
`conversation.item.input_audio_transcription.completed` event. The plugin's handler
(`plugins/openai/realtime/realtime_model.py`, `_handle_conversion_item_input_audio_transcription_completed`)
keeps the transcript and drops `usage`, so nothing reaches the SDK's `ModelUsageCollector`
and the call stores zero — indistinguishable from "no transcription ran".

The usage is still reachable without touching a private symbol: `RealtimeSession` emits every
raw server frame as `openai_server_event_received`, a documented public event. The plugin
parses events with `.construct()`, which skips validation, so what arrives here is the plain
dict off the wire — no `openai.types` import and nothing to break when a field is added.

Gemini has no equivalent. Its Live API reports no per-transcription usage; input audio is
already inside `prompt_tokens_details`, so it is counted in the LLM numbers.
"""

from __future__ import annotations

from dataclasses import dataclass

from livekit.agents.metrics import STTModelUsage
from livekit.plugins.openai import realtime

from src.core.logger import logger

_TRANSCRIPTION_COMPLETED = "conversation.item.input_audio_transcription.completed"

# The ASR model both OpenAI realtime branches ask for. It lives here so the tally that
# records the spend and the AudioTranscription that incurs it cannot drift apart.
NATIVE_TRANSCRIBE_MODEL = "gpt-4o-mini-transcribe"


class NativeSttModelUsage(STTModelUsage):
    """An `stt_usage` entry that also carries OpenAI's audio/text input split.

    OpenAI bills transcription input audio and input text at different rates and reports both
    in `usage.input_token_details`. `STTModelUsage` has no field for the split, and losing it
    forces pricing to assume one blended rate. Subclassing keeps `type == "stt_usage"`, so
    `summarize_usage` folds this exactly like an entry the SDK produced.
    """

    # Subsets of `input_tokens`, never additional to it.
    input_audio_tokens: int = 0
    input_text_tokens: int = 0


@dataclass
class NativeSttUsage:
    """Running tally of the transcription usage the Realtime API reported.

    `audio_duration` stays zero for the token-billed models this platform uses; it is filled
    only by the duration-billed variant (whisper-1), which OpenAI reports under a different
    usage shape.
    """

    model: str = ""
    input_tokens: int = 0
    input_audio_tokens: int = 0
    input_text_tokens: int = 0
    output_tokens: int = 0
    audio_duration: float = 0.0

    def observe(self, event: dict) -> None:
        """Listener for `openai_server_event_received`.

        Runs inside the plugin's websocket read loop, so it must never raise: an exception
        here would end the call over a metric. Every field is read defensively for the same
        reason — the plugin skips pydantic validation, so nothing guarantees the shape.
        """
        try:
            if not isinstance(event, dict) or event.get("type") != _TRANSCRIPTION_COMPLETED:
                return
            usage = event.get("usage")
            if not isinstance(usage, dict):
                return
            if usage.get("type") == "duration":
                self.audio_duration += usage.get("seconds") or 0.0
                return
            self.input_tokens += usage.get("input_tokens") or 0
            self.output_tokens += usage.get("output_tokens") or 0
            details = usage.get("input_token_details") or {}
            if isinstance(details, dict):
                self.input_audio_tokens += details.get("audio_tokens") or 0
                self.input_text_tokens += details.get("text_tokens") or 0
        except Exception as e:  # pragma: no cover - defensive, see docstring
            logger.warning(f"Could not read realtime transcription usage: {e}")

    def to_model_usage(self) -> NativeSttModelUsage | None:
        """None when nothing was transcribed, so a call that ran no ASR records no entry at
        all rather than a zero row that reads like a missing measurement."""
        if not (self.input_tokens or self.output_tokens or self.audio_duration):
            return None
        return NativeSttModelUsage(
            provider="openai",
            model=self.model,
            input_tokens=self.input_tokens,
            input_audio_tokens=self.input_audio_tokens,
            input_text_tokens=self.input_text_tokens,
            output_tokens=self.output_tokens,
            audio_duration=self.audio_duration,
        )


class MeteredRealtimeModel(realtime.RealtimeModel):
    """`realtime.RealtimeModel` that tallies its own transcription spend into `usage`.

    Overrides the public `session()` — the SDK calls it once per agent activity — purely to
    subscribe to the raw server event stream. Everything else is the plugin's own behaviour.
    """

    def __init__(self, *args, usage: NativeSttUsage, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._usage = usage

    def session(self, *, turn_detection_disabled: bool = False) -> realtime.RealtimeSession:
        sess = super().session(turn_detection_disabled=turn_detection_disabled)
        sess.on("openai_server_event_received", self._usage.observe)
        return sess
