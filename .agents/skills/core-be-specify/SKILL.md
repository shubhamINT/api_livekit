---
name: core-be-specify
description: >
  Write the persistent spec for a new feature: `specs/<NNN-topic>/spec.md`, which
  says what it does and why, with numbered testable acceptance criteria and
  open questions marked. Use whenever the user asks to build, add, or implement
  something new — "add CSV export" — after scope is agreed through
  `core-be-workflow`. Not for changing an existing feature (use `core-be-change`), and not for
  refactors, audits, security reviews, debugging, or test work.
---

# Specify

`agent-tracking/` records what an agent did. A spec records what the system does
now. It outlives the task: the next change starts from it, and a new developer
reads it instead of reverse-engineering code.

<gate>
`core-be-workflow` is loaded (do not re-read it); scope must be agreed (`scope.md`). Missing
`specs/constitution.md`? Run `core-be-constitution` first, or tell the user and note
it in `progress.md` if they decline.
</gate>

**The rule:** behaviour starts at the spec. Never write code first and the spec
afterward.

Idea still fuzzy, or the user asks "should we build this"? Run `core-be-assess`
first. This skill starts when the answer is `go`.

## Layout

```
specs/
├── constitution.md
└── 001-csv-export/
    ├── spec.md        # this skill
    └── plan.md        # core-be-plan
```

`NNN` is the next free number: scan `specs/` for folders named `NNN-*`, take the
highest, add one, zero-pad to three digits. This skill never creates a branch or
commits; the user chooses the branch.

## Steps

1. Get the folder name from `sh core-be-workflow/scripts/sdd-check.sh next <topic>` (never count by hand). Copy
   `templates/spec.md` to `specs/<that-name>/spec.md`.
2. Fill it from the user's request and the agreed scope. The spec says **what**
   and **why**. It never names a framework, library, table, or file; those belong in the plan. A named external standard (RFC, ISO) is fine.
3. Acceptance criteria are numbered `AC-1`, `AC-2`, ... and testable.
   Each criterion is an input, an action, and an observable result. Cover
   the happy path, every error case, who may call it and see what, and limits
   (size, rate, time).
4. Anything you would have to guess goes under **Open questions** as
   `[NEEDS CLARIFICATION: ...]`. Never fill a gap with an assumption.
5. Add the spec path to `scope.md` (row `Spec`). Acceptance criteria live in the
   spec only; do not copy them into `scope.md`.
6. Run `sh core-be-workflow/scripts/sdd-check.sh spec specs/<NNN-topic>`; fix every CRITICAL and HIGH line. Set
   `Status: draft`. `core-be-clarify` sets `approved` once the user approves the
   spec; `core-be-converge` sets `implemented`.
7. Hand over to `core-be-clarify`.
