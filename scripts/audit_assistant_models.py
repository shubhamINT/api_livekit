"""Find stored assistants whose model this deployment can no longer run.

Read-only by default. Writes nothing unless `--apply` is passed, which only ever clears a
model field so the assistant falls back to the documented default.

## Why

The API now refuses to store a model OpenAI does not serve, but that gate cannot reach
backwards. Three ways a row can already be broken:

- it was written before the gate existed;
- OpenAI retired the model *after* the row was last saved (three `*-chat-latest` aliases went
  on 2026-06-19);
- somebody edited MongoDB directly.

Each of those produces the same call: it connects, OpenAI rejects every LLM turn, and the
caller hears silence. Nothing surfaces until someone complains, so this finds them first.

## Usage

    uv run python scripts/audit_assistant_models.py                 # report only
    uv run python scripts/audit_assistant_models.py --no-network    # skip the OpenAI lookup
    uv run python scripts/audit_assistant_models.py --apply         # clear unusable models

`--apply` unsets `assistant_llm_config.model` on affected rows, so the assistant runs the
default for its mode (gpt-4.1 in cascade, gpt-realtime-1.5 in pipeline/realtime). It never
touches the API key, the knobs, or any other field, and it never guesses a replacement model.

The same scan covers the STT model, which can go stale the same way — the Deepgram allowlist
lost the nova-2, enhanced, base and whisper tiers when Deepgram stopped publishing a price for
them. There `--apply` unsets `assistant_stt_config.model`, falling back to `nova-3`.

Exit code is 1 when anything unusable was found, so it works as a post-deploy check.
"""

import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from src.core.config import settings  # noqa: E402
from src.core.model_support.capabilities import (  # noqa: E402
    CASCADE_MODELS,
    DEFAULT_CASCADE_MODEL,
    DEFAULT_GEMINI_LIVE_MODEL,
    DEFAULT_REALTIME_MODEL,
    GEMINI_LIVE_MODELS,
    REALTIME_MODELS,
)
from src.core.model_support.openai_live import available_models  # noqa: E402
from src.core.model_support.speech import unsupported_speech_model_reason  # noqa: E402


def expected_models(mode: str, provider: str | None) -> tuple[frozenset[str], str]:
    """The allowlist and the fallback default for this mode/provider pair."""
    if mode == "cascade":
        return CASCADE_MODELS, DEFAULT_CASCADE_MODEL
    if provider == "gemini":
        return GEMINI_LIVE_MODELS, DEFAULT_GEMINI_LIVE_MODEL
    return REALTIME_MODELS, DEFAULT_REALTIME_MODEL


def resolve_provider(mode: str, llm_config: dict) -> str:
    return (llm_config.get("provider") or ("gemini" if mode == "realtime" else "openai")).lower()


async def run(collection, *, apply: bool, servable: frozenset[str] | None) -> int:
    """One pass over the collection, checking both model fields an assistant can hold."""
    scanned = affected = 0

    async for doc in collection.find({}):
        scanned += 1
        mode = doc.get("assistant_mode") or "pipeline"
        llm_config = doc.get("assistant_llm_config") or {}
        model = llm_config.get("model")
        provider = resolve_provider(mode, llm_config)
        allowed, default_model = expected_models(mode, provider)

        # A field left unset runs the documented default, which is allowlisted by construction.
        problems = []
        if model:
            if model not in allowed:
                problems.append("not on this platform's supported list")
            # The live list covers OpenAI only; Gemini has no equivalent endpoint.
            if servable is not None and provider == "openai" and model not in servable:
                problems.append("not served by the OpenAI account for the system key")

        stt_provider = doc.get("assistant_stt_model")
        stt_model = (doc.get("assistant_stt_config") or {}).get("model")
        stt_reason = unsupported_speech_model_reason(stt_provider, stt_model, stage="stt")

        if not problems and not stt_reason:
            continue

        affected += 1
        active = "" if doc.get("assistant_is_active", True) else "  [inactive]"
        print(f"  {doc.get('assistant_id')}  mode={mode} provider={provider}{active}")
        if problems:
            print(f"      model={model!r}: {'; '.join(problems)}")
            print(f"      clearing it would fall back to {default_model!r}")
        if stt_reason:
            print(f"      stt={stt_provider} model={stt_model!r}: {stt_reason}")
            print("      clearing it would fall back to that provider's default")

        if apply:
            unset = {}
            if problems:
                unset["assistant_llm_config.model"] = ""
            if stt_reason:
                unset["assistant_stt_config.model"] = ""
            await collection.update_one({"_id": doc["_id"]}, {"$unset": unset})

    verb = "Cleared a model on" if apply else "Would clear a model on"
    print(f"\n{verb} {affected} of {scanned} assistant(s).")
    if affected and not apply:
        print("Re-run with --apply to write, or set a specific model per assistant instead.")
    return affected


async def main() -> None:
    apply = "--apply" in sys.argv
    no_network = "--no-network" in sys.argv

    servable: frozenset[str] | None = None
    if not no_network:
        if not settings.OPENAI_API_KEY:
            print("OPENAI_API_KEY is not set — checking the static lists only.")
        else:
            servable = await available_models(settings.OPENAI_API_KEY)
            if servable is None:
                print("Could not reach OpenAI — checking the static lists only.")
            else:
                print(f"OpenAI serves {len(servable)} model id(s) for the system key.")

    print(f"Connecting to MongoDB at {settings.MONGODB_URL}...")
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    collection = client[settings.DATABASE_NAME]["assistants"]

    if not apply:
        print("Dry run — nothing will be written.\n")
    affected = await run(collection, apply=apply, servable=servable)
    raise SystemExit(1 if affected and not apply else 0)


if __name__ == "__main__":
    asyncio.run(main())
