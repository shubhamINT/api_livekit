from fastapi import APIRouter, HTTPException, Depends
from src.api.models.api_schemas import TriggerOutboundCall
from src.api.models.response_models import apiResponse
from src.core.db.db_schemas import OutboundSIP, APIKey, Assistant
from src.api.dependencies import get_current_user
from src.core.logger import logger, setup_logging
from src.services.livekit.livekit_svc import LiveKitService
from google.protobuf.json_format import MessageToDict
import uuid
import json

router = APIRouter()
setup_logging()
livekit_services = LiveKitService()


# Triggure Ouboud call
@router.post("/outbound")
async def trigger_outbound_call(request: TriggerOutboundCall, current_user: APIKey = Depends(get_current_user)):
    
    logger.info(f"Received request to trigger outbound call for user: {current_user.user_email}")

    # Check if the call_service is twilio
    if request.call_service != "twilio":
        raise HTTPException(
            status_code=400,
            detail="Call service not supported, currently only twilio is supported",
        )

    # Check of the assistant exists for the user
    assistant = await Assistant.find_one(
        Assistant.assistant_id == request.assistant_id,
        Assistant.assistant_created_by_email == current_user.user_email,
    )
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found in DB")

    # # Check of the trunk exists for the user
    # trunk = await OutboundSIP.find_one(OutboundSIP.trunk_id == request.trunk_id, OutboundSIP.trunk_created_by_email == current_user.user_email)
    # if not trunk:
    #     raise HTTPException(status_code=404, detail="Trunk not found in DB")

    # Create room
    logger.info(f"Creating room for assistant: {request.assistant_id}")
    room_name = await livekit_services.create_room(request.assistant_id)

    # Prepare job metadata with to_number and custom metadata
    job_metadata = request.metadata or {}
    job_metadata["to_number"] = request.to_number

    # Create agent dispatch with metadata (passing metadata through job, not room)
    logger.info(f"Creating agent dispatch for room: {room_name}")
    agent_dispatch = await livekit_services.create_agent_dispatch(room_name, job_metadata)

    # Create SIP participant (no participant metadata needed)
    logger.info(f"Creating SIP participant for room: {room_name}")
    participant = await livekit_services.create_sip_participant(
        room_name=room_name,
        to_number=request.to_number,
        trunk_id=request.trunk_id,
        participant_identity=uuid.uuid4().hex,
    )

    # Return response
    return apiResponse(
        success=True,
        message="Outbound call triggered successfully",
        data={
            "room_name": room_name,
            "agent_dispatch": MessageToDict(agent_dispatch),
            "participant": MessageToDict(participant),
        },
    )
