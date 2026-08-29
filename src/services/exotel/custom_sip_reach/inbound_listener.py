"""
Inbound SIP TCP listener — handles BYE and OPTIONS from Exotel.

When Exotel initiates a BYE on a *new* TCP connection (rather than the
outbound INVITE connection), this listener catches it and signals the
bridge to tear down the call.
"""

import asyncio
import multiprocessing
import multiprocessing.synchronize
import threading

from .config import EXOTEL_CUSTOMER_SIP_PORT, EXOTEL_SIP_ALLOWED_IPS, INBOUND_SIP_LISTEN
from .sip_client import ExotelSipClient
from src.core.config import settings
from src.core.logger import logger

# ─────────────────────────────────────────────────────────────────────────────
# Module-level state
# ─────────────────────────────────────────────────────────────────────────────

_inbound_server: asyncio.AbstractServer | None = None
_inbound_lock = threading.Lock()
# Values are multiprocessing.Event objects (OS-level shared memory). The parent process sets
# them here when Exotel sends BYE. Each bridge subprocess receives its own event handle via
# argument — it does NOT look up this dict. The dict is only used by the inbound listener.
_call_registry: dict[str, multiprocessing.synchronize.Event] = {}
_registry_lock = threading.Lock()


# ─────────────────────────────────────────────────────────────────────────────
# Public helpers
# ─────────────────────────────────────────────────────────────────────────────


class DuplicateCallId(Exception):
    """Raised when an INVITE reuses a Call-ID that already has a live registration."""


def registry_key(call_id: str | None, peer_ip: str | None = None) -> str:
    """Build the registry key for a call.

    Inbound Call-IDs come straight off the wire, so they are namespaced by the sending IP and
    a missing one is rejected rather than silently collapsing every malformed INVITE onto the
    same key. Outbound generates its own UUID and passes no peer_ip, keeping those keys as they
    were.
    """
    if not call_id:
        raise ValueError("SIP INVITE has no Call-ID")
    return f"{peer_ip}|{call_id}" if peer_ip else call_id


def register_call_id(
    call_id: str, peer_ip: str | None = None
) -> tuple[str, multiprocessing.synchronize.Event]:
    """Register a call and return (key, Event) where the Event fires on inbound BYE/CANCEL.

    Raises DuplicateCallId if the key is already live. This used to overwrite: a retransmitted
    or duplicated Call-ID replaced the first call's Event, so that call's BYE could never reach
    it (it ran on until an RTP-silence timeout, holding its port), while the first call's
    teardown deleted the *second* call's registration.
    """
    key = registry_key(call_id, peer_ip)
    # The Event is handed to the bridge process, so it must come from the same multiprocessing
    # context that launches it. A default-context Event passed to a forkserver/spawn child
    # fails outright: "A SemLock created in a fork context is being shared with a process in a
    # spawn context."
    from src.services.outbound_dispatcher.dispatcher import get_bridge_context

    event = get_bridge_context().Event()
    with _registry_lock:
        if key in _call_registry:
            raise DuplicateCallId(key)
        _call_registry[key] = event
    return key, event


def register_call_id_with_event(call_id: str, event: multiprocessing.synchronize.Event) -> None:
    """Register a pre-created multiprocessing.Event for a call-ID.

    Used by the dispatcher when it pre-generates call_id before spawning the bridge
    subprocess, so the inbound listener can signal the subprocess on BYE.
    """
    with _registry_lock:
        _call_registry[call_id] = event


def _lookup_event(call_id: str | None, peer_ip: str | None):
    """Find the Event for an in-dialog request (BYE/CANCEL).

    Tries the exact key first. Exotel may send BYE from a different node than the INVITE came
    from, so it falls back to matching on Call-ID alone — but only when that is unambiguous.
    Firing on an ambiguous match would tear down the wrong call, which is worse than letting
    the RTP-silence watchdog end this one.
    """
    if not call_id:
        return None
    with _registry_lock:
        exact = _call_registry.get(registry_key(call_id, peer_ip))
        if exact is not None:
            return exact
        matches = [
            evt for key, evt in _call_registry.items()
            if key == call_id or key.endswith(f"|{call_id}")
        ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        logger.warning(
            f"[SIP-IN] Ambiguous Call-ID {call_id!r} matches {len(matches)} live calls — "
            "ignoring rather than tearing down the wrong one"
        )
    return None


def unregister_call_id(key: str):
    """Remove a registration. Takes the key returned by register_call_id()."""
    with _registry_lock:
        _call_registry.pop(key, None)


# ─────────────────────────────────────────────────────────────────────────────
# Server lifecycle
# ─────────────────────────────────────────────────────────────────────────────


async def ensure_inbound_server():
    """Start the inbound SIP listener (once, idempotent). Must be called from the main loop."""
    global _inbound_server
    if not INBOUND_SIP_LISTEN:
        return
    with _inbound_lock:
        if _inbound_server is not None:
            return
        try:
            _inbound_server = await asyncio.start_server(
                _handle_inbound_sip, "0.0.0.0", EXOTEL_CUSTOMER_SIP_PORT
            )
            logger.info(
                "[SIP-IN] Listening on 0.0.0.0:%s",
                EXOTEL_CUSTOMER_SIP_PORT,
            )
        except Exception as e:
            logger.error(f"[SIP-IN] Failed to bind {EXOTEL_CUSTOMER_SIP_PORT}: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Connection handler
# ─────────────────────────────────────────────────────────────────────────────


# Bounds how many INVITEs may be in setup at once. Without this every INVITE became a bare
# task, so a burst all reached the concurrency gate before any of them had incremented it and
# they all passed — the 486 Busy Here gate was softest under exactly the burst it exists for.
#
# This is not a cap on live inbound calls: the slot is released as soon as the call is
# answered. It does have to exceed the number of calls that can be ringing at once, because
# the ring-until-agent-ready wait happens inside it — see inbound_bridge.MAX_RING_SECONDS.
_invite_semaphore: asyncio.Semaphore | None = None
_invite_tasks: set[asyncio.Task] = set()


def _get_invite_semaphore() -> asyncio.Semaphore:
    global _invite_semaphore
    if _invite_semaphore is None:
        _invite_semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_INVITE_SETUPS)
    return _invite_semaphore


async def _run_invite(*, handler, peer_ip, call_id, cseq, from_header, to_header,
                      via_headers, record_routes, sdp_body, writer) -> None:
    """Run one INVITE through setup, guaranteeing a SIP final response on any failure."""
    try:
        async with _get_invite_semaphore():
            await handler(
                sdp_body=sdp_body,
                writer=writer,
                from_header=from_header,
                to_header=to_header,
                call_id=call_id,
                cseq=cseq,
                via_headers=via_headers,
                record_routes=record_routes,
                peer_ip=peer_ip,
            )
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(
            f"[SIP-IN] INVITE setup failed call-id={call_id}: {e}", exc_info=True
        )
        try:
            from .inbound_bridge import _build_sip_response
            writer.write(
                _build_sip_response(
                    status_line="SIP/2.0 500 Server Internal Error",
                    call_id=call_id or "",
                    cseq=cseq,
                    from_header=from_header,
                    to_header=to_header,
                    via_headers=via_headers,
                )
            )
            await writer.drain()
        except Exception as reply_err:
            logger.warning(f"[SIP-IN] Could not send 500 for {call_id}: {reply_err}")


async def _handle_inbound_sip(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
):
    buf = b""
    peer = writer.get_extra_info("peername")
    # Only accept SIP from known Exotel IPs (if allowlist is configured)
    if EXOTEL_SIP_ALLOWED_IPS and peer and peer[0] not in EXOTEL_SIP_ALLOWED_IPS:
        logger.warning(f"[SIP-IN] Rejected connection from untrusted IP {peer[0]}")
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
        return
    try:
        while True:
            data = await reader.read(4096)
            if not data:
                break
            buf += data

            while b"\r\n\r\n" in buf:
                he = buf.index(b"\r\n\r\n")
                hb = buf[:he].decode(errors="replace")
                rest = buf[he + 4 :]
                lines = hb.split("\r\n")
                start = lines[0]
                hdrs = {}
                via_headers = []
                record_routes = []

                for l in lines[1:]:
                    if ":" in l:
                        k, v = l.split(":", 1)
                        k = k.strip().lower()
                        v = v.strip()
                        if k == "via":
                            via_headers.append(v)
                        elif k == "record-route":
                            record_routes.append(v)
                        else:
                            hdrs[k] = v

                cl = int(hdrs.get("content-length", "0"))
                if len(rest) < cl:
                    break

                body = rest[:cl].decode(errors="replace")
                buf = rest[cl:]

                if start.startswith("BYE "):
                    call_id = hdrs.get("call-id")
                    logger.info(f"[SIP-IN] ← BYE from {peer} call-id={call_id}")
                    evt = _lookup_event(call_id, peer[0] if peer else None)
                    if evt:
                        evt.set()
                    writer.write(ExotelSipClient._response_200_ok(hdrs, via_headers=via_headers))
                    await writer.drain()
                    logger.info("[SIP-IN] → 200 OK (BYE)")
                elif start.startswith("CANCEL "):
                    # Caller hung up before we answered. Exotel sends CANCEL (not BYE) for
                    # this — it was previously unhandled here, so the in-flight INVITE kept
                    # running, answered anyway, and dispatched an agent for an abandoned
                    # call. Setting the event lets handle_inbound_call (which holds the
                    # INVITE's own writer) notice and reply 487 on its own connection —
                    # same cross-connection signal already used for BYE.
                    call_id = hdrs.get("call-id")
                    logger.info(f"[SIP-IN] ← CANCEL from {peer} call-id={call_id}")
                    evt = _lookup_event(call_id, peer[0] if peer else None)
                    if evt:
                        evt.set()
                    writer.write(ExotelSipClient._response_200_ok(hdrs, via_headers=via_headers))
                    await writer.drain()
                    logger.info("[SIP-IN] → 200 OK (CANCEL)")
                elif start.startswith("OPTIONS "):
                    writer.write(ExotelSipClient._response_200_ok(hdrs, via_headers=via_headers))
                    await writer.drain()
                    logger.info(f"[SIP-IN] → 200 OK (OPTIONS) from {peer}")
                elif start.startswith("INVITE "):
                    call_id = hdrs.get("call-id")
                    logger.info(f"[SIP-IN] ← INVITE from {peer} call-id={call_id}")
                    from .inbound_bridge import handle_inbound_call
                    # Kept in _invite_tasks so the task isn't garbage collected mid-setup and
                    # so a crash surfaces here instead of as a bare "Task exception was never
                    # retrieved" at GC time, which is what used to happen — leaving the INVITE
                    # with no SIP response at all and the caller listening to dead air.
                    task = asyncio.create_task(
                        _run_invite(
                            sdp_body=body,
                            writer=writer,
                            from_header=hdrs.get("from", ""),
                            to_header=hdrs.get("to", ""),
                            call_id=call_id,
                            cseq=hdrs.get("cseq", ""),
                            via_headers=via_headers,
                            record_routes=record_routes,
                            peer_ip=peer[0] if peer else None,
                            handler=handle_inbound_call,
                        )
                    )
                    _invite_tasks.add(task)
                    task.add_done_callback(_invite_tasks.discard)
                elif start.startswith("ACK "):
                    call_id = hdrs.get("call-id")
                    logger.info(f"[SIP-IN] ← ACK from {peer} call-id={call_id}")
    except Exception as e:
        logger.info(f"[SIP-IN] Connection ended: {e}")
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:
            pass
