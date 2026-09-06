# Admin (Super-Admin)

## Overview

The admin endpoints provide cross-tenant analytics visible only to super-admin API keys. Use them to monitor platform-wide call volume, per-user consumption, and token usage.

## Authentication

All admin endpoints require a super-admin API key:

```
Authorization: Bearer YOUR_SUPER_ADMIN_API_KEY
```

The API key must have `is_super_admin` set to `true`. Regular API keys receive a `403 Forbidden` response.

## Available Endpoints

### Call Analytics

| Endpoint | Description |
| :--- | :--- |
| [Dashboard](dashboard.md) | Cross-tenant call totals, duration, status breakdown, and active user count. |
| [Calls by User](by-user.md) | Per-user call count and duration. |
| [Calls by Phone Number](by-phone-number.md) | Cross-tenant destination number breakdown. |
| [Calls by Service](by-service.md) | Cross-tenant service breakdown (exotel, twilio, web). |

### Token and Usage Analytics

| Endpoint | Description |
| :--- | :--- |
| [Token Summary](token-summary.md) | Aggregate LLM token and TTS usage across the platform. |
| [Tokens by Model](tokens-by-model.md) | Per-component provider/model attribution across the platform. |
| [Tokens by User](tokens-by-user.md) | Per-user token consumption breakdown. |
| [Tokens by Assistant](tokens-by-assistant.md) | Per-assistant token consumption breakdown. |

## Common Query Parameters

Most admin endpoints accept:

| Parameter | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `start_date` | datetime | No | 30 days ago | ISO 8601 start of range. |
| `end_date` | datetime | No | Now | ISO 8601 end of range. |
| `user_email` | string | No | -- | Narrow results to a specific user (where supported). |

!!! warning "Super-admin only"

    These endpoints expose data across all users. Treat the API key with the same care as database credentials.
