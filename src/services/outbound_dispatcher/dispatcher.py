import asyncio
import multiprocessing
import queue as _stdlib_queue
import uuid
from datetime import datetime, timedelta, timezone

from beanie.operators import In

from src.core.config import settings
from src.core.db.database import Database
from src.core.db.db_schemas import CallRecord, OutboundCallQueue, OutboundSIP
from src.core.logger import logger
from src.services.livekit.livekit_svc import LiveKitService, TERMINAL_CALL_STATUSES

# Queue items stuck in 'dispatching' longer than this indicate a worker crash
# mid-dispatch. Reset them back to 'pending' (or 'failed' past MAX_RETRIES).
STUCK_DISPATCHING_MINUTES = 5

MAX_RETRIES = 3           # permanent failure after this many attempts

ORPHAN_REAPER_INTERVAL_SECONDS = 30 * 60  # how often the orphan reaper sweeps

# How long the monitor waits for session.py to finalize a call after the bridge exits,
# before assuming the agent died and finalizing itself. Must exceed session.py's teardown
# (~8s worst case: 1s + END_OF_CALL_GRACE_S + 3s transcript join).
FINALIZE_WAIT_SECONDS = 15

# _watch_agent_join: how long a call may ring before being answered (matches session.py's
# own gate.wait_until_ready(timeout=60.0) for the Exotel path) ...
AGENT_ANSWER_WAIT_SECONDS = 60
# ... and how long the agent gets to reach session.start() *after* the phone was answered,
# before the call is treated as silently dead and force-ended.
AGENT_JOIN_GRACE_SECONDS = 15

livekit_services = LiveKitService()

# Every bridge (inbound and outbound) is its own OS process. Under "spawn" each of those
# re-imported the whole scientific stack from scratch — scipy.signal alone costs ~5 seconds of
# CPU per import. At a dozen simultaneous calls that was over a minute of pure import work on a
# 2-4 vCPU host, which starved the dispatcher's event loop, spiked host CPU past the agent
# worker's load threshold (so it stopped accepting jobs), and pushed memory towards the OOM
# killer, which is what cut calls mid-conversation.
#
# "forkserver" pays that cost once, in a server process, and every bridge forks from it warm.
# The preload list deliberately excludes livekit.rtc: importing it starts the native FFI
# callback thread, and forking a process with live native threads gives children a broken FFI.
# The bridges import it themselves after the fork.
_BRIDGE_PRELOAD = ["numpy", "scipy.signal", "audioop"]
_bridge_context = None


def get_bridge_context():
    """Return the multiprocessing context used to launch bridge processes."""
    global _bridge_context
    if _bridge_context is None:
        try:
            ctx = multiprocessing.get_context("forkserver")
            ctx.set_forkserver_preload(_BRIDGE_PRELOAD)
            _bridge_context = ctx
            logger.info("[Bridge] Using forkserver context (preloaded: %s)", _BRIDGE_PRELOAD)
        except (ValueError, AttributeError) as e:
            logger.warning(f"[Bridge] forkserver unavailable ({e}); falling back to spawn")
            _bridge_context = multiprocessing.get_context("spawn")
    return _bridge_context


TELEPHONY = "telephony"
WEB = "web"
BUCKETS = (TELEPHONY, WEB)

LIVE_CALL_STATUSES = ["initiated", "answered"]


def bucket_for_call_type(call_type: str | None) -> str:
    """Which capacity bucket a CallRecord belongs to.

    Web calls need only an agent job process. Phone calls additionally need a bridge process
    and an RTP port, so they are capped separately and much lower.

    Passthrough is not a call_type — it is a boolean on an "outbound" row — so it lands in
    telephony without a special case, which is correct: it holds a bridge and a port.
    """
    return WEB if call_type == "web" else TELEPHONY


BUCKET_CAPS = {
    TELEPHONY: lambda: settings.MAX_CONCURRENT_JOBS,
    WEB: lambda: settings.MAX_CONCURRENT_WEB_CALLS,
}


_new_call_event = asyncio.Event()

# In-memory reservation counters, one per capacity bucket: calls that are mid-dispatch
# (room created but CallRecord not yet written). Prevents double-dispatch. The reservation is a
# short-lived handover token — once the CallRecord exists, counting comes from the DB.
_dispatching_count: dict[str, int] = {bucket: 0 for bucket in BUCKETS}


async def _fail_stale_calls_on_startup() -> None:
    """On startup, clear out call records left behind by a previous instance.

    This used to fail *every* initiated/answered record unconditionally. That was only safe
    when the dispatcher was the sole owner of every live call — in the current split
    deployment the agent containers outlive a dispatcher restart, so a restart (an OOM restart
    included) cut every call that was in progress across the whole platform at once.

    The orphan reaper already answers the right question, per record: does this call's LiveKit
    room still exist? Records whose room is gone are genuinely dead and get failed; live calls
    are left alone.
    """
    logger.info("Startup cleanup: reaping calls whose LiveKit room no longer exists")
    await _reap_orphaned_calls()


async def _reap_orphaned_calls() -> None:
    """Mark initiated/answered call records as failed when their LiveKit room no longer exists.

    Catches all orphan paths: agent crash, Twilio with no safety net, web token
    issued but client never joined, inbound bridge died without calling end_call().
    Runs every 15 minutes. Skips records whose room is still alive (long calls safe).
    """
    stale = await CallRecord.find(
        In(CallRecord.call_status, ["initiated", "answered"]),
    ).to_list()
    if not stale:
        return

    reaped = 0
    for record in stale:
        try:
            exists = await livekit_services.room_exists(record.room_name)
        except Exception as e:
            logger.warning(f"Reaper: could not check room {record.room_name}: {e}")
            continue
        if not exists:
            record.call_status = "failed"
            record.call_status_reason = "Orphaned: LiveKit room no longer exists"
            if record.ended_at is None:
                record.ended_at = datetime.now(timezone.utc)
            await record.save()
            reaped += 1
            logger.warning(f"Reaper: marked orphaned call failed | room={record.room_name}")

    if reaped:
        logger.warning(f"Reaper: cleaned up {reaped} orphaned call record(s)")


async def _recover_stuck_dispatching() -> None:
    """Recover queue items left in 'dispatching' by a crashed worker.

    Runs on every dispatcher tick. Resets them to 'pending' so they retry,
    or 'failed' once MAX_RETRIES is reached.
    """
    queue_cutoff = datetime.now(timezone.utc) - timedelta(minutes=STUCK_DISPATCHING_MINUTES)
    # Filtered on when the item was *dispatched*, not when it was queued. Using queued_at meant
    # any call that had waited longer than the cutoff in the queue became "stuck" the instant it
    # was dispatched — so it was reset to pending and dialled a second time while its bridge
    # process was still alive and ringing the first one.
    stuck = await OutboundCallQueue.find(
        OutboundCallQueue.status == "dispatching",
        OutboundCallQueue.dispatched_at < queue_cutoff,
    ).to_list()
    if stuck:
        for item in stuck:
            item.retry_count += 1
            item.last_error = "Worker crashed mid-dispatch"
            if item.retry_count >= MAX_RETRIES:
                item.status = "failed"
            else:
                item.status = "pending"
            await item.save()
        logger.warning(
            f"Cleanup: recovered {len(stuck)} stuck 'dispatching' queue item(s)"
        )


async def _get_active_session_counts() -> dict[str, int]:
    """Live (initiated/answered) calls per bucket, plus mid-dispatch reservations.

    One aggregation rather than a query per bucket. The count runs on every inbound INVITE and
    every web-call request, so paying for N collection scans instead of one would be a real
    regression — see the (call_status, call_type) index on CallRecord.
    """
    counts = {bucket: _dispatching_count[bucket] for bucket in BUCKETS}
    pipeline = [
        {"$match": {"call_status": {"$in": LIVE_CALL_STATUSES}}},
        {"$group": {"_id": "$call_type", "n": {"$sum": 1}}},
    ]
    async for row in CallRecord.aggregate(pipeline):
        counts[bucket_for_call_type(row.get("_id"))] += row.get("n", 0)
    return counts


async def _get_active_session_count() -> int:
    """Total live sessions across every bucket."""
    return sum((await _get_active_session_counts()).values())


# Serialises the check-and-reserve below. Without it the `await` between counting active
# sessions and incrementing the counter let concurrent callers all observe the same pre-burst
# count and all pass — so a burst of inbound INVITEs sailed straight through the cap that
# exists precisely for bursts.
_slot_lock = asyncio.Lock()


async def try_reserve_slot(bucket: str = TELEPHONY) -> bool:
    """Atomically reserve a session slot in `bucket` if one is free.

    Two gates: the bucket's own cap, and the global ceiling across all buckets so the caps
    can never together exceed what the agent host can hold.
    """
    async with _slot_lock:
        counts = await _get_active_session_counts()
        if sum(counts.values()) >= settings.MAX_CONCURRENT_SESSIONS:
            logger.info(
                f"Slot refused ({bucket}): global ceiling reached "
                f"({sum(counts.values())}/{settings.MAX_CONCURRENT_SESSIONS})"
            )
            return False
        cap = BUCKET_CAPS[bucket]()
        if counts[bucket] >= cap:
            logger.info(f"Slot refused ({bucket}): bucket cap reached ({counts[bucket]}/{cap})")
            return False
        _dispatching_count[bucket] += 1
        return True


def release_slot(bucket: str = TELEPHONY) -> None:
    """Release a reservation taken by try_reserve_slot()."""
    if _dispatching_count[bucket] > 0:
        _dispatching_count[bucket] -= 1


def _terminate_bridge(process: multiprocessing.Process) -> None:
    """Send SIGTERM to bridge subprocess; ignore if already dead."""
    try:
        process.terminate()
    except OSError:
        pass  # process already exited


def _reap_bridge(process: multiprocessing.Process) -> None:
    """Join (reap) a bridge subprocess, escalating to SIGKILL if it will not exit.

    A bridge that hangs during shutdown used to survive as a zombie holding its RTP socket, so
    the port could not really be reused even after the pool handed it back.
    """
    try:
        process.join(timeout=3)
        if process.is_alive():
            logger.warning(
                f"[Bridge] Process {process.name} (pid={process.pid}) ignored SIGTERM; killing"
            )
            process.kill()
            process.join(timeout=3)
            if process.is_alive():
                logger.error(
                    f"[Bridge] Process {process.name} (pid={process.pid}) survived SIGKILL"
                )
    except Exception as e:
        logger.warning(f"[Bridge] Reaping {process.name} failed: {e}")


async def _finalize_if_agent_failed(room_name: str, assistant_id: str | None) -> None:
    """Safety net for a dead or stuck agent, run after the SIP bridge exits.

    session.py owns finalization — status, duration, and the end-call webhook — so wait
    for it before touching anything. Its teardown takes ~8s worst case (1s disconnect
    delay + 4s END_OF_CALL_GRACE_S + 3s transcript join), while this monitor notices the
    bridge exit within 2s. Force-writing "completed" straight away (the old behaviour)
    made session.py's end_call() hit its terminal-status guard and skip the webhook — so
    a caller-side hangup sent no webhook at all, while an agent-initiated end (no SIP
    BYE, bridge alive until delete_room) did.
    """
    # ponytail: poll the record, no lock or IPC event — one reader, and this is the rare path.
    for _ in range(FINALIZE_WAIT_SECONDS):
        record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if record and record.call_status in TERMINAL_CALL_STATUSES:
            return  # session.py finalized it; webhook already sent
        await asyncio.sleep(1.0)

    # Never finalized — the agent really did fail. end_call(), not update_call_status(),
    # because it also writes duration/billable and sends the webhook; status is still
    # "answered" here so its dedupe guard does not fire.
    logger.warning(f"Agent never finalized call — finalizing from dispatcher | room={room_name}")
    try:
        await livekit_services.end_call(room_name=room_name, assistant_id=assistant_id)
    except Exception as e:
        logger.error(f"Failed to finalize completed call | room={room_name}: {e}")


async def _watch_agent_join(
    room_name: str, assistant_id: str | None, *, already_answered: bool = False
) -> None:
    """Force-end a call whose agent never joined, even though the phone was answered.

    call_status="answered" is written from the SIP/telephony side alone (see
    _monitor_exotel_result and session.py's own "call_answered" handler) — it says nothing
    about whether session.py's entrypoint ever ran session.start() successfully. A crashed
    entrypoint, a bad provider key, or an overloaded worker can all leave a call answered
    with no agent behind it; without this watchdog that call sits in dead air, occupying a
    concurrency slot, until the caller eventually gives up and hangs up.

    Applies uniformly to Twilio outbound, Exotel outbound, and Exotel inbound — all three
    just need "was this call ever answered, and if so did the agent show up after." Inbound
    Exotel calls never write call_status="answered" at all (the 200 OK response *is* the
    answer, tracked only on the SIP side) — pass already_answered=True there to start the
    grace countdown immediately instead of waiting for a status transition that never comes.
    """
    loop = asyncio.get_running_loop()
    ring_deadline = loop.time() + AGENT_ANSWER_WAIT_SECONDS
    answered_since = loop.time() if already_answered else None

    while True:
        record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if not record or record.call_status in TERMINAL_CALL_STATUSES or record.agent_ready_at is not None:
            return  # call ended on its own, or the agent showed up — nothing to do

        now = loop.time()
        if answered_since is None and record.call_status == "answered":
            answered_since = now

        if answered_since is not None:
            if now - answered_since >= AGENT_JOIN_GRACE_SECONDS:
                break  # answered long enough ago with still no agent — give up on it
        elif now > ring_deadline:
            return  # never got answered within the normal ring window — not our problem

        await asyncio.sleep(1.0)

    logger.warning(f"Agent never joined after answer — ending silent call | room={room_name}")
    try:
        await livekit_services.end_call(room_name=room_name, assistant_id=assistant_id)
    except Exception as e:
        logger.error(f"Failed to end silent call | room={room_name}: {e}")


async def _monitor_exotel_result(
    room_name: str,
    assistant_id: str | None,
    result_queue: multiprocessing.Queue,
    bridge_process: multiprocessing.Process,
    port: int,
    call_id: str,
    is_passthrough: bool = False,
    passthrough_webhook_url: str | None = None,
) -> None:
    """Monitor the outbound bridge subprocess for its full lifetime.

    Phase 1 — SIP setup (max 60 s): poll result_queue for INVITE outcome.
    Phase 2 — Active call: wait for process to exit before releasing port.

    Port and call_id are released in finally, guaranteeing cleanup regardless
    of how the subprocess exits (normal end, crash, SIGTERM, or OOM).
    """
    async def _safe_finalize(reason: str) -> None:
        try:
            # The call may already be finalized — shutdown can land while we are waiting
            # out FINALIZE_WAIT_SECONDS below. Overwriting "completed" with "failed" would
            # corrupt the duration and send a second, contradictory webhook.
            existing = await CallRecord.find_one(CallRecord.room_name == room_name)
            if existing and existing.call_status in TERMINAL_CALL_STATUSES:
                logger.info(
                    f"Call already finalized with status={existing.call_status}; "
                    f"skipping finalize | room={room_name} | reason={reason}"
                )
                return
            await livekit_services.update_call_status(
                room_name=room_name,
                call_status="failed",
                call_status_reason=reason,
                ended_at=datetime.now(timezone.utc),
                call_duration_minutes=0,
            )
            # passthrough_webhook_url fires for failure outcomes too (busy/no-answer/timeout).
            # For normal calls it is None, so falls back to assistant's webhook URL as before.
            await livekit_services.send_end_call_webhook(
                room_name=room_name,
                assistant_id=assistant_id,
                webhook_url=passthrough_webhook_url,
            )
        except Exception as e:
            # Best-effort finalizer — keep swallowing, but never silently.
            logger.error(
                f"Failed to finalize call | room={room_name} | reason={reason}: {e}",
                exc_info=True,
            )

    from src.services.exotel.custom_sip_reach.port_pool import get_port_pool
    from src.services.exotel.custom_sip_reach.inbound_listener import unregister_call_id

    pool = get_port_pool()
    sip_result = None
    passthrough_egress_id: str | None = None  # hoisted so CancelledError handler can reference it

    try:
        # ── Phase 1: wait for SIP setup result ──────────────────────────────
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 60.0
        while loop.time() < deadline:
            try:
                sip_result = result_queue.get_nowait()
                break
            except _stdlib_queue.Empty:
                await asyncio.sleep(0.5)

        if sip_result is None:
            _terminate_bridge(bridge_process)
            logger.info(f"Bridge process terminated after timeout | room={room_name}")
            await livekit_services.update_call_status(
                room_name=room_name,
                call_status="timeout",
                call_status_reason="SIP call setup timed out",
                sip_status_code=None,
                sip_status_text="SIP timeout",
                ended_at=datetime.now(timezone.utc),
                call_duration_minutes=0,
            )
            await livekit_services.send_end_call_webhook(
                room_name=room_name, assistant_id=assistant_id, webhook_url=passthrough_webhook_url
            )
            logger.warning(f"Exotel SIP setup timed out | room={room_name}")
            return

        if not sip_result.get("success"):
            await livekit_services.update_call_status(
                room_name=room_name,
                call_status=sip_result.get("call_status", "failed"),
                call_status_reason=sip_result.get("error", "unknown"),
                sip_status_code=sip_result.get("sip_status_code"),
                sip_status_text=sip_result.get("sip_status_text"),
                ended_at=datetime.now(timezone.utc),
                call_duration_minutes=0,
            )
            await livekit_services.send_end_call_webhook(
                room_name=room_name, assistant_id=assistant_id, webhook_url=passthrough_webhook_url
            )
            logger.warning(
                f"Exotel SIP setup failed | room={room_name} | reason={sip_result.get('error', 'unknown')}"
            )
            return

        # ── Phase 2: SIP answered — wait for full call to end ────────────────
        # Port must NOT be released here; subprocess still owns the UDP socket.
        # Poll is_alive() so the event loop stays free during the call duration.
        logger.info(
            f"Exotel SIP answered | room={room_name} — waiting for bridge process to exit"
        )

        # Mark answered so call_duration_minutes is measured from pickup, not ring.
        await livekit_services.update_call_status(
            room_name=room_name,
            call_status="answered",
            answered_at=datetime.now(timezone.utc),
        )

        # Passthrough: no session.py running, so start recording here.
        if is_passthrough:
            try:
                recording_info = await livekit_services.start_room_recording(room_name)
                if recording_info and recording_info.get("success"):
                    passthrough_egress_id = recording_info["data"]["egress_id"]
                    logger.info(f"Passthrough recording started | egress={passthrough_egress_id}")
            except Exception as e:
                logger.error(f"Passthrough recording start failed | room={room_name}: {e}")

        while bridge_process.is_alive():
            await asyncio.sleep(2.0)
        logger.info(f"Bridge process exited | room={room_name}")

        if is_passthrough:
            # end_call() stops the egress recording (via call_record.recording_egress_id)
            # and marks status=completed. No session.py runs for passthrough calls.
            try:
                await livekit_services.end_call(room_name=room_name)
                if passthrough_webhook_url:
                    await livekit_services.send_end_call_webhook(
                        room_name=room_name,
                        webhook_url=passthrough_webhook_url,
                    )
            except Exception as e:
                logger.error(f"Passthrough end_call finalization failed | room={room_name}: {e}")
            await livekit_services.delete_room(room_name=room_name)
            return

        await _finalize_if_agent_failed(room_name, assistant_id)

    except asyncio.CancelledError:
        # Server shutting down — task cancelled. Write terminal status before re-raising
        # so the call doesn't stay stuck in 'initiated'/'answered' across restart.
        logger.warning(f"Monitor task cancelled (server shutdown) | room={room_name}")
        _terminate_bridge(bridge_process)
        # Stop any passthrough recording that was started before cancellation.
        if is_passthrough and passthrough_egress_id:
            await livekit_services.stop_room_recording(passthrough_egress_id)
        await _safe_finalize("Server shutdown during active call")
        raise

    except Exception as e:
        logger.error(f"Exotel monitor crashed | room={room_name}: {e}", exc_info=True)
        _terminate_bridge(bridge_process)
        await _safe_finalize(f"Monitor error: {e}")

    finally:
        # Reap zombie before releasing port — prevents the OS from keeping the
        # socket FD open in a zombie process while a new call tries to bind it.
        # Off the loop: the reap blocks on join() and can now escalate to SIGKILL, so it must
        # not stall the dispatcher's event loop and every other call running on it.
        await asyncio.to_thread(_reap_bridge, bridge_process)
        pool.release(port)
        unregister_call_id(call_id)
        logger.info(f"[MONITOR] Port {port} released, call_id {call_id} unregistered | room={room_name}")


async def _dispatch_queued_call(item: OutboundCallQueue) -> None:
    """Perform the actual LiveKit room creation + SIP dispatch for one queued call."""
    try:
        trunk = await OutboundSIP.find_one(
            OutboundSIP.trunk_id == item.trunk_id,
            OutboundSIP.trunk_is_active == True,
        )
        if not trunk:
            raise ValueError(f"Trunk {item.trunk_id} not found or inactive")

        is_passthrough = trunk.passthrough_mode

        if is_passthrough and item.passthrough_room_name:
            # Passthrough: room pre-created by endpoint, no AI agent dispatched.
            # Audio flows web-user ↔ RTP-bridge ↔ SIP with no session.py running.
            room_name = item.passthrough_room_name
        else:
            # Normal AI call: create room and dispatch agent worker.
            room_name = await livekit_services.create_room(item.assistant_id)
            job_metadata = dict(item.job_metadata)
            job_metadata["to_number"] = item.to_number
            job_metadata["call_service"] = item.call_service
            await livekit_services.create_agent_dispatch(room_name, job_metadata)

        if item.call_service == "twilio":
            await livekit_services.initialize_call_record(
                room_name=room_name,
                assistant_id=item.assistant_id,
                assistant_name=item.assistant_name,
                to_number=item.to_number,
                call_status="initiated",
                created_by_email=item.user_email,
                call_type="outbound",
                call_service="twilio",
                platform_number=(trunk.trunk_config.get("numbers") or [None])[0],
                queue_id=item.queue_id,
                is_passthrough=is_passthrough,
            )
            await livekit_services.create_sip_participant(
                room_name=room_name,
                to_number=item.to_number,
                trunk_id=item.trunk_id,
                participant_identity=uuid.uuid4().hex,
            )
            # Passthrough: no session.py runs, start recording here.
            # LiveKit SIP participant handles call lifecycle; orphan reaper finalizes the record.
            if is_passthrough:
                try:
                    await livekit_services.start_room_recording(room_name)
                except Exception as e:
                    logger.error(f"Twilio passthrough recording start failed | room={room_name}: {e}")
            else:
                # No equivalent of the Exotel monitor exists for Twilio — this is the only
                # thing that notices a Twilio call answered with no agent behind it.
                asyncio.create_task(_watch_agent_join(room_name, item.assistant_id))

        elif item.call_service == "exotel":
            from src.services.exotel.custom_sip_reach.bridge import _bridge_subprocess_entry
            from src.services.exotel.custom_sip_reach.port_pool import get_port_pool
            from src.services.exotel.custom_sip_reach.inbound_listener import register_call_id_with_event

            sip_config = trunk.trunk_config
            await livekit_services.initialize_call_record(
                room_name=room_name,
                assistant_id=item.assistant_id,
                assistant_name=item.assistant_name,
                to_number=item.to_number,
                call_status="initiated",
                created_by_email=item.user_email,
                call_type="outbound",
                call_service="exotel",
                platform_number=sip_config.get("exotel_number"),
                queue_id=item.queue_id,
                is_passthrough=is_passthrough,
            )

            # Pre-allocate resources in parent so monitor can release them
            # regardless of how the subprocess exits.
            pool = get_port_pool()
            bridge_port = pool.acquire()
            bridge_call_id = str(uuid.uuid4())
            ctx = get_bridge_context()
            inbound_bye = ctx.Event()
            register_call_id_with_event(bridge_call_id, inbound_bye)
            result_queue: multiprocessing.Queue = ctx.Queue()

            bridge_process = ctx.Process(
                target=_bridge_subprocess_entry,
                args=(item.to_number, room_name, sip_config, result_queue,
                      bridge_port, bridge_call_id, inbound_bye, is_passthrough),
                daemon=True,
                name=f"bridge-out-{item.to_number}",
            )
            bridge_process.start()
            asyncio.create_task(
                _monitor_exotel_result(
                    room_name, item.assistant_id, result_queue,
                    bridge_process, bridge_port, bridge_call_id,
                    is_passthrough=is_passthrough,
                    passthrough_webhook_url=trunk.passthrough_webhook_url,
                )
            )
            if not is_passthrough:
                # _monitor_exotel_result only reconciles status *after* the bridge process
                # exits (i.e. after the call is already over) — it doesn't catch a call
                # that's answered and silently agent-less while still ongoing. This does.
                asyncio.create_task(_watch_agent_join(room_name, item.assistant_id))

        # Targeted $set, not save(): save() writes the whole document from this task's stale
        # in-memory copy and would clobber any field another writer touched meanwhile.
        item.status = "dispatched"
        item.room_name = room_name
        await OutboundCallQueue.find_one(
            OutboundCallQueue.queue_id == item.queue_id
        ).update({"$set": {
            "status": "dispatched",
            "dispatched_at": datetime.now(timezone.utc),
            "room_name": room_name,
        }})
        logger.info(
            f"Dispatched queued call {item.queue_id} → room={room_name} | to={item.to_number}"
        )

    except Exception as e:
        logger.error(
            f"Failed to dispatch queued call {item.queue_id}: {e}", exc_info=True
        )
        item.retry_count += 1
        item.last_error = str(e)
        if item.retry_count >= MAX_RETRIES:
            item.status = "failed"
            logger.error(
                f"Queued call {item.queue_id} permanently failed after {MAX_RETRIES} retries"
            )
        else:
            item.status = "pending"
            logger.warning(
                f"Queued call {item.queue_id} will retry "
                f"(attempt {item.retry_count}/{MAX_RETRIES})"
            )
        await item.save()

    finally:
        release_slot(TELEPHONY)  # release reservation taken at top of this function


async def _process_pending() -> None:
    """Check queue and dispatch as many calls as current capacity allows."""
    try:
        counts = await _get_active_session_counts()
        active = counts[TELEPHONY]
        # Bounded by the telephony cap and by whatever the global ceiling still allows, so a
        # busy web tier cannot be crowded out by the outbound queue or vice versa.
        slots = min(
            settings.MAX_CONCURRENT_JOBS - active,
            settings.MAX_CONCURRENT_SESSIONS - sum(counts.values()),
        )

        if slots <= 0:
            logger.info(
                f"Dispatcher: telephony={active}, total={sum(counts.values())}, "
                f"no slots available (telephony max={settings.MAX_CONCURRENT_JOBS}, "
                f"global max={settings.MAX_CONCURRENT_SESSIONS})"
            )
            return

        pending = (
            await OutboundCallQueue.find(OutboundCallQueue.status == "pending")
            .sort("queued_at")
            .limit(slots)
            .to_list()
        )

        if not pending:
            logger.debug(f"Dispatcher: active={active}, slots={slots}, queue empty")
            return

        claimed = 0
        for item in pending:
            # Claimed with a conditional update rather than a read-then-save(). The old code
            # read the pending rows and then wrote status back unconditionally, so two
            # dispatchers (or one dispatcher racing its own stuck-item sweep) could both claim
            # the same row and dial the same number twice. The same reasoning is already
            # documented for CallRecord in livekit_svc.py.
            #
            # dispatched_at is stamped here, at claim time, because the stuck-item sweep
            # measures how long a row has been *dispatching*.
            claim = await OutboundCallQueue.find_one(
                OutboundCallQueue.queue_id == item.queue_id,
                OutboundCallQueue.status == "pending",
            ).update(
                {"$set": {
                    "status": "dispatching",
                    "dispatched_at": datetime.now(timezone.utc),
                }}
            )
            if getattr(claim, "modified_count", 1) == 0:
                logger.info(f"Queue item {item.queue_id} already claimed elsewhere; skipping")
                continue
            item.status = "dispatching"
            # Reserve before the task starts, to prevent double-dispatch.
            _dispatching_count[TELEPHONY] += 1
            claimed += 1
            asyncio.create_task(_dispatch_queued_call(item))

        logger.info(
            f"Dispatcher: active={active}, slots={slots}, "
            f"dispatching {claimed} call(s)"
        )
    except Exception as e:
        logger.error(f"Dispatcher process error: {e}", exc_info=True)


_TERMINAL_STATUSES = [
    "completed", "failed", "busy", "no_answer",
    "rejected", "cancelled", "unreachable", "timeout",
]


async def _watch_for_new_calls() -> None:
    """Change Stream: wakes dispatcher the moment a new call is inserted — cross-container."""
    while True:
        try:
            col = Database.client[settings.DATABASE_NAME]["outbound_call_queue"]
            async with await col.watch([{"$match": {"operationType": "insert"}}]) as stream:
                async for _ in stream:
                    logger.info("ChangeStream: new call queued → waking dispatcher")
                    _new_call_event.set()
        except Exception as e:
            logger.warning(f"ChangeStream (new calls) error, restarting in 5s: {e}")
            await asyncio.sleep(5)


async def _watch_for_call_completions() -> None:
    """Change Stream: wakes dispatcher when a call finishes → chain next pending call."""
    pipeline = [{
        "$match": {
            "operationType": "update",
            "updateDescription.updatedFields.call_status": {"$in": _TERMINAL_STATUSES},
        }
    }]
    while True:
        try:
            col = Database.client[settings.DATABASE_NAME]["call_records"]
            async with await col.watch(pipeline) as stream:
                async for _ in stream:
                    logger.info("ChangeStream: call completed → checking pending queue")
                    _new_call_event.set()
        except Exception as e:
            logger.warning(f"ChangeStream (completions) error, restarting in 5s: {e}")
            await asyncio.sleep(5)


async def _orphan_reaper_loop() -> None:
    """Run _reap_orphaned_calls() on a fixed interval forever."""
    while True:
        await asyncio.sleep(ORPHAN_REAPER_INTERVAL_SECONDS)
        try:
            await _reap_orphaned_calls()
        except Exception as e:
            logger.error(f"Orphan reaper error: {e}", exc_info=True)


async def outbound_dispatcher_loop() -> None:
    """Event-driven dispatcher: wakes instantly when a call is enqueued or completes.

    Change Streams provide cross-container notification. 30s poll is a safety-net fallback.
    """
    logger.info(f"Outbound call dispatcher started (max_concurrent={settings.MAX_CONCURRENT_JOBS})")

    await _fail_stale_calls_on_startup()
    await _process_pending()

    asyncio.create_task(_watch_for_new_calls())
    asyncio.create_task(_watch_for_call_completions())
    asyncio.create_task(_orphan_reaper_loop())

    while True:
        try:
            await asyncio.wait_for(_new_call_event.wait(), timeout=30.0)
        except asyncio.TimeoutError:
            pass  # safety-net poll
        finally:
            _new_call_event.clear()

        # Check for stuck dispatching
        await _recover_stuck_dispatching()
        await _process_pending()
