from fastapi import APIRouter, HTTPException, Depends
from src.api.models.api_schemas import CreateAssistant, UpdateAssistant
from src.api.models.response_models import apiResponse
from src.core.db.db_schemas import Assistant, APIKey
from src.api.dependencies import get_current_user
from src.core.logger import logger, setup_logging
import uuid
from datetime import datetime

router = APIRouter()
setup_logging()

# Create new assistant
@router.post("/create")
async def create_assistant(request: CreateAssistant, current_user: APIKey = Depends(get_current_user)):

    logger.info(f"Received request to create assistant")
    # Generate unique assistant ID
    assistant_id = str(uuid.uuid4())
    
    # Convert Pydantic model to dict
    assistant_data = request.model_dump()
    
    try:
        logger.info(f"Inserting assistant into database")
        # Create database document
        new_assistant = Assistant(
            assistant_id=assistant_id,
            assistant_created_by_email=current_user.user_email,
            assistant_updated_by_email=current_user.user_email,
            **assistant_data
        )
        await new_assistant.insert()
    except Exception as e:
        logger.error(f"Failed to create assistant: {e}")
        raise HTTPException(status_code=400, detail=f"Failed to create assistant: {e}")
    
    logger.info(f"Assistant created successfully: {assistant_id}")
    return apiResponse(
        success=True,
        message="Assistant created successfully",
        data={
            "assistant_id": assistant_id,
            "assistant_name": new_assistant.assistant_name
        }
    )


# Update assistant
@router.patch("/update/{assistant_id}")
async def update_assistant(assistant_id: str, request: UpdateAssistant, current_user: APIKey = Depends(get_current_user)):

    logger.info(f"Received request to update assistant: {assistant_id}")
    
    # Update fields
    update_data = request.model_dump(exclude_unset=True)
    
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields provided for update")
        
    logger.info(f"Updating assistant {assistant_id}")
    update_data.update({"assistant_updated_at": datetime.utcnow(),"assistant_updated_by_email": current_user.user_email})
        
    result = await Assistant.find_one(Assistant.assistant_id == assistant_id,
                                    Assistant.assistant_created_by_email == current_user.user_email).update({"$set":update_data})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Assistant not found")
    
    logger.info(f"Assistant updated successfully: {assistant_id}")
    return apiResponse(
        success=True,
        message="Assistant updated successfully",
        data={
            "assistant_id": assistant_id
        }
    )
