---
name: core-be-audit-code
description: >
  Code-quality audit of Python and Node.js / TypeScript backend code: bugs, bad
  code, code smells, structure violations, weak tests, and the failure patterns
  of AI-generated code (hallucinated APIs and packages, happy-path-only logic,
  over-engineering, inconsistent style, outdated practices, test theater,
  comments that lie). Use whenever the user asks to review, audit, or assess
  code — "check for bad code", "is this code ok", "review this PR / module",
  "code quality report", "review what Copilot/Claude/Cursor wrote", "find bugs"
  — starting with core-be-workflow scoping (phases 1–3). Produces a traceable findings report
  that names each smell and the refactoring that fixes it; fixes nothing unless
  remediation is in scope. For vulnerabilities use core-be-audit-security (they can run
  together).
---

# Audit Code

An audit answers: *what is wrong with this code, how much does it matter, and
what exactly should be done about it?* Every finding is specific (`file:line`),
named (a bug class or a Fowler smell), justified (why it hurts here), and
actionable (the named refactoring or fix). Vague feedback ("could be cleaner")
is not a finding.

<gate>
**Gate — before anything else:** load `core-be-workflow`. If
`agent-tracking/plans/<slug>/scope.md` for this task is missing, or its
"Agreed scope" rows are not all filled, run `core-be-workflow` phases 1–3 now and
end your turn at the scope questions. Invoking this skill directly (a slash
command, a one-line request) is not an exemption, and harness plan mode does
not replace `tasks.md`. This skill
supplies phases 4–7. **Default is report-only.** Fixing is a separate planned
task (`core-be-refactor-code` for structure, `core-be-build-feature`/a fix task for behaviour).
</gate>

**Always, even inside another task:** make sure the repo is registered — the
core-be block in `AGENTS.md` and the `@AGENTS.md` import in `CLAUDE.md`
(`core-be-workflow`, Phase 2, "Register the pack") — and, when code or config
changed, finish with the docs sync (`core-be-workflow`, Phase 7) so the README
matches the code.

Yardsticks:

| Need | Read |
|------|------|
| The quality bar, finding severity, review dimensions | `core-be-coding-standards/SKILL.md` |
| Smell names → refactoring names | `core-be-coding-standards/references/smells-and-refactorings.md` |
| Language idioms | `core-be-coding-standards/references/python-style.md`, `typescript-style.md` |
| The repo's structure rules | `AGENTS.md` → `## Project structure` (or `core-be-structure-service`) |
| AI-generated code failure patterns | `references/ai-generated-code.md` |

---

## Phase 4 — Automated pass

Run what the repo has, or the tools in `core-be-coding-standards/references/tooling.md`
ephemerally (ask before installing permanently):

- formatter check, linter (incl. complexity: Ruff `C901` / ESLint `complexity`)
- type checker (`mypy`/`pyright` / `tsc --noEmit`)
- test suite with coverage
- dependency audit (`pip-audit` / `npm audit`) — flag, and hand security depth to `core-be-audit-security`

Record counts and the worst offenders in `research/<slug>.md`. Tool output is a
starting point, not the audit.

## Phase 5 — Review plan

In `tasks.md`: files in review order (entry points and most-changed files first —
`git log --since=6.months --name-only --pretty=format: | sort | uniq -c | sort -rn | head`),
checklists to apply, whether the code is (partly) AI-generated. Get approval.

## Phase 6 — Manual review

**Fan out at `standard` / `deep` depth.** With more than a handful of files,
split them into groups (by module or trust boundary) and give each group to a
read-only `investigator` subagent with the checklist below
(`core-be-workflow/references/SUBAGENTS.md`). You own the report: open
every returned `file:line` and confirm the finding before it goes in.
Subagent and Explore excerpts are leads, not a review: read every in-scope
file yourself. Depth comes from `scope.md`; if it was never agreed, ask.

For each in-scope file, walk these in order — earlier ones matter more:

1. **Bugs** — wrong logic, unhandled `None`/`undefined`, off-by-one, wrong
   error handling (swallowed exceptions, fail-open), race conditions on
   read-modify-write, resource leaks, blocking calls in async code, missing
   timeouts, wrong status codes, calls to APIs that do not exist.
2. **Structure** — layer leaks (SQL/HTTP in handlers, framework imports in
   business logic), code in the wrong place per the recorded structure,
   config read outside the settings module, per-route error bodies.
3. **Design** — shallow modules and pass-throughs (deletion test), speculative
   generality, god functions/classes, duplicated logic across modules.
4. **Readability** — names, function size and complexity, nesting, comments
   that lie or restate code, dead and commented-out code.
5. **Tests** — missing tests for risky paths, test theater, mocks of the unit
   under test, no failure-path tests.
6. **AI-generated code** — the eight checks in `references/ai-generated-code.md`.
   Apply them to all code: humans make the same mistakes, AI makes them more
   confidently.
7. **Security smell spotted?** Record it briefly and recommend `core-be-audit-security`
   if it is not already in scope.

Verify suspected bugs instead of guessing: read the called library's source or
docs for the installed version, run the code path in a test or REPL where
cheap. Mark anything you could not verify as **suspected**.

Log progress per file in `progress.md`.

## Finding format

```
Q-007 | High | Bug: fail-open error handling | src/billing/invoice.py:88-94
  `except Exception: pass` around the fraud alert call; a timeout silently skips
  the alert for invoices over 10,000.
  Why it matters: large invoices go unreviewed with no log entry.
  Fix: catch `httpx.HTTPError`, log at WARNING with the invoice id, and decide
  with the owner whether a failed alert should block creation.

Q-012 | Medium | Long Function + Repeated Switches | src/billing/invoice.py:120-214
  `build_invoice` is 94 lines, complexity 23, three `if kind == ...` ladders.
  Fix: Extract Function per step (Split Phase: parse → price → persist), then a
  dispatch dict for kinds; Replace Conditional with Polymorphism only if kinds grow.
```

Severity (quality): **High** causes or hides bugs, or breaks a structure rule
that blocks change · **Medium** makes change slow or risky · **Low** local
readability · **Info** observation. Bugs that are exploitable belong in
`core-be-audit-security` with security severity.

## Phase 7 — Report

Write the report to `agent-tracking/reports/<slug>.html` (or `.md`). Never the
repo root, the temp directory, or a hosted page (claude.ai Artifact, gist, docs
connector): audit findings stay local. If the user asks for another location,
state this rule first, then follow their answer.

`core-be-workflow` report template in the agreed format (HTML default). Visuals per
`core-be-workflow/references/VISUAL-REPORT.md`: severity tiles and severity bar, one
card per finding, structure conformance as a tree with violating paths red.
**No Mermaid or any external script** — delete the template's script block;
use the template's plain boxes and tables. Include:

- summary with counts by severity and the top 3 things to fix first
- findings table + details (format above), grouped by file or by theme
- automated results before any change (lint, types, complexity, coverage)
- structure conformance: what matches the recorded structure, what does not
- recommended follow-up tasks, each scoped (e.g. "core-be-refactor-code: split
  `src/billing/invoice.py` into service + repository")
- what was not reviewed

Explain findings so a developer new to the code understands them: what, why it
matters here, and exactly how to fix it.
