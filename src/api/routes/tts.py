from typing import Optional
import base64
import io
import uuid
import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Response

from src.api.dependencies import get_current_user
from src.api.models.api_schemas.standalone import SynthesizeRequest
from src.api.models.response_models import apiResponse
from src.api.routes.standalone_helper import (
    log_standalone_usage,
    probe_audio_duration,
    resolve_stage_config,
)
from src.core.db.db_schemas import APIKey, AudioAsset
from src.core.logger import logger
from src.services.storage import s3_audio
from src.services.storage.audio_transcode import transcode_to_wav
from src.services.tts.client import synthesize_speech

router = APIRouter()


@router.post("/synthesize")
async def synthesize(
    request: SynthesizeRequest,
    current_user: APIKey = Depends(get_current_user),
    x_provider_api_key: Optional[str] = Header(None, alias="X-Provider-API-Key"),
):
    """Synthesize text into speech audio using direct provider REST clients or assistant defaults."""
    stage_config = await resolve_stage_config(
        stage="tts",
        user=current_user,
        assistant_id=request.assistant_id,
        explicit_provider=request.provider,
        explicit_model=request.model,
        explicit_voice=request.voice,
        explicit_language=request.language,
        explicit_api_key=x_provider_api_key,
    )

    try:
        audio_bytes, media_type = await synthesize_speech(
            text=request.text,
            provider=stage_config["provider"],
            model=stage_config["model"],
            voice=stage_config["voice"],
            language=stage_config["language"],
            api_key=stage_config["api_key"],
        )
    except ValueError as ve:
        raise HTTPException(status_code=422, detail=str(ve))
    except httpx.HTTPStatusError as hse:
        logger.error(f"TTS provider HTTP error: {hse}")
        raise HTTPException(status_code=502, detail=f"Upstream TTS provider error: {hse.response.text}")
    except Exception as exc:
        logger.error(f"TTS unexpected error: {exc}")
        raise HTTPException(status_code=502, detail="Failed to synthesize speech from upstream provider")

    # Probe synthesized audio duration
    audio_duration = probe_audio_duration(audio_bytes)

    # If requested, persist to user's audio asset library
    if request.save_to_library:
        try:
            wav_bytes, duration = transcode_to_wav(audio_bytes)
            audio_duration = duration
            audio_id = str(uuid.uuid4())
            s3_url = await s3_audio.upload_audio(audio_id, wav_bytes)
            asset = AudioAsset(
                audio_id=audio_id,
                audio_name=f"TTS_{audio_id[:8]}",
                s3_key=s3_audio.build_key(audio_id),
                s3_url=s3_url,
                duration_seconds=duration,
                created_by_email=current_user.user_email,
                is_active=True,
            )
            await asset.insert()
        except Exception as exc:
            logger.warning(f"Failed to save synthesized speech to library: {exc}")

    # Record usage & compute cost
    usage_info = await log_standalone_usage(
        stage="tts",
        user_email=current_user.user_email,
        provider=stage_config["provider"],
        model=stage_config["model"],
        assistant_id=stage_config["assistant_id"],
        characters_count=len(request.text),
        duration_seconds=audio_duration,
    )

    if request.response_format == "json":
        return apiResponse(
            success=True,
            message="Speech synthesized successfully",
            data={
                "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
                "media_type": media_type,
                "provider": stage_config["provider"],
                "model": stage_config["model"],
                "usage": usage_info,
            },
        )

    ext = "wav" if "wav" in media_type else "mp3"
    headers = {
        "Content-Disposition": f'inline; filename="speech.{ext}"',
        "Content-Length": str(len(audio_bytes)),
        "X-TTS-Characters": str(len(request.text)),
        "X-Audio-Duration": f"{audio_duration:.3f}",
        "X-Estimated-Cost-USD": f"{usage_info.get('estimated_cost_usd', 0.0):.6f}",
        "X-Pricing-Complete": str(usage_info.get("pricing_complete", False)).lower(),
        "X-Provider": stage_config["provider"],
        "X-Model": stage_config["model"],
    }
    return Response(content=audio_bytes, media_type=media_type, headers=headers)

