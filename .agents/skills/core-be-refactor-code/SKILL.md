---
name: core-be-refactor-code
description: >
  Behaviour-preserving refactoring of Python and Node.js backend code, plus
  architecture review for deepening opportunities. Use whenever the user wants
  to clean up, restructure, simplify, de-duplicate, split, rename, or "fix bad
  code" — "this module is a mess", "refactor the payments service", "reduce
  complexity", "make this testable", "improve the architecture" — after scope
  and plan are agreed through core-be-workflow. Detects the project structure first and
  moves misplaced code into it, baselines tests and metrics, names every smell
  and refactoring (Fowler), changes in small green steps, and reports
  before/after.
---

# Refactor Code

A refactor changes structure and keeps behaviour. That promise is the whole
value: reviewers can approve a large diff because nothing observable changed.
Break it — sneak in a fix, a feature, or an API change — and the diff becomes
unreviewable. Behaviour changes are separate tasks.

<gate>
**Gate — before anything else:** load `core-be-workflow`. If
`agent-tracking/plans/<slug>/scope.md` for this task is missing, or its
"Agreed scope" rows are not all filled, run `core-be-workflow` phases 1–3 now and
end your turn at the scope questions. Invoking this skill directly (a slash command, a one-line
request) is not an exemption, and harness plan mode does not replace
`tasks.md`. This skill supplies the content of phases 4–7.
</gate>

**Always, even inside another task:** make sure the repo is registered — the
core-be block in `AGENTS.md` and the `@AGENTS.md` import in `CLAUDE.md`
(`core-be-workflow`, Phase 2, "Register the pack") — and, when code or config
changed, finish with the docs sync (`core-be-workflow`, Phase 7) so the README
matches the code.

Yardsticks: `core-be-coding-standards` (what good looks like),
`core-be-coding-standards/references/smells-and-refactorings.md`
(names), `core-be-coding-standards/references/module-design.md` (module and seam vocabulary), and the repo's recorded
project structure (`AGENTS.md` → `## Project structure`, set by `core-be-structure-service`).

---

## Modes

| Mode | When | Output |
|------|------|--------|
| **Code refactor** (default) | Specific files/modules are hard to read or change | Changed code + report |
| **Architecture review** | "Improve the architecture", "why is this hard to change", whole-service scope | Candidate report only; each chosen candidate becomes its own refactor task. See `references/architecture-review.md` |

Ask which mode if the request is ambiguous.

## Phase 4 — Baseline (research)

Record in `agent-tracking/research/<slug>.md`:

0. **Structure**: read the repo's recorded structure (`AGENTS.md` →
   `## Project structure`). None recorded? Run `core-be-structure-service` first: detect
   the current structure, ask the user which one they want, record it. Then list
   every file or function that sits in the wrong place for that structure
   (e.g. SQL in a route handler, business rules in a repository) — these become
   relocation steps.
1. **Tests**: run the suite; record pass/fail counts and coverage for the in-scope files.
2. **Lint/type**: `ruff check` + `mypy` / `eslint` + `tsc` counts for in-scope files.
3. **Complexity**: functions over 10 (`ruff check --select C901` / ESLint `complexity`), longest functions, largest files.
4. **Behaviour surface**: public functions, endpoints, CLI commands, events, DB writes the in-scope code exposes. This list is what must not change.
5. **Smell inventory**: each smell with Fowler name, `file:line`, and why it hurts here. Apply `core-be-audit-code/references/ai-generated-code.md` too if the code was AI-generated.

**No tests covering the in-scope behaviour?** The first plan step is to write
**characterization tests**: tests that pin current behaviour (including odd
behaviour) through the public interface. Without them you cannot prove the
refactor preserved anything. If current behaviour looks like a bug, pin it
anyway, record it as an out-of-scope observation, and ask. A `test-writer`
subagent can write them from the public interface while you plan
(`core-be-workflow/references/SUBAGENTS.md`).

## Phase 5 — Plan

<example>
Each plan step names the refactoring and is independently verifiable:

```
- [ ] 3. Extract Function: pull tax calculation out of `build_invoice`
         (src/billing/invoice.py:120-168) into `compute_tax(lines, region)`.
         Verify: uv run pytest tests/billing -q ; complexity of build_invoice 23 → 14.
```
</example>

Order steps so the code is green after every one:

1. characterization tests (if missing)
2. renames and dead-code removal (cheap, low risk, shrink the problem)
3. extractions inside a module
4. relocations into the recorded structure — `Move Function` / move file
   (`git mv` to keep history), one area at a time, every import updated in the
   same step; incremental unless the user approved a full migration
5. interface changes to internal modules (update every caller in the same step)

Priority: fix what blocks the requested change or hides bugs first; cosmetic
last or never. Leave out anything the scope did not ask for.

Plan must state: public behaviour surface unchanged (list it), no dependency
changes unless approved, expected before/after metrics.

## Phase 6 — Execute

- One refactoring at a time. Run the relevant tests after each. Red means undo
  or fix before continuing — never stack changes on a red build.
- Keep commits small, one refactoring each where practical; message says which
  refactoring (`refactor: extract compute_tax from build_invoice`).
- Update every import and caller in the same step. Search for string references
  too (routes, DI registrations, `getattr`, dynamic imports, config).
- Do not reformat untouched code. Do not "improve" code outside scope.
- Delete dead code instead of commenting it out. Delete tests that only tested
  deleted shallow wrappers once the deeper interface is tested (replace, don't
  layer — see `core-be-coding-standards/references/DEEPENING.md`).
- New files: follow the repo's existing licence-header convention if it has one.
- Structure moved? Update README project tree in the same change.
- Before the report, a fresh-context `reviewer` subagent checks the diff for
  behaviour changes and scope creep; a large move follows
  `core-be-workflow/references/SAFE-DELIVERY.md`.

## Phase 7 — Report

<output>
Write the report to `agent-tracking/reports/<slug>.html` (or `.md`). Never the
repo root, the temp directory, or a hosted page (claude.ai Artifact, gist, docs
connector).

Use `core-be-workflow` report template and `core-be-workflow/references/VISUAL-REPORT.md`.
Refactor-specific content:

- **Current → Target diagram**: module or call graph before and after, moved
  and extracted parts amber, removed parts grey, leaks red. Add a layer list,
  interface-vs-implementation table, or call-graph collapse when it makes the gain clearer.
- **Metrics table** (Before · After · Δ) for the numbers below

- **Changes table**: change · named refactoring · files · reason (smell addressed)
- **Metrics before/after**: tests (count, pass), coverage, lint/type errors,
  functions over complexity 10, max function length, files changed, lines +/−
- **Behaviour surface**: confirm unchanged; list characterization tests added
- **Deferred smells**: what was found but left, and why
</output>

## Guardrails

<hard-rules>
- Behaviour change needed to finish the refactor? Stop and ask; it becomes its own task.
- Public API (HTTP routes, response shapes, package exports) is behaviour. Do not change it in a refactor.
- Performance-sensitive path? Record a before/after timing if the refactor could affect it.
- Can't get a test around it (e.g. untestable global side effects)? Say so in the plan, propose the smallest seam that makes it testable, and get approval.
</hard-rules>
