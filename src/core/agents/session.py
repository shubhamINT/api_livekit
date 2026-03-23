from dotenv import load_dotenv
from collections import deque
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
from livekit.plugins import sarvam
from livekit.plugins.openai import realtime
from livekit.agents.beta.tools import EndCallTool
from openai.types.realtime import AudioTranscription
import os
import asyncio
import json
from datetime import datetime, timezone

from src.core.config import settings
from src.core.logger import logger, setup_logging
from src.core.agents.dynamic_assistant import DynamicAssistant
from src.core.agents.inbound_context import resolve_inbound_context
from src.core.agents.utils import render_prompt
from src.core.agents.voice_features import SilenceWatchdogController, FillerController
from src.core.agents.tool_builder import build_tools_from_db
from src.core.db.database import Database
from src.core.db.db_schemas import Assistant, InboundContextStrategy
from src.services.livekit.livekit_svc import LiveKitService
from src.services.elevenlabs.v3_nonstream import ElevenLabsNonStreamingTTS


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
    to_number = "Unknown | Web Call"
    job_metadata = {}
    render_data = {}
    if ctx.job.metadata:
        try:
            job_metadata = json.loads(ctx.job.metadata)
            to_number = job_metadata.get("to_number", "Unknown | Web Call")
            logger.info(f"Extracted to_number from job metadata: {to_number}")
        except Exception as e:
            logger.warning(f"Failed to parse job metadata or process placeholders: {e}")

    if job_metadata:
        # Keep current top-level placeholders working and add namespaced access for new templates.
        render_data = {**job_metadata, "call": job_metadata}

    if job_metadata.get("call_type") == "inbound":
        strategy_id = job_metadata.get("inbound_context_strategy_id")
        if strategy_id:
            strategy = await InboundContextStrategy.find_one(
                InboundContextStrategy.strategy_id == strategy_id,
                InboundContextStrategy.strategy_created_by_email == assistant.assistant_created_by_email,
                InboundContextStrategy.strategy_is_active == True,
            )
            if strategy:
                context = await resolve_inbound_context(
                    strategy=strategy,
                    assistant_id=assistant.assistant_id,
                    assistant_name=assistant.assistant_name,
                    user_email=assistant.assistant_created_by_email,
                    room_name=room_name,
                    job_metadata=job_metadata,
                )
                if context is not None:
                    render_data = {**render_data, "context": context}
            else:
                logger.warning(
                    f"Inbound context strategy '{strategy_id}' not found or inactive; continuing with default prompt"
                )

    # Update Assistant Prompt and Start Instruction with metadata placeholders {{key}}
    if assistant.assistant_prompt:
        assistant.assistant_prompt = render_prompt(assistant.assistant_prompt, render_data)

    if assistant.assistant_start_instruction:
        assistant.assistant_start_instruction = render_prompt(
            assistant.assistant_start_instruction,
            render_data,
        )

    if render_data:
        logger.info("Successfully processed metadata placeholders in assistant instructions")

    interaction_config = assistant.assistant_interaction_config
    filler_words_enabled = bool(interaction_config.filler_words)
    silence_reprompts_enabled = bool(interaction_config.silence_reprompts)

    logger.info(f"Assistant voice features | filler_words={filler_words_enabled} | silence_reprompts={silence_reprompts_enabled}")

    # Initialize Services per session
    livekit_services = LiveKitService()
    s3_url = None
    is_exotel_outbound = job_metadata.get("call_service") == "exotel"
    recording_started = False

    async def _start_recording_once():
        nonlocal s3_url, recording_started
        if recording_started:
            return
        recording_started = True
        max_retries = 2
        for attempt in range(1, max_retries + 1):
            try:
                recording_info = await livekit_services.start_room_recording(
                    room_name=ctx.room.name, 
                    assistant_id=assistant_id
                )
                if recording_info and recording_info.get("success"):
                    recording_data = recording_info.get("data")
                    if isinstance(recording_data, dict):
                        s3_url = recording_data.get("s3_url")
                        logger.info(f"Recording started | S3: {s3_url}")
                    return
                else:
                    logger.warning(f"Recording attempt {attempt}/{max_retries} returned failure: {recording_info}")
            except Exception as e:
                logger.error(f"Recording attempt {attempt}/{max_retries} failed: {e}", exc_info=True)
            if attempt < max_retries:
                await asyncio.sleep(2)
        logger.error("Recording failed after all retries — call will proceed without recording")

    # Keep existing behavior for non-Exotel calls.
    if not is_exotel_outbound:
        asyncio.create_task(_start_recording_once())

    # Load tools attached to this assistant
    tools = []
    if assistant.tool_ids:
        try:
            tools = await build_tools_from_db(
                assistant.tool_ids,
                user_email=assistant.assistant_created_by_email,
                room_name=room_name,
                assistant_id=assistant_id,
            )
            logger.info(f"Loaded {len(tools)} tool(s) for assistant {assistant.assistant_id}")
        except Exception as e:
            logger.error(f"Failed to load tools: {e}", exc_info=True)

    # Built-in EndCallTool support
    if getattr(assistant, "assistant_end_call_enabled", False):
        trigger_phrase = (getattr(assistant, "assistant_end_call_trigger_phrase", None) or "").strip()
        if trigger_phrase:
            extra_description = (
                "Only call this tool after the user clearly says:- "
                f"'{trigger_phrase}'."
            )
        else:
            extra_description = "Only call this tool after the user clearly asks to end the call."

        end_instructions = getattr(assistant, "assistant_end_call_agent_message", None) or "say goodbye to the user"

        try:
            end_call_tool = EndCallTool(
                extra_description=extra_description,
                delete_room=True,
                end_instructions=end_instructions,
            )
            tools.extend(end_call_tool.tools)
            logger.info(f"EndCallTool enabled for assistant {assistant.assistant_id}")
        except Exception as e:
            logger.error(f"Failed to initialize EndCallTool: {e}", exc_info=True)

    # Initialize Agent Instance
    agent_instance = DynamicAssistant(
        room=ctx.room,
        instructions=assistant.assistant_prompt,
        start_instruction=assistant.assistant_start_instruction
        or "Greet the user Professionally",
        tools=tools,
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
            eagerness="high",
            create_response=True,
            interrupt_response=True,
        ),
        modalities=["text"],
        api_key=settings.OPENAI_API_KEY,
    )

    # Check between cartesia and sarvam
    tts_config = assistant.assistant_tts_config or {}
    tts = None
    
    if assistant.assistant_tts_model == "cartesia":
        voice_id = tts_config.get("voice_id")
        if not voice_id:
             logger.error(f"Missing voice_id for Cartesia assistant {assistant.assistant_id}")
             return

        # Check api key present
        api_key=tts_config.get("api_key")
        if not api_key:
            api_key=settings.CARTESIA_API_KEY

        tts = cartesia.TTS(
            model="sonic-3",
            speed=1.1,
            voice=voice_id,
            api_key=api_key,
        )
    elif assistant.assistant_tts_model == "sarvam":
        speaker = tts_config.get("speaker")
        if not speaker:
             logger.error(f"Missing speaker for Sarvam assistant {assistant.assistant_id}")
             return
        
        # Check api key present
        api_key=tts_config.get("api_key")
        if not api_key:
            api_key=settings.SARVAM_API_KEY

        tts = sarvam.TTS(
            model="bulbul:v3",
            pace=1.1,
            target_language_code=tts_config.get("target_language_code", "en-IN"),
            speaker=speaker,
            api_key=api_key,
        )
    elif assistant.assistant_tts_model == "elevenlabs":
        voice_id = tts_config.get("voice_id")
        if not voice_id:
             logger.error(f"Missing voice_id for ElevenLabs assistant {assistant.assistant_id}")
             return

        # Check api key present
        api_key=tts_config.get("api_key")
        if not api_key:
            api_key=settings.ELEVENLABS_API_KEY

        tts = ElevenLabsNonStreamingTTS(
            model="eleven_v3",
            voice_id=voice_id,
            api_key=api_key
        )
    else:
        logger.error(f"Unsupported TTS model for assistant {assistant.assistant_id}")
        return

    session = AgentSession(
        llm=llm,
        tts=tts,
        preemptive_generation=True,
        use_tts_aligned_transcript=True,
    )

    context_turns = deque(maxlen=4)
    user_is_speaking = False
    silence_watchdog = (
        SilenceWatchdogController(
            session=session, 
            logger=logger,
            reprompt_interval_sec=interaction_config.silence_reprompt_interval,
            max_reprompts=interaction_config.silence_max_reprompts
        ) if silence_reprompts_enabled else None
    )
    filler_controller = FillerController(session=session, context_turns=context_turns) if filler_words_enabled else None

    # Background audio
    ambient_path = os.path.join(settings.AUDIO_DIR, "office-ambience_48k.wav")
    typing_path = os.path.join(settings.AUDIO_DIR, "typing-sound_48k.wav")

    background_audio = BackgroundAudioPlayer(
        ambient_sound=AudioConfig(ambient_path, volume=0.4),
        thinking_sound=AudioConfig(typing_path, volume=0.5),
    )

    # Enable text input only for web calls; keep SIP/inbound voice behavior unchanged.
    is_web_call = job_metadata.get("call_type") == "web"
    logger.info(f"Session input mode | call_type={job_metadata.get('call_type')} | text_input={is_web_call}")

    # Configure room options
    room_options = room_io.RoomOptions(
        text_input=is_web_call,
        audio_input=True,
        audio_output=True,
        close_on_disconnect=False, # Imp or else it will not send the the details of call end to the call end url
        delete_room_on_close=False,
    )

    # --- TRANSCRIPTION EVENT HANDLERS ---
    @session.on("conversation_item_added")
    def on_conversation_item(event):
        if event.item.text_content:
            if filler_words_enabled and event.item.role in ("user", "assistant"):
                context_turns.append({"role": event.item.role, "text": event.item.text_content})

            if silence_watchdog and event.item.role == "user":
                silence_watchdog.on_user_message()

            if silence_watchdog and event.item.role == "assistant" and not user_is_speaking:
                silence_watchdog.on_assistant_message(event.item.text_content)

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

    if filler_words_enabled or silence_reprompts_enabled:
        @session.on("user_state_changed")
        def on_user_state_changed(event):
            nonlocal user_is_speaking
            is_speaking = event.new_state == "speaking"
            user_is_speaking = is_speaking

            if silence_watchdog:
                silence_watchdog.on_user_state_changed(is_speaking)

            if filler_controller:
                if is_speaking:
                    filler_controller.start()
                else:
                    filler_controller.stop()

    # --- EVENT TRACKING FOR CALL ANSWERED ---
    # We register `data_received` EARLY (before wait_for_participant) so we never
    # miss the call_answered signal from the Exotel bridge, even if it connects
    # while the agent is still booting up (common in inbound calls).
    audio_ready = asyncio.Event()

    @ctx.room.on("data_received")
    def on_data_received(data: rtc.DataPacket):
        if data.topic == "sip_bridge_events":
            try:
                msg = json.loads(data.data.decode())
                if msg.get("event") == "call_answered":
                    logger.info("Bridge reported call answered via data message (SIP 200 OK)")
                    audio_ready.set()
                    if is_exotel_outbound:
                        asyncio.create_task(_start_recording_once())
                        asyncio.create_task(
                            livekit_services.update_call_status(
                                room_name=ctx.room.name,
                                call_status="answered",
                                call_status_reason=None,
                                answered_at=datetime.now(timezone.utc),
                            )
                        )
            except (json.JSONDecodeError, TypeError):
                pass

    # WAIT for participant
    logger.info("Waiting for participant...")
    participant = await ctx.wait_for_participant()

    # Check for sip participant
    is_sip = participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP

    # Also detect Exotel bridge participants (join as sip participants)
    is_exotel_bridge = False
    if participant.metadata:    
        try:
            meta = json.loads(participant.metadata)
            is_exotel_bridge = meta.get("source") == "exotel_bridge"
        except (json.JSONDecodeError, TypeError):
            pass

    logger.info(
        f"Participant joined: {participant.identity} | "
        f"kind={participant.kind} | "
        f"is_sip={is_sip} | "
        f"is_exotel_bridge={is_exotel_bridge}"
    )

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
    # Respect the assistant_speaks_first flag (defaults True for backward compatibility).
    # When False, the assistant stays silent on connect and waits for the user to speak first.
    should_speak_first = interaction_config.speaks_first

    if should_speak_first:
        start_instruction = agent_instance.start_instruction
        if start_instruction:
            try:
                # For Exotel bridge: wait for the explicit call_answered signal before speaking.
                # The bridge publishes this event AFTER 200 OK is confirmed, meaning the user
                # has actually picked up and the RTP path is open.
                if is_exotel_bridge:
                    logger.info("Exotel bridge detected — waiting for call_answered event before speaking")
                    try:
                        await asyncio.wait_for(audio_ready.wait(), timeout=60.0)
                        logger.info("[EXOTEL] call_answered confirmed — sleeping 0.5s for RTP stabilization")
                        await asyncio.sleep(0.5)
                    except asyncio.TimeoutError:
                        logger.warning("[EXOTEL] Timed out waiting for call_answered — proceeding anyway")

                await session.generate_reply(instructions=start_instruction)
                if silence_watchdog:
                    silence_watchdog.on_assistant_message(start_instruction)
                logger.info("Start instruction sent successfully")
            except Exception as e:
                logger.error(f"Failed to send start instruction: {e}", exc_info=True)
    else:
        logger.info(
            "assistant_speaks_first=False — skipping start instruction; "
            "assistant is silent and waiting for the user to speak first"
        )

    # --- WAIT FOR DISCONNECT ---
    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        if filler_controller:
            filler_controller.stop()
        if silence_watchdog:
            silence_watchdog.stop()
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
            num_idle_processes=2,
        )
    )
