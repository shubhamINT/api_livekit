---
name: core-be-debug
description: >
  Evidence-first debugging of Python (FastAPI) and Node.js
  (TypeScript) backend services: reproduce the bug as a failing test, rank
  hypotheses, test them (in parallel with investigator subagents when
  available), prove the root cause, fix it at the narrowest layer, and keep a
  regression test. Use whenever something is broken or behaves unexpectedly —
  "this endpoint returns 500", "getting an exception", "tests are failing",
  "flaky test", "it worked yesterday", "users see wrong data", "it's slow",
  "why does X happen", a pasted stack trace or error log — even if the user
  only says "fix this". Runs inside core-be-workflow as task type `debug`.
---

# Debug

The expensive debugging failure is the confident fix for the wrong cause: a
patch that makes the symptom disappear in one test while the bug lives on. This
skill stops that by demanding evidence at each step. No fix is written until
the bug is reproduced and the root cause is shown, not guessed.

**Gate — before anything else:** load `core-be-workflow`. If
`agent-tracking/plans/<slug>/scope.md` for this task is missing, run
`core-be-workflow` phases 1–2 now (task type `debug`, request recorded).
Invoking this skill directly (a slash command, a one-line request) is not an
exemption, and harness plan mode does not replace `tasks.md`. Scoping is light: the bug report is the scope. Ask only for what is
missing from:

- **Symptom** — exact error, status code, wrong output, or timing.
- **Expected** behaviour.
- **Where and when** — endpoint/job, environment, since when, how often
  (always / intermittent / under load), what changed recently.
- **Constraints** — hotfix now vs proper fix, may the fix change the public API.

If the user pasted a stack trace and the fix is obvious, still reproduce it —
the reproduction becomes the regression test.

**Always, even inside another task:** make sure the repo is registered — the
core-be block in `AGENTS.md` and the `@AGENTS.md` import in `CLAUDE.md`
(`core-be-workflow`, Phase 2, "Register the pack") — and, when code or config
changed, finish with the docs sync (`core-be-workflow`, Phase 7) so the README
matches the code.

---

## Phase 4 — Reproduce, then investigate

Log everything in `research/<slug>.md` as you go.

### 4.1 Reproduce

Write the smallest thing that shows the bug, in this order of preference:

1. a failing test at the mirror path (`core-be-write-tests`) — best, it
   becomes the regression test;
2. a script or `curl` against a local run;
3. for production-only bugs: the exact logs, request ids, and data shape, and
   a test that recreates that data shape offline.

Run it and record the failure verbatim. Cannot reproduce? Say so, list what was
tried, and ask for more data (logs, payload, version). Do not fix a bug you
cannot see — unless the user explicitly accepts a speculative fix, which is
then labelled as such everywhere.

### 4.2 Gather evidence

- Read the failing path end to end: route → service → data access → upstream.
- `git log -p --since=<when it started> -- <paths>`; for a regression with a
  known good commit, `git bisect run <repro command>`.
- Compare with a working case: which input, tenant, or environment differs?

### 4.3 Rank hypotheses

Write 2–5 hypotheses in research, each with: the mechanism, the evidence for
and against, and the cheapest check that would confirm or kill it. Rank by
likelihood × cheapness of the check.

### 4.4 Test hypotheses

Check the top hypothesis first. When two or more are independent and each
needs real reading or running, delegate one per `investigator` subagent in
parallel (`core-be-workflow/references/SUBAGENTS.md`); brief each with the
repro command and the single hypothesis to confirm or kill, with `file:line`
evidence. Verify what they return before trusting it.

### 4.5 State the root cause

One paragraph: the defect, the exact `file:line`, the mechanism from input to
symptom, and the evidence that proves it (the repro now explained, a log line,
a bisected commit). "The fix makes the test pass" is not proof of cause —
explain why.

Then ask: **where else does this bug class live?** (the same missing owner
filter in sibling routes, the same unguarded `None`). Record hits as
out-of-scope observations; tell the user; do not fix them unasked.

### 4.6 Check the spec

Search `specs/*/spec.md` for the behaviour. Spec states it correctly: the code is
wrong, and the regression test cites that `AC-n`. Spec wrong or silent: the bug is
a missing requirement, so stop and run `core-be-change` to edit the spec first,
then fix. No spec for this code: skip this step.

## Phase 5 — Plan the fix

In `tasks.md`: root cause (link to research), fix at the narrowest responsible
layer, the regression test, blast radius and rollback
(`core-be-workflow/references/SAFE-DELIVERY.md`). If the proper fix is
large, offer two options — a contained hotfix now and the structural fix as a
follow-up task — with a recommendation.

Get approval. For an urgent production bug the user may approve in one line;
the record is still written.

## Phase 6 — Fix and prove

1. The repro test is red on the unfixed code. (If it was written as a script,
   turn it into a test now.)
2. Apply the smallest fix that removes the cause, not the symptom. No
   drive-by refactors, no catch-and-ignore, no retry wrapped around a logic bug.
3. The repro test is green; the full suite, types, and lint are green.
4. For non-trivial fixes, a `reviewer` subagent (or your own separate review
   pass) checks the diff against the root cause: does it fix the mechanism, and
   only that?
5. Log the step in `progress.md`.

## Special cases

**Flaky tests.** Treat as a real bug until proven otherwise. Usual causes:
test order / shared state (run the one test alone and the file shuffled), time
(`now()`, timezones, sleeps — control the clock), concurrency (unawaited
promises/coroutines), unmocked network. Run it many times in a loop to measure
the failure rate before and after. Never add a retry or a longer sleep as the
fix.

**Slow / performance.** Measure before changing anything: reproduce with a
realistic data size, time it, profile (`py-spy`, `cProfile`, `node --prof`,
`clinic`, `EXPLAIN ANALYZE` for queries). Change one thing at a time and
re-measure. Usual causes: N+1 queries, missing index, unbounded result sets,
network calls in a loop, sync I/O on an async path. Report numbers before and
after.

**Production-only.** Never debug against production data or credentials from
the agent. Work from logs and recreated data shapes offline.

## Phase 7 — Report

<output>
Write the report to `agent-tracking/reports/<slug>.html` (or `.md`). Never the
repo root, the temp directory, or a hosted page (claude.ai Artifact, gist, docs
connector).

`core-be-workflow` report template and
`core-be-workflow/references/VISUAL-REPORT.md`. Required: symptom, root
cause with `file:line` and evidence, a sequence diagram of the failing path
with the defect marked, the fix (Current → Target of the changed step), the
regression test name, verification before/after, same-class occurrences found
elsewhere, and follow-up tasks.
</output>
