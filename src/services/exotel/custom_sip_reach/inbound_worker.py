"""
Inbound bridge worker — the media half of one inbound Exotel call.

This runs in its own OS process, one per call. It deliberately imports nothing from the API,
the dispatcher or the database: the parent has already done all of that work by the time this
starts, and keeping the import graph small keeps process startup cheap.

Why a process and not a thread. Inbound bridges used to run as one thread per call inside the
SIP dispatcher process. Every LiveKit media object they created talked to `FfiClient`, which is
a process-wide singleton whose event dispatch walks every subscriber under a single lock on a
single thread — and `AudioSource.capture_frame` subscribes a fresh queue for each frame, which
this bridge calls once per RTP packet. The per-event cost therefore grew with the number of
concurrent calls in the process. Past roughly half a dozen calls the agent's audio stopped
reaching the caller, while the LiveKit-side recording (server egress) still captured everything
— a call that sounded fine in the recording and silent on the phone.

Outbound already solved this by moving each bridge into its own process. This is the same fix
for inbound.
"""

import asyncio
import json

from livekit import rtc

from .config import (
    EXOTEL_MEDIA_IP,
    LK_URL,
    RTP_SILENCE_TIMEOUT_SECONDS,
    NO_RTP_AFTER_ANSWER_SECONDS,
)
from .rtp_bridge import RTPMediaBridge
from src.core.logger import logger, set_room_context, clear_room_context


async def _run_inbound_bridge(
    *,
    room_name: str,
    port: int,
    remote_ip: str,
    remote_port: int,
    pt: int,
    token: str,
    ready_queue,
    answered_event,
    inbound_bye,
) -> None:
    """Own the LiveKit room + RTP bridge for one inbound call, start to finish."""
    set_room_context(room_name)
    room = rtc.Room()
    rtp_bridge: RTPMediaBridge | None = None

    try:
        # Bind the RTP socket before telling the parent it may answer. Exotel starts sending
        # RTP the moment it sees the 200 OK, so the socket has to exist first or those packets
        # draw ICMP port-unreachable.
        rtp_bridge = RTPMediaBridge(public_ip=EXOTEL_MEDIA_IP, bind_port=port)

        # The parent answers the call on this, so it must be sent exactly once however the
        # agent turns up — an explicit agent_ready message, or its audio track appearing.
        agent_ready_sent = False

        def signal_agent_ready(how: str) -> None:
            nonlocal agent_ready_sent
            if agent_ready_sent:
                return
            agent_ready_sent = True
            logger.info(f"[INBOUND] Agent ready ({how}) — parent may answer")
            ready_queue.put({"event": "agent_ready"})

        @room.on("track_subscribed")
        def on_track(track, publication, participant):
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                logger.info(
                    f"[INBOUND] Agent audio from {participant.identity} "
                    f"(source={publication.source}) — adding to mixer"
                )
                rtp_bridge.add_outbound_track(track)
                rtp_bridge.start_outbound_mixer()
                # Fallback readiness signal. Weaker than the agent's own agent_ready message
                # (a published track means session.start() finished, not that the greeting is
                # queued), but it needs nothing from the agent side, so ringing still works
                # against an older agent build that never publishes.
                signal_agent_ready("audio track published")

        @room.on("data_received")
        def on_data(data: rtc.DataPacket):
            if data.topic != "sip_bridge_events":
                return
            try:
                event = json.loads(data.data.decode()).get("event")
            except Exception:
                return
            if event == "agent_ready":
                signal_agent_ready("agent_ready event")

        await asyncio.wait_for(room.connect(LK_URL, token), timeout=15.0)
        logger.info(f"[INBOUND] Bridge process: LiveKit connected room={room_name}")
        await rtp_bridge.start_inbound(room)

        # Phase one: the media path is up. The parent sends 180 Ringing on this and starts
        # waiting for agent_ready above.
        ready_queue.put({"event": "media_ready", "port": port})

        # Media stays gated until the parent has actually sent the 200 OK.
        if not await asyncio.to_thread(answered_event.wait, 60.0):
            logger.error("[INBOUND] Parent never signalled answer — aborting")
            return
        rtp_bridge.set_remote_endpoint(remote_ip, remote_port, pt)

        # No sleep before this any more. There used to be an unconditional 1.5s wait here to
        # "give the agent process a moment to finish booting" — the parent now rings until the
        # agent says it is ready, so by this point booting is already done.
        try:
            await room.local_participant.publish_data(
                json.dumps({"event": "call_answered"}).encode(),
                topic="sip_bridge_events",
            )
            logger.info("[INBOUND] Published call_answered event to agent")
        except Exception as e:
            logger.error(f"[INBOUND] Failed to publish call_answered event: {e}")

        answered_at = asyncio.get_running_loop().time()
        disconnect_reason = "unknown"
        while True:
            if room.connection_state != rtc.ConnectionState.CONN_CONNECTED:
                disconnect_reason = "livekit_disconnected"
                break
            if inbound_bye.is_set():
                disconnect_reason = "sip_bye"
                break
            since_rx = rtp_bridge.seconds_since_rx()
            if since_rx is None:
                # No RTP has *ever* arrived. The old loop only watched for silence after audio
                # had started flowing, so a call that never received a single packet sat here
                # holding its port until LiveKit disconnected.
                waited = asyncio.get_running_loop().time() - answered_at
                if NO_RTP_AFTER_ANSWER_SECONDS > 0 and waited > NO_RTP_AFTER_ANSWER_SECONDS:
                    disconnect_reason = "no_rtp_after_answer"
                    break
            elif RTP_SILENCE_TIMEOUT_SECONDS > 0 and since_rx > RTP_SILENCE_TIMEOUT_SECONDS:
                disconnect_reason = "rtp_silence_after_flow"
                break
            await asyncio.sleep(1)

        logger.info(f"[INBOUND] Call ended — reason={disconnect_reason}")

    except Exception as e:
        logger.error(f"[INBOUND] Bridge error: {e}", exc_info=True)
        try:
            ready_queue.put({"event": "failed", "error": str(e)})
        except Exception:
            pass

    finally:
        if rtp_bridge is not None:
            try:
                await rtp_bridge.close_streams()
                rtp_bridge.stop()
            except Exception as e:
                logger.warning(f"[INBOUND] rtp_bridge.stop() raised: {e}")
        try:
            await room.disconnect()
        except Exception as e:
            logger.warning(f"[INBOUND] room.disconnect() raised: {e}")
        clear_room_context()


def inbound_bridge_subprocess_entry(
    room_name: str,
    port: int,
    remote_ip: str,
    remote_port: int,
    pt: int,
    token: str,
    ready_queue,
    answered_event,
    inbound_bye,
):
    """Top-level process entry point — must be module-level to be picklable."""
    asyncio.run(
        _run_inbound_bridge(
            room_name=room_name,
            port=port,
            remote_ip=remote_ip,
            remote_port=remote_port,
            pt=pt,
            token=token,
            ready_queue=ready_queue,
            answered_event=answered_event,
            inbound_bye=inbound_bye,
        )
    )
