<!-- core-be:start -->
# AGENTS.md — Backend Engineering Rules

<!-- Managed by the core-backend skill pack (core-be-workflow, "Register the
pack"). Agents refresh the text between the core-be markers; edit the pack, not
this block. Repo-specific notes go outside the markers. -->

These rules apply to every agent working in this repository. They cover backend
services written in **Python** (FastAPI, async, uv) and **Node.js** (TypeScript,
Express / Fastify). Skills are installed as a Claude Code plugin, with
`npx skills`, or by copying `.agents/skills/`, so find each one by name. Read
the ones named here before you act.

> Talk first, plan first, then build. Simple, clean, verified code beats clever
> code. Tools enforce style; you enforce correctness, security, and scope.

## Load the skills before you act

This repo uses the `core-be-*` skills. Before any code change, load
`core-be-coding-standards`. For any non-trivial task, load `core-be-workflow`
first; it routes to the other skills. Find them by name (Claude Code plugin
skills appear as `core-backend:core-be-<skill>`).

Skills not installed? Tell the user and suggest one of:

```
/plugin marketplace add shubhamINT/agent_rules
/plugin install core-backend@int-agent-rules
```

```bash
npx skills add shubhamINT/agent_rules      # pick every core-be-* skill
```

Until they are installed, follow the rules in this file.

---

## 1. Always on — every task, however small

These apply to everything, including trivial edits and questions.

| Always-on skill | What it guarantees |
|-----------------|--------------------|
| `core-be-coding-standards` | Clean code, style, module design, the self-review for AI-generated code, and the **bug and smell radar** |
| `core-be-workflow` | Non-trivial work is recorded, scoped with the user, planned, and approved before any code changes |

Always-on behaviour:

1. **Converse before acting.** Understand what the user wants. If the request is
   ambiguous, ask — offer concrete options with a recommended default. Never
   guess scope.
2. **Plan before code** for anything non-trivial (§2). No source edits before
   the user approves the plan.
3. **Bug and smell radar.** While reading code for any reason, watch for bugs,
   security holes, and bad code. Explain each one to the user in plain terms —
   what, where (`file:line`), why it matters, how to fix it (name the fix or
   refactoring). Record it. Do not silently fix anything outside the agreed
   scope; offer a follow-up task. Report security holes immediately.
4. **Structure first.** Before placing or moving code, read the
   the Project structure section at the end of this file. If it is empty, run
   `core-be-structure-service`: detect the current structure, confirm it with the user,
   and record it there.
5. **Help the user understand.** Explain decisions and findings so a developer
   new to the code could follow and apply them. Prefer showing the fix over
   describing it.
6. **Spend tokens on evidence, not words.** Search before reading, read a
   file once, run one test file while iterating, filter logs before reading.
   Chat replies short; files in normal prose. Never skip a check to save
   tokens (`core-be-workflow/references/TOKEN-ECONOMY.md`).

## 2. Classify the task

| Task type | Examples | Skills |
|-----------|----------|--------|
| **Trivial** | answer a question, fix a typo, rename one variable, explain code | Just do it (always-on rules still apply, radar included). No tracking. |
| **Feature** | "add an endpoint", "support X", "integrate Y" | `core-be-workflow` → [`core-be-constitution` once] → `core-be-specify` → `core-be-clarify` → `core-be-plan` → `core-be-tasks` → `core-be-analyze` → approval → `core-be-implement` → `core-be-converge` |
| **Change** | "limit it to 10k rows", "change how X works", "drop support for Y" | `core-be-workflow` → `core-be-change` (edit the spec first) → `core-be-clarify` → `core-be-plan` (delta) → `core-be-tasks` → `core-be-analyze` → approval → `core-be-implement` → `core-be-converge` |
| **Assess** | "should we build X", "is this worth it", a vague idea | `core-be-workflow` → `core-be-assess` → `go` / `needs-clarification` / `kill` |
| **Explain** | "how does X work", "walk me through this flow", "I am new to this code" | `core-be-workflow` → `core-be-explain` |
| **Init** | "set up this repo", "onboard this project", "start a new project", messy `AGENTS.md` / `CLAUDE.md` | `core-be-workflow` → `core-be-init` → first feature through `core-be-specify` |
| **Constitution** | "set up SDD", "project principles" | `core-be-workflow` → `core-be-constitution` |
| **Refactor** | "clean this up", "this code is a mess", "restructure", "reduce duplication" | `core-be-workflow` → `core-be-refactor-code` |
| **Code audit** | "review this code", "check for bad code", "find bugs", "review what the AI wrote" | `core-be-workflow` → `core-be-audit-code` |
| **Security audit** | "security audit", "find vulnerabilities", "is this safe", "OWASP check" | `core-be-workflow` → `core-be-audit-security` |
| **Tests** | "add tests", "raise coverage", "fix the failing suite" | `core-be-workflow` → `core-be-write-tests` |
| **Debug** | "this returns 500", "flaky test", "worked yesterday", "users see wrong data", "it's slow", a pasted stack trace | `core-be-workflow` → `core-be-debug` |
| **Structure** | "structure this repo", "where should this go", "which architecture" | `core-be-workflow` → `core-be-structure-service` |
| **Health endpoint** | "add a health check", "readiness probe" | `core-be-workflow` → `core-be-add-health-endpoint` |

Unsure whether a task is trivial? Treat it as non-trivial. A change that touches
more than one file, any trust boundary (auth, input parsing, external calls,
secrets), or any public interface is never trivial.

### Specs (spec-driven development)

`feature` and `change` tasks are spec-driven. Files, all committed with the code:

- `specs/constitution.md` — project principles, each with a yes/no gate question
  (`core-be-constitution`).
- `specs/<NNN-topic>/spec.md` — what and why, numbered acceptance criteria
  (`core-be-specify`, edited first by `core-be-change`).
- `specs/<NNN-topic>/plan.md` — the durable design (`core-be-plan`).

Order: spec, then plan, then tasks, then analysis, then user approval, then
code, then converge. Edit the spec first, never the code first. Done means
`core-be-converge` returned `Converged`. Refactors, audits, security reviews,
debugging, and test work change no behaviour and need no spec.

### Guard

An edit guard (a command hook that Claude Code, Codex, Cursor, Copilot, Gemini CLI, and
Windsurf can run: `core-be-workflow/scripts/sdd-hook.sh`) and a validator
(`core-be-workflow/scripts/sdd-check.sh`) back these rules. A source edit needs an approved
task row in `agent-tracking/INDEX.md`; a `feature` or `change` task also needs its
spec first. You may not stop mid-implementation before `Verdict: Converged` is in
`progress.md`. When the guard says no, do what its message says. Never edit the
hook, its config, or the scripts, and never set `SDD_GUARD`. CI runs
`sdd-check.sh ci` on the committed files, so a skipped step fails the build.

## 3. The non-trivial workflow (mandatory)

Follow the `core-be-workflow` skill. In short:

1. **Record first.** Create `agent-tracking/` if missing and write the user's
   request verbatim to `agent-tracking/plans/<slug>/scope.md`, plus a row in
   `agent-tracking/INDEX.md`. Everything after — questions, answers, research,
   plan, progress, report — lands in the same folder.
2. **Scope with the user.** Ask until it is unambiguous: which paths, how deep,
   what is out of scope, constraints, success criteria, and the report format
   (**HTML by default, or Markdown**). Log questions and answers in `scope.md`.
   Reports are visual: a Current → Target diagram for every change
   (`core-be-workflow/references/VISUAL-REPORT.md`). Audit and security reports load no
   external scripts.
3. **Research**, then **plan**: write `tasks.md`, show it, and wait for explicit
   approval.
4. **Execute the approved plan only.** Log each step in `progress.md`. New scope
   found mid-task: stop, record it, ask.
5. **Report** into `agent-tracking/reports/` and update `INDEX.md`.

**Think like the senior engineer on call for it.** Features get a system design
pass (`core-be-build-feature/references/system-design.md`): concurrency,
idempotency, failure modes, limits, compatibility — sized to the real risk.
Every code change ships in small reversible steps with a concrete rollback
(`core-be-workflow/references/SAFE-DELIVERY.md`).

**Use subagents where they add independence or parallelism**
(`core-be-workflow/references/SUBAGENTS.md`): read-only `investigator`s for
audit fan-out and debugging hypotheses, a `test-writer` that writes tests from
the contract, and a fresh-context `reviewer` before every report (a separate
pass when the host has no subagents; a self-pass is enough for a diff under
about 50 lines). Brief a
general-purpose subagent with the role text from `SUBAGENTS.md`. Verify what
they return.

`agent-tracking/` belongs in version control, but the user commits it — see rule 12.

## 4. Coding rules

1. **Read before you change.** Never edit code you have not read. Follow the
   repo's existing patterns and recorded structure.
2. **Simplest thing that works.** No speculative abstractions, config options, or
   layers "for later". Delete dead code; never leave commented-out blocks.
3. **Never invent an API.** Every import, package, function, method, flag, and
   config key must exist in the installed version. Verify in the lockfile and
   the package source or official docs. Never add a dependency you have not
   confirmed exists under that exact name.
4. **Handle errors explicitly.** No bare `except:` / empty `catch {}`. Fail
   closed at trust boundaries; degrade gracefully only where the contract says so.
5. **Validate all external input** (bodies, headers, query params, files, env,
   upstream responses) with a schema: pydantic (Python) or zod (Node).
6. **No secrets in code, logs, errors, or tests.** One settings module reads the
   environment; `.env.example` lists every variable with safe placeholders.
7. **Every outbound call has a timeout. Every query is parameterised. Every
   resource-scoped read checks ownership.**
8. **Tests ship with the change** and pass offline. Coverage floor 80%; never
   lower it, never loosen an assertion to go green.
9. **Docs stay true.** README endpoint, env, and structure sections change in
   the same change as the code.
10. **Do not reformat code you did not otherwise change.** Keep diffs reviewable.
11. **No git side effects unless asked.** Do not commit, branch, push, or delete
    lockfiles. Leave changes in the working tree for the user to review.
12. **Parallel agents share one board.** When other agents work here too, join
    `agent-tracking/board/` with `core-be-workflow/scripts/board.sh`: claim a
    task and lock its files before editing, never wait by re-reading code, and
    `leave` when done. The last agent out removes the board
    (`core-be-workflow/references/PARALLEL-AGENTS.md`).

## 5. Language baselines

| | Python | Node.js |
|--|--------|---------|
| Runtime | Python 3.12+, `uv` | Node 24 LTS, TypeScript `strict` |
| Style guide | Google Python Style Guide | Google TypeScript Style Guide |
| Format + lint | Ruff (`ruff format`, `ruff check`) | Prettier + ESLint 9 flat config + typescript-eslint |
| Types | mypy or pyright, strict on new code | `tsc --noEmit`, no `any` |
| Security lint | Ruff `S` rules, Semgrep | eslint-plugin-security, Semgrep |
| Dependencies | `pip-audit` | `npm audit` / `pnpm audit` |
| Secrets | gitleaks | gitleaks |
| Complexity | Ruff `C901`, max 10 | ESLint `complexity`, max 10 |
| Tests | pytest (`core-be-write-tests`) | vitest (`core-be-write-tests`) |

Every section of the Google Python, TypeScript and JavaScript style guides is
indexed (enforced by tool / rule / override) in
`references/{python,typescript,javascript}-style.md` of the
`core-be-coding-standards` skill; the full guides are bundled in its
`references/google/`.

## 6. Skill index

| Skill | Kind | Use when |
|-------|------|----------|
| `core-be-coding-standards` | always on | Writing, changing, or judging any code |
| `core-be-workflow` | always on | Any non-trivial task: record, scope, plan, approve, report |
| `core-be-constitution` | task | Creating or amending `specs/constitution.md` |
| `core-be-assess` | task | Deciding go / needs-clarification / kill for an idea before any spec |
| `core-be-explain` | task | Explaining how existing code works: read-only trace, HTML page |
| `core-be-init` | task | Setting up or repairing a repo for the pack; fixing `AGENTS.md` and `CLAUDE.md`; the project brief |
| `core-be-specify` | task | Writing the spec for a new feature |
| `core-be-change` | task | Changing an existing feature: spec first |
| `core-be-clarify` | task | Resolving open questions in a spec |
| `core-be-plan` | task | Writing the durable design plan for a spec |
| `core-be-tasks` | task | Turning spec and plan into the test-first checklist |
| `core-be-analyze` | task | Read-only consistency check before approval |
| `core-be-implement` | task | Building from the approved checklist |
| `core-be-converge` | task | Checking code against the spec; verdict `Converged` |
| `core-be-build-feature` | task | Building new behaviour |
| `core-be-refactor-code` | task | Changing structure without changing behaviour; architecture review |
| `core-be-audit-code` | task | Finding bugs, bad code, weak tests, AI-generated-code failures |
| `core-be-audit-security` | task | Finding vulnerabilities (OWASP, ASVS, CWE) |
| `core-be-write-tests` | task | Writing or fixing tests; coverage |
| `core-be-debug` | task | Reproducing, root-causing, and fixing bugs, flaky tests, slowness |
| `core-be-structure-service` | task | Detecting, choosing, recording, applying the project structure |
| `core-be-add-health-endpoint` | task | Adding or fixing `GET /health` |
<!-- core-be:end -->

## Project structure

<!-- Repo-owned. Filled in per repository by the `core-be-structure-service` skill, after the user
confirms the structure: pattern, layout tree, dependency rules, "where does X
go" table, terms, migration approach. Empty = run `core-be-structure-service` before
placing or moving code. -->
