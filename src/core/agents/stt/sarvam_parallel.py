from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from livekit import rtc
from livekit.agents import stt as stt_pkg
from livekit.agents.metrics import STTModelUsage
from livekit.plugins import sarvam as sarvam_plugin

from src.core.agents.audio_denoise import SpeechGate
from src.core.agents.stt.lang import validate_sarvam_language, validate_sarvam_mode
from src.core.config import settings
from src.core.logger import logger

# ponytail: debounce, not turn detection. SpeechGate zeroes non-speech after a 600 ms
# hangover (audio_denoise._HANGOVER_MS), so Sarvam's server VAD endpoints on any longer
# intra-sentence pause and returns one FINAL_TRANSCRIPT per fragment. Rejoining on a quiet
# window puts the sentence back together; a pause longer than the window still splits.
# Raise this, or drive flush() from more turn events, if callers report split lines.
MERGE_WINDOW_S = 1.0

# Silence fed to Sarvam once the caller's audio stops, so the last utterance comes back.
# Sarvam only returns a segment after its server VAD endpoints, and the plugin forwards the
# resulting flush from inside its send loop — i.e. only when the *next* frame arrives
# (plugins/sarvam/stt.py:1074). At hangup the frames stop, so that flush is never sent and the
# segment stays stuck server-side. end_input() cannot rescue it either: the plugin sends
# end_of_stream and cancels its own reader in the same event-loop turn (stt.py:1064, 957-973),
# discarding the reply. Silence endpoints the segment, carries the pending flush, and pushes
# the sub-chunk tail over the plugin's 50 ms boundary. Same trick the SDK uses on its own STT
# (agents/voice/audio_recognition.py::commit_user_turn).
DRAIN_SILENCE_S = 2.0
# 20 ms of digital silence at 16 kHz mono int16. Reused — the plugin only reads it.
_SILENCE_FRAME = rtc.AudioFrame(
    b"\x00" * 640, sample_rate=16000, num_channels=1, samples_per_channel=320
)


@dataclass
class SttUsage:
    """How much audio this tap fed to Sarvam, for the call's UsageRecord.

    Measured here rather than taken from Sarvam's own RECOGNITION_USAGE event. That event
    carries whatever the server put in `metrics.audio_duration`, which is absent on some
    responses and would then record a silent zero — indistinguishable from "no transcription
    ran", which is the exact failure this accounting exists to remove. The number can differ
    slightly from the seconds Sarvam bills; it is never falsely zero.

    This is the audio the tap sent, which includes frames SpeechGate muted — it zeroes
    samples, not frames, and the zeros still go over the open connection. The one thing
    left out is the DRAIN_SILENCE_S burst at hangup, which is fed from `_stop_watch` rather
    than from the pump.
    """

    model: str = ""
    audio_duration: float = 0.0

    def to_model_usage(self) -> STTModelUsage:
        """Shape the tally like an entry the SDK's own collector would have produced, so
        `summarize_usage` folds it with no per-mode special case."""
        return STTModelUsage(
            provider="sarvam",
            model=self.model or "saaras:v3",
            audio_duration=self.audio_duration,
        )


class FinalCoalescer:
    """Joins Sarvam's per-fragment finals back into whole utterances.

    Emits ``(text, started_at)`` where ``started_at`` is when the first fragment of the
    group arrived, not when the group was emitted. The caller stores that as the
    transcript timestamp, so a user turn that took a network round-trip to transcribe
    still sorts above the agent reply it triggered.
    """

    def __init__(
        self,
        emit: Callable[[str, datetime], None],
        window: float = MERGE_WINDOW_S,
    ) -> None:
        self._emit = emit
        self._window = window
        self._parts: list[str] = []
        self._started_at: datetime | None = None
        self._task: asyncio.Task | None = None

    def add(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        if self._started_at is None:
            self._started_at = datetime.now(timezone.utc)
        self._parts.append(text)
        if self._task is not None:
            self._task.cancel()
        self._task = asyncio.create_task(self._flush_after_window())

    async def _flush_after_window(self) -> None:
        try:
            await asyncio.sleep(self._window)
        except asyncio.CancelledError:
            return
        self._task = None
        self.flush()

    def flush(self) -> None:
        """Emit whatever is buffered right now — the agent started speaking, or the call is ending."""
        if self._task is not None:
            self._task.cancel()
            self._task = None
        if not self._parts:
            return
        text, started_at = " ".join(self._parts), self._started_at
        self._parts = []
        self._started_at = None
        try:
            self._emit(text, started_at or datetime.now(timezone.utc))
        except Exception as e:
            logger.error(f"[SARVAM-STT] emit callback error: {e}")


async def run_sarvam_parallel_stt(
    *,
    room: rtc.Room,
    target_identity: str,
    coalescer: FinalCoalescer,
    stop_event: asyncio.Event,
    usage: SttUsage,
    api_key: str | None = None,
    model: str | None = None,
    language: str | None = None,
    mode: str | None = None,
    assistant_id: str = "unknown",
) -> None:
    """Stream caller audio into Sarvam Saras v3 and feed finalized utterances to `coalescer`.

    Runs alongside OpenAI Realtime — does not touch the LLM audio pipeline.
    On `stop_event` it feeds Sarvam silence so it finalizes its buffered audio rather than
    dropping it, so the caller's last sentence survives a hangup.
    """
    sarvam_model = model or "saaras:v3"
    usage.model = sarvam_model
    sarvam_stt = sarvam_plugin.STT(
        model=sarvam_model,
        # Same field, same meaning as in cascade (see src/core/agents/stt/factory.py) —
        # "codemix" stays the default because callers here routinely mix English with an
        # Indian language mid-sentence.
        mode=validate_sarvam_mode(sarvam_model, mode or "codemix", assistant_id=assistant_id),
        # Validated, not passed through: the plugin RAISES on a code its model does not
        # speak, which would take down the tap for the whole call. The accepted set is per
        # model. An empty string is reachable from the API too — the schema
        # sets no min_length — and the plugin reads it as en-IN rather than auto-detect.
        language=validate_sarvam_language(sarvam_model, language, assistant_id=assistant_id),
        # Never assistant_tts_config["api_key"] — that key belongs to the selected TTS
        # provider (cartesia/elevenlabs/mistral) and Sarvam rejects it with a 403.
        api_key=api_key or settings.SARVAM_API_KEY,
        sample_rate=16000,
    )
    stream = sarvam_stt.stream()
    pump_task: asyncio.Task | None = None

    async def _pump(track: rtc.Track) -> None:
        # This tap opens its own AudioStream, so it does not inherit the SpeechGate that
        # RoomIO applies to the LLM's input — it needs its own instance (the APM and VAD
        # are both stateful per stream). Gating here also keeps Sarvam from transcribing
        # noise, which is what produced the hallucinated scripts described in
        # docs/architecture/audio-pipeline.md.
        audio = rtc.AudioStream(
            track, sample_rate=16000, num_channels=1, noise_cancellation=SpeechGate()
        )
        try:
            async for ev in audio:
                stream.push_frame(ev.frame)
                # Every frame, gated or not. SpeechGate zeroes non-speech samples in place
                # and returns the same frame, so gated audio is still sent to Sarvam over
                # an open connection — which is what Sarvam meters.
                usage.audio_duration += ev.frame.duration
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[SARVAM-STT] Audio pump error: {e}", exc_info=True)

    def _on_track(track, _pub, participant) -> None:
        nonlocal pump_task
        if participant.identity != target_identity:
            return
        if track.kind != rtc.TrackKind.KIND_AUDIO:
            return
        if pump_task and not pump_task.done():
            return
        logger.info(f"[SARVAM-STT] Attaching to {participant.identity} audio track")
        pump_task = asyncio.create_task(_pump(track))

    # Late-bind if track already exists
    for p in room.remote_participants.values():
        for pub in p.track_publications.values():
            if pub.track:
                _on_track(pub.track, pub, p)

    room.on("track_subscribed", _on_track)

    async def _stop_watch() -> None:
        await stop_event.wait()
        if pump_task and not pump_task.done():
            pump_task.cancel()
            # Awaited, so no real frame can land after the silence below.
            with contextlib.suppress(asyncio.CancelledError):
                await pump_task
        # Feed silence so Sarvam endpoints and returns the caller's last utterance — see
        # DRAIN_SILENCE_S. It arrives through the normal event path, which the teardown
        # grace in session.py is still open for.
        with contextlib.suppress(Exception):
            for _ in range(int(DRAIN_SILENCE_S / _SILENCE_FRAME.duration)):
                stream.push_frame(_SILENCE_FRAME)
        # Only now close the input: this makes the plugin tear the connection down, so
        # anything Sarvam has not already sent back is lost.
        with contextlib.suppress(Exception):
            stream.end_input()

    stop_task = asyncio.create_task(_stop_watch())

    try:
        async for ev in stream:
            if ev.type == stt_pkg.SpeechEventType.FINAL_TRANSCRIPT:
                coalescer.add(ev.alternatives[0].text if ev.alternatives else "")
    except asyncio.CancelledError:
        # By the time anything cancels us the silence drain has already run, so this only
        # means the plugin's WebSocket close handshake outlived the call. The finally below
        # still flushes whatever came back.
        logger.info("[SARVAM-STT] Cancelled while closing the stream")
    except Exception as e:
        logger.error(f"[SARVAM-STT] Stream error: {e}", exc_info=True)
    finally:
        # Sync first: this must land even if the task is being cancelled out from under us.
        coalescer.flush()
        room.off("track_subscribed", _on_track)
        stop_task.cancel()
        if pump_task:
            pump_task.cancel()
        await asyncio.gather(
            *(t for t in (pump_task, stop_task) if t), return_exceptions=True
        )
        try:
            await stream.aclose()
        except Exception as e:
            logger.debug(f"[SARVAM-STT] aclose error: {e}")
        logger.info("[SARVAM-STT] Parallel STT stopped")
