# Inbound Call Flow

Inbound calling currently uses the custom Exotel SIP bridge.

## Routing Steps

1. Exotel sends a SIP `INVITE` to the custom inbound bridge.
2. The bridge reads the dialed number from the SIP `To` header.
3. The number is normalized with the same formatter used by the `/inbound` API.
4. The bridge looks up an active `InboundSIP` mapping by `phone_number_normalized`.
5. If the mapping is missing or detached, the bridge returns `480 Temporarily Unavailable`.
6. The bridge loads the assistant from `assistant_id` on the mapping.
7. If the mapped assistant is inactive or missing, the bridge returns `480 Temporarily Unavailable`.
8. If the telephony concurrency cap (`MAX_CONCURRENT_JOBS`) or the global ceiling
   (`MAX_CONCURRENT_SESSIONS`) is reached, the bridge returns `486 Busy Here`. Inbound shares the
   telephony pool with outbound and passthrough calls; web calls have their own
   (`MAX_CONCURRENT_WEB_CALLS`). Running out of RTP ports also answers `486`.
9. The media bridge runs in its own OS process. It binds the RTP socket and connects to LiveKit
   *before* the call is answered, so Exotel never sends RTP at a port nothing is listening on; if
   it cannot start, the INVITE is answered `503 Service Unavailable`.
10. The caller hears **ringing until the agent is ready to speak**. `100 Trying` goes out
    immediately, `180 Ringing` once the media path is up, and `200 OK` only when the agent
    signals readiness — which is after the inbound-context webhook has returned. If the agent is
    not ready within `INBOUND_MAX_RING_SECONDS` (default 15) the call is answered anyway, never
    dropped. Hanging up while ringing gets `487 Request Terminated`.
9. When routing succeeds, the bridge creates a LiveKit room, dispatches the assistant, and connects RTP audio.
10. The agent session optionally runs inbound context lookup before rendering prompt templates.

## Dispatch Metadata

The bridge creates the LiveKit dispatch with these metadata keys:

| Key | Value |
| :--- | :--- |
| `call_type` | `inbound` |
| `service` | `exotel` |
| `assistant_id` | Assistant selected from the mapping |
| `assistant_name` | Assistant display name |
| `inbound_id` | Inbound mapping identifier |
| `inbound_context_strategy_id` | Optional strategy attached to the mapping |
| `inbound_number` | Normalized dialed number |
| `caller_number` | Parsed caller number from the SIP `From` header |

## Agent Prompt Rendering Phase

After dispatch, the worker loads metadata and renders:

- `assistant_prompt`
- `assistant_start_instruction`

Render inputs are:

- Existing top-level metadata keys.
- `call.*` namespace containing the call metadata.
- Optional `context.*` namespace when inbound context lookup succeeds.

## Optional Strategy and Fallback Behavior

If `inbound_context_strategy_id` is not present:

- No lookup is attempted.
- Prompt rendering continues using call metadata only.

If `inbound_context_strategy_id` is present:

- The worker tries to load the strategy and call the configured webhook.
- The webhook must return JSON with a top-level `context` object.
- Full request/response contract is documented in [Inbound Context Strategies](../inbound-context-strategy/index.md#webhook-request-payload).

If strategy loading or webhook lookup fails:

- Timeout, HTTP error, invalid JSON, invalid payload shape, missing URL, or inactive strategy all fall back to default prompt behavior.
- The call continues and the assistant still starts.
- An `inbound_context_lookup` activity log is written for attempted lookups.

## Runtime Notes

- A `200 OK` SIP response is sent only after LiveKit room setup and RTP bridge startup succeed.
- The bridge waits briefly after room connection, then publishes a `call_answered` event on the `sip_bridge_events` topic so the agent can start speaking after the media path is ready.
- If room creation, call record initialization, or dispatch setup fails, the bridge returns `500 Internal Server Error` and releases the reserved slot.
- Active call shutdown is driven by SIP `BYE`, LiveKit disconnect, or RTP silence timeout.
- On startup, inbound `CallRecord`s left in `initiated`/`answered` are checked one by one: those whose LiveKit room no longer exists are failed as orphaned, freeing the concurrency slot. Records whose room is still alive are left running — a dispatcher restart no longer cuts calls that agent containers are still serving.

```mermaid
sequenceDiagram
    participant Caller
    participant Exotel
    participant Bridge as Exotel Inbound Bridge
    participant DB as MongoDB
    participant LK as LiveKit
    participant Agent as Agent Worker
    participant Webhook as Context Webhook

    Caller->>Exotel: Dial Exotel number
    Exotel->>Bridge: SIP INVITE
    Bridge->>Bridge: Normalize dialed number
    Bridge->>DB: Lookup active inbound mapping
    DB-->>Bridge: mapping (assistant_id + optional strategy_id) or no match
    alt No mapping or detached mapping
        Bridge-->>Exotel: 480 Temporarily Unavailable
    else Mapping found
        Bridge->>DB: Load assistant
        Bridge->>LK: Create room and dispatch agent
        Bridge-->>Exotel: 200 OK
        LK->>Agent: Start session with dispatch metadata
    end
    alt strategy_id exists and strategy found
        Agent->>DB: Load active strategy
        Agent->>Webhook: POST caller/context lookup
        Webhook-->>Agent: context payload or error/timeout
    else strategy_id exists but strategy missing/inactive
        Agent->>DB: Load active strategy
        Agent->>Agent: Skip lookup and continue
    else No strategy_id
        Agent->>Agent: Continue without lookup
    end
    Agent->>Agent: Render prompt/start instruction
    Bridge->>Agent: Publish call_answered event
    Exotel->>Bridge: RTP audio
    Agent->>Bridge: RTP audio
```
