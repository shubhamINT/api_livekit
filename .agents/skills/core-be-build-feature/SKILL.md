---
name: core-be-build-feature
description: >
  How to add new behaviour to a Python (FastAPI) or Node.js
  (TypeScript) backend service the right way: agreed acceptance criteria, the
  right layer, a small deep interface, tests first, security at every trust
  boundary, docs in the same change. Use whenever the user asks to
  build, add, implement, integrate, or support something new — "add an
  endpoint", "build a webhook", "integrate Stripe", "support CSV export", "new
  job that…" — after scope and plan are agreed through core-be-workflow.
---

# Feature Development

A feature is done when it does what was agreed, is tested through its
interface, is safe at its trust boundaries, sits in the right place, and the
docs say it exists. Code that works on the happy path is roughly a third of that.

<gate>
**Gate — before anything else:** load `core-be-workflow`. If
`agent-tracking/plans/<slug>/scope.md` for this task is missing, or its
"Agreed scope" rows are not all filled, run `core-be-workflow` phases 1–3 now and
end your turn at the scope questions. Invoking this skill directly (a slash command, a one-line
request) is not an exemption, and harness plan mode does not replace
`tasks.md`. This skill supplies phases 4–7.
</gate>

**Always, even inside another task:** make sure the repo is registered — the
core-be block in `AGENTS.md` and the `@AGENTS.md` import in `CLAUDE.md`
(`core-be-workflow`, Phase 2, "Register the pack") — and, when code or config
changed, finish with the docs sync (`core-be-workflow`, Phase 7) so the README
matches the code.

## Phase 4 — Research

1. **Acceptance criteria** — read them from `specs/<NNN-topic>/spec.md`
   (`core-be-specify`): inputs, outputs, error cases, who may call it and see
   what, limits (size, rate, time). Do not copy them into `scope.md`. Each
   `AC-n` becomes at least one test. No spec yet? Run `core-be-specify` first.
   This skill supplies the engineering rules; the SDD chain
   (`core-be-plan`, `core-be-tasks`, `core-be-implement`) calls it.
2. **Read the neighbourhood** — the repo's recorded structure (`AGENTS.md` →
   `## Project structure`; if missing, run `core-be-structure-service` first), the closest existing
   feature of the same kind (a similar route, a similar upstream client), and its
   tests. The new feature copies that shape unless there is a reason not to.
3. **Reuse before writing** — search for existing helpers, clients, models,
   error types, and fixtures that already do part of the job.
4. **External facts** — for any library or upstream API involved, read the
   docs for the **installed** version and record the relevant bits with links in
   `research/<slug>.md`. Never code against a remembered API (`core-be-audit-code/references/ai-generated-code.md` §1).
5. **Baseline** — run tests, lint, types; record results.

## Phase 5 — Design and plan

Think like the engineer who will be paged when this breaks. Before the
interface, run the **system design pass** in `references/system-design.md` and
write its answers into the Design notes of `tasks.md`: numbers, data and
invariants, concurrency and idempotency, failure mode of every outbound call,
limits, compatibility, observability. Answer each in a line or write
`N/A — reason`; add machinery (queues, caches, retries, flags) only for a risk
named there.

Then design the interface, in `tasks.md`:

- **HTTP surface**: method, path, auth, request schema, response schema (in the
  service's envelope), every status code.
- **Placement**: which files in which folder, exactly as the recorded project
  structure's "where does X go" table says. HTTP handlers stay HTTP-only;
  business logic and data access go where the structure puts them.
- **Module interface**: smallest interface that covers the acceptance criteria
  (`core-be-coding-standards/references/module-design.md`: deep modules, no speculative seams — one adapter is not a
  seam; production + test fake is two).
- **Data**: new collections/tables/fields, indexes, migrations (reversible).
- **Config**: new env vars with defaults, added to the settings module and `.env.example`.
- **Security**: trust boundaries crossed and the control for each (see below).
- **Tests**: list them, mapped to acceptance criteria.
- **Docs**: README sections that change.

Steps in `tasks.md` follow `core-be-workflow/references/SAFE-DELIVERY.md`:
small, each green and revertable, expand → migrate → contract for anything
already deployed, riskiest step last, and a concrete rollback recipe. Get
approval.

## Phase 6 — Build

1. **Tests first where the behaviour is clear**: write the failing test for the
   next acceptance criterion, make it pass with the least code, repeat. At
   minimum every criterion has a test by the end of the step that implements it.
   For more than a couple of criteria, hand them to a `test-writer` subagent
   (`core-be-workflow/references/SUBAGENTS.md`) — it writes the tests from
   the criteria without reading your implementation, so they check the
   contract rather than echo the code.
2. **Smallest change at the right layer.** Routes validate, delegate, shape the
   response. Business rules in the domain. I/O in services, behind a function
   that condenses the upstream response at the boundary.
3. **Security controls by default** at every boundary the feature crosses:
   - authentication on the route, and **ownership / role checks on every resource access**
   - schema validation with unknown fields rejected (pydantic `extra="forbid"` / zod `.strict()`)
   - parameterised queries; no shell; no dynamic code
   - timeouts on outbound calls; limits on sizes, page lengths, concurrency
   - secrets only from config; never logged or returned
   - errors through the central handler; no internals in responses
4. **No new dependency** unless the plan approved it — then verify it exists, is
   maintained, and licence-compatible with the repo's own licence (read `LICENSE`); flag GPL/AGPL/unknown for human review. New files: follow the repo's existing licence-header convention if it has one.
5. **Docs in the same change**: README endpoint table, env table, structure
   tree, data stores; docstrings / JSDoc on public functions.
6. Log each step in `progress.md`.

## Phase 6b — Self-review before calling it done

Start with a fresh-context review: a `reviewer` subagent (or, without
subagents or for a diff under about 50 lines, a separate pass reading `tasks.md`
before the diff) checks the diff
against the plan, the design notes, and the items below. Fix or answer every
finding before the gates.

- The AI-generated-code self-review in `core-be-coding-standards` (all eight checks).
- `core-be-audit-security` checklist items for every trust boundary the feature touched.
- `core-be-coding-standards` checklist.
- Gates: formatter, linter, type checker, full test suite, coverage ≥ 80%.
  All green, no new ignores.

## Phase 7 — Report

<output>
Write the report to `agent-tracking/reports/<slug>.html` (or `.md`). Never the
repo root, the temp directory, or a hosted page (claude.ai Artifact, gist, docs
connector).

`core-be-workflow` report template and `core-be-workflow/references/VISUAL-REPORT.md`.
Required visuals: a Current → Target component graph with the added parts
green, and a sequence diagram of the new request path end to end.
Feature-specific content: what was built
(mapped to acceptance criteria), the interface (routes / functions / events),
files added and changed, tests added (mapped to criteria), config and data
changes, verification results before/after, known limits and follow-ups.
</output>
