"""STT spend the SDK's usage collector does not get, and the wrappers that recover it.

Two providers report transcription usage the collector never sees. The OpenAI Realtime API
drops `usage` off the transcription-completed event, so those numbers are read from the raw
server event stream (src/core/agents/stt/native_usage.py). The cascade Sarvam plugin reports
a duration the server may omit entirely, so the session counts the frames instead and the
plugin's own metrics are suppressed (src/core/agents/stt/cascade_usage.py).
"""

import asyncio
import unittest
from types import SimpleNamespace
from unittest import mock

from livekit.agents import Agent
from livekit.agents.metrics import STTMetrics

from src.core.agents.dynamic_assistant import DynamicAssistant
from src.core.agents.stt.cascade_usage import CascadeSttUsage, MeteredSarvamSTT
from src.core.agents.stt.native_usage import (
    NATIVE_TRANSCRIBE_MODEL,
    MeteredRealtimeModel,
    NativeSttUsage,
)

_COMPLETED = "conversation.item.input_audio_transcription.completed"


def _tokens_event(input_tokens=100, audio=90, text=10, output=12):
    """One transcription-completed frame as OpenAI sends it for a token-billed ASR model."""
    return {
        "type": _COMPLETED,
        "event_id": "event_1",
        "item_id": "item_1",
        "content_index": 0,
        "transcript": "hello",
        "usage": {
            "type": "tokens",
            "input_tokens": input_tokens,
            "input_token_details": {"audio_tokens": audio, "text_tokens": text},
            "output_tokens": output,
            "total_tokens": input_tokens + output,
        },
    }


class TestNativeSttUsage(unittest.TestCase):
    def test_token_billed_events_accumulate_with_the_audio_text_split(self):
        usage = NativeSttUsage(model=NATIVE_TRANSCRIBE_MODEL)
        usage.observe(_tokens_event())
        usage.observe(_tokens_event(input_tokens=50, audio=40, text=10, output=8))

        self.assertEqual(usage.input_tokens, 150)
        self.assertEqual(usage.input_audio_tokens, 130)
        self.assertEqual(usage.input_text_tokens, 20)
        self.assertEqual(usage.output_tokens, 20)
        self.assertEqual(usage.audio_duration, 0.0)

    def test_duration_billed_events_fill_seconds_and_no_tokens(self):
        """whisper-1 is billed by audio length and reports the other usage shape."""
        usage = NativeSttUsage(model="whisper-1")
        usage.observe({"type": _COMPLETED, "usage": {"type": "duration", "seconds": 4.5}})

        self.assertEqual(usage.audio_duration, 4.5)
        self.assertEqual(usage.input_tokens, 0)

    def test_unrelated_events_are_ignored(self):
        usage = NativeSttUsage(model=NATIVE_TRANSCRIBE_MODEL)
        usage.observe({"type": "response.done", "response": {"usage": {"input_tokens": 999}}})
        self.assertIsNone(usage.to_model_usage())

    def test_a_malformed_event_never_raises(self):
        """observe() runs inside the plugin's websocket read loop. An exception there would
        end the call over a metric, so every shape has to be survivable."""
        usage = NativeSttUsage(model=NATIVE_TRANSCRIBE_MODEL)
        for bad in (None, "not a dict", {}, {"type": _COMPLETED}, {"type": _COMPLETED, "usage": None}):
            usage.observe(bad)
        self.assertIsNone(usage.to_model_usage())

    def test_nothing_transcribed_reports_no_entry_at_all(self):
        """A zero row reads like a missing measurement; no row says no ASR ran."""
        self.assertIsNone(NativeSttUsage(model=NATIVE_TRANSCRIBE_MODEL).to_model_usage())

    def test_entry_is_shaped_like_an_sdk_stt_entry(self):
        usage = NativeSttUsage(model=NATIVE_TRANSCRIBE_MODEL)
        usage.observe(_tokens_event())
        entry = usage.to_model_usage()

        self.assertIsNotNone(entry)
        # summarize_usage partitions on this discriminator; a wrong value silently drops it.
        self.assertEqual(entry.type, "stt_usage")
        self.assertEqual(entry.provider, "openai")
        self.assertEqual(entry.model, NATIVE_TRANSCRIBE_MODEL)
        self.assertEqual(entry.input_tokens, 100)
        self.assertEqual(entry.input_audio_tokens, 90)
        self.assertEqual(entry.input_text_tokens, 10)
        self.assertEqual(entry.output_tokens, 12)
        # The split has to survive the dump — model_usage is what pricing reads.
        self.assertEqual(entry.model_dump()["input_audio_tokens"], 90)


class TestMeteredRealtimeModel(unittest.TestCase):
    def test_session_subscribes_the_tally_to_the_raw_event_stream(self):
        """The whole point of the subclass. If this listener is not attached, every realtime
        call silently records zero transcription spend."""
        usage = NativeSttUsage(model=NATIVE_TRANSCRIBE_MODEL)
        model = MeteredRealtimeModel.__new__(MeteredRealtimeModel)
        model._usage = usage
        subscribed = SimpleNamespace(on=mock.Mock())

        with mock.patch.object(
            MeteredRealtimeModel.__bases__[0], "session", return_value=subscribed
        ):
            self.assertIs(model.session(), subscribed)

        subscribed.on.assert_called_once_with("openai_server_event_received", usage.observe)


def _stt_metrics(audio_duration=1.5, input_tokens=0, output_tokens=0):
    """One STTMetrics as the SDK's metrics monitor builds it (agents/stt/stt.py:526-540)."""
    return STTMetrics(
        label="sarvam.STT",
        request_id="req_1",
        timestamp=0.0,
        duration=0.0,
        audio_duration=audio_duration,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        streamed=True,
    )


class TestCascadeSttUsage(unittest.TestCase):
    def test_an_unclaimed_tally_reports_no_entry(self):
        """Every cascade provider except Sarvam meters itself, and its entry is already in
        session.usage — a second, zero one would read like a missing measurement."""
        self.assertIsNone(CascadeSttUsage().to_model_usage())

    def test_a_claimed_tally_is_shaped_like_an_sdk_stt_entry(self):
        entry = CascadeSttUsage(
            provider="sarvam", model="saaras:v3", audio_duration=12.5
        ).to_model_usage()
        self.assertEqual(entry.type, "stt_usage")
        # Lowercase: the plugin says "Sarvam" and the pipeline tap says "sarvam". Pricing
        # keys on (provider, model) and must not need two spellings for one vendor.
        self.assertEqual(entry.provider, "sarvam")
        self.assertEqual(entry.model, "saaras:v3")
        # model_usage is the dict pricing reads, so the number has to survive the dump.
        self.assertEqual(entry.model_dump()["audio_duration"], 12.5)


class TestMeteredSarvamSTT(unittest.TestCase):
    def _stt(self):
        # __new__ + attribute injection: constructing the real plugin wants an API key and
        # a session. Same pattern as TestMeteredRealtimeModel above.
        stt = MeteredSarvamSTT.__new__(MeteredSarvamSTT)
        stt._events = {}
        stt._usage = CascadeSttUsage()
        stt._warned_tokens = False
        return stt

    def test_stt_metrics_never_reach_a_listener(self):
        """The suppression itself. Without it every cascade Sarvam call stores two stt
        entries and double-counts stt_audio_duration."""
        stt = self._stt()
        seen = mock.Mock()
        stt.on("metrics_collected", seen)
        stt.emit("metrics_collected", _stt_metrics())
        seen.assert_not_called()

    def test_other_events_still_arrive(self):
        """agent_activity subscribes to "error"; swallowing it would hide a provider outage
        behind a call that simply goes quiet."""
        stt = self._stt()
        seen = mock.Mock()
        stt.on("error", seen)
        stt.emit("error", "boom")
        seen.assert_called_once_with("boom")

    def test_provider_is_lowercase(self):
        # The SDK stamps this into the entry metadata (agents/stt/stt.py:537-539).
        self.assertEqual(MeteredSarvamSTT.provider.fget(self._stt()), "sarvam")

    def test_dropped_token_usage_is_logged_once(self):
        """Sarvam is duration-billed today. If that changes, the tokens would vanish here —
        so they have to show up in a log rather than silently."""
        stt = self._stt()
        with self.assertLogs("app", level="WARNING") as logs:
            stt.emit("metrics_collected", _stt_metrics(input_tokens=5))
            stt.emit("metrics_collected", _stt_metrics(input_tokens=5))
        self.assertEqual(len(logs.output), 1)
        self.assertIn("token usage", logs.output[0])


class TestCascadeSttNodeTally(unittest.TestCase):
    """DynamicAssistant.stt_node is where the audio is actually counted."""

    def _agent(self, tally):
        return DynamicAssistant(
            room=None, start_instruction="hi", instructions="be nice", stt_usage=tally
        )

    @staticmethod
    def _frames(count, samples=320, sample_rate=16000):
        async def _gen():
            for _ in range(count):
                yield SimpleNamespace(
                    duration=samples / sample_rate, samples_per_channel=samples
                )

        return _gen()

    def _run(self, agent, audio):
        async def _drive():
            # The default node is the SDK's real STT plumbing; a pass-through stands in for
            # it so the test measures the counting and nothing else.
            async def _passthrough(_self, frames, _settings):
                async for frame in frames:
                    yield frame

            with mock.patch.object(Agent.default, "stt_node", _passthrough):
                return [ev async for ev in agent.stt_node(audio, {})]

        return asyncio.run(_drive())

    def test_frames_are_summed_into_the_tally(self):
        tally = CascadeSttUsage()
        events = self._run(self._agent(tally), self._frames(50))  # 50 x 20 ms
        self.assertAlmostEqual(tally.audio_duration, 1.0)
        self.assertEqual(len(events), 50)  # nothing swallowed on the way past

    def test_no_tally_means_the_default_node_runs_untouched(self):
        """pipeline and realtime have no stt= stage and pass no tally."""
        events = self._run(
            DynamicAssistant(room=None, start_instruction="hi", instructions="be nice"),
            self._frames(3),
        )
        self.assertEqual(len(events), 3)


if __name__ == "__main__":
    unittest.main()
