# Constitution

- **Version:** 1.0.0
- **Ratified:** YYYY-MM-DD
- **Owner:** <name/role>

Standing rules every plan must pass. Each principle has a gate question a plan
answers yes or no. Stricter than the coding standards, never looser. Change it
only through `core-be-constitution`, with the user's approval.

## Principles

Starter set; keep, drop, or reword with the user before ratifying.

| # | Principle | Rule | Gate question |
|---|-----------|------|---------------|
| 1 | Test-first | Every acceptance criterion has a failing test before its code exists. | Does every `AC-n` have a test step that runs before its code step? |
| 2 | Simplicity | The smallest design that meets the spec. No layer, queue, cache, retry, or flag without a named risk. | Does each new layer or moving part name the risk it removes? |
| 3 | Reuse first | Search for an existing helper, client, model, or fixture before writing one. | Does the plan list what it reuses and why nothing existing fits for each new piece? |
| 4 | Security at trust boundaries | Validate input, authorise, and limit at every boundary; no secret in code or logs. | Is the control stated for every trust boundary the feature crosses? |
| 5 | Explicit contracts | Interfaces, error cases, and limits are written down before they are coded. | Does the plan state request, response, every error status, and limits? |
| 6 | Observable and reversible | Failures are logged with context, and every rollout step has a rollback recipe. | Does the plan name what is logged and give a rollback recipe? |

For each principle kept, add a one-line **Why** below.

- **<Principle>:** <why it matters in this repo>

## Governance

- A violation is allowed only when the plan records it under Complexity
  tracking, with the reason and the simpler alternative rejected.
- `core-be-analyze` treats an unrecorded violation as Critical.
- Amendments need the user's approval and a version bump.

## Amendment log

| Date | Version | Change | Reason |
|------|---------|--------|--------|
| YYYY-MM-DD | 1.0.0 | Ratified | |
