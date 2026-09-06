"""Record how much audio the cascade STT stage was fed, when the plugin will not.

Cascade mode puts a real plugin STT on the `AgentSession`, so the SDK's `ModelUsageCollector`
normally records it without help. That works for cartesia, deepgram and elevenlabs, which all
count `frame.duration` themselves. It does not work for Sarvam:

- `plugins/sarvam/stt.py:1574-1587` builds its `RECOGNITION_USAGE` event from
  `metrics.get("audio_duration", 0.0)` — whatever the server put in the transcript payload.
  The field is absent on some responses and the plugin does no local frame accounting at all,
  so the call records a silent zero, indistinguishable from "no transcription ran".
- `plugins/sarvam/stt.py:1568-1571` returns before building the event at all when the
  transcript text is empty, so those turns report nothing whatsoever.

`sarvam_parallel.SttUsage` already rejected that same server field for pipeline mode and
counts the audio itself. This module does the same for cascade, and additionally has to stop
the plugin's own (wrong) number reaching the collector — in pipeline mode the tap runs outside
the `AgentSession` and there is nothing to suppress.

There is no seam between the plugin and the SDK's metrics monitor: `RecognizeStream.__init__`
tees its event channel and starts the monitor task at construction
(`agents/stt/stt.py:384-388`), so anything wrapping the object `stream()` returns sees the
event only after `STTMetrics` has already been built. The seam *after* the monitor is public —
it reports by calling `self._stt.emit("metrics_collected", ...)` (`agents/stt/stt.py:540`), and
`emit` is `rtc.EventEmitter.emit`. Overriding it on a `sarvam.STT` subclass is the whole trick.
"""

from __future__ import annotations

from dataclasses import dataclass

from livekit.agents.metrics import STTMetrics, STTModelUsage
from livekit.plugins import sarvam

from src.core.logger import logger


@dataclass
class CascadeSttUsage:
    """How much audio the session fed the cascade STT stage, for the call's UsageRecord.

    Like the pipeline tap's tally this is stream time, not speech time: `SpeechGate` zeroes
    non-speech samples in place and returns the same frame, so muted audio still reaches the
    STT stage and is still counted. That matches how a continuously open connection is
    metered. It can differ slightly from the seconds Sarvam bills; it is never falsely zero.
    """

    # Empty until create_stt stamps it, which it does only for the provider whose own
    # reporting this tally replaces. Every other cascade provider meters itself.
    provider: str = ""
    model: str = ""
    audio_duration: float = 0.0

    def to_model_usage(self) -> STTModelUsage | None:
        """None while unclaimed, so a cascade call on another provider records no second
        entry beside the one its plugin already reported."""
        if not self.provider:
            return None
        return STTModelUsage(
            provider=self.provider,
            model=self.model,
            audio_duration=self.audio_duration,
        )


class MeteredSarvamSTT(sarvam.STT):
    """`sarvam.STT` whose own STT metrics never reach the AgentSession's collector.

    Dropped rather than zeroed: the collector creates an `stt_usage` entry from the first
    metric it sees, so a zeroed duration would leave a second, all-zero row beside the one
    `CascadeSttUsage` contributes, and `summarize_usage` sums both into `stt_audio_duration`.
    """

    def __init__(self, *args, usage: CascadeSttUsage, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._usage = usage
        self._warned_tokens = False

    @property
    def provider(self) -> str:
        # The stock plugin returns "Sarvam" while the pipeline tap stores "sarvam", and the
        # SDK stamps this straight into the entry's metadata (agents/stt/stt.py:537-539).
        # Pricing keys on (provider, model) and should not need two spellings for one vendor.
        return "sarvam"

    def emit(self, event, *args) -> None:
        """Swallow this stage's STT metrics; pass everything else through.

        Runs on the plugin's websocket read path, so it must never raise — anything
        unexpected falls through to the base implementation. "error" in particular has to
        keep arriving: `agent_activity` subscribes to it, and swallowing it would hide a
        provider outage behind a silent call.
        """
        try:
            if event == "metrics_collected" and args and isinstance(args[0], STTMetrics):
                metrics = args[0]
                if not self._warned_tokens and (metrics.input_tokens or metrics.output_tokens):
                    # Sarvam is duration-billed today. If that changes, the tokens would
                    # vanish here instead of being recorded, so say so once.
                    self._warned_tokens = True
                    logger.warning(
                        "Sarvam STT reported token usage "
                        f"(input={metrics.input_tokens}, output={metrics.output_tokens}); "
                        "MeteredSarvamSTT drops it and records duration only"
                    )
                return
        except Exception as e:  # pragma: no cover - defensive, see docstring
            logger.warning(f"Could not inspect Sarvam STT metrics: {e}")
        super().emit(event, *args)
