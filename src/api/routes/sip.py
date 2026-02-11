from fastapi import APIRouter, HTTPException, Depends
from src.api.models.api_schemas import CreateOutboundTrunk
from src.api.models.response_models import apiResponse
from src.core.db.db_schemas import OutboundSIP, APIKey
from src.api.dependencies import get_current_user
from src.core.logger import logger, setup_logging
from src.services.livekit.livekit_svc import LiveKitService
import uuid

router = APIRouter()
setup_logging()
livekit_services = LiveKitService()

# Create Outbound Trunk
@router.post("/create-outbound-trunk")
async def create_outbound_trunk(request: CreateOutboundTrunk, current_user: APIKey = Depends(get_current_user)):
    logger.info(f"Received request to create outbound trunk")
    try:
        
        if request.trunk_type != "twilio":
            raise HTTPException(status_code=400, detail="Trunk type not supported. Currently present only from twilio")
        
        # Creating outbout trunk
        try:
            trunk = livekit_services.create_sip_outbound_trunk(
                trunk_name=request.trunk_name,
                trunk_address=request.trunk_address,
                trunk_numbers=request.trunk_numbers,
                trunk_auth_username=request.trunk_auth_username,    
                trunk_auth_password=request.trunk_auth_password
            )
        except Exception as e:
            logger.error(f"Failed to create outbound trunk: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to create outbound trunk in livekit: {str(e)}")

        logger.info(f"Inserting outbound trunk into database")
        outbound_trunk = OutboundSIP(
            trunk_id=trunk.id, 
            trunk_name=request.trunk_name, 
            trunk_created_by_email=current_user.user_email, 
            trunk_updated_by_email=current_user.user_email)
        await outbound_trunk.insert()
    except Exception as e:
        logger.error(f"Failed to create outbound trunk: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create outbound trunk in database: {str(e)}") 
    
    logger.info(f"Outbound trunk created successfully")
    return apiResponse(
        success=True,
        message="Outbound trunk created successfully, Store the trunk id securely.",
        data={"trunk_id": trunk.id}
    )