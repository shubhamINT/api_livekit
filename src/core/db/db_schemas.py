from datetime import datetime
from typing import Optional, Literal, Text
from beanie import Document, Indexed
from pydantic import Field, EmailStr


# API key storage
class APIKey(Document):
    """API key model for Beanie ODM"""
    api_key: Indexed(str, unique=True)
    user_name: str
    org_name: Optional[str] = None
    user_email: Indexed(EmailStr, unique=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_active: bool = True
    
    class Settings:
        name = "api_keys"  # Collection name in MongoDB


# Assistant storage
class Assistant(Document):
    """Assistant model for Beanie ODM"""
    assistant_id: Indexed(str, unique=True)
    assistant_name: str
    assistant_description: Optional[str] = None
    assistant_tts_model: str
    assistant_tts_voice_id: str
    assistant_prompt: str = Field(default="")
    assistant_start_instruction: Optional[str] = None
    assistant_welcome_message: Optional[str] = None
    assistant_created_at: datetime = Field(default_factory=datetime.utcnow)
    assistant_updated_at: datetime = Field(default_factory=datetime.utcnow)
    assistant_is_active: bool = True
    
    class Settings:
        name = "assistants"  # Collection name in MongoDB
