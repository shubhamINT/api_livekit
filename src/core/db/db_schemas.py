from datetime import datetime
from typing import Optional, Literal, Text, List, Dict
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
    assistant_created_at: datetime = Field(default_factory=datetime.utcnow)
    assistant_updated_at: datetime = Field(default_factory=datetime.utcnow)
    assistant_created_by_email: EmailStr
    assistant_updated_by_email: EmailStr
    assistant_is_active: bool = True
    
    class Settings:
        name = "assistants"  # Collection name in MongoDB


class OutboundSIP(Document):
    """Outbound SIP trunk model for Beanie ODM"""
    trunk_id: Indexed(str, unique=True)
    trunk_name: str
    trunk_created_by_email: EmailStr
    trunk_updated_by_email: EmailStr
    trunk_created_at: datetime = Field(default_factory=datetime.utcnow)
    trunk_updated_at: datetime = Field(default_factory=datetime.utcnow)
    trunk_is_active: bool = True
    
    class Settings:
        name = "outbound_sip"  # Collection name in MongoDB


class CallRecord(Document):
    room_name: Indexed(str, unique=True)
    assistant_id: str
    assistant_name: str
    to_number: str
    recording_path: Optional[str] = None
    transcripts: List[Dict] = []  # [{speaker, text, timestamp}]
    started_at: datetime = Field(default_factory=datetime.utcnow)
    ended_at: Optional[datetime] = None
    call_duration_minutes: Optional[float] = None
    
    class Settings:
        name = "call_records"