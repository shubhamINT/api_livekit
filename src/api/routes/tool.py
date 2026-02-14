from fastapi import APIRouter, HTTPException, Depends
from src.api.models.api_schemas import CreateTool, UpdateTool, AttachToolsRequest
from src.api.models.response_models import apiResponse
from src.core.db.db_schemas import Tool, Assistant, APIKey
from src.api.dependencies import get_current_user
from src.core.logger import logger, setup_logging
import uuid
from datetime import datetime

router = APIRouter()
setup_logging()


# ---- TOOL CRUD ----


@router.post("/create")
async def create_tool(
    request: CreateTool, current_user: APIKey = Depends(get_current_user)
):
    logger.info(f"Received request to create tool: {request.tool_name}")

    tool_id = str(uuid.uuid4())

    tool_data = request.model_dump()

    # Convert ToolParameterSchema list to plain dicts for storage
    tool_data["tool_parameters"] = [
        param.model_dump() if hasattr(param, "model_dump") else param
        for param in request.tool_parameters
    ]

    try:
        new_tool = Tool(
            tool_id=tool_id,
            tool_created_by_email=current_user.user_email,
            tool_updated_by_email=current_user.user_email,
            **tool_data,
        )
        await new_tool.insert()
    except Exception as e:
        logger.error(f"Failed to create tool: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to create tool: {e}")

    logger.info(f"Tool created successfully: {tool_id}")
    return apiResponse(
        success=True,
        message="Tool created successfully",
        data={
            "tool_id": tool_id,
            "tool_name": new_tool.tool_name,
        },
    )


@router.patch("/update/{tool_id}")
async def update_tool(
    tool_id: str,
    request: UpdateTool,
    current_user: APIKey = Depends(get_current_user),
):
    logger.info(f"Received request to update tool: {tool_id}")

    update_data = request.model_dump(exclude_unset=True)

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")

    # Convert ToolParameterSchema if present
    if "tool_parameters" in update_data and update_data["tool_parameters"] is not None:
        update_data["tool_parameters"] = [
            param.model_dump() if hasattr(param, "model_dump") else param
            for param in update_data["tool_parameters"]
        ]

    update_data.update(
        {
            "tool_updated_at": datetime.utcnow(),
            "tool_updated_by_email": current_user.user_email,
        }
    )

    result = await Tool.find_one(
        Tool.tool_id == tool_id,
        Tool.tool_created_by_email == current_user.user_email,
    ).update({"$set": update_data})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tool not found")

    logger.info(f"Tool updated successfully: {tool_id}")
    return apiResponse(
        success=True,
        message="Tool updated successfully",
        data={"tool_id": tool_id},
    )


@router.get("/list")
async def list_tools(current_user: APIKey = Depends(get_current_user)):
    logger.info("Received request to list tools")

    tools = await Tool.find(
        Tool.tool_created_by_email == current_user.user_email,
        Tool.tool_is_active == True,
    ).to_list()

    filtered_tools = [
        {
            "tool_id": tool.tool_id,
            "tool_name": tool.tool_name,
            "tool_description": tool.tool_description,
            "tool_execution_type": tool.tool_execution_type,
            "tool_created_at": tool.tool_created_at.isoformat(),
        }
        for tool in tools
    ]

    return apiResponse(
        success=True,
        message="Tools retrieved successfully",
        data=filtered_tools,
    )


@router.get("/details/{tool_id}")
async def get_tool_details(
    tool_id: str, current_user: APIKey = Depends(get_current_user)
):
    logger.info(f"Received request to get tool details: {tool_id}")

    tool = await Tool.find_one(
        Tool.tool_id == tool_id,
        Tool.tool_created_by_email == current_user.user_email,
        Tool.tool_is_active == True,
    )

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    return apiResponse(
        success=True,
        message="Tool details retrieved successfully",
        data=tool.model_dump(exclude={"id"}),
    )


@router.delete("/delete/{tool_id}")
async def delete_tool(
    tool_id: str, current_user: APIKey = Depends(get_current_user)
):
    logger.info(f"Received request to delete tool: {tool_id}")

    tool = await Tool.find_one(
        Tool.tool_id == tool_id,
        Tool.tool_created_by_email == current_user.user_email,
        Tool.tool_is_active == True,
    )

    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")

    tool.tool_is_active = False
    tool.tool_updated_at = datetime.utcnow()
    tool.tool_updated_by_email = current_user.user_email
    await tool.save()

    # Remove this tool from all assistants that reference it
    assistants = await Assistant.find(
        Assistant.assistant_created_by_email == current_user.user_email,
        Assistant.tool_ids == tool_id,
    ).to_list()

    for assistant in assistants:
        assistant.tool_ids = [tid for tid in assistant.tool_ids if tid != tool_id]
        await assistant.save()

    logger.info(f"Tool deleted and removed from {len(assistants)} assistant(s): {tool_id}")
    return apiResponse(
        success=True,
        message="Tool deleted successfully",
        data={"tool_id": tool_id},
    )


# ---- ATTACH / DETACH ----


@router.post("/attach/{assistant_id}")
async def attach_tools(
    assistant_id: str,
    request: AttachToolsRequest,
    current_user: APIKey = Depends(get_current_user),
):
    logger.info(f"Attaching tools to assistant: {assistant_id}")

    # Verify assistant exists and belongs to user
    assistant = await Assistant.find_one(
        Assistant.assistant_id == assistant_id,
        Assistant.assistant_created_by_email == current_user.user_email,
        Assistant.assistant_is_active == True,
    )
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    # Verify all tool IDs exist and belong to user
    valid_tools = await Tool.find(
        Tool.tool_created_by_email == current_user.user_email,
        Tool.tool_is_active == True,
    ).to_list()

    valid_tool_ids = {t.tool_id for t in valid_tools}
    invalid_ids = [tid for tid in request.tool_ids if tid not in valid_tool_ids]

    if invalid_ids:
        raise HTTPException(
            status_code=404,
            detail=f"Tool(s) not found: {', '.join(invalid_ids)}",
        )

    # Merge: add new tool_ids without duplicates
    existing = set(assistant.tool_ids)
    new_ids = [tid for tid in request.tool_ids if tid not in existing]
    assistant.tool_ids = assistant.tool_ids + new_ids
    assistant.assistant_updated_at = datetime.utcnow()
    assistant.assistant_updated_by_email = current_user.user_email
    await assistant.save()

    logger.info(f"Attached {len(new_ids)} tool(s) to assistant {assistant_id}")
    return apiResponse(
        success=True,
        message=f"Attached {len(new_ids)} tool(s) to assistant",
        data={
            "assistant_id": assistant_id,
            "tool_ids": assistant.tool_ids,
        },
    )


@router.post("/detach/{assistant_id}")
async def detach_tools(
    assistant_id: str,
    request: AttachToolsRequest,
    current_user: APIKey = Depends(get_current_user),
):
    logger.info(f"Detaching tools from assistant: {assistant_id}")

    assistant = await Assistant.find_one(
        Assistant.assistant_id == assistant_id,
        Assistant.assistant_created_by_email == current_user.user_email,
        Assistant.assistant_is_active == True,
    )
    if not assistant:
        raise HTTPException(status_code=404, detail="Assistant not found")

    detach_set = set(request.tool_ids)
    assistant.tool_ids = [tid for tid in assistant.tool_ids if tid not in detach_set]
    assistant.assistant_updated_at = datetime.utcnow()
    assistant.assistant_updated_by_email = current_user.user_email
    await assistant.save()

    logger.info(f"Detached {len(detach_set)} tool(s) from assistant {assistant_id}")
    return apiResponse(
        success=True,
        message=f"Detached tool(s) from assistant",
        data={
            "assistant_id": assistant_id,
            "tool_ids": assistant.tool_ids,
        },
    )
