# Reference: Python — FastAPI / async

Contract and rules: [`../SKILL.md`](../SKILL.md). This file is syntax only.

Concurrency: `asyncio.gather`. Timeout: passed to the client per probe.

## The route module — `src/api/routes/health.py`

```python
"""GET /health — one deep probe of every dependency a request needs.

Always answers HTTP 200: a degraded dependency shows up in the body, never as a
5xx, so a downstream blip can't cascade into this service being pulled out of
rotation. Read `status` / `checks`, not the status code.
"""
import asyncio
import time

import httpx
from fastapi import APIRouter

from src.api.models.response_schemas import apiResponse
from src.core.config import APP_VERSION, settings
from src.core.db.db_connect import ping_db
from src.core.logging.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

_STARTED = time.monotonic()


async def _timed(coro) -> dict:
    """Run a probe, report ok/latency, turn any failure into `error` text."""
    t0 = time.perf_counter()
    try:
        await coro
        ok, err = True, None
    except Exception as e:
        ok, err = False, f"{type(e).__name__}: {e}"
    result = {"ok": ok, "latency_ms": round((time.perf_counter() - t0) * 1000, 1)}
    if err:
        result["error"] = err
    return result


async def _probe(url: str) -> None:
    """Reachability check only. These are POST-only business endpoints with no
    health route, so ANY HTTP status (404, 405, 401...) means a server answered
    and counts as up. Only a transport failure — connect refused, DNS, TLS,
    timeout — is a failure. Do not "fix" this into raise_for_status()."""
    async with httpx.AsyncClient(timeout=settings.HEALTH_PROBE_TIMEOUT_S) as client:
        await client.get(url)


@router.get("/health", tags=["Health"])
async def health() -> apiResponse:
    probes = {
        "postgres": ping_db(),
        "orders_api": _probe(settings.ORDERS_API_URL),
    }
    # Optional feature — an empty URL means it is off, not broken.
    if settings.ANALYTICS_URL:
        probes["analytics"] = _probe(settings.ANALYTICS_URL)

    names = list(probes)
    results = await asyncio.gather(*(_timed(c) for c in probes.values()))
    checks = dict(zip(names, results))
    checks.setdefault("analytics", {"ok": True, "skipped": True})

    healthy = all(c["ok"] for c in checks.values())
    if not healthy:
        logger.warning("health degraded: %s",
                       [n for n, c in checks.items() if not c["ok"]])
    status = "ok" if healthy else "degraded"
    return apiResponse(
        success=healthy,
        message=status,
        data={
            "status": status,
            "version": APP_VERSION,
            "uptime_s": round(time.monotonic() - _STARTED, 1),
            "checks": checks,
        },
    )
```

## The ping helper — beside the connection lifecycle

The route never touches the driver handle itself.

```python
# src/core/db/db_connect.py

async def ping_db() -> None:
    """Round-trip the database. Raises if the client was never built or the
    server does not answer. Used by the /health probe."""
    if _client is None:
        raise RuntimeError("database client not initialised")
    await _client.admin.command("ping")          # MongoDB
    # SQLAlchemy async: async with engine.connect() as c: await c.execute(text("SELECT 1"))
```

## Wiring — `server.py`

Mounted unprefixed, so it sits outside the API's tenant-header dependency.

```python
app.include_router(v1_chat.router, prefix="/v1/agent")
app.include_router(health.router)          # no prefix, no auth dependency
```

## Config

```python
# src/core/config.py
APP_VERSION = "1.4.2"   # single source; also passed to FastAPI(version=...)

# inside Settings.__init__ — deliberately far below the 60s call timeouts
self.HEALTH_PROBE_TIMEOUT_S = float(os.getenv("HEALTH_PROBE_TIMEOUT_S", "3"))
```

## Tests — `tests/api/routes/test_health.py`

`respx` for HTTP, monkeypatch for the ping helper. Patch `health.ping_db`, not the
driver.

```python
@pytest.fixture
def probes(monkeypatch):
    async def _ok():
        return None

    monkeypatch.setattr(health, "ping_db", _ok)
    with respx.mock:
        respx.get(settings.ORDERS_API_URL).mock(return_value=httpx.Response(200))
        yield respx


def test_a_404_from_a_downstream_service_still_counts_as_reachable(client, probes):
    respx.get(settings.ORDERS_API_URL).mock(return_value=httpx.Response(404))
    assert client.get("/health").json()["data"]["status"] == "ok"


def test_a_transport_failure_degrades_but_returns_200(client, probes):
    respx.get(settings.ORDERS_API_URL).mock(side_effect=httpx.ConnectError("refused"))
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()["data"]
    assert body["status"] == "degraded"
    assert "ConnectError" in body["checks"]["orders_api"]["error"]
    assert body["checks"]["postgres"]["ok"] is True     # peers unaffected
```

## Gotchas

- **A sync `def` route blocks the event loop.** The handler must be `async def`.
- **`time.monotonic()`, not `time.time()`**, for uptime — a clock adjustment must
  not produce a negative uptime.
- **`round(..., 1)`** on latency; raw floats make dashboards noisy.
- Framework health plugins (`fastapi-health` and friends) buy you nothing here —
  the whole endpoint is ~40 lines. Do not add a dependency for it.
