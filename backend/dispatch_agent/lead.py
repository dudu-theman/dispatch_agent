"""Lead state: what the agent knows about a conversation, and whether it is dispatchable.

The LLM fills in the state each turn; plain code here decides what is still missing.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

from dispatch_agent.config import MIN_CATEGORY_CONFIDENCE


class Urgency(StrEnum):
    EMERGENCY = "emergency"  # needs someone now or today
    SOON = "soon"  # within a few days
    FLEXIBLE = "flexible"  # no rush, or getting quotes


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


CONFIDENCE_RANK = {c: i for i, c in enumerate(Confidence)}


class RequiredField(StrEnum):
    """Fields a lead needs before dispatch, in the order to ask for them.

    Contact comes last: asking for a phone number early hurts conversion.
    """

    CATEGORY = "category"
    ZIP_CODE = "zip_code"
    URGENCY = "urgency"
    CONTACT_NAME = "contact_name"
    CONTACT_PHONE = "contact_phone"


@dataclass
class LeadState:
    # One or two sentences with the specifics a provider needs: what's wrong, which
    # equipment, where in the home, since when.
    problem_summary: str | None = None
    category: str | None = None
    category_confidence: Confidence | None = None
    alternate_category: str | None = None  # runner-up, for an "is it X or Y?" question
    urgency: Urgency | None = None
    zip_code: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    safety_alert: bool = False  # a hazard: lead with safety guidance before any question


def normalize_zip(value):
    """5-digit ZIP from a ZIP or ZIP+4, or None if the format is invalid."""
    if not value:
        return None
    match = re.fullmatch(r"(\d{5})(-\d{4})?", value.strip())
    return match.group(1) if match else None


def normalize_phone(value):
    """10-digit US phone number with punctuation, a leading +1 and any extension removed,
    or None."""
    if not value:
        return None
    value = re.sub(r"(?i)\s*(?:ext\.?|extension|x|#)\s*\d+\s*$", "", value)
    digits = re.sub(r"\D", "", value)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    # US area codes and exchanges never start with 0 or 1.
    if len(digits) != 10 or digits[0] in "01" or digits[3] in "01":
        return None
    return digits


def category_is_known(state):
    return (
        bool(state.category)
        and state.category_confidence is not None
        and CONFIDENCE_RANK[state.category_confidence]
        >= CONFIDENCE_RANK[Confidence(MIN_CATEGORY_CONFIDENCE)]
    )


def missing_fields(state):
    """Required fields the lead still lacks, in the order to ask for them."""
    present = {
        RequiredField.CATEGORY: category_is_known(state),
        RequiredField.ZIP_CODE: normalize_zip(state.zip_code) is not None,
        RequiredField.URGENCY: state.urgency is not None,
        RequiredField.CONTACT_NAME: bool(state.contact_name and state.contact_name.strip()),
        RequiredField.CONTACT_PHONE: normalize_phone(state.contact_phone) is not None,
    }
    return [f for f in RequiredField if not present[f]]


def is_dispatchable(state):
    return not missing_fields(state)
