---
name: core-be-implement
description: >
  Build from the approved task checklist: test first for each acceptance
  criterion, tick each step, log progress, and stop when the code would diverge
  from the spec. Use after the user approves the plan, then run `core-be-converge`.
  Never starts without an approved plan and a clean analysis.
---

# Implement

<gate>
the checklist at `agent-tracking/plans/<slug>/tasks.md` is approved,
and `core-be-analyze` left no Critical or High finding. Either missing? Stop.
</gate>

Engineering rules come from `core-be-build-feature` (security at every trust
boundary, tests through the interface, docs in the same change) and
`core-be-coding-standards` (load it before the first edit).

## Steps

For each step in order (`core-be-workflow`, Phase 6):

1. If it is a behavioural `AC-n`: write its test from the spec's wording and run
   it. It must fail for the right reason. A spec with five or fewer criteria may
   write all its tests first and take one red run. A boundary test that already
   passes on existing code is allowed: log it in `progress.md` as a guard.
2. Write the smallest code that makes it pass.
3. Run the step's verification. A red step is fixed before the next starts.
4. Tick the box in `tasks.md`; append to `progress.md`: what changed, why,
   commands, result.

`[P]` steps may run in parallel through the board
(`core-be-workflow/references/PARALLEL-AGENTS.md`).

## When the code wants to diverge from the spec

<hard-rules>
Stop. Do not "just make it work". The spec is wrong, the plan is wrong, or the
requirement changed.

- Spec wrong or silent: tell the user, run `core-be-change`, then resume.
- Plan wrong: edit `specs/<NNN-topic>/plan.md`, re-run `core-be-analyze`, tell the
  user.
- Something outside the agreed scope: record it in `progress.md` under
  Out-of-scope observations and tell the user. Do not fix it unasked.
</hard-rules>

When the last step before converge is ticked, run `core-be-converge`.
