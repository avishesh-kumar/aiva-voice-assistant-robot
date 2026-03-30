"""
Context Manager (Mac Side)
--------------------------

Maintains short-term conversational context for the AI.

Design goals (LOCKED):
- Keep memory small and fast
- Preserve recent turns only
- Provide clean text context for LLMs
- No persistence (disk is handled elsewhere)
"""

from collections import deque
from typing import Deque, List


class ContextManager:
    def __init__(self):
        self.history = []
        self._guide_active = False
        self._guide_topic = None
        self.session_topic = None

    def add_user_message(self, text: str):
        self.history.append({"role": "user", "content": text})
        self._trim_history()

    def add_ai_message(self, text: str):
        self.history.append({"role": "assistant", "content": text})
        self._trim_history()

    def _trim_history(self):
        """Keep history within a reasonable size (max 50 messages)."""
        if len(self.history) > 50:
            self.history = self.history[-50:]

    def get_context(self) -> str:
        """
        Return recent conversation turns (user + assistant)
        to maintain short-term conversational memory.

        Keeps last 12 turns max to control token size.
        """
        if not self.history:
            return ""

        # Take last 12 messages (balanced memory vs speed)
        recent = self.history[-12:]

        lines = []
        for m in recent:
            role = m["role"].upper()
            lines.append(f"{role}: {m['content']}")

        return "\n".join(lines)


    # ---------------- GUIDE ----------------

    def set_guide_active(self, value: bool):
        self._guide_active = value
        if not value:
            self._guide_topic = None

    def is_guide_active(self) -> bool:
        return self._guide_active

    def set_guide_topic(self, topic: str):
        if self._guide_topic is None:
            self._guide_topic = topic

    def get_guide_topic(self):
        return self._guide_topic
