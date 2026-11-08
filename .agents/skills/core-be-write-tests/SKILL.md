---
name: core-be-write-tests
description: >
  How to write, fix, and structure tests for Python (pytest) and
  Node.js / TypeScript (vitest) backend services: tests mirror the source tree,
  run fully offline (mocked HTTP, DB and LLM seams), assert the service
  contract, and hold an 80% coverage floor. Use whenever a test is written or
  changed, whenever a module under src/ is added or edited (its test ships in
  the same change), when a suite fails or coverage drops, and when asked to "add
  tests", "raise coverage", "fix the failing tests", "set up testing", or "write
  characterization tests before refactoring".
---

# Write Tests

Every module under `src/` has a test that fails when its logic breaks. That is
the whole standard. The stack-specific mechanics are in the references; the
rules below hold for both.

| Stack | Read |
|-------|------|
| Python — pytest, httpx `MockTransport`, `uv run pytest` | `references/python-pytest.md` |
| Node / TypeScript — vitest, undici `MockAgent` / MSW, supertest / `app.inject` | `references/node-vitest.md` |

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

## Non-negotiables (both stacks)

<hard-rules>
1. **Tests ship with the change.** A new or changed branch, loop, parser,
   money path, or security path comes with its test in the same change.
2. **Coverage floor 80%.** A floor, never a target to lower. An untestable line
   gets an explicit ignore comment **with the reason on the same line**.
3. **Offline.** No test touches the network, a live database, or a real LLM. A
   global guard turns any unmocked outbound call into a failure; never weaken it.
4. **Test the interface, mock the seam outside it.** To test a route, fake the
   service it calls; to test a service, mock its transport. Mocking the function
   under test proves nothing.
5. **Tests mirror the source tree** (following the repo's recorded structure —
   see `core-be-structure-service`), one behaviour per test, names that state the
   invariant (`returns 404 for another owner's order`).
</hard-rules>

## What to assert — the service contract

- Status codes for every path: success, 401 missing auth, 403 wrong role, 404
  not found **or another owner's resource**, 409 conflict, 422/400 validation,
  500 unhandled.
- The response envelope on success *and* every error.
- Owner / tenant scoping: one owner's data is invisible to another.
- Validation: unknown fields and bad types are rejected before the handler runs.
- Upstream failures: 5xx, timeout, malformed body, network error — each degrades
  per contract, never an unhandled exception.
- Secrets never appear in responses, logs, or stored records.
- Limits: page size maximums, body size, rate limits where implemented.

Parametrise when one invariant holds across a set (every status, every type).

## Characterization tests (before a refactor)

When `core-be-refactor-code` finds no tests around the code to be changed, write tests
that pin **current** behaviour through the public interface — including odd
behaviour. If current behaviour looks like a bug, pin it anyway, name the test
accordingly (`test_currently_returns_200_on_missing_amount`), and report it as
an observation. The refactor must keep these green.

## Test quality — reject test theater

A test is worthless if no plausible bug would make it fail. Reject:
`assert result` / `toBeTruthy()` only; expected values recomputed with the same
logic as the implementation; mocking the unit under test; snapshots as the only
assertion; happy path only; sleeps instead of controlled time.

## When a test fails

In order of likelihood: **a real bug** (fix the source, keep the test), **a
stale expectation** (the contract changed on purpose — update the test and say
so), **a bad test** (flaky, over-mocked, asserting implementation — rewrite it).
Never delete a test to go green, never loosen an assertion, never lower the
coverage floor. Skips carry a reason and a ticket. If the cause is not obvious
within a few minutes, or the failure is flaky, switch to `core-be-debug`.

## Independence — who writes the test

Tests written by reading the implementation tend to assert what the code does,
bugs included. For new behaviour, write tests from the contract first — or
delegate to a `test-writer` subagent that sees the contract and signatures but
not the function bodies (`core-be-workflow/references/SUBAGENTS.md`).
For a large campaign, split by module across test-writers with disjoint test
paths. Finish with a `reviewer` pass that names, for each new test, the
plausible bug that would make it fail.

## Working procedure

1. Read the existing test at the mirror path; reuse its fixtures/helpers.
2. Read the module under test end to end — every branch is a case.
3. Write the test; run the subtree while iterating.
4. Run the full suite with coverage; read the uncovered lines you touched.
5. Headers on new files; docs updated if behaviour or config changed.

## Report

<output>
Write the report to `agent-tracking/reports/<slug>.html` (or `.md`). Never the
repo root, the temp directory, or a hosted page (claude.ai Artifact, gist, docs
connector).

When tests are the task (not a step inside another task), use the `core-be-workflow`
report template and `core-be-workflow/references/VISUAL-REPORT.md`: a metrics table for
coverage and test count before/after, and a list of the behaviours now pinned
(one line each, named like the tests).
</output>
