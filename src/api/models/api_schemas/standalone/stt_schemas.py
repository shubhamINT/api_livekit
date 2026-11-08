from typing import Literal, Optional
from pydantic import BaseModel, Field


class TranscribeResponseData(BaseModel):
    text: str
    language: Optional[str] = None
    duration_seconds: Optional[float] = None
    provider: str
    model: str


class TranscribeResponse(BaseModel):
    status: str = "success"
    data: TranscribeResponseData

