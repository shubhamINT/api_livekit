from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

router = APIRouter()

@router.get("/health", response_class=PlainTextResponse)
async def health():
    return "ok"
