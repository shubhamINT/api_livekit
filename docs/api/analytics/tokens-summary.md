# User Token Summary

`GET /analytics/tokens/summary` returns flat usage totals and `total_estimated_cost_usd` for
the authenticated user's calls.
It accepts optional `start_date` and `end_date` filters, defaulting to the last 30 days.

Data comes from `UsageRecord.created_at`; live and non-finalized rows are included. Response
shape matches the admin token summary, with `data` containing the aggregate fields.
Cost covers AI-provider public PAYG estimates only; unpriced entries and platform costs are
excluded.

```bash
curl "https://api-livekit-vyom.indusnettechnologies.com/analytics/tokens/summary" \
  -H "Authorization: Bearer YOUR_API_KEY"
```
