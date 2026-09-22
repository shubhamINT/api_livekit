# Changelog

Every release that changes platform behaviour is recorded here. The version is single-sourced in
`src/core/version.py` and reported by the API at `GET /docs` (the OpenAPI `info.version`), so you
can always tell which release a deployment is running.

The minor version goes up whenever behaviour changes in a way an operator has to know about.
Given how this platform is used, that includes anything that changes **what a caller hears**.

!!! warning "Read the breaking changes before upgrading"
    Releases below contain breaking changes. Each one lists what to do about it.

---

## 1.5.0

Gemini 3.8 Live, a new Gemini default, and a pricing sweep that changed which Deepgram models
this platform accepts.

### The default Gemini Live model is now `gemini-3.8-live`

`livekit-agents` moves from `~=1.7.1` to `~=1.8.2`, which is where Google's 3.8 Live line
arrives. Two new models are accepted in `realtime` mode:

- **`gemini-3.8-live`** — stable, the line Google names for low-latency voice agents, and the
  new default.
- **`gemini-3.8-live-extended-thinking`** — reasons before it speaks. Slower first word, async
  function calling only. Selectable, never forced.

**An assistant that stores no `assistant_llm_config.model` moves from
`gemini-2.5-flash-native-audio-preview-12-2025` to `gemini-3.8-live` on its next call.** Voices
are unchanged, so no stored `voice` breaks. Pin the old id explicitly if you need the previous
behaviour.

`gemini-3.1-flash-live-preview` stays available and is no longer warned about: its mid-session
limitation (no farewell, no silence re-prompt) was a plugin bug that `livekit-plugins-google`
1.8.2 fixes. Deployments still running an older worker see the old symptom — see
[Troubleshooting](reference/troubleshooting.md#gemini-live-mid-session-updates).

### Breaking: `gemini-live-2.5-flash-native-audio` is now rejected

That id runs on Vertex AI only. This platform authenticates with `GOOGLE_API_KEY`, so the
plugin raised while building the model and the job died *after* the call connected — a
connected call with no agent behind it. It is now a `422` at create and update.

**If a stored assistant holds it**, the next update of that assistant fails validation. Run
`uv run python scripts/audit_assistant_models.py` to list them, `--apply` to clear the field so
they fall back to the default.

### Breaking: the Deepgram STT allowlist is the priced set

Deepgram no longer publishes a price for the `nova-2`, `enhanced`, `base` and hosted-`whisper`
tiers. This platform prices every call it accepts — an accepted model with no rate bills as
zero, which reads like a free call rather than an unpriced one — so those ids are now a `422`.

Accepted: `nova-3`, `nova-3-general`, `nova-3-multilingual`, `flux-general-en`,
`flux-general-multi`.

**If a stored assistant holds a retired tier**, the same audit script finds it:
`uv run python scripts/audit_assistant_models.py` now sweeps `assistant_stt_config.model` as
well, and `--apply` clears it so the assistant falls back to `nova-3`.

### Every provider now has a rate

Calls used to come back `pricing_complete: false` whenever they touched a provider the rate
table did not carry. Added: Gemini Live (all four accepted models), Cartesia TTS and STT,
Mistral TTS. Two carry a caveat, stated in `src/core/pricing/rates.py` beside the numbers:

- **Cartesia is derived**, not quoted — it publishes plan tiers rather than a per-unit price,
  so the rate comes from the $49 Startup tier. Replace it with your contract rate if you have
  one.
- **Deepgram is priced at its regular rate**, not the lower promotional rate its page currently
  shows, so the estimate survives the promotion ending.

Gemini Live prices are listed per model in
[Models & Providers](reference/models.md#gemini-live-pricing).

---

## 1.4.0

Meeting-call documentation release, plus one behaviour change to how a failed meeting setup is
reported.

### A meeting call that fails during setup now sends the end-call webhook

`POST /meeting_call/join` creates a LiveKit room, a call record, and two agent dispatches. If
anything after the room creation failed, the API cleaned the room up but finalized the call record
without the assistant, so the end-call webhook resolved no URL and silently did not fire. A client
whose setup failed received `500` and then nothing — no webhook, while every other call type reports
its own failure.

The abandon path now carries the assistant through, so the webhook fires with the failed call
record. **If you register `assistant_end_call_url` and handle meeting calls, you will start
receiving end-call webhooks for setups that failed before the call ever started.** They carry
`call_status: "failed"` and the reason `Meeting call setup failed`. No action is needed if your
handler already branches on `call_status`.

### Documentation: the meeting connector contract

[Build a Meeting Connector](guides/meeting-connector.md) is a new guide, in a new **Guides**
section, documenting the contract the meeting side implements: the dispatch name, the job metadata,
the single mixed audio track, the `lk.publish_on_behalf` match, the four lifecycle events, and the
two rules that decide whether the meeting can hear the assistant at all — subscribe visibly, and
mix the assistant's tracks rather than picking one. It ends with a walkthrough of building a
connector for a platform other than Google Meet.

[Google Meet Call Architecture](architecture/meeting-calls.md) gains a census of how many workers,
participants and audio tracks each call type puts in a LiveKit room, the mechanism of the audio
path in both directions, and the behaviour that was previously undocumented: the agent-track
subscription diagnostic, the third readiness-recovery path, and that recording egress starts at
session setup rather than at connector readiness.

---

## 1.3.0

Usage observability and deployment-maintenance release. This release keeps the call behavior and
provider integrations documented in 1.2.0, but changes usage payloads, usage attribution, pricing
visibility, and the supported worker launch path.

### Usage and pricing are now available in assistant call logs

`GET /assistant/call-logs/{assistant_id}` now includes a nested `usage` object for each call when a
usage record exists. The object includes flat totals, per-provider/model `model_usage`, estimated
provider cost, pricing completeness, and the `usage_finalized` state. The endpoint remains
backward-compatible at the HTTP level, but clients that deserialize a fixed response schema must
allow the new fields and the nullable `usage` object.

The same usage contract is available through the per-call usage endpoint, end-call webhook, and
analytics endpoints. The canonical field definitions are in [Usage accounting](reference/usage-accounting.md)
and [Assistant call logs](api/assistant/logs.md).

### Per-model usage attribution

New usage records retain one entry per billable `(provider, model)` pair in `model_usage`. This
prevents a call that changes models from losing attribution behind a blended total. Provider names
are normalized to lowercase billing keys at write time; OpenAI hostnames normalize to `openai`.

New records use `usage_schema_version=3`. Existing version 2 records retain their old provider
spellings until the explicit migration is run:

```bash
uv run python scripts/normalize_model_usage_providers.py
uv run python scripts/normalize_model_usage_providers.py --apply
```

The migration changes only version 2 usage records and sets them to version 3. Version 1 records
were written before per-model attribution existed and cannot be reconstructed from stored data.

### Estimated provider cost

New usage records expose `estimated_cost_usd`, `pricing_schema_version`, `pricing_complete`, and
`unpriced_model_usage`. These are estimates from versioned public PAYG rates, not invoices. A
partial estimate is explicit: `pricing_complete=false` and unknown entries appear in
`unpriced_model_usage`; unknown usage is never silently reported as zero.

### Usage capture is more complete

- Cascade Sarvam STT duration is measured from the audio tap rather than inferred from an absent
  SDK metric.
- Pipeline Sarvam STT tap usage is included in the usage record.
- OpenAI Realtime ASR usage is captured separately from realtime model usage when the provider
  reports it.
- SDK-reported token fields are preserved instead of being reduced to only flat totals.
- Usage snapshots can survive a worker failure before normal teardown. Treat
  `usage_finalized=false` as an incomplete current snapshot, not as a final bill.

### Worker launch path

Production Docker workers now launch through the supported LiveKit CLI:

```bash
python -m livekit.agents start agent_run.py
```

`uv run agent_run.py dev` remains a local development compatibility path and uses the SDK's
deprecated Python CLI. Production deployments must use the Docker command above.

### Dependency and model alignment

`livekit-agents` is upgraded to `1.7.1`, and provider/model rosters are synchronized with the
runtime factories and validation tables. Before adding or restoring a model, run
`uv run python scripts/check_model_allowlist.py`; do not copy a model name from an old release or
from memory. See [Models & Providers](reference/models.md) and [Compatibility Matrix](reference/compatibility.md).

### Breaking changes and upgrade steps

1. **Usage response shape is additive but not schema-neutral.** Update strict clients to accept
   `usage: null`, `model_usage`, pricing fields, `usage_schema_version`, and
   `usage_finalized` in assistant call logs, webhooks, and usage responses.
2. **Provider attribution is normalized for new records.** Consumers must use normalized provider
   keys rather than relying on historical plugin spellings. Run the version 2 normalization
   migration if consistent historical analytics are required.
3. **Pricing is not an invoice.** Do not use `estimated_cost_usd` as a payment or billing total;
   check `pricing_complete` before treating it as complete.
4. **Worker startup command changed in production.** Rebuild the agent image and use
   `python -m livekit.agents start agent_run.py`; do not use the deprecated Python CLI for
   production.
5. **Model validation follows the 1.7.1 roster.** Run the allowlist audit before deployment and
   repair stored assistants whose model is no longer supported.

### Documentation and MCP

The MkDocs site, `/documentation` endpoint, and read-only `/mcp` server all read the same `docs/`
source. The MCP server reports version `1.3.0`; agents should use `search_docs` followed by
`get_doc`, prefer endpoint/reference pages over this historical changelog, and state when a value
is versioned or only an estimate.

---

## 1.2.0

Outbound Exotel answer-to-speech release. Callers reported 5-6s of silence after picking up an
outbound call, sometimes much longer — this release fixes the actual cause, not just the symptom.

### A dropped `call_answered` message could silence the whole call

The agent's listener for the SIP bridge's `call_answered` data message was registered *after*
`session.start()` returned. `session.start()` can itself take 10s+ (the inbound-context webhook,
tool loading, TTS prewarm), and a LiveKit `data_received` event is a plain synchronous dispatch
with no buffering or replay — if the callee answered while the agent was still booting, the
message arrived with nobody listening yet, and was gone for good. The only recovery was the
60-second gate timeout, meaning a call could connect and the agent could stay silent for up to a
minute in the worst case, not just the reported 5-6s.

The listener is now registered before `session.start()` runs, closing the window entirely — the
room cannot receive any data message before this point, so the fix is unconditional, not a race
that's merely less likely to lose.

### The post-answer wait no longer ignores a hang-up

Before speaking, the agent waits for `call_answered`, then for recording to start, then a short
fixed RTP/egress warmup pause. If the callee answered and immediately hung up, none of that used
to notice — the agent kept running the full sequence (including a live recording-start API call)
for up to ~13s, concurrently with the call's own teardown already tearing down the same room and
session state.

That sequence is now raced against the participant-disconnected signal: a hang-up during the wait
aborts it immediately and skips the greeting, instead of running to completion after the call is
already over.

### Slow calls now log where the time went

Every outbound Exotel call logs one `[EXOTEL] phase timing` line breaking the wait down into
`gate_wait`, `recorder_wait` and `warmup` — so if a future call is unusually slow, the log shows
which phase caused it instead of it looking like an unexplained one-off.

The fixed post-answer warmup pause (`EXOTEL_RTP_WARMUP_SLEEP_SEC`) and the bridge's own 0.5s
mixer-settle pause before publishing `call_answered` are unchanged — both remain load-bearing and
are not addressed by this release.

---

## 1.1.0

Concurrency and call-setup release. 1.0 worked well at low volume and came apart at 12–14
simultaneous calls; this release is about holding that load and about what the caller experiences
while a call is being set up.

### The caller no longer hears silence after pickup

Inbound calls used to be answered as soon as the *media bridge* was ready. Everything the agent
still had to do after that — the inbound-context webhook (up to 10s), tool loading, session
start — played out as dead air on the caller's phone. Outbound never had this problem, because
the agent boots while the phone is ringing.

Inbound now behaves the same way:

- `100 Trying` is sent immediately on INVITE. Previously Exotel saw no response at all for the
  whole setup window.
- `180 Ringing` is sent once the media path is up, and the caller hears ringing while the agent
  boots.
- `200 OK` is sent when the agent reports it is ready to speak, or after
  `INBOUND_MAX_RING_SECONDS` (default 15), whichever comes first. **The call is never dropped
  because the agent was slow** — the deadline answers it regardless.

The agent signals readiness over the room's data channel after `session.start()`, which is after
the inbound-context webhook has already returned. If that message never arrives — an older agent
build, say — the bridge falls back to the agent's audio track appearing, and then to the deadline.

Set `INBOUND_RING_UNTIL_AGENT_READY=false` to restore the 1.0 behaviour.

Two related bugs fixed on the way:

- A caller who hung up while the platform was still setting up was **answered anyway**. There was
  no cancellation check between the last checkpoint and the 200 OK, so the CANCEL was recorded and
  ignored, producing a protocol violation and a spurious call record. The ring wait now watches
  for it and replies `487 Request Terminated`.
- The silent-agent watchdog was armed *before* the call was answered, and would force-end a call
  15 seconds later. With ringing, that fired on healthy calls. It is now armed after the answer,
  which is what its grace period was always measuring from.

### Concurrency caps are per call type

One counter used to govern every call type, so a burst of web sessions could give phone callers a
busy tone — even though a web call costs a fraction of a phone call (no bridge process, no RTP
port, and a text-only web call has no TTS, STT or VAD at all).

| Setting | Default | Governs |
|---|---|---|
| `MAX_CONCURRENT_JOBS` | `12` | telephony: inbound, outbound, passthrough |
| `MAX_CONCURRENT_WEB_CALLS` | `40` | web calls |
| `MAX_CONCURRENT_SESSIONS` | `48` | hard ceiling across everything |
| `MAX_CONCURRENT_INVITE_SETUPS` | `24` | inbound INVITEs in setup at once (not a cap on live calls) |

`MAX_CONCURRENT_JOBS` keeps its name and its meaning as the telephony cap, so a deployment that
already sets it keeps the behaviour it was tuned for.

!!! note "The web default is provisional"
    `MAX_CONCURRENT_WEB_CALLS=40` is **not** derived from a measured agent-session footprint —
    the only figure available is a ~238 MiB import floor per agent job process, before audio
    buffers, model state and provider connections. Run a load test, read the agent container's
    steady-state RSS per session with `docker stats`, and raise these with evidence.

The live-session count is now a single aggregation served by a new
`(call_status, call_type)` index on `call_records`. It previously ran as a full collection scan on
every inbound INVITE and every web-call request, growing with total call history rather than with
the number of calls actually in progress.

### Load fixes

- **Inbound bridges run one process per call.** They previously ran one thread per call inside the
  SIP dispatcher, sharing LiveKit's process-wide FFI singleton, whose event dispatch walks every
  subscriber under a single lock on a single thread. Past roughly half a dozen calls the agent's
  audio stopped reaching the caller — while the S3 recording, which is server-side egress,
  captured both sides perfectly. Outbound had already been moved to process-per-call for this
  reason; inbound had not.
- **Bridges launch from a forkserver.** Under `spawn` each bridge re-imported the whole scientific
  stack; `scipy.signal` alone costs seconds per import, and a dozen at once starved the
  dispatcher's event loop and pushed memory toward the OOM killer. Measured over 8 concurrent
  bridges: startup 1.45s → 0.68s each, resident memory 869 MiB → 605 MiB.
- **Audio no longer crosses between calls.** Three separate causes: the RTP socket adopted the
  first sender as its peer (it now accepts only the SDP-negotiated endpoint), the port pool
  recycled the lowest port after 5 seconds (now round-robin with a 30 second cooldown), and the
  call registry was keyed on the wire-supplied SIP Call-ID and silently overwrote on collision
  (now namespaced by peer, duplicates refused).
- **A dispatcher restart no longer cuts live calls.** Startup used to fail every active call
  record unconditionally, which was only safe while the dispatcher owned every call. It now asks,
  per record, whether the LiveKit room still exists.
- **The concurrency cap actually holds under a burst.** The check and the reservation were
  separated by an `await`, so concurrent callers all saw the same pre-burst count and all passed.
- **Port exhaustion answers `486` instead of hanging.** It used to raise out of an unawaited task,
  leaving the INVITE with no response at all and the caller on dead air until Exotel timed out.
- **The agent worker measures its own load.** It used the SDK default, which averages CPU across
  the whole machine, so a busy SIP dispatcher on the same host silently stopped the worker
  accepting jobs and calls connected with no agent behind them.
- **Log lines are attributed to the right call.** The room context was a module global that
  concurrent calls overwrote, which is why these failures were so hard to diagnose from logs.

### Documentation

- Added `scripts/check_mermaid.py`, which validates every Mermaid diagram in the docs.
  `mkdocs build --strict` cannot do this — diagrams are rendered in the reader's browser, so a
  broken one builds and deploys clean and then shows a red error box on the live site. The
  checker catches both diagrams that fail to parse and diagrams that parse but render wrong
  (a literal `\n` in a label, which is what shipped on the documentation home page).
- Fixed the two diagrams it found.

### Breaking changes

**`POST /get_token` (web call) can now return `503`.** Web calls were previously never throttled.
Clients must handle a capacity rejection. Raise `MAX_CONCURRENT_WEB_CALLS` if you see it sooner
than you expect.

**The default RTP port range moved from `31000-31100` to `41000-42000`**, out of the
`10000-40000` band a self-hosted `livekit-sip` uses — a co-hosted collision there sends audio to
whichever service bound the port last. Deployments that set `SIP_BRIDGE_PORT_RANGE_*` or
`RTP_PORT_*` are unaffected. Everyone else must **open the new UDP range in their firewall before
deploying**, or all audio breaks.

**Inbound calls are answered later**, by design — see the ringing section above. If anything in
your stack measured call setup from the 200 OK, it now measures from a later point.

### Upgrade steps

1. Open the new RTP UDP range in your firewall if you rely on the default.
2. After deploying, clear queue rows stranded by the stuck-item sweep's new `dispatched_at`
   filter. Rows already in `dispatching` from before the upgrade have a null `dispatched_at`, and
   MongoDB's `$lt` does not compare across BSON types, so they would never be recovered:

    ```javascript
    db.outbound_call_queue.countDocuments({status: "dispatching", dispatched_at: null})
    db.outbound_call_queue.updateMany(
      {status: "dispatching", dispatched_at: null},
      {$set: {status: "pending"}})
    ```

3. Confirm your client handles `503` from `POST /get_token`.
4. Run a load test and set `MAX_CONCURRENT_WEB_CALLS` / `MAX_CONCURRENT_SESSIONS` from the
   measured agent memory footprint.

---

## 1.0.0

The platform as it stood before the 1.1 concurrency work: assistants in three modes, outbound and
inbound telephony over Exotel and Twilio, web calls, passthrough, tools, an audio library and
analytics.

### Assistant modes and the model layer

- **Cascade mode** — a true three-stage pipeline (plugin STT → non-realtime OpenAI Responses LLM →
  plugin TTS), alongside the existing `pipeline` (half-cascade) and `realtime` modes.
- **STT provider selection** — chosen the same way as TTS, via `assistant_stt_model` and
  `assistant_stt_config`, with Sarvam, Cartesia, Deepgram, ElevenLabs, OpenAI and the native
  path.
- **Model-specific parameters are gated before the call.** `temperature`, `reasoning_effort` and
  `verbosity` are only accepted by some models, and OpenAI answers a wrong pairing with a 400 on
  *every* LLM turn — so the call connects and the assistant never speaks. Configuration is now
  validated in four gates, cheapest first, ending in a live probe against the real model.
- **A retired model can no longer validate clean.** Three `*-chat-latest` aliases were retired
  upstream while assistants still held them; the allowlist is now checked against what the
  account actually serves.

### Calls

- **Inbound context strategies** — a webhook called at call setup to enrich the assistant's
  prompt with caller context.
- **Passthrough mode** — a web user connected directly to a phone caller, with no AI agent.
- **Web calls** in voice + text, plus opt-in `text_only` for a pure chatbot with no
  mic, TTS, STT or recording.
- **Prerecorded greetings** from a reusable audio library, played instead of generating the
  greeting with the model.
- **SIP `CANCEL` handling** — a caller who hung up before the answer previously left the INVITE
  running, so the call was answered anyway and an agent dispatched for an abandoned call.

### Breaking changes in 1.0

These shipped incrementally and are collected here for reference: `assistant_llm_mode` was
renamed as part of the cascade work; `assistant_llm_config` began merging on `PATCH` rather than
being replaced wholesale; `preferred_languages` stopped being used as a language code; provider
keys are redacted from error responses; and the inbound-context webhook timeout default rose
to 10s.
