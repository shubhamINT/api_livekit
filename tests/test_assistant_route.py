import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi import HTTPException
from pydantic import ValidationError

from src.api.models.api_schemas import (
    NativeSTTConfig,
    UpdateAssistant,
)
from src.api.routes.assistant import (
    get_assistant_details,
    get_call_logs,
    merge_interaction_config,
    merge_llm_config,
    update_assistant,
)
from src.api.validation import effective_value
from src.core.agents.stt.factory import resolve_stt
from src.core.providers.keys import (
    SYSTEM_KEY_PLACEHOLDER,
    mask_api_key,
    mask_assistant_keys,
    provider_key_or_system,
)

sys.path.append(str(Path(__file__).resolve().parents[1] / "scripts"))
from migrate_stt_config import legacy_to_stt

from src.core.db.db_schemas import AssistantInteractionConfig


class QueryField:
    def __eq__(self, other):
        return other


class TestAssistantRoute(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        # The update route asks OpenAI two things: whether it still serves the model, and
        # whether it accepts this exact request. Both stubbed here so the suite never touches
        # the network — the gates themselves are covered by tests/test_live_model_check.py.
        for target in (
            "src.api.validation.assistant_guard.unavailable_model_reason",
            "src.api.validation.assistant_guard.rejected_config_reason",
        ):
            patcher = patch(target, AsyncMock(return_value=None))
            self.addCleanup(patcher.stop)
            patcher.start()

    async def test_get_call_logs_includes_nested_usage(self):
        user = SimpleNamespace(user_email="user@example.com")
        assistant = SimpleNamespace()
        call = SimpleNamespace(
            room_name="room-1",
            model_dump=lambda **_: {"room_name": "room-1", "call_status": "completed"},
        )
        call_query = Mock()
        call_query.count = AsyncMock(return_value=1)
        call_query.sort.return_value = call_query
        call_query.skip.return_value = call_query
        call_query.limit.return_value = call_query
        call_query.to_list = AsyncMock(return_value=[call])
        usage = SimpleNamespace(
            room_name="room-1",
            model_dump_json=lambda **_: '{"room_name":"room-1","estimated_cost_usd":"0.0234","pricing_complete":true}',
        )
        usage_query = Mock()
        usage_query.to_list = AsyncMock(return_value=[usage])
        assistant_model = SimpleNamespace(
            assistant_id=QueryField(),
            assistant_created_by_email=QueryField(),
            assistant_is_active=QueryField(),
            find_one=AsyncMock(return_value=assistant),
        )
        call_model = SimpleNamespace(
            assistant_id=QueryField(),
            started_at=QueryField(),
            find=Mock(return_value=call_query),
        )
        usage_model = SimpleNamespace(
            find=Mock(return_value=usage_query),
        )

        with patch("src.api.routes.assistant.Assistant", assistant_model), patch(
            "src.api.routes.assistant.CallRecord", call_model
        ), patch("src.api.routes.assistant.UsageRecord", usage_model):
            response = await get_call_logs(
                "assistant-1", page=1, limit=10, start_date=None, end_date=None,
                sort_by="started_at", sort_order="desc", current_user=user,
            )

        self.assertEqual(response.data["logs"][0]["usage"]["estimated_cost_usd"], "0.0234")
        self.assertTrue(response.data["logs"][0]["usage"]["pricing_complete"])
        usage_model.find.assert_called_once_with({"room_name": {"$in": ["room-1"]}})

    async def test_get_call_logs_returns_null_usage_when_record_missing(self):
        user = SimpleNamespace(user_email="user@example.com")
        assistant = SimpleNamespace()
        call = SimpleNamespace(
            room_name="room-without-usage",
            model_dump=lambda **_: {"room_name": "room-without-usage"},
        )
        call_query = Mock()
        call_query.count = AsyncMock(return_value=1)
        call_query.sort.return_value = call_query
        call_query.skip.return_value = call_query
        call_query.limit.return_value = call_query
        call_query.to_list = AsyncMock(return_value=[call])
        usage_query = Mock()
        usage_query.to_list = AsyncMock(return_value=[])
        assistant_model = SimpleNamespace(
            assistant_id=QueryField(),
            assistant_created_by_email=QueryField(),
            assistant_is_active=QueryField(),
            find_one=AsyncMock(return_value=assistant),
        )
        call_model = SimpleNamespace(
            assistant_id=QueryField(),
            started_at=QueryField(),
            find=Mock(return_value=call_query),
        )
        usage_model = SimpleNamespace(find=Mock(return_value=usage_query))

        with patch("src.api.routes.assistant.Assistant", assistant_model), patch(
            "src.api.routes.assistant.CallRecord", call_model
        ), patch("src.api.routes.assistant.UsageRecord", usage_model):
            response = await get_call_logs(
                "assistant-1", page=1, limit=10, start_date=None, end_date=None,
                sort_by="started_at", sort_order="desc", current_user=user,
            )

        self.assertIsNone(response.data["logs"][0]["usage"])

    async def test_update_assistant_merges_partial_interaction_config(self):
        request = UpdateAssistant(
            assistant_interaction_config={
                "thinking_sound_enabled": False,
            }
        )
        current_user = SimpleNamespace(user_email="user@example.com")
        assistant = SimpleNamespace(
            assistant_mode="pipeline",
            assistant_interaction_config=AssistantInteractionConfig(
                speaks_first=True,
                filler_words=True,
                silence_reprompts=True,
                silence_reprompt_interval=12.0,
                silence_max_reprompts=3,
                background_sound_enabled=True,
                thinking_sound_enabled=True,
            ),
            update=AsyncMock(),
        )

        assistant_model = SimpleNamespace(
            assistant_id=QueryField(),
            assistant_created_by_email=QueryField(),
            find_one=AsyncMock(return_value=assistant),
        )

        with patch("src.api.routes.assistant.Assistant", assistant_model):
            response = await update_assistant(
                assistant_id="assistant-1",
                request=request,
                current_user=current_user,
            )

        self.assertTrue(response.success)
        assistant.update.assert_awaited_once()
        update_doc = assistant.update.await_args.args[0]["$set"]
        self.assertEqual(update_doc["assistant_interaction_config"]["speaks_first"], True)
        self.assertEqual(update_doc["assistant_interaction_config"]["filler_words"], True)
        self.assertEqual(
            update_doc["assistant_interaction_config"]["background_sound_enabled"],
            True,
        )
        self.assertEqual(
            update_doc["assistant_interaction_config"]["thinking_sound_enabled"],
            False,
        )

    async def _patch_llm_config(self, stored_llm, requested_llm, **stored):
        """Run PATCH /update with a stored llm_config and return the written $set doc."""
        request = UpdateAssistant(assistant_llm_config=requested_llm, **stored.pop("request", {}))
        assistant = SimpleNamespace(
            assistant_mode=stored.pop("assistant_mode", "cascade"),
            assistant_llm_config=stored_llm,
            assistant_stt_model=stored.pop("assistant_stt_model", "sarvam"),
            assistant_tts_model=stored.pop("assistant_tts_model", "cartesia"),
            assistant_interaction_config=AssistantInteractionConfig(),
            update=AsyncMock(),
            **stored,
        )
        assistant_model = SimpleNamespace(
            assistant_id=QueryField(),
            assistant_created_by_email=QueryField(),
            find_one=AsyncMock(return_value=assistant),
        )

        with patch("src.api.routes.assistant.Assistant", assistant_model):
            await update_assistant(
                assistant_id="assistant-1",
                request=request,
                current_user=SimpleNamespace(user_email="user@example.com"),
            )
        return assistant.update.await_args.args[0]["$set"]["assistant_llm_config"]

    async def test_update_assistant_merges_partial_llm_config(self):
        """A PATCH naming one key must not drop provider, api_key or the other knobs."""
        merged = await self._patch_llm_config(
            {
                "provider": "openai",
                "model": "gpt-5-mini",
                "api_key": "sk-stored-12345678",
                "reasoning_effort": "low",
                "max_output_tokens": 512,
            },
            {"model": "gpt-5-nano"},
        )

        self.assertEqual(
            merged,
            {
                "provider": "openai",
                "model": "gpt-5-nano",
                "api_key": "sk-stored-12345678",
                "reasoning_effort": "low",
                "max_output_tokens": 512,
            },
        )

    async def test_update_assistant_null_clears_a_stale_knob(self):
        """The documented way out of a knob the new model rejects: send it as null."""
        merged = await self._patch_llm_config(
            {"provider": "openai", "model": "gpt-4.1", "temperature": 0.7},
            {"model": "gpt-5-mini", "temperature": None},
        )

        self.assertNotIn("temperature", merged)
        self.assertEqual(merged["model"], "gpt-5-mini")

    async def test_update_assistant_rejects_a_stale_knob_left_in_place(self):
        """Omitting the knob keeps it, so the model switch is still refused — with a reason."""
        with self.assertRaises(HTTPException) as ctx:
            await self._patch_llm_config(
                {"provider": "openai", "model": "gpt-4.1", "temperature": 0.7},
                {"model": "gpt-5-mini"},
            )

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("temperature", ctx.exception.detail)

    async def test_leaving_realtime_replaces_llm_config_instead_of_merging(self):
        """A stored Gemini voice/key must not survive under an OpenAI provider."""
        merged = await self._patch_llm_config(
            {"provider": "gemini", "model": "gemini-3.1-flash-live-preview", "voice": "Puck", "api_key": "goog-123456789"},
            {"provider": "openai", "model": "gpt-4.1"},
            assistant_mode="realtime",
            request={"assistant_mode": "cascade"},
        )

        self.assertEqual(merged, {"provider": "openai", "model": "gpt-4.1"})

    def test_merge_llm_config_drops_cleared_keys(self):
        merged = merge_llm_config(
            {"provider": "openai", "model": "gpt-5-mini", "verbosity": "low"},
            {"verbosity": None, "reasoning_effort": "high"},
        )

        self.assertEqual(
            merged,
            {"provider": "openai", "model": "gpt-5-mini", "reasoning_effort": "high"},
        )
        # A row that has never held an llm_config still merges cleanly.
        self.assertEqual(merge_llm_config(None, {"model": "gpt-4.1"}), {"model": "gpt-4.1"})

    def test_merge_interaction_config_accepts_model_or_dict(self):
        merged_from_model = merge_interaction_config(
            AssistantInteractionConfig(background_sound_enabled=False),
            {"thinking_sound_enabled": False},
        )
        merged_from_dict = merge_interaction_config(
            {"speaks_first": True},
            {"background_sound_enabled": False},
        )

        self.assertEqual(merged_from_model["background_sound_enabled"], False)
        self.assertEqual(merged_from_model["thinking_sound_enabled"], False)
        self.assertEqual(merged_from_dict["speaks_first"], True)
        self.assertEqual(merged_from_dict["background_sound_enabled"], False)

    async def test_get_assistant_details_masks_llm_config_api_key(self):
        current_user = SimpleNamespace(user_email="user@example.com")
        assistant = SimpleNamespace(
            model_dump=lambda exclude=None: {
                "assistant_id": "assistant-1",
                "assistant_name": "Masked Bot",
                "assistant_llm_config": {"api_key": "sk-test-12345678"},
                "assistant_tts_config": None,
            }
        )

        assistant_model = SimpleNamespace(
            assistant_id=QueryField(),
            assistant_created_by_email=QueryField(),
            assistant_is_active=QueryField(),
            find_one=AsyncMock(return_value=assistant),
        )

        with patch("src.api.routes.assistant.Assistant", assistant_model):
            response = await get_assistant_details(
                assistant_id="assistant-1",
                current_user=current_user,
            )

        self.assertTrue(response.success)
        self.assertEqual(
            response.data["assistant_llm_config"]["api_key"],
            "sk-t...5678",
        )


class TestEffectiveValue(unittest.TestCase):
    """Every guard has to resolve "the PATCH's value, else the row's" the same way.

    This used to be hand-rolled at four call sites with three different mechanics, which is how
    a newly guarded field ends up checked in one place and missed in the others.
    """

    def setUp(self):
        self.assistant = SimpleNamespace(
            assistant_tts_model="cartesia", tool_ids=["t1"], assistant_end_call_enabled=True
        )

    def test_the_patch_wins_when_it_names_the_field(self):
        self.assertEqual(
            effective_value(self.assistant, {"assistant_tts_model": "sarvam"}, "assistant_tts_model"),
            "sarvam",
        )

    def test_the_stored_value_stands_when_the_patch_omits_it(self):
        self.assertEqual(
            effective_value(self.assistant, {}, "assistant_tts_model"), "cartesia"
        )

    def test_an_explicit_null_clears_rather_than_falling_back(self):
        """Key presence, not truthiness — a null is the documented way to clear a field."""
        self.assertIsNone(
            effective_value(self.assistant, {"assistant_tts_model": None}, "assistant_tts_model")
        )

    def test_an_empty_list_is_a_value_not_an_absence(self):
        """Detaching the last tool must read as "no tools", not as "keep the stored ones"."""
        self.assertEqual(effective_value(self.assistant, {"tool_ids": []}, "tool_ids"), [])

    def test_a_field_absent_from_both_is_none(self):
        self.assertIsNone(effective_value(self.assistant, {}, "assistant_stt_model"))


class TestMaskedKeyGuard(unittest.TestCase):
    """A masked key read from GET /details must never be writable back."""

    def test_masked_tts_key_rejected_for_every_provider(self):
        configs = {
            "cartesia": {"voice_id": "v1"},
            "sarvam": {"speaker": "shubh"},
            "elevenlabs": {"voice_id": "v1"},
            "mistral": {"voice_id": "v1"},
        }
        for provider, base in configs.items():
            for masked in ("sk-t...5678", "****", SYSTEM_KEY_PLACEHOLDER):
                with self.subTest(provider=provider, masked=masked):
                    with self.assertRaises(ValidationError):
                        UpdateAssistant(
                            assistant_tts_model=provider,
                            assistant_tts_config={**base, "api_key": masked},
                        )

    def test_masked_llm_key_rejected(self):
        with self.assertRaises(ValidationError):
            UpdateAssistant(assistant_llm_config={"provider": "openai", "api_key": "sk-t...5678"})

    def test_masked_stt_key_rejected_for_every_provider(self):
        for provider in ("sarvam", "cartesia", "deepgram", "elevenlabs", "openai"):
            for masked in ("sk-t...5678", "****", SYSTEM_KEY_PLACEHOLDER):
                with self.subTest(provider=provider, masked=masked):
                    with self.assertRaises(ValidationError):
                        UpdateAssistant(
                            assistant_stt_model=provider,
                            assistant_stt_config={"api_key": masked},
                        )

    def test_real_keys_accepted(self):
        request = UpdateAssistant(
            assistant_tts_model="cartesia",
            assistant_tts_config={"voice_id": "v1", "api_key": "sk_cartesia_real_key"},
            assistant_llm_config={"provider": "openai", "api_key": "sk-proj-realkey"},
            assistant_stt_model="sarvam",
            assistant_stt_config={"api_key": "sk_sarvam_real_key"},
        )
        self.assertEqual(request.assistant_tts_config.api_key, "sk_cartesia_real_key")
        self.assertEqual(request.assistant_stt_config.api_key, "sk_sarvam_real_key")

    def test_omitted_keys_accepted(self):
        request = UpdateAssistant(
            assistant_tts_model="sarvam",
            assistant_tts_config={"speaker": "shubh"},
        )
        self.assertIsNone(request.assistant_tts_config.api_key)


class TestSTTConfig(unittest.TestCase):
    """assistant_stt_model / assistant_stt_config mirror the TTS pair."""

    def test_bare_model_gets_defaults_config(self):
        request = UpdateAssistant(assistant_stt_model="sarvam")
        self.assertEqual(request.assistant_stt_config.model, "saaras:v3")
        self.assertEqual(request.assistant_stt_config.language, "unknown")
        self.assertIsNone(request.assistant_stt_config.api_key)

    def test_discriminator_injected_from_model(self):
        request = UpdateAssistant(assistant_stt_model="native", assistant_stt_config={})
        self.assertIsInstance(request.assistant_stt_config, NativeSTTConfig)

    def test_config_without_model_rejected(self):
        with self.assertRaises(ValidationError):
            UpdateAssistant(assistant_stt_config={"type": "sarvam"})

    def test_retired_interaction_fields_rejected(self):
        for field in ("user_stt_provider", "stt_api_key"):
            with self.subTest(field=field):
                with self.assertRaises(ValidationError):
                    UpdateAssistant(assistant_interaction_config={field: "sarvam"})


class TestResolveSTT(unittest.TestCase):
    def test_unset_defaults_to_sarvam(self):
        assistant = SimpleNamespace(assistant_stt_model=None, assistant_stt_config=None)
        self.assertEqual(resolve_stt(assistant), ("sarvam", {}))

    def test_legacy_openai_maps_to_native(self):
        assistant = SimpleNamespace(assistant_stt_model="openai", assistant_stt_config=None)
        self.assertEqual(resolve_stt(assistant), ("native", {}))

    def test_no_key_anywhere_degrades_to_native(self):
        """An unauthenticated Sarvam tap would leave the call with no transcripts at all."""
        assistant = SimpleNamespace(
            assistant_id="assistant-1", assistant_stt_model="sarvam", assistant_stt_config={}
        )
        with patch("src.core.agents.stt.factory.settings.SARVAM_API_KEY", ""):
            self.assertEqual(resolve_stt(assistant), ("native", {}))

    def test_per_assistant_key_survives_missing_system_key(self):
        assistant = SimpleNamespace(
            assistant_id="assistant-1",
            assistant_stt_model="sarvam",
            assistant_stt_config={"api_key": "sk_x"},
        )
        with patch("src.core.agents.stt.factory.settings.SARVAM_API_KEY", ""):
            self.assertEqual(resolve_stt(assistant), ("sarvam", {"api_key": "sk_x"}))

    def test_returns_stored_config(self):
        config = {"type": "sarvam", "api_key": "sk_x", "language": "hi-IN"}
        assistant = SimpleNamespace(assistant_stt_model="sarvam", assistant_stt_config=config)
        self.assertEqual(resolve_stt(assistant), ("sarvam", config))

    def test_cascade_only_provider_without_key_degrades_to_native(self):
        for provider, env in (
            ("cartesia", "CARTESIA_API_KEY"),
            ("deepgram", "DEEPGRAM_API_KEY"),
            ("elevenlabs", "ELEVENLABS_API_KEY"),
        ):
            with self.subTest(provider=provider), patch(
                f"src.core.agents.stt.factory.settings.{env}", ""
            ):
                assistant = SimpleNamespace(
                    assistant_id="assistant-1",
                    assistant_stt_model=provider,
                    assistant_stt_config={},
                )
                self.assertEqual(resolve_stt(assistant), ("native", {}))

    def test_openai_stt_collapses_to_native_in_pipeline(self):
        """Same vendor, same model as the realtime model's own transcription — a second
        connection would buy nothing. Also keeps pre-migration 'openai' rows working."""
        assistant = SimpleNamespace(
            assistant_id="assistant-1",
            assistant_stt_model="openai",
            assistant_stt_config={"api_key": "sk_x"},
        )
        self.assertEqual(resolve_stt(assistant), ("native", {"api_key": "sk_x"}))

    def test_cascade_only_provider_with_config_key_is_kept(self):
        for provider in ("deepgram", "elevenlabs"):
            with self.subTest(provider=provider):
                assistant = SimpleNamespace(
                    assistant_id="assistant-1",
                    assistant_stt_model=provider,
                    assistant_stt_config={"api_key": "sk_x"},
                )
                model, config = resolve_stt(assistant)
                self.assertEqual(model, provider)
                self.assertEqual(config["api_key"], "sk_x")


class TestSTTBackfill(unittest.TestCase):
    """scripts/migrate_stt_config.py translation — the part that can lose a customer key."""

    def test_sarvam_key_carried_over(self):
        self.assertEqual(
            legacy_to_stt({"user_stt_provider": "sarvam", "stt_api_key": "sk_x"}),
            ("sarvam", {"type": "sarvam", "api_key": "sk_x"}),
        )

    def test_legacy_openai_alias(self):
        self.assertEqual(legacy_to_stt({"user_stt_provider": "openai"}), ("native", {"type": "native"}))

    def test_missing_fields_default_to_sarvam(self):
        self.assertEqual(legacy_to_stt({}), ("sarvam", {"type": "sarvam"}))

    def test_native_drops_stale_sarvam_key(self):
        self.assertEqual(
            legacy_to_stt({"user_stt_provider": "native", "stt_api_key": "sk_x"}),
            ("native", {"type": "native"}),
        )


class TestMaskApiKey(unittest.TestCase):
    def test_masks_named_field(self):
        masked = mask_api_key({"api_key": "sk_sarvam_1234"})
        self.assertEqual(masked["api_key"], "sk_s...1234")

    def test_absent_key_still_announces_system_fallback_by_default(self):
        self.assertEqual(mask_api_key({"voice_id": "v1"})["api_key"], SYSTEM_KEY_PLACEHOLDER)

    def test_short_key_fully_hidden(self):
        self.assertEqual(mask_api_key({"api_key": "short"})["api_key"], "****")


class TestMaskAssistantKeys(unittest.TestCase):
    """Every key-bearing config is masked; native STT is left alone."""

    def test_masks_all_key_bearing_configs(self):
        masked = mask_assistant_keys(
            {
                "assistant_tts_config": {"type": "cartesia", "api_key": "sk_cartesia_1234"},
                "assistant_stt_config": {"type": "sarvam", "api_key": "sk_sarvam_1234"},
                "assistant_llm_config": {"provider": "openai", "api_key": "sk-proj-12345678"},
            }
        )
        self.assertEqual(masked["assistant_tts_config"]["api_key"], "sk_c...1234")
        self.assertEqual(masked["assistant_stt_config"]["api_key"], "sk_s...1234")
        self.assertEqual(masked["assistant_llm_config"]["api_key"], "sk-p...5678")

    def test_native_stt_config_untouched(self):
        masked = mask_assistant_keys({"assistant_stt_config": {"type": "native"}})
        self.assertEqual(masked["assistant_stt_config"], {"type": "native"})

class TestProviderKeyOrSystem(unittest.TestCase):
    """A key belonging to one provider must never be sent to another (see 6e77183)."""

    def test_matching_provider_uses_assistant_key(self):
        config = {"provider": "openai", "api_key": "sk-proj-assistant"}
        self.assertEqual(
            provider_key_or_system(config, "openai", "openai", "sk-system"),
            "sk-proj-assistant",
        )

    def test_other_provider_falls_back_to_system_key(self):
        config = {"provider": "gemini", "api_key": "google-key"}
        self.assertEqual(
            provider_key_or_system(config, "gemini", "openai", "sk-system"),
            "sk-system",
        )

    def test_no_config_falls_back_to_system_key(self):
        self.assertEqual(provider_key_or_system(None, None, "openai", "sk-system"), "sk-system")


if __name__ == "__main__":
    unittest.main()
