import unittest

from src.core.db.usage_aggregations import (
    usage_by_model_pipeline,
    usage_totals_pipeline,
)


class TestUsageAggregations(unittest.TestCase):
    def test_by_model_groups_on_type_provider_model(self):
        pipeline = usage_by_model_pipeline({"user_email": "a@example.com"})
        group = pipeline[2]["$group"]["_id"]
        self.assertEqual(set(group), {"type", "provider", "model"})
        self.assertEqual(pipeline[1], {"$unwind": "$model_usage"})

    def test_summary_starts_with_match(self):
        pipeline = usage_totals_pipeline({"user_email": "a@example.com"})
        self.assertEqual(pipeline[0], {"$match": {"user_email": "a@example.com"}})
        self.assertEqual(pipeline[1]["$group"]["_id"], None)
        self.assertIn("total_estimated_cost_usd", pipeline[1]["$group"])

    def test_by_model_sums_entry_cost(self):
        pipeline = usage_by_model_pipeline({})
        self.assertEqual(
            pipeline[2]["$group"]["total_estimated_cost_usd"],
            {"$sum": {"$ifNull": ["$model_usage.estimated_cost_usd", 0]}},
        )
