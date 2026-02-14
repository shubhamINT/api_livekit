from datetime import datetime
from typing import Optional, Literal, Text, List, Dict
from beanie import Document, Indexed
from pydantic import BaseModel, Field, EmailStr


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
    assistant_tts_voice_id: Optional[str] = None
    assistant_tts_speaker: Optional[str] = None
    assistant_prompt: str = Field(default="")
    assistant_start_instruction: Optional[str] = None
    assistant_end_call_url: Optional[str] = None
    assistant_created_at: datetime = Field(default_factory=datetime.utcnow)
    assistant_updated_at: datetime = Field(default_factory=datetime.utcnow)
    assistant_created_by_email: EmailStr
    assistant_updated_by_email: EmailStr
    assistant_is_active: bool = True
    tool_ids: List[str] = []  # References to Tool.tool_id

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


class ToolParameter(BaseModel):
    """Single parameter definition for a tool."""

    name: str
    type: Literal["string", "number", "boolean", "object", "array"] = "string"
    description: Optional[str] = None
    required: bool = True
    enum: Optional[List[str]] = None


class Tool(Document):
    """Tool definition stored in MongoDB."""

    tool_id: Indexed(str, unique=True)
    tool_name: str  # e.g. "lookup_weather" (snake_case, unique per user)
    tool_description: str  # Docstring sent to the LLM
    tool_parameters: List[ToolParameter] = []
    tool_execution_type: Literal["webhook", "static_return"] = "webhook"
    tool_execution_config: Dict = {}  # {"url": "..."} or {"value": ...}
    tool_created_by_email: EmailStr
    tool_updated_by_email: EmailStr
    tool_created_at: datetime = Field(default_factory=datetime.utcnow)
    tool_updated_at: datetime = Field(default_factory=datetime.utcnow)
    tool_is_active: bool = True

    class Settings:
        name = "tools"  # Collection name in MongoDB
