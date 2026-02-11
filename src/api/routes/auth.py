from fastapi import APIRouter, HTTPException, Depends
from src.api.models.api_schemas import CreateApiKey
from src.api.models.response_models import apiResponse
from src.core.db.db_schemas import APIKey
from src.api.dependencies import get_current_user
from src.core.logger import logger,setup_logging
import secrets

router = APIRouter()
setup_logging()

# Create api key
@router.post("/create-key")
async def create_api_key(request: CreateApiKey):
    logger.info(f"Received request to create API key")
    # check if user already exists
    existing_user = await APIKey.find_one(APIKey.user_email == request.user_email)
    if existing_user:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    # generate api key
    api_key = "lvk_" + secrets.token_urlsafe(32)

    try:
        logger.info(f"Inserting API key into database")
        # create new user
        user = APIKey(user_name=request.user_name,org_name=request.org_name,user_email=request.user_email,api_key=api_key)
        await user.insert()
    except Exception as e:
        logger.error(f"Failed to create API key: {e}")
        raise HTTPException(status_code=500, detail=str(e)) 
    
    logger.info(f"API key created successfully")
    return apiResponse(
        success=True,
        message="API key created successfully, Store it securely",
        data={"api_key": api_key,"user_name": request.user_name,"org_name": request.org_name,"user_email": request.user_email}
    )


# Check key details
@router.get("/check-key")
async def check_api_key(current_user: APIKey = Depends(get_current_user)):
    logger.info(f"Checking API key for user: {current_user.user_email}")
    return apiResponse(
        success=True,
        message="API key is valid",
        data={
            "user_name": current_user.user_name,
            "org_name": current_user.org_name,
            "user_email": current_user.user_email,
            "created_at": current_user.created_at
        }
    )