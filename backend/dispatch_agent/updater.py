"""LLM state updater: turns each homeowner message into an updated lead state.

One Claude call per turn with structured output. The model returns the full updated
state (not a diff), so corrections and cleared fields need no merge logic, plus a draft
of the next question. Code then validates the output before it becomes the new state.
"""

import json
import logging
from dataclasses import asdict, dataclass

import anthropic

from dispatch_agent.config import LLM_EFFORT, LLM_MAX_TOKENS, LLM_MODEL
from dispatch_agent.lead import Confidence, LeadState, RequiredField, Urgency, missing_fields

log = logging.getLogger(__name__)

# Used when the LLM call fails, so the conversation can continue.
FALLBACK_QUESTIONS = {
    RequiredField.CATEGORY: "Could you tell me a bit more about the problem you're seeing?",
    RequiredField.ZIP_CODE: "What's the ZIP code where the work is needed?",
    RequiredField.URGENCY: "How soon do you need someone: today, in the next few days, or no rush?",
    RequiredField.CONTACT_NAME: "What name should the provider ask for?",
    RequiredField.CONTACT_PHONE: "What's the best phone number for the provider to reach you?",
}
DONE_MESSAGE = "Thanks, that's everything I need."

SYSTEM_PROMPT = """\
You are the intake assistant for a home-services marketplace in the Chicago area. A \
homeowner describes a problem; you keep a lead state up to date and ask one question at a \
time until a local provider can be dispatched.

Each turn you get the current lead state and the homeowner's new message. Return the \
complete updated state: keep every value you already have unless the homeowner corrects \
or retracts it, and add anything new they told you.

## Fields

- problem_summary: one or two sentences with the specifics a provider needs: what's \
wrong, which equipment, where in the home, since when. Rewrite it as you learn more.
- category: the service category that fits the problem, from the list below.
- category_confidence:
  - high: the category is clear (e.g. "my AC stopped blowing cold air" is hvac).
  - medium: one category is likely but another is plausible.
  - low: the problem could belong to several categories.
- alternate_category: the runner-up when confidence is below high, otherwise null.
- urgency:
  - emergency: needs someone now or today (active leak, no heat in winter, hazard).
  - soon: within a few days.
  - flexible: no rush, or getting quotes.
  Only set urgency when the homeowner says or clearly implies it; don't guess.
- zip_code, contact_name, contact_phone: exactly as the homeowner gives them.
- safety_alert: true when there is a hazard (gas smell, sparking or burning smell from \
wiring, water near the electrical panel, carbon monoxide alarm). Once true, keep it true.

Leave any field you don't know as null.

## Service categories

{categories}

## Next question

Draft the next question for the first required field that is still missing after your \
update, in this order:
1. category: missing until confidence is high. Ask a question that tells the category \
apart from the alternate (e.g. "Is the water coming from a pipe, or seeping in through \
the walls or floor?").
2. zip_code
3. urgency
4. contact_name
5. contact_phone

Set question_field to that field. If nothing is missing, set question_field to null and \
next_question to a short thank-you.

Ask exactly one question, in plain, friendly language, briefly acknowledging what they \
said. If safety_alert is true, start with short safety guidance (e.g. leave the house and \
call the gas company from outside) before the question.
"""


@dataclass
class Update:
    state: LeadState
    next_question: str
    question_field: RequiredField | None  # the field next_question asks for


def load_categories(conn):
    """Service categories as (name, description) pairs, from the database."""
    rows = conn.execute("SELECT name, description FROM service_categories ORDER BY id")
    return [(row["name"], row["description"]) for row in rows]


def system_prompt(categories):
    listing = "\n".join(f"- {name}: {description}" for name, description in categories)
    return SYSTEM_PROMPT.format(categories=listing)


def _nullable(values):
    return {"anyOf": [{"type": "string", "enum": list(values)}, {"type": "null"}]}


def output_schema(categories):
    names = [name for name, _ in categories]
    nullable_string = {"type": ["string", "null"]}
    properties = {
        "problem_summary": nullable_string,
        "category": _nullable(names),
        "category_confidence": _nullable(list(Confidence)),
        "alternate_category": _nullable(names),
        "urgency": _nullable(list(Urgency)),
        "zip_code": nullable_string,
        "contact_name": nullable_string,
        "contact_phone": nullable_string,
        "safety_alert": {"type": "boolean"},
        "next_question": {"type": "string"},
        "question_field": _nullable(list(RequiredField)),
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def user_turn(state, message):
    return (
        f"Current lead state:\n{json.dumps(asdict(state), indent=2)}\n\n"
        f"New message from the homeowner:\n{message}"
    )


def _clean(value):
    """Strip a string, treating empty as missing."""
    if value is None:
        return None
    return value.strip() or None


def parse_output(data, categories):
    """Validate the model's output into an Update, dropping values code can't trust."""
    names = {name for name, _ in categories}
    category = data.get("category") if data.get("category") in names else None
    confidence = data.get("category_confidence") if category else None
    alternate = data.get("alternate_category")
    if alternate not in names or alternate == category:
        alternate = None

    state = LeadState(
        problem_summary=_clean(data.get("problem_summary")),
        category=category,
        category_confidence=Confidence(confidence) if confidence else None,
        alternate_category=alternate,
        urgency=Urgency(data["urgency"]) if data.get("urgency") else None,
        zip_code=_clean(data.get("zip_code")),
        contact_name=_clean(data.get("contact_name")),
        contact_phone=_clean(data.get("contact_phone")),
        safety_alert=bool(data.get("safety_alert")),
    )
    field = data.get("question_field")
    return Update(
        state=state,
        next_question=data.get("next_question") or "",
        question_field=RequiredField(field) if field else None,
    )


def fallback_update(state):
    """Keep the previous state and ask a canned question for the top missing field."""
    missing = missing_fields(state)
    if not missing:
        return Update(state=state, next_question=DONE_MESSAGE, question_field=None)
    return Update(
        state=state, next_question=FALLBACK_QUESTIONS[missing[0]], question_field=missing[0]
    )


def update_lead(client, categories, state, history, message):
    """Run one turn: the new message plus the current state -> updated state and next question.

    `history` is the earlier conversation as Messages API turns
    ({"role": "user" | "assistant", "content": str}), without the new message.
    """
    try:
        response = client.beta.messages.create(
            model=LLM_MODEL,
            max_tokens=LLM_MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": system_prompt(categories),
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[*history, {"role": "user", "content": user_turn(state, message)}],
            output_config={
                "effort": LLM_EFFORT,
                "format": {"type": "json_schema", "schema": output_schema(categories)},
            },
            # On a safety refusal, the API retries on a fallback model it picks.
            fallbacks="default",
            betas=["server-side-fallback-2026-07-01"],
        )
    # Only transient failures fall back; a 400 is a bug in the request and should surface.
    except (
        anthropic.APIConnectionError,
        anthropic.RateLimitError,
        anthropic.InternalServerError,
    ):
        log.exception("state updater call failed")
        return fallback_update(state)

    if response.stop_reason in ("refusal", "max_tokens"):
        log.warning("state updater stopped early: %s", response.stop_reason)
        return fallback_update(state)
    text = next((b.text for b in response.content if b.type == "text"), None)
    try:
        return parse_output(json.loads(text), categories)
    except TypeError, ValueError:
        log.exception("state updater returned invalid output")
        return fallback_update(state)
