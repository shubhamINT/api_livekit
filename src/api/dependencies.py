from fastapi import Security, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.core.db.db_schemas import APIKey

security = HTTPBearer()

async def get_current_user(auth: HTTPAuthorizationCredentials = Security(security)) -> APIKey:
    """
    Verify the API key provided in the Authorization header.
    Expects: 'Authorization: Bearer <api_key>'
    """
    api_key_str = auth.credentials
    
    # Find the API key in the database
    api_key_doc = await APIKey.find_one(
        APIKey.api_key == api_key_str,
        APIKey.is_active == True
    )
    
    if not api_key_doc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or inactive API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return api_key_doc
