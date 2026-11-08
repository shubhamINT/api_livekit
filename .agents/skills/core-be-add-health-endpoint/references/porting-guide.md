# Porting to any other stack

Contract and rules: [`../SKILL.md`](../SKILL.md). Read those first — this page
only maps them onto a stack that has no reference file yet.

The endpoint is small. Every implementation is the same six primitives wired
together. Find each one in your stack, then write the file.

## The six primitives

| # | Primitive | What to look for | Examples |
|---|-----------|------------------|----------|
| 1 | **Run N tasks concurrently, collect all results** | The stack's fan-out join. Must wait for *all*, not first-wins | `asyncio.gather` · `Promise.all` · `sync.WaitGroup` · `CompletableFuture.allOf` · `Task.WhenAll` (C#) · `Async.Parallel` (F#) · `tokio::join!` / `futures::future::join_all` (Rust) · `Enum.map + Task.await_many` (Elixir) · threads + a join if there is nothing better |
| 2 | **A per-task deadline** | Cancellation token, abort signal, or a client-level timeout | `context.WithTimeout` · `AbortSignal.timeout` · `orTimeout` · `CancellationTokenSource` · `tokio::time::timeout` · client `timeout=` argument |
| 3 | **Catch everything from one task without failing the batch** | Broad catch, `Result`, or a settled-promise variant | `try/except Exception` · `Promise.allSettled` · `err != nil` · `.handle(...)` · `Result<T, E>` · `rescue` |
| 4 | **A monotonic clock** | Not wall-clock — a clock adjustment must not yield negative uptime | `time.monotonic` / `perf_counter` · `performance.now` / `hrtime.bigint` · `time.Since` · `System.nanoTime` · `Stopwatch` · `Instant::now` |
| 5 | **A cheap round-trip per dependency** | The client library already has one | `SELECT 1` · `PING` · `admin.command("ping")` · list-metadata · the upstream's own health route |
| 6 | **A route registered outside the auth/tenant layer** | Wherever your framework composes middleware, filters, or guards | mount before the auth middleware · `permitAll()` · a router with no guard attached |

Have all six? You have the endpoint. If your stack is missing #1 or #2, probe
sequentially with a client-level timeout and note it in a comment — degraded, but
still honest. Never drop #3.

## Assembly order

1. Record process start with the monotonic clock (#4), at module/class init.
2. Write `timed(probe)`: start clock → run probe under the deadline (#2) → catch
   everything (#3) → return `{ok, latency_ms, error?}`.
3. Write `probe(url)` for HTTP upstreams: a `GET`, **any status counts as up**.
   Comment why, or the next reader will "fix" it.
4. Build the probe map. Add optional dependencies only when configured; give
   the skipped ones `{ok: true, skipped: true}`.
5. Fan out (#1), collect into `checks` keyed by dependency name.
6. `healthy = all checks ok`. Log the failed names once at WARN if not.
7. Return **HTTP 200** with `{status, version, uptime_s, checks}`.

## Language-specific traps

**Single-threaded event loops** (Node, Python asyncio, Ruby with async): a
blocking driver call freezes every other request. Use the async client, or push
the blocking probe to a thread pool.

**Thread-per-request runtimes** (classic JVM, .NET sync, PHP-FPM): each probe
costs a thread. A bounded pool or virtual threads keep `/health` from becoming a
thundering herd under a fast poll interval.

**Languages without exceptions** (Go, Rust): #3 is `if err != nil` / matching on
`Result` in the `timed` wrapper. The rule is unchanged — convert, never
propagate.

**Frameworks with a built-in health endpoint** (Spring Actuator, ASP.NET
`HealthChecks`, NestJS Terminus, Micronaut, Quarkus SmallRye): they almost all
return **503 when unhealthy** and auto-register indicators for dependencies your
code never calls. Either reconfigure both behaviours explicitly, or write the
plain route — it is ~50 lines. See [`java-spring.md`](java-spring.md) for what
"reconfigure explicitly" looks like in practice.

**Serverless / FaaS**: `uptime_s` measures the container, not the service, and is
close to meaningless across cold starts. Keep the field for shape compatibility,
and do not alert on it.

**Non-HTTP services** (workers, consumers, cron runners): the same contract,
exposed on a tiny side HTTP listener on its own port. Same body, same rules.

## Before you finish

Run the checklist at the end of [`../SKILL.md`](../SKILL.md), then add a
reference file for your stack next to this one so the next person does not
re-derive it. Mirror the existing files: route module, ping helper, wiring,
config, tests, gotchas.
