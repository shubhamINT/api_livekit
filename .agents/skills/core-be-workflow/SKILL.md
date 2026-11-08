---
name: core-be-workflow
description: >
  The mandatory scope → track → plan → approve → execute → report workflow for
  every non-trivial backend task (feature, refactor, code audit, security audit,
  test campaign, debugging). Use it BEFORE touching code whenever the user asks
  to refactor, clean up, audit, review, "check for bad code", find
  vulnerabilities, add a feature, fix a bug, or raise test coverage — even when they phrase it casually ("fix this
  mess", "make it secure", "is this code ok"). Creates and maintains the
  `agent-tracking/` folder (scope, research, plan, progress, report) so every
  piece of agent work is structured and traceable. Also keeps the repo README current
  (setup, run, env, endpoints, structure) and registers the pack in the repo's
  AGENTS.md and CLAUDE.md so later agents follow the rules without being told.
  Also runs `explain` tasks: a read-only walkthrough of how existing code works, as an HTML page.
  Also runs `init` tasks: set up or repair a repo (`AGENTS.md`, `CLAUDE.md`, tracking, constitution) and agree the project brief with the user.
---

# Workflow

Agents that jump straight into code produce changes nobody asked for, audits of
the wrong scope, and no record of why anything happened. This skill prevents
that. Every non-trivial task runs through seven phases, and each phase leaves a
file on disk before the next begins. The files are the audit trail: a reviewer
who never saw the conversation must be able to reconstruct what was asked, what
was decided, and what was done.

Trivial tasks (a question, a typo, a one-line rename) skip this skill — but a
trivial change that adds or changes an endpoint, env variable, dependency,
script, or folder still updates the README (`core-be-structure-service/references/readme-standard.md`). Unsure =
not trivial. Touching more than one file, any trust boundary (auth, input
parsing, external calls, secrets), or any public interface is never trivial.

With the edit guard installed (`scripts/sdd-hook.sh`), even a trivial source edit
needs one row in `agent-tracking/INDEX.md` (type `trivial`, status `in-progress`)
so the edit is on record. No scope interview, plan, or report for it.

Paths like `core-be-<skill>/references/<file>.md` name a sibling skill: resolve
them from the parent of this skill's base directory. Sibling missing? Tell the
user to install the whole pack.

Token economy applies to every phase (`references/TOKEN-ECONOMY.md`): read
cheap, build less, think to the point, reply short, and never cut a check to
save tokens.

---

## Quick path: feature and change

Everything below applies. This is the order of outputs and stops for the two
spec-driven types, so you can see the whole run first.

| Stop | Before it | Files written |
|------|-----------|---------------|
| 1. Scope questions | classify, bootstrap tracking | `agent-tracking/INDEX.md` row, `plans/<slug>/scope.md` |
| 2. Spec questions | `core-be-specify` (`core-be-change` for a change) | `specs/constitution.md` (once), `specs/<NNN-topic>/spec.md` |
| 3. Plan approval | `core-be-clarify`, `core-be-plan`, `core-be-tasks`, `core-be-analyze` | `specs/<NNN-topic>/plan.md`, `plans/<slug>/tasks.md`, `research/<slug>.md` |
| done | `core-be-implement`, `core-be-converge`, docs sync | code and tests, `reports/<slug>.md` or `.html` |

`explain` stops once (scope questions), then runs `core-be-explain`: no plan, no approval, no code.
`init` stops three times (scope questions, onboarding plan, project brief), then hands the first feature to `core-be-specify`. It changes no source.
Every other type skips the spec files and runs Phases 1–7 below.

**Scripts that check you.** `sh core-be-workflow/scripts/sdd-check.sh next|spec|analyze|converge|status|ci|doctor` and the
edit guard `scripts/sdd-hook.sh` (a Claude Code hook) enforce this chain. When a
script or the guard says no, do what its message says; never edit the scripts,
the hook config, or set `SDD_GUARD`.

**Read lazily.** Read a chain skill when its step starts, never before. Read a
reference only when a step names it. Reading everything up front wastes the
context the work needs.

## Phase 1 — Classify

Name the task type. It sets the slug and which skills apply.

| Type | Follow-on skill(s) |
|------|--------------------|
| `feature` | `core-be-constitution` (once, if `specs/constitution.md` is missing) → `core-be-specify` → `core-be-clarify` → `core-be-plan` → `core-be-tasks` → `core-be-analyze` → *approval* → `core-be-implement` → `core-be-converge`; `core-be-build-feature` supplies the engineering rules inside plan and implement |
| `change` | `core-be-change` → `core-be-clarify` → `core-be-plan` (delta) → `core-be-tasks` → `core-be-analyze` → *approval* → `core-be-implement` → `core-be-converge` |
| `assess` | `core-be-assess` (verdict `go`, `needs-clarification`, or `kill`) |
| `constitution` | `core-be-constitution` |
| `explain` | `core-be-explain` |
| `init` | `core-be-init` |
| `refactor` | `core-be-refactor-code` |
| `audit` | `core-be-audit-code` |
| `security` | `core-be-audit-security` |
| `test` | `core-be-write-tests` |
| `debug` | `core-be-debug` |
| `structure` | `core-be-structure-service` |
| `health` | `core-be-add-health-endpoint` |

`change` is new behaviour on an existing feature ("limit it to 10k rows"). It
starts at the spec: `core-be-change` edits `specs/<NNN-topic>/spec.md` first,
then the plan is edited for the delta. `feature` and `change` are spec-driven
(SDD): the spec and constitution drive the plan, the checklist, the check before
coding, and the check after. The other types change no behaviour and need no
spec. `feature` and `change` stop the turn three times: (1) scope questions,
(2) spec questions from `core-be-clarify`, (3) plan approval after
`core-be-analyze`. Unsure which? A new feature is `feature`; altering one that exists is
`change`; a vague idea is `assess`.

A request can span types ("audit and fix"). Split it: the audit is one task, the
fix is a second task planned from the audit's findings. This keeps each report
honest about what was examined versus what was changed.

## Phase 2 — Bootstrap tracking (before asking anything)

The very first thing you write is the record of what the user asked — before the
scope interview, so the questions and answers are captured too. Create the
tracking layout if it is missing. It belongs in version control alongside the
code, but **you never commit, branch, or push on your own** — the user commits
it with their change, unless they ask you to. Creating these files
is not "starting work": no source file is touched.

```
agent-tracking/
├── INDEX.md                         # one row per task
├── plans/
│   └── <slug>/
│       ├── scope.md                 # the user's words + agreed scope
│       ├── tasks.md                 # the approved plan (checklist)
│       └── progress.md              # step log, decisions, deviations
├── research/
│   └── <slug>.md                    # what was read / measured, and what it showed
└── reports/
    └── <slug>.html | <slug>.md      # the deliverable
```

**Slug**: `YYYY-MM-DD-<type>-<short-topic>`, lowercase, hyphenated, e.g.
`2026-09-24-security-payments-api`. Same slug everywhere for one task.

Copy the templates from this skill's `templates/` directory and fill them in:

- `INDEX.md` — create from `templates/INDEX.md` if absent; append one row now
  (status `scoping`), and update the row at every phase change.
- `plans/<slug>/scope.md` — from `templates/scope.md`. Quote the user's original
  request verbatim now. Fill the "Agreed scope" table as answers arrive, and log
  every question you ask (and its answer, or "awaiting answer") in the
  clarification log. If the topic is unclear, use a provisional slug and rename
  the folder once scope is agreed.

### Register the pack in the repo

Every non-trivial task: make sure the repo root carries the pack rules
(`AGENTS.md` block, `CLAUDE.md` import). It is a no-op when nothing changed.
Procedure: `references/REGISTER-PACK.md`. Read it the first time in a repo, and
whenever `AGENTS.md` or `CLAUDE.md` is missing or lacks the markers.
`sh core-be-workflow/scripts/sdd-check.sh doctor` lists what is missing or stale. Many gaps,
or a messy or duplicated `AGENTS.md` / `CLAUDE.md`? Run `core-be-init` instead of patching.

## Phase 3 — Scope interview (no work yet)

Do not read deeply, run scanners, or edit source until scope is agreed. A
quick look at the repo tree to ask sensible questions is fine.

Ask about every item below that the user has not already answered. A
`change` task inherits the answers from the spec's original task and asks only
about the change itself. Group the
questions into one message; offer concrete options and a recommended default so
the user can answer fast.

1. **Target** — whole repo, specific directories, specific files, a diff/branch,
   or specific endpoints?
2. **Depth** — `quick` (automated tools + top risks), `standard` (tools + manual
   review of every in-scope file), or `deep` (standard + data-flow tracing across
   modules, every trust boundary)?
3. **Out of scope** — tests? generated code? vendored code? infra/Docker? frontend?
4. **Constraints** — public API must not change? no new dependencies? no DB
   migrations? time box?
5. **Success criteria** — what does "done" look like? (e.g. "no High+ findings",
   "complexity ≤10 everywhere", "endpoint returns X with tests")
6. **Output** — report format: **HTML (default)** or **Markdown**? Severity
   cut-off for the report (all findings, or Medium and above)?
7. **Type-specific** —
   - refactor: may files move / be renamed? is behaviour allowed to change? (default no)
   - security: which ASVS level (L1 / **L2 default** / L3)? does the service call an LLM?
   - feature / change: the acceptance criteria live in the spec
     (`core-be-specify`), so do not ask for them here. Ask only what the spec
     cannot hold: API shape preferences, auth rules, who can see what. Ask
     scope only here; the spec does not exist yet.
   - audit: fix nothing (default) or propose patches in the report?
   - explain: ask only the six questions in `core-be-explain`; skip items 4 and 5.
   - init: ask only the questions in `core-be-init`; skip items 1–6.
   - debug: the bug report is most of the scope — ask only for missing
     symptom, expected behaviour, where/when, and hotfix vs proper fix
     (`core-be-debug`).

If an answer is vague ("just check everything", "make it good"), say what you
would assume and ask the user to confirm. Never silently assume scope — the most
expensive agent failure is doing a large amount of excellent work on the wrong
thing.

Record the questions in `scope.md` before you send them, then end your turn and
wait. When answers arrive, write them into `scope.md` (INDEX status stays
`scoping` until every row of "Agreed scope" is filled or explicitly defaulted).
If the user answers "use your defaults", record each default as the answer.

## Phases 4–7

Scope is agreed (`scope.md` filled). Read `references/PHASES-4-7.md` now: it
holds research, plan-then-stop, execute, and report. Do not start Phase 4 from
memory. In short:

4. **Research** — read, measure the baseline, write `research/<slug>.md`.
5. **Plan, then stop** — write `tasks.md`, show it, wait for explicit approval.
6. **Execute** — one step at a time, tick `tasks.md`, log `progress.md`.
7. **Report** — docs sync, then the report in `agent-tracking/reports/`.

`feature` and `change`: the chain in the Quick path above runs inside Phases 4–6.
`explain` and `init` skip Phases 4–7; `core-be-explain` or `core-be-init` runs instead.

## Resuming work

When the user returns to a task, read `INDEX.md`, then the task's `scope.md`,
`tasks.md`, and `progress.md` before doing anything. Continue from the first
unticked step. If the code has moved on since the plan was written, say so and
re-confirm the plan.

## Status values

`scoping` → `researching` → `awaiting-approval` → `approved` → `in-progress` →
`done` (or `blocked`, `cancelled` with a one-line reason). Set each when its
phase starts: `scoping` Phase 2, `researching` Phase 4, `awaiting-approval` when
the plan is shown, `approved` on the user's explicit OK, `in-progress` Phase 6,
`done` after the report.
