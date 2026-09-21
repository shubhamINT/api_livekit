# Plan 05 — Add Gemini 3.8 Live models (`gemini-3.8-live`, `gemini-3.8-live-extended-thinking`)

Status: **planned, not started** (2026-09-21). Research done against live sources; no code changed.
Requester asked for "the latest gemini 3.8 model … with proper pricings and everything so users can use it."

## Verified findings (research summary)

Sources: LiveKit Google plugin source (`livekit/agents@main`,
`livekit-plugins/google/realtime/api_proto.py` and `realtime_api.py`, fetched via the
livekit-docs MCP `code_search`), the LiveKit Gemini plugin docs page
(`docs.livekit.io/agents/models/realtime/plugins/gemini/`), Google's model pages
(`ai.google.dev/gemini-api/docs/models/gemini-3.8-live`, `…/gemini-3.8-live-extended-thinking`),
and Google's pricing page (`ai.google.dev/gemini-api/docs/pricing`). All fetched 2026-09-21.

### What exists upstream

The plugin's `LiveAPIModels` literal in `api_proto.py` now lists five ids:

| Model | Status | Notes |
|---|---|---|
| `gemini-3.8-live` | Stable (2026-09-15) | Google's recommended default for low-latency voice agents. Interleaved reasoning, **async function calling**, **full mid-session client-content updates** (`generate_reply()`, `update_instructions()`, `update_chat_ctx()` all work). 131,072 input / 65,536 output tokens. |
| `gemini-3.8-live-extended-thinking` | Stable | High-reasoning audio-to-audio variant for complex multi-step voice agents; **async-only** function calling; designed to mask tool latency. |
| `gemini-3.1-flash-live-preview` | Preview | Already allowlisted here. Its mid-session-update breakage is **fixed in `livekit-plugins-google>=1.8.2`** (LiveKit docs: "On current plugin versions, `generate_reply()`, `update_instructions()`, and `update_chat_ctx()` all work with 3.1 models"). Remaining 3.1 caveats we don't use anyway: no affective dialog, no proactive audio, `thinkingLevel` instead of `thinkingBudget`. |
| `gemini-2.5-flash-native-audio-preview-12-2025` | Preview | Current default (`DEFAULT_GEMINI_LIVE_MODEL`, `src/core/model_support/capabilities.py:218`). |
| `gemini-live-2.5-flash-native-audio` | GA, **Vertex-only** | Already allowlisted here; unusable with a plain `GOOGLE_API_KEY` (plugin's `_validate_model_api_match` raises `ValueError`). Out of scope. |

Plugin-internal 3.8 handling (`realtime_api.py`) we inherit for free:
`MODELS_WITHOUT_REPLY_PLACEHOLDER = ("3.1", "3.8")` and
`MODELS_DEFAULT_NON_BLOCKING = ("3.8",)` — the plugin skips the `.` reply placeholder and
defaults tools to `NON_BLOCKING` on 3.8 models. No factory change needed.

### Pricing (official Google pricing page, Standard paid tier, per 1M tokens)

All three 3.x Live models (`gemini-3.8-live`, `gemini-3.8-live-extended-thinking`,
`gemini-3.1-flash-live-preview`) share **one** price block:

| | Text | Audio | Image/Video |
|---|---|---|---|
| Input | $0.75 | $3.00 (≈$0.005/min) | $1.00 (≈$0.002/min) |
| Output (incl. thinking tokens) | $4.50 | $12.00 (≈$0.018/min) | — |

Search grounding: 5,000 free requests/month shared across all Gemini 3.x models, then
$14 per 1,000 requests. A rate-limited free tier exists (content used to improve products).

### Dependency reality

- Repo pins `livekit-agents[…]~=1.7.1` (`pyproject.toml:13`) → `livekit-plugins-google==1.7.1`
  (`uv.lock`), which predates the 3.8 models entirely.
- 3.8 support landed in `livekit-agents@1.8.2` (2026-09-15, PR #7289 "(gemini live): add new
  models"). `livekit-agents[google]~=1.8.2` resolves to `livekit-plugins-google>=1.8.2`.
- Changelog scan 1.7.1 → 1.8.2: the only **breaking** block is 1.8.0's OpenTelemetry GenAI
  semantic-convention migration (span/attribute renames, PII strip moved in-process). This repo
  does not consume OTel span names — impact is nil, but it is why the bump is called out
  explicitly. Everything else touching our plugins (deepgram, elevenlabs, cartesia, openai,
  google) is fixes/features, no API removals seen.
- `tests/test_realtime_capabilities.py:84` asserts
  `GEMINI_LIVE_MODELS == set(get_args(LiveAPIModels))` — after the bump the parity test **fails
  until the allowlist grows**, which is the intended forcing function.

### Decisions (confirmed with the requester 2026-09-21)

1. **Default moves to `gemini-3.8-live`.** Google calls it the default option for low-latency
   voice agents; every platform feature that depends on `generate_reply()` (max-duration
   farewell, silence re-prompts) works on it. Behavior change for assistants that omit
   `model` is accepted.
2. **Both 3.8 ids are allowlisted**, including `gemini-3.8-live-extended-thinking`, with its
   latency/async-tools trade-off documented (the parity test would otherwise need a carve-out).
3. **The 3.1 guard is removed.** `GEMINI_NO_MIDSESSION_CONTENT_MODELS`
   (`src/core/model_support/capabilities.py:174`) and the warning in
   `src/core/agents/session.py:879-886` document a limitation that plugin ≥1.8.2 fixes
   upstream. Keeping them would warn about a bug that no longer exists.

## Tickets (execution order)

### T1 — Dependency bump

- `pyproject.toml:13`: `~=1.7.1` → `~=1.8.2`.
- `uv lock` (expect `livekit-agents==1.8.2`, `livekit-plugins-google>=1.8.2`; check nothing
  else jumps unexpectedly).
- `uv run python -m unittest discover -s tests` — baseline must be green before touching code.
  Expect exactly one failure class: the `LiveAPIModels` parity assertion in
  `tests/test_realtime_capabilities.py:84`, fixed by T2.

### T2 — `src/core/model_support/capabilities.py`

- `GEMINI_LIVE_MODELS` (`:157-163`): add `"gemini-3.8-live"` and
  `"gemini-3.8-live-extended-thinking"`. Keep the comment block but update it — it currently
  says the list came from "livekit-agents 1.6.7"; re-source it to the 1.8.2 `api_proto.py`.
- Delete `GEMINI_NO_MIDSESSION_CONTENT_MODELS` (`:174`) and its comment block (`:165-173`).
- `DEFAULT_GEMINI_LIVE_MODEL` (`:218`): → `"gemini-3.8-live"`. Keep the comment style.
- Validation error text in `src/api/models/api_schemas/config/llm_config.py:229-232` sorts the
  set at raise time — no change needed there.

### T3 — `src/core/agents/session.py`

- Remove the `GEMINI_NO_MIDSESSION_CONTENT_MODELS` import (`:94`) and the warning block
  (`:871-886`, keeping `_gemini_model = llm_config.get("model") or DEFAULT_GEMINI_LIVE_MODEL`
  which feeds the constructor at `:887-893`).

### T4 — Tests

- `tests/test_realtime_capabilities.py`: drop the `GEMINI_NO_MIDSESSION_CONTENT_MODELS` import
  (`:20`) and the `assertNotIn(DEFAULT_GEMINI_LIVE_MODEL, GEMINI_NO_MIDSESSION_CONTENT_MODELS)`
  assertion (`:95`). Parity test (`:84`) now passes unmodified. Existing tests using
  `gemini-3.1-flash-live-preview` (`:41`, `:113`, `:144`) keep passing — 3.1 stays allowlisted.
- Add coverage:
  - `gemini-3.8-live` and `gemini-3.8-live-extended-thinking` accepted in `realtime` mode;
    rejected (`422`) in `pipeline` and `cascade` (extend the existing mode-validation cases in
    `tests/test_realtime_capabilities.py` / `tests/test_assistant_schemas.py`).
  - Default assertion: `DEFAULT_GEMINI_LIVE_MODEL == "gemini-3.8-live"` and membership in
    `GEMINI_LIVE_MODELS` (`:94` already does the membership half).
- Grep check afterwards: no reference to `GEMINI_NO_MIDSESSION_CONTENT_MODELS` anywhere.

### T5 — Docs sweep (Definition of Done, AGENTS.md)

- `docs/reference/models.md`:
  - `:20` — "one of the three `GEMINI_LIVE_MODELS`" → full five-id list; default cell →
    `gemini-3.8-live`.
  - Replace the `!!! warning` block (`:34-40`) — the "default moved off 3.1" story is obsolete;
    replace with a short note: default is `gemini-3.8-live` (stable), 3.1's mid-session
    limitation is fixed by `livekit-plugins-google>=1.8.2`, extended-thinking trades latency
    for reasoning and is async-function-calling only.
  - Add a pricing table for the Gemini Live models (numbers in "Pricing" above, cite
    `ai.google.dev/gemini-api/docs/pricing`).
- `docs/reference/compatibility.md`:
  - `:30` — gemini row default → `gemini-3.8-live`.
  - `:55` — the `GEMINI_LIVE_MODELS` enumeration gains both 3.8 ids, new default marked.
- `docs/reference/troubleshooting.md`: rewrite the 3.1 section (`:217`, `:230`, `:234`) — the
  1007/`generate_reply()` failure is fixed by the dep bump; keep the *symptom* documented
  (silent farewell on old plugin versions) with the remedy "upgrade `livekit-agents` to ≥1.8.2".
- `docs/getting-started/index.md:43` and `:93`, `docs/api/assistant/index.md:29`,
  `docs/api/assistant/update.md:42`, `docs/api/assistant/create.md:175` and `:204`,
  `docs/api/assistant/get.md:67` — default model strings and "only the three Gemini Live
  models" phrasing → five models, `gemini-3.8-live` default.
- `docs/architecture/cascade-pipeline.md:275` — mentions both lists by name only; verify the
  sentence still reads true (it does; no edit expected).
- `AGENTS.md` — update the "Recent changes — the silent call" item 5 (Gemini default rationale
  is superseded) and add a short recent-changes entry for this change (bump + new default +
  guard removal).

### T6 — Verification (all must pass)

- `uv run python -m unittest discover -s tests` — green.
- `uv run mkdocs build --strict` — clean.
- `uvx ruff check <touched files>` — clean.
- `uv run python scripts/check_model_allowlist.py` — OpenAI-side only, but AGENTS.md requires
  running it before/after touching any model set.
- Optional but strongly recommended: one live smoke call with a real `GOOGLE_API_KEY` on
  `gemini-3.8-live` confirming greeting + a tool call + the max-duration farewell fires
  (the two features the 3.1 guard existed for).

## Risks / watch-items

- **Default change is user-visible.** Assistants omitting `model` silently move from a 2.5
  preview to 3.8 stable. Voice roster is unchanged (same 30-name `Voice` literal in
  `api_proto.py`), so no stored `voice` breaks.
- **`gemini-3.8-live-extended-thinking` latency.** Reasoning before speaking is the point of
  the model; docs must set expectations rather than the API rejecting anything.
- **Vertex-only id stays allowlisted** (`gemini-live-2.5-flash-native-audio`) and still cannot
  work with `GOOGLE_API_KEY`-auth deployments (plugin raises `ValueError` by design). Not in
  scope, but worth a follow-up ticket: the API could reject it at create-time instead of
  letting the job fail at connect.
- **Dep bump blast radius** is covered by the full test suite; the 1.8.0 OTel rename is the
  only upstream breaking change and we consume none of those names.
