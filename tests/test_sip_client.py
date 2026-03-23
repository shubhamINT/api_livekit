import unittest

from src.services.exotel.custom_sip_reach.sip_client import ExotelSipClient


class TestSipStatusMapping(unittest.TestCase):
    def test_map_call_status_from_sip(self):
        self.assertEqual(ExotelSipClient._map_call_status_from_sip(486), "busy")
        self.assertEqual(ExotelSipClient._map_call_status_from_sip(600), "busy")
        self.assertEqual(ExotelSipClient._map_call_status_from_sip(408), "no_answer")
        self.assertEqual(ExotelSipClient._map_call_status_from_sip(480), "no_answer")
        self.assertEqual(ExotelSipClient._map_call_status_from_sip(603), "rejected")
        self.assertEqual(ExotelSipClient._map_call_status_from_sip(403), "rejected")
        self.assertEqual(ExotelSipClient._map_call_status_from_sip(487), "cancelled")
        self.assertEqual(ExotelSipClient._map_call_status_from_sip(404), "unreachable")
        self.assertEqual(ExotelSipClient._map_call_status_from_sip(410), "unreachable")
        self.assertEqual(ExotelSipClient._map_call_status_from_sip(484), "unreachable")
        self.assertEqual(ExotelSipClient._map_call_status_from_sip(500), "failed")


if __name__ == "__main__":
    unittest.main()
