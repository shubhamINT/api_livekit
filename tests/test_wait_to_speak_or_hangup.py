import asyncio
import unittest
from unittest.mock import AsyncMock

from src.core.agents.session import _wait_to_speak_or_hangup
from src.core.agents.session_lifecycle import CallReadinessGate, RecordingManager


class TestWaitToSpeakOrHangup(unittest.IsolatedAsyncioTestCase):
    """Regression: the greeting used to run to completion even after the caller hung up,
    burning up to ~13s (including a live egress-start call) concurrently with teardown
    already tearing the same room/session down. These pin the race against hang-up.
    """

    def _ready_recorder(self) -> RecordingManager:
        fake_lk = AsyncMock()
        fake_lk.start_room_recording = AsyncMock(
            return_value={"success": True, "data": {"s3_url": "https://s3/foo.ogg", "egress_id": "EG_1"}}
        )
        return RecordingManager(fake_lk, room_name="room-1", assistant_id="assistant-1")

    async def test_speaks_once_answered_and_warmed_up(self):
        gate = CallReadinessGate(is_exotel_outbound=True)
        gate.mark_answered()
        should_speak = await _wait_to_speak_or_hangup(
            gate=gate,
            recorder=self._ready_recorder(),
            hangup_event=asyncio.Event(),
            warmup_sec=0.01,
        )
        self.assertTrue(should_speak)

    async def test_skips_speaking_when_never_answered(self):
        gate = CallReadinessGate(is_exotel_outbound=True)  # never marked answered
        should_speak = await _wait_to_speak_or_hangup(
            gate=gate,
            recorder=self._ready_recorder(),
            hangup_event=asyncio.Event(),
            warmup_sec=0.01,
            gate_timeout=0.05,
        )
        self.assertFalse(should_speak)

    async def test_hangup_during_warmup_skips_speaking_instead_of_running_to_completion(self):
        gate = CallReadinessGate(is_exotel_outbound=True)
        gate.mark_answered()
        hangup_event = asyncio.Event()

        async def hangup_shortly():
            await asyncio.sleep(0.01)
            hangup_event.set()

        asyncio.create_task(hangup_shortly())

        # warmup_sec is much longer than the hangup delay — if the wait weren't
        # interruptible this would take the full warmup instead of bailing early.
        should_speak = await _wait_to_speak_or_hangup(
            gate=gate,
            recorder=self._ready_recorder(),
            hangup_event=hangup_event,
            warmup_sec=5.0,
        )
        self.assertFalse(should_speak)

    async def test_hangup_while_waiting_for_answer_skips_speaking(self):
        gate = CallReadinessGate(is_exotel_outbound=True)  # never answered
        hangup_event = asyncio.Event()
        hangup_event.set()  # already hung up before we even start waiting

        should_speak = await _wait_to_speak_or_hangup(
            gate=gate,
            recorder=self._ready_recorder(),
            hangup_event=hangup_event,
            warmup_sec=0.01,
        )
        self.assertFalse(should_speak)


if __name__ == "__main__":
    unittest.main()
