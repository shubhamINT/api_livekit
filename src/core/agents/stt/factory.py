"""Resolve the user-transcription source from the assistant's STT model + config."""

from livekit.plugins import cartesia, deepgram, elevenlabs, openai

from src.core.agents.stt.cascade_usage import CascadeSttUsage, MeteredSarvamSTT
from src.core.agents.stt.lang import (
    DEEPGRAM_MULTI,
    validate_language,
    validate_sarvam_language,
    validate_sarvam_mode,
)
from src.core.config import settings
from src.core.logger import logger
from src.core.model_support.speech import OPENAI_STT_DURATION_BILLED_MODELS

# Deepgram models that can auto-detect. The nova-2 and flux-general-en families cannot, so
# an unpinned language there stays on Deepgram's own documented default.
_DEEPGRAM_AUTODETECT_MODELS = ("nova-3", "flux-general-multi")


def resolve_stt(assistant) -> tuple[str, dict]:
    """Return (provider, config) for user transcription. Unset means Sarvam, the default.

    "sarvam" runs Sarvam Saras v3 as a parallel audio tap (native-script Indic
    transcripts); "native" lets the conversational LLM transcribe itself
    (OpenAI gpt-4o-mini-transcribe, or Gemini's own); "cartesia", "deepgram",
    "elevenlabs" and "openai" are cascade-only plugins — resolved here but only
    instantiated by create_stt. Ignored in realtime (audio-out) mode.
    """
    model = assistant.assistant_stt_model or "sarvam"
    if model == "openai":
        # In pipeline mode the OpenAI STT plugin buys nothing over the realtime model's own
        # transcription — same vendor, same gpt-4o-mini-transcribe, one less connection. It
        # is a cascade-only provider, so collapse it to native here. This also keeps the
        # pre-migration rows (where "openai" *meant* native) working unchanged.
        model = "native"
    config = assistant.assistant_stt_config or {}

    # Selecting a plugin STT disables the LLM's own transcription, so an unauthenticated
    # plugin means the call keeps no user transcripts at all. Degrade to native instead.
    key_var = {
        "sarvam": settings.SARVAM_API_KEY,
        "cartesia": settings.CARTESIA_API_KEY,
        "deepgram": settings.DEEPGRAM_API_KEY,
        "elevenlabs": settings.ELEVENLABS_API_KEY,
    }.get(model)
    plugin_model = model in {"sarvam", "cartesia", "deepgram", "elevenlabs"}
    if plugin_model and not (config.get("api_key") or key_var):
        logger.warning(
            f"No {model} API key for assistant {assistant.assistant_id} — falling back to native STT."
        )
        return "native", {}

    return model, config


def create_stt(assistant, usage: CascadeSttUsage | None = None):
    """Build a plugin STT instance for cascade mode. Returns None on error.

    Distinct from resolve_stt: cascade puts STT on the AgentSession as a first-class
    stage, so "native" (the conversational LLM transcribing itself) has no meaning
    here — there is no realtime model in the loop to do it.

    `usage` is the call's cascade STT tally. It is stamped, and the returned STT wrapped,
    only for a provider whose own usage reporting cannot be trusted — Sarvam today. Left
    None (the default) the behaviour is exactly what it was before that tally existed.
    """
    stt_config = assistant.assistant_stt_config or {}
    model = assistant.assistant_stt_model or "sarvam"
    assistant_id = assistant.assistant_id

    if model == "sarvam":
        api_key = stt_config.get("api_key") or settings.SARVAM_API_KEY
        if not api_key:
            logger.error(f"No Sarvam API key for cascade assistant {assistant_id}")
            return None
        # The multilingual default: language "unknown" auto-detects, and mode "codemix"
        # keeps code-switching intact inside a single utterance.
        # interaction_config.preferred_languages needs no wiring here — auto-detect
        # already covers every language it could list, and pinning one would be strictly
        # worse for a caller who switches mid-call. Set `language` explicitly to pin.
        # The language is validated, not passed through: the Sarvam plugin RAISES on a code
        # its model does not speak, and that exception escapes create_stt and kills the job.
        sarvam_model = stt_config.get("model", "saaras:v3")
        # Wrapped, not plain: the plugin reports the audio duration the server sent, which is
        # missing on some responses and absent entirely on an empty transcript. The session
        # counts the frames instead (DynamicAssistant.stt_node) and MeteredSarvamSTT keeps the
        # plugin's number out of the collector, so the record carries one entry, not two.
        if usage is not None:
            usage.provider = "sarvam"
            usage.model = sarvam_model
        return MeteredSarvamSTT(
            usage=usage if usage is not None else CascadeSttUsage(),
            model=sarvam_model,
            mode=validate_sarvam_mode(
                sarvam_model, stt_config.get("mode", "codemix"), assistant_id=assistant_id
            ),
            language=validate_sarvam_language(
                sarvam_model, stt_config.get("language"), assistant_id=assistant_id
            ),
            api_key=api_key,
            sample_rate=16000,
        )

    if model == "cartesia":
        api_key = stt_config.get("api_key") or settings.CARTESIA_API_KEY
        if not api_key:
            logger.error(f"No Cartesia API key for cascade assistant {assistant_id}")
            return None
        # Cartesia STT cannot auto-detect, so exactly one language gets transcribed and
        # "unpinned" has to mean something — English, the plugin's own default. Note this
        # is the ONE provider here with no auto-detect: for a multilingual caller, use
        # Sarvam, or Deepgram nova-3 on 'multi'.
        language = validate_language(
            "cartesia",
            stt_config.get("language"),
            assistant_id=assistant_id,
            field="assistant_stt_config.language",
        ) or "en"
        # ponytail: model pinned, never left to the plugin default. That default flipped
        # to the English-only ink-2 in livekit-agents 1.5.15; ink-whisper is the
        # 43-language one.
        return cartesia.STT(
            model=stt_config.get("model", "ink-whisper"),
            language=language,
            api_key=api_key,
        )

    if model == "deepgram":
        api_key = stt_config.get("api_key") or settings.DEEPGRAM_API_KEY
        if not api_key:
            logger.error(f"No Deepgram API key for cascade assistant {assistant_id}")
            return None
        deepgram_model = stt_config.get("model", "nova-3")
        pinned = validate_language(
            "deepgram",
            stt_config.get("language"),
            assistant_id=assistant_id,
            field="assistant_stt_config.language",
        )
        kwargs: dict[str, object] = {}
        if stt_config.get("keyterm"):
            kwargs["keyterm"] = stt_config["keyterm"]
        # Two different Deepgram APIs behind one provider name. The nova family speaks
        # /listen/v1 (deepgram.STT); the flux family speaks the turn-based /listen/v2
        # (deepgram.STTv2) and ships its own endpointing. Neither class validates the
        # model at construction, so a flux ID sent to STT connects to v1 and fails there
        # — dispatch on the name instead.
        if deepgram_model.startswith("flux"):
            if stt_config.get("enable_diarization"):
                logger.warning(
                    f"enable_diarization is ignored on Deepgram '{deepgram_model}' "
                    f"(nova models only) for assistant {assistant_id}"
                )
            # language_hint, not language: v2 detects on its own and only takes a bias.
            # It is a list[str], not a str — a bare string reaches the wire as a JSON
            # string where the API wants an array. It is also flux-general-multi only
            # (the plugin warns and drops it otherwise), and 'multi' is a v1 sentinel
            # that means nothing here: for flux, "no hint" already IS auto-detect.
            if pinned and pinned != DEEPGRAM_MULTI:
                if deepgram_model == "flux-general-multi":
                    kwargs["language_hint"] = [pinned]
                else:
                    logger.warning(
                        f"Deepgram '{deepgram_model}' ignores a pinned language "
                        f"({pinned!r}) for assistant {assistant_id} — language_hint is "
                        "supported on 'flux-general-multi' only"
                    )
            return deepgram.STTv2(
                model=deepgram_model,
                api_key=api_key,
                **kwargs,
            )
        # nova-3 is the multilingual default (45 languages; 'multi' auto-detects per
        # segment). Unpinned means auto-detect wherever the model can do it — 'multi' is
        # billed at a higher per-minute rate, so pin a language to avoid that. nova-2 and
        # the -en model families cannot detect, so they stay on Deepgram's own default.
        default_language = (
            DEEPGRAM_MULTI
            if deepgram_model.startswith(_DEEPGRAM_AUTODETECT_MODELS)
            else "en-US"
        )
        if stt_config.get("enable_diarization"):
            kwargs["enable_diarization"] = True
        return deepgram.STT(
            model=deepgram_model,
            language=pinned or default_language,
            api_key=api_key,
            **kwargs,
        )

    if model == "elevenlabs":
        api_key = stt_config.get("api_key") or settings.ELEVENLABS_API_KEY
        if not api_key:
            logger.error(f"No ElevenLabs API key for cascade assistant {assistant_id}")
            return None
        # Scribe wants ISO 639-3 ('eng'), not BCP-47 ('en-US') — a BCP-47 code closes the
        # socket with `1008 invalid_request` on the first utterance, so validate before
        # sending. Unset (or rejected) means auto-detect among ~190 languages, which is
        # what this provider is for. no_verbatim cleans filler words out of the transcript.
        language_code = validate_language(
            "elevenlabs",
            stt_config.get("language_code"),
            assistant_id=assistant_id,
            field="assistant_stt_config.language_code",
        )
        stt = elevenlabs.STT(
            model=stt_config.get("model", "scribe_v2_realtime"),
            language_code=language_code,
            no_verbatim=stt_config.get("no_verbatim", False),
            api_key=api_key,
        )
        if language_code:
            # ponytail: private attribute, deliberately. The plugin wraps language_code in
            # livekit.agents.LanguageCode, which normalizes ISO 639-3 down to ISO 639-1
            # ("hin" -> "hi") — and ISO 639-1 is exactly what Scribe rejects. So the
            # constructor argument above cannot express a valid pin for any language that
            # has a 639-1 code, and the raw string has to be put back afterwards. The
            # stream reads _opts.language_code straight into the query string.
            # Upgrade path: drop this line once the plugin stops normalizing.
            stt._opts.language_code = language_code
        return stt

    if model == "openai":
        api_key = stt_config.get("api_key") or settings.OPENAI_API_KEY
        if not api_key:
            logger.error(f"No OpenAI API key for cascade assistant {assistant_id}")
            return None
        openai_model = stt_config.get("model", "gpt-4o-mini-transcribe")
        # gpt-realtime-whisper has no server-side endpointing: the plugin then wants a
        # livekit-plugins-silero VAD to commit the buffer, which is not installed here
        # (the session's VAD is inference.VAD from livekit-local-inference and cannot be
        # handed to the STT). Constructing it would raise ImportError at job start.
        if openai_model.startswith("gpt-realtime-whisper"):
            logger.error(
                f"OpenAI STT model {openai_model!r} is not supported for assistant "
                f"{assistant_id} — it needs a client-side VAD to commit audio. Use "
                "'gpt-4o-mini-transcribe', 'gpt-4o-transcribe' or 'whisper-1'."
            )
            return None
        # detect_language wins: the plugin blanks `language` when it is set, which is how
        # auto-detect is expressed. Codes here are ISO 639-1 ('hi'), not BCP-47 ('hi-IN').
        # With nothing pinned, detect rather than silently transcribing a Hindi caller as
        # English — the plugin's own default is a hardcoded "en".
        language = validate_language(
            "openai",
            stt_config.get("language"),
            assistant_id=assistant_id,
            field="assistant_stt_config.language",
        )
        detect_language = bool(stt_config.get("detect_language", False)) or not language
        language = language or "en"  # ignored while detect_language is on
        kwargs: dict[str, object] = {}
        if stt_config.get("prompt"):
            # whisper-1 only; the gpt-4o transcribe models ignore it.
            kwargs["prompt"] = stt_config["prompt"]
        if stt_config.get("noise_reduction_type"):
            kwargs["noise_reduction_type"] = stt_config["noise_reduction_type"]
        # use_realtime streams over the transcription WebSocket (interim results, much
        # lower latency); the plugin default is the batch REST API, which is wrong for a
        # live call, so default the other way.
        use_realtime = bool(stt_config.get("use_realtime", True))
        if not use_realtime and openai_model not in OPENAI_STT_DURATION_BILLED_MODELS:
            # The batch path discards the server's usage, so a token-billed model on it
            # stores stt_input_tokens = 0 and prices to nothing. The API rejects this pairing
            # now; a row stored before that gate existed is overridden rather than refused —
            # a call must not start failing over a metric.
            logger.warning(
                f"Assistant {assistant_id} pairs OpenAI STT model {openai_model!r} with "
                "use_realtime=false, which reports no token usage — forcing use_realtime=true. "
                "Only 'whisper-1' is billed by duration and may use the batch path."
            )
            use_realtime = True
        return openai.STT(
            model=openai_model,
            language=language,
            detect_language=detect_language,
            use_realtime=use_realtime,
            api_key=api_key,
            **kwargs,
        )

    logger.error(
        f"Unsupported cascade STT model {model!r} for assistant {assistant_id} "
        "— cascade supports 'sarvam', 'cartesia', 'deepgram', 'elevenlabs' or 'openai'"
    )
    return None
