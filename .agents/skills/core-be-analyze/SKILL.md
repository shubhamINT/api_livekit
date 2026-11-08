---
name: core-be-analyze
description: >
  Read-only consistency check before any code: compare the constitution, spec,
  design plan, and task checklist, and list gaps, contradictions, and
  unrequested work. Use after `core-be-tasks` and before the user approves the plan.
  Changes nothing; findings go back to the author of the file at fault.
---

# Analyze

Cheaper to find a contradiction in three Markdown files than in a finished
diff. This skill reads and reports; it edits nothing.

**Inputs:** `specs/constitution.md`, `specs/<NNN-topic>/spec.md`,
`specs/<NNN-topic>/plan.md`, `agent-tracking/plans/<slug>/tasks.md`.

## Run the script first

Run `sh core-be-workflow/scripts/sdd-check.sh analyze <slug>` and paste its output under **Analysis** in
`progress.md`. It checks coverage, unrequested work, open markers, and the
constitution gates, and exits 1 on any Critical or High. Then do the checks it
cannot: spec versus plan contradictions, testability, term drift, gaps.

## Checks

| Check | Finding when |
|-------|--------------|
| Coverage | an `AC-n` has no task, or no test step |
| Unrequested work | a task maps to no `AC-n` and is not `setup` or `docs` |
| Spec vs plan | the plan contradicts, or silently narrows, a criterion |
| Constitution | a gate answered no with no entry under Complexity tracking |
| Open items | a `[NEEDS CLARIFICATION]` marker remains |
| Testability | a criterion no test could fail |
| Terms | the same thing is named two ways across the files |
| Gaps | an error case, limit, or actor the plan needs is absent from the spec |

## Output

<output>
The script's output, plus a table of your own findings in the same section: ID,
severity, location (`file:line`), problem, fix, and which file's author fixes it.

- **Critical**: a constitution violation, or an `AC-n` with no task.
- **High**: spec and plan contradict; a criterion that cannot be tested.
- **Medium**: unrequested work; term drift.
- **Low**: wording.

Critical and High block `core-be-implement`. The author fixes them: spec issues go
back through `core-be-clarify` or `core-be-change` (the user decides what the spec
says), plan and task issues are fixed in place. Re-run until none remain.

When clean, the workflow's Phase 5 shows the user the spec, the design plan, and
the checklist together and asks: "Approve spec, design plan and checklist?". On a yes, record
`approved by <name>, <date>` in the `Status:` line of the task `tasks.md`.
</output>
