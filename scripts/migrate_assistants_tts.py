import asyncio
import os
import sys

# Ensure project root is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motor.motor_asyncio import AsyncIOMotorClient
from src.core.config import settings
from src.core.logger import logger, setup_logging

setup_logging()

async def migrate():
    # Only connect to DB, no Beanie init needed
    client = AsyncIOMotorClient(settings.MONGODB_URL)
    db = client[settings.DATABASE_NAME]
    collection = db["assistants"]

    logger.info("Connected to database...")

    cursor = collection.find({
        "$or": [
            {"assistant_tts_voice_id": {"$exists": True, "$ne": None}},
            {"assistant_tts_speaker": {"$exists": True, "$ne": None}}
        ]
    })

    updated_count = 0
    async for doc in cursor:
        tts_model = doc.get("assistant_tts_model")
        
        # Determine config based on model
        config = {}
        if tts_model == "cartesia":
            voice_id = doc.get("assistant_tts_voice_id")
            if voice_id:
                config = {"voice_id": voice_id}
        elif tts_model == "sarvam":
            speaker = doc.get("assistant_tts_speaker")
            if speaker:
                config = {
                    "speaker": speaker, 
                    "target_language_code": "bn-IN" # Default based on old code
                }

        if config:
            logger.info(f"Migrating assistant {doc.get('assistant_name')} ({doc.get('assistant_id')})")
            
            # Update operation
            await collection.update_one(
                {"_id": doc["_id"]},
                {
                    "$set": {"assistant_tts_config": config},
                    "$unset": {
                        "assistant_tts_voice_id": "", 
                        "assistant_tts_speaker": ""
                    }
                }
            )
            updated_count += 1
    
    logger.info(f"Migration complete. Updated {updated_count} assistants.")
    client.close()

if __name__ == "__main__":
    asyncio.run(migrate())
