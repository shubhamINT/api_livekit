from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from src.api.routes import auth, health
from src.core.logger import setup_logging

# Setup logging
setup_logging()

app = FastAPI(title="LiveKit AI Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/auth")
app.include_router(health.router)

if __name__ == "__main__":
    import uvicorn
    from src.core.config import settings
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
