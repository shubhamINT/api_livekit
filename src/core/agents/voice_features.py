import asyncio
import logging
import random
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Final

from livekit.agents import AgentSession
from openai import AsyncOpenAI

from src.core.agents.audio_denoise import SpeechGate
from src.core.config import settings

REPROMPT_INTERVAL_SEC: Final[float] = 10.0
MAX_REPROMPTS: Final[int] = 2
POST_REPROMPT_GRACE_SEC: Final[float] = 5.0  # wait after reprompt before restarting the silence timer
_recent_fillers: deque[str] = deque(maxlen=5)
_client: AsyncOpenAI | None = None


async def generate_filler(context: list[dict[str, str]], api_key: str | None = None) -> str | None:
    """Generate a short filler phrase for live backchanneling."""
    global _client
    resolved_key = api_key or settings.OPENAI_API_KEY
    if not resolved_key:
        return None

    if _client is None:
        _client = AsyncOpenAI(api_key=resolved_key)

    avoid = list(_recent_fillers)
    avoid_clause = f"Do not use any of these phrases: {avoid}. " if avoid else ""

    if context:
        context_lines = "\n".join(
            f"{index + 1}. [{turn['role'].capitalize()}]: {turn['text']}"
            for index, turn in enumerate(context[-4:])
        )
        context_block = f"Recent conversation:\n{context_lines}\n\n"
    else:
        context_block = ""

    try:
        response = await _client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a human listener on a live voice call. The user is mid-sentence RIGHT NOW — "
                        "they haven't finished speaking.\n\n"
                        "Your ONLY job: produce a single backchannel filler (1–3 words) that a human would "
                        "murmur WHILE the other person is still talking — not after.\n\n"
                        "CRITICAL RULES:\n"
                        "- The filler must feel natural MID-SENTENCE, not as a response to a complete thought.\n"
                        "- Prefer ultra-short: 'Mm.', 'Yeah.', 'Mm-hmm.', 'Right.', 'Uh-huh.' for neutral flow.\n"
                        "- Tone-match only if the emotional signal is very strong:\n"
                        "    sad/heavy → 'Mm.', 'Yeah...', 'I see.'\n"
                        "    excited/surprising → 'Oh!', 'Wow.', 'Really?'\n"
                        "    thoughtful/explaining → 'Right.', 'Um-hmm.', 'Yeah.'\n"
                        "- NEVER complete their thought, answer, advise, or ask anything.\n"
                        "- NEVER use more than 3 words.\n"
                        "- No quotes. Natural punctuation only.\n"
                        "- Default to the shortest possible filler. When in doubt: 'Um-hmm.' or 'Yeah.'\n"
                        f"{avoid_clause}"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"{context_block}"
                        "The user is still speaking mid-sentence. "
                        "Output only the filler word or phrase a human listener would murmur right now."
                    ),
                },
            ],
            max_tokens=10,
            temperature=0.9,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            return None
        _recent_fillers.append(text)
        return text
    except Exception:
        return None


class SilenceWatchdogController:
    """Reprompt the user and end the session after repeated silence."""

    def __init__(
        self,
        session: AgentSession,
        logger: logging.Logger,
        on_silence_exhausted: Callable[[], Awaitable[None]],
        reprompt_interval_sec: float = 10.0,
        max_reprompts: int = 2,
        use_llm_for_speech: bool = False,
    ) -> None:
        self._session = session
        self._logger = logger
        # The owner's teardown. This controller must not end the call itself.
        self._on_silence_exhausted = on_silence_exhausted
        self._reprompt_interval_sec = reprompt_interval_sec
        self._max_reprompts = max_reprompts
        self._use_llm_for_speech = use_llm_for_speech  # True for realtime mode (no external TTS)
        self._silence_task: asyncio.Task | None = None
        self._reprompt_count = 0
        self._user_is_speaking = False
        self._agent_is_speaking = False
        self._pending_start = False  # start watchdog once agent finishes speaking
        # Guards on_assistant_message during in-flight reprompt. Safe: asyncio cooperative scheduling
        # ensures the flag is only toggled between awaits, never concurrently.
        self._reprompt_in_progress = False

    def stop(self, reset_count: bool = True) -> None:
        if reset_count:
            self._reprompt_count = 0
        if self._silence_task and not self._silence_task.done():
            self._silence_task.cancel()
        self._silence_task = None

    def start(self) -> None:
        if self._user_is_speaking or self._agent_is_speaking:
            return
        if self._silence_task and not self._silence_task.done():
            return
        self._silence_task = asyncio.create_task(self._watchdog_loop())

    def on_user_message(self) -> None:
        self._pending_start = False
        self.stop(reset_count=True)

    def on_assistant_message(self, message_text: str) -> None:
        if not message_text or self._reprompt_in_progress:
            return
        self.stop(reset_count=True)
        # Defer start until agent finishes speaking — avoids timer running during TTS playback
        self._pending_start = True

    def on_agent_started_speaking(self) -> None:
        self._agent_is_speaking = True
        # Pause the running watchdog (user can't respond while agent speaks)
        if self._silence_task and not self._silence_task.done():
            self._silence_task.cancel()
            self._silence_task = None

    def on_agent_done_speaking(self) -> None:
        self._agent_is_speaking = False
        if self._pending_start:
            self._pending_start = False
            self.start()

    def on_user_state_changed(self, is_speaking: bool) -> None:
        self._user_is_speaking = is_speaking
        if is_speaking:
            self.stop(reset_count=False)
            return
        self.start()

    async def _watchdog_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._reprompt_interval_sec)

                if self._user_is_speaking:
                    return

                self._reprompt_count += 1
                self._logger.info(
                    "[silence] reprompt %s/%s",
                    self._reprompt_count,
                    self._max_reprompts,
                )

                if self._reprompt_count >= self._max_reprompts:
                    self._logger.info("[silence] ending call after repeated silence")
                    # Detached, never awaited: stop() below cancels this very task, and the
                    # teardown's delete_room makes participant_disconnected cancel it again.
                    asyncio.create_task(self._on_silence_exhausted())
                    self.stop(reset_count=True)
                    return

                self._reprompt_in_progress = True
                try:
                    if self._use_llm_for_speech:
                        await self._session.generate_reply(
                            instructions="The user has been silent. Briefly ask if they are still there.",
                        )
                    else:
                        await self._session.say(
                            "Sorry, I didn't catch that. Are you still there?",
                            allow_interruptions=True,
                        )
                finally:
                    self._reprompt_in_progress = False
                await asyncio.sleep(POST_REPROMPT_GRACE_SEC)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._logger.exception("[silence] watchdog failed")
        finally:
            if asyncio.current_task() is self._silence_task:
                self._silence_task = None


class HoldController:
    """Suppress agent activity during SIP hold."""

    def __init__(
        self,
        logger: logging.Logger,
        session: AgentSession,
        silence_watchdog: "SilenceWatchdogController | None",
        filler_controller: "FillerController | None",
    ) -> None:
        self._logger = logger
        self._session = session
        self._silence_watchdog = silence_watchdog
        self._filler_controller = filler_controller
        self._is_on_hold = False

    @property
    def is_on_hold(self) -> bool:
        return self._is_on_hold

    def signal_hold(self, is_hold: bool) -> None:
        if is_hold and not self._is_on_hold:
            self._is_on_hold = True
            self._logger.info("[HOLD] Call on hold — suppressing agent")
            if self._silence_watchdog:
                self._silence_watchdog.stop(reset_count=True)
            if self._filler_controller:
                self._filler_controller.stop()
            self._session.interrupt()
        elif not is_hold and self._is_on_hold:
            self._is_on_hold = False
            self._logger.info("[HOLD] Call resumed")
            if self._silence_watchdog:
                self._silence_watchdog.start()


class InputGuardController:
    """Blank user audio for the first N seconds of each agent utterance.

    Prevents the impatient-user feedback loop on phone calls: users repeat
    themselves before the agent has finished producing its reply, those
    repeats trip the interruption path, and the agent fragments/restarts.
    Also the only thing that stops short filler sounds ("um", "uh") from
    barging in — SpeechGate cannot, because those are genuine speech.
    Restores early if the agent stops speaking before the window expires.

    Blanking is done through `SpeechGate.muted`, not
    `session.input.set_audio_enabled(False)`: the latter drops frames outright, and a
    realtime model expecting a continuous audio feed (notably Gemini Live) can misbehave on
    the gap. Muting keeps frames flowing at the same rate, carrying silence.
    """

    def __init__(
        self,
        logger: logging.Logger,
        gate: SpeechGate,
        window_sec: float = 1.8,
    ) -> None:
        self._logger = logger
        self._gate = gate
        self._window = window_sec
        self._task: asyncio.Task | None = None
        self._active = False

    def on_speaking_start(self) -> None:
        if self._active:
            return
        try:
            self._gate.muted = True
        except Exception as e:
            self._logger.warning("[input-guard] mute failed: %s", e)
            return
        self._active = True
        self._task = asyncio.create_task(self._auto_reenable())

    def on_speaking_end(self) -> None:
        if not self._active:
            return
        if self._task and not self._task.done():
            self._task.cancel()
        self._reenable("speaking-ended")

    async def _auto_reenable(self) -> None:
        try:
            await asyncio.sleep(self._window)
            self._reenable("window-expired")
        except asyncio.CancelledError:
            raise

    def _reenable(self, reason: str) -> None:
        try:
            self._gate.muted = False
        except Exception as e:
            # User stays muted on failure — escalate, don't whisper
            self._logger.error("[input-guard] unmute FAILED — user audio remains blocked: %s", e)
        self._active = False
        self._logger.debug("[input-guard] restored (%s)", reason)

    async def aclose(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        if self._active:
            self._reenable("close")


class FillerController:
    """Manage the filler word task lifecycle."""

    def __init__(
        self,
        session: AgentSession,
        context_turns: deque[dict[str, str]],
        openai_api_key: str | None = None,
    ) -> None:
        self._session = session
        self._context_turns = context_turns
        self._openai_api_key = openai_api_key
        self._filler_task: asyncio.Task | None = None

    def stop(self) -> None:
        """Stop the filler word task."""
        if self._filler_task and not self._filler_task.done():
            self._filler_task.cancel()
        self._filler_task = None

    def start(self) -> None:
        """Start the filler word loop."""
        self.stop()
        self._filler_task = asyncio.create_task(self._filler_loop())

    async def _filler_loop(self) -> None:
        """Generate and speak filler words periodically."""
        try:
            # Initial wait before first filler
            await asyncio.sleep(random.uniform(2.0, 3.0))
            while True:
                text = await generate_filler(list(self._context_turns), self._openai_api_key)
                if text:
                    await self._session.say(text, allow_interruptions=True)
                await asyncio.sleep(random.uniform(4.0, 6.0))
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        finally:
            if asyncio.current_task() is self._filler_task:
                self._filler_task = None
