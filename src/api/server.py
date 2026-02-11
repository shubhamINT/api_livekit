from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import auth, health, assistant
from src.core.logger import setup_logging
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
    import traceback
    error_msg = str(exc)
    # Log detailed error
    print(f"Validation Error: {error_msg}")
    return JSONResponse(
        status_code=422,
        content=apiResponse(
            success=False,
            message=f"Validation Error: {error_msg}",
            data={"errors": exc.errors()}
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
    print(f"Generic Error: {error_msg}\nTraceback: {trace}")
    
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

if __name__ == "__main__":
    import uvicorn
    from src.core.config import settings
    uvicorn.run("src.api.server:app", host="0.0.0.0", port=int(settings.PORT), reload=True)
