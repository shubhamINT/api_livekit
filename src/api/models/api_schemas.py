from pydantic import BaseModel, EmailStr, Field, model_validator
from typing import Optional, Literal, Union, Annotated, List


# Model for creating API key
class CreateApiKey(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=100, description="User's name (cannot be empty)")
    org_name: Optional[str] = Field(None, max_length=100, description="Organization name (optional)")
    user_email: EmailStr = Field(..., description="User's email address (cannot be empty)")

    class Config:
        # Strip whitespace from string fields
        str_strip_whitespace = True
        # Example for API documentation
        json_schema_extra = {
            "example": {
                "user_name": "Shubham Halder",
                "org_name": "Indus Net Technologies",
                "user_email": "shubham@example.com",
            }
        }


# For Assistant creation
class CreateAssistant(BaseModel):
    assistant_name: str = Field(..., min_length=1, max_length=100, description="Assistant's name (cannot be empty)")
    assistant_description: str = Field(..., description="Assistant's description (optional)")
    assistant_prompt: str = Field(..., description="Assistant's prompt (cannot be empty)")
    assistant_tts_model: Literal["cartesia", "sarvam"] = Field(..., description="TTS Provider")
    assistant_tts_speaker: Optional[str] = Field(None, max_length=30, description="Sarvam speaker (required for sarvam)")
    assistant_tts_voice_id: Optional[str] = Field(None, min_length=1, max_length=100, description="TTS Voice ID (required for cartesia or sarvam)")
    assistant_start_instruction: Optional[str] = Field(None, max_length=200, description="Assistant's start instruction")
    assistant_end_call_url: Optional[str] = Field(None, max_length=200, description="Assistant's end call url")

    class Config:
        # Strip whitespace from string fields
        str_strip_whitespace = True
        # Example for API documentation
        json_schema_extra = {
            "example": {
                "assistant_name": "Test Assistant",
                "assistant_description": "Test Assistant Description(Optional)",
                "assistant_prompt": "You are a helpful assistant. This is the prompt for the assistant You can have placeholders liken {{name}} and {{email}} in the prompt",
                "assistant_tts_model": "cartesia",
                "assistant_tts_voice_id": "Cartesia Voice ID",
                "assistant_start_instruction": "Start instruction. This can have placeholders liken {{name}} in the start instruction",
                "assistant_end_call_url": "End call url. This is the place where sever will sen dthe detial at the end of the call",
                "assistant_tts_speaker": "Sarvam speaker. Only allowed for sarvam",
            }
        }

    @model_validator(mode="after")
    def validate_tts_fields(self):
        if self.assistant_tts_model == "cartesia":
            if not self.assistant_tts_voice_id:
                raise ValueError(
                    "assistant_tts_voice_id is required for cartesia."
                )
            if self.assistant_tts_speaker:
                raise ValueError("assistant_tts_speaker is only allowed for sarvam.")
        elif self.assistant_tts_model == "sarvam":
            if not self.assistant_tts_speaker:
                raise ValueError("assistant_tts_speaker is required for sarvam.")
            if self.assistant_tts_voice_id:
                raise ValueError("assistant_tts_voice_id is not allowed for sarvam.")
        return self


# For Assistant update
class UpdateAssistant(BaseModel):
    assistant_name: Optional[str] = Field(None, min_length=1, max_length=100, description="Assistant's name (optional)")
    assistant_description: Optional[str] = Field(None, description="Assistant's description (optional)")
    assistant_prompt: Optional[str] = Field(None, description="Assistant's prompt (optional)")
    assistant_tts_model: Optional[Literal["cartesia", "sarvam"]] = Field(None, description="TTS Provider (optional)")
    assistant_tts_speaker: Optional[str] = Field(None, max_length=30, description="Sarvam speaker (optional)")
    assistant_tts_voice_id: Optional[str] = Field(None, min_length=1, max_length=100, description="TTS Voice ID (optional)")
    assistant_start_instruction: Optional[str] = Field(None, max_length=200, description="Assistant's start instruction (optional)")
    assistant_end_call_url: Optional[str] = Field(None, max_length=200, description="Assistant's end call url (optional)")

    class Config:
        # Strip whitespace from string fields
        str_strip_whitespace = True
        # # Example for API documentation
        # json_schema_extra = {
        #     "example": {
        #         "assistant_name": "Updated Assistant Name",
        #         "assistant_prompt": "You are an updated assistant.",
        #         "assistant_tts_voice_id": "New Voice ID",
        #     }
        # }

    @model_validator(mode="after")
    def validate_tts_fields(self):
        if self.assistant_tts_model == "cartesia":
            if not self.assistant_tts_voice_id:
                raise ValueError(
                    "assistant_tts_voice_id is required for cartesia."
                )
            if self.assistant_tts_speaker:
                raise ValueError("assistant_tts_speaker is only allowed for sarvam.")
        elif self.assistant_tts_model == "sarvam":
            if not self.assistant_tts_speaker:
                raise ValueError("assistant_tts_speaker is required for sarvam.")
            if self.assistant_tts_voice_id:
                raise ValueError("assistant_tts_voice_id is not allowed for sarvam.")
        else:
            if self.assistant_tts_speaker and self.assistant_tts_voice_id:
                raise ValueError(
                    "Provide only one of assistant_tts_speaker or assistant_tts_voice_id."
                )
        return self


# For Outbound Trunk creation
class CreateOutboundTrunk(BaseModel):
    trunk_name: str = Field(..., min_length=1, max_length=100, description="Trunk name (cannot be empty)")
    trunk_address: str = Field(..., min_length=1, max_length=100, description="Trunk address (cannot be empty)")
    trunk_numbers: List[str] = Field(..., description="Trunk numbers (cannot be empty)")
    trunk_auth_username: str = Field(..., min_length=1, max_length=100, description="Trunk auth username (cannot be empty)")
    trunk_auth_password: str = Field(..., min_length=1, max_length=100, description="Trunk auth password (cannot be empty)")
    trunk_type: Literal["exotel", "twilio"] = Field(..., description="Trunk type (cannot be empty) Currently present only from twilio")

    class Config:
        # Strip whitespace from string fields
        str_strip_whitespace = True
        # Example for API documentation
        json_schema_extra = {
            "example": {
                "trunk_name": "Test Trunk",
                "trunk_address": "Test Trunk Address",
                "trunk_numbers": ["Test Trunk Number"],
                "trunk_auth_username": "Test Trunk Auth Username",
                "trunk_auth_password": "Test Trunk Auth Password",
                "trunk_type": "twilio, Currently present only from twilio",
            }
        }


# Triggure Outbound call
class TriggerOutboundCall(BaseModel):
    assistant_id: str = Field(..., min_length=1, max_length=100, description="Assistant ID (cannot be empty)")
    trunk_id: str = Field(..., min_length=1, max_length=100, description="Trunk ID (cannot be empty)")
    to_number: str = Field(..., min_length=1, max_length=100, description="To Number (cannot be empty)")
    call_service: Literal["twilio", "exotel"] = Field(..., description="Call service (cannot be empty) Currently present only from twilio")
    metadata: Optional[dict] = Field(None, description="Metadata (optional)")

    class Config:
        # Strip whitespace from string fields
        str_strip_whitespace = True
        # Example for API documentation
        json_schema_extra = {
            "example": {
                "assistant_id": "Test Assistant ID",
                "trunk_id": "Test Trunk ID",
                "to_number": "Test To Number",
                "call_service": "twilio, Currently present only from twilio",
                "metadata": {"extra": "value about the call"},
            }
        }
