from fastapi import APIRouter, HTTPException, Depends
from src.api.models.response_models import apiResponse
from src.core.db.db_schemas import Assistant, APIKey
from src.api.dependencies import get_current_user
from src.core.logger import logger
from src.services.livekit.livekit_svc import LiveKitService
from src.api.models.api_schemas import TriggerWebCall
from src.services.outbound_dispatcher.dispatcher import WEB, release_slot, try_reserve_slot
from google.protobuf.json_format import MessageToDict

router = APIRouter()
livekit_services = LiveKitService()

# Generate Web Call Token
@router.post("/get_token")
async def get_token(request: TriggerWebCall, current_user: APIKey = Depends(get_current_user)):
    slot_held = False
    try:
        logger.info(f"Web call token requested by: {current_user.user_email} for assistant: {request.assistant_id}")

        # Verify the assistant belongs to this user
        assistant = await Assistant.find_one(
            Assistant.assistant_id == request.assistant_id,
            Assistant.assistant_created_by_email == current_user.user_email,
        )
        if not assistant:
            raise HTTPException(status_code=404, detail="Assistant not found")

        # Text-only mode is incompatible with realtime assistants (Gemini/OpenAI realtime
        # bundle STT+LLM+TTS in one model and do not expose a pure-text path).
        if request.text_only and assistant.assistant_mode == "realtime":
            raise HTTPException(
                status_code=400,
                detail="text_only is not supported for realtime assistants. Use a pipeline-mode assistant.",
            )

        # Web calls dispatch a real agent and write a CallRecord, so they need capacity of
        # their own — they used to skip the cap entirely, which let a burst of web sessions
        # starve the telephony queue. They are counted in their own bucket because a web call
        # is much cheaper than a phone call: no bridge process and no RTP port.
        if not await try_reserve_slot(WEB):
            logger.warning("Web call rejected — concurrency cap reached")
            raise HTTPException(
                status_code=503,
                detail="Server at capacity, please retry shortly",
            )
        slot_held = True

        # Create a unique room
        logger.info(f"Creating room for assistant: {request.assistant_id}")
        room_name = await livekit_services.create_room(request.assistant_id)

        # Force web sessions to be tagged as call_type=web while preserving custom metadata.
        job_metadata = {
            **(request.metadata or {}),
            "call_type": "web",
            "text_only": request.text_only,
        }

        # Initialize call record for web call
        await livekit_services.initialize_call_record(
            room_name=room_name,
            assistant_id=assistant.assistant_id,
            assistant_name=assistant.assistant_name,
            to_number="Web Call",
            call_status="initiated",
            created_by_email=current_user.user_email,
            call_type="web",
            call_service="web",
        )
        # Reservation handed over to the DB-counted CallRecord above.
        release_slot(WEB)
        slot_held = False

        # Create agent dispatch
        logger.info(f"Creating dispatch for room: {room_name}")
        agent_dispatch = await livekit_services.create_agent_dispatch(room_name, job_metadata)

        # Generate join token (agent dispatch embedded via RoomConfiguration)
        logger.info(f"Creating token for room: {room_name}")
        token = await livekit_services.create_token(room_name, job_metadata)
        if not token:
            raise HTTPException(status_code=500, detail="Failed to generate token")

        return apiResponse(
            success=True,
            message="Token generated successfully",
            data={
                "room_name": room_name,
                "agent_dispatch": MessageToDict(agent_dispatch),
                "token": token,
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating web call token: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate web call token")
    finally:
        # Releases the reservation if we bailed out before the CallRecord took over counting it.
        if slot_held:
            release_slot(WEB)
