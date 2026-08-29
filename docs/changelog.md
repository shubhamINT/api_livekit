# Changelog

Every release that changes platform behaviour is recorded here. The version is single-sourced in
`src/core/version.py` and reported by the API at `GET /docs` (the OpenAPI `info.version`), so you
can always tell which release a deployment is running.

The minor version goes up whenever behaviour changes in a way an operator has to know about.
Given how this platform is used, that includes anything that changes **what a caller hears**.

!!! warning "Read the breaking changes before upgrading"
    Both releases below contain breaking changes. Each one lists what to do about it.

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
