---
name: core-be-clarify
description: >
  Resolve every open question in a spec before planning: find ambiguity and gaps,
  ask the user once with options and a recommended default, write the answers
  into the spec, and run the spec checklist. Use right after `core-be-specify` or
  `core-be-change`, and whenever a spec still holds `[NEEDS CLARIFICATION]` markers,
  vague words ("fast", "secure", "user-friendly"), or missing error cases.
---

# Clarify

Planning on a spec with guesses in it builds the wrong thing well. This skill
closes the gaps first.

<gate>
a spec exists at `specs/<NNN-topic>/spec.md`.
</gate>

## Steps

1. List every `[NEEDS CLARIFICATION]` marker.
2. Read the spec for gaps the author did not mark: vague words with no number,
   an action with no error case, no limit where one is needed, an actor who is
   never named, two criteria that contradict each other, a criterion no test
   could fail.
3. Ask the user **once**, in one message (`core-be-workflow`, Phase 3 rules): group the
   questions, give concrete options and a recommended default for each, and log
   each in the clarification log of `scope.md`. End the turn and wait.
4. Write each answer into the spec as a criterion or a constraint. Delete its
   marker. Add a change-log row with the date.
5. Run `sh core-be-workflow/scripts/sdd-check.sh spec specs/<NNN-topic>`; it must exit 0. Run `templates/spec-checklist.md` from `core-be-specify`. Planning starts only
   when every box is ticked and the user has approved the spec. Then set
   `Status: approved`.
6. Hand over to `core-be-plan`.

Answer "use your defaults"? Record each default as the answer, in the spec and
in `scope.md`.
