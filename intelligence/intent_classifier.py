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
from typing import Tuple

class Intent(str, Enum):
    """
    High-level intent categories.

    These are used by the Brain to route behavior,
    NOT to generate language.
    """
    COMMAND = "command"
    QUESTION = "question"
    CHAT = "chat"
    UNKNOWN = "unknown"


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

    def classify(self, text: str) -> Tuple[Intent, float]:
        """
        Classify user text into an intent category with confidence.

        Returns:
            (Intent, confidence) where confidence ∈ [0.0, 1.0]
        """
        if not text:
            return Intent.UNKNOWN, 0.0

        normalized = text.strip().lower()

        # --------------------------------------------------
        # STEP queries → very high confidence QUESTION
        # --------------------------------------------------
        if normalized in {
            "step 1", "step 2", "step 3",
            "step one", "step two", "step three"
        }:
            return Intent.QUESTION, 0.95

        if normalized.startswith("step "):
            step_part = normalized[5:].strip()
            if step_part.isdigit() or step_part in {
                "one", "two", "three", "four", "five",
                "six", "seven", "eight", "nine", "ten"
            }:
                return Intent.QUESTION, 0.95

        # --------------------------------------------------
        # QUESTIONS
        # --------------------------------------------------
        if normalized.endswith("?"):
            return Intent.QUESTION, 0.9

        question_words = (
            "what", "why", "how", "when", "where",
            "who", "which", "can you", "do you",
            "is there", "are there",
        )

        for q in question_words:
            if normalized.startswith(q):
                return Intent.QUESTION, 0.85

        question_phrases = (
            "tell me about",
            "what is",
            "explain",
            "define",
            "meaning of",
        )

        for phrase in question_phrases:
            if phrase in normalized:
                return Intent.QUESTION, 0.8

        # --------------------------------------------------
        # ACTION-INTENT PHRASES (NO EXECUTION)
        # --------------------------------------------------
        words = normalized.split()

        # Strong command: starts with command keyword
        if words and words[0] in self._command_keywords:
            return Intent.COMMAND, 0.9

        # Medium confidence command: phrase match
        command_phrases = (
            "move forward", "move backward",
            "turn left", "turn right",
            "stop", "pause", "cancel",
            "forward", "backward",
            "left", "right",
        )

        for phrase in command_phrases:
            if phrase in normalized:
                return Intent.COMMAND, 0.7

        # --------------------------------------------------
        # CHAT fallback
        # --------------------------------------------------
        if normalized:
            return Intent.CHAT, 0.6

        return Intent.UNKNOWN, 0.0
