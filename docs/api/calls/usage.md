# Per-Call Usage

Returns the complete `UsageRecord` for one call, including `model_usage` attribution.

It also returns `estimated_cost_usd`, `pricing_schema_version`, `pricing_complete`, and
`unpriced_model_usage`. The estimate covers AI-provider public PAYG rates only. When
`pricing_complete` is false, the total is partial. When `usage_finalized` is false, usage and
cost are a live snapshot or crash-floor.

## Endpoint

- **URL**: `/call/records/{room_name}/usage`
- **Method**: `GET`
- **Authentication**: API key that owns the call

The route first checks `CallRecord.created_by_email`, so another user's room name returns
the same `404` as a missing usage row. Rows are returned even when `usage_finalized` is false;
that means the call is live or the worker stopped before teardown and the values are a floor.

```bash
curl -X GET "https://api-livekit-vyom.indusnettechnologies.com/call/records/ROOM_NAME/usage" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Response `data` is the stored `UsageRecord` without Mongo's internal `id`. See
[Usage accounting](../../reference/usage-accounting.md) for schema versions and pricing rules.
