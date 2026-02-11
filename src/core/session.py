# session.py

import asyncio
from typing import cast

from livekit import rtc
from livekit.agents import (
    WorkerOptions,
    AgentSession,
    JobContext,
    cli,
    room_io,
)

from openai.types.realtime import AudioTranscription
from openai.types.beta.realtime.session import TurnDetection
from livekit.plugins.openai import realtime
from livekit.plugins import cartesia

from src.core.config import settings
from src.core.logger import logger
from src.models.agent_model import AgentModel
from src.agents.factory import AgentFactory


# ==============================
# ENTRYPOINT (Triggered per Job)
# ==============================
async def entrypoint(ctx: JobContext):

    logger.info("New Job Received")

    # ------------------------------------
    # 1️⃣ Get agent_id from job metadata
    # ------------------------------------
    agent_id = ctx.job.metadata.get("agent_id")

    if not agent_id:
        raise Exception("agent_id missing in job metadata")

    # ------------------------------------
    # 2️⃣ Load agent config from DB
    # ------------------------------------
    agent_config = await AgentModel.find_one(
        AgentModel.agent_id == agent_id
    )

    if not agent_config:
        raise Exception(f"Agent {agent_id} not found")

    logger.info(f"Loaded agent config: {agent_config.name}")

    # ------------------------------------
    # 3️⃣ Create LLM dynamically
    # ------------------------------------
    llm = realtime.RealtimeModel(
        model=agent_config.llm_model,
        input_audio_transcription=AudioTranscription(
            model=agent_config.transcription_model,
            prompt="Transcribe exactly what is spoken.",
        ),
        turn_detection=TurnDetection(
            type="semantic_vad",
            eagerness="low",
            create_response=True,
            interrupt_response=True,
        ),
        modalities=["text"],
        api_key=cast(str, settings.OPENAI_API_KEY),
    )

    # ------------------------------------
    # 4️⃣ Create TTS dynamically
    # ------------------------------------
    tts = cartesia.TTS(
        model="sonic-3",
        voice=agent_config.voice_id,
        api_key=settings.CARTESIA_API_KEY,
    )

    # ------------------------------------
    # 5️⃣ Create AgentSession (PER CALL)
    # ------------------------------------
    session = AgentSession(
        llm=llm,
        tts=tts,
        preemptive_generation=True,
        use_tts_aligned_transcript=True,
    )

    # ------------------------------------
    # 6️⃣ Create dynamic agent instance
    # ------------------------------------
    agent_instance = AgentFactory.create_agent(
        config=agent_config,
        room=ctx.room,
    )

    # ------------------------------------
    # 7️⃣ Configure Room
    # ------------------------------------
    room_options = room_io.RoomOptions(
        text_input=True,
        audio_input=True,
        audio_output=True,
        close_on_disconnect=True,
        delete_room_on_close=True,
    )

    # ------------------------------------
    # 8️⃣ Start Session
    # ------------------------------------
    await session.start(
        agent=agent_instance,
        room=ctx.room,
        room_options=room_options,
    )

    logger.info("Agent session started successfully")

    # ------------------------------------
    # 9️⃣ Wait for participant
    # ------------------------------------
    participant = await ctx.wait_for_participant()
    logger.info(f"User Connected: {participant.identity}")

    # ------------------------------------
    # 🔟 Greet User
    # ------------------------------------
    await session.generate_reply(
        instructions=f"{agent_config.system_prompt}\n\nGreet the user professionally."
    )

    # ------------------------------------
    # Keep session alive
    # ------------------------------------
    participant_left = asyncio.Event()

    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(p: rtc.RemoteParticipant):
        if p.identity == participant.identity:
            participant_left.set()

    while (
        ctx.room.connection_state == rtc.ConnectionState.CONN_CONNECTED
        and not participant_left.is_set()
    ):
        await asyncio.sleep(1)

    logger.info("Session ended")
