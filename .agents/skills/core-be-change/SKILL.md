---
name: core-be-change
description: >
  Change an existing feature the spec-driven way: edit its spec first, then
  plan only the difference. Use whenever the user asks to modify, extend,
  limit, tighten, or remove behaviour that already exists — "limit it to 10k rows",
  "change how X works", "drop support for Y" — and when a bug turns out to be a
  wrong or missing requirement. Not for behaviour-preserving cleanup (use the
  refactor skill) and not for a bug the spec already forbids (use debug).
---

# Change an existing feature

**The rule:** edit the spec first, then the plan, then the code. A change made
in code only leaves the spec lying.

<gate>
`core-be-workflow` is loaded (do not re-read it); scope agreed.
</gate>

## Is it a change?

| The request... | Route |
|----------------|-------|
| alters, adds, limits, or removes what the feature does | this skill |
| keeps behaviour identical and only restructures code | refactor skill, no spec edit |
| says the code breaks something the spec already states | `core-be-debug`; the regression test cites that `AC-n` |
| reveals the spec was wrong or silent (a bug from a missing requirement) | this skill, then fix |
| adds a wholly new feature | `core-be-specify` |

## Steps

1. **Find the spec.** `grep` `specs/*/spec.md` for the feature. None, but code
   exists? Write one from the code, tests, and README, set
   `Status: reconstructed`, and have the user confirm it before relying on it.
   This is a one-time catch-up, not a license to skip specs.
2. **Edit the spec.** Change, add, or retire acceptance criteria. Retire by
   striking through with a reason; never reuse an `AC` number. Add a row to the
   **Change log**: date, what changed, task slug. Set `Status: draft` until the
   user approves.
3. **Impact.** Search the code and tests for the affected `AC-n`. List the
   plan sections in `specs/<NNN-topic>/plan.md`, the tests, and the code that
   the change touches. Write the list in `research/<slug>.md`.
4. **Inherit.** Scope inherits the Agreed-scope rows of the spec's original
   task; ask only about the change. The research file holds the impact list and
   the baseline; skip README gaps and structure unless folders change.
5. Hand over to `core-be-clarify` (resolve open questions), then `core-be-plan` in
   **delta mode**, `core-be-tasks`, `core-be-analyze`, `core-be-implement`, `core-be-converge`.

A change that grows beyond the original feature is a new spec. Say so and
route to `core-be-specify`.
