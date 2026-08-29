# Troubleshooting

Symptom first, then cause, then the command that proves it. Every entry here is a failure this
platform has actually produced.

The recurring one is worth naming up front, because it accounts for most "the assistant is
broken" reports and it looks like nothing at all from the outside:

!!! danger "The silent call"

    The call connects. The caller hears the line open and then nothing — no greeting, no
    reply, no error. The call record is `completed` with a normal duration.

    Cause: OpenAI rejected the LLM request. Not once — **on every turn**, because the request
    body is the same every time. The rejection is not retryable, so the agent never speaks and
    the call runs until the caller hangs up.

    What makes it hard: the cascade LLM talks to OpenAI over a WebSocket, and a rejection
    arrives as an error frame carrying no detail:

    ```
    livekit.agents._exceptions.APIStatusError: message='There was an issue with your request.
    Please check your inputs and try again', status_code=-1, retryable=False
    ```

    `status_code=-1` means there was no HTTP status — that is the tell. No parameter name, no
    model name, nothing to act on.

    **The fix is one command:**

    ```bash
    uv run python scripts/replay_cascade_request.py <assistant_id>
    ```

    It rebuilds the exact payload the runtime builds — same model, same knobs, same tool
    schemas — and posts it over HTTPS instead of the WebSocket. Sometimes that alone is the
    answer, because HTTPS returns the parameter name:

    ```
    Unsupported value: 'reasoning.effort' does not support 'none' with this model.
      [param: reasoning.effort]
    ```

    Sometimes it does not. When OpenAI names no parameter, the script **bisects automatically**
    — re-sending with one knob removed at a time until it can name the offender:

    ```
    OpenAI refused the request (HTTP 400):
      There was an issue with your request. Please check your inputs and try again

    No parameter named, so bisecting automatically — one knob removed at a time:
      without temperature=0.5: still refused
      without service_tier='flex': ACCEPTED without it
      without tool_choice='auto': still refused
      without parallel_tool_calls=False: still refused

    Offending knob(s): service_tier
    Clear them with a PATCH sending each as null:
      PATCH /assistant/update/0a687f1e-…
      {"assistant_llm_config": {"service_tier": null}}
    ```

    That transcript is a real one — see the `service_tier` entry below.

---

## The call connects and the assistant never speaks

### 1. Check whether the model still exists

The most common cause, and the one that arrives without anyone changing anything: OpenAI
retired the model. Three `*-chat-latest` aliases were retired on 2026-06-19, and every
assistant holding one kept passing validation and then answered calls with silence.

```bash
uv run python scripts/check_model_allowlist.py     # is our allowlist still true?
uv run python scripts/audit_assistant_models.py    # which stored assistants are affected?
```

The first compares every allowlisted model against what your OpenAI account can actually serve
and exits non-zero on any mismatch — worth running after each `livekit-agents` bump and before
editing any model list. The second lists stored assistants whose model this deployment cannot
run, and with `--apply` clears the model field so those assistants fall back to the documented
default (`gpt-4.1` in cascade, `gpt-realtime-1.5` in pipeline/realtime).

New assistants cannot be saved with such a model: `POST /assistant/create` asks OpenAI whether
it serves the model before storing it, and answers `422` if not.

### 2. Check the worker log for the line that names the config

`create_llm` logs this immediately before the first LLM turn:

```
Cascade LLM built | assistant=asst_9f2 | model=gpt-5-mini | has_tools=True |
knobs={'reasoning': Reasoning(effort='none'), 'service_tier': 'flex'} |
if every turn fails: uv run python scripts/replay_cascade_request.py asst_9f2 --bisect
```

Grep the room's logs for `Cascade LLM built`, `Dropping ` and `strict schema off`. Between them
they show the model, every knob that reached OpenAI, every knob that was dropped and why, and
each tool whose schema had to be relaxed.

If the model is off the supported list you also get:

```
WARNING  Cascade assistant asst_9f2 runs model 'gpt-5.2-chat-latest', which is not on the
         supported list. If this call connects and the assistant never speaks, that is why …
```

### 3. Knobs that a specific model refuses

`temperature`, `reasoning_effort` and `verbosity` are model-gated, and the API rejects an
impossible pairing at create/update time — see
[Compatibility Matrix](compatibility.md). Two things the API cannot know offline, and asks
OpenAI about instead:

| Knob | Why offline rules are not enough |
|---|---|
| `reasoning_effort` **value** | OpenAI's docs say only "some models support every value" — which of `none`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max` a model takes is per model |
| `service_tier` | `flex` is beta with limited **model** availability; `priority`/`scale` depend on the **account** |

!!! danger "Fixed at the source: `service_tier: \"flex\"` on a non-gpt-5 model"

    This is the config that produced the silent calls this page was written for. An assistant on
    `gpt-4.1-nano` with `service_tier: "flex"` is answered HTTP 400 on every turn, and OpenAI
    names **no parameter** — the message is the same "There was an issue with your request.
    Please check your inputs and try again" you get over the WebSocket. Nothing else in that
    config was wrong. Setting the tier to `default` made the assistant speak immediately.

    **This can no longer be stored.** Every tier was probed against the API
    ([measured table](compatibility.md#service_tier-measured)) and the result is now an offline
    rule, not a guess:

    - `flex` is **gpt-5 generation only** → `422` on `gpt-4.1*`, `gpt-4o*` and `chat-latest`.
    - `scale` is **not an OpenAI tier at all** → removed from the accepted values. It could
      never have worked on any model.
    - `auto`, `default`, `fast` and `priority` work on every model tested. `fast` is not in
      OpenAI's documentation and works anyway.

    If you are reading this because a call went silent and the assistant has a `flex` tier on a
    gpt-4 model, the fix is one PATCH:

    ```json
    {"assistant_llm_config": {"service_tier": null}}
    ```

    `null` clears it and OpenAI picks. Leaving `service_tier` unset is the right default for
    almost every assistant.

Both are covered by one short probe request when the assistant is saved: the API sends the
exact model + knobs + tool schemas to OpenAI once (16 output tokens, nothing stored) and
returns OpenAI's own message as a `422`. So a knob combination that would silence every call is
refused with, for example:

```json
{
  "detail": "OpenAI rejected this configuration for model 'gpt-5-mini': Unsupported value: 'reasoning.effort' does not support 'none' with this model. (param: reasoning.effort). Stored as-is it would fail on every LLM turn, so the call would connect and the assistant would never speak. See docs/reference/troubleshooting.md."
}
```

When OpenAI refuses without naming a parameter — the `flex` case above — the `422` says so and
lists the candidates instead of leaving you with "check your inputs":

```json
{
  "detail": "OpenAI rejected this configuration for model 'gpt-4.1-nano': There was an issue with your request. Please check your inputs and try again OpenAI named no parameter. The candidates, in the order they are usually the answer: service_tier, temperature, tool_choice, parallel_tool_calls. `service_tier` availability is per-model and per-account, so it leads that list. To find out which, clear them one at a time — or, for an assistant that is already stored, run `uv run python scripts/replay_cascade_request.py <assistant_id>`, which bisects the knobs automatically and names every offender. …"
}
```

The probe result is cached per (key, model, knob combination), so it costs one request per new
combination, not one per write.

### 4. Tools

Three tool-shaped ways to silence a call, all now refused at config time:

- **`tool_choice: "required"` with no tools attached.** OpenAI rejects a forced tool choice
  with an empty tool list. Attach a tool (`POST /tool/attach/{assistant_id}`) or enable
  `assistant_end_call_enabled`, or use `"auto"`.
- **A tool schema the Responses API refuses.** Cascade sends `strict` function schemas; a
  schema that is not strict-valid is refused with the whole request. The runtime turns `strict`
  off by itself when a tool has optional or `object`/`array` parameters and logs
  `strict schema off`.
- **`reasoning_effort` on `gpt-5.2` / `gpt-5.4*` while tools are attached.** Those models
  reject `reasoning.effort` as soon as function tools are present. `create_llm` drops the knob
  and logs it; attaching a tool re-runs the check, so `POST /tool/attach/...` answers `400`
  rather than quietly breaking the next call.

Because attaching and detaching tools can invalidate a stored config, both endpoints re-run the
same guards as `PATCH /assistant/update`.

---

## The job dies at start (no audio at all, traceback in the worker log)

A stage could not be built. Each one logs a single line naming what was missing, and the job
ends. Most are now refused at create/update time instead:

| Cause | Now caught by |
|---|---|
| A provider with no API key (per-assistant or system) | `422` at create, `400` at update |
| An STT/TTS model id that does not exist (`nova-9`, `saaras:v4`) | `422` — the accepted sets are in `src/core/model_support/speech.py` |
| A `bulbul:v2` Sarvam speaker (`anushka`, `manisha`, …) on the pinned `bulbul:v3` | `422` — v2 and v3 share no speaker names |
| `assistant_stt_model: "native"` in cascade mode | `422` — there is no realtime model to self-transcribe |
| A Gemini chat model (`gemini-2.5-flash`) in realtime mode | `422` — only the three Live models can hold a session |
| A Gemini voice (`Puck`) under `provider: "openai"`, or the reverse | `422` — the two rosters share no names |

If a job still dies at start, the log line names the stage. `create_llm`, `create_stt` and
`create_tts` all end the job through the same `return None` path rather than raising, so what
you should see is one `ERROR` line, not a traceback.

---

## Realtime mode: no greeting, or no farewell

`gemini-3.1-flash-live-preview` restricts `send_client_content` to initial history seeding.
After the first model turn it rejects it, and `generate_reply()`, `update_instructions()` and
`update_chat_ctx()` are ignored with a warning
([LiveKit docs](https://docs.livekit.io/agents/models/realtime/plugins/gemini/#gemini-3-1-compatibility)).

On this platform that means, on 3.1 only:

- the **max-duration farewell** is not spoken (the call still ends on time);
- **silence re-prompts** are not spoken;
- agent handoff cannot change instructions mid-session.

The greeting is unaffected — it is sent as realtime *input*, not client content.

The default Gemini Live model is therefore `gemini-2.5-flash-native-audio-preview-12-2025`,
where all of the above work. Selecting 3.1 is allowed and logs:

```
WARNING  Gemini Live model gemini-3.1-flash-live-preview ignores generate_reply() after the
         first turn — the max-duration farewell and silence re-prompts will not be spoken on
         this call.
```

---

## The end-of-call webhook does not arrive

Check the activity log first — every attempt is recorded:

```
GET /logs?log_type=end_call_webhook&room_name=<room_name>
```

| What you see | Meaning |
|---|---|
| No log row at all | No `assistant_end_call_url` was configured, and no `webhook_url` was passed. Nothing was sent. |
| `status: "error"`, `response_data: null` | Never got a reply: DNS, TLS, connection refused, or a read timeout. The `message` names the exception. |
| `status: "error"` with a `4xx` status code | Your endpoint read the payload and rejected it. **Not retried** — re-sending cannot change a decision the receiver already made. |
| `status: "error"` with `429` or `5xx` | Retried up to `attempts` times, then given up. |
| `status: "success"` | Delivered; `latency_ms` is how long your endpoint took. |

Delivery is retried up to `END_CALL_WEBHOOK_ATTEMPTS` times (default `3`) with a 1s/2s backoff,
each attempt allowing 10s to connect and `END_CALL_WEBHOOK_TIMEOUT` seconds to answer (default
`30`). **Because delivery is retried, your endpoint must be idempotent** — key on
`data.room_name`.

Both values can be set per assistant, which is usually the better answer than moving the global
default for everyone:

```json
{
  "assistant_end_call_webhook": {
    "timeout_seconds": 45,
    "attempts": 5
  }
}
```

Send a field as `null` to fall back to the server default. See
[End-Call Webhook](../api/calls/webhook.md).

A read timeout used to log a full `httpx` traceback, which is why old logs are full of
`httpcore.ReadTimeout` stacks; it is one warning line now.

---

## Callers get a busy tone, or a web call gets 503

Both mean a concurrency cap was reached. The caps are per call type, so the first thing to
establish is *which* one.

| Symptom | Cap | Setting |
|---|---|---|
| Inbound caller hears a busy tone (SIP `486 Busy Here`) | telephony, or the global ceiling | `MAX_CONCURRENT_JOBS`, `MAX_CONCURRENT_SESSIONS` |
| `POST /get_token` returns `503` | web, or the global ceiling | `MAX_CONCURRENT_WEB_CALLS`, `MAX_CONCURRENT_SESSIONS` |
| Inbound caller hears a busy tone with capacity to spare | RTP port pool exhausted | `SIP_BRIDGE_PORT_RANGE_START` / `_END` |

The dispatcher logs which gate refused, so grep for `Slot refused`:

```
Slot refused (telephony): bucket cap reached (12/12)
Slot refused (web): global ceiling reached (48/48)
```

A `486` with slots free points at the port pool instead — look for
`No free RTP ports in <range>`. Note ports have a 30 second cooldown after release, so sustained
call churn makes the usable pool smaller than the raw range.

Rejected inbound calls are answered before the `CallRecord` is written, so **they leave no row in
`call_records`** — the log line above is the only record that a caller was turned away.

Before raising any cap, measure. `docker stats` on the agent container during a load test gives
the steady-state memory per session, and that is what the ceiling should be derived from — the
defaults are deliberately conservative rather than measured.

---

## An inbound caller hears silence after pickup

Expected behaviour is: ringing, then the greeting. Silence *after* the ringing stops means the
call was answered before the agent was ready.

Check `INBOUND_RING_UNTIL_AGENT_READY` is not set to `false`. If it is on, look for this in the
dispatcher log:

```
[INBOUND] Sending 180 Ringing, waiting up to 15s for agent
[INBOUND] Agent not ready after 15s — answering anyway | call-id=...
```

The second line means the agent did not report readiness inside the deadline, so the platform
answered rather than dropping the call. The usual cause is a slow inbound-context webhook — it
blocks agent startup and its own timeout can be up to 10s, leaving little room. Either speed the
webhook up, lower its `timeout_seconds`, or raise `INBOUND_MAX_RING_SECONDS`.

If instead you see `Agent ready (audio track published)` rather than `Agent ready (agent_ready
event)`, the agent container is running a build that predates the readiness signal. The fallback
works, but it fires slightly earlier than the real signal — redeploy the agent to get the tighter
timing.

---

## Changing a model list

Never from memory. OpenAI retires models on its own schedule and a stale entry is
indistinguishable from a working one until a call goes silent.

```bash
uv run python scripts/check_model_allowlist.py
```

Then edit `src/core/model_support/capabilities.py` (LLM) or
`src/core/model_support/speech.py` (STT/TTS) to match its output, and run the suite — the
speech sets are checked against the installed plugins' own definitions by
`tests/test_speech_models.py`, so a `livekit-agents` bump that renames a model fails the tests
instead of failing a call.
