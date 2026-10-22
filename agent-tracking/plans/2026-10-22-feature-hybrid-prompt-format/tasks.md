# Tasks — 2026-10-22-feature-hybrid-prompt-format

**Status:** done (approved 2026-10-22, by Shubham Halder)

**Spec:** specs/001-hybrid-prompt-format/spec.md
**Covers:** AC-1, AC-2, AC-3, AC-4, AC-5, AC-6, AC-7, AC-8, AC-9, AC-10, AC-11

## Goal

Rewrite every built-in prompt the worker sends to a model as top-level XML tags with Markdown inside, without changing what any prompt tells the model.

## Success criteria

- All 8 inventoried prompts built by `src/core/agents/prompts.py`, none left as an inline string at its old site.
- Stored assistant prompt appears byte-identical inside `<assistant_prompt>`; the end-call directive is no longer concatenated onto it.
- Speech rules and backchannel prompt ≤ 1.25 × original length in characters.
- `uv run python -m unittest discover -s tests` green; `uvx ruff check` clean on touched files.

## Skills applied

- core-be-workflow, core-be-specify, core-be-clarify, core-be-plan, core-be-tasks, core-be-constitution
- core-be-coding-standards (during implement), core-be-write-tests (test shape)

## Steps

- [x] 1. `setup` Create `tests/test_builtin_prompts.py` with the `assert_hybrid` helper (balanced tags, no prose outside tags) and the original wording of prompts 1 and 2 as golden constants, copied from `dynamic_assistant.py:6-19` and `voice_features.py:50-67` before any edit. Verify: `uv run python -m unittest tests/test_builtin_prompts.py -v` runs (0 tests of substance yet).
- [x] 2. `AC-3` Read-only check: find where duplex (GPT-Live) takes its instructions (`src/core/agents/llm/factory.py`, `session.py:840-960`). Write the answer into `progress.md`; if the plan's assumption is wrong, stop and amend the plan.
- [x] 3. `AC-1` Test first: `speech_output_rules()` is a balanced `<speech_output_rules>` block. Then create `src/core/agents/prompts.py` with it. Verify: the new test.
- [x] 4. `AC-2` Test first: every rule and example of prompt 1 from the golden constant is present, rule count equal. Fix the wording in `prompts.py` until green.
- [x] 5. `AC-9` Test first: `len(speech_output_rules()) <= 1.25 * len(original)`. Trim tag names or whitespace until green.
- [x] 6. `AC-3` Test first: `compose_instructions("stored", "<x>…</x>")` gives `<assistant_prompt>` with the stored text byte-identical, sections after it in order. Add `compose_instructions` to `prompts.py`.
- [x] 7. `AC-4` Test first: empty and `None` prompt gives no `<assistant_prompt>` tag and still ends with the speech rules via `DynamicAssistant`; also the ordered `<assistant_prompt>` / `<ending_the_call>` / `<speech_output_rules>` case for step 9. Edit `src/core/agents/dynamic_assistant.py` to take `sections` and build with `compose_instructions(prompt, *sections, speech_output_rules())`; delete `_TTS_CHUNK_DIRECTIVE`. Verify: new test plus `tests/test_native_stt_usage.py`.
- [x] 8. `AC-11` Test first: `ending_the_call(trigger_phrase)` shows the "for example" hint only with a phrase; `end_call_reply(message)` contains the message exactly. Add both to `prompts.py`.
- [x] 9. `AC-3` Edit `src/core/agents/session.py`: stop mutating `assistant.assistant_prompt` at `:829`, keep the end-call section in a local list, pass it to `DynamicAssistant(sections=…)` at `:840` and to `compose_instructions` at the Gemini site `:949`; use `end_call_reply` at `:820`. Test (written in step 7, so it fails first): `DynamicAssistant(instructions="stored", sections=[ending_the_call(None)])` yields `<assistant_prompt>stored</assistant_prompt>`, then `<ending_the_call>`, then `<speech_output_rules>`. Step 9 itself is wiring; verify with `grep -n "assistant_prompt =" src/core/agents/session.py` (no concatenation left).
- [x] 10. `AC-5` Test first: `backchannel_system(avoid)` has `<avoid>` only when the list is non-empty, no empty tag or stray text otherwise; plus the AC-2 rule check and AC-9 length check against the golden constant, measured with an empty avoid list on both sides. Add `backchannel_system` and `backchannel_user` to `prompts.py`; use them in `src/core/agents/voice_features.py:44-76`.
- [x] 11. [P] `AC-6` Test first: `farewell(sentence)` contains the sentence verbatim and "say this exactly and nothing else". Add it; use it at `session.py:1618`.
- [x] 12. [P] `AC-7` Test first: `DEFAULT_GREETING` is a balanced one-line tag; a stored start instruction passes through verbatim in its tag. Add it; use it at `session.py:843` and for the stored value. Add `silence_reprompt()` and use it at `voice_features.py:189` (AC-1 via `assert_hybrid`).
- [x] 13. `AC-10` Test first: values containing `<`, `>`, `&` (avoid list, start instruction, goodbye message, trigger phrase) appear verbatim, unescaped. A characterization test that passes at once by design; fix any builder that escapes.
- [x] 14. `AC-8` Run the whole suite and lint. Verify: `uv run python -m unittest discover -s tests` and `uvx ruff check src/core/agents/prompts.py src/core/agents/dynamic_assistant.py src/core/agents/voice_features.py src/core/agents/session.py tests/test_builtin_prompts.py`. Confirm no file under `src/api/` or `src/core/db/` changed (`git diff --stat`).
- [x] 15. `docs` Add the `prompts.py` row to the key-locations table in `AGENTS.md`; add a short "Built-in prompts" section (format rule, section order) to `dev-docs/subsystems/speech-and-llm-stages.md`. Verify: `uv run mkdocs build --strict` and `uv run python scripts/check_mermaid.py`.
- [x] 16. `converge` Run `core-be-converge`.

## Files expected to change

| Path | Change |
|------|--------|
| `src/core/agents/prompts.py` | new: constants and builders for all 8 prompts |
| `src/core/agents/dynamic_assistant.py` | drop `_TTS_CHUNK_DIRECTIVE`, take `sections`, use `compose_instructions` |
| `src/core/agents/session.py` | stop mutating `assistant_prompt`, use builders at `:820`, `:829`, `:843`, `:949`, `:1618` |
| `src/core/agents/voice_features.py` | use builders at `:50`, `:69`, `:189` |
| `tests/test_builtin_prompts.py` | new |
| `AGENTS.md` | one row in key-locations table |
| `dev-docs/subsystems/speech-and-llm-stages.md` | "Built-in prompts" section |
| `agent-tracking/` | progress.md, report |

## Design notes

See `specs/001-hybrid-prompt-format/plan.md` (Design 1-8): no data, no concurrency, no new outbound calls, no new logging; compatibility is the model-visible prompt text only.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Model behaviour drifts on re-formatted prompts though every rule is kept | Rule-for-rule tests (steps 4, 10); one live test call per mode before release |
| Duplex path reads instructions somewhere the plan did not expect | Step 2 checks it before any code |
| Removing the `assistant_prompt` mutation changes what a later reader of `assistant.assistant_prompt` sees (e.g. logging, usage) | `grep -n "assistant_prompt" src` in step 9; fix any reader that relied on the directive being inside it |
| Character cap fails with tags added | Step 5 trims tag names and whitespace; amend the spec, not the test, only with your approval |

## Delivery and rollback

- **Blast radius:** every call; behaviour risk, not an outage.
- **Rollout:** plain deploy of the agent image, no flag; one test call per mode first.
- **Rollback recipe:** revert the commit and redeploy the agent image. No data, schema or API change.

## Verification

| Command | Expected |
|---------|----------|
| `uv run python -m unittest tests/test_builtin_prompts.py -v` | all new tests pass |
| `uv run python -m unittest discover -s tests` | all pass |
| `uvx ruff check <touched files>` | no violations |
| `uv run mkdocs build --strict` | clean |
| `git diff --stat -- src/api src/core/db` | empty |

## Plan changes after first draft

- Step 12: the greeting is wrapped where it goes to the model (`greeting_instruction`), not at construction; `DynamicAssistant.start_instruction` stays plain because the silence watchdog records it (`session.py` `spoken_text`). The builder is `farewell_instruction`, not `farewell`, to avoid shadowing the local variable.
