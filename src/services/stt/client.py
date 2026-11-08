import io
from typing import Any, Optional
import httpx

from src.core.config import settings
from src.core.logger import logger
from src.core.model_support.speech import STT_ENV_KEYS


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str,
    provider: str,
    model: str,
    language: Optional[str] = None,
    api_key: Optional[str] = None,
) -> dict[str, Any]:
    """Direct HTTP transcription client across supported STT providers."""
    resolved_key = api_key or getattr(settings, STT_ENV_KEYS.get(provider, ""), None)
    if not resolved_key:
        raise ValueError(f"No API key configured for STT provider '{provider}'")

    timeout = httpx.Timeout(60.0, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        if provider == "sarvam":
            url = "https://api.sarvam.ai/speech-to-text"
            headers = {"api-subscription-key": resolved_key}
            files = {"file": (filename or "audio.wav", audio_bytes, "audio/wav")}
            data = {"model": model or "saaras:v3"}
            if language and language != "auto":
                data["language_code"] = language
            resp = await client.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            res = resp.json()
            return {
                "text": res.get("transcript", ""),
                "language": res.get("language_code", language or "unknown"),
                "duration_seconds": None,
                "provider": provider,
                "model": model,
            }

        elif provider == "openai":
            url = "https://api.openai.com/v1/audio/transcriptions"
            headers = {"Authorization": f"Bearer {resolved_key}"}
            files = {"file": (filename or "audio.wav", audio_bytes, "audio/wav")}
            data = {"model": model or "whisper-1"}
            if language and language != "auto":
                data["language"] = language
            resp = await client.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            res = resp.json()
            return {
                "text": res.get("text", ""),
                "language": language or "en",
                "duration_seconds": res.get("duration"),
                "provider": provider,
                "model": model,
            }

        elif provider == "deepgram":
            url = f"https://api.deepgram.com/v1/listen?model={model or 'nova-3'}"
            if language and language != "auto":
                url += f"&language={language}"
            headers = {
                "Authorization": f"Token {resolved_key}",
                "Content-Type": "audio/wav",
            }
            resp = await client.post(url, headers=headers, content=audio_bytes)
            resp.raise_for_status()
            res = resp.json()
            transcript = ""
            try:
                transcript = res["results"]["channels"][0]["alternatives"][0]["transcript"]
            except (KeyError, IndexError):
                pass
            return {
                "text": transcript,
                "language": language,
                "duration_seconds": res.get("metadata", {}).get("duration"),
                "provider": provider,
                "model": model,
            }

        elif provider == "cartesia":
            url = "https://api.cartesia.ai/stt/transcribe"
            headers = {
                "X-API-Key": resolved_key,
                "Cartesia-Version": "2024-06-10",
            }
            files = {"file": (filename or "audio.wav", audio_bytes, "audio/wav")}
            data = {"model_id": model or "ink-whisper"}
            if language and language != "auto":
                data["language"] = language
            resp = await client.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            res = resp.json()
            return {
                "text": res.get("text", ""),
                "language": res.get("language", language),
                "duration_seconds": res.get("duration"),
                "provider": provider,
                "model": model,
            }

        elif provider == "elevenlabs":
            url = "https://api.elevenlabs.io/v1/speech-to-text"
            headers = {"xi-api-key": resolved_key}
            files = {"file": (filename or "audio.wav", audio_bytes, "audio/wav")}
            data = {"model_id": model or "scribe_v1"}
            if language and language != "auto":
                data["language_code"] = language
            resp = await client.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            res = resp.json()
            return {
                "text": res.get("text", ""),
                "language": res.get("language_code", language),
                "duration_seconds": None,
                "provider": provider,
                "model": model,
            }

        else:
            raise ValueError(f"Unsupported STT provider: {provider}")

