from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import auth, health, assistant, sip, call, tool
from src.core.logger import setup_logging, logger
from src.core.db.database import init_db, close_db
from src.api.models.response_models import apiResponse

# Setup logging
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan events"""
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


app = FastAPI(title="LiveKit AI Backend", version="1.0.0", lifespan=lifespan)

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    from fastapi.encoders import jsonable_encoder
    error_msg = str(exc)
    # Log detailed error
    logger.error(f"Validation Error: {error_msg}")
    
    # Clean up errors to ensure they are JSON serializable
    errors = jsonable_encoder(exc.errors())
    
    return JSONResponse(
        status_code=422,
        content=apiResponse(
            success=False,
            message=f"Validation Error: {error_msg}",
            data={"errors": errors}
        ).model_dump()
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=apiResponse(
            success=False,
            message=str(exc.detail),
            data={}
        ).model_dump()
    )

@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    import traceback
    error_msg = str(exc)
    trace = traceback.format_exc()
    logger.error(f"Generic Error: {error_msg}\nTraceback: {trace}")
    
    return JSONResponse(
        status_code=500,
        content=apiResponse(
            success=False,
            message=f"Internal Server Error: {error_msg}",
            data={}
        ).model_dump()
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(health.router, tags=["Health"])
app.include_router(assistant.router, prefix="/assistant", tags=["Assistant"])
app.include_router(sip.router, prefix="/sip", tags=["Outbound SIP"])
app.include_router(call.router, prefix="/call", tags=["Call"])
app.include_router(tool.router, prefix="/tool", tags=["Tool"])

if __name__ == "__main__":
    import uvicorn
    from src.core.config import settings
    uvicorn.run("src.api.server:app", host="0.0.0.0", port=int(settings.PORT), reload=True)
