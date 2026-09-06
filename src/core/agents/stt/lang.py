"""Per-provider language-code validation.

Five speech surfaces, four incompatible code standards. `en-US` is valid on Deepgram,
meaningless to Cartesia and OpenAI, and a hard connection error on ElevenLabs
(`1008 invalid_request: Invalid language code received: 'en-US'`). Nothing upstream
normalizes between them, so a code that came from the wrong picker used to reach the
provider unchanged and break the call.

The rule here: a code that the selected provider cannot accept is dropped, not sent. The
caller then falls back to that provider's auto-detect (or its documented default when the
provider has no auto-detect), and the reason is logged once at call start.

`assistant_interaction_config.preferred_languages` is deliberately NOT a source for any of
these values. It is a BCP-47 hint list for the transcription *prompt*
(see native_prompt.py); feeding it into a provider parameter both pins a language the user
never asked to pin and injects the wrong code standard on three providers out of four.
"""

from __future__ import annotations

import re
from typing import get_args

from livekit.plugins.cartesia.models import STTLanguages as _CartesiaSTTLanguages
from livekit.plugins.sarvam.stt import MODEL_CONFIGS as _SARVAM_STT_MODELS
from livekit.plugins.sarvam.tts import (
    MODEL_SPEAKER_COMPATIBILITY as _SARVAM_TTS_SPEAKERS,
)
from livekit.plugins.sarvam.tts import SarvamTTSLanguages as _SarvamTTSLanguages

from src.core.logger import logger

# Sarvam auto-detect. Unlike every other provider here, "no language" is a real code.
SARVAM_AUTO = "unknown"

# Cartesia ink-whisper (ISO 639-1) and Sarvam bulbul (BCP-47 Indic) both ship an exact
# Literal in the plugin. Read it rather than restating it — a plugin bump then updates
# the accepted set for free.
CARTESIA_STT_LANGUAGES: frozenset[str] = frozenset(get_args(_CartesiaSTTLanguages))
SARVAM_TTS_LANGUAGES: frozenset[str] = frozenset(get_args(_SarvamTTSLanguages))

# ElevenLabs Scribe speaks ISO 639-3, and the plugin forwards the string untouched, so this
# is the only place the set exists. Copied verbatim from the API's own rejection message.
_ELEVENLABS_CODES = """
afr amh ara asm ast aze bak bas bel ben bhr bod bos bre bul cat ceb ces chv ckb cnh cre cym
dan dav deu div dyu ell eng epo est eus fao fas fil fin fra fry ful gla gle glg guj hat hau
heb hin hrv hsb hun hye ibo ina ind isl ita jav jpn kab kan kas kat kaz kea khm kin kir kln
kmr kor kur lao lat lav lij lin lit ltg ltz lug luo mal mar mdf mhr mkd mlg mlt mon mri mrj
msa mya myv nan nep nhi nld nor nso nya oci ori orm oss pan pol por pus quy roh ron rus sah
san sat sin skr slk slv smo sna snd som sot spa sqi srd srp sun swa swe tam tat tel tgk tha
tig tir tok ton tsn tuk tur twi uig ukr umb urd uzb vie vot vro wol xho yid yor yue zgh zho
zul zza
"""
ELEVENLABS_STT_LANGUAGES: frozenset[str] = frozenset(_ELEVENLABS_CODES.split())

# OpenAI transcription takes ISO 639-1 and Deepgram takes BCP-47; neither publishes a set
# small enough to pin without going stale, so these are shape checks. They exist to catch
# the cross-provider mix-up (a `-IN` suffix on OpenAI, a bare 3-letter code on Deepgram),
# not to second-guess the vendor's language list.
_ISO_639_1 = re.compile(r"^[a-z]{2}$")
# Two letters in the primary subtag, not two-or-three: every language Deepgram lists has an
# ISO 639-1 code, so a 3-letter primary subtag is an ElevenLabs code in the wrong slot.
_BCP_47 = re.compile(r"^[a-z]{2}(-[A-Za-z0-9]{2,8})*$")

# Deepgram's own auto-detect value — a language code slot, not a language.
DEEPGRAM_MULTI = "multi"


# One row per surface: what it accepts, and how to say so in the log line when it doesn't.
# Kept as a single table so the check and the error message cannot drift apart.
_RULES: dict[str, tuple] = {
    "elevenlabs": (ELEVENLABS_STT_LANGUAGES.__contains__, "ISO 639-3, e.g. 'eng', 'hin'"),
    "cartesia": (CARTESIA_STT_LANGUAGES.__contains__, "ISO 639-1, e.g. 'en', 'hi'"),
    "sarvam_tts": (SARVAM_TTS_LANGUAGES.__contains__, "BCP-47 Indic, e.g. 'en-IN', 'hi-IN'"),
    "openai": (_ISO_639_1.match, "ISO 639-1, e.g. 'en', 'hi'"),
    "deepgram": (
        lambda c: c == DEEPGRAM_MULTI or _BCP_47.match(c),
        "BCP-47, e.g. 'en-US', 'hi-IN', or 'multi'",
    ),
}


def validate_language(
    provider: str, code: str | None, *, assistant_id: str, field: str
) -> str | None:
    """Return `code` when the provider accepts it, else None with one error logged.

    None means "no language pinned" — every caller turns that into the provider's
    auto-detect or its documented default, so a bad code degrades the call instead of
    killing it.
    """
    accepts, expected = _RULES.get(provider, (lambda _c: True, "a supported code"))
    if not code or accepts(code):
        return code or None
    logger.error(
        f"Invalid {provider} language code {code!r} in {field} for assistant "
        f"{assistant_id} — expected {expected}. "
        "Ignoring it and falling back to the provider default."
    )
    return None


def validate_sarvam_language(model: str | None, code: str | None, *, assistant_id: str) -> str:
    """Return a Sarvam STT language code that is safe to construct with.

    Sarvam gets its own function for two reasons the generic table cannot express. Its
    accepted set is **per model** — the sunset saarika:v2.5 spoke a subset of what saaras:v3
    does, and the current roster can diverge again the same way — and the plugin *raises*
    `ValueError` on a code outside that set rather than warning.
    Unguarded, one stale code in a stored config takes the whole job down at start, which
    is a harder failure than any of the wrong-standard bugs this module was written for.

    Always returns a code: `unknown` is Sarvam's auto-detect, so there is nothing to
    express with None. An empty string is reachable from the API (the schema sets no
    min_length) and the plugin turns it into en-IN rather than auto-detect, so it is
    normalized here too.
    """
    code = (code or "").strip() or SARVAM_AUTO
    if code == SARVAM_AUTO:
        return code
    allowed = getattr(_SARVAM_STT_MODELS.get(model or ""), "allowed_languages", None)
    if allowed is None or code in allowed:
        # Unknown model: leave it to the plugin, which knows its own roster better.
        return code
    logger.error(
        f"Invalid sarvam language code {code!r} for model {model!r} on assistant "
        f"{assistant_id} — expected one of {sorted(allowed)}. Auto-detecting instead."
    )
    return SARVAM_AUTO


def sarvam_speakers(model: str) -> list[str] | None:
    """The speakers this Bulbul model can use, or None when the plugin has no list for it."""
    speakers = _SARVAM_TTS_SPEAKERS.get(model)
    return sorted(speakers["all"]) if speakers else None


def validate_sarvam_speaker(model: str, speaker: str | None, *, assistant_id: str) -> str | None:
    """Return the speaker when this Bulbul model can speak it, else None with one error.

    Third variant of the same trap, and the worst of them. The speaker roster is **per
    model version** and the two generations share nobody: all seven bulbul:v2 speakers
    (anushka, manisha, vidya, arya, abhilash, karun, hitesh) are rejected by the v3 model
    this platform pins. The plugin then *raises* `ValueError` in its constructor, which —
    unlike a language code — escapes create_tts and entrypoint() entirely, so the job dies
    with a traceback instead of the one-line log every other config error produces.

    None means "cannot build this TTS": there is no sane fallback. Falling back to some
    other voice would answer the call in a voice nobody chose, which is worse than a clear
    failure for the one field whose entire purpose is picking the voice.
    """
    allowed = sarvam_speakers(model)
    if allowed is None or (speaker and speaker.lower() in allowed):
        # Unknown model: leave it to the plugin, which knows its own roster better.
        return speaker
    logger.error(
        f"Sarvam speaker {speaker!r} is not available on {model} for assistant "
        f"{assistant_id} — {model} speakers are: {', '.join(allowed)}. "
        "Update assistant_tts_config.speaker."
    )
    return None


def validate_sarvam_mode(model: str | None, mode: str | None, *, assistant_id: str) -> str | None:
    """Return a Sarvam transcription mode safe to construct with, or None to leave it unset.

    Same trap as the language: `mode` is model-gated and the plugin raises rather than
    warning. Every model on the current roster (saaras:v3, saaras:v4) takes it, but the
    sunset v2.5 pair rejected anything but its own default, which made the repo-wide
    "codemix" default fatal on them. The gate stays because the roster gained a model once
    and can gain a mode-less one again. None makes the plugin pick that model's default,
    which is the only correct value there anyway.
    """
    config = _SARVAM_STT_MODELS.get(model or "")
    if config is None or config.supports_mode:
        # Unknown model: leave it to the plugin, which knows its own roster better.
        return mode
    if mode and mode != config.default_mode:
        logger.warning(
            f"Sarvam model {model!r} does not support transcription mode {mode!r} "
            f"on assistant {assistant_id} — using the model's default."
        )
    return None


if __name__ == "__main__":
    # The mix-up this module exists to catch: one code, five providers, four verdicts.
    assert validate_language("elevenlabs", "en-US", assistant_id="t", field="f") is None
    assert validate_language("elevenlabs", "eng", assistant_id="t", field="f") == "eng"
    assert validate_language("cartesia", "en-US", assistant_id="t", field="f") is None
    assert validate_language("cartesia", "en", assistant_id="t", field="f") == "en"
    assert validate_language("openai", "hi-IN", assistant_id="t", field="f") is None
    assert validate_language("openai", "hi", assistant_id="t", field="f") == "hi"
    assert validate_language("deepgram", "en-US", assistant_id="t", field="f") == "en-US"
    assert validate_language("deepgram", "multi", assistant_id="t", field="f") == "multi"
    assert validate_language("deepgram", "eng", assistant_id="t", field="f") is None
    assert validate_language("sarvam_tts", "en-US", assistant_id="t", field="f") is None
    assert validate_language("sarvam_tts", "en-IN", assistant_id="t", field="f") == "en-IN"
    # Unset stays unset — the caller, not this function, decides what unset means.
    assert validate_language("elevenlabs", None, assistant_id="t", field="f") is None
    assert validate_language("elevenlabs", "", assistant_id="t", field="f") is None
    # The plugin Literals must actually have loaded; an empty set would accept nothing.
    assert "en" in CARTESIA_STT_LANGUAGES and "hi" in CARTESIA_STT_LANGUAGES
    assert "en-IN" in SARVAM_TTS_LANGUAGES and len(SARVAM_TTS_LANGUAGES) == 11
    assert len(ELEVENLABS_STT_LANGUAGES) == 163  # as listed by the API's rejection message
    # Sarvam: per-model sets, and the plugin RAISES on a bad code rather than warning.
    assert validate_sarvam_language("saaras:v3", "hi-IN", assistant_id="t") == "hi-IN"
    assert validate_sarvam_language("saaras:v3", "en-US", assistant_id="t") == SARVAM_AUTO
    assert validate_sarvam_language("saaras:v3", "sat-IN", assistant_id="t") == "sat-IN"
    assert validate_sarvam_language("saaras:v4", "sat-IN", assistant_id="t") == "sat-IN"
    # A model the plugin has no config for is passed through untouched: the plugin knows its
    # own roster better than a copy of it does. This is the path every sunset model takes.
    assert validate_sarvam_language("saarika:v2.5", "sat-IN", assistant_id="t") == "sat-IN"
    # Empty string is reachable from the API and must mean auto-detect, not en-IN.
    for blank in (None, "", "   ", "unknown"):
        assert validate_sarvam_language("saaras:v3", blank, assistant_id="t") == SARVAM_AUTO
    # Mode is model-gated the same way. Every model on the current roster takes it, and an
    # unknown model is passed through for the plugin to judge.
    assert validate_sarvam_mode("saaras:v3", "codemix", assistant_id="t") == "codemix"
    assert validate_sarvam_mode("saaras:v4", "codemix", assistant_id="t") == "codemix"
    assert validate_sarvam_mode("saarika:v2.5", "codemix", assistant_id="t") == "codemix"
    # TTS speakers are per generation, and the two generations overlap in nothing: every
    # bulbul:v2 speaker is a job-killing ValueError on bulbul:v3.
    assert validate_sarvam_speaker("bulbul:v3", "shubh", assistant_id="t") == "shubh"
    assert validate_sarvam_speaker("bulbul:v3", "anushka", assistant_id="t") is None
    assert validate_sarvam_speaker("bulbul:v2", "anushka", assistant_id="t") == "anushka"
    assert not set(sarvam_speakers("bulbul:v2")) & set(sarvam_speakers("bulbul:v3"))
    print("ok")
