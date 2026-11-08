import base64
from typing import AsyncIterator, Optional, Tuple
import httpx

from src.core.config import settings
from src.core.model_support.speech import DEFAULT_SARVAM_TTS_MODEL, TTS_ENV_KEYS


async def synthesize_speech(
    text: str,
    provider: str,
    model: Optional[str] = None,
    voice: Optional[str] = None,
    language: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Tuple[bytes, str]:
    """Synthesize speech returning (audio_bytes, media_type)."""
    resolved_key = api_key or getattr(settings, TTS_ENV_KEYS.get(provider, ""), None)
    if not resolved_key:
        raise ValueError(f"No API key configured for TTS provider '{provider}'")

    timeout = httpx.Timeout(60.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if provider == "cartesia":
            url = "https://api.cartesia.ai/tts/bytes"
            headers = {
                "X-API-Key": resolved_key,
                "Cartesia-Version": "2024-06-10",
                "Content-Type": "application/json",
            }
            # Default cartesia voice if none provided
            voice_id = voice or "a0e99841-438c-4a64-b679-ae501e7d6091"
            payload = {
                "model_id": model or "sonic-3",
                "transcript": text,
                "voice": {"mode": "id", "id": voice_id},
                "output_format": {
                    "container": "wav",
                    "encoding": "pcm_s16le",
                    "sample_rate": 24000,
                },
            }
            if language:
                payload["language"] = language
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.content, "audio/wav"

        elif provider == "sarvam":
            url = "https://api.sarvam.ai/text-to-speech"
            headers = {
                "api-subscription-key": resolved_key,
                "Content-Type": "application/json",
            }
            payload = {
                "inputs": [text],
                "target_language_code": language or "hi-IN",
                "speaker": voice or "meera",
                "model": model or DEFAULT_SARVAM_TTS_MODEL,
            }
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            res = resp.json()
            audios = res.get("audios", [])
            if not audios:
                raise ValueError("Sarvam TTS returned no audio")
            audio_bytes = base64.b64decode(audios[0])
            return audio_bytes, "audio/wav"

        elif provider == "elevenlabs":
            voice_id = voice or "21m00Tcm4TlvDq8ikWAM"
            url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
            headers = {
                "xi-api-key": resolved_key,
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "model_id": model or "eleven_multilingual_v2",
            }
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.content, "audio/mpeg"

        elif provider == "mistral":
            url = "https://api.mistral.ai/v1/tts"
            headers = {
                "Authorization": f"Bearer {resolved_key}",
                "Content-Type": "application/json",
            }
            payload = {
                "text": text,
                "model": model or "mistral-tts-1",
            }
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            return resp.content, "audio/wav"

        else:
            raise ValueError(f"Unsupported TTS provider: {provider}")

