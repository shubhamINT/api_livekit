from typing import Any, Literal, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1, description="List of chat messages")
    assistant_id: Optional[str] = Field(None, description="Optional assistant ID to inherit LLM configuration")
    provider: Optional[Literal["openai", "gemini"]] = Field(None, description="LLM provider name")
    model: Optional[str] = Field(None, description="Model identifier")
    temperature: Optional[float] = Field(None, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: Optional[int] = Field(None, gt=0, description="Maximum completion tokens")
    stream: bool = Field(False, description="Whether to stream response via Server-Sent Events (SSE)")


class ChatCompletionResponse(BaseModel):
    status: str = "success"
    data: dict[str, Any]

