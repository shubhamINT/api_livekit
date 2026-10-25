# Project brief

- **Status:** approved (2026-10-25, by Shubham Halder)
- **Mode:** existing

## Purpose

The core platform for voice products. It is a self-hosted LiveKit backend exposed through APIs:
developers create and edit assistants, run calls with them, and use the platform's features to
build their own voice products on top — HR automation, sales automation, or any other product
built on voice. Calls run over Exotel telephony, web calls, and Google Meet.

## Users

| User | What they need |
|------|----------------|
| Developers building voice products on the API | Create and edit assistants, place and receive calls with them, and use the platform's call features (recording, webhooks, the configuration knobs) as the base of their own product. |

There are no other users.

## Success measures

Stated goal (the user's words): the more responsive, the quicker, the more humanized and the more
proper the response, the better — without breaking any of the logic that runs inside a call
(recording, the end-of-call webhook, and what follows from it).

- **Response latency:** time from the end of the caller's speech to the first agent audio,
  p50 and p95 in ms, per mode. Measure the baseline first; the numeric target is set from it
  (the user does not know today's latency).
- **No regression:** until the target is set, no change may make p95 response latency worse
  than the measured baseline, and no change may break recording, the end-of-call webhook, or
  the work that follows a call.

## Stack

| Decision | Choice | Why |
|----------|--------|-----|
| Language and framework | Python 3.12+, `uv`, FastAPI + Gunicorn, LiveKit Agents (`~=1.8.8` today) | As built; upgraded as new LiveKit versions ship |
| Data store | MongoDB (Beanie ODM) | As built |
| Hosting and CI | Self-hosted LiveKit and services, deployed with `deploy.sh` (`control`, `agent`, `full`) | Self-hosted by design |
| Tests and lint | stdlib `unittest`, Ruff via `uvx` | As built |

## Features

The platform as it stands, grouped from the published feature list (`docs/features.md`). Every
row is built. Priority marks how central it is to the products built on the platform. New work
comes from what the teams building on the platform need and from new LiveKit capabilities as
they ship; each new feature gets its own spec.

| ID | Feature | Priority | Status | Spec |
|----|---------|----------|--------|------|
| F-1 | Assistant management: create, edit, list, delete; system prompt, placeholders, greeting, call caps | must | built | — |
| F-2 | Assistant modes: pipeline, realtime, cascade, duplex, with config validation that keeps a call from going silent | must | built | — |
| F-3 | Speech providers: STT (Sarvam, native, Cartesia, Deepgram, ElevenLabs, OpenAI) and TTS (Cartesia, Sarvam, ElevenLabs, Mistral) | must | built | — |
| F-4 | Outbound calls over Exotel and Twilio, with the queue, dispatcher and capacity limits | must | built | — |
| F-5 | Inbound calls over Exotel, number-to-assistant mapping, inbound context strategies | must | built | — |
| F-6 | Web calls (voice, text chat, text-only) | must | built | — |
| F-7 | Google Meet calls through a replaceable meeting connector | must | built | — |
| F-8 | Call lifecycle: recording to S3, transcripts, call records, end-of-call webhook | must | built | — |
| F-9 | Function tools (webhook and static) attached to assistants | must | built | — |
| F-10 | Humanizing voice features: speech gate, input guard, silence watchdog, hold handling, filler words, background audio, prerecorded greetings | should | built | — |
| F-11 | Passthrough calls (human web user to phone caller, no AI) | should | built | — |
| F-12 | Usage, billing, analytics and activity logs (per user and super-admin) | should | built | — |
| F-13 | API keys and auth, SIP trunk management | must | built | — |
| F-14 | Deployment roles (`control`, `agent`, `full`) and the bundled docs site | could | built | — |

## Constraints

- Self-hosted: no LiveKit Cloud features.
- The stack follows new LiveKit releases; new capabilities from the LiveKit changelog are added
  as they arrive.
- A change must not break the logic that runs inside a call (recording, webhooks and what
  follows them).

## Out of scope

- Nothing is ruled out. The platform grows with what the teams building on it need.

## Open questions

None (the user: nothing is unknown).

## Change log

| Date | Change | Approved by |
|------|--------|-------------|
| 2026-10-25 | Created | Shubham Halder |
