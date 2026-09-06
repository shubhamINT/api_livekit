# Admin Tokens By Model

`GET /admin/analytics/tokens/by-model` returns one row per `(type, provider, model)` across
all users. Super-admins may filter with `user_email`, `assistant_id`, `start_date`, and `end_date`.

```bash
curl "https://api-livekit-vyom.indusnettechnologies.com/admin/analytics/tokens/by-model" \
  -H "Authorization: Bearer YOUR_SUPER_ADMIN_API_KEY"
```

Rows include numeric usage totals and `total_records`; non-finalized rows are included.
