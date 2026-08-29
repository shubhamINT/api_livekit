from dotenv import load_dotenv
from collections import deque
from livekit import rtc
from livekit.agents import (
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
    inference,
    room_io,
    BackgroundAudioPlayer,
    AudioConfig,
    function_tool,
    RunContext,
    TurnHandlingOptions,
    NOT_GIVEN,
)
from openai.types.beta.realtime.session import TurnDetection
from livekit.plugins import sarvam as sarvam_plugin
from livekit.plugins.openai import realtime
from livekit.plugins.google import realtime as google_realtime
from openai.types.realtime import AudioTranscription
from openai.types.realtime.realtime_truncation_retention_ratio import (
    RealtimeTruncationRetentionRatio,
    TokenLimits,
)
import os
import asyncio
import json
from datetime import datetime, timezone

from src.core.config import settings
from src.core.logger import logger, setup_logging, set_room_context
from src.core.agents.audio_denoise import SpeechGate
from src.core.agents.dynamic_assistant import DynamicAssistant
from src.core.agents.inbound_context import log_missing_strategy, resolve_inbound_context
from src.core.agents.session_lifecycle import CallReadinessGate, RecordingManager
from src.core.agents.llm import DEFAULT_MODEL as DEFAULT_CASCADE_LLM_MODEL, create_llm
from src.core.model_support.capabilities import (
    DEFAULT_GEMINI_LIVE_MODEL,
    DEFAULT_GEMINI_VOICE,
    DEFAULT_REALTIME_MODEL,
    GEMINI_NO_MIDSESSION_CONTENT_MODELS,
    realtime_supports_truncation,
)
from src.core.agents.tts import create_tts, maintain_sarvam_connection
from src.core.agents.stt import (
    FinalCoalescer,
    create_stt,
    build_native_stt_prompt,
    noise_reduction_for,
    resolve_stt,
    run_sarvam_parallel_stt,
)
from src.core.agents.usage import summarize_usage
from src.core.agents.utils import render_prompt
from src.core.agents.voice_features import SilenceWatchdogController, FillerController, HoldController, InputGuardController
from src.core.agents.tool_builder import build_tools_from_db
from src.core.db.database import Database
from src.core.providers.keys import provider_key_or_system
from src.core.db.db_schemas import Assistant, AudioAsset, InboundContextStrategy, UsageRecord, CallRecord
from src.services.livekit.livekit_svc import LiveKitService
from src.services.storage import s3_audio
from livekit.agents.utils.audio import audio_frames_from_file


setup_logging()
load_dotenv(override=True)

# Platform default applied when assistant_interaction_config.max_call_duration_minutes is unset.
DEFAULT_MAX_CALL_DURATION_MINUTES = 30.0

# How long teardown keeps the transcript path open after the caller's audio stops, so the
# last utterance can come back from whichever STT owns it. Everything after it — the queue
# join, the usage record and the end-of-call webhook — is delayed by this much.
END_OF_CALL_GRACE_S = 4.0

# Fixed pause after call_answered before the greeting is sent, to let the RTP mixer and
# egress recording finish settling. Was 2.0s (unconditional, on every Exotel call — a
# real chunk of the reported 5-6s first-speech latency). Lowered as a starting point;
# NOT verified against a live call — listen to the first ~2s of a real Exotel greeting
# after this change and put it back up if the opening word sounds clipped or garbled.
EXOTEL_RTP_WARMUP_SLEEP_SEC = 1.0


def should_record(role: str | None, *, on_hold: bool, gate_active: bool) -> bool:
    """Whether a conversation item belongs in the stored transcript.

    Hold and the pre-answer readiness gate exist to keep the *agent* quiet and out of the
    record. They must never suppress the caller: `gate_active` flips on a single
    `call_answered` SIP packet, so gating user speech on it meant one dropped packet
    discarded every transcript for the whole call, silently. The Sarvam tap already bypasses
    both checks, so this also keeps the two STT paths behaving the same.
    """
    if role == "user":
        return True
    return gate_active and not on_hold


# Helper to build background audio player based on interaction config
def build_background_audio(interaction_config) -> BackgroundAudioPlayer | None:
    ambient_sound = None
    if getattr(interaction_config, "background_sound_enabled", True):
        ambient_path = os.path.join(settings.AUDIO_DIR, "office-ambience_48k.wav")
        ambient_sound = AudioConfig(ambient_path, volume=0.6)

    thinking_sound = None
    if getattr(interaction_config, "thinking_sound_enabled", True):
        typing_path = os.path.join(settings.AUDIO_DIR, "typing-sound_48k.wav")
        thinking_sound = AudioConfig(typing_path, volume=0.7)

    if ambient_sound is None and thinking_sound is None:
        return None

    return BackgroundAudioPlayer(
        ambient_sound=ambient_sound,
        thinking_sound=thinking_sound,
    )


# Looks up the audio asset and downloads it from S3 — the two slow, network-bound steps of
# playing a prerecorded greeting. Split out so entrypoint() can start this the moment the
# assistant loads, well before the greeting is actually needed, instead of paying for it
# cold at greeting time.
async def _prefetch_greeting_audio(audio_id: str) -> tuple[str, str] | None:
    asset = await AudioAsset.find_one(
        AudioAsset.audio_id == audio_id,
        AudioAsset.is_active == True,
    )
    if not asset:
        logger.warning("Greeting audio_id %s not found or inactive; using model greeting", audio_id)
        return None
    try:
        tmp_path = await asyncio.to_thread(s3_audio.download_to_tempfile, asset.s3_key)
    except Exception as e:
        logger.error(f"Greeting audio download failed, falling back to model greeting: {e}", exc_info=True)
        return None
    # transcript goes to the chat context so the model knows it already greeted
    return asset.transcript or "", tmp_path


# Play a referenced audio asset as the greeting instead of generating it with the model.
# Returns the spoken transcript on success, or None so the caller falls back to the model greeting.
async def play_prerecorded_greeting(
    session, audio_id, allow_interruptions, prefetch: asyncio.Task | None = None,
) -> str | None:
    # Use the in-flight prefetch task if entrypoint() started one; otherwise fetch cold
    # (keeps this function usable on its own).
    result = await prefetch if prefetch is not None else await _prefetch_greeting_audio(audio_id)
    if result is None:
        return None
    transcript, tmp_path = result
    try:
        handle = session.say(
            transcript,
            audio=audio_frames_from_file(tmp_path, sample_rate=48000, num_channels=1),
            allow_interruptions=allow_interruptions,
            add_to_chat_ctx=True,
        )
        # wait for playout: the file is streamed lazily, so keep it until reading finishes
        await handle.wait_for_playout()
        logger.info("Start instruction strategy | mode=prerecorded_greeting_audio | audio=%s", audio_id)
        return transcript
    except Exception as e:
        logger.error(f"Prerecorded greeting failed, falling back to model greeting: {e}", exc_info=True)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)


async def entrypoint(ctx: JobContext):
    # Ensure database connection
    try:
        await Database.connect_db()
    except Exception as e:
        logger.error(f"Failed to connect to database in worker: {e}")
        return

    # Retrieve agent ID from room name
    room_name = ctx.room.name
    assistant_id = room_name.split("_", 1)[0]
    set_room_context(room_name)
    logger.info(f"Agent session starting | room: {room_name} | identifier: {assistant_id}")

    # Fetch assistant from DB
    assistant = await Assistant.find_one(Assistant.assistant_id == assistant_id)
    if not assistant:
        logger.error(f"No assistant found for identifier: {assistant_id}")
        return

    # Kick off the prerecorded-greeting lookup + S3 download now, in parallel with the rest
    # of session setup below, instead of starting it cold once we're actually about to speak
    # (previously the single biggest avoidable chunk of first-speech latency for assistants
    # using a greeting audio asset). Harmless if the greeting path below never uses it.
    _greeting_prefetch_task = None
    _greeting_cfg = assistant.assistant_greeting_audio
    if _greeting_cfg and _greeting_cfg.enabled and _greeting_cfg.audio_id:
        _greeting_prefetch_task = asyncio.create_task(_prefetch_greeting_audio(_greeting_cfg.audio_id))

    logger.info(f"Loaded assistant config: {assistant.assistant_name} (ID: {assistant.assistant_id})")
    # Three modes, one discriminator each. "pipeline" (half-cascade) is the implicit
    # third case: a realtime model emitting text, spoken by an external TTS.
    #   realtime — one model does STT + LLM + TTS (audio out)
    #   cascade  — a true pipeline: plugin STT -> plain LLM -> plugin TTS
    #   pipeline — realtime model emits text, external TTS speaks it
    _mode = assistant.assistant_mode
    is_realtime = _mode == "realtime"
    is_cascade = _mode == "cascade"
    # assistant_mode is a plain string in the DB (see src/core/db/db_schemas.py), so a row
    # written outside the API can hold anything. Anything unrecognised lands in the pipeline
    # branch below; say so rather than letting it look intentional.
    if _mode not in {"pipeline", "realtime", "cascade"}:
        logger.warning(
            f"Unknown assistant_mode '{_mode}' — treating as 'pipeline'. "
            "Valid values are 'pipeline', 'realtime' and 'cascade'."
        )

    # Extract metadata from job metadata
    to_number = "Web Call"
    job_metadata = {}
    render_data = {}
    if ctx.job.metadata:
        try:
            job_metadata = json.loads(ctx.job.metadata)
            to_number = job_metadata.get("to_number", "Web Call")
            logger.info(f"Extracted to_number from job metadata: {to_number}")
        except Exception as e:
            logger.warning(f"Failed to parse job metadata or process placeholders: {e}")

    # Text-only web chat: skip STT, TTS, recording. Validated upstream against realtime mode.
    is_web_call = job_metadata.get("call_type") == "web"
    is_text_only = is_web_call and job_metadata.get("text_only") is True

    if job_metadata:
        render_data = {**job_metadata, "call": job_metadata}

    # Resolve inbound context if applicable
    if job_metadata.get("call_type") == "inbound":
        strategy_id = job_metadata.get("inbound_context_strategy_id")
        if strategy_id:
            strategy = await InboundContextStrategy.find_one(
                InboundContextStrategy.strategy_id == strategy_id,
                InboundContextStrategy.strategy_created_by_email == assistant.assistant_created_by_email,
                InboundContextStrategy.strategy_is_active == True,
            )
            if strategy:
                # Best-effort by contract: nothing this lookup can do — a bad stored
                # config, a Mongo hiccup — may be allowed to abort the entrypoint and
                # drop the call.
                try:
                    context_data = await resolve_inbound_context(
                        strategy=strategy,
                        assistant_id=assistant.assistant_id,
                        assistant_name=assistant.assistant_name,
                        user_email=assistant.assistant_created_by_email,
                        room_name=room_name,
                        job_metadata=job_metadata,
                    )
                except Exception as e:
                    logger.warning(
                        f"Inbound context lookup raised for strategy '{strategy_id}': {e}; continuing with default prompt"
                    )
                    context_data = None
                if context_data is not None:
                    # Spread flat, exactly like job_metadata above: the webhook's own
                    # response shape is the placeholder path. Merged last, so a webhook
                    # key wins a bare-name collision; {{call.*}} still holds the
                    # platform value.
                    render_data = {**render_data, **context_data}
            else:
                logger.warning(
                    f"Inbound context strategy '{strategy_id}' not found or inactive; continuing with default prompt"
                )
                try:
                    await log_missing_strategy(
                        user_email=assistant.assistant_created_by_email,
                        assistant_id=assistant.assistant_id,
                        room_name=room_name,
                        strategy_id=strategy_id,
                    )
                except Exception as e:
                    logger.warning(f"Failed to log missing inbound context strategy: {e}")

    # Render metadata placeholders in prompts
    if assistant.assistant_prompt:
        assistant.assistant_prompt = render_prompt(assistant.assistant_prompt, render_data)
    if assistant.assistant_start_instruction:
        assistant.assistant_start_instruction = render_prompt(
            assistant.assistant_start_instruction, render_data,
        )
    if render_data:
        logger.info("Successfully processed metadata placeholders in assistant instructions")


    interaction_config = assistant.assistant_interaction_config
    # Filler words require external TTS (session.say), disabled in realtime mode.
    # Voice-only features (filler, silence reprompts, background/thinking sounds) all
    # off for text-only chats — no audio in or out.
    filler_words_enabled = bool(interaction_config.filler_words) and not is_realtime and not is_text_only
    silence_reprompts_enabled = bool(interaction_config.silence_reprompts) and not is_text_only
    background_sound_enabled = bool(getattr(interaction_config, "background_sound_enabled", True)) and not is_text_only
    thinking_sound_enabled = bool(getattr(interaction_config, "thinking_sound_enabled", True)) and not is_text_only
    logger.info(
        "Assistant voice features | "
        f"filler_words={filler_words_enabled} | "
        f"silence_reprompts={silence_reprompts_enabled} | "
        f"background_sound={background_sound_enabled} | "
        f"thinking_sound={thinking_sound_enabled} | "
        f"mode={_mode}"
    )

    # --- Call Readiness & Recording ---
    is_exotel_outbound = job_metadata.get("call_service") == "exotel"
    livekit_services = LiveKitService()
    gate = CallReadinessGate(is_exotel_outbound)
    recorder = RecordingManager(livekit_services, room_name, assistant_id)

    # Bounded queue serializes transcript DB writes off the audio hot path.
    # put_nowait on the event handler never blocks; single consumer drains async.
    _transcript_queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    async def _transcript_worker():
        while True:
            fn = await _transcript_queue.get()
            try:
                await fn()
            except Exception as e:
                logger.error(f"Transcript write failed | room={room_name}: {e}")
            finally:
                _transcript_queue.task_done()

    transcript_worker = asyncio.create_task(_transcript_worker())

    # Start recording immediately for non-Exotel calls. Text-only web chats have no audio.
    if not is_exotel_outbound and not is_text_only:
        asyncio.create_task(recorder.start_once())

    # --- Load Tools ---
    tools = []
    if assistant.tool_ids:
        try:
            tools = await build_tools_from_db(
                assistant.tool_ids,
                user_email=assistant.assistant_created_by_email,
                room_name=room_name,
                assistant_id=assistant_id,
                # Only cascade talks to the Responses API, which is where `strict` on a
                # function tool means anything. The Realtime API has no such field and
                # errors on the unknown key.
                strict_schemas=is_cascade,
            )
            logger.info(f"Loaded {len(tools)} tool(s) for assistant {assistant.assistant_id}")
        except Exception as e:
            logger.error(f"Failed to load tools: {e}", exc_info=True)

    # Persist usage metrics at call end
    async def _persist_usage():
        try:
            metered = summarize_usage(session)
            telephony_provider = job_metadata.get("call_service") or job_metadata.get("service")
            if job_metadata.get("call_type") == "web":
                telephony_provider = None

            # Compute call duration from CallRecord
            call_duration = 0.0
            call_record = await CallRecord.find_one(CallRecord.room_name == room_name)
            if call_record:
                ended_at = datetime.now(timezone.utc)
                duration_start = call_record.answered_at or call_record.started_at
                call_duration = (ended_at - duration_start).total_seconds() / 60

            # LLM vendor, recorded for all modes. Resolved once at model build (see below).
            llm_realtime_provider = realtime_provider

            usage = UsageRecord(
                room_name=room_name,
                assistant_id=assistant_id,
                user_email=assistant.assistant_created_by_email,
                mode=assistant.assistant_mode,
                llm_realtime_provider=llm_realtime_provider,
                tts_provider=assistant.assistant_tts_model if not is_realtime else None,
                # Only cascade has a standalone STT stage worth attributing cost to; the
                # other modes transcribe inside the LLM, so the spend is in its tokens.
                stt_provider=(assistant.assistant_stt_model or "sarvam") if is_cascade else None,
                call_service=telephony_provider,
                call_duration_minutes=call_duration,
                **metered,
            )
            await usage.insert()
            logger.info(
                f"Usage persisted | room={room_name} | mode={usage.mode} | "
                f"llm_tokens={usage.llm_total_tokens} | "
                f"tts_chars={usage.tts_characters_count} | "
                f"stt_audio={usage.stt_audio_duration:.1f}s"
            )
        except Exception as e:
            logger.error(f"Failed to persist usage record: {e}", exc_info=True)

    _sarvam_stop = asyncio.Event()
    _sarvam_task: asyncio.Task | None = None
    # Assigned below, once _enqueue_transcript exists. Declared here because teardown reads it.
    _user_coalescer: FinalCoalescer | None = None

    # Watchdog/tools stamp a reason before teardown persists it.
    _end_reason: str = "natural"
    _max_duration_task: asyncio.Task | None = None
    _teardown_started: bool = False
    # Declared here, not after wait_for_participant: the conversation_item_added handler
    # closes over it and can fire before a participant has joined.
    call_end_triggered: bool = False
    # Separate from call_end_triggered on purpose. That flag guards duplicate teardown and
    # must be set the instant a hangup is seen; this one closes the transcript path and is
    # set only once Sarvam has handed over the caller's last utterance.
    _transcripts_closed: bool = False

    # Single teardown path used by both EndCallTool and participant disconnect
    async def _flush_and_end_call(delay: float = 0.0):
        nonlocal call_end_triggered, _teardown_started, _transcripts_closed
        if _teardown_started:  # ponytail: idempotency guard, single teardown per call
            return
        _teardown_started = True
        call_end_triggered = True  # Block duplicate from disconnect handler
        _sarvam_stop.set()
        # Never on the max-duration path: the watchdog calls this teardown itself, so there
        # _max_duration_task is the task running these very lines. Cancelling it killed
        # teardown at the next await and the watchdog's own `except CancelledError: pass`
        # swallowed it — no transcripts, no usage record, no webhook, no delete_room, silently.
        if (
            _max_duration_task is not None
            and _max_duration_task is not asyncio.current_task()
            and not _max_duration_task.done()
        ):
            _max_duration_task.cancel()
        if input_guard is not None:
            await input_guard.aclose()
        # Started at assistant-load time; harmless if it finished, but cancel if the call
        # ended before the greeting path ever awaited it (e.g. speaks_first=False).
        if _greeting_prefetch_task is not None and not _greeting_prefetch_task.done():
            _greeting_prefetch_task.cancel()
        # Mute all room audio inputs immediately — prevents STT from
        # processing any new speech during the TTS playout delay window
        # await livekit_services.mute_room_audio_inputs(ctx.room.name)
        if delay > 0:
            await asyncio.sleep(delay)  # Let TTS audio finish streaming to egress
        # The caller's last utterance comes back *after* their audio has stopped, on both STT
        # paths: Sarvam needs a network round-trip, and the realtime model has to transcribe
        # the audio it is still holding. Ask each to finalize, then hold the transcript path
        # open for one fixed window. Both feed the same _user_coalescer, so one flush at the
        # end catches whichever produced text and no per-path bookkeeping is needed.
        # _sarvam_stop was set above; the tap drains and keeps feeding the coalescer here.
        if not is_text_only:
            if _sarvam_task is None:
                # Native: commit_user_turn sends input_audio_buffer.commit so the model
                # transcribes the audio it holds and fires one more conversation_item_added.
                # skip_reply stops it answering a caller who has already hung up. Not awaited:
                # the future it returns resolves immediately in realtime mode (no separate STT
                # — see agents/voice/audio_recognition.py::commit_user_turn), so awaiting it
                # gives no grace at all; the sleep below is the grace. No-op on Gemini, whose
                # plugin logs commit_audio as unsupported and only finalizes on turn_complete,
                # which a mid-turn hangup never reaches.
                # In cascade the session owns a real STT stage, so this future resolves
                # when that STT actually flushes instead of immediately — await it and
                # stop waiting the moment the tail lands, capped by the same window.
                try:
                    _commit = session.commit_user_turn(skip_reply=True)
                    if is_cascade:
                        await asyncio.wait_for(
                            asyncio.shield(_commit), timeout=END_OF_CALL_GRACE_S
                        )
                except asyncio.TimeoutError:
                    logger.warning("Final user turn did not finalize before the grace window")
                except Exception as e:
                    logger.warning(f"Could not commit final user turn: {e}")
            if not is_cascade:
                await asyncio.sleep(END_OF_CALL_GRACE_S)
        if _user_coalescer is not None:
            _user_coalescer.flush()
        # No new transcripts past this point, so the queue below can be joined.
        _transcripts_closed = True
        # Drain transcript queue before ending (max 3s).
        try:
            await asyncio.wait_for(_transcript_queue.join(), timeout=3.0)
        except asyncio.TimeoutError:
            logger.warning("Timed out waiting for pending transcripts")
        transcript_worker.cancel()
        await asyncio.gather(transcript_worker, return_exceptions=True)
        await _persist_usage()
        try:
            rec = await CallRecord.find_one(CallRecord.room_name == ctx.room.name)
            if rec and rec.call_end_reason is None:
                rec.call_end_reason = _end_reason
                await rec.save()
        except Exception as e:
            logger.error(f"Failed to persist call_end_reason: {e}")
        try:
            await livekit_services.end_call(room_name=ctx.room.name, assistant_id=assistant_id)
        except Exception as e:
            logger.error(f"end_call failed — call may stay stuck in 'answered' | room={ctx.room.name}: {e}", exc_info=True)
        try:
            await livekit_services.delete_room(room_name=ctx.room.name)
        except Exception as e:
            logger.error(f"delete_room failed | room={ctx.room.name}: {e}")

    # Custom end_call tool — LLM speaks goodbye first, tool waits for playout before stopping recording
    if getattr(assistant, "assistant_end_call_enabled", False):
        trigger_phrase = (getattr(assistant, "assistant_end_call_trigger_phrase", None) or "").strip()
        agent_message = (getattr(assistant, "assistant_end_call_agent_message", None) or "Thank you, goodbye!").strip()

        trigger_condition = (
            f"Call this as soon as the user signals they want to end or finish the call — "
            f"in ANY language, dialect, or wording, including partial, misspelled, or accented "
            f"speech. Do not require an exact phrase. Example of such intent: '{trigger_phrase}'."
            if trigger_phrase else
            "Call this as soon as the user signals they want to end or finish the call, "
            "in any language or wording."
        )
        tool_description = f"End the current call. {trigger_condition}"

        @function_tool(description=tool_description)
        async def end_call(_ctx: RunContext):
            """Wait for the LLM's goodbye reply to actually finish playing, then end the call."""
            async def _end_after_goodbye():
                # Two different shapes, so two paths:
                #
                # Realtime models emit the goodbye as a NEW speech handle after the tool
                # returns, so this callback fires *before* it is spoken — catch that handle
                # via speech_created, then wait for real playout. Mirrors
                # livekit.agents.beta EndCallTool._delayed_session_shutdown.
                #
                # A cascade (non-realtime) LLM continues in the SAME speech handle across
                # tool steps (agent_activity._pipeline_reply_task_impl passes
                # speech_handle=speech_handle back in), and a handle is only marked done
                # once all its tasks finish. So by the time this callback runs the goodbye
                # has already played, and waiting for a second speech_created would just
                # burn the full timeout as dead air before hangup.
                if not is_cascade:
                    fut: asyncio.Future = asyncio.Future()

                    @session.once("speech_created")
                    def _on_created(ev):
                        if not fut.done():
                            fut.set_result(ev.speech_handle)

                    try:
                        handle = await asyncio.wait_for(fut, timeout=5.0)
                        await handle.wait_for_playout()
                    except asyncio.TimeoutError:
                        logger.warning("end_call goodbye reply timed out; ending anyway")
                    finally:
                        session.off("speech_created", _on_created)
                # small buffer for egress to finalize the tail, then teardown
                await _flush_and_end_call(delay=1.0)

            _ctx.speech_handle.add_done_callback(
                lambda _: asyncio.create_task(_end_after_goodbye())
            )
            return f"Say this to the user: '{agent_message}'"

        tools.append(end_call)
        logger.info(f"Custom end_call tool enabled for assistant {assistant.assistant_id}")

        # System-prompt directive is the strong trigger signal (tool description alone is weak).
        # Intent-based + multilingual so the model fires on approximate/other-language speech.
        _phrase_hint = f' For example, when the user says something like "{trigger_phrase}".' if trigger_phrase else ""
        assistant.assistant_prompt = (assistant.assistant_prompt or "") + (
            "\n\n---\nENDING THE CALL:\n"
            "You have an `end_call` tool. Call it the moment the user shows they want to "
            "end, finish, or hang up the call — in ANY language or wording, even if their "
            "words are partial, misspelled, mispronounced, or only roughly match."
            f"{_phrase_hint} "
            "Do not wait for an exact phrase and do not ask for confirmation. "
            "After calling it, speak the goodbye it gives you, then stop.\n---"
        )

    # --- Build Agent & LLM ---
    agent_instance = DynamicAssistant(
        room=ctx.room,
        instructions=assistant.assistant_prompt,
        start_instruction=assistant.assistant_start_instruction or "Greet the user Professionally",
        tools=tools,
    )

    # LLM vendor is orthogonal to mode. `is_realtime` = model speaks its own audio
    # (no external TTS); provider = which vendor. Default per mode keeps old assistants working.
    llm_config = assistant.assistant_llm_config or {}
    _default_provider = "gemini" if is_realtime else "openai"
    realtime_provider = (llm_config.get("provider") or _default_provider).lower()
    # Set inside the half-cascade branches when Sarvam parallel STT is active.
    _use_sarvam_stt = False
    _stt_provider, _stt_config = resolve_stt(assistant)

    # Shared by both modes: whenever the LLM does its own transcription it gets the same
    # prompt and the same phone-tuned noise reduction. Full realtime used to pass neither
    # and silently fell back to gpt-4o-mini-transcribe with no instructions at all.
    # The model stays mini deliberately. What was actually missing was the prompt and
    # far_field, not model size, and mini takes both — so the fix costs nothing per minute.
    # Swap to "gpt-4o-transcribe" if Indic accuracy is ever measured to justify the price.
    _is_phone_call = job_metadata.get("call_type") != "web"
    _noise_reduction = noise_reduction_for(_is_phone_call)
    _stt_prompt = build_native_stt_prompt(
        interaction_config.preferred_languages, is_phone_call=_is_phone_call
    )
    _native_transcription = AudioTranscription(model="gpt-4o-mini-transcribe", prompt=_stt_prompt)

    # Shared by the two OpenAI realtime branches (full realtime and half-cascade). The default
    # lives in model_support so the API validates the model this line will actually pick.
    _openai_realtime_model = llm_config.get("model") or DEFAULT_REALTIME_MODEL
    # `session.truncation` is a GA Realtime API field. The older gpt-4o-*realtime-preview
    # models — still on the allowlist, so still reachable — do not carry it in their session
    # shape, and an unknown session field comes back as an error event rather than being
    # ignored. None omits the field entirely (the plugin only sends it when non-None).
    _realtime_truncation = (
        RealtimeTruncationRetentionRatio(
            type="retention_ratio",
            retention_ratio=0.75,
            token_limits=TokenLimits(post_instructions=8000),
        )
        if realtime_supports_truncation(_openai_realtime_model)
        else None
    )
    if _realtime_truncation is None and not is_cascade and realtime_provider == "openai":
        logger.info(
            "Realtime model %s predates session.truncation — running without it "
            "(context is truncated by the API's own default instead).",
            _openai_realtime_model,
        )

    # Set in the cascade branch only: the plugin STT that becomes the session's own
    # first stage. The other two modes leave it None (their LLM owns transcription).
    cascade_stt = None

    if is_cascade:
        # True pipeline: three independent stages, each separately metered and swappable.
        # Nothing here is a RealtimeModel, so there is no server-side VAD and no
        # self-transcription — turn detection and STT are the session's own job.
        # has_tools decides one knob the LLM cannot be built without knowing: gpt-5.2 and
        # gpt-5.4* reject reasoning.effort while function tools are attached. `tools` is
        # complete by here — DB tools loaded above, end_call appended with them.
        llm = create_llm(assistant, has_tools=bool(tools))
        if llm is None:
            return
        if not is_text_only:
            cascade_stt = create_stt(assistant)
            if cascade_stt is None:
                return
        logger.info(
            "Cascade mode | stt=%s | llm=%s/%s | tts=%s",
            assistant.assistant_stt_model or "sarvam",
            realtime_provider,
            llm_config.get("model") or DEFAULT_CASCADE_LLM_MODEL,
            assistant.assistant_tts_model,
        )
    elif is_realtime:
        # Full realtime mode: single model handles STT + LLM + TTS (audio out).
        if realtime_provider == "gemini":
            _gemini_model = llm_config.get("model") or DEFAULT_GEMINI_LIVE_MODEL
            # The 3.1 Live model answers `send_client_content` with a 1007 close after the
            # first model turn, so `generate_reply()` is ignored from then on. Two features
            # here go through it: the max-duration farewell and the silence re-prompt. The
            # greeting is unaffected — it is sent as realtime *input*, not client content.
            # Not a rejection, because everything else about the model works; a log line
            # instead, so the missing farewell is traceable to a choice rather than a bug.
            # https://docs.livekit.io/agents/models/realtime/plugins/gemini/#gemini-3-1-compatibility
            if _gemini_model in GEMINI_NO_MIDSESSION_CONTENT_MODELS:
                logger.warning(
                    "Gemini Live model %s ignores generate_reply() after the first turn — the "
                    "max-duration farewell and silence re-prompts will not be spoken on this "
                    "call. Use %s to keep them.",
                    _gemini_model,
                    DEFAULT_GEMINI_LIVE_MODEL,
                )
            llm = google_realtime.RealtimeModel(
                model=_gemini_model,
                voice=llm_config.get("voice") or DEFAULT_GEMINI_VOICE,
                modalities=["AUDIO"],
                instructions=assistant.assistant_prompt,
                api_key=llm_config.get("api_key") or settings.GOOGLE_API_KEY,
            )
        elif realtime_provider == "openai":
            llm = realtime.RealtimeModel(
                model=_openai_realtime_model,
                voice=llm_config.get("voice", "marin"),
                modalities=["audio"],
                # Sarvam never runs in full realtime mode, so the model always transcribes.
                input_audio_transcription=_native_transcription,
                input_audio_noise_reduction=_noise_reduction,
                turn_detection=TurnDetection(
                    type="semantic_vad",
                    eagerness="high",
                    create_response=True,
                    interrupt_response=False,
                ),
                truncation=_realtime_truncation,
                api_key=llm_config.get("api_key") or settings.OPENAI_API_KEY,
            )
        else:
            logger.error(f"Unsupported realtime provider: {realtime_provider}")
            return

        logger.info(f"Realtime mode | provider={realtime_provider} | model={llm_config.get('model')}")
    else:
        # Half-cascade mode: realtime model emits TEXT, separate TTS speaks the audio.
        # Sarvam Saras v3 handles user STT in parallel (default, "sarvam"). The alternative
        # ("native") lets the conversational LLM transcribe itself — provider-agnostic. When
        # Sarvam is active we skip the LLM's own transcription to avoid dual writes and save cost.
        # Text-only chats have no audio, so treat as "no parallel STT" — the SDK's own
        # conversation events carry the user text.
        _use_sarvam_stt = not is_text_only and _stt_provider == "sarvam"

        # cartesia / deepgram / elevenlabs are cascade-only plugins — there is no pipeline
        # tap for them. Degrade to the LLM's own native transcription while in a pipeline
        # call so the caller still leaves with transcripts (matches the no-key fallback).
        # 'openai' is cascade-only too, but resolve_stt already collapses it to native
        # (same vendor, same model), so it never shows up here.
        if _stt_provider in {"cartesia", "deepgram", "elevenlabs"}:
            logger.warning(
                f"assistant_stt_model '{_stt_provider}' is cascade-only and ignored in "
                "pipeline mode — falling back to native transcription"
            )

        if realtime_provider == "openai":
            llm = realtime.RealtimeModel(
                model=_openai_realtime_model,
                input_audio_transcription=None if _use_sarvam_stt else _native_transcription,
                input_audio_noise_reduction=_noise_reduction,
                turn_detection=TurnDetection(
                    type="semantic_vad",
                    eagerness="high",
                    create_response=True,
                    interrupt_response=False,  # Don't interrupt LLM response mid-generation; let it finish and handle turn-taking in the agent logic instead
                ),
                modalities=["text"],
                truncation=_realtime_truncation,
                api_key=llm_config.get("api_key") or settings.OPENAI_API_KEY,
            )
        else:
            # Gemini used to be wired up here. It is no longer supported in pipeline mode:
            # the LiveKit half-cascade pattern needs a realtime model in text-only modality,
            # and Google's Live API only supports that on non-native-audio models
            # (https://github.com/googleapis/python-genai/issues/1780). The default model here
            # was a native-audio one, and the 3.1 Live models additionally ignore
            # generate_reply()/update_instructions(), which the greeting and handoff paths
            # depend on. Use assistant_mode 'realtime' for Gemini, or provider 'openai' here.
            # See docs/reference/compatibility.md.
            logger.error(
                f"Unsupported pipeline provider: {realtime_provider} — "
                "pipeline mode supports 'openai' only."
            )
            return
        logger.info("Half-cascade mode | llm=%s | tts=%s", realtime_provider, assistant.assistant_tts_model)

    # --- Build TTS (pipeline mode only) ---
    tts = None
    if not is_realtime and not is_text_only:
        tts = create_tts(assistant)
        if tts is None:
            return
        if hasattr(tts, "prewarm"):
            tts.prewarm()

    # --- Session Setup ---
    # Text-only chats reuse the realtime branch shape (no TTS, no audio knobs).
    if is_realtime or is_text_only:
        session = AgentSession(llm=llm)
    elif is_cascade:
        session = AgentSession(
            stt=cascade_stt,
            llm=llm,
            tts=tts,
            # Local Silero via livekit-local-inference (a core SDK dependency): in-process,
            # no API key, no Cloud call, nothing to prewarm. min_silence_duration is raised
            # from the 0.25 default to clear the turn detector's 0.25 floor with margin.
            vad=inference.VAD(model="silero", min_silence_duration=0.4),
            use_tts_aligned_transcript=True,
            aec_warmup_duration=1.0,  # seconds
            turn_handling=TurnHandlingOptions(
                # Audio end-of-utterance model, pinned to v1-mini: that version runs
                # fully local (weights ship inside the wheel). Left unpinned it would
                # try the Cloud-only "v1" first whenever LIVEKIT_DEV_MODE is set and
                # fall back with a warning — this platform is self-hosted, so ask for
                # the local one directly. 14 languages incl. hi.
                turn_detection=inference.TurnDetector(version="v1-mini"),
                endpointing={
                    "mode": "dynamic",
                    "min_delay": 0.3,
                    "max_delay": 1.0,
                },
                # "adaptive" is Cloud-only — _resolve_interruption_detection disables it
                # in production and there is no local fallback. "vad" is the real choice
                # here, and unlike the half-cascade branch below these knobs are live:
                # a plain LLM has no server-side VAD to short-circuit them.
                interruption={
                    "mode": "vad",
                    "min_duration": 0.5,
                    "false_interruption_timeout": 2.0,
                    "resume_false_interruption": True,
                },
            ),
        )
    else:
        session = AgentSession(
            llm=llm,
            tts=tts,
            # preemptive_generation=True,  # Deprecated in favor of turn_detection options below
            use_tts_aligned_transcript=True,
            aec_warmup_duration=1.0,  # seconds
            # No `interruption={...}` here on purpose. With turn_detection="realtime_llm"
            # the SDK skips VAD-based interruption entirely (agent_activity.py
            # on_vad_inference_done), and "adaptive" mode additionally needs a streaming
            # stt=, a vad=, a non-realtime LLM and a Cloud-hosted worker
            # (agent_activity._resolve_interruption_detection) — none of which apply. So
            # min_duration / min_words / false_interruption_timeout were dead config:
            # _on_input_speech_started interrupts unconditionally the moment the realtime
            # model's VAD reports speech. Noise filtering happens in SpeechGate instead,
            # upstream of that VAD. Don't re-add knobs here; tune audio_denoise.py.
            turn_handling=TurnHandlingOptions(
                turn_detection="realtime_llm",
                endpointing={
                    "mode": "dynamic",
                    "min_delay": 0.3,
                    "max_delay": 1.0,
                },
            ),
        )

    # --- Usage Tracking ---
    # No collector to wire: the session aggregates plugin metrics itself and exposes them
    # on `session.usage`, read once at teardown by summarize_usage(). The old
    # UsageCollector + "metrics_collected" subscription did the same job by hand and is
    # deprecated in the SDK.

    context_turns = deque(maxlen=4)
    user_is_speaking = False
    # Built here rather than inline in RoomOptions because InputGuardController mutes
    # through it. Text-only chats have no audio input, so there is nothing to gate.
    speech_gate = None if is_text_only else SpeechGate()
    silence_watchdog = (
        SilenceWatchdogController(
            session=session,
            logger=logger,
            reprompt_interval_sec=interaction_config.silence_reprompt_interval,
            max_reprompts=interaction_config.silence_max_reprompts,
            use_llm_for_speech=is_realtime,
        ) if silence_reprompts_enabled else None
    )
    # Filler words always go through OpenAI, so the assistant's LLM key only fits
    # when the assistant's LLM provider is OpenAI too.
    _filler_api_key = provider_key_or_system(
        llm_config, realtime_provider, "openai", settings.OPENAI_API_KEY
    )
    filler_controller = FillerController(session=session, context_turns=context_turns, openai_api_key=_filler_api_key) if filler_words_enabled else None
    hold_controller = HoldController(
        logger=logger,
        session=session,
        silence_watchdog=silence_watchdog,
        filler_controller=filler_controller,
    )
    # Enabled in realtime mode too: the guard now blanks audio through SpeechGate instead
    # of detaching the input, so the model keeps receiving a continuous feed (the reason
    # realtime used to be excluded). Text-only chats have no audio to guard.
    _guard_window = interaction_config.input_guard_window_sec
    input_guard = None if (speech_gate is None or _guard_window <= 0) else InputGuardController(
        logger=logger,
        gate=speech_gate,
        window_sec=_guard_window,
    )

    # Background audio
    background_audio = build_background_audio(interaction_config)

    # Text-only web chats turn off audio I/O on both sides and publish agent replies as
    # transcription text on the lk.chat topic. Regular web calls keep audio plus text input.
    logger.info(
        f"Session input mode | call_type={job_metadata.get('call_type')} | "
        f"text_input={is_web_call} | text_only={is_text_only}"
    )

    # SpeechGate is the only barge-in filter that works here: self-hosted rules out Cloud
    # noise cancellation, and turn_detection="realtime_llm" makes every LiveKit-side
    # interruption knob inert (see the comment on the AgentSession above). It runs upstream
    # of the realtime model, so noise never reaches the VAD that interrupts the agent.
    # AGC is off deliberately — the SDK default is True, and WebRTC AGC re-amplified the
    # agent's own echo into false barge-ins (docs/architecture/audio-pipeline.md).
    room_options = room_io.RoomOptions(
        text_input=is_web_call,
        audio_input=(
            # sample_rate is left at the SDK default: the gate resamples only its own VAD
            # copy, so the model still receives full-rate audio.
            False if speech_gate is None else room_io.AudioInputOptions(
                noise_cancellation=speech_gate,
                auto_gain_control=False,
            )
        ),
        audio_output=not is_text_only,
        text_output=True,
        close_on_disconnect=False,
        delete_room_on_close=False,
    )

    def _enqueue_transcript(speaker: str, text: str, timestamp: datetime | None = None) -> None:
        if _transcripts_closed:
            return
        # Stamped here, not at DB-write time: the queue and the Mongo round-trip both add
        # latency, and the Sarvam tap passes the time the caller actually started talking.
        timestamp = timestamp or datetime.now(timezone.utc)
        try:
            _transcript_queue.put_nowait(
                lambda: livekit_services.add_transcript(
                    room_name=ctx.room.name,
                    speaker=speaker,
                    text=text,
                    timestamp=timestamp,
                    assistant_id=assistant_id,
                    assistant_name=assistant.assistant_name,
                    to_number=to_number,
                    recording_path=recorder.s3_url,
                    created_by_email=assistant.assistant_created_by_email,
                    call_type=job_metadata.get("call_type"),
                    call_service=job_metadata.get("call_service") or job_metadata.get("service"),
                    platform_number=job_metadata.get("inbound_number"),
                )
            )
        except asyncio.QueueFull:
            logger.warning(f"Transcript queue full, dropping | room={room_name}")

    def _on_user_utterance(text: str, started_at: datetime) -> None:
        _enqueue_transcript("user", text, timestamp=started_at)
        if silence_watchdog:
            silence_watchdog.on_user_message()

    # One coalescer for both STT sources. Sarvam's per-endpoint finals and the LLM's own
    # committed turns are both fragments of a single sentence when the caller pauses
    # mid-speech, and both are rejoined the same way. Text-only chats skip it: there is no
    # endpointing to undo, and a debounce would wrongly merge two separately typed messages.
    _user_coalescer = None if is_text_only else FinalCoalescer(_on_user_utterance)

    # --- Transcription Event Handler ---
    @session.on("conversation_item_added")
    def on_conversation_item(event):
        role = getattr(event.item, "role", None)
        text = getattr(event.item, "text_content", None)
        if not text:
            return

        on_hold = hold_controller.is_on_hold
        if on_hold and role == "assistant":
            session.interrupt()
        if not should_record(role, on_hold=on_hold, gate_active=gate.is_active):
            return

        if role == "user":
            # Sarvam owns user transcripts when active — it feeds the coalescer directly.
            if _use_sarvam_stt:
                return
            if _user_coalescer is not None:
                _user_coalescer.add(text)
            else:
                _on_user_utterance(text, datetime.now(timezone.utc))
        else:
            _enqueue_transcript(role, text)

        if on_hold:
            return
        if filler_words_enabled and role in ("user", "assistant"):
            context_turns.append({"role": role, "text": text})
        if silence_watchdog and role == "assistant" and not user_is_speaking:
            silence_watchdog.on_assistant_message(text)

    # --- Start Session ---
    logger.info("Starting AgentSession...")
    await session.start(agent=agent_instance, room=ctx.room, room_options=room_options)
    logger.info("AgentSession started successfully")
    # Tell the dispatcher's silent-agent watchdog we actually made it into the room —
    # SIP can mark a call "answered" with no agent behind it (crash, provider outage,
    # worker overload); this timestamp is the thing that tells the difference.
    await livekit_services.mark_agent_ready(room_name)

    # Tell the SIP bridge the same thing over the room's data channel, so an inbound call can
    # ring until this point instead of answering into silence.
    #
    # This spot is chosen deliberately: it is after the inbound-context webhook (which can take
    # up to 10s), after tool loading, after TTS prewarm and after session.start() — so it means
    # both halves of "ready", the agent is up *and* the webhook has already answered.
    #
    # The bridge is the only listener and it treats this as advisory: if the publish fails, or
    # an older agent build never sends it, the bridge falls back to the agent's audio track
    # appearing and then to its own ring deadline. So a failure here delays an answer, it never
    # blocks one.
    try:
        await ctx.room.local_participant.publish_data(
            json.dumps({"event": "agent_ready"}).encode(),
            topic="sip_bridge_events",
        )
        logger.info("Published agent_ready to sip_bridge_events")
    except Exception as e:
        logger.warning(f"Could not publish agent_ready (call proceeds regardless): {e}")

    @session.on("user_state_changed")
    def on_user_state_changed(event):
        nonlocal user_is_speaking
        is_speaking = event.new_state == "speaking"
        user_is_speaking = is_speaking

        if hold_controller.is_on_hold:
            return  # Suppress filler/silence during hold

        if silence_watchdog:
            silence_watchdog.on_user_state_changed(is_speaking)
        if filler_controller:
            if is_speaking:
                filler_controller.start()
            else:
                filler_controller.stop()

    @session.on("agent_state_changed")
    def on_agent_state_changed(event):
        if hold_controller.is_on_hold and event.new_state == "speaking":
            session.interrupt()
        # The agent talking means the user's turn is over — emit the buffered utterance now
        # instead of waiting out the merge window, so it is written before the reply it caused.
        if _user_coalescer is not None and event.new_state == "speaking":
            _user_coalescer.flush()
        if silence_watchdog:
            if event.new_state == "speaking":
                silence_watchdog.on_agent_started_speaking()
            elif event.new_state == "listening":
                silence_watchdog.on_agent_done_speaking()
        if input_guard:
            if event.new_state == "speaking":
                input_guard.on_speaking_start()
            elif event.old_state == "speaking":
                input_guard.on_speaking_end()

    # --- Exotel Bridge: Call-Answered Handling ---
    @ctx.room.on("data_received")
    def on_data_received(data: rtc.DataPacket):
        if data.topic == "sip_bridge_events":
            try:
                msg = json.loads(data.data.decode())
                if msg.get("event") == "call_answered":
                    logger.info("Bridge reported call answered via data message (SIP 200 OK)")
                    gate.mark_answered()
                    if is_exotel_outbound:
                        asyncio.create_task(recorder.start_once())
                        asyncio.create_task(
                            livekit_services.update_call_status(
                                room_name=ctx.room.name,
                                call_status="answered",
                                call_status_reason=None,
                                answered_at=datetime.now(timezone.utc),
                            )
                        )
                elif msg.get("event") == "call_hold":
                    hold_controller.signal_hold(True)
                elif msg.get("event") == "call_resume":
                    hold_controller.signal_hold(False)
            except (json.JSONDecodeError, TypeError):
                pass

    # Wait for participant
    logger.info("Waiting for participant...")
    participant = await ctx.wait_for_participant()
    primary_participant_identity = participant.identity

    # --- Wait for Disconnect ---
    # Registered here, not after the greeting: the greeting block below can await the
    # readiness gate, recorder start and a full audio playout, and with close_on_disconnect
    # =False nothing else ends the job — so a caller who hung up in that window used to get
    # no teardown at all. Every name this closure reads is already bound by this point.
    @ctx.room.on("participant_disconnected")
    def on_participant_disconnected(participant):
        nonlocal call_end_triggered
        if filler_controller:
            filler_controller.stop()
        if silence_watchdog:
            silence_watchdog.stop()
        logger.info(f"Participant disconnected: {participant.identity}")
        if participant.identity != primary_participant_identity:
            logger.info(
                f"Ignoring non-primary disconnect: {participant.identity} "
                f"(primary={primary_participant_identity})"
            )
            return
        if call_end_triggered:
            logger.info(f"Call end already triggered for room: {ctx.room.name}")
            return
        call_end_triggered = True  # Immediate guard before task creation
        asyncio.create_task(_flush_and_end_call(delay=1.0))  # No delay — user already gone
        logger.info(f"Agent session ended for room: {ctx.room.name}")

    # --- Max call-duration watchdog ---
    # Hard cap on active-call length. Counts from gate-ready (post-answer for Exotel outbound,
    # immediately otherwise). On expiry, agent says a brief farewell then teardown runs.
    _max_minutes = (
        getattr(interaction_config, "max_call_duration_minutes", None)
        or DEFAULT_MAX_CALL_DURATION_MINUTES
    )

    async def _max_duration_watchdog(limit_minutes: float):
        nonlocal _end_reason
        try:
            if not await gate.wait_until_ready(timeout=3600.0):
                return  # call never answered — nothing to police
            await asyncio.sleep(limit_minutes * 60.0)
            if call_end_triggered:
                return
            logger.warning(
                f"Max call duration reached ({limit_minutes:.2f}min) — ending gracefully | room={room_name}"
            )
            _end_reason = "max_duration_exceeded"
            try:
                farewell = "I'm sorry, our call has reached its time limit. Thank you for calling. Goodbye!"
                await session.generate_reply(
                    instructions=f"Say this exactly and nothing else: '{farewell}'",
                    allow_interruptions=False,
                )
            except Exception as e:
                logger.error(f"Failed to deliver max-duration farewell: {e}")
            await _flush_and_end_call(delay=3.0)
        except asyncio.CancelledError:
            pass

    _max_duration_task = asyncio.create_task(_max_duration_watchdog(_max_minutes))
    logger.info(f"Max-duration watchdog armed | limit={_max_minutes:.2f}min | room={room_name}")

    is_sip = participant.kind == rtc.ParticipantKind.PARTICIPANT_KIND_SIP
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

    # Background audio start
    if background_audio:
        try:
            asyncio.create_task(
                background_audio.start(room=ctx.room, agent_session=session)
            )
            logger.info("Background audio task spawned")
        except Exception as e:
            logger.error(f"Failed to start background audio: {e}")

    # Persistent Sarvam WS keepalive — holds connection open for entire call.
    if isinstance(tts, sarvam_plugin.TTS):
        asyncio.create_task(maintain_sarvam_connection(tts, _sarvam_stop))

    # Sarvam Saras v3 parallel STT — overrides user transcript when half-cascade + sarvam selected.
    if _use_sarvam_stt:
        # Held, not fire-and-forget: teardown awaits this to get the last utterance, and a
        # crash inside it would otherwise cost every user transcript with only a stray
        # "exception was never retrieved" warning.
        _sarvam_task = asyncio.create_task(run_sarvam_parallel_stt(
            room=ctx.room,
            target_identity=primary_participant_identity,
            coalescer=_user_coalescer,
            stop_event=_sarvam_stop,
            api_key=_stt_config.get("api_key"),
            model=_stt_config.get("model"),
            language=_stt_config.get("language"),
            mode=_stt_config.get("mode"),
            assistant_id=assistant.assistant_id,
        ))

    # --- Start Instruction ---
    should_speak_first = interaction_config.speaks_first
    if should_speak_first:
        start_instruction = agent_instance.start_instruction
        if start_instruction:
            allow_int = getattr(interaction_config, "allow_interruptions", False)
            _saved_td = None
            _gate_muted_for_answer = False
            should_send_instruction = True
            try:
                # Disable server-side VAD before the Exotel gate wait, not just before generate_reply.
                # Pre-answer RTP audio (183, ring tone) during the 60s wait triggers the framework's
                # own generate_reply, which races with ours and logs spurious timeouts. Each call has
                # its own llm instance so this is safe under concurrency.
                if is_exotel_bridge and not allow_int and isinstance(llm, realtime.RealtimeModel):
                    _saved_td = llm._opts.turn_detection
                    llm.update_options(turn_detection=None)
                # Cascade has no realtime model whose VAD can be switched off, and its own
                # VAD + turn detector are live — so the same pre-answer ring tone would
                # create a spurious user turn. Blank the input at the gate instead, the
                # same lever InputGuardController uses. Unmuted in the finally below.
                elif is_exotel_bridge and not allow_int and is_cascade and speech_gate is not None:
                    speech_gate.muted = True
                    _gate_muted_for_answer = True

                if is_exotel_bridge:
                    logger.info("Exotel bridge detected — waiting for call_answered event before speaking")
                    answered = await gate.wait_until_ready(timeout=60.0)
                    if answered:
                        recording_ready = await recorder.ensure_started(timeout=12.0)
                        if not recording_ready:
                            logger.warning(
                                "[EXOTEL] Recording did not become ready before first reply; proceeding"
                            )
                        logger.info(
                            f"[EXOTEL] call_answered confirmed — sleeping {EXOTEL_RTP_WARMUP_SLEEP_SEC}s for RTP + egress warmup"
                        )
                        await asyncio.sleep(EXOTEL_RTP_WARMUP_SLEEP_SEC)
                    else:
                        logger.warning("[EXOTEL] Timed out waiting for call_answered — skipping start instruction")
                        should_send_instruction = False

                if should_send_instruction:
                    # The text recorded for the silence watchdog (transcript when prerecorded).
                    spoken_text = start_instruction

                    # For non-Exotel, non-interruptible realtime models: disable VAD before speaking
                    # (Exotel already did it above). Applies to every greeting path below.
                    if not allow_int and not is_exotel_bridge and isinstance(llm, realtime.RealtimeModel):
                        if _saved_td is None:
                            _saved_td = llm._opts.turn_detection
                        llm.update_options(turn_detection=None)

                    # Prefer a prerecorded greeting when configured — skips LLM + TTS for both modes.
                    greeting_cfg = assistant.assistant_greeting_audio
                    played_prerecorded = False
                    if greeting_cfg.enabled and greeting_cfg.audio_id:
                        transcript = await play_prerecorded_greeting(
                            session, greeting_cfg.audio_id, allow_int, prefetch=_greeting_prefetch_task,
                        )
                        if transcript is not None:
                            played_prerecorded = True
                            spoken_text = transcript

                    if not played_prerecorded:
                        if is_realtime:
                            logger.info("Start instruction strategy | mode=realtime_speaks_first_via_user_input | provider = %s", realtime_provider)

                            if realtime_provider == "gemini":
                                from google.genai import types as genai_types

                                rt_session = agent_instance.realtime_llm_session
                                rt_session._send_client_event(
                                    genai_types.LiveClientRealtimeInput(text=start_instruction)
                                )
                            else:
                                # OpenAI realtime (audio out): standard greeting via generate_reply.
                                if not allow_int:
                                    agent_instance._allow_interruptions = False
                                try:
                                    await session.generate_reply(instructions=start_instruction, allow_interruptions=allow_int)
                                finally:
                                    agent_instance._allow_interruptions = NOT_GIVEN
                        else:
                            # Shared by pipeline and cascade: both speak through an
                            # external TTS, so a generated reply is the opening.
                            logger.info(
                                "Start instruction strategy | mode=%s_speaks_first_via_instructions",
                                _mode,
                            )
                            try:
                                if not allow_int:
                                    agent_instance._allow_interruptions = False
                                await session.generate_reply(instructions=start_instruction, allow_interruptions=allow_int)
                            finally:
                                agent_instance._allow_interruptions = NOT_GIVEN

                    if silence_watchdog and spoken_text:
                        silence_watchdog.on_assistant_message(spoken_text)
                    logger.info("Start instruction sent successfully")
            except Exception as e:
                logger.error(f"Failed to send start instruction: {e}", exc_info=True)
            finally:
                if _saved_td is not None:
                    llm.update_options(turn_detection=_saved_td)
                # Must run even if the greeting raised, or the caller stays muted for the
                # whole call. InputGuardController owns `muted` from here on.
                if _gate_muted_for_answer and speech_gate is not None:
                    speech_gate.muted = False
    else:
        logger.info(
            "assistant_speaks_first=False — skipping start instruction; "
            "assistant is silent and waiting for the user to speak first"
        )


def _worker_load(worker) -> float:
    """Report this worker's load as a fraction of the jobs it is willing to run.

    The SDK default measures CPU across the whole machine. That made job intake depend on
    whatever else the host was doing: when the SIP dispatcher spiked CPU launching bridge
    processes, this worker quietly stopped accepting jobs, so calls connected with no agent
    behind them and the caller heard nothing. Counting our own jobs keeps the decision local
    and predictable.
    """
    # Measured against the global ceiling, not the telephony cap: this worker runs the agent
    # job for *every* call type — phone, web and passthrough — so the telephony cap alone would
    # make it refuse web jobs it has ample room for.
    max_jobs = max(1, settings.MAX_CONCURRENT_SESSIONS)
    return min(1.0, len(worker.active_jobs) / max_jobs)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            api_key=settings.LIVEKIT_API_KEY,
            api_secret=settings.LIVEKIT_API_SECRET,
            ws_url=settings.LIVEKIT_URL,
            job_memory_warn_mb=1024,
            # A hard ceiling, not just a warning. Only job_memory_warn_mb was set before, which
            # logs and does nothing, so a leaking session grew until the container OOMed and
            # took every call running alongside it down with it.
            job_memory_limit_mb=2048,
            entrypoint_fnc=entrypoint,
            agent_name="api-agent",
            # Raised from 2: at a dozen simultaneous calls, jobs past the second one queued
            # behind a cold process start each.
            num_idle_processes=4,
            load_fnc=_worker_load,
            # The SDK refuses a job when load >= threshold, so 1.0 means "refuse once we are
            # already running MAX_CONCURRENT_JOBS". Anything lower would make the worker refuse
            # jobs the dispatcher is still willing to send, and a dispatched call with no agent
            # behind it is a call that connects to silence.
            load_threshold=1.0,
        )
    )
