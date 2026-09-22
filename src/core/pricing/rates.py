"""Public PAYG rates used for estimated AI-provider cost.

Rates are intentionally static. They are estimates of public list pricing, not provider
invoice truth. Keep the source URL and effective date beside each provider's table when
changing a rate.
"""

from dataclasses import dataclass
from decimal import Decimal

PRICING_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ModelRate:
    input_text: Decimal = Decimal(0)
    input_audio: Decimal = Decimal(0)
    input_image: Decimal = Decimal(0)
    cached_input_text: Decimal = Decimal(0)
    cached_input_audio: Decimal = Decimal(0)
    cached_input_image: Decimal = Decimal(0)
    cache_creation: Decimal = Decimal(0)
    output_text: Decimal = Decimal(0)
    output_audio: Decimal = Decimal(0)
    audio_second: Decimal = Decimal(0)
    character: Decimal = Decimal(0)


def _tokens(input_text, cached_input_text, output_text, **kwargs):
    return ModelRate(
        input_text=Decimal(input_text) / 1_000_000,
        cached_input_text=Decimal(cached_input_text) / 1_000_000,
        output_text=Decimal(output_text) / 1_000_000,
        **{key: Decimal(value) / 1_000_000 for key, value in kwargs.items()},
    )


def _realtime(
    audio_in, text_in, cached_audio, cached_text, output_audio, output_text, image_in
):
    return ModelRate(
        input_audio=Decimal(audio_in) / 1_000_000,
        input_text=Decimal(text_in) / 1_000_000,
        cached_input_audio=Decimal(cached_audio) / 1_000_000,
        cached_input_text=Decimal(cached_text) / 1_000_000,
        input_image=Decimal(image_in) / 1_000_000,
        output_audio=Decimal(output_audio) / 1_000_000,
        output_text=Decimal(output_text) / 1_000_000,
    )


# Sources checked 2026-09-06:
# https://developers.openai.com/api/docs/pricing
OPENAI_RATES = {
    "gpt-4.1": _tokens("2.00", ".50", "8.00"),
    "gpt-4.1-mini": _tokens(".40", ".10", "1.60"),
    "gpt-4.1-nano": _tokens(".10", ".025", ".40"),
    "gpt-4o": _tokens("2.50", "1.25", "10.00"),
    "gpt-4o-mini": _tokens(".15", ".075", ".60"),
    "gpt-5": _tokens("1.25", ".125", "10.00"),
    "gpt-5-mini": _tokens(".25", ".025", "2.00"),
    "gpt-5-nano": _tokens(".05", ".005", ".40"),
    "gpt-5.1": _tokens("1.25", ".125", "10.00"),
    "gpt-5.2": _tokens("1.75", ".175", "14.00"),
    "gpt-5.4": _tokens("2.50", ".25", "15.00"),
    "gpt-5.4-mini": _tokens(".75", ".075", "4.50"),
    "gpt-5.4-nano": _tokens(".20", ".02", "1.25"),
    "gpt-5.5": _tokens("5.00", ".50", "30.00"),
    "gpt-5.6-sol": _tokens("4.00", ".40", "20.00"),
    "gpt-5.6-terra": _tokens("2.00", ".20", "12.00"),
    "gpt-5.6-luna": _tokens(".20", ".02", "1.20"),
}

OPENAI_REALTIME_RATES = {
    "gpt-realtime": _realtime("32", "4", ".40", ".40", "64", "16", "5"),
    "gpt-realtime-1.5": _realtime("32", "4", ".40", ".40", "64", "16", "5"),
    "gpt-realtime-2": _realtime("32", "4", ".40", ".40", "64", "24", "5"),
    "gpt-realtime-2025-08-28": _realtime("32", "4", ".40", ".40", "64", "16", "5"),
    "gpt-realtime-mini": _realtime("10", ".60", ".30", ".06", "20", "2.40", ".80"),
}

OPENAI_STT_RATES = {
    "gpt-transcribe": ModelRate(audio_second=Decimal("0.0045") / 60),
    "gpt-4o-transcribe": ModelRate(
        input_audio=Decimal("2.50") / 1_000_000,
        output_text=Decimal(10) / 1_000_000,
    ),
    "gpt-4o-mini-transcribe": ModelRate(
        input_audio=Decimal("1.25") / 1_000_000,
        output_text=Decimal(5) / 1_000_000,
    ),
    "gpt-4o-mini-transcribe-2025-12-15": ModelRate(
        input_audio=Decimal("1.25") / 1_000_000,
        output_text=Decimal(5) / 1_000_000,
    ),
    "gpt-4o-transcribe-diarize": ModelRate(
        input_audio=Decimal("2.50") / 1_000_000,
        output_text=Decimal(10) / 1_000_000,
    ),
    "whisper-1": ModelRate(audio_second=Decimal("0.006") / 60),
}

# https://elevenlabs.io/pricing/api, checked 2026-09-06.
ELEVENLABS_TTS_RATES = {
    "eleven_v3": ModelRate(character=Decimal("0.10") / 1000),
    "eleven_v3_conversational": ModelRate(character=Decimal("0.05") / 1000),
    "eleven_multilingual_v1": ModelRate(character=Decimal("0.10") / 1000),
    "eleven_multilingual_v2": ModelRate(character=Decimal("0.10") / 1000),
    "eleven_turbo_v2": ModelRate(character=Decimal("0.05") / 1000),
    "eleven_turbo_v2_5": ModelRate(character=Decimal("0.05") / 1000),
    "eleven_flash_v2": ModelRate(character=Decimal("0.05") / 1000),
    "eleven_flash_v2_5": ModelRate(character=Decimal("0.05") / 1000),
    "eleven_monolingual_v1": ModelRate(character=Decimal("0.10") / 1000),
}

ELEVENLABS_STT_RATES = {
    "scribe_v1": ModelRate(audio_second=Decimal("0.22") / 3600),
    "scribe_v2": ModelRate(audio_second=Decimal("0.22") / 3600),
    "scribe_v2_realtime": ModelRate(audio_second=Decimal("0.39") / 3600),
}

# https://docs.sarvam.ai/api-reference-docs/pricing, checked 2026-09-06.
# Fixed conversion snapshot: 1 USD = INR 83.75. USD is the only public output currency.
SARVAM_INR_TO_USD = Decimal(1) / Decimal("83.75")
SARVAM_RATES = {
    "saaras:v3": ModelRate(audio_second=Decimal(30) / 3600 * SARVAM_INR_TO_USD),
    "saaras:v4": ModelRate(audio_second=Decimal(30) / 3600 * SARVAM_INR_TO_USD),
    "bulbul:v3": ModelRate(character=Decimal(30) / 10000 * SARVAM_INR_TO_USD),
}

# https://cartesia.ai/pricing, checked 2026-09-22. **Derived, not quoted.** Cartesia
# publishes plan tiers, not a per-unit price, so these come from the Startup tier: $49/month
# buys 1.25M credits, which that page equates to about 1,667 minutes of sonic-3 speech and
# about 115h44m of ink-2 transcription. A TTS credit is one character, so the character rate
# is the tier price over the credits; STT is the tier price over the hours. Replace both with
# the contract rate if this deployment has one.
CARTESIA_TTS_RATES = {
    "sonic-3": ModelRate(character=Decimal(49) / 1_250_000),
}
_CARTESIA_STT_SECOND = ModelRate(audio_second=Decimal(49) / (Decimal("115.7333") * 3600))
CARTESIA_STT_RATES = {
    "ink-2": _CARTESIA_STT_SECOND,
    "ink-whisper": _CARTESIA_STT_SECOND,
}

# https://mistral.ai/pricing/api, checked 2026-09-22. The page names the model "Voxtral TTS"
# at $0.016 per 1K characters; the ids below are what `GET /v1/models` actually serves and
# what `tts/factory.py` sends.
MISTRAL_TTS_RATES = {
    "voxtral-mini-tts-2603": ModelRate(character=Decimal("0.016") / 1000),
}

# https://ai.google.dev/gemini-api/docs/pricing, checked 2026-09-22. Paid tier.
# The three 3.x Live models share one price block; 2.5 native audio is its own, cheaper on
# text and the same on audio. Thinking tokens bill as output text, so no separate rate.
# Cached input carries the uncached rate: Google publishes no Live API cache discount,
# so the estimate is high rather than free.
_GEMINI_3X_LIVE = _realtime("3.00", ".75", "3.00", ".75", "12.00", "4.50", "1.00")
GEMINI_LIVE_RATES = {
    "gemini-3.8-live": _GEMINI_3X_LIVE,
    "gemini-3.8-live-extended-thinking": _GEMINI_3X_LIVE,
    "gemini-3.1-flash-live-preview": _GEMINI_3X_LIVE,
    "gemini-2.5-flash-native-audio-preview-12-2025": _realtime(
        "3.00", ".50", "3.00", ".50", "12.00", "2.00", "3.00"
    ),
}

# https://deepgram.com/pricing, checked 2026-09-22. Streaming, pay-as-you-go, **regular**
# price — the page currently quotes a lower promotional rate on three of these (nova-3
# $0.0048, nova-3-multilingual $0.0058, flux-general-en $0.0065). The regular price is used
# on purpose: a promotion ends without warning, and an estimate that is a little high is
# recoverable where one that is 40% low is not.
DEEPGRAM_RATES = {
    "nova-3": ModelRate(audio_second=Decimal("0.0077") / 60),
    "nova-3-general": ModelRate(audio_second=Decimal("0.0077") / 60),
    "nova-3-multilingual": ModelRate(audio_second=Decimal("0.0092") / 60),
    "flux-general-en": ModelRate(audio_second=Decimal("0.0077") / 60),
    "flux-general-multi": ModelRate(audio_second=Decimal("0.0078") / 60),
}


def get_rate(component: str, provider: str, model: str) -> ModelRate | None:
    tables = {
        ("llm_usage", "openai"): {**OPENAI_RATES, **OPENAI_REALTIME_RATES},
        # "Gemini" is what the plugin reports for an API-key session, lowercased by
        # `normalize_provider`. A Vertex session would say "Vertex AI", which this deployment
        # cannot open — it never passes `vertexai=True`.
        ("llm_usage", "gemini"): GEMINI_LIVE_RATES,
        ("stt_usage", "openai"): OPENAI_STT_RATES,
        ("tts_usage", "elevenlabs"): ELEVENLABS_TTS_RATES,
        ("stt_usage", "elevenlabs"): ELEVENLABS_STT_RATES,
        ("stt_usage", "sarvam"): SARVAM_RATES,
        ("tts_usage", "sarvam"): SARVAM_RATES,
        ("stt_usage", "deepgram"): DEEPGRAM_RATES,
        ("tts_usage", "cartesia"): CARTESIA_TTS_RATES,
        ("stt_usage", "cartesia"): CARTESIA_STT_RATES,
        ("tts_usage", "mistral"): MISTRAL_TTS_RATES,
    }
    return tables.get((component, provider), {}).get(model)
