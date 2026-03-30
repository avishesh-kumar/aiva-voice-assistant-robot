# intelligence/guide/guide_controller.py

class GuideController:
    """
    Deterministic GUIDE flow controller.
    LLM is used only to explain ONE step at a time.
    """

    CONTINUE_WORDS = {
        "yes", "yeah", "ok", "okay",
        "continue", "next",
        "go on", "proceed"
    }


    def __init__(self, guide_state):
        self.state = guide_state

    # ---------------------------
    # GUIDE LIFECYCLE
    # ---------------------------

    def start(self, topic: str):
        self.state.active = True
        self.state.topic = topic
        self.state.step_index = 1

    def stop(self):
        self.state.reset()

    def is_active(self) -> bool:
        return self.state.active

    # ---------------------------
    # USER INPUT HANDLING
    # ---------------------------

    def is_continue(self, text: str) -> bool:
        tokens = set(text.strip().lower().split())
        return any(word in tokens for word in self.CONTINUE_WORDS)


    # ---------------------------
    # PROMPT BUILDERS
    # ---------------------------

    def build_step_prompt(self) -> str:
        """
        Build a STRICT one-action-only step prompt.
        """
        return (
            "You are in STEP-BY-STEP GUIDE MODE.\n\n"
            f"Topic: {self.state.topic}\n"
            f"Current step number: {self.state.step_index}\n\n"
            "VERY STRICT RULES (MUST FOLLOW):\n"
            "- A step means ONLY ONE physical or logical action.\n"
            "- Describe ONLY ONE action.\n"
            "- Do NOT combine multiple actions.\n"
            "- Do NOT use words like 'then', 'after', 'and then'.\n"
            "- Do NOT mention past or future steps.\n"
            "- Do NOT summarize.\n"
            "- Do NOT ask questions.\n"
            "- End immediately after describing that one action.\n\n"
            "Now describe ONLY ONE action for this step."
        )


    def next_step(self) -> str:
        """
        Advance to next step and return next prompt.
        """
        self.state.step_index += 1
        return self.build_step_prompt()
