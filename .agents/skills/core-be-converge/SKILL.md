---
name: core-be-converge
description: >
  Check the finished code against its spec and loop until they agree: one table
  row per acceptance criterion with evidence, a drift scan for behaviour the spec
  never asked for, and a constitution re-check. Returns `Converged` or
  `Not converged`. Use at the end of `core-be-implement`, and any time someone asks
  whether the code still matches the spec.
---

# Converge

<gate>
code exists for the spec; tests are runnable.
</gate>

## Steps

1. **Evidence table**, one row per active `AC-n` (not retired ones). Write it into
   `progress.md` under `## Converge`; the report copies it:

   | AC | Evidence | Code | Status |
   |----|----------|------|--------|
   | AC-1 | test (`tests/test_export.py::test_csv_header`) | `path/to/file:42` | met |

   Evidence for an `AC-n` is a passing test that exercises it. Run the tests. Never mark `met` from reading code. Refresh every `file:line` after any later
   edit; line numbers drift.

   After writing it, run `sh core-be-workflow/scripts/sdd-check.sh converge <slug>`; it exits 1 while any criterion in the
   task's `**Covers:**` line is not `met` or lacks evidence. The table itself still
   lists every active criterion, so a change cannot break an older one unseen.

   Status: `met` (evidence exists and passes), `partial` (implemented, evidence
   missing or incomplete), `missing` (not implemented).
2. **Drift scan.** Read the diff for behaviour the spec does not state: a
   route, field, flag, option, or error path with no `AC-n`. Either add it to the
   spec (the user decides, through `core-be-change`) or remove it.
3. **Constitution re-check** on the final diff, not just the plan.
4. **Design check.** Does the shipped design still match
   `specs/<NNN-topic>/plan.md`? Update the plan if the design changed for a good
   reason, and log it.
5. **Verdict.**
   - `Converged`: every row `met`, no drift, constitution passes, tests green.
   - `Not converged`: list what is missing.

   Write the verdict as its own line in `progress.md`, exactly `Verdict: Converged`
   or `Verdict: Not converged`. The Stop hook and CI read it.

## Loop

`Not converged`: fix what is listed (through `core-be-implement`, or `core-be-change` if
the spec was at fault), then converge again. After **three** rounds without
`Converged`, stop and show the user what keeps failing and why.

## On `Converged`

Set the spec's `Status: implemented`, add the change-log row, and put the table
in the report (`core-be-workflow`, Phase 7). The spec and plan are left for the user to
commit with the code.
