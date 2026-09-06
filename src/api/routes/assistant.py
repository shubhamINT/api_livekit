import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.dependencies import get_current_user
from src.api.models.api_schemas import (
    CreateAssistant,
    UpdateAssistant,
)
from src.api.models.response_models import apiResponse
from src.api.validation import (
    effective_llm_config,
    effective_value,
    enforce_openai_config,
    enforce_provider_keys,
    enforce_stored_mode_constraints,
    resolve_probe_tools,
    will_attach_tools,
)
from src.core.db.db_schemas import (
    APIKey,
    Assistant,
    AudioAsset,
    CallRecord,
    UsageRecord,
)
from src.core.logger import logger
from src.core.providers.keys import mask_assistant_keys, redact_text

router = APIRouter()


def merge_interaction_config(base, overrides: dict) -> dict:
    base_dict = base.model_dump() if hasattr(base, "model_dump") else dict(base)
    return {**base_dict, **overrides}


def merge_llm_config(base, overrides: dict) -> dict:
    """Merge a PATCH's `assistant_llm_config` over the stored one, dropping cleared keys.

    Same partial-update contract as `assistant_interaction_config`: an omitted key keeps
    whatever the row holds, and an explicit null removes it. Removing rather than storing
    `None` matters for the model-gated knobs — `create_llm` and the validator both test key
    presence, so a lingering `temperature: null` would read as "set" to a future reader even
    though nothing is sent to OpenAI.

    Replacing the whole subdocument instead (what `$set` does on its own) meant a PATCH of
    `{"model": "gpt-4.1"}` silently dropped `provider` and `api_key`, while
    `enforce_stored_mode_constraints` still judged the request against the values that write
    was about to delete.
    """
    base_dict = base.model_dump() if hasattr(base, "model_dump") else dict(base or {})
    merged = {**base_dict, **overrides}
    return {k: v for k, v in merged.items() if v is not None}


async def validate_owned_audio(audio_id: str, current_user: APIKey) -> None:
    """Ensure the audio asset exists, is active, and belongs to the caller."""
    asset = await AudioAsset.find_one(
        AudioAsset.audio_id == audio_id,
        AudioAsset.created_by_email == current_user.user_email,
        AudioAsset.is_active == True,
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Audio asset not found")


# Create new assistant
@router.post("/create")
async def create_assistant(
    request: CreateAssistant, current_user: APIKey = Depends(get_current_user)
):
    logger.info(f"Received request to create assistant")
    # Generate unique assistant ID
    assistant_id = str(uuid.uuid4())

    # Convert Pydantic model to dict
    assistant_data = request.model_dump()

    # A referenced greeting audio must be one of the caller's active assets.
    greeting_audio = assistant_data.get("assistant_greeting_audio") or {}
    if greeting_audio.get("audio_id"):
        await validate_owned_audio(greeting_audio["audio_id"], current_user)

    # The offline rules ran inside the schema. These two ask OpenAI what no local list can
    # know: whether it still serves the model, and whether it accepts this exact request.
    # A new assistant has no tool_ids yet, so end_call is the only tool that can be present —
    # /assistant/attach-tools re-runs the same guard when tools arrive.
    enforce_provider_keys(
        assistant_data.get("assistant_mode"),
        assistant_data.get("assistant_stt_model"),
        assistant_data.get("assistant_stt_config"),
        assistant_data.get("assistant_tts_model"),
        assistant_data.get("assistant_tts_config"),
        status_code=422,
    )

    probe_assistant = SimpleNamespace(
        tool_ids=[],
        assistant_end_call_enabled=assistant_data.get("assistant_end_call_enabled", False),
    )
    await enforce_openai_config(
        assistant_data.get("assistant_mode"),
        assistant_data.get("assistant_llm_config"),
        status_code=422,
        tools=await resolve_probe_tools(
            probe_assistant,
            strict_schemas=assistant_data.get("assistant_mode") == "cascade",
        ),
        has_tools=will_attach_tools(probe_assistant),
    )

    try:
        logger.info(f"Inserting assistant into database")
        # Create database document
        new_assistant = Assistant(
            assistant_id=assistant_id,
            assistant_created_by_email=current_user.user_email,
            assistant_updated_by_email=current_user.user_email,
            **assistant_data,
        )
        await new_assistant.insert()
    except Exception as e:
        logger.error(f"Failed to create assistant: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to create assistant: {redact_text(str(e))}")

    logger.info(f"Assistant created successfully: {assistant_id}")
    return apiResponse(
        success=True,
        message="Assistant created successfully",
        data={
            "assistant_id": assistant_id,
            "assistant_name": new_assistant.assistant_name,
        },
    )


# Update assistant
@router.patch("/update/{assistant_id}")
async def update_assistant(
    assistant_id: str,
    request: UpdateAssistant,
    current_user: APIKey = Depends(get_current_user),
):
    logger.info(f"Received request to update assistant: {assistant_id}")


    update_data = request.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    assistant = await Assistant.find_one(
        Assistant.assistant_id == assistant_id,
        Assistant.assistant_created_by_email == current_user.user_email,
    )
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    if "assistant_interaction_config" in update_data:
        update_data["assistant_interaction_config"] = merge_interaction_config(
            assistant.assistant_interaction_config,
            update_data["assistant_interaction_config"],
        )

    # Webhook delivery settings: same partial-update contract as the interaction config, so a
    # PATCH naming only `attempts` keeps the stored timeout. A field sent as null stays null,
    # which is how "fall back to the server default" is expressed.
    if "assistant_end_call_webhook" in update_data:
        update_data["assistant_end_call_webhook"] = merge_interaction_config(
            assistant.assistant_end_call_webhook,
            update_data["assistant_end_call_webhook"],
        )

    # Greeting audio: merge with existing, then validate the referenced asset.
    if "assistant_greeting_audio" in update_data:
        merged_greeting = merge_interaction_config(
            assistant.assistant_greeting_audio,
            update_data["assistant_greeting_audio"],
        )
        if merged_greeting.get("audio_id"):
            await validate_owned_audio(merged_greeting["audio_id"], current_user)
        update_data["assistant_greeting_audio"] = merged_greeting

    # Mode-switch guards (need DB state for full validation)
    new_mode = update_data.get("assistant_mode")
    if new_mode in ("pipeline", "cascade"):
        # Both speak through an external TTS: ensure one exists (in request or already in DB)
        if not update_data.get("assistant_tts_model") and not assistant.assistant_tts_model:
            raise HTTPException(
                status_code=400,
                detail=f"assistant_tts_model and assistant_tts_config are required when switching to {new_mode} mode (none found in DB).",
            )
        # Clear stale realtime llm_config only when actually leaving realtime mode
        if assistant.assistant_mode == "realtime" and "assistant_llm_config" not in update_data:
            update_data["assistant_llm_config"] = None

    # Partial LLM config: merge over the stored dict so a PATCH naming one key does not drop
    # the rest. Leaving realtime mode is the one exception — the stored config there is a
    # Gemini one (voice, Gemini api_key) that must not survive under an OpenAI provider, and
    # the guard above already documents it as cleared.
    leaving_realtime = assistant.assistant_mode == "realtime" and new_mode in ("pipeline", "cascade")
    if update_data.get("assistant_llm_config") is not None and not leaving_realtime:
        update_data["assistant_llm_config"] = merge_llm_config(
            assistant.assistant_llm_config,
            update_data["assistant_llm_config"],
        )

    enforce_stored_mode_constraints(assistant, update_data, new_mode)
    # 400, matching enforce_stored_mode_constraints: the request on its own is well-formed,
    # and the value being judged may have come from the stored row rather than this PATCH.
    effective_mode = new_mode or assistant.assistant_mode
    # Both stages judged against the effective row: switching TTS provider without sending a
    # key has to be checked against the key the row already holds, and against the server's.
    enforce_provider_keys(
        effective_mode,
        effective_value(assistant, update_data, "assistant_stt_model"),
        effective_value(assistant, update_data, "assistant_stt_config"),
        effective_value(assistant, update_data, "assistant_tts_model"),
        effective_value(assistant, update_data, "assistant_tts_config"),
        status_code=400,
    )
    await enforce_openai_config(
        effective_mode,
        effective_llm_config(assistant, update_data),
        status_code=400,
        tools=await resolve_probe_tools(
            assistant, update_data, strict_schemas=effective_mode == "cascade"
        ),
        has_tools=will_attach_tools(assistant, update_data),
    )

    logger.info(f"Updating assistant {assistant_id}")
    update_data.update(
        {
            "assistant_updated_at": datetime.now(timezone.utc),
            "assistant_updated_by_email": current_user.user_email,
        }
    )

    await assistant.update({"$set": update_data})

    logger.info(f"Assistant updated successfully: {assistant_id}")
    return apiResponse(
        success=True,
        message="Assistant updated successfully",
        data={"assistant_id": assistant_id},
    )


# List assistants
@router.get("/list")
async def list_assistants(
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    assistant_name: Optional[str] = Query(None, description="Filter by assistant name (case-insensitive)"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering (ISO 8601)"),
    sort_by: str = Query("assistant_created_at", description="Field to sort by"),
    sort_order: str = Query("desc", description="Sort order: 'asc' or 'desc'"),
    current_user: APIKey = Depends(get_current_user)
):
    logger.info(f"Received request to list assistants")

    # Build query using Beanie expressions
    query_conditions = [
        Assistant.assistant_created_by_email == current_user.user_email,
        Assistant.assistant_is_active == True
    ]
    
    if assistant_name:
        # Case-insensitive partial match search
        query_conditions.append({
            "assistant_name": {
                "$regex": assistant_name,
                "$options": "i"
            }
        })
    
    if start_date:
        query_conditions.append(Assistant.assistant_created_at >= start_date)
    if end_date:
        query_conditions.append(Assistant.assistant_created_at <= end_date)

    # Calculate skip
    skip = (page - 1) * limit
    
    # Sorting
    sort_prefix = "-" if sort_order == "desc" else "+"
    sort_field = f"{sort_prefix}{sort_by}"

    assistant_query = Assistant.find(*query_conditions)
    
    # Get total count before pagination
    total_assistants = await assistant_query.count()
    
    # Apply sorting and pagination
    assistants = await assistant_query.sort(sort_field).skip(skip).limit(limit).to_list()

    # Filter only requested fields
    filtered_assistants = [
        mask_assistant_keys(
            {
                "assistant_id": assistant.assistant_id,
                "assistant_name": assistant.assistant_name,
                "assistant_mode": assistant.assistant_mode,
                "assistant_tts_model": assistant.assistant_tts_model,
                "assistant_tts_config": assistant.assistant_tts_config,
                "assistant_stt_model": assistant.assistant_stt_model,
                "assistant_stt_config": assistant.assistant_stt_config,
                "assistant_interaction_config": assistant.assistant_interaction_config.model_dump(),
                "assistant_created_by_email": assistant.assistant_created_by_email,
            }
        )
        for assistant in assistants
    ]

    return apiResponse(
        success=True,
        message="Assistants retrieved successfully",
        data={
            "assistants": filtered_assistants,
            "pagination": {
                "total": total_assistants,
                "page": page,
                "limit": limit,
                "total_pages": (total_assistants + limit - 1) // limit if total_assistants > 0 else 0
            }
        },
    )


# Fetch assistant details
@router.get("/details/{assistant_id}")
async def get_assistant_details(
    assistant_id: str, current_user: APIKey = Depends(get_current_user)
):
    logger.info(f"Received request to get assistant details: {assistant_id}")

    assistant = await Assistant.find_one(
        Assistant.assistant_id == assistant_id,
        Assistant.assistant_created_by_email == current_user.user_email,
        Assistant.assistant_is_active == True,
    )

    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    assistant_data = mask_assistant_keys(assistant.model_dump(exclude={"id"}))

    return apiResponse(
        success=True,
        message="Assistant details retrieved successfully",
        data=assistant_data,
    )


# Delete assistant
@router.delete("/delete/{assistant_id}")
async def delete_assistant(
    assistant_id: str, current_user: APIKey = Depends(get_current_user)
):
    logger.info(f"Received request to delete assistant: {assistant_id}")

    assistant = await Assistant.find_one(
        Assistant.assistant_id == assistant_id,
        Assistant.assistant_created_by_email == current_user.user_email,
        Assistant.assistant_is_active == True,
    )

    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    assistant.assistant_is_active = False
    assistant.assistant_updated_at = datetime.now(timezone.utc)
    assistant.assistant_updated_by_email = current_user.user_email
    await assistant.save()

    logger.info(f"Assistant deleted successfully: {assistant_id}")
    return apiResponse(
        success=True,
        message="Assistant deleted successfully",
        data={"assistant_id": assistant_id},
    )


# Get call logs
@router.get("/call-logs/{assistant_id}")
async def get_call_logs(
    assistant_id: str,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, ge=1, le=100, description="Items per page"),
    start_date: Optional[datetime] = Query(None, description="Start date for filtering (ISO 8601)"),
    end_date: Optional[datetime] = Query(None, description="End date for filtering (ISO 8601)"),
    sort_by: str = Query("started_at", description="Field to sort by (e.g., started_at, ended_at, call_duration_minutes, billable_duration_minutes)"),
    sort_order: str = Query("desc", description="Sort order: 'asc' or 'desc'"),
    current_user: APIKey = Depends(get_current_user)
):
    logger.info(f"Received request to get call logs for assistant: {assistant_id}")

    # Verify the caller owns this assistant — prevents cross-tenant data leakage
    assistant = await Assistant.find_one(
        Assistant.assistant_id == assistant_id,
        Assistant.assistant_created_by_email == current_user.user_email,
        Assistant.assistant_is_active == True,
    )
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    # Build query using Beanie expressions
    query_conditions = [CallRecord.assistant_id == assistant_id]
    
    if start_date:
        query_conditions.append(CallRecord.started_at >= start_date)
    if end_date:
        query_conditions.append(CallRecord.started_at <= end_date)

    # Calculate skip
    skip = (page - 1) * limit
    
    # Sorting
    sort_prefix = "-" if sort_order == "desc" else "+"
    sort_field = f"{sort_prefix}{sort_by}"

    call_log_query = CallRecord.find(*query_conditions)
    
    # Get total count before pagination
    total_logs = await call_log_query.count()
    
    # Apply sorting and pagination
    call_logs = await call_log_query.sort(sort_field).skip(skip).limit(limit).to_list()

    room_names = [call_log.room_name for call_log in call_logs]
    usage_by_room = {}
    if room_names:
        usage_records = await UsageRecord.find({"room_name": {"$in": room_names}}).to_list()
        usage_by_room = {
            usage_record.room_name: json.loads(usage_record.model_dump_json(exclude={"id"}))
            for usage_record in usage_records
        }

    call_log_data = []
    for call_log in call_logs:
        call_log_data.append(
            {
                **call_log.model_dump(exclude={"id"}),
                "usage": usage_by_room.get(call_log.room_name),
            }
        )

    return apiResponse(
        success=True,
        message="Call logs retrieved successfully",
        data={
            "logs": call_log_data,
            "pagination": {
                "total": total_logs,
                "page": page,
                "limit": limit,
                "total_pages": (total_logs + limit - 1) // limit if total_logs > 0 else 0
            }
        },
    )
