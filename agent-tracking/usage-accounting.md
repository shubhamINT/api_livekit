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

PR 8 — deliver per-model usage to webhook and API consumers. Measurement is complete; this PR
normalizes providers at write time, migrates version-2 rows, exposes per-call and per-model
usage, and documents the consumer contracts.

Still outstanding, all needing a real deployment: the PR 0 manual verification (one inbound
Exotel call and one cascade call — audio both ways, transcript, usage record) and the PR 1 /
PR 2 / PR 3 / PR 4 / PR 6 / PR 7 verification described in their sections below.

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

The new fields are exposed in the stored record and admin aggregation implementation; webhook
and ordinary-user delivery are completed by PR 8. Tests went into the existing
`TestSummarizeUsage` rather than a new file, and `tests/test_livekit_lifecycle.py` now builds its
fake usage record with `UsageRecord.model_construct()` so the next added field cannot break it. One unrelated test
needed a fix: `test_mcp_docs.py` asserted that a page ranks in the top 8 of a keyword search,
and the new docs page pushed it to 9th; the search window in the test widened to 10.

Not fixed here, still zero, and now documented as such: pipeline-mode Sarvam STT (PR 2) and
realtime native transcription (PR 3).

Gates: 479 tests OK, `mkdocs build --strict` clean, 15 Mermaid diagrams parse, ruff on the
touched files reports only pre-existing violations.

**PR 2 — pipeline Sarvam STT is recorded.** `SttUsage` (a two-field dataclass in
`src/core/agents/stt/sarvam_parallel.py`) is handed to `run_sarvam_parallel_stt`; the audio
pump adds each frame's duration to it, and teardown turns it into an `STTModelUsage` that
goes to `summarize_usage(session, extra_usage=...)`. It lands in the flat `stt_*` columns
and in the raw `model_usage` list with the same shape as a cascade STT row, so pricing needs
no per-mode branch. `stt_provider` now records `"sarvam"` on a pipeline call that ran the
tap, not only on cascade.

Changed from the plan, agreed with the user: the tap does **not** read Sarvam's own
`RECOGNITION_USAGE` event. That event carries whatever the server put in
`metrics.audio_duration` (`plugins/sarvam/stt.py:1585`), which is absent on some responses
and would record a silent zero — the exact failure this effort exists to remove. Measuring
the frames the tap pushes gives one number from one source with no branch. It can differ
slightly from Sarvam's invoice; it is never falsely zero. The `DRAIN_SILENCE_S` silence
pushed at hangup is fed from `_stop_watch`, not the pump, so it stays out by construction.

The tally is stream time, not speech time: `SpeechGate` zeroes non-speech samples in place
and returns the same frame, so gated audio still goes over the open connection and is still
counted. That is deliberate and now stated in the code and in
`docs/reference/usage-accounting.md`; an earlier line in `docs/architecture/audio-pipeline.md`
claimed the opposite and was corrected.

`_use_sarvam_stt` keeps its single existing initialisation (`session.py:663`), with the
comment extended to say why it must stay unconditional: `_persist_usage` reads it and
swallows exceptions, so an unbound name would silently zero the whole record.

Gates: 482 tests OK, `mkdocs build --strict` clean, 15 Mermaid diagrams parse, ruff on the
touched files reports only pre-existing violations.

Manual, needs a deployment: one pipeline call with `assistant_stt_model` unset or `sarvam`.
Expect `stt_provider == "sarvam"`, `stt_audio_duration` roughly the caller's speaking time,
and one `stt_usage` entry in `model_usage`. A cascade call must be unchanged.

**PR 3 — realtime native transcription is recorded.** The last unmetered component. The
OpenAI Realtime API transcribes the caller with a separate ASR model (`gpt-4o-mini-transcribe`)
and bills it on that model's own pricing, reporting the usage on every
`conversation.item.input_audio_transcription.completed` event. The plugin's handler keeps the
transcript and drops `usage`, so both `realtime` mode and `pipeline` mode without the Sarvam
tap stored zero.

`src/core/agents/stt/native_usage.py` holds the whole change: `NativeSttUsage` (the tally),
`NativeSttModelUsage` (an `STTModelUsage` subclass that also carries the audio/text split) and
`MeteredRealtimeModel`. Both OpenAI branches in `session.py` build the subclass instead of
`realtime.RealtimeModel`; teardown appends the entry to the same `extra_usage` list PR 2
introduced. `stt_provider` gains a third case, `"openai"`.

Changed from the plan, agreed with the user: **no monkeypatch.** The plan called for wrapping
the private `_handle_conversion_item_input_audio_transcription_completed` with an import-time
assert. That is unnecessary — `RealtimeSession` already emits every raw server frame as
`openai_server_event_received`, a documented public event (`realtime_model.py:869-880`,
emitted at `:1173`), and the SDK calls the public `session()` once per agent activity
(`agents/voice/agent_activity.py:1073`). Subclassing and overriding `session()` attaches the
listener with no private symbol, no assert, and no `openai.types` import: the plugin parses
events with `.construct()`, so the payload arrives as the plain dict off the wire.

Also agreed with the user: **keep the audio/text token split.** OpenAI reports
`usage.input_token_details.{audio_tokens,text_tokens}` and charges a different rate for each.
`STTModelUsage` has no field for it, so the subclass carries it into two new `UsageRecord`
columns, `stt_input_audio_tokens` / `stt_input_text_tokens` — subsets of `stt_input_tokens`,
never additional. `summarize_usage` reads them with `getattr(..., 0)`, so a plain SDK entry
still contributes zero and nothing else changed. `usage_schema_version` stays `2`: a record
written before this PR reports `0` for both, which is also what a duration-billed provider
reports.

Two deliberate behaviours: `observe()` never raises (it runs inside the plugin's websocket
read loop, where an exception would end the call over a metric), and `to_model_usage()`
returns `None` when nothing was transcribed, so a call that ran no ASR records no entry at all
rather than a zero row that reads like a missing measurement.

Gemini needed no code and is not a gap: its Live API reports no per-transcription usage
because the input audio is already inside `prompt_tokens_details`, so that spend is in the LLM
numbers. A Gemini `realtime` call is now the only configuration that stores `stt_provider =
null` by design, and the docs say so instead of listing a known gap.

The `gpt-4o-mini-transcribe` literal moved out of `session.py` into `NATIVE_TRANSCRIBE_MODEL`
beside the tally, so the model that incurs the cost and the model recorded against it cannot
drift apart.

Gates: 490 tests OK, `mkdocs build --strict` clean, 15 Mermaid diagrams parse, ruff on the
touched files reports only pre-existing violation classes (the one hit on the new file is
BLE001 on the deliberate never-raise catch).

Manual, needs a deployment:

- One `realtime` (OpenAI) call → `stt_provider == "openai"`, `stt_model ==
  "gpt-4o-mini-transcribe"`, non-zero `stt_input_tokens` with `stt_input_audio_tokens` making
  up most of it, and one `stt_usage` entry in `model_usage`.
- One `pipeline` call with `assistant_stt_model = "native"` → same.
- One `pipeline` call with Sarvam → unchanged from PR 2 (no OpenAI entry, because
  `input_audio_transcription` is `None` there).
- One `realtime` Gemini call → STT fields still `0`, by design.

**PR 4 — the record survives a worker that never reaches teardown.** `UsageRecord` was
written once, by a plain `insert()` at the end of `_flush_and_end_call`. A worker that died
mid-call — crash, OOM kill, container restart — lost every token the call had already spent,
and the end-of-call webhook found no row and silently omitted its whole `usage` block. A
second write was an error rather than an update: `room_name` is uniquely indexed, so a
duplicate `insert()` raised `DuplicateKeyError` into the blanket `except`.

The write is now incremental and idempotent. `upsert_usage_record`
(`src/core/agents/usage.py`) upserts on `room_name`, leaving `created_at` out of the update so
it keeps marking when the row first appeared. `_persist_usage(final: bool = True)` is called
by a 15 s `_usage_flusher()` loop while the call runs and once more at teardown; teardown
cancels the loop first, so a snapshot can never land after the authoritative write. An interim
write is skipped when nothing moved — the comparison excludes `call_duration_minutes`, which
grows on the wall clock and would otherwise defeat it on every tick.

`usage_finalized` (new `UsageRecord` field, also on the end-of-call webhook) separates the two
cases that now look alike: `true` is the teardown write, `false` on a call that is over means
the worker died and the counts are a floor, missing up to 15 s. `usage_schema_version` stays
`2` — nothing about what is *measured* changed.

Changed from the plan, agreed with the user: **a periodic task, not a `session_usage_updated`
subscription.** `AgentSession.on()` rejects async callbacks outright
(`livekit/rtc/event_emitter.py:159-168`), so the event version needs a sync handler that spawns
a task per event plus its own `monotonic()` throttle and in-flight guard. The event also fires
once per *metric* — STT, LLM, TTS and VAD each emit separately
(`voice/agent_activity.py:1966-1970`) — and carries nothing `session.usage` does not already
expose on demand. A sleep loop is smaller, has no SDK coupling, and picks up the Sarvam tap and
the native ASR tally, neither of which emits an SDK event at all.

Two smaller decisions: the analytics endpoints and the webhook deliberately keep including
non-finalized rows, because a live call's tokens are real usage and a partial `usage` block
beats today's omitted one; and `upsert_usage_record` takes the built document rather than
living inside `session.py`, because `_persist_usage` is a closure inside `entrypoint` that no
test can reach.

One unrelated comment was wrong and is fixed: `src/api/routes/admin.py` still called
`total_stt_audio_duration` cascade-only, untrue since PR 2 filled it in pipeline mode.

Gates: 494 tests OK, `mkdocs build --strict` clean, 15 Mermaid diagrams parse, ruff on the
touched files reports the same 241 pre-existing violations as before the change.

Manual, needs a deployment:

- One normal call → exactly one row for that `room_name`, `usage_finalized: true`, numbers
  unchanged from a pre-PR call.
- The same call queried while it is still up (after ~20 s) → the row already exists with
  `usage_finalized: false` and non-zero LLM tokens.
- Kill the agent container mid-call → the row stays, `usage_finalized: false`. Before this
  there was no row.
- The end-of-call webhook carries `usage.usage_finalized: true`.

**PR 6 — the worker no longer launches through the deprecated Python CLI.** The follow-up PR 0
deferred. `cli.run_app` in 1.7.1 only emits a `DeprecationWarning` and hands off to
`livekit/agents/cli/_legacy.py`, which its own docstring says will be removed in a future
release; production launched through it from three places (`docker/Dockerfile.agent`,
`Dockerfile`, `docker-compose.yml`).

The supported replacement, `python -m livekit.agents start <entrypoint>`, discovers a
module-level `AgentServer` rather than taking a `WorkerOptions`. New root file `agent_run.py`
holds that server, built by `AgentServer.from_server_options(WorkerOptions(...))` — every option
value moved across unchanged — plus `_worker_load`, which existed only to be its `load_fnc`.
`src/core/agents/session.py` is now only the job handler; its `__main__` block and two imports
are gone. Build-time `download-files` became `python -m livekit.agents download-files`, which
walks the whole `livekit.plugins` namespace instead of whatever our module happened to import:
six plugin packages, the same set, and `livekit.agents.inference` registers no plugin so the
local VAD and turn-detector weights were never part of that step.

Two decisions worth keeping:

- **The entrypoint is a root-level file, not `session.py`.** `cli/discover.py` walks parents only
  while each holds an `__init__.py`, and `src/` has none — it is a namespace package. Pointing the
  CLI at `src/core/agents/session.py` would import it a second time under the bare name `session`,
  giving one process two copies of the module. `agent_run.py` sits beside `server_run.py` and
  `sip_dispatcher_run.py`, which is also where the CLI's own default-path list expects it.
- **`dev` still runs through the deprecated CLI, on purpose.** `agent_run.py` keeps an
  `if __name__ == "__main__": cli.run_app(server)` block, so the developer command is
  `uv run agent_run.py dev` and only production is off the legacy path. The supported alternative,
  `lk agent dev`, is a separate binary every developer would have to install; that migration is
  what is left here, and nothing forces it until the SDK deletes `_legacy.py`.

The worker config also had to leave `session.py` for a practical reason: several test modules
import the job handler, and building an `AgentServer` at import of *that* file would make every
one of them build a worker.

`tests/test_agent_entrypoint.py` covers the two things that break only at container start — the
CLI finding a global named `server` that is an `AgentServer`, and `agent_name` still being
`api-agent` — plus the three `_worker_load` boundaries.

Gates: 499 tests OK, `mkdocs build --strict` clean, 15 Mermaid diagrams parse, ruff on the
touched files reports only pre-existing violations. Verified locally that
`get_import_data(Path("agent_run.py"))` resolves to `agent_run:server`, that
`python -m livekit.agents start agent_run.py` raises no `DeprecationWarning` under
`-W error::DeprecationWarning`, and that the new `download-files` exits 0 over all six plugins.

Manual, needs a deployment:

- `docker compose --profile agent build` succeeds, including the `download-files` layer.
- The rebuilt agent container registers and takes one inbound Exotel call and one cascade call —
  audio both ways, transcript written, a `usage_records` row with `usage_finalized: true`. This
  doubles as the PR 0 through PR 4 verification still outstanding above.
- `docker logs` on the agent container shows no `DeprecationWarning` about the built-in CLI.

**PR 7 — cascade Sarvam STT is measured, not reported.** With PR 6 landed the tracking file
held only a developer-setup item and out-of-scope pricing, so every configurable provider was
audited against the installed plugins to check the goal actually held.

TTS came back clean. Every TTS metric is computed by the SDK base classes from the text pushed
and the frames decoded (`agents/tts/tts.py:326-367` chunked, `:683-726` streaming), never from a
provider response — including for the two TTS classes written in this repo
(`src/services/elevenlabs/v3_nonstream.py`, `src/services/mistral/tts.py`), which subclass
`tts.ChunkedStream` and inherit it. Two documentation claims were wrong and are fixed:
`tts_input_tokens` / `tts_output_tokens` are structurally always `0` for every provider this
platform can build (only `plugins/openai/tts.py:319` calls `_set_token_usage`, and `create_tts`
never constructs `openai.TTS`), and for ElevenLabs and Mistral the character count is the sum of
tokenized sentence lengths, because the SDK wraps both non-streaming classes in a
`StreamAdapter` that synthesizes sentence by sentence.

Cascade Sarvam STT carried the exact defect PR 2 removed from pipeline mode. `create_stt`
handed `AgentSession` a raw `sarvam.STT`, whose only usage source is
`metrics.get("audio_duration", 0.0)` off the transcript payload
(`plugins/sarvam/stt.py:1574-1587`) — a server field absent on some responses, with no local
frame accounting anywhere in that file — and which emits no usage event at all when the
transcript came back empty (`stt.py:1568-1571`).

`src/core/agents/stt/cascade_usage.py` holds the fix: `CascadeSttUsage` (the tally) and
`MeteredSarvamSTT`. `DynamicAssistant.stt_node` sums every frame the session hands the STT
stage, and the entry reaches `summarize_usage` through the same `extra_usage` list PR 2 and PR 3
already use.

The design decisions worth keeping:

- **The plugin's metric is dropped, not zeroed.** Cascade STT lives *inside* the
  `AgentSession`, unlike the pipeline tap, so its entry already reaches the collector. The
  collector creates an `stt_usage` entry from the first metric it sees and `summarize_usage`
  sums every entry, so a zeroed metric would leave a second row beside ours and the record would
  report the audio twice. `tests/test_cascade_config.py::TestSummarizeUsage` asserts both the
  single-entry result and the doubling it prevents.
- **The suppression is on `emit`, because there is no seam before the monitor.**
  `RecognizeStream.__init__` tees its event channel and starts `_metrics_monitor_task` at
  construction (`agents/stt/stt.py:384-388`), so anything wrapping the object `stream()` returns
  sees the event only after `STTMetrics` was built. The monitor reports by calling
  `self._stt.emit("metrics_collected", ...)` (`stt.py:540`), and `emit` is public
  `rtc.EventEmitter` — the same preference for a public seam that PR 3 followed.
- **Rejected: rewriting `audio_duration` on the emitted metric.** It leaks the tail. The rewrite
  only fires when the plugin emits, which needs a non-empty transcript, so a quiet final minute
  reports nothing. Recovering it needs a flush at stream close, and `_flush_and_end_call` never
  calls `session.aclose()` before `_persist_usage`, so that flush would land after the
  authoritative write — and PR 4's 15 s snapshots need the number readable at arbitrary instants
  regardless. A running tally satisfies both.
- **Counting in `stt_node`, not in the STT object.** `Agent.stt_node` is a documented override
  that receives every frame; the frames only reach a `RecognizeStream` through SDK-private
  plumbing. The cost: overriding it disables STT-pipeline reuse across agent handoffs
  (`agents/voice/agent_activity.py:917-918` gates reuse on
  `type(agent).stt_node is Agent.stt_node`). This runtime calls `session.start` once and never
  hands off, so that is free today — recorded in the code so the coupling is not a surprise.

**Only Sarvam is wrapped** *(decided with the user after the audit)*. Cartesia and deepgram
`nova-*` count frames themselves, and nova additionally tops its figure up with the connection's
wall-clock lifetime (`plugins/deepgram/stt.py:713-727`) — closer to Deepgram's invoice than a
frame count would be, so replacing it would make the number worse. `openai` is the only STT
provider that reports billing tokens and must not be suppressed at all. Deepgram
`flux-general-*` and elevenlabs flush their 5 s usage collector but never flush again at stream
close, losing up to 5 s per stream; that is an undercount with a known ceiling, in the
operator's favour, and never zero — documented rather than worked around.

**`MeteredSarvamSTT.provider` returns `"sarvam"` lowercase**, where the stock plugin returns
`"Sarvam"` and the pipeline tap already stored `"sarvam"`. Pricing keys on `(provider, model)`
and should not need two spellings for one vendor. This is a change to stored data shape, so the
docs now also state the general rule: `provider` in `model_usage` is whatever the plugin calls
itself and is not normalized — vendor casing for cartesia/deepgram/elevenlabs, and a *hostname*
for the OpenAI STT plugin, which returns its client's base-URL netloc
(`plugins/openai/stt.py:333-334`). The reference page's example JSON showed a lowercase
`"cartesia"` that no real record contains; that is corrected.

**OpenAI `use_realtime: false` is now a 422, except on `whisper-1`** *(decided with the user)*.
The batch REST path discards the server's usage entirely, and every OpenAI STT model but
`whisper-1` is billed per token — such a call transcribes normally and stores zero STT spend.
`whisper-1` is duration-billed and the batch path computes duration locally, so it is the one
model the pairing is safe for; a blanket block would have been wrong. `OPENAI_STT_DURATION_BILLED_MODELS`
lives in `src/core/model_support/speech.py` so the API validator and `create_stt` read one list,
and the runtime side warns and forces streaming rather than refusing — a stored row must not
start failing calls over a metric.

`usage_schema_version` stays `2`: nothing about *what* is measured changed.

Gates: 514 tests OK, `mkdocs build --strict` clean, 15 Mermaid diagrams parse, ruff on the
touched files reports only pre-existing violations.

Manual, needs a deployment:

- One cascade call with `assistant_stt_model` unset or `sarvam` → `stt_provider == "sarvam"`,
  `stt_audio_duration` ≈ the caller's stream time, and **exactly one** `stt_usage` entry in
  `model_usage`, with lowercase `"provider": "sarvam"`.
- The same call queried at ~20 s → the snapshot already carries a growing non-zero
  `stt_audio_duration`.
- A cascade call where the caller says nothing intelligible → non-zero `stt_audio_duration`,
  where the old code stored `0`.
- One cascade cartesia call and one deepgram nova call → unchanged, one `stt_usage` entry each,
  providers still `"Cartesia"` / `"Deepgram"`.
- One pipeline call and one realtime call → identical to PR 2 / PR 3 behaviour.

**PR 8 — per-model usage attribution reaches its consumers.** `model_usage` is now the stable
source of per-(component, provider, model) billing attribution outside MongoDB:

- `summarize_usage` normalizes providers to lowercase and maps `api.openai.com` plus OpenAI
  subdomains to `openai`; schema version 3 records that shape.
- `scripts/normalize_model_usage_providers.py` dry-runs by default and migrates only version-2
  rows with `--apply`.
- The end-call webhook includes `model_usage`, `sdk_version`, token totals, call metadata, and
  provider metadata.
- Users can read one owned call at `/call/records/{room_name}/usage`, flat token totals at
  `/analytics/tokens/summary`, and per-model totals at `/analytics/tokens/by-model`.
- Super-admins can read per-model totals at `/admin/analytics/tokens/by-model`.
- Shared dependency-free aggregation builders keep user and admin grouping semantics aligned;
  non-finalized rows remain included.

The raw SDK metrics remain intact. Only the dumped `provider` key is normalized, and Vertex AI
remains distinct from Gemini because they may bill separate accounts.

## Left

**PR 5 — closed, nothing left to do.** Every item shipped inside the PR that needed it: the
field-level tests in `TestSummarizeUsage`, the per-mode coverage (PR 2
`tests/test_transcript_coalescer.py::TestSarvamUsageTally`, PR 3
`tests/test_native_stt_usage.py`, PR 4 `tests/test_cascade_config.py::TestUpsertUsageRecord`),
the reference page `docs/reference/usage-accounting.md` — whose "Known gaps" section PR 3
emptied — and the troubleshooting rows.

**Follow-up left by PR 6 — the developer `dev` command.**

`uv run agent_run.py dev` still goes through the SDK's deprecated Python CLI and warns. The
replacement is `lk agent dev`, a separate binary each developer installs, so it is a developer-
setup change rather than a code change. Nothing forces it until the SDK deletes
`livekit/agents/cli/_legacy.py`; production no longer depends on that module.

**Pricing follow-up — implemented.** New usage records now calculate estimated AI-provider
cost from a versioned static public-PAYG rate table. The estimate is USD-only, excludes
telephony/recording/LiveKit infrastructure, and remains partial when a provider/model has no
verified public rate. Historical rows are not backfilled.

A `src/core/pricing/` package with a versioned rate table keyed by
`(component, provider, model, token_class)` reads raw `model_usage`. Rate definitions stay out
of the usage schema; `pricing_schema_version` records calculation semantics without requiring
a rate migration or historical backfill.
