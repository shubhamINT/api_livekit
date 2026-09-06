import json
import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from src.core.billing import calculate_billable_duration_minutes
from src.core.db.db_schemas import UsageRecord
from src.services.livekit import livekit_svc
from src.services.livekit.livekit_svc import LiveKitService


class FakeCallRecord:
    def __init__(self, status="initiated", answered_at=None):
        self.room_name = "room-1"
        self.assistant_id = "assistant-1"
        self.assistant_name = "Assistant"
        self.to_number = "+911234567890"
        self.call_status = status
        self.call_status_reason = None
        self.sip_status_code = None
        self.sip_status_text = None
        self.answered_at = answered_at
        self.recording_path = None
        self.recording_egress_id = "EG_test_123"
        self.transcripts = []
        self.started_at = datetime.now(UTC) - timedelta(minutes=1)
        self.ended_at = None
        self.call_duration_minutes = None
        self.billable_duration_minutes = None

    async def save(self):
        return None

    def model_dump_json(self):
        return json.dumps(
            {
                "id": "mongo-id",
                "room_name": self.room_name,
                "assistant_id": self.assistant_id,
                "assistant_name": self.assistant_name,
                "to_number": self.to_number,
                "call_status": self.call_status,
                "call_status_reason": self.call_status_reason,
                "sip_status_code": self.sip_status_code,
                "sip_status_text": self.sip_status_text,
                "answered_at": self.answered_at.isoformat() if self.answered_at else None,
                "recording_path": self.recording_path,
                "transcripts": self.transcripts,
                "started_at": self.started_at.isoformat(),
                "ended_at": self.ended_at.isoformat() if self.ended_at else None,
                "call_duration_minutes": self.call_duration_minutes,
                "billable_duration_minutes": self.billable_duration_minutes,
                "created_by_email": "user@example.com",
                "call_type": "outbound",
                "call_service": "exotel",
                "platform_number": "08044319240",
            }
        )


class RoomNameField:
    def __eq__(self, other):
        return other

    def __ne__(self, other):
        return other


class FakeActivityLog:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def insert(self):
        return None


class TestLiveKitLifecycle(unittest.IsolatedAsyncioTestCase):
    def test_calculate_billable_duration_minutes_rounds_up_connected_calls(self):
        self.assertEqual(calculate_billable_duration_minutes("completed", 0.30), 1)
        self.assertEqual(calculate_billable_duration_minutes("completed", 1.25), 2)
        self.assertEqual(calculate_billable_duration_minutes("completed", 2.0), 2)
        self.assertEqual(calculate_billable_duration_minutes("failed", 1.25), 0)

    async def test_end_call_prefers_answered_at_for_duration(self):
        svc = LiveKitService()
        answered_at = datetime.now(UTC) - timedelta(seconds=30)
        record = FakeCallRecord(status="answered", answered_at=answered_at)

        with patch("src.services.livekit.livekit_svc.CallRecord") as call_record_model:
            call_record_model.room_name = RoomNameField()
            call_record_model.find_one = AsyncMock(return_value=record)
            svc.stop_room_recording = AsyncMock(return_value=True)
            svc.send_end_call_webhook = AsyncMock(return_value=True)

            await svc.end_call(room_name="room-1", assistant_id="assistant-1")

            self.assertEqual(record.call_status, "completed")
            self.assertIsNotNone(record.ended_at)
            self.assertAlmostEqual(record.call_duration_minutes * 60, 30, delta=2)
            self.assertEqual(record.billable_duration_minutes, 1)
            svc.stop_room_recording.assert_awaited_once_with("EG_test_123")
            self.assertEqual(svc.send_end_call_webhook.await_count, 1)

    async def test_end_call_falls_back_to_started_at_when_answered_missing(self):
        svc = LiveKitService()
        record = FakeCallRecord(status="initiated")

        with patch("src.services.livekit.livekit_svc.CallRecord") as call_record_model:
            call_record_model.room_name = RoomNameField()
            call_record_model.find_one = AsyncMock(return_value=record)
            svc.stop_room_recording = AsyncMock(return_value=True)
            svc.send_end_call_webhook = AsyncMock(return_value=True)
            await svc.end_call(room_name="room-1", assistant_id="assistant-1")

            self.assertAlmostEqual(record.call_duration_minutes * 60, 60, delta=2)
            self.assertEqual(
                record.billable_duration_minutes,
                calculate_billable_duration_minutes("completed", record.call_duration_minutes),
            )
            self.assertEqual(svc.send_end_call_webhook.await_count, 1)

    async def test_end_call_skips_duplicate_completed_status(self):
        svc = LiveKitService()
        record = FakeCallRecord(status="completed")

        with patch("src.services.livekit.livekit_svc.CallRecord") as call_record_model:
            call_record_model.room_name = RoomNameField()
            call_record_model.find_one = AsyncMock(return_value=record)
            svc.stop_room_recording = AsyncMock(return_value=True)
            svc.send_end_call_webhook = AsyncMock(return_value=True)

            await svc.end_call(room_name="room-1", assistant_id="assistant-1")

            svc.stop_room_recording.assert_not_awaited()
            svc.send_end_call_webhook.assert_not_awaited()

    async def test_update_call_status_sets_zero_billable_for_failed_call(self):
        svc = LiveKitService()
        record = FakeCallRecord(status="initiated")

        with patch("src.services.livekit.livekit_svc.CallRecord") as call_record_model:
            call_record_model.room_name = RoomNameField()
            call_record_model.find_one = AsyncMock(return_value=record)

            await svc.update_call_status(
                room_name="room-1",
                call_status="failed",
                ended_at=datetime.now(UTC),
                call_duration_minutes=0,
            )

            self.assertEqual(record.call_status, "failed")
            self.assertEqual(record.billable_duration_minutes, 0)

    async def test_send_end_call_webhook_includes_billable_duration_minutes(self):
        svc = LiveKitService()
        record = FakeCallRecord(status="completed")
        record.call_duration_minutes = 1.25
        record.billable_duration_minutes = 2
        posted = {}

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, json):
                posted["url"] = url
                posted["payload"] = json
                return SimpleNamespace(status_code=200, text="{\"received\": true}")

        assistant_model = SimpleNamespace(
            assistant_id=RoomNameField(),
            assistant_end_call_url=RoomNameField(),
            find_one=AsyncMock(
                return_value=SimpleNamespace(
                    assistant_end_call_url="https://example.com/webhook",
                    assistant_created_by_email="user@example.com",
                )
            ),
        )
        call_record_model = SimpleNamespace(
            room_name=RoomNameField(),
            find_one=AsyncMock(return_value=record),
        )
        usage_record_model = SimpleNamespace(
            room_name=RoomNameField(),
            find_one=AsyncMock(return_value=None),
        )

        with patch("src.services.livekit.livekit_svc.CallRecord", call_record_model), patch(
            "src.services.livekit.livekit_svc.Assistant", assistant_model
        ), patch("src.services.livekit.livekit_svc.UsageRecord", usage_record_model), patch(
            "src.services.livekit.livekit_svc.ActivityLog", FakeActivityLog
        ), patch("src.services.livekit.livekit_svc.httpx.AsyncClient", FakeAsyncClient):
            await svc.send_end_call_webhook(room_name="room-1", assistant_id="assistant-1")

        self.assertEqual(posted["url"], "https://example.com/webhook")
        self.assertEqual(posted["payload"]["data"]["call_duration_minutes"], 1.25)
        self.assertEqual(posted["payload"]["data"]["billable_duration_minutes"], 2)

    async def test_send_end_call_webhook_reports_per_component_usage(self):
        """A cascade call meters STT separately, so the webhook must carry the STT fields."""
        svc = LiveKitService()
        record = FakeCallRecord(status="completed")
        record.call_duration_minutes = 1.0
        record.billable_duration_minutes = 1
        posted = {}

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, json):
                posted["payload"] = json
                return SimpleNamespace(status_code=200, text="{\"received\": true}")

        assistant_model = SimpleNamespace(
            assistant_id=RoomNameField(),
            assistant_end_call_url=RoomNameField(),
            find_one=AsyncMock(
                return_value=SimpleNamespace(
                    assistant_end_call_url="https://example.com/webhook",
                    assistant_created_by_email="user@example.com",
                )
            ),
        )
        usage_record_model = SimpleNamespace(
            room_name=RoomNameField(),
            # Built from the real document so every field the webhook reads exists with
            # its default — a hand-listed stub breaks whenever a usage field is added.
            find_one=AsyncMock(
                return_value=UsageRecord.model_construct(
                    mode="cascade",
                    llm_model="gpt-4.1-mini",
                    llm_input_text_tokens=90,
                    llm_input_cached_text_tokens=60,
                    llm_output_text_tokens=40,
                    llm_total_tokens=155,
                    tts_characters_count=250,
                    tts_audio_duration=12.5,
                    stt_provider="sarvam",
                    stt_model="saaras:v3",
                    stt_audio_duration=31.25,
                     model_usage=[{"type": "stt_usage", "provider": "sarvam", "model": "saaras:v3"}],
                     estimated_cost_usd=Decimal("0.0123"),
                     pricing_schema_version=1,
                     pricing_complete=True,
                     sdk_version="1.7.1",
                    call_duration_minutes=1.0,
                    call_service="exotel",
                    tts_provider="cartesia",
                    llm_realtime_provider="openai",
                    llm_input_tokens=100,
                    llm_output_tokens=50,
                )
            ),
        )

        with patch(
            "src.services.livekit.livekit_svc.CallRecord",
            SimpleNamespace(room_name=RoomNameField(), find_one=AsyncMock(return_value=record)),
        ), patch("src.services.livekit.livekit_svc.Assistant", assistant_model), patch(
            "src.services.livekit.livekit_svc.UsageRecord", usage_record_model
        ), patch("src.services.livekit.livekit_svc.ActivityLog", FakeActivityLog), patch(
            "src.services.livekit.livekit_svc.httpx.AsyncClient", FakeAsyncClient
        ):
            await svc.send_end_call_webhook(room_name="room-1", assistant_id="assistant-1")

        usage = posted["payload"]["data"]["usage"]
        self.assertEqual(usage["mode"], "cascade")
        self.assertEqual(usage["llm_model"], "gpt-4.1-mini")
        self.assertEqual(usage["stt_provider"], "sarvam")
        self.assertEqual(usage["stt_model"], "saaras:v3")
        self.assertEqual(usage["stt_audio_duration"], 31.25)
        self.assertEqual(usage["tts_characters_count"], 250)
        self.assertEqual(usage["llm_total_tokens"], 155)
        self.assertEqual(usage["llm_input_cached_text_tokens"], 60)
        self.assertEqual(usage["estimated_cost_usd"], "0.0123")
        self.assertTrue(usage["pricing_complete"])
        self.assertEqual(usage["usage_schema_version"], 1)
        self.assertEqual(usage["model_usage"][0]["provider"], "sarvam")
        self.assertEqual(usage["sdk_version"], "1.7.1")
        self.assertEqual(usage["llm_input_tokens"], 100)
        self.assertEqual(usage["llm_output_tokens"], 50)
        self.assertEqual(usage["call_duration_minutes"], 1.0)
        self.assertEqual(usage["call_service"], "exotel")
        self.assertEqual(usage["tts_provider"], "cartesia")
        self.assertEqual(usage["llm_realtime_provider"], "openai")

    async def test_send_end_call_webhook_logs_non_2xx_as_error(self):
        """A rejecting customer endpoint must not be recorded as a successful delivery."""
        svc = LiveKitService()
        record = FakeCallRecord(status="completed")
        record.call_duration_minutes = 1.0
        record.billable_duration_minutes = 1
        logged = []

        class CapturingActivityLog(FakeActivityLog):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                logged.append(kwargs)

        class FakeAsyncClient:
            def __init__(self, *args, **kwargs):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, tb):
                return False

            async def post(self, url, json):
                return SimpleNamespace(status_code=500, text="boom")

        assistant_model = SimpleNamespace(
            assistant_id=RoomNameField(),
            assistant_end_call_url=RoomNameField(),
            find_one=AsyncMock(
                return_value=SimpleNamespace(
                    assistant_end_call_url="https://example.com/webhook",
                    assistant_created_by_email="user@example.com",
                )
            ),
        )

        with patch(
            "src.services.livekit.livekit_svc.CallRecord",
            SimpleNamespace(room_name=RoomNameField(), find_one=AsyncMock(return_value=record)),
        ), patch("src.services.livekit.livekit_svc.Assistant", assistant_model), patch(
            "src.services.livekit.livekit_svc.UsageRecord",
            SimpleNamespace(room_name=RoomNameField(), find_one=AsyncMock(return_value=None)),
        ), patch("src.services.livekit.livekit_svc.ActivityLog", CapturingActivityLog), patch(
            "src.services.livekit.livekit_svc.httpx.AsyncClient", FakeAsyncClient
        ), patch("src.services.livekit.livekit_svc.asyncio.sleep", AsyncMock()):
            # 500 is retryable, so this exercises the give-up path; the backoff sleep is
            # patched out to keep the suite fast.
            await svc.send_end_call_webhook(room_name="room-1", assistant_id="assistant-1")

        self.assertEqual(len(logged), 1)
        self.assertEqual(logged[0]["status"], "error")
        self.assertEqual(logged[0]["response_data"], {"status_code": 500, "body": "boom"})

    async def test_send_end_call_webhook_skips_when_no_url_configured(self):
        """No configured URL is the most common 'webhook not hit' cause — must not POST."""
        svc = LiveKitService()
        record = FakeCallRecord(status="completed")
        logged = []

        class ExplodingAsyncClient:
            def __init__(self, *args, **kwargs):
                raise AssertionError("must not attempt a POST without a resolved url")

        class CapturingActivityLog(FakeActivityLog):
            def __init__(self, **kwargs):
                super().__init__(**kwargs)
                logged.append(kwargs)

        assistant_model = SimpleNamespace(
            assistant_id=RoomNameField(),
            assistant_end_call_url=RoomNameField(),
            find_one=AsyncMock(return_value=None),
        )

        with patch(
            "src.services.livekit.livekit_svc.CallRecord",
            SimpleNamespace(room_name=RoomNameField(), find_one=AsyncMock(return_value=record)),
        ), patch("src.services.livekit.livekit_svc.Assistant", assistant_model), patch(
            "src.services.livekit.livekit_svc.ActivityLog", CapturingActivityLog
        ), patch("src.services.livekit.livekit_svc.httpx.AsyncClient", ExplodingAsyncClient):
            await svc.send_end_call_webhook(room_name="room-1", assistant_id="assistant-1")

        self.assertEqual(logged, [])


class ScriptedAsyncClient:
    """httpx.AsyncClient stand-in that replays a scripted list of results per POST.

    Each entry is either an exception to raise or an object with status_code/text.
    Records how many POSTs were attempted so retry behaviour can be asserted.
    """

    def __init__(self, script):
        self.script = list(script)
        self.attempts = 0

    def factory(self, *args, **kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def post(self, url, json=None):
        self.attempts += 1
        result = self.script.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class TestEndCallWebhookRetries(unittest.IsolatedAsyncioTestCase):
    """A slow or flaky receiver must not lose the post-call payload on the first try."""

    async def _post(self, script, attempts=3):
        svc = LiveKitService()
        client = ScriptedAsyncClient(script)
        with patch("src.services.livekit.livekit_svc.httpx.AsyncClient", client.factory), patch(
            "src.services.livekit.livekit_svc.asyncio.sleep", AsyncMock()
        ), patch.object(
            livekit_svc.settings, "END_CALL_WEBHOOK_ATTEMPTS", attempts
        ):
            result = await svc._post_end_call_webhook("https://hook.example/end", {}, "room-1")
        return result, client.attempts

    async def test_read_timeout_is_retried_and_then_succeeds(self):
        (status, response_data, _), attempts = await self._post(
            [httpx.ReadTimeout("timed out"), SimpleNamespace(status_code=200, text="ok")]
        )
        self.assertEqual(status, "success")
        self.assertEqual(response_data["status_code"], 200)
        self.assertEqual(attempts, 2)

    async def test_4xx_is_not_retried(self):
        (status, response_data, message), attempts = await self._post(
            [SimpleNamespace(status_code=422, text="bad payload")]
        )
        self.assertEqual(status, "error")
        self.assertEqual(response_data["status_code"], 422)
        self.assertIn("422", message)
        self.assertEqual(attempts, 1)

    async def test_5xx_is_retried_until_attempts_are_exhausted(self):
        (status, response_data, _), attempts = await self._post(
            [SimpleNamespace(status_code=502, text="bad gateway")] * 3
        )
        self.assertEqual(status, "error")
        self.assertEqual(response_data["status_code"], 502)
        self.assertEqual(attempts, 3)

    async def test_persistent_timeout_reports_the_exception_without_a_response(self):
        (status, response_data, message), attempts = await self._post(
            [httpx.ReadTimeout("timed out")] * 2, attempts=2
        )
        self.assertEqual(status, "error")
        self.assertIsNone(response_data)
        self.assertIn("ReadTimeout", message)
        self.assertEqual(attempts, 2)

    async def test_the_assistant_can_override_the_attempt_count(self):
        """The right value belongs to the receiver, not to one global setting."""
        svc = LiveKitService()
        client = ScriptedAsyncClient([SimpleNamespace(status_code=500, text="boom")] * 5)
        with patch("src.services.livekit.livekit_svc.httpx.AsyncClient", client.factory), patch(
            "src.services.livekit.livekit_svc.asyncio.sleep", AsyncMock()
        ), patch.object(livekit_svc.settings, "END_CALL_WEBHOOK_ATTEMPTS", 3):
            await svc._post_end_call_webhook(
                "https://hook.example/end",
                {},
                "room-1",
                webhook_config=SimpleNamespace(timeout_seconds=None, attempts=5),
            )
        self.assertEqual(client.attempts, 5)

    async def test_a_null_override_falls_back_to_the_server_default(self):
        svc = LiveKitService()
        client = ScriptedAsyncClient([SimpleNamespace(status_code=500, text="boom")] * 3)
        with patch("src.services.livekit.livekit_svc.httpx.AsyncClient", client.factory), patch(
            "src.services.livekit.livekit_svc.asyncio.sleep", AsyncMock()
        ), patch.object(livekit_svc.settings, "END_CALL_WEBHOOK_ATTEMPTS", 3):
            await svc._post_end_call_webhook(
                "https://hook.example/end",
                {},
                "room-1",
                webhook_config=SimpleNamespace(timeout_seconds=None, attempts=None),
            )
        self.assertEqual(client.attempts, 3)


if __name__ == "__main__":
    unittest.main()
