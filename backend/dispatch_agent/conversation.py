"""Turn handler: one homeowner message in, one question or a finished lead out.

Each turn the LLM updates the lead state, then plain code decides whether the lead is
dispatchable. If not, the agent asks for the top missing field; if so, it searches
providers and returns the lead.
"""

import threading
from dataclasses import dataclass, field

from dispatch_agent.lead import (
    LeadState,
    RequiredField,
    Urgency,
    missing_fields,
    normalize_phone,
    normalize_zip,
)
from dispatch_agent.providers import Provider, UnknownZipError, search_providers
from dispatch_agent.updater import FALLBACK_QUESTIONS, update_lead

GREETING = "Hi! What's going on at your home that you need help with?"
SAFETY_MESSAGE = (
    "If you're in any danger, leave the area and call 911 or your utility company from outside."
)
UNKNOWN_ZIP_QUESTION = "I couldn't find the ZIP code {zip_code}. Could you double-check it?"
LEAD_MESSAGE = "Thanks, that's everything I need. Here are top-rated providers near you."
NO_PROVIDERS_MESSAGE = (
    "Thanks, that's everything I need. We don't have a matching provider near you yet, "
    "but we've saved your request."
)


class ConversationClosedError(Exception):
    """The conversation already produced a lead."""


@dataclass
class Lead:
    problem_summary: str | None
    category: str
    urgency: Urgency
    zip_code: str
    contact_name: str
    contact_phone: str  # 10 digits
    safety_alert: bool
    providers: list[Provider]  # best first; empty if none are in range


@dataclass
class Reply:
    message: str
    safety_alert: bool
    question_field: RequiredField | None = None  # set while asking a question
    lead: Lead | None = None  # set once the lead is dispatchable


@dataclass
class Conversation:
    state: LeadState = field(default_factory=LeadState)
    # Earlier turns as Messages API turns, with the homeowner's raw text.
    history: list[dict] = field(default_factory=list)
    lead: Lead | None = None
    # Held while a turn runs, so concurrent messages can't overwrite each other's state.
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)


def _with_safety(state, message):
    """Lead a message written by code with safety guidance when there is a hazard."""
    return f"{SAFETY_MESSAGE} {message}" if state.safety_alert else message


def _question(update, top_missing):
    """Use the LLM's draft if it asks for the top missing field, else a canned question."""
    state = update.state
    if update.next_question and update.question_field == top_missing:
        message = update.next_question  # the draft already carries any safety guidance
    else:
        message = _with_safety(state, FALLBACK_QUESTIONS[top_missing])
    return Reply(message=message, safety_alert=state.safety_alert, question_field=top_missing)


def _dispatch(conn, conversation):
    """Search providers for a complete state and close the conversation with a lead."""
    state = conversation.state
    zip_code = normalize_zip(state.zip_code)
    try:
        providers = search_providers(conn, state.category, zip_code)
    except UnknownZipError:
        state.zip_code = None
        message = _with_safety(state, UNKNOWN_ZIP_QUESTION.format(zip_code=zip_code))
        return Reply(
            message=message, safety_alert=state.safety_alert, question_field=RequiredField.ZIP_CODE
        )

    conversation.lead = Lead(
        problem_summary=state.problem_summary,
        category=state.category,
        urgency=state.urgency,
        zip_code=zip_code,
        contact_name=state.contact_name.strip(),
        contact_phone=normalize_phone(state.contact_phone),
        safety_alert=state.safety_alert,
        providers=providers,
    )
    message = _with_safety(state, LEAD_MESSAGE if providers else NO_PROVIDERS_MESSAGE)
    return Reply(message=message, safety_alert=state.safety_alert, lead=conversation.lead)


def handle_message(client, conn, categories, conversation, message):
    """Run one turn of `conversation` and return the reply to show the homeowner.

    Raises ConversationClosedError if the conversation already produced a lead.
    """
    if conversation.lead is not None:
        raise ConversationClosedError
    update = update_lead(client, categories, conversation.state, conversation.history, message)
    conversation.state = update.state

    missing = missing_fields(update.state)
    reply = _question(update, missing[0]) if missing else _dispatch(conn, conversation)
    conversation.history += [
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply.message},
    ]
    return reply
