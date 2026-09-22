"""Which realtime models take the GA-only session fields.

`session.truncation` (retention_ratio + token_limits) belongs to the GA Realtime API. The
older gpt-4o-*realtime-preview models are still on the allowlist, and an unknown session
field is answered with an error event rather than ignored — the same shape of failure as
sending a cascade LLM a knob its model cannot read.
"""

import unittest
from types import SimpleNamespace

from src.api.models.api_schemas.config.llm_config import (
    OPENAI_REALTIME_MODELS,
    validate_mode_config,
)
from src.core.model_support.capabilities import (
    DEFAULT_GEMINI_LIVE_MODEL,
    DEFAULT_GEMINI_VOICE,
    GEMINI_LIVE_MODELS,
    GEMINI_VERTEX_ONLY_MODELS,
    GEMINI_VOICES,
    REALTIME_TRUNCATION_MODELS,
    realtime_supports_truncation,
)


class TestGeminiUserTranscription(unittest.TestCase):
    """Gemini realtime writes user transcripts because the plugin defaults them on.

    session.py deliberately passes no `input_audio_transcription` for Gemini — the plugin
    substitutes `AudioTranscriptionConfig()` when the argument is omitted, and passing None
    explicitly is what would turn transcripts off. This test exists because that is a plugin
    default we depend on, not a value we set: call records and the end-call webhook lose
    every user turn if a plugin bump flips it.
    """

    def test_the_plugin_enables_user_transcription_by_default(self):
        from livekit.plugins.google.beta import realtime as google_realtime

        model = google_realtime.RealtimeModel(
            model="gemini-3.1-flash-live-preview",
            voice="Puck",
            modalities=["AUDIO"],
            instructions="x",
            api_key="k",
        )
        self.assertIsNotNone(model._opts.input_audio_transcription)
        self.assertTrue(model.capabilities.user_transcription)


class TestRealtimeTruncationSupport(unittest.TestCase):
    def test_the_ga_line_takes_truncation(self):
        for model in ("gpt-realtime", "gpt-realtime-1.5", "gpt-realtime-mini"):
            with self.subTest(model=model):
                self.assertTrue(realtime_supports_truncation(model))

    def test_the_preview_line_does_not(self):
        for model in ("gpt-4o-realtime-preview", "gpt-4o-mini-realtime-preview"):
            with self.subTest(model=model):
                self.assertFalse(realtime_supports_truncation(model))

    def test_an_unknown_model_is_treated_as_unsupported(self):
        """Omitting an optional field is safe; sending one the session lacks is not."""
        self.assertFalse(realtime_supports_truncation("gpt-realtime-2027-whatever"))

    def test_every_truncation_model_is_actually_allowlisted(self):
        """A truncation model the API rejects is dead code that reads like coverage.

        It happened: `gpt-realtime-2` and `gpt-realtime-2025-08-28` were listed as
        truncation-capable while `OPENAI_REALTIME_MODELS` refused both, so neither entry could
        ever be reached. The sets are now derived from one another, and this asserts it.
        """
        self.assertEqual(REALTIME_TRUNCATION_MODELS - OPENAI_REALTIME_MODELS, set())


class TestGeminiLiveModelRules(unittest.TestCase):
    """Gemini has no /v1/models to ask, so the plugin's own Literal is the only gate."""

    def test_the_allowlist_accounts_for_every_model_the_plugin_lists(self):
        """A model outside the plugin's Literal opens a socket the API then closes.

        Every id the plugin knows is either runnable here or named as Vertex-only; an id the
        plugin adds later belongs to neither set, and this fails until someone places it.
        """
        from livekit.plugins.google.realtime.api_proto import LiveAPIModels
        from typing import get_args

        self.assertEqual(
            GEMINI_LIVE_MODELS | GEMINI_VERTEX_ONLY_MODELS, set(get_args(LiveAPIModels))
        )
        self.assertEqual(GEMINI_LIVE_MODELS & GEMINI_VERTEX_ONLY_MODELS, set())

    def test_the_voice_roster_matches_the_installed_plugin(self):
        from livekit.plugins.google.realtime.api_proto import Voice
        from typing import get_args

        self.assertEqual(GEMINI_VOICES, set(get_args(Voice)))

    def test_the_default_live_model_is_allowlisted(self):
        """The default has to be the model where every feature works, not the newest one."""
        self.assertIn(DEFAULT_GEMINI_LIVE_MODEL, GEMINI_LIVE_MODELS)

    def test_the_default_voice_is_on_the_roster(self):
        self.assertIn(DEFAULT_GEMINI_VOICE, GEMINI_VOICES)

    def test_both_gemini_3_8_models_are_accepted_in_realtime_mode(self):
        """3.8 is the line Google recommends for voice agents, and the new default."""
        for model in ("gemini-3.8-live", "gemini-3.8-live-extended-thinking"):
            with self.subTest(model=model):
                validate_mode_config(
                    "realtime",
                    SimpleNamespace(provider="gemini", model=model, voice="Puck"),
                    None,
                )

    def test_a_gemini_3_8_model_is_rejected_outside_realtime_mode(self):
        """Pipeline and cascade drive OpenAI, so a Live id is refused as an OpenAI model.

        `provider="openai"` is what those two modes resolve to, including when the field is
        omitted — the point is that the id cannot reach a session, not which branch says so.
        """
        for mode in ("pipeline", "cascade"):
            for model in ("gemini-3.8-live", "gemini-3.8-live-extended-thinking"):
                with self.subTest(mode=mode, model=model), self.assertRaises(ValueError):
                    validate_mode_config(
                        mode,
                        SimpleNamespace(provider="openai", model=model, voice=None),
                        None,
                    )

    def test_the_default_live_model_is_the_3_8_stable_line(self):
        self.assertEqual(DEFAULT_GEMINI_LIVE_MODEL, "gemini-3.8-live")

    def test_the_vertex_only_model_is_refused(self):
        """It is in the plugin's Literal, so it passes parity — and then kills the job.

        `RealtimeModel(model="gemini-live-2.5-flash-native-audio")` raises at construction
        unless `vertexai=True`, which this deployment never sets (it authenticates with
        GOOGLE_API_KEY). Accepted at create, the assistant connects and the worker dies
        before a word is spoken.
        """
        with self.assertRaises(ValueError) as ctx:
            validate_mode_config(
                "realtime",
                SimpleNamespace(
                    provider="gemini", model="gemini-live-2.5-flash-native-audio", voice="Puck"
                ),
                None,
            )
        self.assertIn("Vertex AI", str(ctx.exception))

    def test_the_vertex_only_set_matches_the_plugin(self):
        from livekit.plugins.google.realtime.realtime_api import KNOWN_VERTEXAI_MODELS

        self.assertEqual(GEMINI_VERTEX_ONLY_MODELS, set(KNOWN_VERTEXAI_MODELS))

    def test_a_chat_model_is_rejected_in_realtime_mode(self):
        with self.assertRaises(ValueError) as ctx:
            validate_mode_config(
                "realtime",
                SimpleNamespace(provider="gemini", model="gemini-2.5-flash", voice=None),
                None,
            )
        self.assertIn("not a Gemini Live model", str(ctx.exception))

    def test_a_live_model_is_accepted(self):
        validate_mode_config(
            "realtime",
            SimpleNamespace(
                provider="gemini", model="gemini-3.1-flash-live-preview", voice="Puck"
            ),
            None,
        )

    def test_gemini_is_the_default_provider_so_its_models_are_checked_unprovided(self):
        with self.assertRaises(ValueError):
            validate_mode_config(
                "realtime",
                SimpleNamespace(provider=None, model="gpt-realtime", voice=None),
                None,
            )


class TestRealtimeVoiceRules(unittest.TestCase):
    """One `voice` field, two rosters with nothing in common."""

    def test_a_gemini_voice_under_openai_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_mode_config(
                "realtime",
                SimpleNamespace(provider="openai", model="gpt-realtime", voice="Puck"),
                None,
            )
        self.assertIn("is a Gemini Live voice", str(ctx.exception))

    def test_an_openai_voice_under_gemini_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            validate_mode_config(
                "realtime",
                SimpleNamespace(
                    provider="gemini", model="gemini-3.1-flash-live-preview", voice="marin"
                ),
                None,
            )
        self.assertIn("not a Gemini Live voice", str(ctx.exception))

    def test_an_unknown_openai_voice_is_allowed_through(self):
        """OpenAI ships realtime voices without an SDK Literal — do not block a new one."""
        validate_mode_config(
            "realtime",
            SimpleNamespace(provider="openai", model="gpt-realtime", voice="cedar"),
            None,
        )

    def test_no_voice_is_always_fine(self):
        validate_mode_config(
            "realtime",
            SimpleNamespace(provider="openai", model="gpt-realtime", voice=None),
            None,
        )


if __name__ == "__main__":
    unittest.main()
