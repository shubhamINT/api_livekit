"""Tests for the RTP socket's source filter.

RTP used to be accepted from any source until an endpoint was known, and the first sender was
then adopted as the peer. Combined with fast port reuse, that let audio from a call that had
just ended be picked up as a new call's peer — one caller hearing another.
"""

import unittest
from unittest import mock

from src.services.exotel.custom_sip_reach.rtp_bridge import RTPMediaBridge

PEER = ("203.0.113.10", 40000)
STRANGER = ("198.51.100.7", 40000)
RTP_PACKET = b"\x80\x08\x00\x01" + b"\x00" * 8 + b"\xd5" * 160


def _bridge():
    """Build a bridge without binding a real socket. Needs a running loop: the bridge builds an
    rtc.AudioMixer in __init__, which starts a task."""
    with mock.patch("src.services.exotel.custom_sip_reach.rtp_bridge.socket.socket") as sock_cls:
        sock = sock_cls.return_value
        sock.getsockname.return_value = ("0.0.0.0", 41000)
        return RTPMediaBridge(public_ip="203.0.113.1", bind_port=41000)


class TestRTPSourceFilter(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bridge = _bridge()
        self.addCleanup(self.bridge.stop)

    async def test_packets_are_dropped_before_an_endpoint_is_negotiated(self):
        bridge = self.bridge
        bridge._sock.recvfrom.return_value = (RTP_PACKET, STRANGER)
        bridge._on_rtp_readable()
        self.assertTrue(bridge._recv_queue.empty())

    async def test_stranger_never_becomes_the_peer(self):
        bridge = self.bridge
        bridge._sock.recvfrom.return_value = (RTP_PACKET, STRANGER)
        bridge._on_rtp_readable()
        self.assertIsNone(bridge._remote_addr)

    async def test_negotiated_peer_is_accepted(self):
        bridge = self.bridge
        bridge.set_remote_endpoint(PEER[0], PEER[1])
        bridge._sock.recvfrom.return_value = (RTP_PACKET, PEER)
        bridge._on_rtp_readable()
        self.assertEqual(bridge._recv_queue.qsize(), 1)

    async def test_stale_flow_from_a_previous_call_is_dropped(self):
        bridge = self.bridge
        bridge.set_remote_endpoint(PEER[0], PEER[1])
        bridge._sock.recvfrom.return_value = (RTP_PACKET, STRANGER)
        bridge._on_rtp_readable()
        self.assertTrue(bridge._recv_queue.empty())

    async def test_same_host_different_port_is_dropped(self):
        """Exotel media comes from one host; the port is what distinguishes one call's flow
        from another's."""
        bridge = self.bridge
        bridge.set_remote_endpoint(PEER[0], PEER[1])
        bridge._sock.recvfrom.return_value = (RTP_PACKET, (PEER[0], PEER[1] + 2))
        bridge._on_rtp_readable()
        self.assertTrue(bridge._recv_queue.empty())


if __name__ == "__main__":
    unittest.main()
