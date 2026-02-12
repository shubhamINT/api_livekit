import uuid
import json
import httpx
from contextlib import asynccontextmanager
from typing import List, Optional, Dict
from datetime import datetime
from livekit import api
from livekit.api import LiveKitAPI
from livekit.protocol.sip import (
    CreateSIPOutboundTrunkRequest,
    SIPOutboundTrunkInfo,
    ListSIPOutboundTrunkRequest,
)
from src.core.config import settings
from src.core.logger import logger, setup_logging
from src.core.db.db_schemas import CallRecord, Assistant

setup_logging()


class LiveKitService:
    def __init__(self):
        self.api_key = settings.LIVEKIT_API_KEY
        self.api_secret = settings.LIVEKIT_API_SECRET
        self.url = settings.LIVEKIT_URL
        self.transcripts: List[Dict] = []

    @asynccontextmanager
    async def get_livekit_api(self):
        """
        Context manager for LiveKitAPI that handles initialization and cleanup.
        """
        lkapi = LiveKitAPI(
            self.url,
            self.api_key,
            self.api_secret,
        )
        try:
            yield lkapi
        finally:
            await lkapi.aclose()

    # Create livekit room
    async def create_room(self, assistant_id: str) -> str:
        async with self.get_livekit_api() as lkapi:
            # Create a unique room name with agent name
            unique_room_name = f"{assistant_id}_{uuid.uuid4().hex[:8]}"

            # Create room
            room = await lkapi.room.create_room(
                api.CreateRoomRequest(name=unique_room_name)
            )
            return room.name

    # Create agent dispatch
    async def create_agent_dispatch(self, room_name: str, metadata: dict = None):
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
    ):
        # If room name present in call_records collection, update it
        call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if call_record:
            call_record.transcripts.append(
                {
                    "speaker": speaker,
                    "text": text,
                    "timestamp": datetime.utcnow(),
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
                transcripts=[
                    {
                        "speaker": speaker,
                        "text": text,
                        "timestamp": datetime.utcnow(),
                    }
                ],
                started_at=datetime.utcnow(),
            )
            await call_record.insert()

    # Update And send Details at the end of the call
    async def end_call(self, room_name: str, assistant_id: str):
        """Update the call record with the end time"""
        call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
        if call_record:
            call_record.ended_at = datetime.utcnow()
            # Call clculate the call duration
            call_record.call_duration_minutes = (
                call_record.ended_at - call_record.started_at
            ).total_seconds() / 60
            await call_record.save()
            logger.info(f"Call record ended for room: {room_name}")

        # Get End call url from assistant
        assistant = await Assistant.find_one(
            Assistant.assistant_id == assistant_id,
            Assistant.assistant_end_call_url != None,
            Assistant.assistant_end_call_url != ""
        )
        
        if assistant and call_record:
            end_call_url = assistant.assistant_end_call_url
            
            # Serialize the Call record and format the data
            full_data = json.loads(call_record.model_dump_json())
            
            # Filter the data to include only requested fields
            # Exclude: id
            filtered_data = {
                key: value
                for key, value in full_data.items()
                if key not in ["id"]
            }
            
            payload = {
                "success": True,
                "message": "Call details fetched successfully",
                "data": filtered_data
            }
            
            # Send the Call record to the end call url
            try:
                async with httpx.AsyncClient() as client:
                    await client.post(end_call_url, json=payload)
                logger.info(f"Call details sent to end call url: {end_call_url}")
            except Exception as e:
                logger.error(f"Failed to send call details to webhook: {e}")


    async def start_room_recording(self, room_name: str) -> Optional[str]:
        """Start recording the room using LiveKit Egress"""
        try:
            async with self.get_livekit_api() as lkapi:
                timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
                filename = f"{room_name}_{timestamp}.ogg"

                file_output = api.EncodedFileOutput(
                    file_type=api.EncodedFileType.OGG,
                    filepath=f"/out/{filename}",  # Path inside container which is mapped to ./output-recordings/ on host
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
                return egress_info.egress_id

        except Exception as e:
            logger.error(f"Failed to start recording: {e}", exc_info=True)
            return None
