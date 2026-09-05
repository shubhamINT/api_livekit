"""Which STT and TTS model ids each speech provider accepts.

Same job as `capabilities.py` does for the LLM stage, and the same reason it is here rather
than beside the factories: the API has to reject a bad value at create/update time, and the API
container has no `livekit-agents` to read the plugins' own Literals from.

So the sets are written out, and `tests/test_speech_models.py` asserts each one still agrees
with the installed plugin. That test is the mechanism that keeps this file honest across a
`livekit-agents` bump — a plugin that drops a model id fails the suite instead of failing a
call.

Where a set is deliberately *wider* than the plugin's Literal, the extra ids are named and
explained. Those Literals are advisory (every plugin types `model` as `... | str` and forwards
it untouched), and two of them are missing ids the vendor documents and this platform's own
docs already advertise. Where a set is *narrower*, the excluded id is named too — one of them
cannot run in this deployment at all.

Nothing here validates a *language* code: those live in `agents/stt/lang.py`, which may import
plugins because only the agent image needs it. Language mismatches degrade to auto-detect at
call time; a wrong model id does not degrade to anything.
"""

# ── STT ───────────────────────────────────────────────────────────────────────────────
# livekit.plugins.sarvam.stt.MODEL_CONFIGS. saaras:v3 stays the platform default; saaras:v4 is
# the plugin's own default since 1.7.1 and takes the same languages and modes. The v2.5 pair
# (saaras:v2.5, saarika:v2.5) was sunset by Sarvam and dropped from the plugin roster in 1.7.1,
# so it is rejected here too — an assistant still holding one is found by
# `scripts/audit_assistant_models.py`.
SARVAM_STT_MODELS = frozenset({"saaras:v3", "saaras:v4"})

# livekit.plugins.cartesia.models.STTModels. ink-whisper is 43 languages, one at a time;
# ink-2 is English only and became the plugin default in 1.5.15, which is why the factory pins
# a model rather than letting the default ride.
CARTESIA_STT_MODELS = frozenset({"ink-whisper", "ink-2"})

# livekit.plugins.deepgram.models.DeepgramModels + V2Models, plus the two bare family aliases
# below. Deepgram resolves `nova-2` and `nova-3` server-side to the -general variant, this
# platform's docs advertise `nova-2`, and the plugin's Literal happens to list `nova-3` but not
# `nova-2` — an inconsistency in their Literal, not in the API.
DEEPGRAM_FAMILY_ALIASES = frozenset({"nova-2", "nova"})
DEEPGRAM_STT_MODELS = (
    frozenset(
        {
            "base",
            "conversationalai",
            "enhanced-finance",
            "enhanced-general",
            "enhanced-meeting",
            "enhanced-phonecall",
            "finance",
            "flux-general-en",
            "flux-general-multi",
            "meeting",
            "nova-2-atc",
            "nova-2-automotive",
            "nova-2-conversationalai",
            "nova-2-drivethru",
            "nova-2-finance",
            "nova-2-general",
            "nova-2-medical",
            "nova-2-meeting",
            "nova-2-phonecall",
            "nova-2-video",
            "nova-2-voicemail",
            "nova-3",
            "nova-3-general",
            "nova-3-medical",
            "nova-3-multilingual",
            "nova-general",
            "nova-meeting",
            "nova-phonecall",
            "phonecall",
            "video",
            "voicemail",
            "whisper-base",
            "whisper-large",
            "whisper-medium",
            "whisper-small",
            "whisper-tiny",
        }
    )
    | DEEPGRAM_FAMILY_ALIASES
)

# livekit.plugins.elevenlabs.stt.ElevenLabsSTTModels. Only scribe_v2_realtime streams; the
# other two are batch models and add a full utterance of latency per turn.
ELEVENLABS_STT_MODELS = frozenset({"scribe_v1", "scribe_v2", "scribe_v2_realtime"})

# openai.types.AudioModel, minus the realtime-whisper line. That one has no server-side
# endpointing: the plugin then requires a livekit-plugins-silero VAD to commit the buffer,
# which is not installed here (the session's VAD is inference.VAD from
# livekit-local-inference and cannot be handed to an STT). Constructing it raises ImportError
# at job start, so it is rejected at the API instead — see agents/stt/factory.py, which
# repeats the check for rows written before this list existed.
OPENAI_STT_MODELS = frozenset(
    {
        "whisper-1",
        "gpt-transcribe",
        "gpt-4o-transcribe",
        "gpt-4o-mini-transcribe",
        "gpt-4o-mini-transcribe-2025-12-15",
        "gpt-4o-transcribe-diarize",
    }
)

# ── TTS ───────────────────────────────────────────────────────────────────────────────
# livekit.plugins.elevenlabs.models.TTSModels. eleven_v3 is the platform default. It and
# eleven_v3_conversational are the two with no `speed` control — see agents/tts/factory.py,
# which drops the knob for them.
ELEVENLABS_TTS_MODELS = frozenset(
    {
        "eleven_monolingual_v1",
        "eleven_multilingual_v1",
        "eleven_multilingual_v2",
        "eleven_turbo_v2",
        "eleven_turbo_v2_5",
        "eleven_flash_v2_5",
        "eleven_flash_v2",
        "eleven_v3",
        "eleven_v3_conversational",
    }
)

# Cartesia TTS and Sarvam TTS take no model field from the API: both are pinned in
# agents/tts/factory.py (sonic-3, bulbul:v3) because their other knobs are generation-specific
# — a model field would need a compatibility matrix behind it. Mistral is pinned for the same
# reason. Nothing to allowlist here; the pins are the allowlist.

# The bulbul:v3 speaker roster (livekit.plugins.sarvam.tts.MODEL_SPEAKER_COMPATIBILITY, the
# "all" list for the pinned model). Worth checking at the API rather than only at call time:
# the Sarvam plugin *raises* on a speaker its model cannot use, and that exception escapes
# create_tts and entrypoint() — the job dies with a traceback and the caller hears nothing.
#
# The v2 roster shares not one name with v3, so a speaker copied from an older doc or an older
# assistant is the easy way in: anushka, manisha, vidya, arya, abhilash, karun and hitesh are
# all v2-only and all fatal on v3.
SARVAM_V2_SPEAKERS = frozenset(
    {"abhilash", "anushka", "arya", "hitesh", "karun", "manisha", "vidya"}
)

SARVAM_TTS_SPEAKERS = frozenset(
    {
        "aayan",
        "aditya",
        "advait",
        "amelia",
        "amit",
        "ashutosh",
        "dev",
        "ishita",
        "kabir",
        "kavitha",
        "kavya",
        "manan",
        "neha",
        "pooja",
        "priya",
        "rahul",
        "ratan",
        "ritu",
        "rohan",
        "roopa",
        "rupali",
        "shreya",
        "shruti",
        "shubh",
        "simran",
        "sophia",
        "suhani",
        "sumit",
        "tanya",
        "varun",
    }
)


def unsupported_sarvam_speaker_reason(speaker: str | None) -> str | None:
    """Why bulbul:v3 cannot use this speaker, or None when it can."""
    if not speaker or speaker in SARVAM_TTS_SPEAKERS:
        return None
    if speaker in SARVAM_V2_SPEAKERS:
        return (
            f"'{speaker}' is a bulbul:v2 speaker and this platform runs bulbul:v3, whose "
            "roster shares no names with v2 — pick one of: "
            f"{', '.join(sorted(SARVAM_TTS_SPEAKERS))}"
        )
    return (
        f"'{speaker}' is not a bulbul:v3 speaker — pick one of: "
        f"{', '.join(sorted(SARVAM_TTS_SPEAKERS))}"
    )

# Which env var holds the system key for each provider, per stage. One variable per vendor:
# ELEVENLABS_API_KEY and SARVAM_API_KEY each serve both stages.
STT_ENV_KEYS = {
    "sarvam": "SARVAM_API_KEY",
    "cartesia": "CARTESIA_API_KEY",
    "deepgram": "DEEPGRAM_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "openai": "OPENAI_API_KEY",
}

TTS_ENV_KEYS = {
    "cartesia": "CARTESIA_API_KEY",
    "sarvam": "SARVAM_API_KEY",
    "elevenlabs": "ELEVENLABS_API_KEY",
    "mistral": "MISTRAL_API_KEY",
}

STT_MODELS_BY_PROVIDER = {
    "sarvam": SARVAM_STT_MODELS,
    "cartesia": CARTESIA_STT_MODELS,
    "deepgram": DEEPGRAM_STT_MODELS,
    "elevenlabs": ELEVENLABS_STT_MODELS,
    "openai": OPENAI_STT_MODELS,
}

TTS_MODELS_BY_PROVIDER = {
    "elevenlabs": ELEVENLABS_TTS_MODELS,
}


def unsupported_speech_model_reason(provider: str, model: str | None, *, stage: str) -> str | None:
    """Why this provider cannot run this model id, or None when it can.

    `stage` is "stt" or "tts" — the two have separate tables because a vendor can appear in
    both with different model families (ElevenLabs: scribe_* vs eleven_*).

    A provider with no entry in the table returns None: its model is pinned in the factory and
    the API takes no model field for it.
    """
    if not model:
        return None
    table = STT_MODELS_BY_PROVIDER if stage == "stt" else TTS_MODELS_BY_PROVIDER
    allowed = table.get(provider)
    if not allowed or model in allowed:
        return None
    return (
        f"'{provider}' does not have a {stage.upper()} model called '{model}' — "
        f"choose one of: {', '.join(sorted(allowed))}"
    )
