"""
AI Router (Mac Side)
-------------------

Motor/Vision response gate.
Blocks non-command input with fixed responses.

This module hides all LLM-specific details from the Brain.

Contract (LOCKED):
- Input: user text, intent, context
- Output: assistant text (str)
- No audio, no networking, no side effects
"""

from typing import Optional
from intelligence.intent_classifier import Intent

class AIRouter:
    """
    Central AI decision router.

    Rules:
    # Ollama is the DEFAULT for all queries (low latency, offline)
    # Gemini Flash is fallback only (when Ollama fails)
    """

    def __init__(
        self,
        ollama_url: str = "http://localhost:11434/api/generate",
        ollama_model: str = "llama3.2:latest",
        ollama_fast_model: str = "phi:latest",
        gemini_model: str = "models/gemini-2.5-flash",
        temperature: float = 0.3,
    ):
        pass
    
    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_response(self, user_text, intent, context=None):

        # Enrollment is handled by Brain directly
        if intent == Intent.ENROLL:
            return ""

        if intent == Intent.COMMAND:
            return ""

        return "I can only follow movement or vision commands."
