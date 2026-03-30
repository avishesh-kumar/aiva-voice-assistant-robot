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
        self.pending_enrollment = {
            "active": False,
            "name": None,
        }


    def add_user_message(self, text: str):
        self.history.append({"role": "user", "content": text})

    def add_ai_message(self, text: str):
        self.history.append({"role": "assistant", "content": text})

    def get_context(self) -> str:
        return "\n".join(
            f"{m['role'].upper()}: {m['content']}"
            for m in self.history[-10:]
        )
    def set_flag(self, key: str, value):
        setattr(self, key, value)

    def get_flag(self, key: str):
        return getattr(self, key, None)

    def clear_flag(self, key: str):
        if hasattr(self, key):
            delattr(self, key)

    def start_enrollment(self):
        self.pending_enrollment["active"] = True
        self.pending_enrollment["name"] = None

    def set_enrollment_name(self, name: str):
        self.pending_enrollment["name"] = name

    def clear_enrollment(self):
        self.pending_enrollment["active"] = False
        self.pending_enrollment["name"] = None


