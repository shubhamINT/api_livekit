# Node Testing

Every module under `src/` has a test that fails when its logic breaks. That is
the whole standard. This is the Node twin of `core-be-write-tests`.

> **A great developer seeks simplicity. An idiot developer seeks complexity.**

---

## Non-negotiables

<hard-rules>
1. **A new or changed module ships with its test in the same change.**
2. **Coverage floor is 80%** (lines, branches, functions, statements) in
   `vitest.config.ts` `coverage.thresholds`. A floor, never a target to lower. A
   genuinely untestable line gets `/* v8 ignore next */` **with a reason in the
   same comment**.
3. **No test touches the network, a live database, or a real LLM.**
4. **The runner is `npx vitest`** (via `npm test`). No ad-hoc scripts.
</hard-rules>

## Layout: `tests/` mirrors `src/`

```
src/billing/invoice.service.ts      -> tests/billing/invoice.service.test.ts
src/api/routes/v1/orders.routes.ts  -> tests/api/routes/v1/orders.routes.test.ts
src/core/config.ts                  -> tests/core/config.test.ts

tests/
  setup.ts        # global setup: network guard, env defaults — registered in vitest config
  helpers/        # app builder, factories — the ONLY place shared helpers live
```

- Test names state the invariant: `it("returns 404 for another owner's order")`,
  not `it("works")`.
- Shared builders live in `tests/helpers/`; never copy a helper into a test file.

Minimal `vitest.config.ts`:

```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["tests/**/*.test.ts"],
    setupFiles: ["tests/setup.ts"],
    restoreMocks: true,
    coverage: {
      provider: "v8",
      include: ["src/**/*.ts"],
      exclude: ["src/server.ts"],
      thresholds: { lines: 80, branches: 80, functions: 80, statements: 80 },
    },
  },
});
```

## Offline by default

| Real dependency | Use |
|-----------------|-----|
| Outbound HTTP via `fetch` (undici) | `MockAgent` from `undici` + `setGlobalDispatcher`, with `disableNetConnect()`; or MSW `setupServer` with `onUnhandledRequest: "error"` |
| Database | Inject the query module and pass a fake; or an in-memory stand-in (`mongodb-memory-server`, SQLite) only if the repo already uses one |
| Time | `vi.useFakeTimers()` / `vi.setSystemTime()` |
| The app itself | Build it from `app.ts` in-process: `supertest(app)` (Express) or `app.inject()` (Fastify) — never `listen` on a port |

`tests/setup.ts` blocks the network so an unmocked call fails loudly:

```ts
import { MockAgent, setGlobalDispatcher } from "undici";

const agent = new MockAgent();
agent.disableNetConnect();
setGlobalDispatcher(agent);
```

If a test fails with a net-connect error, the test is missing a mock — do not
weaken the guard.

**Never mock what you are testing.** Mock the seam *outside* it: to test a
route, fake the domain/service it calls; to test a service, mock the transport;
to test domain logic, pass fakes for its dependencies.

## What to assert: the service contract

- **Status codes** — 200 / 401 missing auth / 403 wrong role / 404 not found or
  another owner's resource / 409 conflict / 422 or 400 validation (unknown
  fields rejected) / 500 unhandled.
- **The response envelope** on success *and* every error path.
- **Owner scoping** — one owner's data is invisible to another.
- **Validation** — zod rejects unknown fields and bad types; the handler is not reached.
- **Upstream failures** — 500 from upstream, timeout, malformed body, network
  error: each degrades per contract, never an unhandled rejection.
- **Secrets never echo** in responses or logs.

Use `it.each` / `describe.each` for the same invariant across a set.

## Commands

```bash
npm ci
npx vitest run --coverage            # whole suite, thresholds enforced
npx vitest run tests/api             # one subtree
npx vitest run -t "owner scoping"    # by name
npx vitest                           # watch mode while iterating
```

## Working procedure

1. **Look before adding.** Read the mirror-path test; reuse its helpers.
2. **Read the module under test end to end** — every branch is a case, including error branches.
3. **Write the test, run the subtree** while iterating.
4. **Run the full suite with coverage.**
5. **Read uncovered lines** for what you touched: a gap, or a justified ignore?
6. **Keep the docs true.**

### When a test fails

In order of likelihood: **a real bug** (fix `src/`), **a stale expectation**
(the contract changed on purpose — update the test and say so in the commit),
**a bad test** (flaky, over-mocked, asserting implementation — rewrite it).

<hard-rules>
Never delete a test to go green, never loosen an assertion, never lower
thresholds. Skips need `it.skip` with a comment giving the reason and a ticket.
</hard-rules>

## Anti-patterns

| Don't | Do |
|-------|----|
| `expect(result).toBeTruthy()` | assert the actual value / shape |
| `app.listen()` in tests | `supertest(app)` / `app.inject()` |
| Real URLs, real DB | MockAgent / MSW / injected fake |
| `vi.mock` of the module under test | mock the seam outside it |
| Snapshot of an entire response as the only assertion | assert the fields that matter |
| `setTimeout` / sleeps to wait | fake timers, or await the promise |
| Lowering thresholds to pass | cover the branch or a reasoned ignore |
| One giant `it()` with 20 expects | one behaviour per test, named for it |
| Floating promises in tests | `await` every async call; `await expect(...).rejects` |

