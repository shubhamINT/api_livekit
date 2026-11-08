import io
import uuid
from decimal import Decimal
from typing import Any, Optional
import av
from fastapi import HTTPException

from src.core.db.db_schemas import APIKey, Assistant, UsageRecord
from src.core.logger import logger
from src.core.model_support import capabilities, speech
from src.core.pricing.calculator import price_model_usage


def probe_audio_duration(data: bytes) -> float:
    """Extract audio duration in seconds using container metadata without re-encoding."""
    if not data:
        return 0.0
    try:
        container = av.open(io.BytesIO(data))
        if container.duration:
            return round(float(container.duration / av.time_base), 3)
        if container.streams.audio:
            stream = container.streams.audio[0]
            if stream.duration and stream.time_base:
                return round(float(stream.duration * stream.time_base), 3)
    except Exception:
        pass
    return 0.0


def compute_stage_pricing(
    stage: str,  # "stt", "tts", "llm"
    provider: str,
    model: str,
    audio_duration: float = 0.0,
    characters_count: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> dict[str, Any]:
    """Compute usage statistics and estimated cost in USD for the standalone request."""
    entry_type = f"{stage}_usage"
    entry: dict[str, Any] = {
        "type": entry_type,
        "provider": provider,
        "model": model,
    }
    if stage == "stt":
        entry["audio_duration"] = float(audio_duration)
    elif stage == "tts":
        entry["characters_count"] = int(characters_count)
        entry["audio_duration"] = float(audio_duration)
    elif stage == "llm":
        entry["input_tokens"] = int(prompt_tokens)
        entry["output_tokens"] = int(completion_tokens)

    pricing_res = price_model_usage([entry])
    cost_float = float(pricing_res.estimated_cost_usd)

    usage_dict: dict[str, Any] = {
        "estimated_cost_usd": cost_float,
        "pricing_complete": pricing_res.pricing_complete,
        "provider": provider,
        "model": model,
    }
    if stage == "stt":
        usage_dict["audio_duration_seconds"] = float(audio_duration)
    elif stage == "tts":
        usage_dict["characters_count"] = int(characters_count)
        usage_dict["audio_duration_seconds"] = float(audio_duration)
    elif stage == "llm":
        usage_dict["prompt_tokens"] = int(prompt_tokens)
        usage_dict["completion_tokens"] = int(completion_tokens)
        usage_dict["total_tokens"] = int(prompt_tokens + completion_tokens)

    return usage_dict


async def resolve_stage_config(
    stage: str,  # "stt", "tts", "llm"
    user: APIKey,
    assistant_id: Optional[str] = None,
    explicit_provider: Optional[str] = None,
    explicit_model: Optional[str] = None,
    explicit_voice: Optional[str] = None,
    explicit_language: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve stage configuration from assistant inheritance and explicit overrides."""
    assistant: Optional[Assistant] = None
    if assistant_id and isinstance(assistant_id, str):
        assistant = await Assistant.find_one(
            Assistant.assistant_id == assistant_id,
            Assistant.created_by_email == user.user_email,
        )
        if not assistant:
            raise HTTPException(status_code=404, detail="Assistant not found")

    provider = explicit_provider if isinstance(explicit_provider, str) else None
    model = explicit_model if isinstance(explicit_model, str) else None
    voice = explicit_voice if isinstance(explicit_voice, str) else None
    language = explicit_language if isinstance(explicit_language, str) else None
    api_key = None

    if stage == "stt":
        if assistant and not provider:
            provider = assistant.assistant_stt_model or "sarvam"
            stt_conf = assistant.assistant_stt_config or {}
            model = model or stt_conf.get("model")
            language = language or stt_conf.get("language")
            api_key = stt_conf.get("api_key")
        provider = provider or "sarvam"
        if not model:
            if provider == "sarvam":
                model = "saaras:v3"
            elif provider == "openai":
                model = "whisper-1"
            elif provider == "cartesia":
                model = "ink-whisper"
            elif provider == "deepgram":
                model = "nova-3"
            elif provider == "elevenlabs":
                model = "scribe_v1"

        # Validate STT provider & model
        if provider not in speech.STT_ENV_KEYS:
            raise HTTPException(status_code=422, detail=f"Unsupported STT provider: '{provider}'")
        provider_models = speech.STT_MODELS_BY_PROVIDER.get(provider, set())
        if model and provider_models and model not in provider_models:
            raise HTTPException(
                status_code=422,
                detail=f"Model '{model}' is not a valid STT model for provider '{provider}'",
            )

    elif stage == "tts":
        if assistant and not provider:
            provider = assistant.assistant_tts_model or "cartesia"
            tts_conf = assistant.assistant_tts_config or {}
            model = model or tts_conf.get("model")
            voice = voice or tts_conf.get("voice") or tts_conf.get("speaker")
            language = language or tts_conf.get("language")
            api_key = tts_conf.get("api_key")
        provider = provider or "cartesia"

        # Validate TTS provider & model
        if provider not in speech.TTS_ENV_KEYS:
            raise HTTPException(status_code=422, detail=f"Unsupported TTS provider: '{provider}'")
        if provider == "sarvam":
            model = model or speech.DEFAULT_SARVAM_TTS_MODEL
            if model not in speech.SARVAM_TTS_MODELS:
                raise HTTPException(
                    status_code=422,
                    detail=f"Model '{model}' is not a valid Sarvam TTS model",
                )
            if voice:
                reason = speech.unsupported_sarvam_speaker_reason(model, voice)
                if reason:
                    raise HTTPException(status_code=422, detail=reason)
        elif provider == "elevenlabs":
            model = model or "eleven_multilingual_v2"
            eleven_models = speech.ELEVENLABS_TTS_MODELS
            if model not in eleven_models:
                raise HTTPException(
                    status_code=422,
                    detail=f"Model '{model}' is not a valid ElevenLabs TTS model",
                )
        elif provider == "cartesia":
            model = model or speech.CARTESIA_TTS_MODEL
            if model != speech.CARTESIA_TTS_MODEL:
                raise HTTPException(
                    status_code=422,
                    detail=f"Model '{model}' is not a valid cartesia TTS model — only '{speech.CARTESIA_TTS_MODEL}' is supported",
                )
        elif provider == "mistral":
            model = model or speech.MISTRAL_TTS_MODEL
            if model != speech.MISTRAL_TTS_MODEL:
                raise HTTPException(
                    status_code=422,
                    detail=f"Model '{model}' is not a valid mistral TTS model — only '{speech.MISTRAL_TTS_MODEL}' is supported",
                )
    elif stage == "llm":
        if assistant and not provider:
            llm_conf = assistant.assistant_llm_config or {}
            provider = llm_conf.get("provider", "openai")
            model = model or llm_conf.get("model")
            api_key = llm_conf.get("api_key")
        provider = provider or "openai"
        if provider not in ("openai", "gemini"):
            raise HTTPException(status_code=422, detail=f"Unsupported LLM provider: '{provider}'")
        if provider == "openai":
            model = model or "gpt-5.4"
            # Validate the model against the platform's sanctioned OpenAI model set.
            # capabilities.CASCADE_MODELS is the sanctioned set (reasoning + chat).
            if model not in capabilities.CASCADE_MODELS:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Model '{model}' is not a valid OpenAI model for this endpoint — "
                        f"choose one of: {', '.join(sorted(capabilities.CASCADE_MODELS))}"
                    ),
                )
        elif provider == "gemini":
            model = model or "gemini-2.5-flash"
            if not model or not isinstance(model, str) or not model.strip():
                raise HTTPException(status_code=422, detail="Model must be a non-empty string")

    return {
        "provider": provider,
        "model": model,
        "voice": voice,
        "language": language,
        "api_key": api_key,
        "assistant_id": assistant.assistant_id if assistant else None,
    }


async def log_standalone_usage(
    stage: str,
    user_email: str,
    provider: str,
    model: str,
    assistant_id: Optional[str] = None,
    duration_seconds: float = 0.0,
    characters_count: int = 0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
) -> dict[str, Any]:
    """Record standalone API invocation metrics in UsageRecord and return priced usage details."""
    usage_info = compute_stage_pricing(
        stage=stage,
        provider=provider,
        model=model,
        audio_duration=duration_seconds,
        characters_count=characters_count,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )

    try:
        record = UsageRecord(
            room_name=f"api_{uuid.uuid4().hex[:16]}",
            assistant_id=assistant_id or "standalone",
            user_email=user_email,
            call_service="standalone_api",
        )
        record.estimated_cost_usd = Decimal(str(usage_info.get("estimated_cost_usd", 0.0)))
        if stage == "stt":
            record.stt_provider = provider
            record.stt_model = model
            record.stt_audio_duration = float(duration_seconds)
            record.model_usage = [
                {
                    "type": "stt_usage",
                    "provider": provider,
                    "model": model,
                    "audio_duration": float(duration_seconds),
                    "estimated_cost_usd": record.estimated_cost_usd,
                    "pricing_complete": usage_info.get("pricing_complete", False),
                }
            ]
        elif stage == "tts":
            record.tts_provider = provider
            record.tts_characters_count = characters_count
            record.tts_audio_duration = float(duration_seconds)
            record.model_usage = [
                {
                    "type": "tts_usage",
                    "provider": provider,
                    "model": model,
                    "characters_count": characters_count,
                    "audio_duration": float(duration_seconds),
                    "estimated_cost_usd": record.estimated_cost_usd,
                    "pricing_complete": usage_info.get("pricing_complete", False),
                }
            ]
        elif stage == "llm":
            record.llm_realtime_provider = provider
            record.llm_model = model
            record.llm_input_tokens = prompt_tokens
            record.llm_output_tokens = completion_tokens
            record.llm_total_tokens = total_tokens or (prompt_tokens + completion_tokens)
            record.model_usage = [
                {
                    "type": "llm_usage",
                    "provider": provider,
                    "model": model,
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "estimated_cost_usd": record.estimated_cost_usd,
                    "pricing_complete": usage_info.get("pricing_complete", False),
                }
            ]

        await record.insert()
    except Exception as exc:
        logger.warning(f"Failed to record standalone usage: {exc}")

    return usage_info
