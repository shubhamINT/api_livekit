# Progress — 2026-10-22-feature-hybrid-prompt-format

## Analysis (2026-10-22)

Script: `sdd-check.sh analyze 2026-10-22-feature-hybrid-prompt-format` -> `OK`, exit 0.

| ID | Severity | Location | Problem | Fix | Owner |
|----|----------|----------|---------|-----|-------|
| A-1 | Medium | tasks.md step 9 | Its test was optional ("if the existing session tests allow it"), breaking test-first | Test moved into step 7 (ordered three-section case); step 9 verified by grep | tasks (fixed in place) |
| A-2 | Low | tasks.md step 10 | AC-9 length compared with the avoid clause unspecified | Both sides measured with an empty avoid list | tasks (fixed in place) |
| A-3 | Low | tasks.md step 13 | Test passes immediately, not red-first | Marked as a characterization test | tasks (fixed in place) |

No Critical or High. Open risk, not a finding: the duplex instruction path is unverified until step 2.

## Implementation log

- Step 2 (read-only): duplex persona is the agent's own instructions (`src/core/agents/llm/factory.py:191` doc; `create_gpt_live` takes no prompt argument), so `DynamicAssistant` carries it. Plan assumption holds. Only readers of `assistant.assistant_prompt` are `session.py:405,406,829,842,949`.
- Steps 1, 3-5: `tests/test_builtin_prompts.py` (helper, golden originals, speech-rule tests) red on ImportError, then `src/core/agents/prompts.py::speech_output_rules` green (rule lines kept verbatim, length under 1.25x).
- Steps 6-8: tests for `compose_instructions`, `DynamicAssistant(sections=)`, `ending_the_call`, `end_call_reply` red (missing names, unknown kwarg), then green. `_TTS_CHUNK_DIRECTIVE` deleted from `dynamic_assistant.py`.
- Step 9: `session.py` no longer concatenates onto `assistant_prompt` (grep: only `render_prompt` assigns it); end-call section passed as `sections=` to `DynamicAssistant` and through `compose_instructions` at the Gemini site; `end_call_reply` replaces the inline f-string. `tests/test_agent_entrypoint.py` still green.
- Steps 10-13: tests for backchannel, one-liners, verbatim values red (missing builders), then green. `voice_features.py` and `session.py` (greeting x4 model-bound sites, farewell) use the builders.
- Deviation (recorded in tasks.md): greeting wrapped at model call sites; `start_instruction` stays plain because `session.py` records it as `spoken_text` for the silence watchdog.
- Step 14: `uv run python -m unittest discover -s tests` -> 699 OK. The `assert dropped` trace from livekit rtc dispose also appears on the unmodified tree. Ruff: new files clean; `session.py`/`voice_features.py` back to the baseline 25 pre-existing findings. `git diff --stat -- src/api src/core/db` empty.
- Step 15: `AGENTS.md` key-locations row; `dev-docs/subsystems/speech-and-llm-stages.md` "Built-in prompts" section + table row. `mkdocs build --strict` ok, `check_mermaid` 0 broken.

## Out-of-scope observations

- `src/core/agents/voice_features.py`: `AsyncOpenAI(api_key=...)` for the backchannel call has no explicit timeout (SDK default). Follow-up task offered.
- `session.py`: `llm_config.get("backend_instructions")` (`llm/factory.py:207`) is a user-config prompt, not built-in; untouched.

## Converge

Command: `uv run python -m unittest tests/test_builtin_prompts.py -v` -> 18 ok; full suite 698 OK.

| AC | Evidence | Code | Status |
|----|----------|------|--------|
| AC-1 | `tests/test_builtin_prompts.py::SpeechOutputRulesTests::test_is_a_balanced_tagged_block`, `BackchannelTests::test_system_prompt_is_tagged_and_keeps_every_rule`, `BackchannelTests::test_user_message_wraps_context_only_when_there_is_some`, `OneLinerTests::test_silence_reprompt_is_tagged` (and every `assert_hybrid` call) | `src/core/agents/prompts.py:10,33,51,62,66,70,104` | met |
| AC-2 | `SpeechOutputRulesTests::test_every_original_rule_survives_unchanged`, `BackchannelTests::test_system_prompt_is_tagged_and_keeps_every_rule` | `src/core/agents/prompts.py:10,70` | met |
| AC-3 | `ComposeInstructionsTests::test_stored_prompt_is_wrapped_verbatim_then_sections_in_order`, `DynamicAssistantInstructionsTests::test_speech_rules_follow_the_stored_prompt`, `::test_end_call_section_sits_between_prompt_and_speech_rules` | `src/core/agents/prompts.py:27`, `src/core/agents/dynamic_assistant.py:16`, `src/core/agents/session.py:837,840,950` | met |
| AC-4 | `ComposeInstructionsTests::test_empty_or_missing_prompt_has_no_assistant_prompt_tag`, `DynamicAssistantInstructionsTests::test_empty_prompt_still_carries_the_speech_rules` | `src/core/agents/prompts.py:27`, `src/core/agents/dynamic_assistant.py:16` | met |
| AC-5 | `BackchannelTests::test_avoid_list_gets_its_own_tag_only_when_present` | `src/core/agents/prompts.py:70`, `src/core/agents/voice_features.py:48` | met |
| AC-6 | `OneLinerTests::test_farewell_says_the_sentence_exactly` | `src/core/agents/prompts.py:66`, `src/core/agents/session.py:1619` | met |
| AC-7 | `OneLinerTests::test_greeting_uses_the_stored_text_or_the_default` | `src/core/agents/prompts.py:55,58`, `src/core/agents/session.py:844,1776,1794,1801,1814` | met |
| AC-8 | full suite 698 OK (includes `tests/test_agent_entrypoint.py`, `tests/test_assistant_route.py`); `git diff --stat -- src/api src/core/db` empty | no file under `src/api/` or `src/core/db/` changed | met |
| AC-9 | `SpeechOutputRulesTests::test_no_more_than_25_percent_longer`, `BackchannelTests::test_no_more_than_25_percent_longer` | `src/core/agents/prompts.py:10,70` | met |
| AC-10 | `InsertedValuesAreVerbatimTests::test_nothing_is_escaped` | `src/core/agents/prompts.py:27,33,51,58,66,70,104` | met |
| AC-11 | `EndCallTests::test_trigger_phrase_hint_only_when_set`, `EndCallTests::test_reply_carries_the_goodbye_exactly` | `src/core/agents/prompts.py:33,51`, `src/core/agents/session.py:830,837` | met |

Limits of the evidence: the builders are tested; the call sites in `session.py` and `voice_features.py` (which builder goes where) are checked by grep and the suite, not by a test that runs an entrypoint. A live call per mode is still needed before release (plan, Rollout).

Drift scan: no new route, field, flag or error path. Two judgment calls, both inside the spec: the Gemini realtime greeting text (`session.py:1794`) now carries the `<instruction>` tag like the other model-bound greetings, and `ending_the_call` keeps its prose as one paragraph inside its tag.

Constitution re-check on the final diff: 1 yes (tests red first, step 13 a logged characterization guard); 2 yes (one new module); 3 yes; 4 yes; 5 yes; 6 yes (no new logging, rollback = revert); 7 yes (AGENTS.md row, dev-docs section); 8 yes (`src/core/model_support/` untouched).

Design check: shipped design matches the plan except three names and the greeting wrap point, now written into `plan.md` and its change log.

Verdict: Converged

### Simplicity review (code-simplicity-reviewer), applied after converge

- Applied: item 1 (compose once; `DynamicAssistant` loses `sections`), item 2 (greeting default applied once). Suite re-run: 698 OK (one test folded into another), ruff clean on new files. Verdict above still holds; evidence lines refreshed.
- Not applied, on purpose: items 3-5 (shared `instruction()` helper, constants for fixed strings, one constant for the backchannel prompt) are taste; the tagged `<role>/<task>/<critical_rules>` split is what AC-1 asks for. Item 6 (drop verbatim tests) would leave AC-10 covered at one insertion point only. Item 7 (replace `assert_hybrid`) is test-only churn.
- Noted, not changed: the `<conversation>` label replaces "Recent conversation:" (wording shift in the filler user message); the Gemini greeting text turn now carries `<instruction>` tags. Both need the live-call spot check already in the rollout plan.
