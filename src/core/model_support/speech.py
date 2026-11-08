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

# A deliberate subset of `livekit.plugins.deepgram.models.DeepgramModels` + `V2Models`, not
# the whole Literal: the nova-3 and flux lines, the ones Deepgram still prices (checked 2026-09-22,
# https://deepgram.com/pricing). The nova-2, enhanced, base and hosted-whisper tiers still run
# at Deepgram but are off the price list, and this platform prices every call it accepts —
# accepting a model with no rate bills it as zero, which reads like a free call rather than an
# unpriced one. `nova-3` is the bare family alias Deepgram resolves to `nova-3-general`.
DEEPGRAM_STT_MODELS = frozenset(
    {
        "nova-3",
        "nova-3-general",
        "nova-3-multilingual",
        "flux-general-en",
        "flux-general-multi",
    }
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

# The OpenAI STT models billed by audio duration rather than by token. Everything else in
# OPENAI_STT_MODELS is token-billed, and the plugin's batch REST path (use_realtime=false)
# reports no tokens at all — so pairing a token-billed model with it stores a record that
# prices to zero. Only these models may take that path; see OpenAISTTConfig.use_realtime.
OPENAI_STT_DURATION_BILLED_MODELS = frozenset({"whisper-1"})

# ── TTS ───────────────────────────────────────────────────────────────────────────────
# livekit.plugins.elevenlabs.models.TTSModels, minus the retired models below. eleven_v3 is the
# platform default. eleven_v4 and eleven_v4_turbo arrived in livekit-agents 1.8.4.
#
# ElevenLabs retired the two v1 models. Probed on 2026-10-17, both answer 400
# `unsupported_model` ("have been deprecated and are no longer available"), though the plugin
# still lists them. scripts/migrate_tts_settings.py moves stored rows to eleven_multilingual_v2.
ELEVENLABS_RETIRED_TTS_MODELS = frozenset({"eleven_monolingual_v1", "eleven_multilingual_v1"})
ELEVENLABS_TTS_MODELS = frozenset(
    {
        "eleven_multilingual_v2",
        "eleven_turbo_v2",
        "eleven_turbo_v2_5",
        "eleven_flash_v2_5",
        "eleven_flash_v2",
        "eleven_v3",
        "eleven_v3_conversational",
        "eleven_v4",
        "eleven_v4_turbo",
    }
)

# The voice settings each ElevenLabs model does not read. The API refuses them with a 422
# (ElevenLabsTTSConfig), because ElevenLabs accepts and ignores them, so a stored value would
# look like it was doing something. Two sources, both checked 2026-10-17:
# - `style` and `use_speaker_boost`: the `can_use_style` / `can_use_speaker_boost` flags that
#   ElevenLabs' own `GET /v1/models` reports per model. Only eleven_multilingual_v2 takes both;
#   eleven_v3_conversational takes speaker boost but not style.
# - `speed` and `similarity_boost`: ElevenLabs' model notes
#   (https://elevenlabs.io/docs/eleven-creative/playground/text-to-speech): v3 has no speed or
#   similarity, v4 uses stability and similarity only. `/v1/models` has no flag for either.
# Stability is read by every model.
_NO_STYLE_OR_BOOST = frozenset({"style", "use_speaker_boost"})
ELEVENLABS_UNREAD_SETTINGS = {
    "eleven_v3": frozenset({"speed", "similarity_boost", "style", "use_speaker_boost"}),
    "eleven_v3_conversational": frozenset({"speed", "similarity_boost", "style"}),
    "eleven_v4": frozenset({"speed", "style", "use_speaker_boost"}),
    "eleven_v4_turbo": frozenset({"speed", "style", "use_speaker_boost"}),
    "eleven_turbo_v2": _NO_STYLE_OR_BOOST,
    "eleven_turbo_v2_5": _NO_STYLE_OR_BOOST,
    "eleven_flash_v2": _NO_STYLE_OR_BOOST,
    "eleven_flash_v2_5": _NO_STYLE_OR_BOOST,
}


def unread_elevenlabs_settings(model: str, voice_settings: dict | None) -> list[str]:
    """The settings in `voice_settings` that `model` ignores, sorted. Unset (None) ones never count."""
    unread = ELEVENLABS_UNREAD_SETTINGS.get(model, frozenset())
    return sorted(k for k, v in (voice_settings or {}).items() if v is not None and k in unread)


def models_reading(setting: str) -> list[str]:
    """Every allowlisted ElevenLabs model that reads this voice setting, for error messages."""
    return sorted(
        m for m in ELEVENLABS_TTS_MODELS if setting not in ELEVENLABS_UNREAD_SETTINGS.get(m, ())
    )

# Cartesia TTS takes no model field from the API: it is pinned in agents/tts/factory.py
# (sonic-3) because its other knobs are generation-specific — a model field would need a
# compatibility matrix behind it. Mistral is pinned for the same reason.
#
# Sarvam TTS has a model field since livekit-agents 1.8.6 added bulbul:v4-flash, and the
# matrix behind it is the speaker roster plus the v4 bounds, both below. bulbul:v3 stays the
# default, so a row written before the field existed keeps the voice it had.
DEFAULT_SARVAM_TTS_MODEL = "bulbul:v3"
SARVAM_TTS_MODELS = frozenset({"bulbul:v3", "bulbul:v4-flash"})

# The IN22 language codes: bulbul:v4-flash speaks them, bulbul:v3 does not. Written out
# because this module cannot import the plugin; tests/test_speech_models.py checks it against
# the plugin's language Literal.
SARVAM_V4_FLASH_ONLY_LANGUAGES = frozenset(
    {"as-IN", "brx-IN", "doi-IN", "kok-IN", "ks-IN", "mai-IN", "mni-IN", "ne-IN", "sa-IN", "sat-IN", "sd-IN", "ur-IN"}
)

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


# The bulbul:v4-flash roster (livekit.plugins.sarvam.models.BULBUL_V4_FLASH_SPEAKERS, all of
# it). It shares no name with v3: each v4 name carries its language and style, as in
# `shubh_hi_customer` or `simran_enhi_customer`, so `shubh` alone is fatal on v4 just as
# `shubh_hi_customer` is fatal on v3. The longest name is 31 characters.
SARVAM_V4_FLASH_SPEAKERS = frozenset(
    {
        "aarti_hi_customer",
        "aayan_hi_conversational",
        "aditi_en_stories",
        "aditya_hi_conversational",
        "aditya_hi_sales",
        "advait_hi_character",
        "amelia_en_conversational",
        "amit_hi_conversational",
        "anand_hi_documentary",
        "anand_hi_news",
        "anand_pa_conversation",
        "anand_pa_customer",
        "aparna_en_companion",
        "aparna_en_edtech",
        "aparna_hi_customer",
        "aparna_hi_kyc",
        "aryaman_hi_ads",
        "ashok_hi_character",
        "ashok_hi_news",
        "ashutosh_hi_conversational",
        "ashwin_en_sports",
        "ashwin_en_sports_energetic",
        "bappa_bn_conversation",
        "bhavik_gu_conversation",
        "bimal_bn_suspense",
        "chaitra_hi_customer",
        "chaitra_kn_conversation",
        "chaitra_kn_narration",
        "chandrika_en_stories",
        "chetan_kn_conversation",
        "chhavi_hi_kids",
        "chirag_hi_social",
        "dev_en_conversational",
        "dev_en_recovery",
        "deven_en_conversation",
        "girish_en_devotional",
        "girish_en_documentary",
        "girish_hi_devotional",
        "gokul_ta_narration",
        "harpreet_pa_narration",
        "ishita_en_customer",
        "ishita_en_medical",
        "ishita_en_numbers",
        "ishita_en_social",
        "ishita_en_stories",
        "ishita_enhi_companion",
        "ishita_enhi_customer",
        "ishita_enhi_customer_expressive",
        "ishita_hi_ads",
        "ishita_hi_ads_informal",
        "ishita_hi_banking",
        "ishita_hi_devotional",
        "ishita_hi_edtech",
        "ishita_hi_numbers",
        "ishita_hi_social",
        "ishita_mr_conversational",
        "jaspal_pa_banking",
        "kabir_hi_conversational",
        "kalpit_en_edtech",
        "kangkana_as_conversational",
        "kavitha_te_conversation",
        "kavitha_te_narration",
        "kavya_hi_conversational",
        "kunal_hi_kids",
        "mahesh_hi_documentary",
        "manan_hi_conversational",
        "mani_hi_conversational",
        "mani_hi_devotional",
        "mohit_hi_conversational",
        "mouchumi_as_conversational",
        "mrunal_mr_narration",
        "mukul_hi_ads",
        "mukul_hi_suspense",
        "mukul_mr_stories",
        "nachiket_en_ads",
        "nachiket_hi_devotional",
        "neha_en_customer",
        "neha_en_latenight",
        "neha_mr_narration",
        "nilesh_mr_conversation",
        "nupur_en_kids",
        "ojas_en_social",
        "payal_en_edtech",
        "pooja_gu_conversational",
        "pooja_gu_customer",
        "pooja_te_conversation",
        "priya_hi_recovery",
        "rahul_hi_conversational",
        "ratan_hi_customer_expressive",
        "ratan_hi_devotional",
        "ratan_hi_documentary",
        "ratan_hi_latenight",
        "ratan_hi_latenight_warm",
        "ratan_hi_recovery",
        "ratan_hi_social",
        "ratan_hi_sports",
        "rehan_hi_social",
        "ritu_en_edtech",
        "ritu_en_latenight",
        "ritu_en_medical",
        "ritu_en_reels",
        "ritu_hi_ads_formal",
        "ritu_hi_ads_informal",
        "ritu_hi_banking",
        "ritu_hi_conversation",
        "ritu_hi_customer",
        "ritu_hi_customer_utility",
        "ritu_hi_customer_warm",
        "ritu_hi_edtech",
        "ritu_hi_edtech_bot",
        "ritu_hi_insurance",
        "ritu_hi_kids",
        "ritu_hi_medical",
        "ritu_hi_reels",
        "ritu_hi_sales",
        "ritu_hi_social",
        "ritu_hi_social_lively",
        "ritu_mr_insurance",
        "ritu_mr_narration",
        "rohan_en_recovery",
        "roopa_bn_conversational",
        "roopa_en_conversational",
        "roopa_hi_companion",
        "roopa_hi_conversational",
        "roopa_hi_market",
        "roopa_hi_narration",
        "roopa_hi_recovery",
        "rupali_mr_stories",
        "rustom_en_suspense",
        "sanchita_en_companion",
        "sanchita_en_insurance",
        "sanchita_en_market",
        "sanchita_en_recovery",
        "sanchita_en_social",
        "sanchita_enhi_companion",
        "sanchita_hi_ads_formal",
        "sanchita_hi_ads_informal",
        "sanchita_hi_assistant",
        "sanchita_hi_banking",
        "sanchita_hi_edtech",
        "sanchita_hi_feedback",
        "sanchita_hi_interview",
        "sanchita_hi_kyc",
        "sanchita_hi_market",
        "sanchita_hi_romantic",
        "sanchita_hi_social",
        "sarang_en_narration",
        "sarika_hi_conversation",
        "shabana_en_edtech",
        "shalini_en_companion",
        "shalini_en_customer",
        "shalini_enhi_companion",
        "shalini_enhi_customer",
        "shalini_hi_companion",
        "shalini_hi_social",
        "shilpa_hi_narration",
        "shreya_hi_conversational",
        "shreya_hi_news",
        "shruti_hi_edtech",
        "shubh_en_ads",
        "shubh_en_audiobook",
        "shubh_en_narration",
        "shubh_en_narration_gentle",
        "shubh_en_numbers",
        "shubh_en_recovery",
        "shubh_en_sports",
        "shubh_enhi_ads",
        "shubh_enhi_banking",
        "shubh_enhi_companion",
        "shubh_hi_ads",
        "shubh_hi_customer",
        "shubh_hi_devotional",
        "shubh_hi_ecomm",
        "shubh_hi_recovery",
        "shubh_hi_stories_dramatic",
        "shubh_hi_stories_mixed",
        "simran_en_ads",
        "simran_en_automobile",
        "simran_en_conversation",
        "simran_en_customer",
        "simran_en_edtech",
        "simran_en_edtech_bot",
        "simran_en_narration",
        "simran_en_recovery",
        "simran_en_sales",
        "simran_en_therapist",
        "simran_enhi_banking_expressive",
        "simran_enhi_companion",
        "simran_enhi_customer",
        "simran_hi_assistant",
        "simran_hi_automobile",
        "simran_hi_conversation",
        "simran_hi_latenight",
        "simran_hi_narration",
        "simran_hi_news",
        "simran_hi_news_breaking",
        "simran_hi_recovery",
        "simran_hi_sales",
        "simran_hi_social_energetic",
        "simran_hi_social_excited",
        "soham_mr_narration",
        "sophia_en_conversational",
        "suchitra_hi_ecomm",
        "suchitra_kn_narration",
        "suhani_hi_social",
        "suman_hi_companion",
        "sumit_hi_conversational",
        "sunny_en_social",
        "sunny_enhi_customer",
        "sunny_hi_ads",
        "sunny_hi_reels",
        "tanya_hi_narration",
        "tarun_hi_conversational",
        "tarun_hi_sales",
        "tarun_te_narration",
        "vaibhav_hi_social",
        "vandana_hi_ecomm",
        "varun_en_ads",
        "varun_en_suspense",
        "vetri_ta_ads",
        "vetri_ta_suspense",
        "vijay_ta_narration",
        "vipul_hi_social",
        "zarina_en_conversation",
    }
)

SARVAM_SPEAKERS_BY_MODEL = {
    "bulbul:v3": SARVAM_TTS_SPEAKERS,
    "bulbul:v4-flash": SARVAM_V4_FLASH_SPEAKERS,
}

# Synthesis bounds bulbul:v4-flash enforces, tighter than v3's (livekit.plugins.sarvam.tts
# `_V4_PARAM_BOUNDS`). Streaming v4 also takes only these sample rates with the default mp3
# codec — the plugin raises on any other when it builds the socket URL.
SARVAM_V4_FLASH_PACE = (0.5, 2.0)
SARVAM_V4_FLASH_SAMPLE_RATES = frozenset({8000, 16000, 22050, 24000})


def unsupported_sarvam_speaker_reason(
    speaker: str | None, model: str = DEFAULT_SARVAM_TTS_MODEL
) -> str | None:
    """Why this Bulbul model cannot use this speaker, or None when it can."""
    roster = SARVAM_SPEAKERS_BY_MODEL.get(model)
    if not speaker or roster is None or speaker in roster:
        return None
    if model == "bulbul:v4-flash":
        # Listing 224 names helps nobody; the ones built on the same voice do.
        same_voice = sorted(name for name in roster if name.startswith(f"{speaker}_"))
        if same_voice:
            return (
                f"'{speaker}' is not a bulbul:v4-flash speaker. v4-flash names carry the "
                f"language and style — for this voice: {', '.join(same_voice)}"
            )
        return f"'{speaker}' is not a bulbul:v4-flash speaker"
    if speaker in SARVAM_V4_FLASH_SPEAKERS:
        return (
            f"'{speaker}' is a bulbul:v4-flash speaker — set model to 'bulbul:v4-flash', or "
            f"pick a bulbul:v3 speaker: {', '.join(sorted(SARVAM_TTS_SPEAKERS))}"
        )
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

# Cartesia and Mistral pin their model in the factory (sonic-3 and mistral-tts-1
# respectively) — there is no model field on their TTS config. The standalone
# endpoints still accept a `model` override for symmetry, but only the pinned id
# is legal; anything else is rejected before it reaches the vendor.
CARTESIA_TTS_MODEL = "sonic-3"
MISTRAL_TTS_MODEL = "mistral-tts-1"

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
