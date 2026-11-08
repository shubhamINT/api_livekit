---
name: core-be-add-health-endpoint
description: >
  Every backend service, in any language, exposes one deep GET /health that
  probes its real dependencies and always answers HTTP 200. Use when scaffolding
  a service, when a service has no health endpoint or only a static "ok" stub,
  when adding a dependency (database, upstream API, cache, queue, broker) that a
  health check must now cover, or when asked to "add a health check", "add a
  readiness probe", "why is /health always green", "wire up monitoring".
  Language- and framework-agnostic; per-stack reference implementations live in
  references/. Self-contained — works unchanged in any repo it is copied into.
---

# Service Health Endpoint

A service with no health endpoint can only be diagnosed by sending it real
traffic. A service with a static `{"status": "ok"}` stub is worse: it reports
green while its database is gone, so monitoring actively lies.

Every service — Python, Node, Go, Java, Rust, C#, Ruby, PHP, anything — gets
**one** endpoint, `GET /health`, that probes every dependency a real request
needs, concurrently, and reports each one.

This skill defines the **contract and the rules**. They are identical across
languages. Only syntax differs — see `references/` for a working implementation
in your stack.

<gate>
**Gate — when this is the task itself** (not a step inside another task):
load `core-be-workflow` and run its phases 1–3 before anything else. Invoking this
skill directly (a slash command, a one-line request) is not an exemption,
and harness plan mode does not replace `tasks.md`.
</gate>

**Always, even inside another task:** make sure the repo is registered — the
core-be block in `AGENTS.md` and the `@AGENTS.md` import in `CLAUDE.md`
(`core-be-workflow`, Phase 2, "Register the pack") — and, when code or config
changed, finish with the docs sync (`core-be-workflow`, Phase 7) so the README
matches the code.

---

## The contract

`GET /health`

- **No auth, no tenant header.** It is a probe, not an API. If the service
  requires a tenant/owner/auth header on its API paths, `/health` is mounted
  outside that prefix and exempt from the middleware or filter that enforces it.
- **Always HTTP 200.** Even when every dependency is down.
- **`Content-Type: application/json`.**
- Body uses the service's own standard response envelope if it has one; the
  fields below are what must appear in the payload either way:

```json
{
  "status": "ok",
  "version": "1.4.2",
  "uptime_s": 1421.7,
  "checks": {
    "postgres":  { "ok": true,  "latency_ms": 3.1 },
    "orders_api":{ "ok": false, "latency_ms": 3001.2,
                   "error": "ConnectionRefused: dial tcp 10.0.0.4:8080" },
    "analytics": { "ok": true,  "skipped": true }
  }
}
```

| Field | Rule |
|-------|------|
| `status` | `"ok"` when every non-skipped check passes, else `"degraded"`. If the envelope has a success/ok flag, it mirrors this. |
| `version` | The service version. One constant or build-time value, shared with whatever else reports a version (framework metadata, OpenAPI info, startup log) — never two hardcoded copies that can drift. |
| `uptime_s` | Seconds since process start. Distinguishes "still broken" from "crash-looping and briefly broken again". |
| `checks.<dep>` | One entry per dependency, keyed by a stable short name. `ok` + `latency_ms` always; `error` only on failure; `skipped: true` for a disabled optional feature. |

Names in `checks` are contract: dashboards and alerts key off them. Renaming one
is a breaking change to whoever monitors the service.

### Why always 200 — the rule people break first

The instinct is to return 503 when a dependency is down. Do not, unless an
orchestrator is *actually configured* to gate traffic on this endpoint.

A shared upstream blipping must not turn into every instance of this service
being pulled out of a load-balancer rotation at once. That converts one degraded
dependency into a total outage — and the endpoint you needed to diagnose it is
now unreachable behind the LB too.

Monitor `data.status`, not the status code. If and when an orchestrator needs to
gate traffic, add a **separate** `/health/ready` that returns 503, and leave
`/health` as the always-200 diagnostic. Do not overload one endpoint with both
jobs.

---

## What to probe, and how honestly

**Anything with a real ping — use it.** Every mature client library has a cheap
round-trip: `SELECT 1` (SQL), `admin.command("ping")` (MongoDB), `PING` (Redis),
a metadata/list request (S3, Kafka), a `GET /health` on an upstream that has one.
A pass means the connection is live and the server answers.

**HTTP upstreams with no health route: reachability only.** If an upstream is a
POST-only business endpoint, the honest probe is a `GET` where **any** HTTP
status — 200, 401, 404, 405 — counts as up. A status code proves a server is
listening. Only a transport failure (connection refused, DNS, TLS, timeout) is a
failure.

> This looks like a bug to the next reader, who will "fix" it into a
> raise-on-non-2xx and turn the dashboard permanently red. **Comment the rule at
> the call site**, and pin it with a test. If an upstream *does* expose a real
> health route, call that instead and check its status properly.

**Optional features are `skipped`, not failed.** A feature switched off by an
empty config value is working as configured. Report
`{"ok": true, "skipped": true}` and keep it out of the degraded calculation.

**Probe what a request needs, nothing else.** A dependency no code path uses does
not belong in `checks`. Neither does anything the service merely *ships with*.

## Rules that make the endpoint usable

These hold in every language. The mechanism differs — goroutines and
`errgroup`, `Promise.allSettled`, `asyncio.gather`, `CompletableFuture.allOf`,
a thread pool — the requirement does not.

<hard-rules>
**Run every probe concurrently.** Endpoint latency is then the slowest single
probe, not the sum. Sequential probes make `/health` the slowest route in the
service.

**Use a short, dedicated timeout.** One config value (`HEALTH_PROBE_TIMEOUT_S`,
default `3`) — never reuse the 30–60s timeouts sized for real calls. A probe that
hangs for a minute is a probe nobody polls, and it ties up a worker or connection
while it hangs. Apply it per probe, not to the whole batch.

**Never let a probe fail the request.** Catch every error per check — the broad
catch is correct here, and is one of the few places it is — and record it as
`{"ok": false, "error": "<Type>: <message>"}`. One broken probe must not 500 the
endpoint that exists to report breakage. In languages without exceptions, the
same rule applies to returned errors: convert, never propagate.

**Never leak secrets.** `error` carries an error type and message. Never a
connection string with credentials, an API key, a token, or a full request body.
Report dependency names, not URLs. Assume `/health` is reachable by anyone who
can reach the service.

**Log degradation once, at WARN**, listing the failed check names. Do not log on
the healthy path — this endpoint gets polled and will drown the log.

**Keep it cheap.** No queries against real tables, no writes, no LLM or billed
API calls, no work proportional to data size. If polling `/health` shows up in
your performance profile, the checks are doing too much.

**No caching of results** until polling volume proves it necessary. A cached
health check reports the past, which is exactly what an incident does not need.
</hard-rules>

## Where the code goes

Follow the host repo's own layout conventions. The placement principle is the
same everywhere:

| Piece | Goes in |
|-------|---------|
| The endpoint | Its own module in the HTTP/route layer (`health.*` beside the other route modules), mounted unprefixed |
| Each dependency ping | A named helper **owned by the layer that owns that dependency** — e.g. beside the DB connection lifecycle. The health route must never reach into a driver's private client handle |
| Probe timeout | The service's single config module, alongside the other timeouts |
| Version constant | The config or build-info module, consumed by both the framework metadata and the health payload |
| Tests | The test path mirroring the route module |

The route module assembles checks and shapes the response. It holds no business
logic and no direct driver access.

## Reference implementations

Same contract, per stack. Read the one you need; the rules above are the
authority if an example ever disagrees.

| Stack | File |
|-------|------|
| Python — FastAPI / async | [`references/python-fastapi.md`](references/python-fastapi.md) |
| Node / TypeScript — Express, Fastify | [`references/node-typescript.md`](references/node-typescript.md) |
| Go — net/http, chi, Gin | [`references/go.md`](references/go.md) |
| Java / Kotlin — Spring Boot | [`references/java-spring.md`](references/java-spring.md) |
| Any other stack | [`references/porting-guide.md`](references/porting-guide.md) — the six primitives to map |

## Tests to write

Offline, no real network, no live datastore — mock the dependency helpers. Every
rule above that a future reader might "fix" needs a test holding it down.

- **All dependencies up** → `status: "ok"`, every check `ok`, `version` matches the
  constant, `checks` keys are exactly the expected set.
- **A non-2xx from an upstream still counts as reachable** → mock a `404`, assert
  `status` is still `"ok"`. This is the test that survives the raise-on-non-2xx
  "fix".
- **A transport failure degrades but returns 200** → mock a connect error, assert
  status code `200`, `status: "degraded"`, the error text names the error type,
  and unaffected peers stay `ok`.
- **A datastore down degrades but returns 200** → the ping helper fails; same
  assertions.
- **An optional feature disabled is `skipped`**, and probed normally when configured.
- **The probe uses the short timeout**, not the service's real call timeout.
- **No auth/tenant header required** → the endpoint answers 200 without it.

Mock the ping helper **as the health module resolves it**, not the underlying
driver — that keeps the test independent of whether your driver's test double
implements `ping`.

## Documentation

A health endpoint nobody knows the semantics of gets misused. In the same change:

- README endpoint table: the path, "no header", and **"always HTTP 200 — read
  `status`"**.
- README + docs env table: `HEALTH_PROBE_TIMEOUT_S` and its default.
- A docs page (if the service has a docs site) with a sample healthy and degraded
  body, and the reachability-only caveat spelled out.

## Checklist

- [ ] `GET /health` exists, mounted outside any auth/tenant-scoped prefix
- [ ] Every dependency a real request needs has a check; nothing else does
- [ ] Probes run concurrently
- [ ] Dedicated short timeout from config, applied per probe
- [ ] Every probe failure is caught — the endpoint cannot 500
- [ ] Always HTTP 200; `status` is `ok`/`degraded`
- [ ] Optional disabled features report `skipped`, not failed
- [ ] Reachability-only probes carry the comment explaining why
- [ ] `version` from a single shared source; `uptime_s` present
- [ ] No secrets, credentials, tokens, or URLs in `error` strings
- [ ] Degradation logged once at WARN; healthy path silent
- [ ] Tests cover: all-up, upstream 404 still ok, transport failure, datastore
      down, skipped optional, timeout value, no header needed
- [ ] README endpoint + env tables updated; docs page added

---

## Installation

This skill ships in the core backend rules pack (`core-backend/`) and is
installed with it — see the pack `README.md`. It is self-contained: templates,
scripts and references travel with it.
