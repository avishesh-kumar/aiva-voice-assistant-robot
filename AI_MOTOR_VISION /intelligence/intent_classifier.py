"""
Intent Classifier (Mac Side)
----------------------------

Classifies user text into high-level intent categories.

This module is deliberately simple and deterministic.
It is NOT an LLM.

Contract (LOCKED):
- Input: user text (str)
- Output: intent label (str)
- No side effects
- No external API calls
"""

from enum import Enum
from typing import Optional


class Intent(str, Enum):
    COMMAND = "command"
    SCENE_QUERY = "scene_query"  
    UNKNOWN = "unknown"
    ENROLL = "enroll"

class IntentClassifier:
    """
    Rule-based intent classifier.

    This MUST remain lightweight and fast.
    LLM-based intent detection is NOT allowed here.
    """

    def __init__(self):
        # Keywords that strongly imply a command
        self._command_keywords = {
            "go",
            "move",
            "come",
            "stop",
            "turn",
            "follow",
            "look",
            "find",
            "count",
            "start",
            "shutdown",
            "rotate",
            "walk",
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, text: str) -> Intent:
        """
        Classify user text into an intent category.

        Args:
            text (str): Final STT transcript

        Returns:
            Intent: COMMAND | UNKNOWN
        """
        if not text:
            return Intent.UNKNOWN

        normalized = text.strip().lower()

        enroll_keywords = {
            "remember",
            "register",
            "enroll",
            "save my face",
            "save my name",
            "remember me",
        }

        for kw in enroll_keywords:
            if kw in normalized:
                return Intent.ENROLL


        scene_triggers = (
            "what do you see",
            "what you see",
            "what can you see",
            "what do you see now",
            "describe the room",
            "describe the scene",
            "describe surroundings",
            "what is around",
            "what is in front of you",
            "do you see",
        )

        for trigger in scene_triggers:
            if trigger in normalized:
                return Intent.SCENE_QUERY

        # 2. Command detection
        # First check single command words
        first_word = normalized.split()[0]
        if first_word in self._command_keywords:
            return Intent.COMMAND

        # Check for command phrases anywhere in the text
        command_phrases = (
            "move forward",
            "forward",
            "move backward", 
            "backward",
            "turn left",
            "left",
            "move left",
            "move right",
            "turn right",
            "right",
            "stop",
            "pause",
            "cancel",
        )
        
        for phrase in command_phrases:
            if phrase in normalized:
                return Intent.COMMAND
        
        return Intent.UNKNOWN
