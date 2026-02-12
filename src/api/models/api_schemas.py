from pydantic import BaseModel, EmailStr, Field 
from typing import Optional, Literal, Union, Annotated, List


# Model for creating API key
class CreateApiKey(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=50, description="User's name (cannot be empty)")
    org_name: Optional[str] = Field(None, max_length=50, description="Organization name (optional)")
    user_email: EmailStr = Field(..., description="User's email address (cannot be empty)")
    
    class Config:
        # Strip whitespace from string fields
        str_strip_whitespace = True
        # Example for API documentation
        json_schema_extra = {
            "example": {
                "user_name": "Shubham Halder",
                "org_name": "Indus Net Technologies",
                "user_email": "shubham@example.com"
            }
        }


# For Assistant creation
class CreateAssistant(BaseModel):
    assistant_name: str = Field(..., min_length=1, max_length=50, description="Assistant's name (cannot be empty)")
    assistant_description: str = Field(..., description="Assistant's description (optional)")
    assistant_prompt: str = Field(..., description="Assistant's prompt (cannot be empty)")
    assistant_tts_model: Literal["cartesia", "elevenlabs"] = Field(..., description="TTS Provider")
    assistant_tts_voice_id: str = Field(..., min_length=1, max_length=100, description="TTS Voice ID")
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
                "assistant_prompt": "You are a helpful assistant.",
                "assistant_tts_model": "cartesia",
                "assistant_tts_voice_id": "Cartesia Voice ID",
                "assistant_start_instruction": "Start instruction",
                "assistant_end_call_url": "End call url. This is the place where sever will sen dthe detial at the end of the call"
            }
        }


# For Assistant update
class UpdateAssistant(BaseModel):
    assistant_name: Optional[str] = Field(None, min_length=1, max_length=50, description="Assistant's name (optional)")
    assistant_description: Optional[str] = Field(None, description="Assistant's description (optional)")
    assistant_prompt: Optional[str] = Field(None, description="Assistant's prompt (optional)")
    assistant_tts_model: Optional[Literal["cartesia", "elevenlabs"]] = Field(None, description="TTS Provider (optional)")
    assistant_tts_voice_id: Optional[str] = Field(None, min_length=1, max_length=100, description="TTS Voice ID (optional)")
    assistant_start_instruction: Optional[str] = Field(None, max_length=200, description="Assistant's start instruction (optional)")
    assistant_end_call_url: Optional[str] = Field(None, max_length=200, description="Assistant's end call url (optional)")
    
    class Config:
        # Strip whitespace from string fields
        str_strip_whitespace = True
        # Example for API documentation
        json_schema_extra = {
            "example": {
                "assistant_name": "Updated Assistant Name",
                "assistant_prompt": "You are an updated assistant.",
                "assistant_tts_voice_id": "New Voice ID"
            }
        }


# For Outbound Trunk creation
class CreateOutboundTrunk(BaseModel):
    trunk_name: str = Field(..., min_length=1, max_length=50, description="Trunk name (cannot be empty)")
    trunk_address: str = Field(..., min_length=1, max_length=50, description="Trunk address (cannot be empty)")
    trunk_numbers: List[str] = Field(..., description="Trunk numbers (cannot be empty)")
    trunk_auth_username: str = Field(..., min_length=1, max_length=50, description="Trunk auth username (cannot be empty)")
    trunk_auth_password: str = Field(..., min_length=1, max_length=50, description="Trunk auth password (cannot be empty)")
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
                "trunk_type": "twilio, Currently present only from twilio"
            }
        }


# Triggure Outbound call
class TriggerOutboundCall(BaseModel):
    assistant_id: str = Field(..., min_length=1, max_length=50, description="Assistant ID (cannot be empty)")
    trunk_id: str = Field(..., min_length=1, max_length=50, description="Trunk ID (cannot be empty)")
    to_number: str = Field(..., min_length=1, max_length=50, description="To Number (cannot be empty)")
    call_service: Literal["twilio", "exotel"] = Field(..., description="Call service (cannot be empty) Currently present only from twilio")
    metadata: dict = Field(..., description="Metadata (cannot be empty)")

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
                "metadata": {"extra": "value about the call"}
            }
        }