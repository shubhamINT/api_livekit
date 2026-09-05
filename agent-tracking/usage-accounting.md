# Complete per-call token and usage accounting

## Goal

Every token, character and second that a call is billed for by a provider is stored on the
call's `UsageRecord`, for every assistant mode (`pipeline`, `realtime`, `cascade`) and every
model. Pricing is built later on top of this data; nothing here computes money, but the
record must be complete enough that pricing never needs a schema migration or a backfill.

## Background: what the audit found

Audit of `src/core/agents/usage.py`, `UsageRecord` (`src/core/db/db_schemas.py:345`) and the
installed `livekit-agents` 1.6.7, on 2026-09-04:

1. **Cascade records no token breakdown and loses cache tokens.** `ModelUsageCollector`
   (`livekit/agents/metrics/usage.py:199`) fills only `input_tokens`, `input_cached_tokens`
   and `output_tokens` for `LLMMetrics`. `summarize_usage` never reads `input_cached_tokens`
   and `UsageRecord` has no column for it, so OpenAI prompt-cache hits — the largest single
   discount on a cascade call — are invisible.
2. **Pipeline mode records zero STT usage while paying Sarvam on every call.** The parallel
   tap (`src/core/agents/stt/sarvam_parallel.py:114`) builds a standalone plugin STT that is
   never passed to `AgentSession`, so its `RECOGNITION_USAGE` events reach no collector.
3. **Realtime native transcription is invisible.** The OpenAI realtime plugin receives usage
   on `conversation.item.input_audio_transcription.completed` and discards everything but the
   transcript (`livekit/plugins/openai/realtime/realtime_model.py:1929`).
4. **Token-billed STT/TTS fields are dropped.** `STTModelUsage` and `TTSModelUsage` both carry
   `input_tokens` / `output_tokens`; `UsageRecord` has no columns. Live impact today: cascade
   `assistant_stt_model = "openai"` is token-billed.
5. **Other dropped LLM fields:** `input_image_tokens`, `input_cached_image_tokens`,
   `session_duration`.
6. **Model attribution collapses.** `_models()` comma-joins model names while the numbers are
   summed together, so a mid-call model swap cannot be attributed.
7. **No tests** cover `summarize_usage`.

## Design decisions (agreed with the user, 2026-09-04)

- Persist the raw `model_usage` list verbatim as the pricing source of truth, and keep flat
  columns for the dashboards that already aggregate on them.
- Cached counts are subsets, not separate buckets:
  `input_cached_text_tokens ⊆ input_text_tokens ⊆ input_tokens`, and
  `llm_total_tokens = input_tokens + output_tokens` already contains cached tokens. This has
  to be documented next to the fields; it is the easiest way to get pricing wrong.
- Native realtime transcription: patch the plugin handler to read the usage the SDK drops.
  Version-coupled by construction, so the patch asserts the symbol exists at import.
- Upgrade `livekit-agents` 1.6.7 → 1.7.1 first, in its own PR, because it changes call
  behaviour while the usage PRs do not.
- Write usage incrementally during the call (throttled upsert on `session_usage_updated`) with
  the teardown write authoritative, so a crashed worker still leaves partial data.
- Telephony minutes and recording storage stay out of `UsageRecord`; pricing joins them from
  `CallRecord` and S3.
- No backfill: the data was never captured. Existing rows keep `usage_schema_version = 1` and
  any consumer must treat them as partial.

## Doing now

**PR 2 — pipeline Sarvam STT tap.** Pipeline mode pays Sarvam on every call and records
nothing, because the tap in `src/core/agents/stt/sarvam_parallel.py` builds a standalone
plugin STT that is never handed to `AgentSession`, so its `RECOGNITION_USAGE` events reach
no collector. Plan: pass an accumulator into `run_sarvam_parallel_stt`, handle
`RECOGNITION_USAGE` in the event loop that already runs there, merge the result at teardown
as a synthetic `STTModelUsage` so every raw `model_usage` row has one shape, and drop the
`stt_provider = None unless cascade` rule in `src/core/agents/session.py`.

Still outstanding from PR 0: the manual call verification, which needs a real deployment —
one inbound Exotel call and one cascade call, checking that audio flows both ways and the
transcript and usage record land.

## Done

**PR 0, step 1 — dependency bump.** `livekit-agents[cartesia,deepgram,elevenlabs,google,openai,sarvam]`
moved to `~=1.7.1` in `pyproject.toml` and `docker/requirements-agent.txt`; `uv sync` also pulled
`livekit` 1.1.13 → 1.1.15, `livekit-local-inference` 0.2.6 → 0.2.7 and `google-genai` 1.69 → 2.22.
The control image pins `livekit`/`livekit-api` separately and was left alone — it has no agents
dependency.

**PR 0, step 2 — plugin API drift.** The bump broke eight tests, all of them real drift rather
than test noise:

- Sarvam sunset `saaras:v2.5` and `saarika:v2.5` and added `saaras:v4`, so `SARVAM_STT_MODELS`
  in `src/core/model_support/speech.py` now holds `{saaras:v3, saaras:v4}`. `saaras:v3` stays
  this platform's default even though the plugin's own default moved to v4 — changing the
  transcription model on every pipeline call does not belong in a version bump.
- ElevenLabs added `eleven_v3_conversational`, which is in `ELEVENLABS_TTS_MODELS` and in
  `_ELEVENLABS_NO_SPEED_MODELS`: it is a v3 model, and the plugin now routes the whole v3
  family through the text-to-dialogue API, where `stability` is the only voice setting that
  survives.
- The OpenAI STT plugin replaced `_STTOptions.language: str` with `languages: list[str]` for
  code-switched transcription. The constructor keyword is unchanged, so `create_stt` needed no
  edit — only the three tests asserting on the private field.
- The per-model Sarvam language and mode gates in `src/core/agents/stt/lang.py` lost their real
  test subject when the v2.5 pair went. Both gates stay (the roster diverged once and can
  again) and the tests now register a deliberately narrower model in the plugin's own
  `MODEL_CONFIGS` to exercise them.

Docs updated in every place that listed these: `docs/reference/models.md`,
`docs/reference/troubleshooting.md`, `docs/api/assistant/create.md`, `docs/features.md`, plus
the field descriptions in `src/api/models/api_schemas/config/stt_config.py`.

**PR 0, step 3 — behavioural release notes checked against this repo.**

- 1.6.8 `auto-disable realtime server-side turn detection`: harmless here. The pipeline branch
  sets `turn_detection="realtime_llm"` explicitly, which `_resolve_rt_turn_detection_enabled`
  reads as "the model keeps doing turn-taking"; the realtime branch passes no VAD, which
  reaches the same answer.
- 1.7.0 `wait for final user turn during close`: the SDK now waits at session close, after our
  own `END_OF_CALL_GRACE_S` window. Additive delay at teardown, no conflict.
- The plan said to migrate the deprecated `console`/`dev` CLI to `lk agent`. **Changed:** the
  whole built-in Python CLI is deprecated in 1.7.1, `start` and `download-files` included, and
  none of it is removed yet — production launches through `python -m src.core.agents.session
  start` in `docker/Dockerfile.agent` and `docker-compose.yml`. Swapping the launch path is its
  own change with its own blast radius, and `lk agent` is a separate binary developers would
  have to install. Left as is, tracked below.

**PR 0, step 4 — gates.** `uv run python -m unittest discover -s tests` → 475 tests, OK.
`uv run mkdocs build --strict` → clean. `uv run python scripts/check_mermaid.py` → 15 diagrams,
0 broken. `uv run python scripts/check_model_allowlist.py` → no drift. `uvx ruff check` on the
touched files reports only the violations that were already there before this change.

**PR 1 — capture everything the SDK already reports.** `UsageRecord` gained the missing LLM
fields (`llm_input_tokens`, `llm_output_tokens`, `llm_input_cached_tokens`,
`llm_input_cache_creation_tokens`, `llm_input_image_tokens`, `llm_input_cached_image_tokens`,
`llm_session_duration`), the token-billed STT/TTS pairs, and three provenance fields:
`model_usage` (the raw per-`(provider, model)` list, filtered to the billable components),
`usage_schema_version` (1 = old partial rows, 2 = everything) and `sdk_version`.
`summarize_usage` folds all of them. The cached-subset invariant is documented beside the
fields, in the webhook and admin docs, and in the new `docs/reference/usage-accounting.md`.

Deviations from the plan, both deliberate:

- **Did not** move `_persist_usage` onto `ctx.make_session_report()`. That method raises
  `RuntimeError` while `RecorderIO` is still recording (`livekit/agents/job.py:395`), which
  is exactly the state teardown runs in. `sdk_version` comes from
  `livekit.agents.__version__` instead — same value, no failure mode.
- **Did not** re-bind `realtime_provider` / `session` as explicit parameters. Both are bound
  (session.py:642, 819) before `_persist_usage` is ever awaited, so the closure is already
  correct; churning it is unrelated risk.

The new fields are exposed on the end-call webhook and in all three `/admin` token analytics
aggregations, additive only. Tests went into the existing `TestSummarizeUsage` rather than a
new file, and `tests/test_livekit_lifecycle.py` now builds its fake usage record with
`UsageRecord.model_construct()` so the next added field cannot break it. One unrelated test
needed a fix: `test_mcp_docs.py` asserted that a page ranks in the top 8 of a keyword search,
and the new docs page pushed it to 9th; the search window in the test widened to 10.

Not fixed here, still zero, and now documented as such: pipeline-mode Sarvam STT (PR 2) and
realtime native transcription (PR 3).

Gates: 479 tests OK, `mkdocs build --strict` clean, 15 Mermaid diagrams parse, ruff on the
touched files reports only pre-existing violations.

## Left

**PR 2 — pipeline Sarvam STT tap.**

- Pass an accumulator into `run_sarvam_parallel_stt` and handle `RECOGNITION_USAGE` in the
  existing event loop.
- Merge it at teardown as a synthetic `STTModelUsage` so every raw row has one shape.
- Drop the `stt_provider = None unless cascade` rule in `src/core/agents/session.py`.

**PR 3 — realtime native transcription.**

- Wrap `_handle_conversion_item_input_audio_transcription_completed` to read `event.usage`
  before delegating, and feed a synthetic `STTModelUsage`.
- Assert the patched symbol exists at import so a future SDK bump fails loudly instead of
  silently recording zero.
- Applies to `realtime` mode always, and to `pipeline` whenever the STT provider is not Sarvam.

**PR 4 — durability.**

- Subscribe to `session_usage_updated` and upsert on the unique `room_name`, throttled to at
  most one write per 15 s.
- Make the teardown write an upsert too, which also removes the duplicate-key path when two
  teardown routes race.

**PR 5 — close out the tests and docs.** Most of this shipped with PR 1: the field-level
tests live in `TestSummarizeUsage`, the reference page is
`docs/reference/usage-accounting.md`, and troubleshooting has the "usage record is all
zeros" section. What is left depends on PR 2 to PR 4 landing first:

- Per-mode coverage that the earlier PRs make meaningful: pipeline + Sarvam and realtime +
  native both currently record zero STT on purpose, so the assertions only become real once
  those taps report.
- Remove the "Known gaps" section from `docs/reference/usage-accounting.md` as each gap
  closes, and update the per-mode table with it.

**Follow-up left by PR 0 — the deprecated Python CLI.**

`python -m src.core.agents.session start` (and `download-files` in both Dockerfiles) now emits
a `DeprecationWarning`; the replacement is the `lk` binary or `python -m livekit.agents`.
Nothing is broken today. Worth doing before the SDK removes the legacy CLI, and worth doing on
its own so a launch-path change is not buried in another PR.

**Later, not part of this effort — pricing.**

A `src/core/pricing/` package with an effective-dated rate table keyed by
`(component, provider, model, token_class)`, reading the raw `model_usage`. Rates stay out of
the schema so a price change needs neither a migration nor a backfill.
