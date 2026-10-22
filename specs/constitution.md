# Constitution

- **Version:** 1.0.0
- **Ratified:** 2026-10-22
- **Owner:** Shubham Halder, backend engineer

Standing rules every plan must pass. Each principle has a gate question a plan
answers yes or no. Stricter than the coding standards, never looser. Change it
only through `core-be-constitution`, with the user's approval.

## Principles

| # | Principle | Rule | Gate question |
|---|-----------|------|---------------|
| 1 | Test-first | Every acceptance criterion has a failing test before its code exists. | Does every `AC-n` have a test step that runs before its code step? |
| 2 | Simplicity | The smallest design that meets the spec. No layer, queue, cache, retry, or flag without a named risk. | Does each new layer or moving part name the risk it removes? |
| 3 | Reuse first | Search for an existing helper, client, model, or fixture before writing one. | Does the plan list what it reuses and why nothing existing fits for each new piece? |
| 4 | Security at trust boundaries | Validate input, authorise, and limit at every boundary; no secret in code or logs. | Is the control stated for every trust boundary the feature crosses? |
| 5 | Explicit contracts | Interfaces, error cases, and limits are written down before they are coded. | Does the plan state request, response, every error status, and limits? |
| 6 | Observable and reversible | Failures are logged with context, and every rollout step has a rollback recipe. | Does the plan name what is logged and give a rollback recipe? |
| 7 | Docs agree with code | A change is done only when every place that lists the changed thing is updated (the Definition of done in `AGENTS.md`). | Does the plan list each doc, schema and test that must change with the code? |
| 8 | Dependency-free model support | `src/core/model_support/` imports only the stdlib, `httpx`, `src.core.config` and `src.core.logger`. | Does the plan keep `livekit` and `fastapi` imports out of `src/core/model_support/`? |

## Why

- **Test-first:** a prompt or config that is accepted but wrong shows up as a silent call, so the failing test is the only early signal.
- **Simplicity:** this repo has shipped over-built config knobs that were later removed.
- **Reuse first:** three runtimes share one package, and duplicated helpers drift between them.
- **Security at trust boundaries:** the API takes user-authored config and forwards it to paid providers.
- **Explicit contracts:** external workers and webhook consumers implement against documented payloads.
- **Observable and reversible:** a bad deploy affects live phone calls, so a rollback recipe must exist before rollout.
- **Docs agree with code:** the public docs, dev-docs and the code have each disagreed before, and the factory code is the authority.
- **Dependency-free model support:** the control image has no `livekit-agents` and the agent image has no FastAPI, so a stray import breaks one image.

## Governance

- A violation is allowed only when the plan records it under Complexity
  tracking, with the reason and the simpler alternative rejected.
- `core-be-analyze` treats an unrecorded violation as Critical.
- Amendments need the user's approval and a version bump.

## Amendment log

| Date | Version | Change | Reason |
|------|---------|--------|--------|
| 2026-10-22 | 1.0.0 | Ratified | |
