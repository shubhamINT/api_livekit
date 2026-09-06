from fastapi import APIRouter, HTTPException, Depends, Request, Body, Query
from fastapi.responses import JSONResponse
from typing import Optional
from datetime import datetime
from src.api.models.api_schemas import TriggerOutboundCall, TriggerPassthroughCall
from src.api.models.response_models import apiResponse
from src.core.db.db_schemas import OutboundSIP, APIKey, Assistant, OutboundCallQueue, CallRecord, UsageRecord
from src.api.dependencies import get_current_user
from src.core.logger import logger
from src.core.providers.keys import redact_text
from src.services.livekit.livekit_svc import LiveKitService

router = APIRouter()
_livekit_services = LiveKitService()


@router.post("/outbound", status_code=202)
async def trigger_outbound_call(
    request: TriggerOutboundCall, current_user: APIKey = Depends(get_current_user)
):
    logger.info(
        f"Received outbound call request | user={current_user.user_email} "
        f"service={request.call_service} to={request.to_number}"
    )

    assistant = await Assistant.find_one(
        Assistant.assistant_id == request.assistant_id,
        Assistant.assistant_created_by_email == current_user.user_email,
    )
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found in DB")

    trunk = await OutboundSIP.find_one(
        OutboundSIP.trunk_id == request.trunk_id,
        OutboundSIP.trunk_created_by_email == current_user.user_email,
        OutboundSIP.trunk_is_active == True,
    )
    if not trunk:
        raise HTTPException(status_code=404, detail="Trunk not found in DB")

    if trunk.trunk_type != request.call_service:
        raise HTTPException(
            status_code=400,
            detail=f"Trunk type '{trunk.trunk_type}' does not match call service '{request.call_service}'",
        )

    queue_item = OutboundCallQueue(
        user_email=current_user.user_email,
        assistant_id=assistant.assistant_id,
        assistant_name=assistant.assistant_name,
        trunk_id=trunk.trunk_id,
        to_number=request.to_number,
        call_service=request.call_service,
        job_metadata=request.metadata or {},
    )
    await queue_item.insert()

    logger.info(
        f"Enqueued outbound call {queue_item.queue_id} | "
        f"to={request.to_number} user={current_user.user_email}"
    )

    return JSONResponse(
        status_code=202,
        content=apiResponse(
            success=True,
            message="Outbound call queued successfully",
            data={"queue_id": queue_item.queue_id, "status": "queued"},
        ).model_dump(),
    )


@router.get("/queue/{queue_id}")
async def get_queue_status(
    queue_id: str, current_user: APIKey = Depends(get_current_user)
):
    item = await OutboundCallQueue.find_one(
        OutboundCallQueue.queue_id == queue_id,
        OutboundCallQueue.user_email == current_user.user_email,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Queue item not found")

    return apiResponse(
        success=True,
        message="Queue status retrieved",
        data={
            "queue_id": item.queue_id,
            "status": item.status,
            "to_number": item.to_number,
            "call_service": item.call_service,
            "queued_at": item.queued_at.isoformat(),
            "dispatched_at": item.dispatched_at.isoformat() if item.dispatched_at else None,
            "retry_count": item.retry_count,
            "last_error": redact_text(item.last_error) if item.last_error else None,
        },
    )


@router.get("/records/{room_name}/usage")
async def get_call_usage(room_name: str, current_user: APIKey = Depends(get_current_user)):
    """Return usage for one call owned by the authenticated user."""
    call_record = await CallRecord.find_one(
        CallRecord.room_name == room_name,
        CallRecord.created_by_email == current_user.user_email,
    )
    if not call_record:
        raise HTTPException(status_code=404, detail="Call usage not found")

    usage_record = await UsageRecord.find_one(UsageRecord.room_name == room_name)
    if not usage_record:
        raise HTTPException(status_code=404, detail="Call usage not found")

    return apiResponse(
        success=True,
        message="Call usage fetched successfully",
        data=usage_record.model_dump(exclude={"id"}),
    )


@router.post("/outbound_passthrough", status_code=202)
async def trigger_passthrough_call(
    request: TriggerPassthroughCall, current_user: APIKey = Depends(get_current_user)
):
    """Start a passthrough call: web user ↔ SIP with no AI agent.

    Creates the LiveKit room synchronously and returns a room token so the
    web client can connect immediately while the SIP call is dialled in the background.
    """
    trunk = await OutboundSIP.find_one(
        OutboundSIP.trunk_id == request.trunk_id,
        OutboundSIP.trunk_created_by_email == current_user.user_email,
        OutboundSIP.trunk_is_active == True,
    )
    if not trunk:
        raise HTTPException(status_code=404, detail="Trunk not found")

    if not trunk.passthrough_mode:
        raise HTTPException(
            status_code=400,
            detail="Trunk does not have passthrough_mode enabled",
        )

    # Create room now so web user gets a token before SIP dial begins.
    room_name = await _livekit_services.create_room()
    room_token = await _livekit_services.create_token(room_name)
    if not room_token:
        raise HTTPException(status_code=500, detail="Failed to generate room token")

    # Resolve platform number from whichever trunk type is in use.
    if trunk.trunk_type == "exotel":
        platform_number = trunk.trunk_config.get("exotel_number")
    else:
        platform_number = (trunk.trunk_config.get("numbers") or [None])[0]

    queue_item = OutboundCallQueue(
        user_email=current_user.user_email,
        trunk_id=trunk.trunk_id,
        to_number=request.to_number,
        call_service=trunk.trunk_type,
        job_metadata=request.metadata or {},
        passthrough_room_name=room_name,
    )
    await queue_item.insert()

    # Initialize call record immediately so status is visible before SIP connects.
    await _livekit_services.initialize_call_record(
        room_name=room_name,
        to_number=request.to_number,
        call_status="initiated",
        created_by_email=current_user.user_email,
        call_type="outbound",
        call_service=trunk.trunk_type,
        platform_number=platform_number,
        queue_id=queue_item.queue_id,
        is_passthrough=True,
    )

    logger.info(
        f"Enqueued passthrough call {queue_item.queue_id} | "
        f"to={request.to_number} room={room_name} user={current_user.user_email}"
    )

    return JSONResponse(
        status_code=202,
        content=apiResponse(
            success=True,
            message="Passthrough call queued successfully",
            data={
                "queue_id": queue_item.queue_id,
                "room_name": room_name,
                "room_token": room_token,
                "status": "queued",
            },
        ).model_dump(),
    )


@router.get("/records")
async def list_call_records(
    passthrough_only: bool = Query(False, description="Return only passthrough calls (no AI agent)"),
    to_number: Optional[str] = Query(None, description="Filter by destination phone number"),
    call_status: Optional[str] = Query(None, description="Filter by status (completed, failed, busy, no_answer, ...)"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering (ISO 8601)"),
    sort_by: str = Query("started_at", description="Field to sort by (e.g., started_at, ended_at, call_duration_minutes)"),
    sort_order: str = Query("desc", description="Sort order: 'asc' or 'desc'"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    current_user: APIKey = Depends(get_current_user),
):
    query_conditions = [CallRecord.created_by_email == current_user.user_email]

    if passthrough_only:
        query_conditions.append(CallRecord.is_passthrough == True)
    if to_number:
        query_conditions.append(CallRecord.to_number == to_number)
    if call_status:
        query_conditions.append(CallRecord.call_status == call_status)
    if start_date:
        query_conditions.append(CallRecord.started_at >= start_date)
    if end_date:
        query_conditions.append(CallRecord.started_at <= end_date)

    sort_field = f"{'-' if sort_order == 'desc' else '+'}{sort_by}"
    skip = (page - 1) * limit

    records_query = CallRecord.find(*query_conditions)
    total = await records_query.count()
    records = await records_query.sort(sort_field).skip(skip).limit(limit).to_list()

    return apiResponse(
        success=True,
        message="Call records fetched successfully",
        data={
            "records": [r.model_dump(exclude={"id"}) for r in records],
            "pagination": {
                "total": total,
                "page": page,
                "limit": limit,
                "total_pages": (total + limit - 1) // limit,
            },
        },
    )


@router.post("/end_call")
async def end_call(request: Request, _: dict = Body(...)):
    from src.core.providers.keys import mask_secret_values

    logger.info("Received payload after end call")

    body = await request.json()
    # The caller's webhooks may include credential-looking fields (Authorization,
    # api_key, tokens); don't round-trip those verbatim in the response body.
    return apiResponse(
        success=True,
        message="Call ended successfully",
        data=mask_secret_values(body),
    )
