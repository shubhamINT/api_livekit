# Inbound Routing

How Exotel inbound calls reach an assistant: the bridge accepts `INVITE`, normalises the dialled number, resolves the assistant mapping in MongoDB, creates a LiveKit room, and dispatches the matched assistant — optionally enriching the prompt via a context-strategy webhook before the first reply.

Inbound Exotel calls do not use managed LiveKit SIP participants — the platform owns the bridge end-to-end.

## Inbound Components

- `/inbound` routes manage `inbound_sip` mappings.
- `/inbound_context_strategy` routes manage reusable caller-context lookup strategies.
- MongoDB stores normalized inbound numbers, provider config, and `assistant_id` mappings.
- Inbound mappings can optionally store `inbound_context_strategy_id`.
- Inbound bridge handles SIP signaling, RTP relay, and room setup.
- LiveKit dispatch metadata includes inbound and caller numbers plus mapping/strategy identifiers.
- Agent worker can optionally resolve inbound context via strategy webhook before prompt rendering.

## Inbound Call Sequence

```mermaid
sequenceDiagram
    autonumber
    participant Caller as Caller
    participant Exotel as Exotel
    participant Bridge as Inbound Bridge
    participant DB as MongoDB
    participant LK as LiveKit
    participant Agent as AI Agent
    participant Webhook as Context Webhook

    Caller->>Exotel: Dial inbound number
    Exotel->>Bridge: SIP INVITE
    Bridge-->>Exotel: SIP 100 Trying
    Bridge->>Bridge: Normalize dialed number
    Bridge->>DB: Lookup active inbound mapping
    DB-->>Bridge: Mapping with assistant_id and optional strategy_id
    Bridge->>DB: Load active assistant
    Bridge->>LK: Create room
    Bridge->>LK: Create dispatch metadata
    Bridge->>Bridge: Start bridge process, wait for it to bind RTP + connect LiveKit
    Bridge-->>Exotel: SIP 180 Ringing
    Note over Caller,Bridge: Caller hears ringing while the agent boots
    LK->>Agent: Start session with metadata
    alt strategy_id present and lookup succeeds
        Agent->>DB: Load strategy
        Agent->>Webhook: Request inbound caller context
        Webhook-->>Agent: context payload
    else strategy_id present but lookup fails or times out
        Agent->>DB: Load strategy
        Agent->>Webhook: Request inbound caller context
        Webhook-->>Agent: error or invalid payload
    else strategy_id missing
        Agent->>Agent: Continue without context lookup
    end
    Agent->>Agent: Render prompt/start instruction
    Agent->>LK: agent_ready on sip_bridge_events
    LK-->>Bridge: agent_ready
    Bridge-->>Exotel: SIP 200 OK
    Note over Bridge,Exotel: Answered only now, or after INBOUND_MAX_RING_SECONDS
    Note over Bridge,LK: Bridge process (one per call) — LiveKit connect + RTP start_inbound
    Exotel->>Bridge: RTP audio uplink
    Bridge-->>Exotel: RTP audio downlink
    Bridge->>LK: Audio relay uplink
    LK-->>Bridge: Audio relay downlink
    LK->>Agent: Real-time uplink
    Agent-->>LK: Real-time downlink
```

## Inbound Failure Paths

- No active mapping or detached mapping returns `480 Temporarily Unavailable`.
- Missing or inactive assistant returns `480 Temporarily Unavailable`.
- Missing strategy attachment does not fail the call; context lookup is skipped.
- Strategy lookup failures (timeout/HTTP/payload issues) do not fail the call; worker falls back to default prompt behavior.
- Room creation or dispatch failure returns `500 Internal Server Error`.
- Call teardown is handled by SIP `BYE`, LiveKit disconnect, or RTP timeout.
