# Scope — 2026-10-22-feature-hybrid-prompt-format

- **Type:** feature
- **Requested by:** Shubham Halder (backend engineer)
- **Date:** 2026-10-22

## Original request (verbatim)

> do one thing, that is I want to transform all the system prompt or the master prompt those are present here into a hybrid format of XML and Markdown.

## Agreed scope

| Question | Answer |
|----------|--------|
| Target (paths / endpoints / diff) | Hardcoded prompt strings in `src/` (known so far: `_TTS_CHUNK_DIRECTIVE` in `src/core/agents/dynamic_assistant.py`, silence reprompt in `src/core/agents/voice_features.py`, farewell and `start_instruction` wrappers in `src/core/agents/session.py`). Full inventory is a research step. |
| Depth (quick / standard / deep) | standard (confirmed) |
| Out of scope | Stored `Assistant.assistant_prompt` rows in MongoDB and any migration script for them; docs/examples prompts. |
| Constraints | Prompt behaviour must not change meaning; no new dependencies; public API unchanged (confirmed). |
| Success criteria | Every in-scope prompt string uses XML tags for structure and Markdown inside them; tests green (confirmed). |
| Report format (HTML / MD) | HTML |
| Severity cut-off | all |
| Spec (feature / change) | specs/001-hybrid-prompt-format/spec.md |
| Type-specific answers | Method for stored prompts: not applicable (out of scope). Process: run specify and clarify before plan. |

## Assumptions confirmed with the user

- Scope is hardcoded prompts in `src/` only (user answer, 2026-10-22).

## Clarification log

| Question asked | User's answer |
|----------------|---------------|
| Which prompts count as system/master prompts? | Hardcoded prompts in src/ |
| How to transform stored assistant_prompt? | Manual per prompt (moot: stored rows are out of scope) |
| Gate failed: no constitution or spec. Proceed how? | Run clarify/specify first |
| Depth, constraints, success criteria | Confirm all defaults |
| Create constitution? | Yes, specs/constitution.md v1.0.0 with 8 principles |
| Wrap the operator's stored prompt in its own tag? | Wrap it |
| Wrap one-line prompts (silence re-prompt, default greeting, farewell) in a tag? | Wrap all |
| Escape values inserted into a tag (avoid list, stored start instruction)? | Pass through |
| Token growth cap for the speech-output rules and backchannel prompts? | +25% max |
