from collections.abc import AsyncIterable

from livekit import rtc
from livekit.agents import Agent

_TTS_CHUNK_DIRECTIVE = (
    "\n\n---\n"
    "SPEECH OUTPUT RULES (follow strictly, do not mention these to the user):\n"
    "- Respond in short, natural sentences. One idea per sentence.\n"
    "- Never produce a run-on or compound sentence longer than ~20 words.\n"
    "- After each complete thought, stop. Let the next sentence begin fresh.\n"
    "- Preserve tone, emotion, and meaning across sentences.\n"
    "- Do NOT use bullet points, numbered lists, markdown, or special characters.\n"
    "- Do NOT add meta-commentary like 'Here is my response:' or 'Let me explain:'.\n"
    "- Start each response with a natural spoken opener that matches the context and emotion.\n"
    "  Examples: 'Oh, got it.', 'Hmm, let me think.', 'Right, so...', 'Ah, I see.', 'Sure!', 'Yeah, absolutely.'\n"
    "  Pick the opener that fits the mood — curious, empathetic, confident, casual — not the same one every time.\n"
    "---"
)


class DynamicAssistant(Agent):
    """
    A dynamic agent wrapper that holds configuration fetched from the database.
    This replaces the hardcoded agent classes.
    """

    def __init__(self, room, start_instruction: str, instructions: str, tools=None, stt_usage=None):
        super().__init__(instructions=(instructions or "") + _TTS_CHUNK_DIRECTIVE, tools=tools or [])
        self.room = room
        self.start_instruction = start_instruction
        self._stt_usage = stt_usage

    async def stt_node(self, audio: AsyncIterable[rtc.AudioFrame], model_settings):
        """Count the audio handed to the cascade STT stage on the way past.

        Only cascade passes a tally: it is the one mode with an `stt=` stage, and its Sarvam
        plugin reports a duration the server may omit entirely (see
        src/core/agents/stt/cascade_usage.py). Counting here rather than inside the STT
        object because `stt_node` is a documented `Agent` override, while the frames only
        reach a `RecognizeStream` through SDK-private plumbing.

        Overriding this disables the SDK's STT-pipeline reuse across agent handoffs
        (agents/voice/agent_activity.py:917-918 gates reuse on
        `type(agent).stt_node is Agent.stt_node`). This runtime calls `session.start` once and
        never hands off, so that costs nothing today — but it is why this override exists on
        the agent rather than being free.
        """
        if self._stt_usage is None:
            async for event in Agent.default.stt_node(self, audio, model_settings):
                yield event
            return

        async def _counted():
            async for frame in audio:
                self._stt_usage.audio_duration += frame.duration
                yield frame

        async for event in Agent.default.stt_node(self, _counted(), model_settings):
            yield event
