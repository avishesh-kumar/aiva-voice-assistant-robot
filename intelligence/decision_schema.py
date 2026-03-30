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
    mode: str                  # CASUAL, MENTOR, GUIDE, DECISION, SAFETY, etc.
    response: Response

    behavior: Optional[Behavior] = None
    tools: Optional[List[Dict]] = None

    flags: Dict = field(default_factory=lambda: {
        "interruptible": True,
        "requires_confirmation": False
    })

    reason: str = ""

