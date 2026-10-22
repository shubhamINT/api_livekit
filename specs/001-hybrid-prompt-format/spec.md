# Spec 001 — Hybrid XML + Markdown built-in prompts

- **Status:** implemented
- **Owner:** Shubham Halder, backend engineer
- **Last changed:** 2026-10-22

## Summary

Every prompt the platform itself writes and sends to a model (not the prompts
operators store on their assistants) is restructured into a hybrid format: XML
tags mark the sections, Markdown carries the content inside each section. The
goal is prompts that models can parse by section and that people can edit
without breaking the structure. What each prompt tells the model to do does not
change.

## Users and stories

- As a platform developer, I can open any built-in prompt and see its sections
  as named tags with Markdown inside, so that I can change one rule without
  reading the whole text.
- As an operator, I keep my stored assistant prompt exactly as I wrote it, so
  that nothing I configured changes under me.
- As a caller on a live call, I hear the same behaviour as before, so that the
  restructuring is invisible.

## Acceptance criteria

Numbered, testable, never renumbered.

- **AC-1:** Given each built-in prompt in the inventory (see Data), when it is
  built, then every section is wrapped in a well-formed, balanced XML tag and
  no prose sits outside a tag. Lists and emphasis inside a tag use Markdown.
- **AC-2:** Given the original wording of each inventory prompt, when the
  converted prompt is built, then every rule, example and constraint from the
  original is still present and no new rule is added or dropped.
- **AC-3:** Given an assistant with a stored prompt, when the session
  instructions are built, then the stored prompt text appears byte for byte
  unchanged and the speech-output rules still follow it in every mode that
  appended them before.
- **AC-4:** Given an assistant with an empty or missing stored prompt, when the
  session instructions are built, then building succeeds and still carries the
  speech-output rules.
- **AC-5:** Given the backchannel prompt built with a non-empty avoid list and
  with an empty one, when it is built, then the avoid list appears inside its
  own tag when present and nothing is left behind (no empty tag, no stray
  text) when absent.
- **AC-6:** Given the max-duration farewell, when the farewell instruction is
  built, then it still tells the model to say the fixed sentence exactly and
  nothing else, and the sentence is unchanged.
- **AC-7:** Given an assistant whose stored start instruction is set, and one
  where it is unset, when the greeting instruction is built, then the stored
  text is used verbatim in the first case and the default greeting instruction
  (in the new format) in the second.
- **AC-8:** Given the converted prompts, when the existing test suite and the
  new per-prompt tests run, then all pass, and no stored assistant, API request
  or API response changes shape.
- **AC-9:** Given the speech-output rules and the backchannel prompt, when the
  converted prompt's length in characters is compared with the original
  wording's, then it is no more than 25% larger. (Characters stand in for
  tokens; no tokenizer is installed and none is added.)
- **AC-11:** Given the end-call tool is enabled, with and without a trigger
  phrase, when the ending-the-call directive is built, then the trigger-phrase
  hint appears only when a phrase is set, and the end-call tool's reply to the
  model still contains the goodbye message exactly.
- **AC-10:** Given a value inserted into a tag (avoid list, stored start
  instruction) that contains `<`, `>` or `&`, when the prompt is built, then the
  value appears verbatim, unescaped.

## Interfaces

No endpoint, request or response changes. Prompts are internal strings sent to
the model provider. Error cases: none new; a prompt that fails to build must
fail exactly as it does today.

## Data

Inventory of built-in prompts in scope (to be confirmed complete by research):

| # | Prompt | Sent when |
|---|--------|-----------|
| 1 | Speech-output rules appended to every assistant prompt | every session start |
| 2 | Backchannel filler system prompt (carries an optional avoid list) | each filler request while the caller speaks |
| 3 | Silence re-prompt instruction | caller silent past the configured interval |
| 4 | Max-duration farewell instruction (carries the fixed sentence) | call reaches its time limit |
| 5 | Default greeting instruction | speaks-first with no stored start instruction |
| 6 | Ending-the-call directive appended to the assistant prompt when the end-call tool is enabled (carries an optional trigger phrase) | every session with that tool |
| 7 | Reply the end-call tool hands back to the model (carries the goodbye message) | the model ends the call |
| 8 | Backchannel user message (carries recent conversation lines) | each filler request |

Spoken-aloud fixed strings (the silence re-prompt sentence, the farewell sentence)
are text for the caller, not prompts, and stay as they are.

No stored data changes. Stored assistant prompts and start instructions are out of scope.

## Limits and non-functional

- Who may call: N/A — no new caller-facing surface.
- Size and latency: prompts 1 and 2 are sent on every session or filler request,
  so token growth costs money and latency on every call. Cap: +25% (AC-9).
- Privacy: N/A — no new data reaches a provider.
- Availability: a prompt change must not make any call fail to start.

## Out of scope

- Stored `assistant_prompt` and `assistant_start_instruction` values, and any
  migration or rewrite of them.
- Prompts quoted only as examples in `docs/`.
- Tool descriptions and tool schemas.

## Open questions

None.

## Change log

| Date | Change | Task slug |
|------|--------|-----------|
| 2026-10-22 | Created | 2026-10-22-feature-hybrid-prompt-format |
| 2026-10-22 | Inventory fix found while planning: added prompts 6-8, ending-the-call section in AC-3, AC-11; AC-9 measures characters, not tokens (no tokenizer installed) | 2026-10-22-feature-hybrid-prompt-format |
| 2026-10-22 | Implemented; converge verdict Converged | 2026-10-22-feature-hybrid-prompt-format |
| 2026-10-22 | Clarified: stored prompt wrapped in a tag, all prompts incl. one-liners tagged, inserted values unescaped, +25% token cap (AC-3, AC-9, AC-10) | 2026-10-22-feature-hybrid-prompt-format |
