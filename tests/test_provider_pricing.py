import unittest
from decimal import Decimal

from src.core.pricing import price_model_usage


class TestProviderPricing(unittest.TestCase):
    def test_cached_input_is_a_subset_not_an_additional_charge(self):
        result = price_model_usage(
            [
                {
                    "type": "llm_usage",
                    "provider": "openai",
                    "model": "gpt-4.1-mini",
                    "input_tokens": 1000,
                    "input_text_tokens": 1000,
                    "input_cached_tokens": 400,
                    "input_cached_text_tokens": 400,
                    "output_tokens": 100,
                    "output_text_tokens": 100,
                }
            ]
        )

        expected = Decimal(600) * Decimal("0.40") / 1_000_000
        expected += Decimal(400) * Decimal("0.10") / 1_000_000
        expected += Decimal(100) * Decimal("1.60") / 1_000_000
        self.assertEqual(result.estimated_cost_usd, expected)
        self.assertTrue(result.pricing_complete)

    def test_character_and_duration_rates_are_supported(self):
        result = price_model_usage(
            [
                {
                    "type": "tts_usage",
                    "provider": "elevenlabs",
                    "model": "eleven_v3",
                    "characters_count": 1000,
                },
                {
                    "type": "stt_usage",
                    "provider": "sarvam",
                    "model": "saaras:v3",
                    "audio_duration": 3600,
                },
            ]
        )

        self.assertEqual(len(result.unpriced_model_usage), 0)
        self.assertAlmostEqual(
            float(result.estimated_cost_usd),
            float(Decimal("0.10") + Decimal(30) / Decimal("83.75")),
            places=12,
        )

    def test_unknown_rate_is_partial_not_free(self):
        """A model the table does not carry — here a Cartesia id newer than the pinned one."""
        entry = {
            "type": "tts_usage",
            "provider": "cartesia",
            "model": "sonic-9",
            "characters_count": 100,
        }
        result = price_model_usage([entry])

        self.assertEqual(result.estimated_cost_usd, Decimal(0))
        self.assertFalse(result.pricing_complete)
        self.assertEqual(result.unpriced_model_usage[0]["model"], "sonic-9")
        self.assertFalse(result.model_usage[0]["pricing_complete"])

    def test_realtime_audio_and_text_are_priced_separately(self):
        result = price_model_usage(
            [
                {
                    "type": "llm_usage",
                    "provider": "openai",
                    "model": "gpt-realtime-1.5",
                    "input_audio_tokens": 1_000_000,
                    "input_text_tokens": 1_000_000,
                    "output_audio_tokens": 1_000_000,
                    "output_text_tokens": 1_000_000,
                }
            ]
        )

        self.assertEqual(result.estimated_cost_usd, Decimal(32) + Decimal(4) + Decimal(64) + Decimal(16))


    def test_gemini_live_audio_and_text_are_priced(self):
        """A Gemini realtime call used to come back unpriced — the table had no Gemini at all."""
        result = price_model_usage(
            [
                {
                    "type": "llm_usage",
                    "provider": "gemini",
                    "model": "gemini-3.8-live",
                    "input_audio_tokens": 1_000_000,
                    "input_text_tokens": 1_000_000,
                    "output_audio_tokens": 1_000_000,
                    "output_text_tokens": 1_000_000,
                }
            ]
        )

        self.assertTrue(result.pricing_complete)
        self.assertEqual(
            result.estimated_cost_usd,
            Decimal(3) + Decimal("0.75") + Decimal(12) + Decimal("4.50"),
        )

    def test_every_gemini_live_model_has_a_rate(self):
        """An allowlisted model with no rate silently bills nothing."""
        from src.core.model_support.capabilities import GEMINI_LIVE_MODELS
        from src.core.pricing.rates import get_rate

        for model in GEMINI_LIVE_MODELS:
            with self.subTest(model=model):
                self.assertIsNotNone(get_rate("llm_usage", "gemini", model))


    def test_cartesia_tts_and_stt_are_priced(self):
        """Cartesia publishes no per-unit price; the rate is derived from the Startup tier."""
        result = price_model_usage(
            [
                {
                    "type": "tts_usage",
                    "provider": "cartesia",
                    "model": "sonic-3",
                    "characters_count": 1_250_000,
                },
                {
                    "type": "stt_usage",
                    "provider": "cartesia",
                    "model": "ink-2",
                    "audio_duration": 3600,
                },
            ]
        )

        self.assertTrue(result.pricing_complete)
        # 1.25M credits is one month of the $49 tier, and a TTS credit is one character.
        self.assertEqual(result.model_usage[0]["estimated_cost_usd"], Decimal(49))
        self.assertAlmostEqual(
            float(result.model_usage[1]["estimated_cost_usd"]), 0.4234, places=3
        )

    def test_mistral_tts_is_priced(self):
        result = price_model_usage(
            [
                {
                    "type": "tts_usage",
                    "provider": "mistral",
                    "model": "voxtral-mini-tts-2603",
                    "characters_count": 1000,
                }
            ]
        )

        self.assertTrue(result.pricing_complete)
        self.assertEqual(result.estimated_cost_usd, Decimal("0.016"))

if __name__ == "__main__":
    unittest.main()
