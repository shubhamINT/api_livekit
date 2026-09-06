import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from src.api.models.api_schemas import TriggerOutboundCall
from src.api.routes.call import get_call_usage, trigger_outbound_call


class QueryField:
    def __eq__(self, other):
        return other


class TestCallRoute(unittest.IsolatedAsyncioTestCase):
    async def test_get_call_usage_returns_owned_record(self):
        user = SimpleNamespace(user_email="user@example.com")
        call = SimpleNamespace()
        usage = SimpleNamespace(model_dump=lambda **_: {"room_name": "room-1", "model_usage": []})
        call_model = SimpleNamespace(
            room_name=QueryField(),
            created_by_email=QueryField(),
            find_one=AsyncMock(return_value=call),
        )
        usage_model = SimpleNamespace(room_name=QueryField(), find_one=AsyncMock(return_value=usage))

        with patch("src.api.routes.call.CallRecord", call_model), patch(
            "src.api.routes.call.UsageRecord", usage_model
        ):
            response = await get_call_usage("room-1", current_user=user)

        self.assertTrue(response.success)
        self.assertEqual(response.data["model_usage"], [])
        call_model.find_one.assert_awaited_once()

    async def test_get_call_usage_hides_unowned_call(self):
        user = SimpleNamespace(user_email="other@example.com")
        call_model = SimpleNamespace(
            room_name=QueryField(),
            created_by_email=QueryField(),
            find_one=AsyncMock(return_value=None),
        )
        with patch("src.api.routes.call.CallRecord", call_model), self.assertRaises(HTTPException) as ctx:
            await get_call_usage("room-1", current_user=user)

        self.assertEqual(ctx.exception.status_code, 404)

    async def test_rejects_trunk_service_mismatch(self):
        request = TriggerOutboundCall(
            assistant_id="assistant-1",
            trunk_id="trunk-1",
            to_number="+911234567890",
            call_service="exotel",
            metadata=None,
        )
        current_user = SimpleNamespace(user_email="user@example.com")
        assistant = SimpleNamespace(assistant_id="assistant-1", assistant_name="Assistant")
        twilio_trunk = SimpleNamespace(trunk_type="twilio", trunk_config={})

        assistant_model = SimpleNamespace(
            assistant_id=QueryField(),
            assistant_created_by_email=QueryField(),
            find_one=AsyncMock(return_value=assistant),
        )
        trunk_model = SimpleNamespace(
            trunk_id=QueryField(),
            trunk_created_by_email=QueryField(),
            trunk_is_active=QueryField(),
            find_one=AsyncMock(return_value=twilio_trunk),
        )

        with patch("src.api.routes.call.Assistant", assistant_model), patch(
            "src.api.routes.call.OutboundSIP", trunk_model
        ), self.assertRaises(HTTPException) as ctx:
            await trigger_outbound_call(request=request, current_user=current_user)

        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("does not match", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
