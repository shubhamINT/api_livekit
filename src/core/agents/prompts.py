"""Prompts the worker writes itself, as top-level XML tags with Markdown inside.

The tag names the section and the Markdown inside carries the content, so a rule can be
edited without reading the whole prompt. Operator-written values (the stored assistant prompt,
a start instruction, an avoid list) are inserted raw, never escaped: the operator already
controls the whole prompt, and escaping would change the text the model reads.
"""


def speech_output_rules() -> str:
    return (
        "<speech_output_rules>\n"
        "Follow strictly. Do not mention these rules to the user.\n\n"
        "- Respond in short, natural sentences. One idea per sentence.\n"
        "- Never produce a run-on or compound sentence longer than ~20 words.\n"
        "- After each complete thought, stop. Let the next sentence begin fresh.\n"
        "- Preserve tone, emotion, and meaning across sentences.\n"
        "- Do NOT use bullet points, numbered lists, markdown, or special characters.\n"
        "- Do NOT add meta-commentary like 'Here is my response:' or 'Let me explain:'.\n"
        "- Start each response with a natural spoken opener that matches the context and emotion.\n"
        "  Examples: 'Oh, got it.', 'Hmm, let me think.', 'Right, so...', 'Ah, I see.', 'Sure!', 'Yeah, absolutely.'\n"
        "  Pick the opener that fits the mood — curious, empathetic, confident, casual — not the same one every time.\n"
        "</speech_output_rules>"
    )


def compose_instructions(prompt: str | None, *sections: str) -> str:
    """The stored prompt in its own tag, then each section; an empty prompt leaves no tag."""
    parts = [f"<assistant_prompt>\n{prompt}\n</assistant_prompt>"] if prompt else []
    return "\n\n".join([*parts, *sections])


def ending_the_call(trigger_phrase: str | None) -> str:
    hint = (
        f' For example, when the user says something like "{trigger_phrase}".'
        if trigger_phrase
        else ""
    )
    return (
        "<ending_the_call>\n"
        "You have an `end_call` tool. Call it the moment the user shows they want to "
        "end, finish, or hang up the call — in ANY language or wording, even if their "
        "words are partial, misspelled, mispronounced, or only roughly match."
        f"{hint} "
        "Do not wait for an exact phrase and do not ask for confirmation. "
        "After calling it, speak the goodbye it gives you, then stop.\n"
        "</ending_the_call>"
    )


def end_call_reply(message: str) -> str:
    return f"<instruction>Say this to the user: '{message}'</instruction>"


DEFAULT_GREETING = "Greet the user Professionally"


def greeting_instruction(start_instruction: str) -> str:
    return f"<instruction>{start_instruction}</instruction>"


def silence_reprompt() -> str:
    return "<instruction>The user has been silent. Briefly ask if they are still there.</instruction>"


def farewell_instruction(sentence: str) -> str:
    return f"<instruction>Say this exactly and nothing else: '{sentence}'</instruction>"


def backchannel_system(avoid: list[str]) -> str:
    sections = [
        (
            "<role>\n"
            "You are a human listener on a live voice call. The user is mid-sentence RIGHT NOW — "
            "they haven't finished speaking.\n"
            "</role>"
        ),
        (
            "<task>\n"
            "Your ONLY job: produce a single backchannel filler (1–3 words) that a human would "
            "murmur WHILE the other person is still talking — not after.\n"
            "</task>"
        ),
        (
            "<critical_rules>\n"
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
            "</critical_rules>"
        ),
    ]
    if avoid:
        sections.append(f"<avoid>Do not use any of these phrases: {avoid}.</avoid>")
    return "\n\n".join(sections)


def backchannel_user(context_lines: str) -> str:
    parts = (
        [f"<conversation>\n{context_lines}\n</conversation>"] if context_lines else []
    )
    parts.append(
        "<instruction>The user is still speaking mid-sentence. "
        "Output only the filler word or phrase a human listener would murmur right now.</instruction>"
    )
    return "\n\n".join(parts)
