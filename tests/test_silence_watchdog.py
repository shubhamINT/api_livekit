"""The silence watchdog must end the call through the owner's teardown, not on its own.

It used to call AgentSession.shutdown(), which skipped the transcript flush, the usage record,
call_end_reason, the end-call webhook, the egress stop and delete_room.
"""

import asyncio
import logging
import unittest

from src.core.agents.voice_features import SilenceWatchdogController


class FakeSession:
    """The exhaust path must not touch the session at all."""

    def __init__(self) -> None:
        self.shutdown_calls = 0

    def shutdown(self) -> None:
        self.shutdown_calls += 1


class SilenceWatchdogTeardownTests(unittest.IsolatedAsyncioTestCase):
    async def test_teardown_survives_the_watchdog_task_being_cancelled(self):
        # participant_disconnected calls stop() the moment teardown deletes the room, so the
        # teardown must not be running on the watchdog's own task.
        entered = asyncio.Event()
        finished = asyncio.Event()

        async def fake_teardown() -> None:
            entered.set()
            await asyncio.sleep(0.05)
            finished.set()

        session = FakeSession()
        watchdog = SilenceWatchdogController(
            session=session,
            logger=logging.getLogger("test-silence"),
            on_silence_exhausted=fake_teardown,
            reprompt_interval_sec=0.01,
            max_reprompts=1,
        )

        watchdog.start()
        await asyncio.wait_for(entered.wait(), timeout=1.0)
        watchdog.stop()
        await asyncio.wait_for(finished.wait(), timeout=1.0)

        self.assertEqual(session.shutdown_calls, 0)


if __name__ == "__main__":
    unittest.main()
