# Phases 4–7

Paths are relative to the workflow skill folder.

## Phase 4 — Research

Now read. Write findings to `research/<slug>.md` (template
`templates/research.md`) as you go, not at the end:

- **project structure** — read the `## Project structure` section of the repo's
  `AGENTS.md`. Missing, and the task will place or move code (feature,
  refactor)? Run `core-be-structure-service` now and settle the structure with the user
  before writing the plan. Record the structure in research.
- entry points and the files in scope (with line counts)
- how the pieces connect (a short dependency map)
- baseline measurements — run what the repo already has: tests, coverage,
  linters, type checker, and for security the scanners in `core-be-audit-security`.
  Record exact commands and summarised output. These numbers are the "before" in
  the final report.
- external facts you looked up (library versions, standards) with sources
- open questions for the user
- **README gaps** — compare the README with `core-be-structure-service/references/readme-standard.md` and with
  reality (dependency manifest scripts, `.env.example`, the settings module,
  routes, the folder tree). List what is missing or stale; the docs sync in
  Phase 7 fixes it.

If a tool the plan needs is not installed, record that and ask before installing
anything.

## Phase 5 — Plan, then stop

Write `plans/<slug>/tasks.md` from `templates/tasks.md`:

- goal (one sentence) and success criteria (from scope)
- feature / change: `Spec: specs/<NNN-topic>/spec.md`; every `AC-n` is covered
  by a step, and each step names the `AC-n` it serves. `core-be-plan` writes the
  durable design to `specs/<NNN-topic>/plan.md`; `core-be-tasks` writes this
  checklist; `core-be-analyze` must pass before you ask for approval
- skills that apply
- steps as a checkbox list; each step small enough to verify on its own.
  Mark steps that touch different files and do not depend on each other `[P]`,
  so parallel agents can claim them
- files expected to change or be created
- design notes for features: the system design pass
  (`core-be-build-feature/references/system-design.md`)
- risks and how each is mitigated; delivery and rollback per
  `references/SAFE-DELIVERY.md` (small reversible steps, expand → contract,
  concrete rollback recipe)
- verification: exact commands and expected results

Show the plan to the user (summary in chat, path to the file) and **wait for
explicit approval**. "Looks good", "go ahead", "approved" count; silence and
follow-up questions do not. If the user changes the plan, edit `tasks.md`, note
the change in `progress.md`, and ask again. On approval, write exactly
`**Status:** approved (YYYY-MM-DD, by <name>)` as the second line of `tasks.md`
and set INDEX status `approved`. The edit guard (`scripts/sdd-hook.sh`) and
`scripts/sdd-check.sh ci` read that line and the INDEX row.

For `audit` and `security` tasks the "plan" is the review plan (which files,
which checklists, which tools); the output is a report, not code changes.

## Phase 6 — Execute

Before the first edit, load `core-be-coding-standards`.

Work through the checklist in order. After each step:

1. tick the box in `tasks.md`
2. append to `progress.md` — what changed, why, commands run, result
3. run the step's verification; a red step is fixed before the next starts

When you discover something outside the approved scope (a bug next door, a
security hole in another module), **record it in `progress.md` under
"Out-of-scope observations" and tell the user**. Do not fix it unasked. Scope
creep is how a reviewed plan turns into an unreviewed diff.

Delegate where it helps: parallel read-only investigation, black-box test
writing, and a fresh-context review of the diff before the report
(`references/SUBAGENTS.md`). You stay responsible for everything they return.

**More than one agent editing this repo at once** (parallel sessions, an
orchestrator with workers, subagents that write files)? Coordinate through
`agent-tracking/board/` with `scripts/board.sh`
(`references/PARALLEL-AGENTS.md`): turn plan steps into tasks, claim before
you edit, lock the files you touch, never wait by re-reading code, and
`leave` when done. The last agent out removes the board.

Set INDEX status `in-progress`.

## Phase 7 — Report

**Docs sync first** (every task that changed code or config; audits and
security reviews change nothing, so they only register the pack). A developer
who clones the repo tomorrow must be able to install, configure, run, and find
their way from the README alone:

- update the README per `core-be-structure-service/references/readme-standard.md` — requirements, installation,
  environment table, endpoints, project structure, and stack must match the
  code as it now is; create the README if it is missing
- update `## Project structure` in `AGENTS.md` if folders changed
- refresh the marked block in `AGENTS.md` and the `CLAUDE.md` import
  (Phase 2, "Register the pack")
- feature / change: `core-be-converge` sets the spec's `Status` and change log
  and updates `specs/<NNN-topic>/plan.md` if the design changed
- list every doc change in `progress.md`

Then the report: read `references/REPORT.md` (format, sections, script policy),
build it from `templates/report.html` or `templates/report.md`, and delete every
template comment and every section marked for other task types.

Finish by setting INDEX status `done` with the report link, and give the user a
short chat summary plus the report path.

---
