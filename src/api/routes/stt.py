from typing import Optional
import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Header

from src.api.dependencies import get_current_user
from src.api.models.response_models import apiResponse
from src.api.routes.standalone_helper import (
    log_standalone_usage,
    probe_audio_duration,
    resolve_stage_config,
)
from src.core.db.db_schemas import APIKey
from src.core.logger import logger
from src.services.storage.audio_transcode import MAX_UPLOAD_BYTES
from src.services.stt.client import transcribe_audio

router = APIRouter()


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(..., description="Audio file to transcribe (max 25 MB)"),
    assistant_id: Optional[str] = Form(None, description="Optional assistant ID to inherit STT configuration"),
    provider: Optional[str] = Form(None, description="STT provider (sarvam, cartesia, deepgram, openai, elevenlabs)"),
    model: Optional[str] = Form(None, description="STT model identifier"),
    language: Optional[str] = Form(None, description="Language code (e.g. en-US, hi-IN, or auto)"),
    current_user: APIKey = Depends(get_current_user),
    x_provider_api_key: Optional[str] = Header(None, alias="X-Provider-API-Key"),
):
    """Transcribe an audio file into text using the specified or assistant-configured STT model."""
    # Bounded read to avoid memory exhaustion
    raw_audio = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw_audio) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Audio file exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
        )
    if not raw_audio:
        raise HTTPException(status_code=422, detail="Uploaded audio file is empty")

    stage_config = await resolve_stage_config(
        stage="stt",
        user=current_user,
        assistant_id=assistant_id,
        explicit_provider=provider,
        explicit_model=model,
        explicit_language=language,
        explicit_api_key=x_provider_api_key,
    )

    try:
        result = await transcribe_audio(
            audio_bytes=raw_audio,
            filename=file.filename or "audio.wav",
            provider=stage_config["provider"],
            model=stage_config["model"],
            language=stage_config["language"],
            api_key=stage_config["api_key"],
        )
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except httpx.HTTPStatusError as hse:
        logger.error(f"STT provider HTTP error: {hse}")
        raise HTTPException(status_code=502, detail=f"Upstream STT provider error: {hse.response.text}")
    except Exception as exc:
        logger.error(f"STT unexpected error: {exc}")
        raise HTTPException(status_code=502, detail="Failed to transcribe audio from upstream provider")

    # Ensure duration is populated
    audio_duration = result.get("duration_seconds")
    if not audio_duration or audio_duration <= 0:
        audio_duration = probe_audio_duration(raw_audio)
    result["duration_seconds"] = audio_duration

    # Record metrics & compute cost
    usage_info = await log_standalone_usage(
        stage="stt",
        user_email=current_user.user_email,
        provider=stage_config["provider"],
        model=stage_config["model"],
        assistant_id=stage_config["assistant_id"],
        duration_seconds=audio_duration,
    )
    result["usage"] = usage_info

    return apiResponse(success=True, message="Audio transcribed successfully", data=result)

