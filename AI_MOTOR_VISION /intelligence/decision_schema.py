# intelligence/decision_schema.py

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from intelligence.intent_classifier import Intent


@dataclass
class Response:
    speech: str


@dataclass
class Behavior:
    type: str                  # EXPLORE, FOLLOW_PERSON, GO_TO_OBJECT, STOP
    target: Optional[str] = None


@dataclass
class DecisionEnvelope:
    intent: Intent
    mode: str                 # NOTE: In AI_MOTOR_VISION only DECISION and SAFETY are used
    response: Response

    behavior: Optional[Behavior] = None
    tools: Optional[List[Dict]] = None

    flags: Dict = field(default_factory=lambda: {
        "interruptible": True,
        "requires_confirmation": False
    })

    reason: str = ""

