"""Fold an AgentSession's per-component usage into flat UsageRecord fields.

`session.usage` reports one typed entry per (provider, model) pair — an LLM entry, a
TTS entry, an STT entry, and one more of each if a model was swapped mid-call.

Both representations are stored, on purpose. The raw list is the one pricing should read:
summing loses the per-model attribution, so a call that swapped models cannot be charged
correctly from the totals alone. The flat columns are kept because the admin analytics
endpoints aggregate with `$sum` across thousands of records, which Mongo cannot do over
array elements without unwinding every document first.

This replaces the deprecated UsageCollector/UsageSummary pair. Everything is in-process
aggregation of plugin metrics, so it works on a self-hosted server with no Cloud calls.
"""

from beanie.operators import Set

from src.core.db.db_schemas import UsageRecord
from src.core.logger import logger

# Components that cost money. The SDK also reports eot_usage and interruption_usage, but
# this deployment runs the turn detector locally (inference.TurnDetector v1-mini), so
# those rows are free and would only pad every stored record.
BILLABLE_TYPES = ("llm_usage", "tts_usage", "stt_usage")

# The schema version written into every new record. See UsageRecord in db_schemas.py.
USAGE_SCHEMA_VERSION = 2


def _models(entries) -> str | None:
    """Comma-join the distinct model names seen, preserving order. None if empty."""
    names = list(dict.fromkeys(e.model for e in entries if e.model))
    return ", ".join(names) or None


def _sdk_version() -> str | None:
    try:
        from livekit.agents import __version__

        return __version__
    except Exception:
        return None


def summarize_usage(session, extra_usage=()) -> dict:
    """Return UsageRecord field values for `session`. Never raises — usage is not
    worth losing a call record over, so on any failure it degrades to zeros.

    `extra_usage` carries entries the session's own collector never saw, because the
    component runs outside the AgentSession — today that is the pipeline-mode Sarvam STT
    tap. They are the same typed models the SDK produces, so everything below treats them
    identically, and they survive a failed `session.usage` read on purpose.
    """
    try:
        entries = list(session.usage.model_usage)
    except Exception as e:
        logger.warning(f"Could not read session usage: {e}")
        entries = []  # same code path below, so every field still gets its zero
    entries += extra_usage

    llm = [e for e in entries if e.type == "llm_usage"]
    tts = [e for e in entries if e.type == "tts_usage"]
    stt = [e for e in entries if e.type == "stt_usage"]

    def total(items, field: str):
        return sum(getattr(i, field, 0) or 0 for i in items)

    return {
        "llm_input_tokens": total(llm, "input_tokens"),
        "llm_output_tokens": total(llm, "output_tokens"),
        "llm_input_audio_tokens": total(llm, "input_audio_tokens"),
        "llm_input_text_tokens": total(llm, "input_text_tokens"),
        "llm_input_image_tokens": total(llm, "input_image_tokens"),
        # Subsets of the input counts above, never additional to them — see UsageRecord.
        "llm_input_cached_tokens": total(llm, "input_cached_tokens"),
        "llm_input_cached_audio_tokens": total(llm, "input_cached_audio_tokens"),
        "llm_input_cached_text_tokens": total(llm, "input_cached_text_tokens"),
        "llm_input_cached_image_tokens": total(llm, "input_cached_image_tokens"),
        "llm_input_cache_creation_tokens": total(llm, "input_cache_creation_tokens"),
        "llm_output_audio_tokens": total(llm, "output_audio_tokens"),
        "llm_output_text_tokens": total(llm, "output_text_tokens"),
        # Matches the previous definition (prompt + completion), which the admin
        # analytics endpoints already sum on.
        "llm_total_tokens": total(llm, "input_tokens") + total(llm, "output_tokens"),
        "llm_session_duration": total(llm, "session_duration"),
        "llm_model": _models(llm),
        "tts_characters_count": total(tts, "characters_count"),
        "tts_audio_duration": total(tts, "audio_duration"),
        "tts_input_tokens": total(tts, "input_tokens"),
        "tts_output_tokens": total(tts, "output_tokens"),
        "stt_model": _models(stt),
        "stt_audio_duration": total(stt, "audio_duration"),
        "stt_input_tokens": total(stt, "input_tokens"),
        # Subsets of stt_input_tokens. Only NativeSttModelUsage carries them; `total` reads
        # them with getattr, so a plain SDK entry contributes zero.
        "stt_input_audio_tokens": total(stt, "input_audio_tokens"),
        "stt_input_text_tokens": total(stt, "input_text_tokens"),
        "stt_output_tokens": total(stt, "output_tokens"),
        # Full dump, zeros included: pricing reads keys, it should never have to decide
        # whether a missing one means zero or means the SDK stopped reporting it.
        "model_usage": [e.model_dump() for e in entries if e.type in BILLABLE_TYPES],
        "usage_schema_version": USAGE_SCHEMA_VERSION,
        "sdk_version": _sdk_version(),
    }


async def upsert_usage_record(record: UsageRecord) -> None:
    """Write `record` to the one row keyed by its `room_name`, creating it if it is not there.

    An upsert rather than an insert because the record is now written repeatedly: a snapshot
    every `USAGE_FLUSH_INTERVAL_S` while the call runs, then the authoritative write at
    teardown. A worker that dies between them leaves the last snapshot behind instead of
    nothing at all, and two teardown routes racing each other can no longer produce the
    duplicate-key error a second `insert()` raised.

    `created_at` is left out of the update so it keeps marking when the record was first
    written rather than when the last snapshot landed; `on_insert` carries it for the write
    that creates the row.
    """
    await UsageRecord.find_one({"room_name": record.room_name}).upsert(
        Set(record.model_dump(exclude={"id", "created_at"})),
        on_insert=record,
    )
