---
name: core-be-constitution
description: >
  Create and amend the project constitution, `specs/constitution.md`: a short
  list of principles every plan must pass, each with a yes/no gate question. Use
  when the user says "set up SDD", "project principles", "constitution", or
  before the first feature spec in a repo that has none, and whenever a
  principle needs to change. Plans and analysis check against it.
---

# Constitution

The constitution is the project's standing rules for how features get built. A
spec says what one feature does. The constitution says what every feature must
respect. It is read by `core-be-plan` (gate) and `core-be-analyze` (check), so each
principle must be answerable yes or no from a plan.

<gate>
`core-be-workflow` is loaded (do not re-read it). Scope the task first.
</gate>

## Location

`specs/constitution.md`, from `templates/constitution.md`. One file per repo.

## Create

1. Read `AGENTS.md`, the README, and `core-be-coding-standards`. The constitution may be stricter
   than those, never looser.
2. Propose principles from the starter list in the template, adjusted to what
   the repo already does. Five to nine; more is noise.
3. Ask the user in one message: keep, drop, or reword each principle, add any
   of their own, with a recommended default. Never write the file from
   assumptions.
4. Each principle has: a one-line **rule**, a **why**, and a **gate question**
   that a plan answers yes or no.
5. Write the file and set `Version: 1.0.0` and the ratified date. The managed
   `AGENTS.md` block already names `specs/constitution.md`; do not edit it.

## Amend

Only with the user's explicit approval, never silently.

1. State the proposed change and the reason.
2. Check impact: `grep` the principle name across `specs/*/plan.md`. List every
   plan the change affects.
3. After approval, edit the file, bump the version (rule changed or removed:
   major; principle added: minor; wording only: patch), and add a row to the
   amendment log.
4. Affected plans are not rewritten here. Tell the user which need a
   `core-be-change` task.

## How gates work

`core-be-plan` answers every gate question. A plan that answers no must record the
violation under **Complexity tracking** with the reason and the simpler
alternative it rejected. `core-be-analyze` treats an unrecorded violation as
Critical. An amendment is the only way to remove a gate.
