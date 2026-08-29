"""Tests for the inbound ring-until-agent-ready handshake.

The bridge process reports its progress as a sequence of named events on one queue. The parent
rings on `media_ready` and answers on `agent_ready`, so the ordering rules here decide whether a
caller hears ringing or dead air.
"""

import queue as _stdlib_queue
import unittest

from src.services.exotel.custom_sip_reach import inbound_bridge as ib


class FakeProcess:
    def __init__(self, alive: bool = True):
        self._alive = alive

    def is_alive(self) -> bool:
        return self._alive


class FakeEvent:
    def __init__(self, value: bool = False):
        self._value = value

    def set(self) -> None:
        self._value = True

    def is_set(self) -> bool:
        return self._value


def queue_with(*messages) -> _stdlib_queue.Queue:
    q = _stdlib_queue.Queue()
    for message in messages:
        q.put(message)
    return q


class TestWaitForEvent(unittest.IsolatedAsyncioTestCase):
    async def test_returns_true_on_the_wanted_event(self):
        q = queue_with({"event": "media_ready", "port": 41000})
        self.assertTrue(await ib._wait_for_event(q, FakeProcess(), "media_ready", 1.0))

    async def test_skips_past_other_events(self):
        """agent_ready can arrive before the parent starts waiting for it — a fast agent on a
        slow SIP path. Skipping rather than dropping is what makes that safe."""
        q = queue_with({"event": "media_ready"}, {"event": "agent_ready"})
        self.assertTrue(await ib._wait_for_event(q, FakeProcess(), "agent_ready", 1.0))

    async def test_times_out_when_the_event_never_comes(self):
        self.assertFalse(
            await ib._wait_for_event(queue_with(), FakeProcess(), "agent_ready", 0.3)
        )

    async def test_gives_up_when_the_bridge_process_dies(self):
        self.assertFalse(
            await ib._wait_for_event(queue_with(), FakeProcess(alive=False), "media_ready", 5.0)
        )

    async def test_failed_event_ends_the_wait(self):
        q = queue_with({"event": "failed", "error": "livekit refused the token"})
        self.assertFalse(await ib._wait_for_event(q, FakeProcess(), "media_ready", 5.0))

    async def test_cancel_event_ends_the_wait_immediately(self):
        """A caller who hangs up while ringing must not be made to wait out the full deadline,
        and must never be answered."""
        cancelled = FakeEvent(value=True)
        self.assertFalse(
            await ib._wait_for_event(
                queue_with(), FakeProcess(), "agent_ready", 30.0, cancel_event=cancelled
            )
        )


class TestSipResponseBuilder(unittest.TestCase):
    COMMON = {
        "call_id": "abc@1.2.3.4",
        "cseq": "1 INVITE",
        "from_header": "<sip:+15551234567@exotel>;tag=remote",
        "to_header": "<sip:+15559876543@platform>",
        "via_headers": ["SIP/2.0/TCP 1.2.3.4;branch=z9hG4bK1"],
    }

    def test_no_tag_by_default(self):
        out = ib._build_sip_response(status_line="SIP/2.0 100 Trying", **self.COMMON).decode()
        to_line = next(ln for ln in out.split("\r\n") if ln.startswith("To:"))
        self.assertEqual(to_line, "To: <sip:+15559876543@platform>")

    def test_tag_is_appended_when_given(self):
        out = ib._build_sip_response(
            status_line="SIP/2.0 180 Ringing", to_tag="inbound-deadbeef", **self.COMMON
        ).decode()
        self.assertIn("To: <sip:+15559876543@platform>;tag=inbound-deadbeef", out)

    def test_via_headers_are_echoed_in_order(self):
        out = ib._build_sip_response(
            status_line="SIP/2.0 180 Ringing",
            **{**self.COMMON, "via_headers": ["via-one", "via-two"]},
        ).decode()
        self.assertLess(out.index("Via: via-one"), out.index("Via: via-two"))

    def test_ringing_carries_no_reliability_headers(self):
        """A bare 180 only. Require: 100rel or an RSeq would make Exotel send PRACK, and
        nothing in this codebase answers one."""
        out = ib._build_sip_response(
            status_line="SIP/2.0 180 Ringing", to_tag="t", **self.COMMON
        ).decode()
        self.assertNotIn("Require:", out)
        self.assertNotIn("RSeq:", out)


if __name__ == "__main__":
    unittest.main()
