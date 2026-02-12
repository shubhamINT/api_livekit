from dotenv import load_dotenv
from livekit import rtc
from livekit.agents import (
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    room_io,
    BackgroundAudioPlayer,
    AudioConfig,
)
from openai.types.beta.realtime.session import TurnDetection
from livekit.plugins import cartesia
from livekit.plugins.openai import realtime
from openai.types.realtime import AudioTranscription
import os
import asyncio
import json
from typing import cast, Optional

from src.core.config import settings
from src.core.logger import logger, setup_logging
from src.core.agents.dynamic_assistant import DynamicAssistant
from src.core.agents.utils import render_prompt
from src.core.db.database import Database
from src.core.db.db_schemas import Assistant
from src.services.livekit.livekit_svc import LiveKitService


setup_logging()
load_dotenv(override=True)


async def entrypoint(ctx: JobContext):
    # Ensure database connection
    # Note: explicit connect is needed because the worker entrypoint might run in a separate process/loop
    try:
        await Database.connect_db()
    except Exception as e:
        logger.error(f"Failed to connect to database in worker: {e}")
        return

    # Retrieve agent ID from room name
    # Assumption: room name format is "{assistant_id}-{unique_suffix}" or just "{assistant_id}"
    room_name = ctx.room.name
    assistant_id = room_name.split("_", 1)[0]

    logger.info(f"Agent session starting | room: {room_name} | identifier: {assistant_id}")

    # Fetch assistant from DB
    assistant = await Assistant.find_one(Assistant.assistant_id == assistant_id)

    if not assistant:
        logger.error(f"No assistant found for identifier: {assistant_id}")
        return

    logger.info(f"Loaded assistant config: {assistant.assistant_name} (ID: {assistant.assistant_id})")

    # Extract metadata from job metadata (reliable way to pass data to agent)
    to_number = "Unknown"
    job_metadata = {}
    if ctx.job.metadata:
        try:
            job_metadata = json.loads(ctx.job.metadata)
            to_number = job_metadata.get("to_number", "Unknown")
            logger.info(f"Extracted to_number from job metadata: {to_number}")
            
            # Update Assistant Prompt and Start Instruction with metadata placeholders {{key}}
            if assistant.assistant_prompt:
                assistant.assistant_prompt = render_prompt(assistant.assistant_prompt, job_metadata)
            
            if assistant.assistant_start_instruction:
                assistant.assistant_start_instruction = render_prompt(assistant.assistant_start_instruction, job_metadata)
            
            logger.info("Successfully processed metadata placeholders in assistant instructions")

        except Exception as e:
            logger.warning(f"Failed to parse job metadata or process placeholders: {e}")

    # Initialize Services per session
    livekit_services = LiveKitService()
    s3_url = None

    # Start Recording
    try:
        recording_info = await livekit_services.start_room_recording(
            room_name=ctx.room.name, 
            assistant_id=assistant_id
        )
        if recording_info and recording_info.get("success"):
            logger.info(f"Recording started: {recording_info}")
            s3_url = recording_info["data"]["s3_url"]
            logger.info(f"S3 URL: {s3_url}")
        else:
            logger.warning(f"Recording start returned failure or empty: {recording_info}")
    except Exception as e:
        logger.error(f"Failed to start recording: {e}", exc_info=True)

    # Initialize Agent Instance
    agent_instance = DynamicAssistant(
        room=ctx.room,
        instructions=assistant.assistant_prompt,
        start_instruction=assistant.assistant_start_instruction
        or "Greet the user Professionally",
    )

    llm = realtime.RealtimeModel(
        model="gpt-realtime",
        input_audio_transcription=AudioTranscription(
            model="gpt-4o-mini-transcribe",
            prompt=(
                "The speaker is multilingual and switches between different languages dynamically. "
                "Transcribe exactly what is spoken without translating."
            ),
        ),
        input_audio_noise_reduction="near_field",
        turn_detection=TurnDetection(
            type="semantic_vad",
            eagerness="low",
            create_response=True,
            interrupt_response=True,
        ),
        modalities=["text"],
        api_key=settings.OPENAI_API_KEY,
    )

    tts = cartesia.TTS(
        model="sonic-3",
        voice=assistant.assistant_tts_voice_id,
        api_key=settings.CARTESIA_API_KEY,
    )

    session = AgentSession(
        llm=llm,
        tts=tts,
        preemptive_generation=True,
        use_tts_aligned_transcript=True,
    )

    # Background audio
    ambient_path = os.path.join(settings.AUDIO_DIR, "office-ambience_48k.wav")
    typing_path = os.path.join(settings.AUDIO_DIR, "typing-sound_48k.wav")

    background_audio = BackgroundAudioPlayer(
        ambient_sound=AudioConfig(ambient_path, volume=0.4),
        thinking_sound=AudioConfig(typing_path, volume=0.5),
    )

    # Configure room options
    room_options = room_io.RoomOptions(
        text_input=False,
        audio_input=True,
        audio_output=True,
        close_on_disconnect=True,
        delete_room_on_close=True,
    )

    # --- TRANSCRIPTION EVENT HANDLERS ---
    @session.on("conversation_item_added")
    def on_conversation_item(event):
        if event.item.text_content:
            # Use to_number from job metadata
            asyncio.create_task(
                livekit_services.add_transcript(
                    room_name=ctx.room.name,
                    speaker=event.item.role,
                    text=event.item.text_content,
                    assistant_id=assistant_id,
                    assistant_name=assistant.assistant_name,
                    to_number=to_number,
                    recording_path=s3_url,
                )
            )

    # --- START SESSION ---
    logger.info("Starting AgentSession...")
    await session.start(agent=agent_instance, room=ctx.room, room_options=room_options)
    logger.info("AgentSession started successfully")

    # WAIT for participant
    logger.info("Waiting for participant...")
    participant = await ctx.wait_for_participant()

    is_sip = participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
    logger.info(f"Participant joined: {participant.identity}, kind={participant.kind}, is_sip={is_sip}")

    # --- Background Audio Start ---
    if background_audio:
        try:
            asyncio.create_task(
                background_audio.start(room=ctx.room, agent_session=session)
            )
            logger.info("Background audio task spawned")
        except Exception as e:
            logger.error(f"Failed to start background audio: {e}")

    # --- Start Instruction ---
    start_instruction = agent_instance.start_instruction
    if start_instruction:
        try:
            await session.generate_reply(instructions=start_instruction)
            logger.info("Start instruction sent successfully")
        except Exception as e:
            logger.error(f"Failed to send start instruction: {e}", exc_info=True)

    # --- WAIT FOR DISCONNECT ---
    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        logger.info(f"Participant disconnected: {participant.identity}")
        # Calculate end time and update record
        asyncio.create_task(livekit_services.end_call(room_name=ctx.room.name, assistant_id=assistant_id))
        logger.info(f"Agent session ended for room: {ctx.room.name}")


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
            ws_url=settings.LIVEKIT_URL,
            job_memory_warn_mb=1024,
            entrypoint_fnc=entrypoint,
            agent_name="api-agent",
        )
    )
