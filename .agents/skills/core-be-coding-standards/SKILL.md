---
name: core-be-coding-standards
description: >
  ALWAYS-ON coding standard for Python and Node.js/TypeScript
  backends — applies to every change an agent makes or reviews, however small.
  Clean Code, SOLID, YAGNI, Google Python / TypeScript style guides, Fowler's
  smells and named refactorings, deep-module design (modules, interfaces, seams,
  adapters), Google code-review dimensions, the bug-and-smell radar, the
  self-review for AI-generated code, and the tools that enforce it all (Ruff,
  mypy, ESLint 9, typescript-eslint, Prettier). Use whenever writing, changing,
  reviewing, or judging backend code, designing a module interface, or choosing
  lint/format config; it is the yardstick for core-be-build-feature, core-be-refactor-code and
  core-be-audit-code.
---

# Coding Standards

Code is read far more than it is written. The standard below is what a reviewer
checks and what a refactor aims at. Where a rule has a tool that enforces it,
the tool wins — humans and agents do not argue about spacing.

> Code is clean if it can be read and enhanced by a developer other than its
> original author. — Grady Booch

Language details live in references; read the one for your stack. The style
files index **every** section of the Google style guides with a status —
`tool` (a linter/formatter enforces it), `rule` (follow it by hand), `override`
(this standard deliberately differs, with the reason), `n/a` — so no Google rule is
dropped. Where a style file and the Google text disagree, the style file wins.

| Need | Read |
|------|------|
| Python idioms + index of every Google Python guide section | `references/python-style.md` |
| TypeScript / Node idioms + index of every Google TS guide section | `references/typescript-style.md` |
| Plain JavaScript files + index of every Google JS guide section | `references/javascript-style.md` |
| Full Google style guides (offline copies, read a section when the index points you there) | `references/google/pyguide.md`, `tsguide.md`, `jsguide.md` |
| Naming a smell and the refactoring that fixes it | `references/smells-and-refactorings.md` |
| Linter / formatter / type-checker / pre-commit config | `references/tooling.md` |
| Designing a module interface: depth, seams, adapters, the deletion test | `references/module-design.md` |
| Deepening shallow modules given their dependencies | `references/DEEPENING.md` |
| Comparing alternative interface designs | `references/DESIGN-IT-TWICE.md` |
| AI-generated code failure patterns (full detail) | `core-be-audit-code/references/ai-generated-code.md` |

## 0. Bug and smell radar (always on)

Whenever you read code — for a feature, a refactor, an audit, or a one-line fix —
watch for bugs, security holes, and bad code, including in lines you were not
asked to touch. For each one you notice:

1. **Tell the user**, in plain terms: what it is (`file:line`), why it matters
   here, and how to fix it — name the refactoring or fix so they can learn it.
2. **Record it** in the current task's `progress.md` under "Out-of-scope
   observations" (for trivial tasks with no tracking, in your reply only).
3. **Do not silently fix it** if it is outside the agreed scope. Offer it as a
   follow-up task (`core-be-audit-code`, `core-be-audit-security`, `core-be-refactor-code`), because an
   unreviewed fix is an unreviewed behaviour change.

Security holes (injection, missing authorization, hardcoded secrets, unsafe
deserialization) are always reported immediately, even in a trivial task.

---

## Working rules (every change, trivial included)

<hard-rules>
- Read code before you change it. Never edit what you have not read.
- Do not reformat code you did not otherwise change. Keep diffs reviewable.
- No commit, branch, push, or lockfile deletion unless the user asks.
</hard-rules>

## 1. Names

- Reveal intent: `elapsed_days`, not `d`; `fetch_open_invoices()`, not `get_data()`.
- No disinformation: `account_list` must be a list. No near-duplicates (`ProductData` vs `ProductInfo`).
- Searchable and pronounceable. No abbreviations the team did not agree on.
- Classes and types are nouns (`Invoice`, `RetryPolicy`). Functions are verbs (`send_invoice`).
- Booleans read as predicates: `is_active`, `has_access`, `should_retry`.
- Banned as names: `data`, `info`, `tmp`, `obj`, `stuff`, `manager`, `helper`, `utils` modules.

## 2. Functions

- **One job.** If describing it needs "and", split it.
- **One level of abstraction.** Business steps do not sit next to regex or byte fiddling.
- **Small.** Aim for under ~40 lines. Cyclomatic complexity ≤ 10 (enforced by Ruff `C901` / ESLint `complexity`).
- **Few arguments.** 0–2 ideal, 3 acceptable, 4+ means a parameter object (`Introduce Parameter Object`).
- **No flag arguments.** `send(invoice, True)` becomes two functions (`Remove Flag Argument`).
- **No hidden side effects.** A function named `check_x` does not write. Separate queries from commands.
- **Guard clauses over nesting.** Return early; max nesting depth ~3.

## 3. Errors

- Raise / throw exceptions, not error codes or sentinel values.
- Catch the narrowest type you can handle. Never swallow: no bare `except:`, no empty `catch {}`.
- Add context when re-raising (`raise X(...) from err`, `new Error(msg, { cause: err })`).
- Do not return `None` / `null` to signal failure when the caller will forget to check; raise or return a typed result.
- Every exceptional path must leave state consistent (close files, roll back transactions, release locks).
- Error messages sent to clients never contain stack traces, SQL, internal paths, or secrets.

## 4. Comments and docs

- Explain **why**, not what. If a comment explains what, rename or extract until it does not need to.
- A comment that disagrees with the code is a bug. Fix one of them in the same change.
- Public modules, classes, and functions get a docstring / JSDoc stating purpose, arguments, return, raised errors.
- No commented-out code. No noise (`# increment i`). No position markers or banner comments.
- `TODO` carries a ticket link and a reason (Google format): `# TODO: PROJ-123 - reason`.

## 5. Structure (SOLID, applied to backend services)

| Principle | One line | What it means here |
|-----------|----------|--------------------|
| **S**ingle responsibility | One reason to change | Route layer does HTTP, domain does rules, services do I/O |
| **O**pen/closed | Extend without editing | Add a new handler/strategy instead of another `elif` branch — only once a second case really exists |
| **L**iskov substitution | Subtypes honour the base contract | A fake adapter behaves like the real one, including errors |
| **I**nterface segregation | Callers depend only on what they use | Small protocols / TS interfaces; no god-client passed everywhere |
| **D**ependency inversion | Depend on abstractions | Inject clients / repos into domain code; do not construct them inside |

SOLID is a tool, not a goal. **YAGNI beats OCP**: do not add an interface with
one implementation or a factory for one product. The deletion test (see
`core-be-coding-standards/references/module-design.md`) decides whether an abstraction earns its keep.

## 6. Data and state

- No mutable module-level state except true singletons (config, logger, connection pool).
- Prefer immutable data (frozen dataclasses / pydantic models, `readonly` / `as const`).
- Validate at the boundary; inside the core, trust typed data.
- Law of Demeter: avoid `a.b().c().d()` chains into other objects' internals (`Hide Delegate`).

## 7. Tests

Tests are part of the code quality bar, not an extra. See `core-be-write-tests`. Headlines: test behaviour through the interface; one behaviour
per test; names state the invariant; offline; F.I.R.S.T. (fast, independent,
repeatable, self-validating, timely); coverage floor 80%.

## 8. Formatting and consistency

- The formatter decides layout (Ruff format / Prettier). Do not hand-format.
- Follow the file's existing conventions when they do not break a rule here.
- Newspaper order: public, high-level functions first; helpers below.
- Declare variables near their use. Related lines together; unrelated ones separated.

---

## Reviewing code — the dimensions

Apply these in order (from Google's engineering practices). Earlier ones matter
more; do not bury a design problem under ten naming nits.

1. **Design** — does the change belong here? right layer, right module, right seam?
2. **Functionality** — does it do what was asked, including edge cases and concurrency?
3. **Complexity** — could it be simpler? any speculative generality?
4. **Tests** — correct, meaningful, would they fail if the code broke?
5. **Naming** — clear and consistent?
6. **Comments** — explain why; none lie?
7. **Style** — tool-clean? consistent with the file?
8. **Documentation** — README, env tables, API docs updated?
9. **Security** — trust boundaries touched? then run the `core-be-audit-security` quick checklist.

Cite smells and fixes **by name** (see `references/smells-and-refactorings.md`);
the full audit finding format is in `core-be-audit-code`. Severity for quality findings:

| Severity | Meaning |
|----------|---------|
| High | Causes or hides bugs, blocks change, or breaks a layer rule (e.g. SQL in a route) |
| Medium | Makes change slow or risky (long function, duplication across modules, missing tests) |
| Low | Local readability (naming, comment noise, small duplication) |
| Info | Observation, no action required |

## Checklist before handing back code

- [ ] Tool-clean: formatter, linter, type checker all pass with no new ignores
- [ ] Every function does one thing; complexity ≤ 10
- [ ] Names reveal intent; no banned names
- [ ] Errors explicit, narrow, and contextual; nothing swallowed
- [ ] No dead code, no commented-out code, no unused imports or parameters
- [ ] No abstraction without a second real use
- [ ] Tests added / updated and meaningful
- [ ] Comments explain why and match the code
- [ ] Could anything be deleted without losing behaviour? Delete it.

## Self-review for AI-generated code (your own output included)

Before handing back any code you wrote, run these eight checks — details and
verification steps in `core-be-audit-code/references/ai-generated-code.md`:

- [ ] **No hallucinated APIs** — I opened the installed source or versioned docs for every library call I had not already seen in this repo.
- [ ] **No invented packages** — every new dependency exists under that exact name, is the intended project, licence-compatible, and in the lockfile.
- [ ] **Edge cases handled** — empty / `None` / `undefined`, errors, timeouts, concurrency — or documented why not.
- [ ] **No over-engineering** — nothing I added fails the deletion test.
- [ ] **Consistent style** — I used the repo's existing patterns, not new ones.
- [ ] **No copied code of unknown licence.**
- [ ] **No outdated practices** — APIs match the installed versions.
- [ ] **Tests would fail if the behaviour broke** — no test theater.
- [ ] **Comments are true** of the code as it stands.
