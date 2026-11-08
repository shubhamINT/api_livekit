---
name: core-be-assess
description: >
  Decide whether an idea is worth building before any spec: intake, research,
  define, shape, and a documented verdict of `go`, `needs-clarification`, or
  `kill`. Use when the user has a vague idea, asks "should we build X", "is this
  worth it", "does something like this already exist", or wants options before
  committing. Writes no code and no spec; `go` hands over to `core-be-specify`.
---

# Assess

A killed idea with a written reason is a good outcome: it saved a build. This
skill produces the evidence for the decision, not the feature.

<gate>
`core-be-workflow` is loaded (do not re-read it); scope the question with the user first.
</gate>

Write one file, `specs/assessments/<slug>.md`, from `templates/assessment.md`.
The `NNN-` scan in `core-be-specify` ignores this folder.

## Stages

1. **Intake**: restate the idea in the user's words and yours. Who has the
   problem, how they cope today, what triggered the idea. Ask what you cannot
   infer.
2. **Research**: what the repo already does (search before assuming), existing
   products or libraries that cover it, prior art, and rough cost. Record
   sources with links. Facts from memory are marked unverified.
3. **Define**: the problem in one sentence, success measures with numbers,
   non-goals.
4. **Shape**: two or three options (including "do nothing" and "buy or reuse")
   with effort, risk, and what each gives up. Recommend one.
5. **Decide**: one of
   - `go`: hand over to `core-be-specify` with the shaped option as input.
   - `needs-clarification`: list exactly what must be answered, by whom.
   - `kill`: the reason, and what evidence would reopen it.

The user makes the decision. State your recommendation and the evidence; do not
decide for them.
