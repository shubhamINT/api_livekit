"""Tests for the per-call-type concurrency caps.

One shared counter used to govern four workloads of very different cost, so a burst of web
sessions could give phone callers a busy tone. These check that the buckets are independent and
that the global ceiling still binds across them.
"""

import unittest
from unittest import mock

from src.services.outbound_dispatcher import dispatcher as d


class TestBucketDerivation(unittest.TestCase):
    def test_web_calls_are_their_own_bucket(self):
        self.assertEqual(d.bucket_for_call_type("web"), d.WEB)

    def test_phone_calls_are_telephony(self):
        self.assertEqual(d.bucket_for_call_type("inbound"), d.TELEPHONY)
        self.assertEqual(d.bucket_for_call_type("outbound"), d.TELEPHONY)

    def test_unknown_and_missing_call_types_default_to_telephony(self):
        """Legacy rows predate call_type. Counting them as the scarcer resource is the safe
        direction to be wrong in."""
        self.assertEqual(d.bucket_for_call_type(None), d.TELEPHONY)
        self.assertEqual(d.bucket_for_call_type("something-new"), d.TELEPHONY)


class TestReserveAndRelease(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self._saved = dict(d._dispatching_count)
        for bucket in d.BUCKETS:
            d._dispatching_count[bucket] = 0

    def tearDown(self):
        d._dispatching_count.update(self._saved)

    def _with_live(self, counts):
        """Patch the live-session counts, leaving the in-memory reservations real."""
        async def fake():
            return {b: counts.get(b, 0) + d._dispatching_count[b] for b in d.BUCKETS}
        return mock.patch.object(d, "_get_active_session_counts", fake)

    async def test_reserves_when_free(self):
        with self._with_live({}):
            self.assertTrue(await d.try_reserve_slot(d.TELEPHONY))
        self.assertEqual(d._dispatching_count[d.TELEPHONY], 1)

    async def test_release_returns_the_slot(self):
        with self._with_live({}):
            await d.try_reserve_slot(d.WEB)
        d.release_slot(d.WEB)
        self.assertEqual(d._dispatching_count[d.WEB], 0)

    async def test_release_never_goes_negative(self):
        d.release_slot(d.WEB)
        self.assertEqual(d._dispatching_count[d.WEB], 0)

    async def test_full_telephony_does_not_block_web(self):
        """The whole point: phone calls at capacity must not stop web calls."""
        with self._with_live({d.TELEPHONY: d.settings.MAX_CONCURRENT_JOBS}):
            self.assertFalse(await d.try_reserve_slot(d.TELEPHONY))
            self.assertTrue(await d.try_reserve_slot(d.WEB))

    async def test_full_web_does_not_block_telephony(self):
        with self._with_live({d.WEB: d.settings.MAX_CONCURRENT_WEB_CALLS}):
            self.assertFalse(await d.try_reserve_slot(d.WEB))
            self.assertTrue(await d.try_reserve_slot(d.TELEPHONY))

    async def test_global_ceiling_binds_before_a_bucket_cap(self):
        """Both buckets have room, but the agent host does not."""
        with mock.patch.object(d.settings, "MAX_CONCURRENT_SESSIONS", 5):
            with self._with_live({d.TELEPHONY: 3, d.WEB: 2}):
                self.assertFalse(await d.try_reserve_slot(d.TELEPHONY))
                self.assertFalse(await d.try_reserve_slot(d.WEB))

    async def test_reservation_counts_towards_the_cap(self):
        """The reservation is what closes the window between the cap check and the CallRecord
        write; without it a burst all passes the same pre-burst count."""
        with mock.patch.object(d.settings, "MAX_CONCURRENT_JOBS", 2):
            with self._with_live({}):
                self.assertTrue(await d.try_reserve_slot(d.TELEPHONY))
                self.assertTrue(await d.try_reserve_slot(d.TELEPHONY))
                self.assertFalse(await d.try_reserve_slot(d.TELEPHONY))


if __name__ == "__main__":
    unittest.main()
