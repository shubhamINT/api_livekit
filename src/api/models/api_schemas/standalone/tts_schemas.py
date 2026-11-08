from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class SynthesizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=5000, description="Text to synthesize into speech")
    assistant_id: Optional[str] = Field(None, description="Optional assistant ID to inherit TTS configuration")
    provider: Optional[Literal["cartesia", "sarvam", "elevenlabs", "mistral"]] = Field(
        None, description="TTS provider name"
    )
    model: Optional[str] = Field(None, description="TTS model identifier")
    voice: Optional[str] = Field(None, description="Voice ID or speaker name")
    language: Optional[str] = Field(None, description="Language code")
    save_to_library: bool = Field(False, description="Whether to persist output to user audio library")
    response_format: Literal["audio", "json"] = Field(
        "audio", description="Response format: binary audio stream ('audio') or JSON with base64 payload ('json')"
    )

    @field_validator("text")
    @classmethod
    def validate_non_empty_text(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("text cannot be empty or whitespace only")
        return v

