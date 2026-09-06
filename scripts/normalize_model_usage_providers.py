"""Normalize provider keys in existing version-2 usage records."""

import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient

from src.core.agents.usage import USAGE_SCHEMA_VERSION, normalize_provider
from src.core.config import settings


async def main() -> None:
    apply = "--apply" in sys.argv
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    collection = client[settings.DATABASE_NAME]["usage_records"]
    scanned = changed = 0
    async for row in collection.find({"usage_schema_version": 2}):
        scanned += 1
        usage = row.get("model_usage", [])
        updated = []
        row_changed = False
        for entry in usage:
            normalized = normalize_provider(entry.get("provider", ""))
            if normalized != entry.get("provider"):
                row_changed = True
            updated.append({**entry, "provider": normalized})
        if row_changed:
            changed += 1
            print(f"  {row.get('room_name')}: provider spelling changes")
        if apply:
            await collection.update_one(
                {"_id": row["_id"]},
                {"$set": {"model_usage": updated, "usage_schema_version": USAGE_SCHEMA_VERSION}},
            )
    action = "Updated" if apply else "Would update"
    print(f"{action} {changed} of {scanned} version-2 usage record(s).")
    if not apply:
        print("Dry run — pass --apply to write changes.")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
