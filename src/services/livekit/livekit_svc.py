import asyncio
import uuid
import json
import time
import httpx
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Literal
from datetime import datetime, timezone
from livekit import api
from livekit.api import LiveKitAPI, AccessToken, VideoGrants
from livekit.protocol.sip import (
    CreateSIPOutboundTrunkRequest,
    SIPOutboundTrunkInfo,
    # ListSIPOutboundTrunkRequest,
)
from src.core.config import settings
from src.core.logger import logger
from src.core.billing import calculate_billable_duration_minutes, NON_BILLABLE_FINAL_STATUSES
from src.core.db.db_schemas import CallRecord, Assistant, ActivityLog, UsageRecord


PASSTHROUGH_ROOM_PREFIX = "passthrough"

# A call that reached any of these is finalized: duration written and end-call webhook
# already sent. Both end_call()'s dedupe guard and the dispatcher's safety net read this,
# so the two can't drift apart on what "already ended" means.
TERMINAL_CALL_STATUSES = NON_BILLABLE_FINAL_STATUSES | {"completed"}


class LiveKitService:
    # Shared client reused across all operations to avoid per-call connection overhead
    _shared_client: LiveKitAPI | None = None

    def __init__(self):
        """Initialize service configuration and in-memory transcript storage."""
        self.api_key = settings.LIVEKIT_API_KEY
        self.api_secret = settings.LIVEKIT_API_SECRET
        self.url = settings.LIVEKIT_URL
        self.transcripts: List[Dict] = []

    def _get_client(self) -> LiveKitAPI:
        """Return shared LiveKitAPI client, creating it on first use."""
        if LiveKitService._shared_client is None:
            LiveKitService._shared_client = LiveKitAPI(
                self.url,
                self.api_key,
                self.api_secret,
            )
        return LiveKitService._shared_client

    @asynccontextmanager
    async def get_livekit_api(self):
        """Context manager kept for backward compatibility — returns shared client."""
        yield self._get_client()

    # Create livekit room
    async def create_room(self, assistant_id: Optional[str] = None) -> str:
        """Create and return a unique LiveKit room name."""
        async with self.get_livekit_api() as lkapi:
            prefix = assistant_id if assistant_id else PASSTHROUGH_ROOM_PREFIX
            unique_room_name = f"{prefix}_{uuid.uuid4().hex[:8]}"

            # Create room
            room = await lkapi.room.create_room(
                api.CreateRoomRequest(name=unique_room_name)
            )
            return room.name

    # Create agent dispatch
    async def create_agent_dispatch(self, room_name: str, metadata: Optional[dict] = None):
        """Create an agent dispatch for a room with optional metadata."""
        async with self.get_livekit_api() as lkapi:
            # Create agent dispatch with metadata
            agent_dispatch = await lkapi.agent_dispatch.create_dispatch(
                api.CreateAgentDispatchRequest(
                    room=room_name,
                    agent_name="api-agent",
                    metadata=json.dumps(metadata) if metadata else "",
                )
            )
            return agent_dispatch

    # Create Outbound trunk
    async def create_sip_outbound_trunk(
        self,
        trunk_name: str,
        trunk_address: str,
        trunk_numbers: list,
        trunk_auth_username: str,
        trunk_auth_password: str,
    ):
        """Create and return a SIP outbound trunk in LiveKit."""
        async with self.get_livekit_api() as lkapi:
            trunk_info = SIPOutboundTrunkInfo(
                name=trunk_name,
                address=trunk_address,
                numbers=trunk_numbers,
                auth_username=trunk_auth_username,
                auth_password=trunk_auth_password,
            )

            request = CreateSIPOutboundTrunkRequest(trunk=trunk_info)
            trunk = await lkapi.sip.create_sip_outbound_trunk(request)

        return trunk

    # Create SIP participant
    async def create_sip_participant(
        self,
        room_name: str,
        to_number: str,
        trunk_id: str,
        participant_identity: str,
    ):
        """Dial out by adding a SIP participant to a room via a trunk."""
        async with self.get_livekit_api() as lkapi:
            participant = await lkapi.sip.create_sip_participant(
                api.CreateSIPParticipantRequest(
                    room_name=room_name,
                    sip_trunk_id=trunk_id,
                    sip_call_to=to_number,
                    participant_identity=participant_identity,
                    krisp_enabled=True,
                )
            )
            return participant

    # Add transcript
    async def add_transcript(
        self,
        room_name: str,
        speaker: str,
        text: str,
        assistant_id: str,
        assistant_name: str,
        to_number: str,
        recording_path: Optional[str],
        created_by_email: Optional[str] = None,
        call_type: Optional[str] = None,
        call_service: Optional[str] = None,
        platform_number: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ):
        """Append a transcript entry to an existing call record or create a new one.

        `timestamp` is when the utterance was captured, not when it is written. User
        transcripts come back from Sarvam after a network round-trip, so they can be
        written after the agent reply they triggered — the $sort below slots them back
        into speaking order.
        """
        entry = {
            "speaker": speaker,
            "text": text,
            "timestamp": timestamp or datetime.now(timezone.utc),
        }
        # Atomic append. A read-modify-save() here would race the other writers of this
        # document (update_call_status, end_call, the dispatcher safety net) and could
        # overwrite transcripts with a stale snapshot.
        result = await CallRecord.find_one(CallRecord.room_name == room_name).update(
            {"$push": {"transcripts": {"$each": [entry], "$sort": {"timestamp": 1}}}}
        )
        if getattr(result, "matched_count", 0) == 0:
            # Create new call record (fallback if initialize_call_record was not called)
            call_record = CallRecord(
                room_name=room_name,
                assistant_id=assistant_id,
                assistant_name=assistant_name,
                to_number=to_number,
                recording_path=recording_path,
                transcripts=[entry],
                started_at=datetime.now(timezone.utc),
                created_by_email=created_by_email,
                call_type=call_type,
                call_service=call_service,
                platform_number=platform_number,
            )
            await call_record.insert()

    async def initialize_call_record(
        self,
        room_name: str,
        to_number: str = "",
        assistant_id: Optional[str] = None,
        assistant_name: Optional[str] = None,
        call_status: Literal[
            "initiated",
            "answered",
            "completed",
            "failed",
            "busy",
            "no_answer",
            "rejected",
            "cancelled",
            "unreachable",
            "timeout",
        ] = "initiated",
        call_status_reason: Optional[str] = None,
        created_by_email: Optional[str] = None,
        call_type: Optional[str] = None,
        call_service: Optional[str] = None,
        platform_number: Optional[str] = None,
        queue_id: Optional[str] = None,
        is_passthrough: bool = False,
    ):
        """Create a call record if missing, or refresh base call metadata if present."""
        call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if call_record:
            call_record.assistant_id = assistant_id
            call_record.assistant_name = assistant_name
            call_record.to_number = to_number
            call_record.call_status = call_status
            call_record.call_status_reason = call_status_reason
            call_record.is_passthrough = is_passthrough
            if created_by_email:
                call_record.created_by_email = created_by_email
            if call_type:
                call_record.call_type = call_type
            if call_service:
                call_record.call_service = call_service
            if platform_number:
                call_record.platform_number = platform_number
            if queue_id:
                call_record.queue_id = queue_id
            await call_record.save()
            return call_record

        call_record = CallRecord(
            room_name=room_name,
            queue_id=queue_id,
            assistant_id=assistant_id,
            assistant_name=assistant_name,
            to_number=to_number,
            call_status=call_status,
            call_status_reason=call_status_reason,
            started_at=datetime.now(timezone.utc),
            created_by_email=created_by_email,
            call_type=call_type,
            call_service=call_service,
            platform_number=platform_number,
            is_passthrough=is_passthrough,
        )
        await call_record.insert()
        return call_record

    async def update_call_status(
        self,
        room_name: str,
        call_status: Literal[
            "initiated",
            "answered",
            "completed",
            "failed",
            "busy",
            "no_answer",
            "rejected",
            "cancelled",
            "unreachable",
            "timeout",
        ],
        call_status_reason: Optional[str] = None,
        sip_status_code: Optional[int] = None,
        sip_status_text: Optional[str] = None,
        answered_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        call_duration_minutes: Optional[float] = None,
    ):
        """Update call status fields for a room and persist the changes."""
        call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if not call_record:
            return None

        call_record.call_status = call_status
        call_record.call_status_reason = call_status_reason
        if sip_status_code is not None:
            call_record.sip_status_code = sip_status_code
        if sip_status_text is not None:
            call_record.sip_status_text = sip_status_text
        if answered_at is not None:
            call_record.answered_at = answered_at
        if ended_at is not None:
            call_record.ended_at = ended_at
        if call_duration_minutes is not None:
            call_record.call_duration_minutes = call_duration_minutes
            call_record.billable_duration_minutes = calculate_billable_duration_minutes(
                call_status=call_status,
                call_duration_minutes=call_duration_minutes,
            )
        elif call_status in NON_BILLABLE_FINAL_STATUSES:
            call_record.billable_duration_minutes = 0
        await call_record.save()
        return call_record

    async def mark_agent_ready(self, room_name: str) -> None:
        """Record that the agent actually joined and started running in this room.

        Deliberately separate from update_call_status: this only ever sets one timestamp
        and must never touch call_status/call_status_reason.
        """
        call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if call_record and call_record.agent_ready_at is None:
            call_record.agent_ready_at = datetime.now(timezone.utc)
            await call_record.save()

    async def _post_end_call_webhook(
        self, url: str, payload: dict, room_name: str, webhook_config=None
    ) -> tuple[str, Optional[dict], str]:
        """POST the post-call payload, retrying a slow or failing receiver.

        Returns `(status, response_data, message)` in the shape the ActivityLog row wants.

        A receiver that answers slowly is the normal case, not a fault: most of them write
        the payload into their own database before replying, so the read timeout is
        generous (END_CALL_WEBHOOK_TIMEOUT, default 30s) while the connect timeout stays
        short — an unreachable host should fail in seconds. Timeouts, transport errors,
        429 and 5xx are retried with a 1s/2s/4s backoff; a 4xx is not, because the receiver
        has already read the payload and decided about it.

        `webhook_config` is the assistant's own `assistant_end_call_webhook`, which overrides
        either default per assistant — the right timeout belongs to the receiver, and one
        global value has to suit the slowest of them. Absent, or with null fields, means the
        server default.

        Failures log one line, never a traceback: the stack is always httpx's own transport
        chain and carries nothing the exception name does not.
        """
        configured_timeout = getattr(webhook_config, "timeout_seconds", None)
        configured_attempts = getattr(webhook_config, "attempts", None)
        attempts = max(1, configured_attempts or settings.END_CALL_WEBHOOK_ATTEMPTS)
        timeout = httpx.Timeout(
            configured_timeout or settings.END_CALL_WEBHOOK_TIMEOUT, connect=10.0
        )
        last: tuple[str, Optional[dict], str] = (
            "error",
            None,
            f"Failed to send post-call data to {url}: no attempt was made",
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            for attempt in range(1, attempts + 1):
                retryable = True
                try:
                    response = await client.post(url, json=payload)
                except Exception as e:
                    last = (
                        "error",
                        None,
                        f"Failed to send post-call data to {url}: {type(e).__name__}: {e}",
                    )
                    logger.warning(
                        f"End call webhook attempt {attempt}/{attempts} failed | "
                        f"room={room_name} | url={url} | {type(e).__name__}: {e}"
                    )
                else:
                    # ponytail: body truncated to 500 chars — enough to identify a
                    # rejecting endpoint without storing arbitrary payloads in Mongo.
                    body = (response.text or "")[:500]
                    response_data = {"status_code": response.status_code, "body": body}
                    if 200 <= response.status_code < 300:
                        logger.info(
                            f"Call details sent to end call url: {url} | room={room_name} "
                            f"| HTTP {response.status_code} | attempt {attempt}/{attempts}"
                        )
                        return (
                            "success",
                            response_data,
                            f"Post-call data sent to {url} (HTTP {response.status_code})",
                        )
                    last = (
                        "error",
                        response_data,
                        (
                            f"Webhook rejected post-call data: {url} returned "
                            f"HTTP {response.status_code}: {body}"
                        ),
                    )
                    retryable = response.status_code == 429 or response.status_code >= 500
                    if not retryable:
                        logger.error(
                            f"End call webhook returned non-2xx | room={room_name} "
                            f"| url={url} | HTTP {response.status_code} | body={body}"
                        )
                        return last
                    logger.warning(
                        f"End call webhook attempt {attempt}/{attempts} returned "
                        f"HTTP {response.status_code} | room={room_name} | url={url}"
                    )

                if attempt < attempts:
                    await asyncio.sleep(2 ** (attempt - 1))

        logger.error(
            f"End call webhook gave up after {attempts} attempts | room={room_name} "
            f"| url={url} | {last[2]}"
        )
        return last

    async def send_end_call_webhook(self, room_name: str, assistant_id: Optional[str] = None, webhook_url: Optional[str] = None):
        """Send post-call details to a webhook URL.

        webhook_url takes priority; if absent, falls back to assistant's end_call_url.
        """
        call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if not call_record:
            logger.info(f"No call record found for room: {room_name}; skipping webhook")
            return

        # Resolve webhook target
        end_call_url = webhook_url
        assistant = None
        if not end_call_url and assistant_id:
            assistant = await Assistant.find_one(
                Assistant.assistant_id == assistant_id,
                Assistant.assistant_end_call_url != None,
                Assistant.assistant_end_call_url != "",
            )
            if assistant and assistant.assistant_end_call_url:
                end_call_url = assistant.assistant_end_call_url
                logger.info(f"Resolved end call url from assistant_id: {assistant_id}")
            else:
                # The query filters on a non-empty URL, so None here means
                # "no end-call URL configured", not "assistant does not exist".
                logger.info(f"No assistant_end_call_url configured for assistant_id: {assistant_id}")

        if not end_call_url:
            logger.info(
                f"No end call webhook url resolved; skipping webhook | room={room_name} "
                f"| assistant_id={assistant_id} | webhook_url_arg={'set' if webhook_url else 'unset'}"
            )
            return
        full_data = json.loads(call_record.model_dump_json())
        filtered_data = {key: value for key, value in full_data.items() if key not in ["id"]}

        # Enrich with usage data if available
        usage_record = await UsageRecord.find_one(UsageRecord.room_name == room_name)
        if usage_record:
            filtered_data["usage"] = {
                "mode": usage_record.mode,
                "call_duration_minutes": usage_record.call_duration_minutes,
                "call_service": usage_record.call_service,
                "tts_provider": usage_record.tts_provider,
                "llm_realtime_provider": usage_record.llm_realtime_provider,
                "llm_model": usage_record.llm_model,
                "llm_input_tokens": usage_record.llm_input_tokens,
                "llm_output_tokens": usage_record.llm_output_tokens,
                "llm_input_audio_tokens": usage_record.llm_input_audio_tokens,
                "llm_input_text_tokens": usage_record.llm_input_text_tokens,
                "llm_input_image_tokens": usage_record.llm_input_image_tokens,
                "llm_output_audio_tokens": usage_record.llm_output_audio_tokens,
                "llm_output_text_tokens": usage_record.llm_output_text_tokens,
                "llm_total_tokens": usage_record.llm_total_tokens,
                # Cached counts are a subset of the input counts above, not an addition
                # to them — see UsageRecord in db_schemas.py before pricing off these.
                "llm_input_cached_tokens": usage_record.llm_input_cached_tokens,
                "llm_input_cached_audio_tokens": usage_record.llm_input_cached_audio_tokens,
                "llm_input_cached_text_tokens": usage_record.llm_input_cached_text_tokens,
                "llm_input_cached_image_tokens": usage_record.llm_input_cached_image_tokens,
                "llm_input_cache_creation_tokens": usage_record.llm_input_cache_creation_tokens,
                "llm_session_duration": usage_record.llm_session_duration,
                "tts_characters_count": usage_record.tts_characters_count,
                "tts_audio_duration": usage_record.tts_audio_duration,
                # Token-billed TTS providers only; character-billed ones report zero.
                "tts_input_tokens": usage_record.tts_input_tokens,
                "tts_output_tokens": usage_record.tts_output_tokens,
                # Zero only in Gemini realtime — see UsageRecord in db_schemas.py.
                "stt_provider": usage_record.stt_provider,
                "stt_model": usage_record.stt_model,
                "stt_audio_duration": usage_record.stt_audio_duration,
                # Token-billed STT (OpenAI) only; duration-billed providers report zero.
                "stt_input_tokens": usage_record.stt_input_tokens,
                # Subsets of stt_input_tokens, never additional to it.
                "stt_input_audio_tokens": usage_record.stt_input_audio_tokens,
                "stt_input_text_tokens": usage_record.stt_input_text_tokens,
                "stt_output_tokens": usage_record.stt_output_tokens,
                "usage_schema_version": usage_record.usage_schema_version,
                "model_usage": usage_record.model_usage,
                "sdk_version": usage_record.sdk_version,
                # False means the worker never reached teardown, so these counts are the
                # last mid-call snapshot rather than the final total.
                "usage_finalized": usage_record.usage_finalized,
            }

        payload = {
            "success": True,
            "message": "Call details fetched successfully",
            "data": filtered_data,
        }

        log_owner = (assistant.assistant_created_by_email if assistant else None) or call_record.created_by_email or "unknown"
        start_ms = time.monotonic()
        # Per-assistant delivery settings, when this webhook was resolved from an assistant. A
        # caller-supplied `webhook_url` (the passthrough trunk path) has no assistant behind it
        # and takes the server defaults.
        status, response_data, message = await self._post_end_call_webhook(
            end_call_url,
            payload,
            room_name,
            webhook_config=getattr(assistant, "assistant_end_call_webhook", None),
        )
        latency = int((time.monotonic() - start_ms) * 1000)

        try:
            await ActivityLog(
                user_email=log_owner,
                log_type="end_call_webhook",
                assistant_id=assistant_id,
                room_name=room_name,
                status=status,
                request_data={"url": end_call_url},
                response_data=response_data,
                latency_ms=latency,
                message=message,
            ).insert()
        except Exception as log_err:
            logger.warning(f"Failed to write activity log for end_call_webhook: {log_err}")

    # Update And send Details at the end of the call
    async def end_call(self, room_name: str, assistant_id: Optional[str] = None):
        """Mark a call as completed, store duration, and trigger end-call webhook."""
        call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if call_record:
            if call_record.call_status in TERMINAL_CALL_STATUSES:
                # Dispatcher safety net may have set status="completed" before session.py ran
                # end_call(), skipping duration. Patch it here without re-sending the webhook.
                if call_record.call_duration_minutes is None:
                    ended_at = call_record.ended_at or datetime.now(timezone.utc)
                    duration_start = call_record.answered_at or call_record.started_at
                    if duration_start is None:
                        logger.warning(f"Cannot patch duration for room {room_name}: no start time on record")
                    else:
                        call_record.call_duration_minutes = (ended_at - duration_start).total_seconds() / 60
                        call_record.billable_duration_minutes = calculate_billable_duration_minutes(
                            call_status=call_record.call_status,
                            call_duration_minutes=call_record.call_duration_minutes,
                        )
                        await call_record.save()
                        logger.info(f"Patched missing duration for room: {room_name} | {call_record.call_duration_minutes:.2f}min")
                logger.info(
                    f"Call already ended with status={call_record.call_status} for room: {room_name}; skipping duplicate webhook"
                )
                return

            if call_record.recording_egress_id:
                logger.info(f"Stopping room recording for room: {room_name}")
                await self.stop_room_recording(call_record.recording_egress_id)

            call_record.ended_at = datetime.now(timezone.utc)
            duration_start = call_record.answered_at or call_record.started_at
            call_record.call_duration_minutes = (
                call_record.ended_at - duration_start
            ).total_seconds() / 60
            call_record.billable_duration_minutes = calculate_billable_duration_minutes(
                call_status="completed",
                call_duration_minutes=call_record.call_duration_minutes,
            )
            call_record.call_status = "completed"
            await call_record.save()
            logger.info(f"Call record ended for room: {room_name}")
            await self.send_end_call_webhook(room_name=room_name, assistant_id=assistant_id)


    async def mute_room_audio_inputs(self, room_name: str) -> None:
        """Mute all participants' audio tracks in a room via the LiveKit Server API."""
        try:
            async with self.get_livekit_api() as lkapi:
                participants = await lkapi.room.list_participants(
                    api.ListParticipantsRequest(room=room_name)
                )
                for participant in participants.participants:
                    for track in participant.tracks:
                        if track.type == 0:  # TrackType.AUDIO
                            await lkapi.room.mute_published_track(
                                api.MuteRoomTrackRequest(
                                    room=room_name,
                                    identity=participant.identity,
                                    track_sid=track.sid,
                                    muted=True,
                                )
                            )
            logger.info(f"Muted all audio inputs in room {room_name}")
        except Exception as e:
            logger.warning(f"Failed to mute room audio inputs: {e}")

    async def room_exists(self, room_name: str) -> bool:
        """Return True if the LiveKit room is still active."""
        async with self.get_livekit_api() as lkapi:
            result = await lkapi.room.list_rooms(api.ListRoomsRequest(names=[room_name]))
            return len(result.rooms) > 0

    async def delete_room(self, room_name: str):
        """Delete a LiveKit room, terminating all SIP connections and participants."""
        try:
            async with self.get_livekit_api() as lkapi:
                await lkapi.room.delete_room(api.DeleteRoomRequest(room=room_name))
            logger.info(f"Room deleted: {room_name}")
        except Exception as e:
            logger.error(f"Failed to delete room {room_name}: {e}", exc_info=True)

    async def start_room_recording(self, room_name: str, assistant_id: Optional[str] = None) -> Optional[dict]:
        """Start recording the room using LiveKit Egress"""
        try:
            async with self.get_livekit_api() as lkapi:
                # Store the recording in Year/Month/Day/Timestamp.ogg format
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                folder_path = datetime.now(timezone.utc).strftime('%Y/%m/%d')
                path_key = assistant_id if assistant_id else "passthrough"
                filepath = f"lvk_call_recordings/{folder_path}/{path_key}/{timestamp}.ogg"

                # Set the file output
                file_output = api.EncodedFileOutput(
                    file_type=api.EncodedFileType.OGG,
                    filepath=filepath,  # Path or the s3 key
                    s3=api.S3Upload(
                        access_key=settings.AWS_ACCESS_KEY_ID,
                        secret=settings.AWS_SECRET_ACCESS_KEY,
                        region=settings.AWS_REGION,
                        bucket=settings.S3_BUCKET_NAME,
                    )
                )

                # Start room composite recording (records all participants)
                egress_info = await lkapi.egress.start_room_composite_egress(
                    api.RoomCompositeEgressRequest(
                        room_name=room_name,
                        file_outputs=[file_output],
                        audio_only=True,
                    )
                )

                logger.info(f"Recording started: {egress_info.egress_id}")

                # Create S3 URL
                s3_url = f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{filepath}"
                call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
                if call_record:
                    call_record.recording_path = s3_url
                    call_record.recording_egress_id = egress_info.egress_id
                    await call_record.save()

                payload = {
                    "success": True,
                    "message": "Recording started successfully",
                    "data": {
                        "egress_id": egress_info.egress_id,
                        "room_name": room_name,
                        "s3_url": s3_url,
                    }
                }
                return payload

        except Exception as e:
            logger.error(f"Failed to start recording: {e}", exc_info=True)
            return None

    async def stop_room_recording(self, egress_id: str) -> bool:
        """Stop an active LiveKit egress recording by egress id."""
        try:
            async with self.get_livekit_api() as lkapi:
                await lkapi.egress.stop_egress(api.StopEgressRequest(egress_id=egress_id))
                logger.info(f"Recording stopped: {egress_id}")
                return True
        except Exception as e:
            logger.warning(f"Failed to stop recording {egress_id}: {e}")
            return False


    # Create token for web call — user joins room, agent is auto-dispatched via RoomConfiguration
    async def create_token(self, room_name: str, metadata: Optional[dict] = None) -> Optional[str]:
        """Generate a JWT token that allows a user to join and publish in a room."""
        try:
            at = AccessToken(self.api_key, self.api_secret)
            at.with_identity(f"user-{uuid.uuid4().hex[:8]}")

            # Grant room join with publish + subscribe
            at.with_grants(VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            ))

            # Attach metadata as participant metadata
            at.with_metadata(json.dumps(metadata) if metadata else "")

            return at.to_jwt()
        except Exception as e:
            logger.error(f"Failed to create token: {e}", exc_info=True)
            return None
