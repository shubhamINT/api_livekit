# Research — 2026-10-22-feature-hybrid-prompt-format

Read of `src/` for hardcoded prompts. Citations are `file:line` as of 2026-10-22.

## Inventory of built-in prompts

| # | Prompt | Location |
|---|--------|----------|
| 1 | Speech-output rules, appended to every agent's instructions | `src/core/agents/dynamic_assistant.py:6`, appended at `:29` |
| 2 | Backchannel system prompt with avoid list | `src/core/agents/voice_features.py:50` |
| 3 | Silence re-prompt instruction (realtime modes) | `src/core/agents/voice_features.py:189` |
| 4 | Max-duration farewell instruction | `src/core/agents/session.py:1618` |
| 5 | Default greeting instruction | `src/core/agents/session.py:843` |
| 6 | Ending-the-call directive, concatenated onto the stored prompt | `src/core/agents/session.py:829` |
| 7 | end_call tool reply `Say this to the user: '...'` | `src/core/agents/session.py:820` |
| 8 | Backchannel user message | `src/core/agents/voice_features.py:69` |

Prompts 6, 7, 8 were not in the first scope note. Prompt 6 matters most: it is concatenated onto `assistant.assistant_prompt`, so the stored text and the directive are one string before `DynamicAssistant` sees it.

## Spoken strings, not prompts

`voice_features.py:194` (silence sentence) and `session.py:1616` (farewell sentence) are text for the caller. They stay unchanged.

## Not checked

- Whether the GPT-Live (duplex) path reads its instructions from the `DynamicAssistant` agent or from a separate argument in `src/core/agents/llm/factory.py`. The plan assumes `DynamicAssistant` carries them and routes the Gemini model-level argument through `compose_instructions`. Verify while implementing.
- Whether `render_prompt` (`src/core/agents/utils.py:7`) could mangle tag text: it renders `{{key}}` placeholders only, and the new tags contain none.
