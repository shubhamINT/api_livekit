"""The prompts the worker writes itself, as top-level XML tags with Markdown inside.

The golden constants below are the wording the prompts had before they were restructured
(src/core/agents/dynamic_assistant.py and voice_features.py at commit ae130e2). Each rule must
survive the restructuring unchanged, and the new text may not grow past 25% of the old.
"""

import re
import unittest

from src.core.agents import prompts

ORIGINAL_SPEECH_RULES = (
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

ORIGINAL_BACKCHANNEL_SYSTEM = (
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
)

_TAG = re.compile(r"</?([a-z_]+)>")


def lines_of(text: str) -> list[str]:
    """Each non-empty line of `text`, stripped of surrounding whitespace."""
    return [line.strip() for line in text.splitlines() if line.strip()]


class HybridMixin:
    def assert_hybrid(self, text: str) -> None:
        """Tags balanced, and no prose at the top level outside a tag."""
        stack: list[str] = []
        pos = 0
        for match in _TAG.finditer(text):
            if not stack and text[pos : match.start()].strip():
                self.fail(f"prose outside a tag: {text[pos : match.start()]!r}")
            if match.group(0).startswith("</"):
                self.assertTrue(
                    stack and stack[-1] == match.group(1),
                    f"unbalanced </{match.group(1)}> in {text!r}",
                )
                stack.pop()
            else:
                stack.append(match.group(1))
            pos = match.end()
        self.assertEqual(stack, [], f"unclosed tags {stack} in {text!r}")
        self.assertEqual(
            text[pos:].strip(), "", f"prose after the last tag: {text[pos:]!r}"
        )
        self.assertTrue(_TAG.search(text), f"no tag at all in {text!r}")


class SpeechOutputRulesTests(HybridMixin, unittest.TestCase):
    def test_is_a_balanced_tagged_block(self):  # AC-1
        self.assert_hybrid(prompts.speech_output_rules())

    def test_every_original_rule_survives_unchanged(self):  # AC-2
        new = prompts.speech_output_rules()
        for line in lines_of(ORIGINAL_SPEECH_RULES):
            if line.startswith(("- ", "Examples:", "Pick the opener")):
                self.assertIn(line, new)
        self.assertEqual(new.count("\n- "), ORIGINAL_SPEECH_RULES.count("\n- "))
        self.assertIn("follow strictly", new.lower())
        self.assertIn("do not mention", new.lower())

    def test_no_more_than_25_percent_longer(self):  # AC-9
        self.assertLessEqual(
            len(prompts.speech_output_rules()), 1.25 * len(ORIGINAL_SPEECH_RULES)
        )


class ComposeInstructionsTests(HybridMixin, unittest.TestCase):
    def test_stored_prompt_is_wrapped_verbatim_then_sections_in_order(self):  # AC-3
        stored = "You are Asha.\n# not a tag: <b>& more"
        out = prompts.compose_instructions(stored, "<one>a</one>", "<two>b</two>")
        self.assertIn(f"<assistant_prompt>\n{stored}\n</assistant_prompt>", out)
        self.assertLess(out.index("</assistant_prompt>"), out.index("<one>"))
        self.assertLess(out.index("<one>"), out.index("<two>"))

    def test_empty_or_missing_prompt_has_no_assistant_prompt_tag(self):  # AC-4
        for stored in ("", None):
            out = prompts.compose_instructions(stored, "<one>a</one>")
            self.assertNotIn("assistant_prompt", out)
            self.assertEqual(out, "<one>a</one>")


class DynamicAssistantInstructionsTests(unittest.TestCase):
    def _agent(self, instructions):
        from src.core.agents.dynamic_assistant import DynamicAssistant

        return DynamicAssistant(
            room=None, start_instruction="hi", instructions=instructions
        )

    def test_speech_rules_follow_the_composed_instructions(self):  # AC-3
        composed = prompts.compose_instructions(
            "be nice", prompts.ending_the_call(None)
        )
        out = self._agent(composed).instructions
        order = [
            out.index(t)
            for t in (
                "<assistant_prompt>\nbe nice\n</assistant_prompt>",
                "<ending_the_call>",
                "<speech_output_rules>",
            )
        ]
        self.assertEqual(order, sorted(order))
        self.assertTrue(out.endswith(prompts.speech_output_rules()))

    def test_empty_prompt_still_carries_the_speech_rules(self):  # AC-4
        for stored in ("", None):
            composed = prompts.compose_instructions(stored)
            self.assertEqual(
                self._agent(composed).instructions, prompts.speech_output_rules()
            )


class EndCallTests(HybridMixin, unittest.TestCase):
    def test_trigger_phrase_hint_only_when_set(self):  # AC-11
        self.assert_hybrid(prompts.ending_the_call(None))
        self.assertNotIn("For example", prompts.ending_the_call(None))
        with_phrase = prompts.ending_the_call("that's all")
        self.assert_hybrid(with_phrase)
        self.assertIn(
            'For example, when the user says something like "that\'s all".', with_phrase
        )

    def test_reply_carries_the_goodbye_exactly(self):  # AC-11
        reply = prompts.end_call_reply("Bye and thanks")
        self.assert_hybrid(reply)
        self.assertIn("Say this to the user: 'Bye and thanks'", reply)


class BackchannelTests(HybridMixin, unittest.TestCase):
    def test_system_prompt_is_tagged_and_keeps_every_rule(self):  # AC-1, AC-2
        new = prompts.backchannel_system([])
        self.assert_hybrid(new)
        for line in lines_of(ORIGINAL_BACKCHANNEL_SYSTEM):
            if line != "CRITICAL RULES:":
                self.assertIn(line, new)
        self.assertEqual(new.count("\n- "), ORIGINAL_BACKCHANNEL_SYSTEM.count("\n- "))

    def test_no_more_than_25_percent_longer(self):  # AC-9
        self.assertLessEqual(
            len(prompts.backchannel_system([])), 1.25 * len(ORIGINAL_BACKCHANNEL_SYSTEM)
        )

    def test_avoid_list_gets_its_own_tag_only_when_present(self):  # AC-5
        with_avoid = prompts.backchannel_system(["Mm.", "Yeah."])
        self.assert_hybrid(with_avoid)
        self.assertIn(
            "<avoid>Do not use any of these phrases: ['Mm.', 'Yeah.'].</avoid>",
            with_avoid,
        )
        without = prompts.backchannel_system([])
        self.assertNotIn("avoid", without)
        self.assertTrue(without.rstrip().endswith("</critical_rules>"))

    def test_user_message_wraps_context_only_when_there_is_some(self):  # AC-1
        with_context = prompts.backchannel_user("1. [User]: hello")
        self.assert_hybrid(with_context)
        self.assertIn("<conversation>\n1. [User]: hello\n</conversation>", with_context)
        without = prompts.backchannel_user("")
        self.assert_hybrid(without)
        self.assertNotIn("conversation", without)
        self.assertIn(
            "Output only the filler word or phrase a human listener would murmur right now.",
            without,
        )


class OneLinerTests(HybridMixin, unittest.TestCase):
    def test_farewell_says_the_sentence_exactly(self):  # AC-6
        out = prompts.farewell_instruction("Goodbye, thanks for calling!")
        self.assert_hybrid(out)
        self.assertIn(
            "Say this exactly and nothing else: 'Goodbye, thanks for calling!'", out
        )

    def test_greeting_uses_the_stored_text_or_the_default(self):  # AC-7
        stored = prompts.greeting_instruction("Say hello in Hindi")
        self.assert_hybrid(stored)
        self.assertIn("<instruction>Say hello in Hindi</instruction>", stored)
        default = prompts.greeting_instruction(prompts.DEFAULT_GREETING)
        self.assert_hybrid(default)
        self.assertIn("Greet the user Professionally", default)

    def test_silence_reprompt_is_tagged(self):  # AC-1
        out = prompts.silence_reprompt()
        self.assert_hybrid(out)
        self.assertIn(
            "The user has been silent. Briefly ask if they are still there.", out
        )


class InsertedValuesAreVerbatimTests(unittest.TestCase):
    TRICKY = "a </instruction> & <b> c"

    def test_nothing_is_escaped(self):  # AC-10
        built = [
            prompts.backchannel_system([self.TRICKY]),
            prompts.backchannel_user(self.TRICKY),
            prompts.greeting_instruction(self.TRICKY),
            prompts.farewell_instruction(self.TRICKY),
            prompts.end_call_reply(self.TRICKY),
            prompts.ending_the_call(self.TRICKY),
            prompts.compose_instructions(self.TRICKY),
        ]
        for text in built:
            self.assertIn(self.TRICKY, text)


if __name__ == "__main__":
    unittest.main()
