from pydantic import BaseModel, EmailStr, Field 
from typing import Optional, Literal, Union, Annotated, List


# Model for creating API key
class CreateApiKey(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=20, description="User's name (cannot be empty)")
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
    assistant_name: str = Field(..., min_length=1, max_length=20, description="Assistant's name (cannot be empty)")
    assistant_description: Optional[str] = Field(None, max_length=50, description="Assistant's description (optional)")
    assistant_prompt: str = Field(..., description="Assistant's prompt (cannot be empty)")
    assistant_tts_model: Literal["cartesia", "elevenlabs"] = Field(..., description="TTS Provider")
    assistant_tts_voice_id: str = Field(..., min_length=1, max_length=50, description="TTS Voice ID")
    assistant_start_instruction: Optional[str] = Field(None, max_length=100, description="Assistant's start instruction (optional)")
    assistant_welcome_message: Optional[str] = Field(None, max_length=100, description="Assistant's welcome message (optional)")
    
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
                "assistant_start_instruction": "Start instruction(Optional) Provide any one of them between start_instruction and welcome_message",
                "assistant_welcome_message": "Welcome message(Optional) Provide any one of them between start_instruction and welcome_message"
            }
        }


# For Outbound Trunk creation
class CreateOutboundTrunk(BaseModel):
    trunk_name: str = Field(..., min_length=1, max_length=20, description="Trunk name (cannot be empty)")
    trunk_address: str = Field(..., min_length=1, max_length=20, description="Trunk address (cannot be empty)")
    trunk_numbers: List[str] = Field(..., min_length=1, max_length=20, description="Trunk numbers (cannot be empty)")
    trunk_auth_username: str = Field(..., min_length=1, max_length=20, description="Trunk auth username (cannot be empty)")
    trunk_auth_password: str = Field(..., min_length=1, max_length=20, description="Trunk auth password (cannot be empty)")
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