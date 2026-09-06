import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from bson.decimal128 import Decimal128

from src.core.db.db_schemas import UsageRecord


class TestUsageRecord(unittest.TestCase):
    def test_converts_mongo_decimal128_costs(self):
        with patch.object(
            UsageRecord,
            "get_settings",
            return_value=SimpleNamespace(pymongo_collection=None),
        ):
            record = UsageRecord.model_validate(
                {
                    "room_name": "room-1",
                    "assistant_id": "assistant-1",
                    "user_email": "user@example.com",
                    "estimated_cost_usd": Decimal128(
                        "0.008676768159204008955223880595"
                    ),
                    "model_usage": [
                        {
                            "type": "llm_usage",
                            "estimated_cost_usd": Decimal128("0.0042"),
                        }
                    ],
                }
            )

        self.assertEqual(
            record.estimated_cost_usd,
            Decimal("0.008676768159204008955223880595"),
        )
        self.assertEqual(record.model_usage[0]["estimated_cost_usd"], Decimal("0.0042"))
