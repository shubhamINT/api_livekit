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
from src.core.logger import logger, setup_logging
from src.core.db.db_schemas import CallRecord, Assistant, ActivityLog

setup_logging()


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
    async def create_room(self, assistant_id: str) -> str:
        """Create and return a unique LiveKit room name for an assistant."""
        async with self.get_livekit_api() as lkapi:
            # Create a unique room name with agent name
            unique_room_name = f"{assistant_id}_{uuid.uuid4().hex[:8]}"

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
    ):
        """Append a transcript entry to an existing call record or create a new one."""
        # If room name present in call_records collection, update it
        call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if call_record:
            call_record.transcripts.append(
                {
                    "speaker": speaker,
                    "text": text,
                    "timestamp": datetime.now(timezone.utc),
                }
            )
            await call_record.save()
        else:
            # Create new call record
            call_record = CallRecord(
                room_name=room_name,
                assistant_id=assistant_id,
                assistant_name=assistant_name,
                to_number=to_number,
                recording_path=recording_path,
                transcripts=[
                    {
                        "speaker": speaker,
                        "text": text,
                        "timestamp": datetime.now(timezone.utc),
                    }
                ],
                started_at=datetime.now(timezone.utc),
            )
            await call_record.insert()

    async def initialize_call_record(
        self,
        room_name: str,
        assistant_id: str,
        assistant_name: str,
        to_number: str,
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
    ):
        """Create a call record if missing, or refresh base call metadata if present."""
        call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if call_record:
            call_record.assistant_id = assistant_id
            call_record.assistant_name = assistant_name
            call_record.to_number = to_number
            call_record.call_status = call_status
            call_record.call_status_reason = call_status_reason
            await call_record.save()
            return call_record

        call_record = CallRecord(
            room_name=room_name,
            assistant_id=assistant_id,
            assistant_name=assistant_name,
            to_number=to_number,
            call_status=call_status,
            call_status_reason=call_status_reason,
            started_at=datetime.now(timezone.utc),
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
        await call_record.save()
        return call_record

    async def send_end_call_webhook(self, room_name: str, assistant_id: str):
        """Send post-call details to the assistant's configured end-call webhook URL."""
        call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if not call_record:
            logger.info(f"No call record found for room: {room_name}; skipping webhook")
            return

        assistant = await Assistant.find_one(
            Assistant.assistant_id == assistant_id,
            Assistant.assistant_end_call_url != None,
            Assistant.assistant_end_call_url != "",
        )
        logger.info(f"Assistant found with assistant_id: {assistant_id}")

        if not (assistant and assistant.assistant_end_call_url):
            return

        end_call_url = assistant.assistant_end_call_url
        full_data = json.loads(call_record.model_dump_json())
        filtered_data = {key: value for key, value in full_data.items() if key not in ["id"]}
        payload = {
            "success": True,
            "message": "Call details fetched successfully",
            "data": filtered_data,
        }

        start_ms = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                _ = await client.post(end_call_url, json=payload)
                latency = int((time.monotonic() - start_ms) * 1000)
                logger.info(f"Call details sent to end call url: {end_call_url}")
                try:
                    await ActivityLog(
                        user_email=assistant.assistant_created_by_email,
                        log_type="end_call_webhook",
                        assistant_id=assistant_id,
                        room_name=room_name,
                        status="success",
                        request_data={"url": end_call_url},
                        latency_ms=latency,
                        message=f"Post-call data sent to {end_call_url}",
                    ).insert()
                except Exception as log_err:
                    logger.warning(f"Failed to write activity log for end_call_webhook: {log_err}")
        except Exception as e:
            latency = int((time.monotonic() - start_ms) * 1000)
            logger.error(f"Failed to send call details to webhook: {e}")
            try:
                await ActivityLog(
                    user_email=assistant.assistant_created_by_email,
                    log_type="end_call_webhook",
                    assistant_id=assistant_id,
                    room_name=room_name,
                    status="error",
                    request_data={"url": end_call_url},
                    latency_ms=latency,
                    message=f"Failed to send post-call data to {end_call_url}: {str(e)}",
                ).insert()
            except Exception as log_err:
                logger.warning(f"Failed to write activity log: {log_err}")

    # Update And send Details at the end of the call
    async def end_call(self, room_name: str, assistant_id: str):
        """Mark a call as completed, store duration, and trigger end-call webhook."""
        call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if call_record:
            if call_record.call_status in {
                "busy",
                "no_answer",
                "rejected",
                "cancelled",
                "unreachable",
                "timeout",
                "failed",
            }:
                logger.info(
                    f"Call already ended with status={call_record.call_status} for room: {room_name}; skipping duplicate webhook"
                )
                return

            call_record.ended_at = datetime.now(timezone.utc)
            call_record.call_duration_minutes = (
                call_record.ended_at - call_record.started_at
            ).total_seconds() / 60
            call_record.call_status = "completed"
            await call_record.save()
            logger.info(f"Call record ended for room: {room_name}")
            await self.send_end_call_webhook(room_name=room_name, assistant_id=assistant_id)


    async def start_room_recording(self, room_name: str, assistant_id: str) -> Optional[dict]:
        """Start recording the room using LiveKit Egress"""
        try:
            async with self.get_livekit_api() as lkapi:
                # Store the recording in Year/Month/Day/Timestamp.ogg format
                timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                folder_path = datetime.now(timezone.utc).strftime('%Y/%m/%d')
                filepath = f"lvk_call_recordings/{folder_path}/{assistant_id}/{timestamp}.ogg"

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
