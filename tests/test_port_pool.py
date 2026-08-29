"""Tests for the RTP port pool.

The pool is the resource that runs out first under load, and until now nothing tested it.
"""

import time
import unittest
from unittest import mock

from src.services.exotel.custom_sip_reach.port_pool import PortPool


class TestPortPool(unittest.TestCase):
    def test_allocates_even_ports_leaving_rtcp_free(self):
        pool = PortPool(41000, 41010)
        ports = {pool.acquire() for _ in range(5)}
        self.assertEqual(ports, {41000, 41002, 41004, 41006, 41008})

    def test_never_hands_out_the_same_port_twice(self):
        pool = PortPool(41000, 41020)
        ports = [pool.acquire() for _ in range(10)]
        self.assertEqual(len(ports), len(set(ports)))

    def test_exhaustion_raises(self):
        pool = PortPool(41000, 41002)
        pool.acquire()
        with self.assertRaises(RuntimeError):
            pool.acquire()

    def test_released_port_is_not_reusable_during_cooldown(self):
        pool = PortPool(41000, 41002)
        port = pool.acquire()
        pool.release(port)
        with self.assertRaises(RuntimeError):
            pool.acquire()

    def test_released_port_returns_after_cooldown(self):
        pool = PortPool(41000, 41002)
        port = pool.acquire()
        pool.release(port)
        later = time.time() + PortPool.COOLDOWN_SECONDS + 1
        with mock.patch("src.services.exotel.custom_sip_reach.port_pool.time.time",
                        return_value=later):
            self.assertEqual(pool.acquire(), port)

    def test_allocation_rotates_instead_of_reusing_the_lowest_port(self):
        """Lowest-first allocation meant the same few ports churned constantly, which is what
        let a just-ended call's RTP land on a socket rebound to a new call."""
        pool = PortPool(41000, 41010)
        first = pool.acquire()
        pool.release(first)
        second = pool.acquire()
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
