# Python Testing

Every module under `src/` has a test that fails when its logic breaks. That is
the whole standard. Everything below is how to hit it without writing a test
framework of your own.

> **A great developer seeks simplicity. An idiot developer seeks complexity.**

---

## Non-negotiables

<hard-rules>
1. **A new or changed module ships with its test in the same change.** Not a
   follow-up task. If you touched a branch, a loop, a parser, a money path, or a
   security path, one test came with it.
2. **Coverage floor is 80%** (`fail_under` in `pyproject.toml`). It is a floor,
   never a target to lower. A line that is genuinely untestable gets
   `# pragma: no cover` **with a reason on the same line** — you never edit
   `fail_under` to make a suite pass.
3. **No test touches the network, a live database, or a real LLM.** Ever. See
   *Offline by default*.
4. **The runner is `uv run pytest`.** No `sys.path` hacks, no
   `if __name__ == "__main__":` runner blocks, no `PYTHONPATH=` prefix — config
   handles it.
</hard-rules>

---

## Layout: `tests/` mirrors `src/`

The test's path is the source path. A reader finds the test for
`src/scheduling/schedule_service.py` without searching.

```
src/scheduling/schedule_service.py -> tests/scheduling/test_schedule_service.py
src/api/routes/v1/schedules.py     ->  tests/api/routes/test_v1_schedules.py
src/core/db/db_connect.py          ->  tests/core/db/test_db_connect.py
```

```
tests/
  conftest.py     # shared fixtures — the ONLY place they live
  factories.py    # model builders, one per request/definition model
  api/  core/  scheduling/     # mirrors of src/
```

Rules:

- **Filenames are `test_<module>.py` and globally unique.** There are no
  `__init__.py` files in `tests/` (implicit namespace packages), so two files
  with the same basename collide at collection time.
- **`python_files = ["test_*.py"]`** in config, deliberately *not* pytest's
  default that also matches `*_test.py` — a source module named `v1_test.py` is a
  request model, not a test.
- **Fixtures go in `conftest.py`, factories in `factories.py`.** A fixture
  re-created inside a test file is a bug: import it, don't rebuild it.
- **Test names state the invariant**, not the mechanics:
  `test_observed_route_overrides_the_model`, not `test_route_2`.

---

## Offline by default

Every seam this codebase talks to is mocked at its boundary; never let a test
dial out.

| Real dependency | Use | Fixture / pattern |
|---|---|---|
| Outbound HTTP (webhook actions, notify callback) | `httpx.MockTransport` (`respx` is fine too) | `_mock_client`: swap `actions.httpx` for an `httpx.AsyncClient(transport=MockTransport(...))` |
| MongoDB / Beanie (documents) | patch the seam | async fakes for `Schedule.get` / `insert` / `save`, `run_action`, `notify` |
| The scheduler | patch the entrypoints | `start_scheduler` / `shutdown_scheduler` / `get_scheduler`, fake `MongoDBJobStore` |
| The app itself (routes, middleware, exception handlers) | `httpx.AsyncClient` over `ASGITransport` | `client` fixture (Mongo + scheduler lifecycle patched) |

The `no_network` autouse fixture (in `tests/conftest.py`) turns any unmocked
outbound socket call into an `AssertionError`. If a test suddenly fails with
*"unmocked outbound HTTP call"*, the test is missing a mock — do not weaken the
guard.

**Never mock what you are testing.** Patch the seam *outside* it: to test a route
patch the service it delegates to, to test the service patch the transport, to
test the job executor patch `Schedule.get` / `run_action` / `notify`. Patching
the function under test proves nothing.

---

## What to assert: the contracts this service promises

Test the boundary, not the implementation. For this codebase that means:

- **Status codes** — `200` / `401` missing `X-Owner-Id` / `404` not found or
  another owner's row / `409` name conflict (unique per owner) / `422` strict
  validation (unknown fields, bad timezone, invalid trigger args) / `500`
  unhandled error.
- **The `ApiResponse` envelope** — `{success, message, data}` on success *and*
  every error path (exception handlers emit it centrally).
- **Owner scoping** — one owner's rows are invisible to another (a foreign id is
  a `404`, not a `200`).
- **SSRF guard** — webhook targets on loopback/private/link-local IPs are
  blocked; `WEBHOOK_ALLOW_PRIVATE_HOSTS` is the only bypass.
- **Retry & backoff** — a non-2xx or timeout retries up to `max_retries` times; a
  run that exhausts retries records `last_status: "error"` with the reason.
- **Best-effort stays best-effort** — a failed `notify` callback must not fail
  the run or the request.
- **Secrets never echo** — webhook `headers` (auth tokens) appear in no response
  body and no run record.
- **Run history** — every fire writes a `ScheduleRun`; reads are newest-first.

Failure modes are as much a contract as the happy path: mock a 500, a
`ConnectError`, a malformed body, an empty result — each must degrade to data,
not raise.

Use `@pytest.mark.parametrize` when the same invariant holds across a set (every
`trigger_type`, every webhook HTTP method, each error status). One parametrized
test beats six copy-pastes.

---

## Commands

```bash
uv sync --group dev                     # install the dev group once
uv run pytest                           # whole suite, coverage on, 80% floor enforced
uv run pytest tests/api/routes -q       # one subtree
uv run pytest -k owner_scoping           # one invariant by name
uv run pytest --no-cov -x                # fast loop while iterating, stop at first failure
```

Config lives in `pyproject.toml` — `[dependency-groups] dev`,
`[tool.pytest.ini_options]` (`pythonpath`, `testpaths`, `python_files`,
`asyncio_mode = "auto"`, coverage in `addopts`), and `[tool.coverage.*]`
(`source`, `fail_under`).

`asyncio_mode = "auto"` means an `async def test_*` needs no decorator.

---

## Working procedure

1. **Look before adding.** Read the existing test for the module (mirror path)
   and reuse its fixtures and factories. Most "I need a new fixture" turns out
   to be a factory kwarg.
2. **Read the module under test end to end** — every branch is a case, including
   the error branches.
3. **Write the test, run the subtree**, not the whole suite, while iterating.
4. **Run `uv run pytest`** — the full suite plus the coverage floor.
5. **Read the `Missing` column** for what you touched. Uncovered branch, or a
   deliberate exclusion with a reason? Anything else is a gap.
6. **Keep the docs true.** New endpoint, env var, or collection means
   `README.md` / `CLAUDE.md` change in the same commit.

### When a test fails

Read the assertion before touching anything. A failure is one of three things,
in this order of likelihood:

1. **A real bug** — fix `src/`, keep the test.
2. **A stale expectation** — the contract changed on purpose; update the test to
   the new contract and say so in the commit.
3. **A bad test** — flaky, over-mocked, or asserting an implementation detail;
   rewrite it to assert the invariant.

Never delete a test, never loosen an assertion to green, never lower
`fail_under`. Skipping needs `@pytest.mark.skip(reason=...)` with a real reason.

### Keeping tests current as the code grows

- New endpoint → route test: happy path, every error status, owner scoping.
- New webhook action / notify → `MockTransport` tests: success, non-2xx, HTTP
  error, transport error, retry exhaustion.
- New Document / DB function → seam-fake test: round-trip, scoping, absent row.
- New trigger type → trigger-builder test: what trigger args construct what
  APScheduler trigger, and which values are rejected.
- New config field → assert its default, and its bounds if it has any.
- Deleted feature → delete its test in the same commit. Dead tests rot.

---

## Anti-patterns

| Don't | Do |
|---|---|
| `if __name__ == "__main__":` self-check block | a `test_*.py` file |
| `PYTHONPATH=. uv run python tests/foo.py` | `uv run pytest` |
| `sys.path.insert(...)` in a test | `pythonpath = ["."]` in config |
| A fixture copy-pasted into three files | one fixture in `conftest.py` |
| `assert result` | assert the actual value / shape |
| Mocking the function under test | mock the seam outside it |
| A real URL, a real Mongo, a real socket | `httpx.MockTransport`, a seam fake |
| Lowering `fail_under` to pass | cover the branch, or `# pragma: no cover <reason>` |
| One giant `def test():` with 20 asserts | one behaviour per test, named for it |
| `time.sleep()` to wait for something | drive the async code directly |

