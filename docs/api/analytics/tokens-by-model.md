# User Tokens By Model

`GET /analytics/tokens/by-model` returns one row per `(type, provider, model)` for the
authenticated user's calls. Rows include numeric usage totals and `total_records`.

```bash
curl "https://api-livekit-vyom.indusnettechnologies.com/analytics/tokens/by-model" \
  -H "Authorization: Bearer YOUR_API_KEY"
```

Optional `start_date` and `end_date` filters default to the last 30 days. Provider values use
the schema-version 3 normalization rule.
