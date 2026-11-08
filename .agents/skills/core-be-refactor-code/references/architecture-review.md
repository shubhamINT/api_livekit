# Architecture Review Mode

Adapted from the `improve-codebase-architecture` guidance. Surfaces
**deepening opportunities** — refactors that turn shallow modules into deep ones
— so the service becomes easier to test and to navigate. Output is a candidate
report; nothing is changed. Each candidate the user picks becomes its own
`core-be-refactor-code` task with its own scope and plan.

Vocabulary is mandatory: read `core-be-coding-standards/references/module-design.md` first and use its terms
exactly — **module, interface, implementation, depth, deep, shallow, seam,
adapter, leverage, locality**. Do not drift into "component", "service" (for a
module), "API" (for an interface), or "boundary" (for a seam).

If the repo has a domain glossary (`CONTEXT.md`) or ADRs (`docs/adr/`), read
them first: domain terms name good modules, and ADRs record decisions not to
re-litigate.

## 1. Decide where to look (inside the agreed scope)

Deepening pays off where code keeps changing. Unless the user named a target:

- `git log --since=6.months --name-only --pretty=format: | sort | uniq -c | sort -rn | head -30`
  to find hot spots; weight attention there first.
- Scattered history with no hot spot: widen to the whole in-scope tree.

Record the hot-spot list in `research/<slug>.md`.

## 2. Explore and note friction

Walk the code organically; note where understanding hurts:

- One concept requires bouncing between many small modules.
- A module is **shallow**: its interface is nearly as complex as its implementation.
- Pure functions were extracted for testability, but bugs hide in how they are called (no **locality**).
- Tightly coupled modules leak across their seams.
- Code is untested, or hard to test through its current interface.
- Layer rules from `core-be-structure-service` are broken.

Apply the **deletion test** to every suspect: delete it in your head — does
complexity vanish (pass-through, remove it) or reappear in N callers (it earns
its keep)?

Classify each candidate's dependencies (in-process, local-substitutable,
remote-but-owned, true external) per `core-be-coding-standards/references/DEEPENING.md`; the
category decides how the deepened module gets tested.

## 3. Write the report

Format as chosen in scope (HTML default). Save to
`agent-tracking/reports/<slug>.html|md`. HTML follows `HTML-REPORT.md` in this
directory, built on the shared template and patterns in
`core-be-workflow/references/VISUAL-REPORT.md`.

<output>
Per candidate:

- **Files** involved
- **Problem**: why the current shape causes friction (one sentence)
- **Solution**: what would change, plain English (one sentence)
- **Wins**: in terms of locality, leverage, and tests
- **Before / after diagram**
- **Dependency category**
- **Recommendation strength**: `Strong`, `Worth exploring`, or `Speculative`
- **ADR conflict** callout, only if the friction justifies reopening the ADR

End with a **Top recommendation**: which candidate first and why.
</output>

Do not propose detailed interfaces yet. Ask the user which candidate to pursue.

## 4. After the user picks

- Start a new `core-be-workflow` task (`core-be-refactor-code` type) for that candidate.
- To explore interface alternatives, use `core-be-coding-standards/references/DESIGN-IT-TWICE.md`
  (several radically different designs compared on depth, locality, seam
  placement), and record the chosen design in the plan.
- User rejects a candidate for a lasting reason? Offer to record an ADR so
  future reviews do not re-suggest it.
