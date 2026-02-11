from fastapi import APIRouter, HTTPException, Depends
from src.api.models.api_schemas import CreateAssistantRequest
from src.api.models.response_models import apiResponse
from src.core.db.db_schemas import Assistant, APIKey
from src.api.dependencies import get_current_user
import uuid

router = APIRouter()

# Create new assistant
@router.post("/create")
async def create_assistant(
    request: CreateAssistantRequest,
    current_user: APIKey = Depends(get_current_user)
):
    # Generate unique assistant ID
    assistant_id = str(uuid.uuid4())
    
    # Convert Pydantic model to dict
    assistant_data = request.model_dump()
    
    try:
        # Create database document
        new_assistant = Assistant(
            assistant_id=assistant_id,
            **assistant_data
        )
        await new_assistant.insert()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create assistant: {e}")
    
    return apiResponse(
        success=True,
        message="Assistant created successfully",
        data={
            "assistant_id": assistant_id,
            "assistant_name": new_assistant.assistant_name
        }
    )
