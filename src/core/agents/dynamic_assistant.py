from livekit.agents import Agent


class DynamicAssistant(Agent):
    """
    A dynamic agent wrapper that holds configuration fetched from the database.
    This replaces the hardcoded agent classes.
    """

    def __init__(self, room, start_instruction: str, instructions: str, tools=None):
        super().__init__(instructions=instructions, tools=tools or [])
        self.room = room
        self.start_instruction = start_instruction