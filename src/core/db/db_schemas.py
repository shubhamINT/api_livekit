from datetime import datetime, timezone
from typing import Optional, Literal, List, Dict
from beanie import Document, Indexed
from pydantic import BaseModel, Field, EmailStr
from pymongo import IndexModel
from pymongo.collation import Collation
import uuid


# API key storage
class APIKey(Document):
    """API key model for Beanie ODM"""

    api_key: Indexed(str, unique=True)
    user_name: str
    org_name: Optional[str] = None
    user_email: Indexed(EmailStr, unique=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    is_super_admin: bool = False

    class Settings:
        name = "api_keys"  # Collection name in MongoDB


class AssistantInteractionConfig(BaseModel):
    """Configuration for how the assistant interacts with the user."""

    speaks_first: bool = True
    filler_words: bool = False
    silence_reprompts: bool = False
    silence_reprompt_interval: float = 10.0
    silence_max_reprompts: int = 2
    background_sound_enabled: bool = True
    thinking_sound_enabled: bool = True
    allow_interruptions: bool = False
    # Seconds of every agent utterance during which caller audio is blanked. Stops repeats
    # ("Hello? Hello?") and short filler sounds ("um", "uh") from barging in — SpeechGate
    # cannot filter those, since they are genuine speech. Raise it to reject more fillers,
    # at the cost of the caller being unable to genuinely interrupt for that long.
    input_guard_window_sec: float = 3.0
    preferred_languages: Optional[List[str]] = None
    # STT moved to Assistant.assistant_stt_model / assistant_stt_config (mirrors TTS).
    # scripts/migrate_stt_config.py backfills the retired user_stt_provider / stt_api_key.
    # Hard ceiling for active-call duration. None → falls back to platform default (30 min) at runtime.
    max_call_duration_minutes: Optional[float] = None


class EndCallWebhookConfig(BaseModel):
    """Per-assistant delivery settings for the end-of-call webhook.

    Both fields are optional and mean "use the server default"
    (`END_CALL_WEBHOOK_TIMEOUT` / `END_CALL_WEBHOOK_ATTEMPTS`). They exist because the right
    values belong to the *receiver*, not to the platform: one customer's endpoint answers in
    80 ms, another writes the payload into its own database first and needs 45 seconds, and a
    single global timeout has to be generous enough for the slowest of them — which delays
    every worker teardown behind the slowest customer.

    Same shape as `InboundContextStrategy.timeout_seconds`, deliberately.
    """

    timeout_seconds: Optional[float] = None
    attempts: Optional[int] = None


class GreetingAudioConfig(BaseModel):
    """Per-assistant reference to a greeting audio from the reusable library.

    When enabled, the worker resolves audio_id to an AudioAsset and plays its WAV
    via session.say(audio=...), skipping LLM + TTS for the greeting. Any failure
    (missing/inactive asset, download error) falls back to the model greeting.
    """

    enabled: bool = False
    audio_id: Optional[str] = None  # references AudioAsset.audio_id


# Reusable audio library — one upload, attachable to many assistants
class AudioAsset(Document):
    """A user-uploaded audio file stored in S3, attachable to assistants as a greeting."""

    audio_id: Indexed(str, unique=True)
    audio_name: str
    transcript: str  # literal spoken words, added to chat context so the model knows it greeted
    s3_key: str  # internal S3 object key (used for download/delete, not exposed in API)
    s3_url: str  # plain public URL, stored like CallRecord.recording_path
    duration_seconds: float
    filename: Optional[str] = None  # original upload filename, for display
    created_by_email: EmailStr
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True

    class Settings:
        name = "audio_assets"  # Collection name in MongoDB


# Assistant storage
class Assistant(Document):
    """Assistant model for Beanie ODM"""

    assistant_id: Indexed(str, unique=True)
    assistant_name: str
    assistant_description: Optional[str] = None
    assistant_mode: str = "pipeline"  # "pipeline" | "realtime" | "cascade"
    assistant_llm_config: Optional[Dict] = None  # shared assistant LLM config; pipeline currently uses only api_key
    assistant_tts_model: Optional[str] = None  # required for pipeline, ignored for realtime
    assistant_tts_config: Optional[Dict] = None  # required for pipeline, ignored for realtime
    assistant_stt_model: Optional[str] = None  # "native" | "sarvam" | "cartesia" | "deepgram" | "elevenlabs" | "openai"; None -> sarvam. Ignored for realtime
    assistant_stt_config: Optional[Dict] = None  # provider config; None -> provider defaults + system key
    assistant_prompt: str = Field(default="")
    assistant_start_instruction: Optional[str] = None
    assistant_interaction_config: AssistantInteractionConfig = Field(default_factory=AssistantInteractionConfig)
    assistant_greeting_audio: GreetingAudioConfig = Field(default_factory=GreetingAudioConfig)
    assistant_end_call_enabled: bool = False
    assistant_end_call_trigger_phrase: Optional[str] = None
    assistant_end_call_agent_message: Optional[str] = None
    assistant_end_call_url: Optional[str] = None
    # Delivery tuning for the webhook posted to assistant_end_call_url. Absent or with null
    # fields means the server defaults apply.
    assistant_end_call_webhook: EndCallWebhookConfig = Field(
        default_factory=EndCallWebhookConfig
    )
    assistant_created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    assistant_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    assistant_created_by_email: EmailStr
    assistant_updated_by_email: EmailStr
    assistant_is_active: bool = True
    tool_ids: List[str] = []  # References to Tool.tool_id

    class Settings:
        name = "assistants"  # Collection name in MongoDB
        indexes = [
            IndexModel(
                [("assistant_name", 1)], collation=Collation(locale="en", strength=2)
            )
        ]


class OutboundSIP(Document):
    """Outbound SIP trunk model for Beanie ODM"""

    trunk_id: Indexed(str, unique=True)
    trunk_name: str
    trunk_type: str = "twilio"  # "twilio" or "exotel"
    trunk_config: Dict = {}  # Stores Twilio or Exotel specific config
    passthrough_mode: bool = False  # when True, bridges web user directly to SIP (no AI agent)
    passthrough_webhook_url: Optional[str] = None  # POST target for end-of-call notification in passthrough mode
    trunk_created_by_email: EmailStr
    trunk_updated_by_email: EmailStr
    trunk_created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trunk_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    trunk_is_active: bool = True

    class Settings:
        name = "outbound_sip"  # Collection name in MongoDB


class InboundSIP(Document):
    """Inbound number to assistant mapping."""

    inbound_id: Indexed(str, unique=True)
    phone_number: str
    phone_number_normalized: str
    inbound_config: Dict = Field(default_factory=dict)
    assistant_id: Optional[str] = None
    inbound_context_strategy_id: Optional[str] = None
    service: Literal["exotel", "twilio"] = "exotel"
    created_by_email: EmailStr
    updated_by_email: EmailStr
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True

    class Settings:
        name = "inbound_sip"
        indexes = [
            IndexModel(
                [("phone_number_normalized", 1)],
                unique=True,
                partialFilterExpression={"is_active": True},
            )
        ]


class InboundContextStrategy(Document):
    """Reusable inbound caller-context resolution strategy."""

    strategy_id: Indexed(str, unique=True)
    strategy_name: str
    strategy_type: Literal["webhook"] = "webhook"
    strategy_config: Dict = Field(default_factory=dict)
    strategy_created_by_email: EmailStr
    strategy_updated_by_email: EmailStr
    strategy_created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    strategy_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    strategy_is_active: bool = True

    class Settings:
        name = "inbound_context_strategies"
        indexes = [
            IndexModel(
                [("strategy_name", 1)], collation=Collation(locale="en", strength=2)
            ),
            # /list: filter by owner + active, sort by newest first.
            IndexModel([("strategy_created_by_email", 1), ("strategy_created_at", -1)]),
        ]


class CallRecord(Document):
    room_name: Indexed(str, unique=True)
    queue_id: Optional[str] = None   # set for outbound calls dispatched via queue
    assistant_id: Optional[str] = None
    assistant_name: Optional[str] = None
    is_passthrough: bool = False  # True when web user talks directly to SIP with no AI agent
    to_number: str
    call_status: Literal[
        "initiated",
        "answered",
        "completed",
        "failed",
        "busy",
        "no_answer",
        "rejected",
        "cancelled",
        "unreachable",
        "timeout",
    ] = "initiated"
    call_status_reason: Optional[str] = None
    sip_status_code: Optional[int] = None
    sip_status_text: Optional[str] = None
    answered_at: Optional[datetime] = None
    # Set once session.py's entrypoint actually reaches session.start() successfully — the
    # earliest reliable "the agent is really running in this room" signal. SIP/telephony can
    # mark a call "answered" with no agent ever having joined (crashed entrypoint, provider
    # connect failure, dispatcher/worker overload); a dispatcher watchdog polls this to force
    # -end calls that never get here instead of quietly occupying a slot for their full
    # duration with dead air. See outbound_dispatcher/dispatcher.py's _watch_agent_join.
    agent_ready_at: Optional[datetime] = None
    call_end_reason: Optional[str] = None  # natural | max_duration_exceeded | sip_bye | rtp_silence | no_rtp | livekit_disconnected | error
    recording_path: Optional[str] = None
    recording_egress_id: Optional[str] = None
    transcripts: List[Dict] = []  # [{speaker, text, timestamp}]
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: Optional[datetime] = None
    call_duration_minutes: Optional[float] = None
    billable_duration_minutes: Optional[int] = None
    # Analytics fields
    created_by_email: Optional[EmailStr] = None
    call_type: Optional[Literal["outbound", "inbound", "web"]] = None
    call_service: Optional[Literal["exotel", "twilio", "web"]] = None
    platform_number: Optional[str] = None  # platform's own Exotel/Twilio number used

    class Settings:
        name = "call_records"
        indexes = [
            IndexModel([("created_by_email", 1), ("started_at", -1)]),
            IndexModel([("created_by_email", 1), ("assistant_id", 1), ("started_at", -1)]),
            IndexModel([("created_by_email", 1), ("to_number", 1), ("started_at", -1)]),
            IndexModel([("started_at", -1)]),
            # Serves the live-session count the concurrency caps run on every inbound INVITE
            # and every web-call request. call_status leads because live calls are a tiny
            # fraction of history, so it is by far the more selective predicate; call_type
            # then lets the same index answer the per-type counts without a second scan.
            # Without this the count was a full collection scan that grew with total call
            # history rather than with the number of calls actually in progress.
            IndexModel([("call_status", 1), ("call_type", 1)]),
        ]


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
    tool_created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tool_updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tool_is_active: bool = True

    class Settings:
        name = "tools"  # Collection name in MongoDB


class OutboundCallQueue(Document):
    """Queue for outbound calls — dispatcher processes these at a controlled rate."""

    queue_id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    user_email: str
    assistant_id: Optional[str] = None
    assistant_name: Optional[str] = None
    trunk_id: str
    to_number: str
    call_service: Literal["twilio", "exotel"]
    job_metadata: Dict = Field(default_factory=dict)
    status: str = "pending"   # pending | dispatching | dispatched | failed
    queued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    dispatched_at: Optional[datetime] = None
    room_name: Optional[str] = None
    retry_count: int = 0
    last_error: Optional[str] = None
    passthrough_room_name: Optional[str] = None  # pre-created room for passthrough calls

    class Settings:
        name = "outbound_call_queue"
        indexes = [
            IndexModel([("status", 1), ("queued_at", 1)]),  # dispatcher poll query
            IndexModel([("queue_id", 1)], unique=True),
            IndexModel([("user_email", 1), ("queued_at", -1)]),
        ]


class ActivityLog(Document):
    """User-visible activity log — one record per notable event (tool call, webhook fire)."""

    user_email: Indexed(str)  # used to scope logs to the owning user
    log_type: Literal["tool_call", "end_call_webhook", "inbound_context_lookup"]
    assistant_id: Optional[str] = None
    room_name: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["success", "error"]
    request_data: Optional[Dict] = None  # what was sent outbound
    response_data: Optional[Dict] = None  # what came back
    latency_ms: Optional[int] = None
    message: str  # human-readable one-liner

    class Settings:
        name = "activity_logs"


class UsageRecord(Document):
    """Per-call usage metrics for token and duration tracking."""

    room_name: Indexed(str, unique=True)  # 1:1 with CallRecord
    assistant_id: str
    user_email: Indexed(str)
    tts_provider: Optional[str] = None
    call_service: Optional[str] = None

    # LLM pipeline info
    mode: Optional[str] = None  # "pipeline" | "realtime" | "cascade"
    llm_realtime_provider: Optional[str] = None  # LLM vendor "gemini" | "openai" (recorded for all modes)
    llm_model: Optional[str] = None  # e.g. "gpt-4.1-mini", "gpt-realtime-1.5"

    # LLM tokens (from session.usage — exact values)
    llm_input_audio_tokens: int = 0
    llm_input_text_tokens: int = 0
    llm_input_cached_audio_tokens: int = 0
    llm_input_cached_text_tokens: int = 0
    llm_output_audio_tokens: int = 0
    llm_output_text_tokens: int = 0
    llm_total_tokens: int = 0

    # TTS usage (from session.usage — exact values)
    tts_characters_count: int = 0
    tts_audio_duration: float = 0.0  # seconds

    # STT usage. Only a mode with a standalone STT stage (cascade) reports these; in
    # pipeline/realtime the LLM transcribes internally and the cost is inside its tokens.
    stt_provider: Optional[str] = None  # "sarvam" | "cartesia" | "deepgram" | "elevenlabs" | "openai" | "native"
    stt_model: Optional[str] = None  # e.g. "saaras:v3", "ink-whisper", "nova-3", "scribe_v2_realtime", "gpt-4o-mini-transcribe"
    stt_audio_duration: float = 0.0  # seconds of audio transcribed

    # Telephony duration (copied from CallRecord for aggregation convenience)
    call_duration_minutes: float = 0.0

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "usage_records"
        indexes = [
            IndexModel([("user_email", 1), ("created_at", -1)]),
            IndexModel([("user_email", 1), ("assistant_id", 1), ("created_at", -1)]),
        ]
