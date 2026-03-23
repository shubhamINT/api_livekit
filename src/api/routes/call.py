from fastapi import APIRouter, HTTPException, Depends, Request, Body
from fastapi.responses import JSONResponse
from src.api.models.api_schemas import TriggerOutboundCall
from src.api.models.response_models import apiResponse
from src.core.db.db_schemas import OutboundSIP, APIKey, Assistant
from src.api.dependencies import get_current_user
from src.core.logger import logger, setup_logging
from src.services.livekit.livekit_svc import LiveKitService
from google.protobuf.json_format import MessageToDict
from datetime import datetime, timezone
import asyncio
import uuid

router = APIRouter()
setup_logging()
livekit_services = LiveKitService()


# Triggure Ouboud call
@router.post("/outbound")
async def trigger_outbound_call(
    request: TriggerOutboundCall, current_user: APIKey = Depends(get_current_user)
):
    logger.info(
        f"Received request to trigger outbound call for user: {current_user.user_email} service: {request.call_service}"
    )

    # Check of the assistant exists for the user
    assistant = await Assistant.find_one(
        Assistant.assistant_id == request.assistant_id,
        Assistant.assistant_created_by_email == current_user.user_email,
    )
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found in DB")

    # Check if the trunk exists and is active for the user
    trunk = await OutboundSIP.find_one(
        OutboundSIP.trunk_id == request.trunk_id,
        OutboundSIP.trunk_created_by_email == current_user.user_email,
        OutboundSIP.trunk_is_active == True,
    )
    if not trunk:
        raise HTTPException(status_code=404, detail="Trunk not found in DB")

    # Create room (unique room name with assistant name) common for all the call services
    logger.info(f"Creating room for assistant: {request.assistant_id}")
    room_name = await livekit_services.create_room(request.assistant_id)

    # Job metadata common for all the call services
    job_metadata = request.metadata or {}
    job_metadata["to_number"] = request.to_number
    job_metadata["call_service"] = request.call_service

    # Create agent dispatch common for all the call services
    logger.info(f"Creating dispatch for room: {room_name}")
    agent_dispatch = await livekit_services.create_agent_dispatch(room_name, job_metadata)

    if request.call_service == "twilio":
        # Create SIP participant
        logger.info(f"Triggering Twilio SIP participant for number: {request.to_number}")
        participant = await livekit_services.create_sip_participant(
            room_name=room_name,
            to_number=request.to_number,
            trunk_id=request.trunk_id,
            participant_identity=uuid.uuid4().hex,
        )

        return apiResponse(
            success=True,
            message="Outbound call triggered successfully via Twilio",
            data={
                "room_name": room_name,
                "agent_dispatch": MessageToDict(agent_dispatch),
                "participant": MessageToDict(participant),
            },
        )

    elif request.call_service == "exotel":
        # Custom SIP bridge for Exotel
        from src.services.exotel.custom_sip_reach.bridge import run_bridge

        logger.info(f"Triggering Exotel SIP bridge call to {request.to_number}")

        await livekit_services.initialize_call_record(
            room_name=room_name,
            assistant_id=assistant.assistant_id,
            assistant_name=assistant.assistant_name,
            to_number=request.to_number,
            call_status="initiated",
        )

        # Trunk config (Exotel number, etc.)
        sip_config = trunk.trunk_config

        # One-shot queue — bridge puts result after INVITE resolves, then keeps running
        result_signal = asyncio.Queue(maxsize=1)

        asyncio.create_task(
            run_bridge(
                phone_number=request.to_number,
                room_name=room_name,
                sip_config=sip_config,
                result_signal=result_signal,
            )
        )

        async def monitor_exotel_setup_result():
            try:
                try:
                    sip_result = await asyncio.wait_for(result_signal.get(), timeout=60.0)
                except asyncio.TimeoutError:
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
                        room_name=room_name,
                        assistant_id=assistant.assistant_id,
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
                        room_name=room_name,
                        assistant_id=assistant.assistant_id,
                    )
                    logger.warning(
                        f"Exotel SIP setup failed | room={room_name} | reason={sip_result.get('error', 'unknown')}"
                    )
                    return

                # Status update deferred to agent session (session.py handles "answered" + recording)
                logger.info(f"Exotel SIP answered | room={room_name} — status update deferred to agent session")

            except Exception as e:
                logger.error(f"Exotel monitor crashed | room={room_name}: {e}", exc_info=True)
                try:
                    await livekit_services.update_call_status(
                        room_name=room_name,
                        call_status="failed",
                        call_status_reason=f"Monitor error: {e}",
                        ended_at=datetime.now(timezone.utc),
                        call_duration_minutes=0,
                    )
                    await livekit_services.send_end_call_webhook(
                        room_name=room_name,
                        assistant_id=assistant.assistant_id,
                    )
                except Exception:
                    pass

        asyncio.create_task(monitor_exotel_setup_result())

        response = apiResponse(
            success=True,
            message="Outbound call accepted via Exotel bridge",
            data={
                "room_name": room_name,
                "agent_dispatch": MessageToDict(agent_dispatch),
                "status": "initiated",
            },
        )
        return JSONResponse(status_code=202, content=response.model_dump())

    else:
        raise HTTPException(
            status_code=400,
            detail=f"Call service '{request.call_service}' not supported",
        )


# DEMO END CALL URL endpoint. This endpint will be hit after the call is ended
@router.post("/end_call")
async def end_call(request: Request, _ : dict= Body(...)):
    
    logger.info(f"Received payload after end call")
    
    # Get the request body
    body = await request.json()
    
    # Get the room name from the body
    return apiResponse(
        success=True,
        message="Call ended successfully",
        data=body,
    )
