# intelligence/planner.py

from intelligence.intent_classifier import Intent
from intelligence.decision_schema import (
    DecisionEnvelope,
    Response,
    Behavior,
)
LOW_COMMAND_CONFIDENCE = 0.6
class Planner:
    """
    Phase 3 Planner (LOCKED)

    Responsibilities:
    - Decide MODE (behavioral contract)
    - Declare HIGH-LEVEL behavior (never execution)
    - ALWAYS return a complete DecisionEnvelope
    - NEVER call AI, motors, vision, or networking
    """

    def decide(
        self,
        user_text: str,
        intent: Intent,
        confidence: float,
        context: str,
    ) -> DecisionEnvelope:

        """
        Core decision entry point.
        This function MUST always return a valid DecisionEnvelope.
        """

        text = (user_text or "").strip().lower()
        tokens = set(text.split())

        # --------------------------------------------------
        # 0. Empty / noise input
        # --------------------------------------------------
        if not text:
            return DecisionEnvelope(
                intent=intent,
                mode="CASUAL",
                response=Response(
                    speech="I didn’t catch that. Could you please repeat?"
                ),
                reason="empty_input",
            )

        # --------------------------------------------------
        # 1. Greetings – delegate to AI
        # --------------------------------------------------
        greetings = {
            "hi", "hello", "hey", "hii",
            "hello robot", "hi robot",
            "hello ava", "hi ava",
        }

        if text in greetings:
            return DecisionEnvelope(
                intent=intent,
                mode="CASUAL",
                response=Response(
                    speech=""
                ),
                reason="greeting_delegate",
            )

        # --------------------------------------------------
        # 2. Polite closures – delegate to AI
        # --------------------------------------------------
        polite_closures = {
            "thanks", "thank you", "thanks a lot",
            "ok thanks", "okay thanks",
        }

        if text in polite_closures:
            return DecisionEnvelope(
                intent=intent,
                mode="CASUAL",
                response=Response(
                    speech=""
                ),
                reason="polite_closure_delegate",
            )

        # --------------------------------------------------
        # 3. Explicit GUIDE requests (HIGH PRIORITY)
        # --------------------------------------------------
        guide_triggers = (
            "step by step",
            "step-by-step",
            "guide me",
            "walk me through",
            "one by one",
        )

        if any(trigger in text for trigger in guide_triggers):
            return DecisionEnvelope(
                intent=intent,
                mode="GUIDE",
                response=Response(
                    speech="Okay. I’ll explain it step by step."
                ),
                flags={"interruptible": True},
                reason="guide_request",
            )

        # --------------------------------------------------
        # 4. Incomplete / dangling input
        # (LESS AGGRESSIVE — allows normal small talk)
        # --------------------------------------------------

        # Do NOT treat common conversational phrases as incomplete
        chat_like_phrases = (
            "how are you",
            "what's up",
            "how are things",
            "how are you doing",
        )

        if intent == Intent.UNKNOWN:
            if any(p in text for p in chat_like_phrases):
                pass  # allow normal processing
            elif len(text.split()) <= 2:
                return DecisionEnvelope(
                    intent=intent,
                    mode="GUIDE",
                    response=Response(
                        speech="Could you please complete your question or tell me what you want me to do?"
                    ),
                    reason="incomplete_input",
                )


        # --------------------------------------------------
        # 4.5 Low-confidence COMMAND guard (noise safety)
        # --------------------------------------------------
        if intent == Intent.COMMAND and confidence < LOW_COMMAND_CONFIDENCE:
            return DecisionEnvelope(
                intent=intent,
                mode="CASUAL",
                response=Response(
                    speech="I might have misunderstood. Could you please repeat that?"
                ),
                reason="low_confidence_command",
            )

        # --------------------------------------------------
        # 5. High-level autonomous COMMANDS
        # --------------------------------------------------
        if intent == Intent.COMMAND:

            # --- AUTONOMOUS BEHAVIORS ---
            if "explore" in tokens:
                return DecisionEnvelope(
                    intent=intent,
                    mode="DECISION",
                    response=Response(
                        speech="Okay, I’ll explore the area and avoid obstacles."
                    ),
                    behavior=Behavior(type="EXPLORE"),
                    reason="autonomy_explore",
                )

            if "follow" in tokens:
                return DecisionEnvelope(
                    intent=intent,
                    mode="DECISION",
                    response=Response(
                        speech="I’ll follow you. Please move slowly."
                    ),
                    behavior=Behavior(type="FOLLOW_PERSON"),
                    reason="autonomy_follow",
                )

            if "stop" in tokens:
                return DecisionEnvelope(
                    intent=intent,
                    mode="SAFETY",
                    response=Response(
                        speech="Stopping now."
                    ),
                    behavior=Behavior(type="STOP"),
                    reason="explicit_stop",
                )

            # --- UNKNOWN / UNSAFE COMMAND ---
            return DecisionEnvelope(
                intent=intent,
                mode="SAFETY",
                response=Response(
                    speech="I’m not sure how to do that safely."
                ),
                reason="unknown_command",
            )

        # --------------------------------------------------
        # 6. Questions → Mentor mode, delegate to AI
        # --------------------------------------------------
        if intent == Intent.QUESTION:
            return DecisionEnvelope(
                intent=intent,
                mode="MENTOR",
                response=Response(
                    speech=""
                ),
                reason="question_delegate",
            )

        # --------------------------------------------------
        # 7. Chat / default fallback (delegate to AI)
        # --------------------------------------------------
        return DecisionEnvelope(
            intent=intent,
            mode="MENTOR",
            response=Response(
                speech=""
            ),
            reason="default_fallback",
        )
