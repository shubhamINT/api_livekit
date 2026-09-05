"""Cascade mode: STT/LLM construction, schema rules, and per-component usage folding.

Cascade is the true STT -> LLM -> TTS pipeline (assistant_mode="cascade"). These
tests cover the parts that decide what actually gets built, without touching the network.
"""

import sys
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from pydantic import ValidationError

from livekit.agents.metrics.usage import (
    AgentSessionUsage,
    LLMModelUsage,
    STTModelUsage,
    TTSModelUsage,
)
from livekit.plugins.sarvam.stt import MODEL_CONFIGS as SARVAM_MODEL_CONFIGS

from src.api.models.api_schemas import CreateAssistant, UpdateAssistant
from src.core.agents.llm import create_llm
from src.core.agents.stt import create_stt
from src.core.agents.usage import summarize_usage
from src.core.db.db_schemas import UsageRecord

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
from migrate_llm_knobs import stale_knobs  # noqa: E402


def narrower_sarvam_model(name, *, languages=None, supports_mode=True):
    """Register a Sarvam STT model with a narrower surface than the shipped roster.

    The per-model language and mode gates exist because the plugin raises rather than
    warning, and that exception kills the job. Today every model the plugin ships accepts
    the same languages and modes, so there is nothing real to gate against; this registers
    a model that does not, in the plugin's own table, which is the one `stt/lang.py` reads.
    """
    base = SARVAM_MODEL_CONFIGS["saaras:v3"]
    return mock.patch.dict(
        SARVAM_MODEL_CONFIGS,
        {
            name: replace(
                base,
                supports_mode=supports_mode,
                # "unknown" is Sarvam's auto-detect, and the fallback every dropped code
                # lands on, so a model that rejected it could not be built at all.
                allowed_languages=(
                    {*languages, "unknown"} if languages else base.allowed_languages
                ),
            )
        },
    )


def make_assistant(preferred_languages=None, **overrides):
    """Minimal stand-in for the Assistant document — the factories only read these."""
    fields = {
        "assistant_id": "assistant-1",
        "assistant_stt_model": None,
        "assistant_stt_config": None,
        "assistant_llm_config": None,
        "assistant_interaction_config": SimpleNamespace(
            preferred_languages=preferred_languages
        ),
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


class TestCreateSTT(unittest.TestCase):
    def test_sarvam_defaults_are_multilingual(self):
        """Unset config must give auto-detect + code-mixing, the multilingual default."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="sarvam", assistant_stt_config={"api_key": "k"}
            )
        )
        self.assertEqual(stt._opts.model, "saaras:v3")
        self.assertEqual(stt._opts.language, "unknown")  # auto-detect
        self.assertEqual(stt._opts.mode, "codemix")  # keeps code-switching intact

    def test_sarvam_config_overrides_defaults(self):
        stt = create_stt(
            make_assistant(
                assistant_stt_model="sarvam",
                assistant_stt_config={
                    "api_key": "k",
                    "model": "saaras:v4",
                    "language": "hi-IN",
                    "mode": "transcribe",
                },
            )
        )
        self.assertEqual(stt._opts.model, "saaras:v4")
        self.assertEqual(stt._opts.language, "hi-IN")
        self.assertEqual(stt._opts.mode, "transcribe")

    def test_cartesia_model_is_pinned_not_defaulted(self):
        """The plugin default flipped to the English-only ink-2 in 1.5.15, so the
        43-language ink-whisper must be passed explicitly."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="cartesia", assistant_stt_config={"api_key": "k"}
            )
        )
        self.assertEqual(stt._model, "ink-whisper")
        self.assertEqual(stt._language, "en")

    def test_cartesia_ignores_preferred_languages(self):
        """Contract change: preferred_languages is a prompt hint, never a provider
        parameter. It holds BCP-47 while Cartesia takes ISO 639-1, so the old fallback
        sent 'hi-IN' where only 'hi' is understood — and pinned a language the caller
        never asked to pin. Unpinned now means the plugin's own default, English."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="cartesia",
                assistant_stt_config={"api_key": "k"},
                preferred_languages=["hi-IN", "en-US"],
            )
        )
        self.assertEqual(stt._language, "en")

    def test_cartesia_explicit_language_is_honoured(self):
        stt = create_stt(
            make_assistant(
                assistant_stt_model="cartesia",
                assistant_stt_config={"api_key": "k", "language": "ta"},
                preferred_languages=["hi-IN"],
            )
        )
        self.assertEqual(stt._language, "ta")

    def test_cartesia_rejects_bcp47_language(self):
        """'en-US' is not an ISO 639-1 code. Drop it and take the default rather than
        transcribing against a code Cartesia does not understand."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="cartesia",
                assistant_stt_config={"api_key": "k", "language": "en-US"},
            )
        )
        self.assertEqual(stt._language, "en")

    def test_sarvam_unsupported_language_does_not_crash_the_job(self):
        """The Sarvam plugin RAISES on a code its model does not speak, and that exception
        escapes create_stt and ends the job before the call connects — a harder failure
        than any wrong-standard code on the other providers. Degrade to auto-detect."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="sarvam",
                assistant_stt_config={"api_key": "k", "language": "en-US"},
            )
        )
        self.assertIsNotNone(stt)
        self.assertEqual(stt._opts.language, "unknown")

    def test_sarvam_language_sets_are_per_model(self):
        """A code valid on one Sarvam model raises on another, so the check has to know
        which model it is building for. Every model on the current roster takes the same
        codes, so the narrow model is a stand-in — the roster diverged this way before
        (the sunset saarika:v2.5 spoke 11 codes to saaras:v3's 23) and can again."""
        with narrower_sarvam_model("saaras:vNarrow", languages={"en-IN", "hi-IN"}):
            cfg = {"api_key": "k", "model": "saaras:vNarrow", "language": "sat-IN"}
            stt = create_stt(
                make_assistant(assistant_stt_model="sarvam", assistant_stt_config=cfg)
            )
            self.assertEqual(stt._opts.language, "unknown")
        cfg = {"api_key": "k", "model": "saaras:v3", "language": "sat-IN"}
        stt = create_stt(make_assistant(assistant_stt_model="sarvam", assistant_stt_config=cfg))
        self.assertEqual(stt._opts.language, "sat-IN")

    def test_sarvam_mode_is_dropped_on_models_that_reject_it(self):
        """`mode` is model-gated exactly like `language`, and the plugin raises the same
        way, so this repo's blanket "codemix" default would kill every job on a model that
        does not take it. saaras:v3 and saaras:v4 both do; the v2.5 pair that did not is
        sunset, hence the stand-in."""
        with narrower_sarvam_model("saaras:vNoMode", supports_mode=False):
            stt = create_stt(
                make_assistant(
                    assistant_stt_model="sarvam",
                    assistant_stt_config={"api_key": "k", "model": "saaras:vNoMode"},
                )
            )
        self.assertIsNotNone(stt)
        self.assertNotEqual(stt._opts.mode, "codemix")

    def test_sarvam_blank_language_means_auto_detect(self):
        """An empty string is reachable from the API — the schema sets no min_length — and
        the plugin reads it as en-IN, not auto-detect."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="sarvam",
                assistant_stt_config={"api_key": "k", "language": "  "},
            )
        )
        self.assertEqual(stt._opts.language, "unknown")

    def test_sarvam_ignores_preferred_languages_by_design(self):
        """Auto-detect already covers every language preferred_languages could list;
        pinning one would be worse for a caller who switches mid-call."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="sarvam",
                assistant_stt_config={"api_key": "k"},
                preferred_languages=["hi", "en"],
            )
        )
        self.assertEqual(stt._opts.language, "unknown")

    def test_unset_model_defaults_to_sarvam(self):
        stt = create_stt(make_assistant(assistant_stt_config={"api_key": "k"}))
        self.assertEqual(stt._opts.model, "saaras:v3")

    def test_native_is_rejected(self):
        """ "native" means the realtime model transcribes itself; cascade has none."""
        self.assertIsNone(create_stt(make_assistant(assistant_stt_model="native")))

    def test_unknown_provider_is_rejected(self):
        self.assertIsNone(create_stt(make_assistant(assistant_stt_model="whisper")))

    def test_deepgram_defaults_to_multilingual_nova3(self):
        stt = create_stt(
            make_assistant(
                assistant_stt_model="deepgram", assistant_stt_config={"api_key": "k"}
            )
        )
        self.assertEqual(stt._opts.model, "nova-3")

    def test_deepgram_model_and_language_override(self):
        # nova, not flux: flux runs on a different Deepgram class entirely — see
        # TestDeepgramFamilyDispatch.
        stt = create_stt(
            make_assistant(
                assistant_stt_model="deepgram",
                assistant_stt_config={
                    "api_key": "k",
                    "model": "nova-2",
                    "language": "multi",
                    "enable_diarization": True,
                },
            )
        )
        self.assertEqual(stt._opts.model, "nova-2")
        self.assertEqual(stt._opts.language, "multi")
        self.assertTrue(stt._opts.enable_diarization)

    def test_deepgram_unpinned_autodetects_on_nova3(self):
        """Contract change: unpinned no longer means preferred_languages[0]. nova-3 can
        detect per segment, so unpinned means 'multi' — billed higher, hence the pin."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="deepgram",
                assistant_stt_config={"api_key": "k"},
                preferred_languages=["hi-IN", "en-US"],
            )
        )
        self.assertEqual(stt._opts.language, "multi")

    def test_deepgram_unpinned_stays_english_on_nova2(self):
        """nova-2 has no per-segment detection, so 'multi' would be a lie. Keep Deepgram's
        own default instead."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="deepgram",
                assistant_stt_config={"api_key": "k", "model": "nova-2"},
            )
        )
        self.assertEqual(stt._opts.language, "en-US")

    def test_deepgram_explicit_language_is_honoured(self):
        stt = create_stt(
            make_assistant(
                assistant_stt_model="deepgram",
                assistant_stt_config={"api_key": "k", "language": "hi-IN"},
                preferred_languages=["en-US"],
            )
        )
        self.assertEqual(stt._opts.language, "hi-IN")

    def test_deepgram_rejects_iso639_3_language(self):
        """A 3-letter primary subtag is an ElevenLabs code in the wrong slot — every
        language Deepgram lists has an ISO 639-1 code."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="deepgram",
                assistant_stt_config={"api_key": "k", "language": "hin"},
            )
        )
        self.assertEqual(stt._opts.language, "multi")

    def test_deepgram_optional_knobs_switched_off_by_default(self):
        """When diarization/keyterm are omitted they must not leak into the request as
        truthy — otherwise every Deepgram call would silently turn them on."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="deepgram", assistant_stt_config={"api_key": "k"}
            )
        )
        self.assertFalse(stt._opts.enable_diarization)
        self.assertEqual(stt._opts.keyterm, [])

    def test_deepgram_keyterm_forwarded(self):
        stt = create_stt(
            make_assistant(
                assistant_stt_model="deepgram",
                assistant_stt_config={"api_key": "k", "keyterm": "Vyom"},
            )
        )
        self.assertIn("Vyom", stt._opts.keyterm)

    def test_elevenlabs_defaults_to_scribe_v2_realtime(self):
        stt = create_stt(
            make_assistant(
                assistant_stt_model="elevenlabs", assistant_stt_config={"api_key": "k"}
            )
        )
        self.assertEqual(stt._opts.model_id, "scribe_v2_realtime")

    def test_elevenlabs_config_override(self):
        stt = create_stt(
            make_assistant(
                assistant_stt_model="elevenlabs",
                assistant_stt_config={
                    "api_key": "k",
                    "model": "scribe_v2",
                    "language_code": "hin",  # ISO 639-3, the only standard Scribe takes
                    "no_verbatim": True,
                },
            )
        )
        self.assertEqual(stt._opts.model_id, "scribe_v2")
        # Exactly "hin", not the plugin's normalized "hi": livekit.agents.LanguageCode maps
        # ISO 639-3 down to ISO 639-1, and 639-1 is what Scribe rejects. If this ever reads
        # "hi" again, the factory's post-construction fix-up has stopped working and every
        # pinned-language ElevenLabs call is back to closing with 1008.
        self.assertEqual(str(stt._opts.language_code), "hin")
        self.assertTrue(stt._opts.no_verbatim)

    def test_elevenlabs_ignores_preferred_languages(self):
        """Contract change: the old fallback put BCP-47 into an ISO 639-3 slot and the
        socket closed with `1008 invalid_request` on the first utterance. A preferred list
        must not disable auto-detect on the one provider built around it."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="elevenlabs",
                assistant_stt_config={"api_key": "k"},
                preferred_languages=["hi-IN", "en-US"],
            )
        )
        self.assertIsNone(stt._opts.language_code)

    def test_elevenlabs_rejects_bcp47_language_code(self):
        """The exact code that produced `Invalid language code received: 'en-US'` in
        production. Dropping it degrades to auto-detect instead of killing the call."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="elevenlabs",
                assistant_stt_config={"api_key": "k", "language_code": "en-US"},
            )
        )
        self.assertIsNone(stt._opts.language_code)

    def test_elevenlabs_omits_language_when_unset(self):
        """No language_code → the plugin stays auto-detect (~190 languages). The module
        sends `language_code` upstream only when set, so `None` is the auto-detect signal,
        not a literal `null`."""
        stt = create_stt(
            make_assistant(
                assistant_stt_model="elevenlabs", assistant_stt_config={"api_key": "k"}
            )
        )
        self.assertIsNone(stt._opts.language_code)

    def test_elevenlabs_no_verbatim_defaults_off(self):
        stt = create_stt(
            make_assistant(
                assistant_stt_model="elevenlabs", assistant_stt_config={"api_key": "k"}
            )
        )
        self.assertFalse(stt._opts.no_verbatim)

    def test_missing_key_is_rejected(self):
        with mock.patch("src.core.agents.stt.factory.settings.SARVAM_API_KEY", ""):
            self.assertIsNone(
                create_stt(
                    make_assistant(
                        assistant_stt_model="sarvam", assistant_stt_config={}
                    )
                )
            )
        with mock.patch("src.core.agents.stt.factory.settings.CARTESIA_API_KEY", ""):
            self.assertIsNone(
                create_stt(
                    make_assistant(
                        assistant_stt_model="cartesia", assistant_stt_config={}
                    )
                )
            )
        with mock.patch("src.core.agents.stt.factory.settings.DEEPGRAM_API_KEY", ""):
            self.assertIsNone(
                create_stt(
                    make_assistant(
                        assistant_stt_model="deepgram", assistant_stt_config={}
                    )
                )
            )
        with mock.patch("src.core.agents.stt.factory.settings.ELEVENLABS_API_KEY", ""):
            self.assertIsNone(
                create_stt(
                    make_assistant(
                        assistant_stt_model="elevenlabs", assistant_stt_config={}
                    )
                )
            )
        with mock.patch("src.core.agents.stt.factory.settings.OPENAI_API_KEY", ""):
            self.assertIsNone(
                create_stt(
                    make_assistant(assistant_stt_model="openai", assistant_stt_config={})
                )
            )


class TestOpenAISTT(unittest.TestCase):
    def _stt(self, preferred_languages=None, **config):
        return create_stt(
            make_assistant(
                preferred_languages=preferred_languages,
                assistant_stt_model="openai",
                assistant_stt_config={"api_key": "k", **config},
            )
        )

    def test_defaults_stream_over_the_realtime_socket(self):
        """The plugin default is batch REST — a live call needs the streaming path."""
        stt = self._stt()
        self.assertEqual(stt._opts.model, "gpt-4o-mini-transcribe")
        self.assertTrue(stt.capabilities.streaming)
        self.assertTrue(stt.capabilities.interim_results)

    def test_use_realtime_false_falls_back_to_batch(self):
        self.assertFalse(self._stt(use_realtime=False).capabilities.streaming)

    def test_unpinned_autodetects(self):
        """Contract change: unpinned used to mean preferred_languages[0], then a hardcoded
        'en' — a Hindi caller was transcribed as English. Detect instead. The plugin
        expresses auto-detect as an empty language list (it was a single empty string
        before 1.7.0, which added code-switched transcription)."""
        stt = self._stt()
        self.assertTrue(stt._opts.detect_language)
        self.assertEqual(stt._opts.languages, [])

    def test_preferred_languages_do_not_pin(self):
        stt = self._stt(preferred_languages=["hi-IN"])
        self.assertTrue(stt._opts.detect_language)

    def test_explicit_language_pins(self):
        stt = self._stt(preferred_languages=["hi-IN"], language="ta")
        self.assertEqual(stt._opts.languages, ["ta"])
        self.assertFalse(stt._opts.detect_language)

    def test_rejects_bcp47_language(self):
        """OpenAI transcription takes ISO 639-1; 'hi-IN' is a Sarvam code in the wrong
        slot, so it is dropped and the call auto-detects."""
        stt = self._stt(language="hi-IN")
        self.assertTrue(stt._opts.detect_language)

    def test_detect_language_blanks_the_pinned_language(self):
        stt = self._stt(language="hi", detect_language=True)
        self.assertTrue(stt._opts.detect_language)
        self.assertEqual(stt._opts.languages, [])

    def test_optional_knobs_stay_unset_by_default(self):
        stt = self._stt()
        self.assertFalse(stt._opts.prompt)
        self.assertFalse(stt._opts.noise_reduction_type)

    def test_optional_knobs_forwarded(self):
        stt = self._stt(
            model="whisper-1", prompt="Acme Corp", noise_reduction_type="far_field"
        )
        self.assertEqual(stt._opts.prompt, "Acme Corp")
        self.assertEqual(stt._opts.noise_reduction_type, "far_field")

    def test_realtime_whisper_is_rejected(self):
        """No server-side endpointing: the plugin would need a silero VAD we don't ship."""
        self.assertIsNone(self._stt(model="gpt-realtime-whisper"))


class TestCreateLLM(unittest.TestCase):
    def test_defaults_to_gpt_41(self):
        llm = create_llm(make_assistant(assistant_llm_config={"api_key": "k"}))
        self.assertEqual(llm.model, "gpt-4.1")

    def test_model_override(self):
        llm = create_llm(
            make_assistant(
                assistant_llm_config={"api_key": "k", "model": "gpt-4.1-mini"}
            )
        )
        self.assertEqual(llm.model, "gpt-4.1-mini")

    def test_non_openai_provider_rejected(self):
        self.assertIsNone(
            create_llm(
                make_assistant(
                    assistant_llm_config={"provider": "gemini", "api_key": "k"}
                )
            )
        )

    def test_generation_knobs_forwarded(self):
        """The knobs a reasoning model reads. Temperature is not one of them — see below."""
        llm = create_llm(
            make_assistant(
                assistant_llm_config={
                    "api_key": "k",
                    "model": "gpt-5-mini",
                    "max_output_tokens": 400,
                    "reasoning_effort": "medium",
                    "service_tier": "flex",
                    "verbosity": "low",
                    "tool_choice": "required",
                    "parallel_tool_calls": False,
                }
            )
        )
        opts = llm._opts
        self.assertEqual(opts.max_output_tokens, 400)
        self.assertEqual(opts.service_tier, "flex")
        self.assertEqual(opts.verbosity, "low")
        self.assertEqual(opts.tool_choice, "required")
        self.assertEqual(opts.parallel_tool_calls, False)
        self.assertEqual(opts.reasoning.effort, "medium")

    def test_temperature_forwarded_on_a_non_reasoning_model(self):
        llm = create_llm(
            make_assistant(
                assistant_llm_config={
                    "api_key": "k",
                    "model": "gpt-4.1",
                    "temperature": 0.2,
                }
            )
        )
        self.assertEqual(llm._opts.temperature, 0.2)

    def test_reasoning_effort_dropped_on_a_model_that_rejects_it(self):
        """The failure this gate exists for.

        An effort set on gpt-5 and left behind by a switch to gpt-4.1 used to be forwarded
        verbatim. OpenAI answers 400 ("Unsupported parameter: 'reasoning.effort' is not
        supported with this model"), the plugin raises it non-retryable inside
        _llm_inference_task, and it does so on every turn — the assistant answers the call
        and never speaks.
        """
        from livekit.agents.types import NOT_GIVEN

        llm = create_llm(
            make_assistant(
                assistant_llm_config={
                    "api_key": "k",
                    "model": "gpt-4.1",
                    "reasoning_effort": "low",
                    "temperature": 0.4,
                }
            )
        )
        self.assertIs(llm._opts.reasoning, NOT_GIVEN)
        # The knob the model does read is untouched by the drop.
        self.assertEqual(llm._opts.temperature, 0.4)

    def test_temperature_dropped_on_a_reasoning_model(self):
        """The mirror image: temperature stored, then the model switched to gpt-5."""
        from livekit.agents.types import NOT_GIVEN

        llm = create_llm(
            make_assistant(
                assistant_llm_config={
                    "api_key": "k",
                    "model": "gpt-5",
                    "temperature": 0.4,
                    "reasoning_effort": "low",
                }
            )
        )
        self.assertIs(llm._opts.temperature, NOT_GIVEN)
        self.assertEqual(llm._opts.reasoning.effort, "low")

    def test_verbosity_is_gated_to_the_gpt5_generation(self):
        """`text.verbosity` is a gpt-5 parameter; the gpt-4 line rejects it."""
        from livekit.agents.types import NOT_GIVEN

        def verbosity_for(model):
            llm = create_llm(
                make_assistant(
                    assistant_llm_config={
                        "api_key": "k",
                        "model": model,
                        "verbosity": "low",
                    }
                )
            )
            return llm._opts.verbosity

        self.assertEqual(verbosity_for("gpt-5.4"), "low")
        self.assertEqual(verbosity_for("gpt-5.6-sol"), "low")
        self.assertIs(verbosity_for("gpt-4.1"), NOT_GIVEN)
        self.assertIs(verbosity_for("gpt-4o-mini"), NOT_GIVEN)

    def test_knobs_on_an_unknown_model_are_forwarded_untouched(self):
        """An off-allowlist model gets no guessing — its knobs go through as written.

        This is the documented behaviour of `unsupported_knob_reason` for a model outside
        `CASCADE_MODELS`: a row written before the allowlist, or by a direct DB edit, is not
        second-guessed. It also covers a model that has since been retired — nothing can be
        salvaged there anyway, because OpenAI rejects the turn on the model id alone. The
        retired `*-chat-latest` aliases are the live example.
        """
        llm = create_llm(
            make_assistant(
                assistant_llm_config={
                    "api_key": "k",
                    "model": "gpt-5.2-chat-latest",
                    "temperature": 0.4,
                }
            )
        )
        self.assertEqual(llm._opts.temperature, 0.4)

    def test_reasoning_dropped_when_tools_make_the_model_reject_it(self):
        """gpt-5.2 / gpt-5.4* refuse reasoning.effort while function tools are attached."""
        from livekit.agents.types import NOT_GIVEN

        config = {"api_key": "k", "model": "gpt-5.2", "reasoning_effort": "high"}
        with_tools = create_llm(make_assistant(assistant_llm_config=config), has_tools=True)
        self.assertIs(with_tools._opts.reasoning, NOT_GIVEN)
        # Same assistant, no tools: the knob is legal and must survive.
        without_tools = create_llm(make_assistant(assistant_llm_config=config))
        self.assertEqual(without_tools._opts.reasoning.effort, "high")

    def test_plugin_injected_reasoning_is_cleared_when_tools_are_attached(self):
        """The failure the logs showed, and the one config filtering cannot reach.

        openai.responses.LLM injects Reasoning(effort="none") for gpt-5.2 when the caller
        passes none, so an assistant with an empty config still sent reasoning.effort with
        its tools and got a 400 on every turn ("There was an issue with your request").
        """
        from livekit.agents.types import NOT_GIVEN

        bare = {"api_key": "k", "model": "gpt-5.2"}
        # What the plugin does on its own — if this stops being true, the workaround below
        # is dead code and can go.
        self.assertEqual(create_llm(make_assistant(assistant_llm_config=bare))._opts.reasoning.effort, "none")
        with_tools = create_llm(make_assistant(assistant_llm_config=bare), has_tools=True)
        self.assertIs(with_tools._opts.reasoning, NOT_GIVEN)

    def test_a_compatible_reasoning_model_keeps_its_effort_with_tools(self):
        """Only gpt-5.2/gpt-5.4* are tool-incompatible; gpt-5 itself is unaffected."""
        llm = create_llm(
            make_assistant(
                assistant_llm_config={
                    "api_key": "k",
                    "model": "gpt-5",
                    "reasoning_effort": "medium",
                }
            ),
            has_tools=True,
        )
        self.assertEqual(llm._opts.reasoning.effort, "medium")

    def test_built_llm_is_logged_without_the_api_key(self):
        """A Responses 400 arrives with no detail, so the knobs must be in our own log."""
        with mock.patch("src.core.agents.llm.factory.logger") as log:
            create_llm(
                make_assistant(
                    assistant_llm_config={
                        "api_key": "sk-secret",
                        "model": "gpt-4.1",
                        "temperature": 0.4,
                    }
                )
            )
        logged = str(log.info.call_args)
        self.assertIn("gpt-4.1", logged)
        self.assertIn("temperature", logged)
        self.assertNotIn("sk-secret", logged)

    def test_dropping_a_knob_says_which_one_and_why(self):
        """A silent drop is its own debugging problem — the log has to name the pair."""
        with mock.patch("src.core.agents.llm.factory.logger") as log:
            create_llm(
                make_assistant(
                    assistant_llm_config={
                        "api_key": "k",
                        "model": "gpt-4.1",
                        "reasoning_effort": "low",
                    }
                )
            )
        message = log.warning.call_args[0][0]
        self.assertIn("reasoning_effort", message)
        self.assertIn("gpt-4.1", message)
        self.assertIn("assistant-1", message)

    def test_omitted_knobs_keep_defaults(self):
        llm = create_llm(make_assistant(assistant_llm_config={"api_key": "k"}))
        opts = llm._opts
        # NotGiven — the SDK applies its own defaults.
        from livekit.agents.types import NOT_GIVEN

        self.assertIs(opts.temperature, NOT_GIVEN)
        self.assertIs(opts.max_output_tokens, NOT_GIVEN)

    def test_missing_key_rejected(self):
        with mock.patch("src.core.agents.llm.factory.settings.OPENAI_API_KEY", ""):
            self.assertIsNone(create_llm(make_assistant(assistant_llm_config={})))

    def test_an_off_allowlist_model_warns_and_still_builds(self):
        """The likeliest reason a cascade call connects and never speaks gets a log line.

        Refusing to build would end the job just as silently, and the row is already stored —
        so the LLM is built and the warning names the audit script. The API is what prevents
        such a model being stored in the first place.
        """
        with self.assertLogs("app", level="WARNING") as logs:
            llm = create_llm(
                make_assistant(
                    assistant_llm_config={"api_key": "k", "model": "gpt-5.2-chat-latest"}
                )
            )
        self.assertIsNotNone(llm)
        joined = "\n".join(logs.output)
        self.assertIn("gpt-5.2-chat-latest", joined)
        self.assertIn("audit_assistant_models.py", joined)

    def test_an_allowlisted_model_does_not_warn(self):
        with mock.patch("src.core.agents.llm.factory.logger") as log:
            create_llm(make_assistant(assistant_llm_config={"api_key": "k", "model": "gpt-4.1"}))
        log.warning.assert_not_called()

    def test_a_constructor_failure_returns_none_instead_of_raising(self):
        """Every other config error here ends the job through `return None`; so does this one.

        A raise would escape entrypoint() and kill the job with a traceback — same outcome for
        the caller, much worse for whoever reads the log.
        """
        with mock.patch(
            "src.core.agents.llm.factory.openai.responses.LLM",
            side_effect=TypeError("unexpected keyword argument 'verbosity'"),
        ):
            self.assertIsNone(
                create_llm(make_assistant(assistant_llm_config={"api_key": "k"}))
            )

    def test_the_built_llm_log_line_names_the_replay_command(self):
        """The line someone reads after a failed call should hand them the next step."""
        with self.assertLogs("app", level="INFO") as logs:
            create_llm(make_assistant(assistant_llm_config={"api_key": "k"}))
        joined = "\n".join(logs.output)
        self.assertIn("replay_cascade_request.py", joined)


class TestCascadeSchemaRules(unittest.TestCase):
    BASE = {
        "assistant_name": "A",
        "assistant_description": "d",
        "assistant_prompt": "p",
        "assistant_mode": "cascade",
        "assistant_tts_model": "cartesia",
        "assistant_tts_config": {"voice_id": "v1"},
    }

    def test_cascade_accepted_with_stt_and_tts(self):
        request = CreateAssistant(**self.BASE, assistant_stt_model="sarvam")
        self.assertEqual(request.assistant_mode, "cascade")
        # A bare model still materializes a defaults-only config.
        self.assertEqual(request.assistant_stt_config.model, "saaras:v3")

    def test_cascade_accepts_cartesia_stt(self):
        request = CreateAssistant(
            **self.BASE,
            assistant_stt_model="cartesia",
            assistant_stt_config={"language": "hi"},
        )
        self.assertEqual(request.assistant_stt_config.type, "cartesia")
        self.assertEqual(request.assistant_stt_config.language, "hi")

    def test_cascade_accepts_deepgram_stt(self):
        request = CreateAssistant(
            **self.BASE,
            assistant_stt_model="deepgram",
            assistant_stt_config={"model": "nova-3", "language": "multi"},
        )
        self.assertEqual(request.assistant_stt_config.type, "deepgram")
        self.assertEqual(request.assistant_stt_config.model, "nova-3")
        self.assertEqual(request.assistant_stt_config.language, "multi")

    def test_cascade_accepts_elevenlabs_stt(self):
        request = CreateAssistant(
            **self.BASE,
            assistant_stt_model="elevenlabs",
            assistant_stt_config={"no_verbatim": True},
        )
        self.assertEqual(request.assistant_stt_config.type, "elevenlabs")
        self.assertEqual(request.assistant_stt_config.no_verbatim, True)

    def test_cascade_accepts_openai_stt(self):
        request = CreateAssistant(
            **self.BASE,
            assistant_stt_model="openai",
            assistant_stt_config={"model": "gpt-4o-transcribe", "detect_language": True},
        )
        self.assertEqual(request.assistant_stt_config.type, "openai")
        self.assertEqual(request.assistant_stt_config.model, "gpt-4o-transcribe")
        self.assertTrue(request.assistant_stt_config.detect_language)
        self.assertTrue(request.assistant_stt_config.use_realtime)

    def test_cascade_rejects_native_stt(self):
        with self.assertRaises(ValidationError):
            CreateAssistant(**self.BASE, assistant_stt_model="native")

    def test_cascade_rejects_non_openai_provider(self):
        with self.assertRaises(ValidationError):
            CreateAssistant(**self.BASE, assistant_llm_config={"provider": "gemini"})

    def test_cascade_accepts_documented_openai_model(self):
        request = CreateAssistant(
            **self.BASE,
            assistant_stt_model="sarvam",
            assistant_llm_config={"model": "gpt-4.1-mini"},
        )
        self.assertEqual(request.assistant_llm_config.model, "gpt-4.1-mini")

    def test_cascade_rejects_unknown_openai_model(self):
        with self.assertRaises(ValidationError):
            CreateAssistant(
                **self.BASE,
                assistant_stt_model="sarvam",
                assistant_llm_config={"model": "gpt-4.1-quantum"},
            )

    def test_cascade_accepts_llm_generation_knobs(self):
        """Knobs a reasoning model reads. Temperature is not one of them — next test."""
        request = CreateAssistant(
            **self.BASE,
            assistant_stt_model="sarvam",
            assistant_llm_config={
                "model": "gpt-5-mini",
                "max_output_tokens": 512,
                "reasoning_effort": "low",
                "service_tier": "flex",
                "verbosity": "medium",
                "tool_choice": "auto",
                "parallel_tool_calls": False,
            },
        )
        cfg = request.assistant_llm_config
        self.assertEqual(cfg.max_output_tokens, 512)
        self.assertEqual(cfg.reasoning_effort, "low")
        self.assertEqual(cfg.verbosity, "medium")

    def test_tool_choice_required_needs_a_tool_to_choose(self):
        """`required` with an empty tool list is a 400 from OpenAI on every turn.

        Which is the silent-call shape again: the call connects, the assistant never speaks.
        A fresh assistant has no `tool_ids` yet, so end_call is the only tool it can have at
        creation — /assistant/attach-tools re-checks this when real tools arrive.
        """
        with self.assertRaises(ValidationError) as ctx:
            CreateAssistant(
                **self.BASE,
                assistant_stt_model="sarvam",
                assistant_llm_config={"model": "gpt-4.1", "tool_choice": "required"},
            )
        self.assertIn("tool_choice", str(ctx.exception))
        self.assertIn("needs at least one tool", str(ctx.exception))

    def test_tool_choice_required_is_accepted_when_end_call_is_enabled(self):
        request = CreateAssistant(
            **self.BASE,
            assistant_stt_model="sarvam",
            assistant_llm_config={"model": "gpt-4.1", "tool_choice": "required"},
            assistant_end_call_enabled=True,
            assistant_end_call_trigger_phrase="that's all, bye",
            assistant_end_call_agent_message="Thank you, goodbye.",
        )
        self.assertEqual(request.assistant_llm_config.tool_choice, "required")

    def test_flex_service_tier_is_rejected_on_a_non_gpt5_model(self):
        """Measured: gpt-4.1-nano + flex is a 400 on every turn, with no parameter named.

        That is the config that produced the silent calls this guard exists for. `flex` is a
        gpt-5 generation tier; OpenAI refuses it elsewhere, and on nano it refuses it without
        saying which parameter was wrong.
        """
        with self.assertRaises(ValidationError) as ctx:
            CreateAssistant(
                **self.BASE,
                assistant_stt_model="sarvam",
                assistant_llm_config={"model": "gpt-4.1-nano", "service_tier": "flex"},
            )
        self.assertIn("service_tier", str(ctx.exception))
        self.assertIn("gpt-5 generation tier", str(ctx.exception))

    def test_flex_service_tier_is_accepted_on_the_gpt5_line(self):
        request = CreateAssistant(
            **self.BASE,
            assistant_stt_model="sarvam",
            assistant_llm_config={"model": "gpt-5-mini", "service_tier": "flex"},
        )
        self.assertEqual(request.assistant_llm_config.service_tier, "flex")

    def test_tiers_that_work_everywhere_are_accepted(self):
        for tier in ("auto", "default", "fast", "priority"):
            with self.subTest(tier=tier):
                request = CreateAssistant(
                    **self.BASE,
                    assistant_stt_model="sarvam",
                    assistant_llm_config={"model": "gpt-4.1-nano", "service_tier": tier},
                )
                self.assertEqual(request.assistant_llm_config.service_tier, tier)

    def test_scale_is_not_an_openai_tier_at_all(self):
        """OpenAI: "Invalid value: 'scale'. Supported values are: auto, default, fast, flex, priority"."""
        with self.assertRaises(ValidationError):
            CreateAssistant(
                **self.BASE,
                assistant_stt_model="sarvam",
                assistant_llm_config={"model": "gpt-5-mini", "service_tier": "scale"},
            )

    def test_tool_choice_none_is_fine_without_tools(self):
        """'none' is the legitimate way to say "do not call tools" — nothing to choose from."""
        request = CreateAssistant(
            **self.BASE,
            assistant_stt_model="sarvam",
            assistant_llm_config={"model": "gpt-4.1", "tool_choice": "none"},
        )
        self.assertEqual(request.assistant_llm_config.tool_choice, "none")

    def test_cascade_accepts_temperature_on_a_chat_model(self):
        request = CreateAssistant(
            **self.BASE,
            assistant_stt_model="sarvam",
            assistant_llm_config={"model": "gpt-4.1", "temperature": 0.3},
        )
        self.assertEqual(request.assistant_llm_config.temperature, 0.3)

    def test_cascade_rejects_a_knob_the_model_cannot_read(self):
        """Store-then-fail is the trap: the knob used to be accepted here and only killed
        the call later, as an opaque OpenAI 400 on every LLM turn."""
        bad_pairs = [
            {"model": "gpt-5-mini", "temperature": 0.3},  # reasoning models reject it
            {"model": "gpt-4.1", "reasoning_effort": "low"},  # chat models reject it
            {"model": "gpt-5.2-chat-latest", "reasoning_effort": "low"},  # chat alias
            {"model": "gpt-4o", "verbosity": "low"},  # gpt-5 generation only
        ]
        for llm_config in bad_pairs:
            with self.subTest(llm_config=llm_config):
                with self.assertRaises(ValidationError):
                    CreateAssistant(
                        **self.BASE,
                        assistant_stt_model="sarvam",
                        assistant_llm_config=llm_config,
                    )

    def test_cascade_knob_rules_use_the_default_model_when_none_is_set(self):
        """No model means gpt-4.1, so the knobs are judged against gpt-4.1."""
        with self.assertRaises(ValidationError):
            CreateAssistant(
                **self.BASE,
                assistant_stt_model="sarvam",
                assistant_llm_config={"reasoning_effort": "low"},
            )

    def test_cascade_rejects_unknown_llm_config_key(self):
        with self.assertRaises(ValidationError):
            CreateAssistant(
                **self.BASE,
                assistant_stt_model="sarvam",
                assistant_llm_config={
                    "model": "gpt-4.1-mini",
                    "frequency_penalty": 1.0,
                },
            )

    def test_tts_config_rejects_unknown_keys(self):
        cfg = {
            **self.BASE,
            "assistant_stt_model": "sarvam",
            "assistant_tts_config": {"voice_id": "v1", "bogus": 1},
        }
        with self.assertRaises(ValidationError):
            CreateAssistant(**cfg)

    def test_cascade_requires_tts(self):
        without_tts = {
            k: v for k, v in self.BASE.items() if not k.startswith("assistant_tts")
        }
        with self.assertRaises(ValidationError):
            CreateAssistant(**without_tts)

    def test_update_to_cascade_rejects_native_stt(self):
        with self.assertRaises(ValidationError):
            UpdateAssistant(assistant_mode="cascade", assistant_stt_model="native")

    def test_update_to_cascade_accepts_sarvam(self):
        request = UpdateAssistant(
            assistant_mode="cascade", assistant_stt_model="sarvam"
        )
        self.assertEqual(request.assistant_stt_config.mode, "codemix")

    def test_pipeline_and_realtime_still_valid(self):
        """The two existing modes must be untouched by the cascade rules."""
        pipeline = CreateAssistant(
            **{**self.BASE, "assistant_mode": "pipeline"},
            assistant_stt_model="native",  # legal in pipeline mode
        )
        self.assertEqual(pipeline.assistant_mode, "pipeline")
        realtime = CreateAssistant(
            assistant_name="A",
            assistant_description="d",
            assistant_prompt="p",
            assistant_mode="realtime",
            assistant_llm_config={"provider": "gemini"},
        )
        self.assertEqual(realtime.assistant_mode, "realtime")


class TestStoredCascadeGuards(unittest.TestCase):
    """The schema's mode rules only fire when a request names the mode. A PATCH that
    omits it must still be checked against the stored row, or the assistant is accepted
    and then silently fails to start."""

    def test_schema_alone_does_not_catch_an_omitted_mode(self):
        # Documents exactly why the route-level guard has to exist.
        request = UpdateAssistant(assistant_llm_config={"provider": "gemini"})
        self.assertEqual(request.assistant_llm_config.provider, "gemini")

    def test_route_rejects_gemini_on_a_stored_cascade_assistant(self):
        from fastapi import HTTPException

        from src.api.routes import assistant as assistant_route

        stored = SimpleNamespace(assistant_mode="cascade", assistant_stt_model="sarvam")
        with self.assertRaises(HTTPException) as ctx:
            assistant_route.enforce_stored_mode_constraints(
                stored, {"assistant_llm_config": {"provider": "gemini"}}, new_mode=None
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_route_rejects_native_stt_on_a_stored_cascade_assistant(self):
        from fastapi import HTTPException

        from src.api.routes import assistant as assistant_route

        stored = SimpleNamespace(assistant_mode="cascade", assistant_stt_model="sarvam")
        with self.assertRaises(HTTPException):
            assistant_route.enforce_stored_mode_constraints(
                stored, {"assistant_stt_model": "native"}, new_mode=None
            )

    def test_route_allows_a_valid_cascade_patch(self):
        from src.api.routes import assistant as assistant_route

        stored = SimpleNamespace(assistant_mode="cascade", assistant_stt_model="sarvam")
        assistant_route.enforce_stored_mode_constraints(
            stored,
            {"assistant_llm_config": {"provider": "openai", "model": "gpt-4.1-mini"}},
            new_mode=None,
        )

    def test_route_rejects_gemini_on_a_stored_pipeline_assistant(self):
        """Pipeline is OpenAI-only too, so the same guard applies outside cascade."""
        from fastapi import HTTPException

        from src.api.routes import assistant as assistant_route

        stored = SimpleNamespace(
            assistant_mode="pipeline", assistant_stt_model="native"
        )
        with self.assertRaises(HTTPException) as ctx:
            assistant_route.enforce_stored_mode_constraints(
                stored, {"assistant_llm_config": {"provider": "gemini"}}, new_mode=None
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_route_allows_an_unrelated_pipeline_patch(self):
        from src.api.routes import assistant as assistant_route

        stored = SimpleNamespace(
            assistant_mode="pipeline", assistant_stt_model="native"
        )
        assistant_route.enforce_stored_mode_constraints(
            stored, {"assistant_name": "renamed"}, new_mode=None
        )

    def test_route_rejects_switch_to_cascade_over_stored_gemini(self):
        """The request alone looks fine — only the merge with the stored row is invalid."""
        from fastapi import HTTPException

        from src.api.routes import assistant as assistant_route

        stored = SimpleNamespace(
            assistant_mode="pipeline",
            assistant_stt_model="sarvam",
            assistant_llm_config={"provider": "gemini"},
        )
        with self.assertRaises(HTTPException) as ctx:
            assistant_route.enforce_stored_mode_constraints(
                stored, {"assistant_mode": "cascade"}, new_mode="cascade"
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_route_rejects_switch_to_cascade_over_stored_realtime_model(self):
        from fastapi import HTTPException

        from src.api.routes import assistant as assistant_route

        stored = SimpleNamespace(
            assistant_mode="pipeline",
            assistant_stt_model="sarvam",
            assistant_llm_config={"provider": "openai", "model": "gpt-realtime-1.5"},
        )
        with self.assertRaises(HTTPException) as ctx:
            assistant_route.enforce_stored_mode_constraints(
                stored, {"assistant_mode": "cascade"}, new_mode="cascade"
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_route_lets_the_same_request_fix_the_stored_config(self):
        """The 400 above must be escapable in one request, not a dead end."""
        from src.api.routes import assistant as assistant_route

        stored = SimpleNamespace(
            assistant_mode="pipeline",
            assistant_stt_model="sarvam",
            assistant_llm_config={"provider": "gemini"},
        )
        assistant_route.enforce_stored_mode_constraints(
            stored,
            {
                "assistant_mode": "cascade",
                "assistant_llm_config": {"provider": "openai", "model": "gpt-4.1-mini"},
            },
            new_mode="cascade",
        )

    def test_route_honours_an_explicitly_cleared_llm_config(self):
        """Leaving realtime nulls the stored config; the old Gemini row must not be merged."""
        from src.api.routes import assistant as assistant_route

        stored = SimpleNamespace(
            assistant_mode="realtime",
            assistant_stt_model="native",
            assistant_llm_config={"provider": "gemini"},
        )
        assistant_route.enforce_stored_mode_constraints(
            stored,
            {"assistant_mode": "pipeline", "assistant_llm_config": None},
            new_mode="pipeline",
        )


class TestCreateTTS(unittest.TestCase):
    def test_elevenlabs_absent_voice_settings_stays_unset(self):
        """An existing ElevenLabs assistant with no voice_settings must keep passing
        NOT_GIVEN (not None) — the client's is_given(None) is True and would crash on
        dataclasses.asdict(None) at the first synthesis."""
        from src.core.agents.tts.factory import create_tts

        tts = create_tts(
            make_assistant(
                assistant_tts_model="elevenlabs",
                assistant_tts_config={
                    "voice_id": "v",
                    "api_key": "k",
                    "model": "eleven_v3",
                },
            )
        )
        from livekit.agents.types import NOT_GIVEN

        self.assertIs(tts._opts.voice_settings, NOT_GIVEN)

    def test_elevenlabs_present_voice_settings_is_forwarded(self):
        """Model pinned deliberately: `speed` is dropped on the default v3 model, which has
        no speed control (see TestElevenLabsSpeedGuard)."""
        from src.core.agents.tts.factory import create_tts

        tts = create_tts(
            make_assistant(
                assistant_tts_model="elevenlabs",
                assistant_tts_config={
                    "voice_id": "v",
                    "api_key": "k-key",
                    "model": "eleven_multilingual_v2",
                    "voice_settings": {
                        "stability": 0.7,
                        "similarity_boost": 0.8,
                        "style": 0.3,
                        "speed": 1.2,
                        "use_speaker_boost": True,
                    },
                },
            )
        )
        vs = tts._opts.voice_settings
        self.assertEqual(
            (
                vs.stability,
                vs.similarity_boost,
                vs.style,
                vs.speed,
                vs.use_speaker_boost,
            ),
            (0.7, 0.8, 0.3, 1.2, True),
        )

    def test_cartesia_speed_and_volume_forwarded(self):
        from src.core.agents.tts.factory import create_tts

        tts = create_tts(
            make_assistant(
                assistant_tts_model="cartesia",
                assistant_tts_config={
                    "voice_id": "v",
                    "api_key": "k",
                    "speed": 1.5,
                    "volume": 0.8,
                },
            )
        )
        self.assertEqual(tts._opts.speed, 1.5)
        self.assertEqual(tts._opts.volume, 0.8)

    def test_sarvam_pace_and_temperature_forwarded(self):
        from src.core.agents.tts.factory import create_tts

        tts = create_tts(
            make_assistant(
                assistant_tts_model="sarvam",
                assistant_tts_config={
                    "speaker": "shubh",
                    "api_key": "k",
                    "pace": 1.2,
                    "temperature": 0.5,
                },
            )
        )
        self.assertEqual(tts._opts.pace, 1.2)
        self.assertEqual(tts._opts.temperature, 0.5)

    def test_sarvam_omitted_target_language_falls_back_to_en_in(self):
        """The schema stores null, so the factory's own fallback has to apply. A concrete
        schema default here would silently synthesize the wrong language."""
        from src.api.models.api_schemas.config.tts_config import SarvamTTSConfig
        from src.core.agents.tts.factory import create_tts

        stored = SarvamTTSConfig(speaker="shubh", api_key="k").model_dump()
        self.assertIsNone(stored["target_language_code"])
        tts = create_tts(
            make_assistant(assistant_tts_model="sarvam", assistant_tts_config=stored)
        )
        self.assertEqual(tts._opts.target_language_code, "en-IN")

    def test_cartesia_speed_rejects_preset_strings(self):
        """sonic-3 takes a float only — the plugin raises on "fast", so the schema must
        reject it at create time rather than at the first synthesis."""
        from src.api.models.api_schemas.config.tts_config import CartesiaTTSConfig

        with self.assertRaises(ValidationError):
            CartesiaTTSConfig(voice_id="v", speed="fast")

    def test_partial_voice_settings_uses_the_documented_defaults(self):
        from src.core.agents.tts.factory import create_tts

        tts = create_tts(
            make_assistant(
                assistant_tts_model="elevenlabs",
                assistant_tts_config={
                    "voice_id": "v",
                    "api_key": "k",
                    "voice_settings": {"style": 0.4},
                },
            )
        )
        vs = tts._opts.voice_settings
        self.assertEqual((vs.stability, vs.similarity_boost, vs.style), (0.5, 0.5, 0.4))

    def test_missing_key_returns_none_instead_of_raising(self):
        """Every provider must take the `return None` path, which entrypoint() handles.
        ElevenLabs used to raise ValueError straight out of create_tts."""
        from src.core.agents.tts import factory as tts_factory

        cases = [
            ("cartesia", {"voice_id": "v"}, "CARTESIA_API_KEY"),
            ("sarvam", {"speaker": "shubh"}, "SARVAM_API_KEY"),
            ("elevenlabs", {"voice_id": "v"}, "ELEVENLABS_API_KEY"),
            ("mistral", {"voice_id": "v"}, "MISTRAL_API_KEY"),
        ]
        for model, config, env_key in cases:
            with self.subTest(model=model):
                with mock.patch.object(tts_factory.settings, env_key, ""):
                    self.assertIsNone(
                        tts_factory.create_tts(
                            make_assistant(
                                assistant_tts_model=model, assistant_tts_config=config
                            )
                        )
                    )


class TestDeepgramFamilyDispatch(unittest.TestCase):
    """flux and nova speak different Deepgram APIs; neither class validates the model at
    construction, so a flux ID on the v1 class only fails when the socket opens."""

    def _stt(self, **config):
        return create_stt(
            make_assistant(
                assistant_stt_model="deepgram",
                assistant_stt_config={"api_key": "k", **config},
            )
        )

    def test_nova_uses_the_v1_class(self):
        self.assertEqual(type(self._stt(model="nova-3")).__name__, "STT")

    def test_flux_uses_the_v2_class(self):
        for model in ("flux-general-en", "flux-general-multi"):
            with self.subTest(model=model):
                self.assertEqual(type(self._stt(model=model)).__name__, "STTv2")

    def test_flux_drops_diarization_instead_of_crashing(self):
        stt = self._stt(model="flux-general-multi", enable_diarization=True)
        self.assertEqual(type(stt).__name__, "STTv2")

    def test_flux_language_hint_is_a_list(self):
        """language_hint is list[str] on the v2 API — a bare string reaches the wire as a
        JSON string where an array is expected. The old code passed the language straight
        through."""
        stt = self._stt(model="flux-general-multi", language="hi-IN")
        self.assertEqual(stt._opts.language_hint, ["hi-IN"])

    def test_flux_unpinned_sends_no_hint(self):
        """No hint IS auto-detect on flux. 'multi' is a v1 sentinel and means nothing
        here, so it must never be forwarded as a hint."""
        self.assertEqual(self._stt(model="flux-general-multi")._opts.language_hint, [])
        self.assertEqual(
            self._stt(model="flux-general-multi", language="multi")._opts.language_hint, []
        )

    def test_flux_en_model_takes_no_hint(self):
        """The plugin supports language_hint on flux-general-multi only, and warns then
        drops it elsewhere — do not send it at all."""
        stt = self._stt(model="flux-general-en", language="hi-IN")
        self.assertEqual(stt._opts.language_hint, [])


class TestSarvamTTSLanguageGuard(unittest.TestCase):
    """Bulbul speaks 11 Indic BCP-47 codes. Anything else 400s on every synthesis, so an
    unusable code has to be caught here rather than at the first spoken word."""

    def _tts(self, **config):
        from src.core.agents.tts.factory import create_tts

        return create_tts(
            SimpleNamespace(
                assistant_id="assistant-1",
                assistant_tts_model="sarvam",
                assistant_tts_config={"api_key": "k", "speaker": "shubh", **config},
            )
        )

    def test_supported_code_is_forwarded(self):
        self.assertEqual(self._tts(target_language_code="hi-IN")._opts.target_language_code, "hi-IN")

    def test_unsupported_code_falls_back_to_en_in(self):
        # 'en-US' is the code the assistant picker used to offer; Sarvam has en-IN only.
        self.assertEqual(self._tts(target_language_code="en-US")._opts.target_language_code, "en-IN")

    def test_unset_code_falls_back_to_en_in(self):
        self.assertEqual(self._tts(target_language_code=None)._opts.target_language_code, "en-IN")


class TestSarvamTTSSpeakerGuard(unittest.TestCase):
    """The speaker roster is per Bulbul generation, and the plugin raises on a mismatch.

    Unlike a bad language code, that exception escapes create_tts and entrypoint(): the job
    dies with a traceback and the caller hears nothing at all.
    """

    def _tts(self, speaker):
        from src.core.agents.tts.factory import create_tts

        return create_tts(
            SimpleNamespace(
                assistant_id="assistant-1",
                assistant_tts_model="sarvam",
                assistant_tts_config={"api_key": "k", "speaker": speaker},
            )
        )

    def test_a_v3_speaker_is_forwarded(self):
        self.assertEqual(self._tts("shubh")._opts.speaker, "shubh")

    def test_a_v2_speaker_is_refused_without_raising(self):
        # 'anushka' is the plugin's own bulbul:v2 default, so it is the likeliest stale value.
        self.assertIsNone(self._tts("anushka"))

    def test_an_unknown_speaker_is_refused_without_raising(self):
        self.assertIsNone(self._tts("not-a-speaker"))

    def test_the_refusal_names_the_valid_speakers(self):
        with mock.patch("src.core.agents.stt.lang.logger") as log:
            self._tts("anushka")
        message = log.error.call_args[0][0]
        self.assertIn("anushka", message)
        self.assertIn("shubh", message)  # one of the speakers that would work
        self.assertIn("assistant-1", message)


class TestElevenLabsSpeedGuard(unittest.TestCase):
    """`speed` is not a v3 knob, and v3 is this platform's default ElevenLabs model."""

    def _tts(self, model, **voice_settings):
        from src.core.agents.tts.factory import create_tts

        return create_tts(
            SimpleNamespace(
                assistant_id="assistant-1",
                assistant_tts_model="elevenlabs",
                assistant_tts_config={
                    "api_key": "k",
                    "voice_id": "v1",
                    "model": model,
                    "voice_settings": {"stability": 0.4, **voice_settings},
                },
            )
        )

    def test_speed_is_dropped_on_v3(self):
        opts = self._tts("eleven_v3", speed=1.2)._opts
        self.assertIsNone(opts.voice_settings.speed)
        # The settings the model does read are untouched by the drop.
        self.assertEqual(opts.voice_settings.stability, 0.4)

    def test_speed_survives_on_a_model_that_has_it(self):
        opts = self._tts("eleven_multilingual_v2", speed=1.2)._opts
        self.assertEqual(opts.voice_settings.speed, 1.2)

    def test_the_drop_names_the_model_and_the_alternatives(self):
        with mock.patch("src.core.agents.tts.factory.logger") as log:
            self._tts("eleven_v3", speed=1.2)
        message = log.warning.call_args[0][0]
        self.assertIn("eleven_v3", message)
        self.assertIn("assistant-1", message)
        self.assertIn("eleven_multilingual_v2", message)


class TestSarvamTTSRanges(unittest.TestCase):
    """Schema bounds must match Sarvam's own, or the API 400s on a value we accepted."""

    def test_provider_limits_are_accepted(self):
        from src.api.models.api_schemas.config.tts_config import SarvamTTSConfig

        for field, value in (
            ("pace", 0.3),
            ("pace", 3.0),
            ("temperature", 0.01),
            ("speech_sample_rate", 8000),
        ):
            with self.subTest(field=field, value=value):
                SarvamTTSConfig(speaker="shubh", **{field: value})

    def test_out_of_range_values_are_rejected(self):
        from src.api.models.api_schemas.config.tts_config import SarvamTTSConfig

        for field, value in (
            ("pace", 0.2),
            ("pace", 3.1),
            ("temperature", 0.0),
            ("speech_sample_rate", 20000),  # between two supported rates, still invalid
        ):
            with self.subTest(field=field, value=value):
                with self.assertRaises(ValidationError):
                    SarvamTTSConfig(speaker="shubh", **{field: value})


class TestModeGuardrails(unittest.TestCase):
    """Combinations the runtime cannot execute must fail at the API, not at call time."""

    def _create(self, **overrides):
        payload = {
            "assistant_name": "A",
            "assistant_description": "d",
            "assistant_prompt": "p",
            "assistant_mode": "pipeline",
            "assistant_tts_model": "cartesia",
            "assistant_tts_config": {"voice_id": "v"},
        }
        payload.update(overrides)
        return CreateAssistant(**payload)

    def test_pipeline_rejects_gemini(self):
        with self.assertRaises(ValidationError) as ctx:
            self._create(assistant_llm_config={"provider": "gemini"})
        self.assertIn("realtime", str(ctx.exception))

    def test_pipeline_accepts_openai(self):
        created = self._create(assistant_llm_config={"provider": "openai"})
        self.assertEqual(created.assistant_llm_config.provider, "openai")

    def test_pipeline_rejects_a_cascade_chat_model(self):
        """gpt-4.1 speaks the Responses API, not the Realtime API — it cannot connect."""
        with self.assertRaises(ValidationError):
            self._create(assistant_llm_config={"model": "gpt-4.1"})

    def test_pipeline_accepts_a_realtime_model(self):
        created = self._create(assistant_llm_config={"model": "gpt-realtime-1.5"})
        self.assertEqual(created.assistant_llm_config.model, "gpt-realtime-1.5")

    def test_realtime_still_accepts_gemini_and_free_form_models(self):
        created = CreateAssistant(
            assistant_name="A",
            assistant_description="d",
            assistant_prompt="p",
            assistant_mode="realtime",
            assistant_llm_config={
                "provider": "gemini",
                "model": "gemini-3.1-flash-live-preview",
            },
        )
        self.assertEqual(created.assistant_llm_config.provider, "gemini")

    def test_realtime_rejects_a_chat_model_on_openai(self):
        with self.assertRaises(ValidationError):
            CreateAssistant(
                assistant_name="A",
                assistant_description="d",
                assistant_prompt="p",
                assistant_mode="realtime",
                assistant_llm_config={"provider": "openai", "model": "gpt-4.1"},
            )

    def test_update_rejects_gemini_when_the_request_names_pipeline(self):
        with self.assertRaises(ValidationError):
            UpdateAssistant(
                assistant_mode="pipeline",
                assistant_llm_config={"provider": "gemini"},
            )


class TestUnknownConfigKeys(unittest.TestCase):
    """Every provider config block is strict — a typo is a 422, not a silent no-op."""

    def test_mistral_tts_rejects_unknown_keys(self):
        from src.api.models.api_schemas.config.tts_config import MistralTTSConfig

        with self.assertRaises(ValidationError):
            MistralTTSConfig(voice_id="v", speed=1.5)

    def test_every_stt_config_rejects_unknown_keys(self):
        from src.api.models.api_schemas.config import stt_config as stt_schemas

        cases = [
            (stt_schemas.NativeSTTConfig, {}),
            (stt_schemas.SarvamSTTConfig, {}),
            (stt_schemas.CartesiaSTTConfig, {}),
            (stt_schemas.DeepgramSTTConfig, {}),
            (stt_schemas.ElevenLabsSTTConfig, {}),
            (stt_schemas.OpenAISTTConfig, {}),
        ]
        for model_cls, base in cases:
            with self.subTest(model=model_cls.__name__):
                with self.assertRaises(ValidationError):
                    model_cls(**base, enable_diarisation=True)


class TestSummarizeUsage(unittest.TestCase):
    def _usage(self):
        return AgentSessionUsage(
            model_usage=[
                LLMModelUsage(
                    provider="openai",
                    model="gpt-4.1-mini",
                    input_tokens=100,
                    input_text_tokens=90,
                    output_tokens=40,
                    output_text_tokens=40,
                ),
                # A second entry for the same component: totals must sum across them.
                LLMModelUsage(
                    provider="openai",
                    model="gpt-4o-mini",
                    input_tokens=10,
                    output_tokens=5,
                ),
                TTSModelUsage(
                    provider="cartesia",
                    model="sonic-3",
                    characters_count=250,
                    audio_duration=12.5,
                ),
                STTModelUsage(
                    provider="sarvam", model="saaras:v3", audio_duration=31.25
                ),
            ]
        )

    def test_sums_across_entries_per_component(self):
        metered = summarize_usage(SimpleNamespace(usage=self._usage()))
        self.assertEqual(metered["llm_total_tokens"], 155)  # (100+40) + (10+5)
        self.assertEqual(metered["llm_input_text_tokens"], 90)
        self.assertEqual(metered["tts_characters_count"], 250)
        self.assertEqual(metered["tts_audio_duration"], 12.5)
        self.assertEqual(metered["stt_audio_duration"], 31.25)

    def test_records_model_names(self):
        metered = summarize_usage(SimpleNamespace(usage=self._usage()))
        self.assertEqual(metered["llm_model"], "gpt-4.1-mini, gpt-4o-mini")
        self.assertEqual(metered["stt_model"], "saaras:v3")

    def test_every_key_is_a_usage_record_field(self):
        """session.py splats this dict into UsageRecord(**metered) — a stray key would
        break every call's usage record, so pin the contract here."""
        metered = summarize_usage(SimpleNamespace(usage=self._usage()))
        self.assertEqual(set(metered) - set(UsageRecord.model_fields), set())

    def test_degrades_to_zeros_instead_of_raising(self):
        metered = summarize_usage(SimpleNamespace())  # no .usage at all
        self.assertEqual(metered["llm_total_tokens"], 0)
        self.assertEqual(metered["stt_audio_duration"], 0.0)
        self.assertIsNone(metered["stt_model"])

    def test_empty_usage_reports_no_models(self):
        metered = summarize_usage(
            SimpleNamespace(usage=AgentSessionUsage(model_usage=[]))
        )
        self.assertIsNone(metered["llm_model"])
        self.assertEqual(metered["tts_characters_count"], 0)


class TestStaleKnobBackfill(unittest.TestCase):
    """scripts/migrate_llm_knobs.py — which stored knobs the backfill would clear."""

    def test_reports_only_the_knobs_the_stored_model_rejects(self):
        reasons = stale_knobs(
            {"model": "gpt-5-mini", "temperature": 0.7, "reasoning_effort": "low"}
        )
        self.assertEqual(list(reasons), ["temperature"])
        self.assertIn("reject temperature", reasons["temperature"])

    def test_clean_config_is_left_alone(self):
        self.assertEqual(stale_knobs({"model": "gpt-4.1", "temperature": 0.7}), {})
        self.assertEqual(stale_knobs({"model": "gpt-5-mini", "verbosity": "low"}), {})
        self.assertEqual(stale_knobs({}), {})

    def test_unset_model_is_judged_as_the_cascade_default(self):
        """No model on the row means gpt-4.1 at call time, so reasoning_effort is stale."""
        self.assertEqual(list(stale_knobs({"reasoning_effort": "low"})), ["reasoning_effort"])

    def test_unknown_model_is_never_guessed_at(self):
        """Same rule as the validator: a model outside the allowlist keeps every knob."""
        self.assertEqual(stale_knobs({"model": "gpt-9-turbo", "temperature": 0.7}), {})


if __name__ == "__main__":
    unittest.main()
