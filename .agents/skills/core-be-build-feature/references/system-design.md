# System design pass

A senior engineer does not start with the handler. They start with the
questions that decide whether the feature survives production: what happens
when it is called twice, when the upstream is slow, when two requests race,
when the table has ten million rows, when an old client sends last month's
payload. Answering those on paper costs minutes; discovering them in an
incident costs days.

Run this pass in Phase 5, before the step list. Write the answers into the
**Design notes** section of `plan.md`.

## Proportionality — design for the risks this feature has

The checklist is a list of questions, not a list of things to build. An
internal, low-traffic CRUD route needs no circuit breaker, no queue, no cache,
and no feature flag. For every section, either answer it in one or two lines or
write `N/A — <reason>`. A reason is required: "N/A — single-row insert, no
outbound calls" shows the question was asked; a blank does not.

Machinery (queues, caches, sagas, retries, flags) is added only when a named
risk in these notes needs it. Each piece of machinery is a new failure mode.

---

## 1. Requirements and numbers

- Functional: the acceptance criteria from `scope.md`.
- Non-functional: expected request rate (normal and peak), payload and result
  sizes, latency budget (p95), data growth per month, availability need
  (can it be down for a minute? does a failure block a customer?).
- Back-of-envelope: rows × row size, requests/s × fan-out calls, time per call ×
  calls per request. Unknown? Ask the user or write the assumption down —
  an explicit wrong number is fixable, an implicit one is not.

## 2. Data

- Model: which entity owns the data, who may read and write it (owner/tenant
  column on every resource-scoped table).
- Queries: list the real queries the feature runs; each has an index that
  serves it. No index for a query that is never run.
- Invariants: enforce with the database first — `NOT NULL`, `UNIQUE`, foreign
  keys, `CHECK` — not with an application-level "check then insert", which
  races.
- Transactions: what must change together, atomically? Keep the transaction
  short and never hold it open across a network call.
- Migrations: reversible; for existing tables follow expand → migrate →
  contract (`core-be-workflow/references/SAFE-DELIVERY.md`).

## 3. Correctness under concurrency and retries

Clients, proxies, and queues retry. Two users click at once. Assume both.

- **Read-modify-write** (balances, counters, stock, status transitions): use an
  atomic update (`UPDATE … SET x = x - 1 WHERE x >= 1`), optimistic locking
  (version column), or `SELECT … FOR UPDATE`. Name which.
- **Idempotency**: any operation that moves money, sends a message, creates an
  external resource, or is consumed from an at-least-once queue needs an
  idempotency key (client-supplied header or natural key) stored with a
  `UNIQUE` constraint, returning the first result on replay.
- **Duplicate submissions**: a `UNIQUE` constraint plus mapping the violation to
  `409` (or the original result) beats any "exists?" check.
- **Ordering**: if events can arrive out of order, say how (timestamps,
  sequence numbers, last-write-wins, reject stale).

## 4. Failure modes — every outbound call

For each database, HTTP upstream, queue, or LLM call, fill one row:

| Call | Timeout | Retry? | On failure the caller sees | Partial-failure handling |
|------|---------|--------|----------------------------|--------------------------|

- **Timeout** always, shorter than the caller's own timeout.
- **Retry** only idempotent operations (or ones made idempotent by a key), with
  a small cap, exponential backoff, and jitter. Never retry a `4xx`.
- **Caller sees**: the documented error in the service envelope (`502`/`503`/
  `504` for upstream trouble), never a raw exception.
- **Partial failure**: if step 2 of 3 fails, what state is left behind? Options,
  simplest first: reorder so the irreversible step runs last; record a pending
  state and reconcile; compensate (refund, delete). Pick one and write it down.
- Circuit breakers and bulkheads only when the upstream is known to fail and
  its slowness would exhaust this service's workers.

## 5. Load and limits

- Pagination with a maximum page size on every list; no unbounded `SELECT`.
- No N+1 queries; no network call inside a loop over user-controlled input
  without a cap and bounded concurrency.
- Sizes: body size, file size, array lengths bounded in the schema.
- Long work (> a few seconds, or anything that fans out) goes to a background
  job with a status endpoint — only if the numbers in §1 say so.
- Caching only with a measured need, a stated staleness tolerance, and an
  invalidation rule.

## 6. Compatibility

- API changes are additive: new optional fields, new endpoints. Removing or
  renaming a field, tightening validation, or changing a status code breaks
  clients — that needs a new version or an expand → contract rollout.
- Events and stored JSON: consumers must tolerate unknown fields; producers must
  not drop fields consumers read.
- Config: new env vars have safe defaults so an old deployment config still boots.

## 7. Observability

How will someone know, at 3am, that this feature is broken?

- Structured log at each boundary crossing, with the request id, the resource
  id, and the outcome; never secrets or full payloads with personal data.
- Errors logged once, at the central handler, with context.
- The one signal that proves it works (a counter of successes/failures, a
  latency metric) — only where the service already emits metrics.

## 8. Security

Covered by `core-be-build-feature` Phase 6 step 3 and `core-be-audit-security`.
List the trust boundaries here so the design and the controls line up.

---

## Interfaces that are not obvious

If there are two or more reasonable shapes for the module interface, use
`core-be-coding-standards/references/DESIGN-IT-TWICE.md` before committing
to one.

## Design notes template (for `plan.md`)

```markdown
## Design notes

- **Numbers:** <rate, sizes, growth, latency budget — or assumptions>
- **Data:** <tables/fields, indexes, constraints, transaction boundary>
- **Concurrency / idempotency:** <mechanism, or N/A — reason>
- **Failure modes:** <table from §4, or N/A — no outbound calls>
- **Limits:** <page size, body size, fan-out caps>
- **Compatibility:** <additive? migration path?>
- **Observability:** <logs/metrics added>
- **Machinery added and the risk that justifies it:** <none, or list>
```
