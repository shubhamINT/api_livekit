from fastapi import APIRouter, HTTPException, Depends
from src.api.models.api_schemas import CreateAssistant
from src.api.models.response_models import apiResponse
from src.core.db.db_schemas import Assistant, APIKey
from src.api.dependencies import get_current_user
from src.core.logger import logger, setup_logging
import uuid

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
            assistant_updated_by_email=current_user.user_email
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
