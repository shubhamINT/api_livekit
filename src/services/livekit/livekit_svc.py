import uuid
import json
import logging
from contextlib import asynccontextmanager
from typing import List, Optional
from livekit.api import (
    LiveKitAPI,
    CreateRoomRequest,
    CreateAgentDispatchRequest,
    CreateSIPParticipantRequest,
    ListRoomsRequest
)
from livekit.protocol.sip import (
    CreateSIPOutboundTrunkRequest,
    SIPOutboundTrunkInfo,
    ListSIPOutboundTrunkRequest
)
from livekit import api as lk_api
from src.core.config import settings

class LiveKitService:
    def __init__(self):
        self.api_key = settings.LIVEKIT_API_KEY
        self.api_secret = settings.LIVEKIT_API_SECRET
        self.url = settings.LIVEKIT_URL

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
    async def create_room(self, agent: str) -> str:
        async with self.get_livekit_api() as lkapi:
            
            # Create a unique room name with agent name
            unique_room_name = f"{agent}_{uuid.uuid4().hex[:8]}"

            # Create room
            room = await lkapi.room.create_room(CreateRoomRequest(name=unique_room_name))
            logger.info(f"Room created: {room.name}")
            return room.name
            
    
    # Create agent dispatch
    async def create_agent_dispatch(self, room_name: str) -> str:
        async with self.get_livekit_api() as lkapi:
            
            # Create agent dispatch
            agent_dispatch = await lkapi.agent_dispatch.create_dispatch(
                CreateAgentDispatchRequest(
                    room=room_name,
                    agent_name="api-agent",
                )
            )


    def get_token(self, identity: str, name: str, agent: str, room: Optional[str] = None, email: Optional[str] = None) -> str:
        metadata = {
            "agent": agent,
            "user_email": email
        }
        
        token = (
            lk_api.AccessToken(self.api_key, self.api_secret)
            .with_identity(identity)
            .with_name(name)
            .with_metadata(json.dumps(metadata))
            .with_grants(
                lk_api.VideoGrants(
                    room_join=True,
                    room=room,
                )
            )
        )
        return token.to_jwt()


    # Create Outbound trunk
    async def create_sip_outbound_trunk(
        trunk_name: str,
        trunk_address: str,
        trunk_numbers: list,
        trunk_auth_username: str,
        trunk_auth_password: str
    ):
        
        async with get_livekit_api() as lkapi:
            trunk_info = SIPOutboundTrunkInfo(
                name=trunk_name,
                address=trunk_address,
                numbers=trunk_numbers,
                auth_username=trunk_auth_username,
                auth_password=trunk_auth_password
            )
            
            request = CreateSIPOutboundTrunkRequest(trunk=trunk_info)
            trunk = await lkapi.sip.create_sip_outbound_trunk(request)
            
            logger.info(f"Successfully created trunk: {trunk_name}")
        return trunk
