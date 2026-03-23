import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from src.services.livekit.livekit_svc import LiveKitService


class FakeCallRecord:
    def __init__(self, status="initiated"):
        self.room_name = "room-1"
        self.assistant_id = "assistant-1"
        self.assistant_name = "Assistant"
        self.to_number = "+911234567890"
        self.call_status = status
        self.call_status_reason = None
        self.sip_status_code = None
        self.sip_status_text = None
        self.answered_at = None
        self.recording_path = None
        self.transcripts = []
        self.started_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        self.ended_at = None
        self.call_duration_minutes = None

    async def save(self):
        return None


class TestLiveKitLifecycle(unittest.IsolatedAsyncioTestCase):
    async def test_refuses_terminal_overwrite_failed_to_completed(self):
        svc = LiveKitService()
        record = FakeCallRecord(status="initiated")

        with patch("src.services.livekit.livekit_svc.CallRecord.find_one", AsyncMock(return_value=record)):
            svc._claim_end_call_webhook = AsyncMock(return_value=True)
            svc.send_end_call_webhook = AsyncMock(return_value=True)
            svc._mark_end_call_webhook_result = AsyncMock(return_value=None)

            await svc.finalize_call(
                room_name="room-1",
                assistant_id="assistant-1",
                call_status="failed",
                call_status_reason="setup failed",
            )
            await svc.finalize_call(
                room_name="room-1",
                assistant_id="assistant-1",
                call_status="completed",
            )

            self.assertEqual(record.call_status, "failed")
            self.assertEqual(svc._claim_end_call_webhook.await_count, 1)
            self.assertEqual(svc.send_end_call_webhook.await_count, 1)

    async def test_duplicate_terminal_event_sends_webhook_once(self):
        svc = LiveKitService()
        record = FakeCallRecord(status="initiated")

        with patch("src.services.livekit.livekit_svc.CallRecord.find_one", AsyncMock(return_value=record)):
            svc._claim_end_call_webhook = AsyncMock(side_effect=[True, False])
            svc.send_end_call_webhook = AsyncMock(return_value=True)
            svc._mark_end_call_webhook_result = AsyncMock(return_value=None)

            await svc.finalize_call(
                room_name="room-1",
                assistant_id="assistant-1",
                call_status="failed",
                call_status_reason="no rtp",
            )
            await svc.finalize_call(
                room_name="room-1",
                assistant_id="assistant-1",
                call_status="failed",
                call_status_reason="no rtp",
            )

            self.assertEqual(svc.send_end_call_webhook.await_count, 1)


if __name__ == "__main__":
    unittest.main()
