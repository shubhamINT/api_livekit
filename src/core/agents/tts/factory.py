"""Factory for creating TTS provider instances based on assistant configuration."""

import asyncio

from livekit.agents.types import NOT_GIVEN
from livekit.plugins import cartesia, sarvam

from src.core.agents.stt.lang import validate_language, validate_sarvam_speaker
from src.core.config import settings
from src.core.logger import logger
from src.services.elevenlabs.v3_nonstream import (
    ElevenLabsNonStreamingTTS,
    VoiceSettings,
)
from src.services.mistral.tts import MistralTTS

# The Bulbul generation this platform speaks. Pinned rather than configurable: the speaker
# roster changes wholesale between generations (v2 and v3 share no speaker at all), so a
# model field would need a matching speaker field and a matrix between them.
SARVAM_TTS_MODEL = "bulbul:v3"

# ElevenLabs models with no speed control: the whole v3 family, which includes this
# platform's default, so a `speed` stored against one is the likely case, not the rare one.
# https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech ("Speed is not
# available for the Eleven v3 model"). Dropped rather than sent: v3 also reads stability as
# three discrete modes (creative/natural/robust) rather than a continuum, so its
# voice_settings surface is genuinely narrower, not just differently tuned.
_ELEVENLABS_NO_SPEED_MODELS = frozenset({"eleven_v3", "eleven_v3_conversational"})

# Per-provider system key, used when the assistant config carries no api_key of its own.
# One variable per vendor: ELEVENLABS_API_KEY and SARVAM_API_KEY each serve both the STT and the
# TTS stage (see src/core/agents/stt/factory.py for the STT side).
_TTS_ENV_KEYS = {
    "cartesia": "CARTESIA_API_KEY",
    "sarvam": "SARVAM_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}


def _resolve_api_key(model: str, tts_config: dict, assistant_id: str) -> str | None:
    """Config key, else the system key, else None with a log line.

    Checked up front so a missing key ends the job through the same `return None` path as
    every other config error. Without this the key reaches the plugin constructor, and at
    least one of them (ElevenLabs) raises out of create_tts and out of entrypoint().
    """
    api_key = tts_config.get("api_key") or getattr(settings, _TTS_ENV_KEYS[model], None)
    if not api_key:
        logger.error(
            f"Missing API key for {model} TTS on assistant {assistant_id} — set "
            f"assistant_tts_config.api_key or the {_TTS_ENV_KEYS[model]} environment variable"
        )
        return None
    return api_key


def create_tts(assistant):
    """Build a TTS instance from the assistant's model + config. Returns None on error."""
    tts_config = assistant.assistant_tts_config or {}
    model = assistant.assistant_tts_model
    assistant_id = assistant.assistant_id

    if model == "cartesia":
        voice_id = tts_config.get("voice_id")
        if not voice_id:
            logger.error(f"Missing voice_id for Cartesia assistant {assistant_id}")
            return None
        api_key = _resolve_api_key(model, tts_config, assistant_id)
        if not api_key:
            return None
        # ponytail: model pinned, no config field. sonic-3 is the newest ID the installed
        # plugin lists (livekit.plugins.cartesia.models.TTSModels) — sonic-3.5 exists only on
        # the LiveKit Inference gateway, which needs Cloud credentials this deployment does
        # not have. Adding the field later means adding the gating with it: speed must be a
        # float on sonic-3 (the plugin raises on the "slow"/"fast" presets), and emotion and
        # pronunciation_dict_id are sonic-3-only.
        return cartesia.TTS(
            model="sonic-3",
            voice=voice_id,
            api_key=api_key,
            language=tts_config.get("language", "en"),
            speed=tts_config.get("speed", 1.0),
            volume=tts_config.get("volume"),
            emotion=tts_config.get("emotion"),
            pronunciation_dict_id=tts_config.get("pronunciation_dict_id"),
        )

    if model == "sarvam":
        speaker = tts_config.get("speaker")
        if not speaker:
            logger.error(f"Missing speaker for Sarvam assistant {assistant_id}")
            return None
        # Checked before construction, not after: the plugin raises on a speaker its model
        # cannot use, and that exception escapes create_tts and entrypoint() — the job dies
        # with a traceback and the caller hears nothing. A speaker from the v2 roster is the
        # easy way in: none of the seven work on bulbul:v3.
        speaker = validate_sarvam_speaker(
            SARVAM_TTS_MODEL, speaker, assistant_id=assistant_id
        )
        if not speaker:
            return None
        api_key = _resolve_api_key(model, tts_config, assistant_id)
        if not api_key:
            return None
        return sarvam.TTS(
            model=SARVAM_TTS_MODEL,
            pace=tts_config.get("pace", 1.0),
            speech_sample_rate=tts_config.get("speech_sample_rate", 24000),
            # Bulbul speaks 11 Indic BCP-47 codes and nothing else — 'en-US' in particular
            # is not one of them, however reasonable it looks in a language picker. An
            # unusable code falls back to en-IN rather than failing every synthesis.
            # `or`, not a .get default: the schema always serializes the key, as None when
            # the caller omits it.
            target_language_code=validate_language(
                "sarvam_tts",
                tts_config.get("target_language_code"),
                assistant_id=assistant_id,
                field="assistant_tts_config.target_language_code",
            ) or "en-IN",
            speaker=speaker,
            api_key=api_key,
            min_buffer_size=30,
            max_chunk_length=50,
            temperature=tts_config.get("temperature", 0.3),
        )

    if model == "elevenlabs":
        voice_id = tts_config.get("voice_id")
        if not voice_id:
            logger.error(f"Missing voice_id for ElevenLabs assistant {assistant_id}")
            return None
        api_key = _resolve_api_key(model, tts_config, assistant_id)
        if not api_key:
            return None
        # eleven_v3 (latest, best quality) has no websocket API — HTTP /stream only.
        # Only when the caller provides a voice_settings block do we build a VoiceSettings
        # object. When it is absent we must pass NOT_GIVEN (not None): the client's
        # `is_given(voice_settings)` treats None as "set", so `dataclasses.asdict(None)`
        # would crash on the first synthesis. NOT_GIVEN reproduces the pre-existing
        # behaviour (serializes `"voice_settings": null`, which means "use API defaults").
        elevenlabs_model = tts_config.get("model", "eleven_v3")
        voice_settings = tts_config.get("voice_settings") or NOT_GIVEN
        speed = (
            voice_settings.get("speed") if voice_settings is not NOT_GIVEN else None
        )
        if speed is not None and elevenlabs_model in _ELEVENLABS_NO_SPEED_MODELS:
            logger.warning(
                f"Dropping voice_settings.speed={speed!r} for assistant {assistant_id}: "
                f"{elevenlabs_model} has no speed control. Use eleven_multilingual_v2, "
                "eleven_turbo_v2_5 or eleven_flash_v2_5 to change speaking rate, or pace "
                "the delivery through the prompt."
            )
            speed = None
        settings_obj = (
            VoiceSettings(
                stability=voice_settings.get("stability", 0.5),
                similarity_boost=voice_settings.get("similarity_boost", 0.5),
                style=voice_settings.get("style"),
                speed=speed,
                use_speaker_boost=voice_settings.get("use_speaker_boost"),
            )
            if voice_settings is not NOT_GIVEN
            else NOT_GIVEN
        )
        return ElevenLabsNonStreamingTTS(
            model=elevenlabs_model,
            voice_id=voice_id,
            api_key=api_key,
            voice_settings=settings_obj,
        )

    if model == "mistral":
        voice_id = tts_config.get("voice_id")
        if not voice_id:
            logger.error(f"Missing voice_id for Mistral assistant {assistant_id}")
            return None
        api_key = _resolve_api_key(model, tts_config, assistant_id)
        if not api_key:
            return None
        return MistralTTS(
            model="voxtral-mini-tts-2603",
            voice_id=voice_id,
            api_key=api_key,
        )

    logger.error(f"Unsupported TTS model for assistant {assistant_id}")
    return None


async def maintain_sarvam_connection(tts, stop_event: asyncio.Event) -> None:
    """Keep Sarvam WS alive for the entire call duration.

    Connects once at call start, pings every 3s while the WS is idle in the pool.
    Skips ping when TTS has taken the WS for synthesis. Reconnects if server closes it.
    Stops when stop_event is set (call end). No-op for non-Sarvam TTS providers.
    """
    if not isinstance(tts, sarvam.TTS):
        return

    # Force fresh connection at call start.
    try:
        tts._pool.invalidate()
        current_ws = await tts._pool.get(timeout=10.0)
        tts._pool.put(current_ws)
        logger.debug("Sarvam WS connected for call")
    except Exception as e:
        logger.debug(f"Sarvam WS initial connect failed: {e}")
        return

    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=3.0)
            break
        except asyncio.TimeoutError:
            pass

        if current_ws not in tts._pool._available:
            # TTS is actively using the connection — skip ping, don't interfere.
            continue

        if current_ws.closed:
            try:
                tts._pool.invalidate()
                current_ws = await tts._pool.get(timeout=5.0)
                tts._pool.put(current_ws)
                logger.debug("Sarvam WS reconnected")
            except Exception:
                pass
            continue

        try:
            await current_ws.ping()
            logger.debug("Sarvam WS keepalive ping sent")
        except Exception:
            try:
                tts._pool.invalidate()
                current_ws = await tts._pool.get(timeout=5.0)
                tts._pool.put(current_ws)
                logger.debug("Sarvam WS reconnected after ping failure")
            except Exception:
                pass
