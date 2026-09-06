import asyncio
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest import mock

from livekit import rtc
from livekit.agents import stt as stt_pkg

from src.core.agents.stt.sarvam_parallel import (
    DRAIN_SILENCE_S,
    FinalCoalescer,
    SttUsage,
    run_sarvam_parallel_stt,
)


class TestFinalCoalescer(unittest.IsolatedAsyncioTestCase):
    """Sarvam endpoints on any pause longer than SpeechGate's 600 ms hangover, so one
    sentence arrives as several finals. The coalescer rejoins them into one transcript row.
    """

    def setUp(self) -> None:
        self.emitted: list[tuple[str, object]] = []

    def _make(self, window: float = 0.05) -> FinalCoalescer:
        return FinalCoalescer(lambda text, ts: self.emitted.append((text, ts)), window=window)

    async def test_fragments_inside_window_join_into_one_utterance(self):
        c = self._make()
        c.add("I want to")
        await asyncio.sleep(0.02)
        c.add("book a ticket")

        await asyncio.sleep(0.15)
        self.assertEqual([t for t, _ in self.emitted], ["I want to book a ticket"])

    async def test_timestamp_is_first_fragment_not_emission(self):
        c = self._make(window=0.2)
        before_first = datetime.now(timezone.utc)
        c.add("I want to")
        await asyncio.sleep(0.1)
        after_second = datetime.now(timezone.utc)
        c.add("book a ticket")

        await asyncio.sleep(0.4)
        (_, ts), = self.emitted
        # Stamped when the caller started talking, not when the merged row was emitted —
        # that is what keeps the utterance above the agent reply it triggered.
        self.assertGreaterEqual(ts, before_first)
        self.assertLess(ts, after_second)

    async def test_gap_longer_than_window_splits_utterances(self):
        c = self._make()
        c.add("first")
        await asyncio.sleep(0.15)
        c.add("second")
        await asyncio.sleep(0.15)

        self.assertEqual([t for t, _ in self.emitted], ["first", "second"])

    async def test_flush_emits_immediately_without_waiting_out_window(self):
        c = self._make(window=10.0)
        c.add("last thing I said")

        c.flush()
        self.assertEqual([t for t, _ in self.emitted], ["last thing I said"])

    async def test_flush_on_empty_buffer_is_a_noop(self):
        c = self._make()
        c.flush()
        c.flush()
        self.assertEqual(self.emitted, [])

    async def test_blank_fragments_are_ignored(self):
        c = self._make()
        c.add("   ")
        c.add("")
        c.flush()
        self.assertEqual(self.emitted, [])

    async def test_emit_failure_does_not_break_the_next_utterance(self):
        def boom(text, ts):
            raise RuntimeError("db down")

        c = FinalCoalescer(boom, window=0.05)
        c.add("dropped")
        c.flush()  # must not raise — a failed write cannot kill the STT tap

        self.emitted.clear()
        c._emit = lambda text, ts: self.emitted.append((text, ts))
        c.add("kept")
        c.flush()
        self.assertEqual([t for t, _ in self.emitted], ["kept"])


class _FakeStream:
    """Stands in for the Sarvam plugin stream, with its endpointing behaviour.

    It answers only once enough audio has arrived to endpoint the segment, and goes deaf the
    moment `end_input()` is called — which is what the real plugin does, since it cancels its
    own reader in the same turn it sends `end_of_stream`.
    """

    def __init__(self, frames_needed: int) -> None:
        self.frames = 0
        self.frames_needed = frames_needed
        self.frames_at_end_input: int | None = None
        self._answered = False
        self._closed = asyncio.Event()

    def push_frame(self, frame) -> None:
        self.frames += 1

    def end_input(self) -> None:
        self.frames_at_end_input = self.frames
        self._closed.set()

    async def aclose(self) -> None:
        pass

    def __aiter__(self):
        return self

    async def __anext__(self):
        # end_input() is the last step of the drain, so by the time it fires the tap has
        # pushed everything it is going to push.
        await self._closed.wait()
        if not self._answered and self.frames >= self.frames_needed:
            self._answered = True
            return stt_pkg.SpeechEvent(
                type=stt_pkg.SpeechEventType.FINAL_TRANSCRIPT,
                alternatives=[stt_pkg.SpeechData(language="", text="the last thing I said")],
            )
        raise StopAsyncIteration


class _FakeRoom:
    def __init__(self, with_caller_track: bool = False) -> None:
        self.remote_participants: dict = {}
        if with_caller_track:
            track = SimpleNamespace(kind=rtc.TrackKind.KIND_AUDIO)
            self.remote_participants["caller"] = SimpleNamespace(
                identity="caller",
                track_publications={"pub": SimpleNamespace(track=track)},
            )

    def on(self, *args) -> None:
        pass

    def off(self, *args) -> None:
        pass


class TestSarvamDrain(unittest.IsolatedAsyncioTestCase):
    """A caller who hangs up mid-sentence leaves no trailing audio, so Sarvam never endpoints
    and never returns the last utterance. The tap feeds it silence on stop to force it out.
    """

    async def test_stop_feeds_silence_and_gets_the_last_utterance(self):
        emitted: list[str] = []
        coalescer = FinalCoalescer(lambda text, ts: emitted.append(text), window=0.01)
        stop = asyncio.Event()
        usage = SttUsage()
        # One frame short of the silence burst, so only the drain can satisfy it.
        stream = _FakeStream(frames_needed=int(DRAIN_SILENCE_S / 0.02))

        with mock.patch(
            "src.core.agents.stt.sarvam_parallel.sarvam_plugin.STT",
            return_value=SimpleNamespace(stream=lambda: stream),
        ):
            task = asyncio.create_task(
                run_sarvam_parallel_stt(
                    room=_FakeRoom(),
                    target_identity="caller",
                    coalescer=coalescer,
                    stop_event=stop,
                    usage=usage,
                    api_key="test",
                )
            )
            await asyncio.sleep(0)
            stop.set()
            await asyncio.wait_for(task, timeout=2.0)

        self.assertEqual(emitted, ["the last thing I said"])
        # Silence must go in *before* the input closes — reversed, the real plugin discards
        # the reply and the utterance is lost.
        self.assertEqual(stream.frames_at_end_input, stream.frames_needed)
        # Nobody spoke — this room has no participant to pump. The drain silence went into
        # the stream but must not be billed as transcribed audio.
        self.assertEqual(usage.audio_duration, 0.0)
        self.assertEqual(usage.model, "saaras:v3")


class TestSarvamUsageTally(unittest.IsolatedAsyncioTestCase):
    """Pipeline mode pays Sarvam per second of caller audio, and the tap is the only place
    that knows how many seconds went in — its plugin STT never reaches the AgentSession's
    usage collector.
    """

    async def test_pumped_audio_is_measured_and_shaped_like_an_sdk_entry(self):
        stop = asyncio.Event()
        usage = SttUsage()
        stream = _FakeStream(frames_needed=0)
        frame = rtc.AudioFrame(
            b"\x00" * 640, sample_rate=16000, num_channels=1, samples_per_channel=320
        )

        async def _frames():
            for _ in range(50):  # 50 x 20 ms = 1.0 s
                yield SimpleNamespace(frame=frame)

        with (
            mock.patch(
                "src.core.agents.stt.sarvam_parallel.sarvam_plugin.STT",
                return_value=SimpleNamespace(stream=lambda: stream),
            ),
            mock.patch(
                "src.core.agents.stt.sarvam_parallel.rtc.AudioStream",
                return_value=_frames(),
            ),
        ):
            task = asyncio.create_task(
                run_sarvam_parallel_stt(
                    room=_FakeRoom(with_caller_track=True),
                    target_identity="caller",
                    coalescer=FinalCoalescer(lambda text, ts: None, window=0.01),
                    stop_event=stop,
                    usage=usage,
                    model="saaras:v4",
                    api_key="test",
                )
            )
            # Let the pump drain its 50 frames before the stop drain adds silence.
            for _ in range(10):
                await asyncio.sleep(0)
            stop.set()
            await asyncio.wait_for(task, timeout=2.0)

        self.assertAlmostEqual(usage.audio_duration, 1.0, places=3)

        entry = usage.to_model_usage()
        self.assertEqual(entry.type, "stt_usage")
        self.assertEqual(entry.provider, "sarvam")
        self.assertEqual(entry.model, "saaras:v4")
        self.assertAlmostEqual(entry.audio_duration, 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
