# intelligence/planner.py

from intelligence.intent_classifier import Intent
from intelligence.decision_schema import (
    DecisionEnvelope,
    Response,
    Behavior,
)
from utils.logger import setup_logger
logger = setup_logger("AI", log_file="ai.log")

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
        context: str,
    ) -> DecisionEnvelope:
        """
        Core decision entry point.
        This function MUST always return a valid DecisionEnvelope.
        """

        text = (user_text or "").strip().lower()
        tokens = set(text.split())

        if intent == Intent.ENROLL:
            return DecisionEnvelope(
                intent=intent,
                mode="DECISION",
                response=Response(
                    speech=""  # Brain will speak, not planner
                ),
                reason="face_enrollment",
            )


        # --------------------------------------------------
        # 0. Empty / noise input
        # --------------------------------------------------
        if not text:
            return DecisionEnvelope(
                intent=intent,
                mode="SAFETY",
                response=Response(
                    speech="I can only follow movement or vision commands."
                ),
                reason="unsupported_input",
            )

        if intent == Intent.SCENE_QUERY:
            return DecisionEnvelope(
                intent=intent,
                mode="DECISION",
                response=Response(speech=""),  # Brain will speak
                reason="scene_query",
            )               

        # --------------------------------------------------
        # 5. High-level autonomous COMMANDS
        # --------------------------------------------------
        if intent == Intent.COMMAND:

            # --- GO TO OBJECT ---
            text_l = (user_text or "").strip().lower()
            if "go to" in text_l or "move to" in text_l:
                # extract target object
                obj = ""
                if "go to" in text_l:
                    parts = text_l.split("go to", 1)
                else:
                    parts = text_l.split("move to", 1)
                if len(parts) > 1:
                    obj = parts[1].strip().split()[0] if parts[1].strip() else ""
                if obj:
                    return DecisionEnvelope(
                        intent=intent,
                        mode="DECISION",
                        response=Response(speech=f"Going to the {obj}."),
                        behavior=Behavior(type="GO_TO_OBJECT", target=obj),
                        reason="go_to_object",
                    )

            # --- AUTONOMOUS BEHAVIORS ---
            if "explore" in tokens:
                return DecisionEnvelope(
                    intent=intent,
                    mode="DECISION",
                    response=Response(
                        speech="Exploring the area."
                    ),
                    behavior=Behavior(type="EXPLORE"),
                    reason="autonomy_explore",
                )

            if "follow" in tokens:
                return DecisionEnvelope(
                    intent=intent,
                    mode="DECISION",
                    response=Response(
                        speech="Following you."
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
        # FINAL FALLBACK (non-command input)
        # --------------------------------------------------
        return DecisionEnvelope(
            intent=intent,
            mode="SAFETY",
            response=Response(
                speech="I can only follow movement or vision commands."
            ),
            reason="unsupported_input",
        )

