# Reference: Node / TypeScript — Express, Fastify

Contract and rules: [`../SKILL.md`](../SKILL.md). This file is syntax only.

Concurrency: `Promise.all` over already-wrapped probes (each one resolves, never
rejects). Timeout: `AbortSignal.timeout` — built in since Node 17.3, no
dependency.

## The shared probe helpers — `src/routes/health.ts`

```ts
/**
 * GET /health — one deep probe of every dependency a request needs.
 *
 * Always answers HTTP 200: a degraded dependency shows up in the body, never as
 * a 5xx, so a downstream blip can't cascade into this service being pulled out
 * of rotation. Read `status` / `checks`, not the status code.
 */
import { Router } from "express";
import { APP_VERSION, config } from "../config";
import { pingDb } from "../db/connect";
import { logger } from "../logging/logger";

const router = Router();
const STARTED = process.hrtime.bigint();

type Check = { ok: boolean; latency_ms?: number; error?: string; skipped?: true };

/** Run a probe, report ok/latency, turn any failure into `error` text. */
async function timed(probe: () => Promise<unknown>): Promise<Check> {
  const t0 = performance.now();
  try {
    await probe();
    return { ok: true, latency_ms: round1(performance.now() - t0) };
  } catch (e) {
    const err = e as Error;
    return {
      ok: false,
      latency_ms: round1(performance.now() - t0),
      error: `${err.name}: ${err.message}`,
    };
  }
}

/**
 * Reachability check only. These are POST-only business endpoints with no
 * health route, so ANY HTTP status (404, 405, 401...) means a server answered
 * and counts as up. Only a transport failure — connect refused, DNS, TLS,
 * timeout — is a failure. Do not "fix" this into an `if (!res.ok) throw`.
 */
async function probe(url: string): Promise<void> {
  await fetch(url, { signal: AbortSignal.timeout(config.healthProbeTimeoutMs) });
}

const round1 = (n: number) => Math.round(n * 10) / 10;
```

## The handler

```ts
router.get("/health", async (_req, res) => {
  const probes: Record<string, () => Promise<unknown>> = {
    postgres: () => pingDb(),
    orders_api: () => probe(config.ordersApiUrl),
  };
  // Optional feature — an empty URL means it is off, not broken.
  if (config.analyticsUrl) probes.analytics = () => probe(config.analyticsUrl);

  const names = Object.keys(probes);
  const results = await Promise.all(names.map((n) => timed(probes[n])));
  const checks: Record<string, Check> = Object.fromEntries(
    names.map((n, i) => [n, results[i]]),
  );
  checks.analytics ??= { ok: true, skipped: true };

  const healthy = Object.values(checks).every((c) => c.ok);
  if (!healthy) {
    logger.warn(
      { failed: Object.entries(checks).filter(([, c]) => !c.ok).map(([n]) => n) },
      "health degraded",
    );
  }
  const status = healthy ? "ok" : "degraded";

  // Always 200 — see SKILL.md. Do not res.status(503) here.
  res.json({
    success: healthy,
    message: status,
    data: {
      status,
      version: APP_VERSION,
      uptime_s: round1(Number(process.hrtime.bigint() - STARTED) / 1e9),
      checks,
    },
  });
});

export default router;
```

Fastify is the same body with `fastify.get("/health", async () => ({ ... }))`
returning the object instead of calling `res.json`.

## The ping helper — beside the connection lifecycle

The route never touches the driver handle itself.

```ts
// src/db/connect.ts
export async function pingDb(): Promise<void> {
  if (!pool) throw new Error("database pool not initialised");
  await pool.query("SELECT 1");                  // pg
  // mongodb: await client.db().admin().command({ ping: 1 });
  // redis:   await redis.ping();
}
```

## Wiring

Mounted before/outside the auth middleware, not after it.

```ts
app.use("/", healthRouter);           // no auth, no tenant middleware
app.use("/v1", requireTenant, v1Router);
```

## Config

```ts
// src/config.ts
export const APP_VERSION = process.env.npm_package_version ?? "0.0.0";

export const config = {
  // Deliberately far below the 30–60s call timeouts.
  healthProbeTimeoutMs: Number(process.env.HEALTH_PROBE_TIMEOUT_S ?? 3) * 1000,
};
```

`npm_package_version` is only set when started via an npm script. If the service
is started directly (`node dist/server.js`, a container CMD), read the version
from a generated build-info module instead — do not hardcode a second copy.

## Tests — `test/routes/health.test.ts`

`nock` or `msw` for HTTP, a module mock for the ping helper. Mock the helper as
the health module resolves it, not `pg` itself.

```ts
it("counts a 404 from a downstream service as reachable", async () => {
  nock(base).get("/").reply(404);
  const r = await request(app).get("/health");
  expect(r.status).toBe(200);
  expect(r.body.data.status).toBe("ok");
});

it("degrades but returns 200 on a transport failure", async () => {
  nock(base).get("/").replyWithError({ code: "ECONNREFUSED" });
  const r = await request(app).get("/health");
  expect(r.status).toBe(200);
  expect(r.body.data.status).toBe("degraded");
  expect(r.body.data.checks.postgres.ok).toBe(true);   // peers unaffected
});
```

## Gotchas

- **`Promise.all` is correct here only because `timed()` never rejects.** If you
  refactor `timed` to rethrow, one failed probe kills the whole response — use
  `Promise.allSettled` if that ever happens.
- **`AbortSignal.timeout` throws a `TimeoutError`**, whose `name` lands in the
  `error` string. Good — that is the diagnostic.
- **`process.hrtime.bigint()`, not `Date.now()`**, for uptime — a clock adjustment
  must not produce a negative uptime.
- **`fetch` does not reject on 4xx/5xx.** That is exactly the behaviour the
  reachability rule wants. Leave it.
- Do not reach for `terminus`, `express-healthcheck`, or similar. The whole
  endpoint is ~50 lines and they hide the 503 behaviour you do not want.
