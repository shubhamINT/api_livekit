"""Tests for the inbound SIP call registry.

The registry maps a call to the Event that fires when Exotel sends BYE or CANCEL. Its key used
to be the raw wire Call-ID with overwrite-on-collision, which let one call's teardown signal be
handed to a different call.
"""

import unittest

from src.services.exotel.custom_sip_reach import inbound_listener as il


class TestRegistryKey(unittest.TestCase):
    def setUp(self):
        il._call_registry.clear()

    tearDown = setUp

    def test_key_is_namespaced_by_peer(self):
        """The property that matters is distinctness, not the separator we happen to use."""
        key_a = il.registry_key("abc", "1.2.3.4")
        key_b = il.registry_key("abc", "5.6.7.8")
        self.assertNotEqual(key_a, key_b)
        self.assertNotEqual(key_a, il.registry_key("abc"))

    def test_key_without_peer_is_the_call_id(self):
        """Outbound generates its own UUID Call-ID and registers it unnamespaced; the BYE that
        comes back carries that same value."""
        self.assertEqual(il.registry_key("abc"), "abc")

    def test_missing_call_id_is_rejected(self):
        with self.assertRaises(ValueError):
            il.registry_key(None, "1.2.3.4")

    def test_duplicate_registration_is_refused_not_overwritten(self):
        key, first = il.register_call_id("abc", "1.2.3.4")
        with self.assertRaises(il.DuplicateCallId):
            il.register_call_id("abc", "1.2.3.4")
        # The original call still owns its event.
        self.assertIs(il._call_registry[key], first)

    def test_same_call_id_from_different_peers_coexists(self):
        key_a, evt_a = il.register_call_id("abc", "1.2.3.4")
        key_b, evt_b = il.register_call_id("abc", "5.6.7.8")
        self.assertNotEqual(key_a, key_b)
        self.assertIsNot(evt_a, evt_b)

    def test_unregister_removes_only_its_own_key(self):
        key_a, _ = il.register_call_id("abc", "1.2.3.4")
        key_b, evt_b = il.register_call_id("abc", "5.6.7.8")
        il.unregister_call_id(key_a)
        self.assertNotIn(key_a, il._call_registry)
        self.assertIs(il._call_registry[key_b], evt_b)


class TestEventLookup(unittest.TestCase):
    def setUp(self):
        il._call_registry.clear()

    tearDown = setUp

    def test_exact_peer_match_wins(self):
        _, evt = il.register_call_id("abc", "1.2.3.4")
        self.assertIs(il._lookup_event("abc", "1.2.3.4"), evt)

    def test_falls_back_to_call_id_when_bye_comes_from_another_node(self):
        _, evt = il.register_call_id("abc", "1.2.3.4")
        self.assertIs(il._lookup_event("abc", "9.9.9.9"), evt)

    def test_ambiguous_match_fires_nothing(self):
        """Two live calls share a Call-ID: tearing down a guess is worse than waiting for the
        RTP-silence watchdog."""
        il.register_call_id("abc", "1.2.3.4")
        il.register_call_id("abc", "5.6.7.8")
        self.assertIsNone(il._lookup_event("abc", "9.9.9.9"))

    def test_unknown_call_id_returns_none(self):
        self.assertIsNone(il._lookup_event("nope", "1.2.3.4"))
        self.assertIsNone(il._lookup_event(None, "1.2.3.4"))


if __name__ == "__main__":
    unittest.main()
