"""The transcription the OpenAI Realtime API bills separately from the realtime model.

The plugin drops `usage` off the transcription-completed event, so these numbers are read
from the raw server event stream instead. See src/core/agents/stt/native_usage.py.
"""

import unittest
from types import SimpleNamespace
from unittest import mock

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


if __name__ == "__main__":
    unittest.main()
