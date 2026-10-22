# Plan 001 — Hybrid XML + Markdown built-in prompts

- **Spec:** [spec.md](spec.md)
- **Last changed:** 2026-10-22

## Technical context

Python 3.12+, `uv`, stdlib `unittest` (`uv run python -m unittest discover -s tests`), `livekit-agents~=1.8.8`, `openai` client for the backchannel call. No tokenizer installed (`tiktoken` is absent from `pyproject.toml` and the venv), so the length cap in AC-9 is measured in characters. The prompts live in three worker modules: `src/core/agents/dynamic_assistant.py:6` (speech rules), `src/core/agents/voice_features.py:50,69,189` (backchannel system and user messages, silence re-prompt), `src/core/agents/session.py:820,829,843,1618` (end-call reply and directive, default greeting, farewell).

## Constitution check

| # | Principle | Gate question | Answer | Note |
|---|-----------|---------------|--------|------|
| 1 | Test-first | Does every `AC-n` have a test step that runs before its code step? | yes | Tasks order each test before its code. |
| 2 | Simplicity | Does each new layer or moving part name the risk it removes? | yes | One new module, named in Complexity tracking. |
| 3 | Reuse first | Does the plan list what it reuses and why nothing existing fits? | yes | Reuses `DynamicAssistant`, `render_prompt` untouched; no existing prompt module exists. |
| 4 | Security at trust boundaries | Is the control stated for every trust boundary crossed? | yes | See Design 5: no new boundary; unescaped pass-through is the accepted AC-10 decision. |
| 5 | Explicit contracts | Does the plan state request, response, every error status, and limits? | yes | No HTTP surface; builder signatures in Contracts. |
| 6 | Observable and reversible | Does the plan name what is logged and give a rollback recipe? | yes | See Design 7 and Rollout. |
| 7 | Docs agree with code | Does the plan list each doc, schema and test that must change? | yes | See Design 8. |
| 8 | Dependency-free model support | Does the plan keep `livekit` and `fastapi` imports out of `src/core/model_support/`? | yes | Nothing is added there; the new module is in `src/core/agents/`. |

## Design

**Format.** A built-in prompt is a sequence of top-level snake_case tags, nothing outside a tag. Markdown (`-` lists, `**bold**`) goes inside. No Markdown headings, because the tag name already is the heading.

**Placement.** One new module, `src/core/agents/prompts.py`: constants and small builder functions, stdlib only, no `livekit` import. It sits in `core/agents/` because only the worker uses it. `api/` never imports it.

**Assembly of the session instructions.** Today `session.py:829` appends the end-call directive onto `assistant.assistant_prompt`, and `DynamicAssistant` (`dynamic_assistant.py:29`) appends the speech rules. That mutation would put the directive inside the stored text and break AC-3. Instead:

1. `session.py` stops mutating `assistant.assistant_prompt` and keeps the end-call section in a local list.
2. `compose_instructions(prompt, *sections)` returns `<assistant_prompt>…</assistant_prompt>` (omitted when the prompt is empty, so no empty tag), then each section in order.
3. `session.py` calls `compose_instructions(prompt, *sections)` once. `DynamicAssistant` receives that text and appends `speech_output_rules()`.
4. The Gemini realtime site (`session.py:950`) previously received the stored prompt plus the end-call directive but no speech rules. It receives the same composed text, which keeps that content set.

Section order is fixed: `assistant_prompt`, `ending_the_call`, `speech_output_rules`.

**Builders** (all return `str`): `speech_output_rules()`, `ending_the_call(trigger_phrase)`, `end_call_reply(message)`, `backchannel_system(avoid)`, `backchannel_user(context_lines)`, `silence_reprompt()`, `farewell_instruction(sentence)`, `greeting_instruction(stored)`, `DEFAULT_GREETING`.

**1. Numbers.** No traffic change. Prompts 1 and 6 ride on every session start; 2 and 8 on every filler request. Cap: converted length ≤ 1.25 × original characters (AC-9).
**2. Data.** N/A — no stored data, no schema, no migration.
**3. Concurrency and idempotency.** N/A — pure string building, no shared state. The one module-level state (`_recent_fillers` in `voice_features.py`) is untouched.
**4. Outbound calls.** The backchannel request to the model provider (`voice_features.py:45`) and all `generate_reply` calls keep their current timeouts, retries and error handling; only the text they send changes.
**5. Security.** No new trust boundary. Inserted values (avoid list, start instruction, goodbye message, trigger phrase) are operator-written or model-produced and are inserted raw (AC-10). A value containing a closing tag can end its own section early, but the same operator already controls the whole prompt, so nothing is gained. Recorded as accepted, not overlooked.
**6. Compatibility.** Stored assistants, API payloads and responses are unchanged (AC-8). The text the model receives changes on every call, so behaviour can drift even though each rule is preserved (AC-2). That risk is handled in Rollout.
**7. Observability.** No new logging. Prompt text is never logged (it can hold caller metadata). A failure to build instructions raises at session start and is logged by the existing entrypoint handling.
**8. Docs and tests to change.** `AGENTS.md` key-locations table (new row for `prompts.py`); `dev-docs/subsystems/speech-and-llm-stages.md` (a short "built-in prompts" section naming the format rule); `tests/` (one new `test_builtin_prompts.py`). A grep over `docs/`, `dev-docs/`, `README.md` and `tests/` for the prompt wording found no page quoting any of them, so no `docs/` page changes.

**Observations outside scope** (not fixed here): the backchannel client in `voice_features.py` is built with `AsyncOpenAI(api_key=...)` and no explicit timeout, so it uses the SDK default. Offer a follow-up task.

## Data model

None. AC-8 requires no stored or API shape change.

## Contracts

| Function | Input | Output | Traces to |
|----------|-------|--------|-----------|
| `compose_instructions(prompt, *sections)` | stored prompt (may be empty or `None`), section strings | one string: optional `<assistant_prompt>`, then sections in order | AC-3, AC-4 |
| `speech_output_rules()` | none | the `<speech_output_rules>` block, same rules as today | AC-1, AC-2, AC-9 |
| `ending_the_call(trigger_phrase)` | optional phrase | `<ending_the_call>` block; the "for example" hint only when a phrase is set | AC-11 |
| `end_call_reply(message)` | goodbye message | tagged reply containing the message exactly | AC-11 |
| `backchannel_system(avoid)` | list of recent fillers | tagged prompt; `<avoid>` tag only when the list is non-empty | AC-5, AC-9 |
| `backchannel_user(context_lines)` | context text or empty | tagged user message | AC-1 |
| `silence_reprompt()`, `farewell_instruction(sentence)`, `greeting_instruction(stored)`, `DEFAULT_GREETING` | — / sentence / — | one-line prompts wrapped in a tag; farewell keeps "say this exactly and nothing else" and the sentence verbatim | AC-1, AC-6, AC-7 |

A stored start instruction replaces `DEFAULT_GREETING` and is passed verbatim in its tag (AC-7). The wrap happens where the text goes to the model, because `DynamicAssistant.start_instruction` must stay plain: the silence watchdog records it as the assistant's last message. Errors: none new; a builder never raises on empty input.

A test-only helper (`assert_hybrid`) checks that tags are balanced and no prose sits outside them (AC-1). It is test code, not a production function.

## Research decisions

| Choice | Options compared | Picked | Why |
|--------|------------------|--------|-----|
| Where prompts live | Edit in place at 8 sites; one `prompts.py` | `prompts.py` | The convention and its test then sit in one place, and the end-call directive stops being glued onto stored text inside `session.py`. |
| Wrap stored prompt | Wrap; leave raw | Wrap (user decision, spec) | Clear section boundary. |
| Length measure | Add `tiktoken`; characters | Characters | No new dependency for a ±25% bound; characters track tokens closely enough for that. |
| Empty stored prompt | Emit empty `<assistant_prompt></assistant_prompt>`; omit | Omit | An empty tag is noise the model reads on every turn. |
| Headings inside tags | Markdown headings; none | None | The tag name already labels the section; headings add tokens (AC-9). |

No external documentation was consulted: the choices above are about this repo's own structure, not a library's behaviour.

## Complexity tracking

| Violation or extra moving part | Why needed | Simpler option rejected, and why |
|--------------------------------|------------|-----------------------------------|
| New module `src/core/agents/prompts.py` | 8 prompts across 3 modules, one convention, one test file; removes drift risk between sites | Editing each site in place: fewer files, but the convention and its test scatter and the end-call directive keeps mutating the stored prompt. |

## Rollout and rollback

- **Blast radius:** every call, because the speech rules and the stored-prompt wrapper go into every session. Behaviour risk, not an outage: the model reads a re-formatted prompt.
- **Rollout:** one release behind no flag (a flag would double the prompts to maintain). Before release, place one test call per mode (pipeline, realtime, cascade, duplex) on a non-production assistant and listen for the speech rules and end-call phrase still working. The test suite cannot judge that.
- **Rollback recipe:** revert the commit and redeploy the agent image. No data, schema or API change, so nothing else to undo.

## Change log

| Date | Change | Caused by |
|------|--------|-----------|
| 2026-10-22 | Created | AC-1 … AC-11 |
| 2026-10-22 | Simplicity review: compose once in `session.py`, `DynamicAssistant` only appends the speech rules (no `sections` parameter); `greeting_instruction` no longer defaults, `DEFAULT_GREETING` is applied once at construction | AC-3, AC-7 |
| 2026-10-22 | Shipped names and greeting wrap point differ from the draft: `farewell_instruction`, `backchannel_user(context_lines)`, greeting wrapped at the model call sites | AC-6, AC-7 |
