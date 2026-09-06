# Analytics

## Overview

The analytics endpoints provide per-user call and usage metrics scoped to the authenticated API key owner. Use them to monitor call volume, duration, status, and per-model consumption.

Call analytics use `CallRecord`; token analytics use `UsageRecord` and filter by the caller's `user_email`.

## Authentication

All analytics endpoints require a valid API key passed as a Bearer token:

```
Authorization: Bearer YOUR_API_KEY
```

## Common Query Parameters

Every analytics endpoint accepts optional date-range filters:

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `start_date` | datetime | No | 30 days ago | ISO 8601 start of range. |
| `end_date` | datetime | No | Now | ISO 8601 end of range. |

## Available Endpoints

| Endpoint | Description |
| :--- | :--- |
| [Dashboard](dashboard.md) | At-a-glance totals: calls, duration, status breakdown, period counts. |
| [By Assistant](by-assistant.md) | Per-assistant call count and duration. |
| [By Phone Number](by-phone-number.md) | Per destination number breakdown. |
| [By Time](by-time.md) | Time-series data with day, week, or month granularity. |
| [By Service](by-service.md) | Breakdown by telephony service (exotel, twilio, web). |
| [Token Summary](tokens-summary.md) | Flat token, character, duration, and call totals. |
| [Tokens by Model](tokens-by-model.md) | Per-component provider/model attribution. |

!!! info "Data scoping"

    Results are always scoped to the authenticated user. To see cross-tenant data, use the [Admin](../admin/index.md) endpoints with a super-admin API key.
