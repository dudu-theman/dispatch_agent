import pytest
from fakes import fake_client, scripted_client

from dispatch_agent.config import TOP_N
from dispatch_agent.conversation import (
    LEAD_MESSAGE,
    NO_PROVIDERS_MESSAGE,
    SAFETY_MESSAGE,
    Conversation,
    ConversationClosedError,
    handle_message,
)
from dispatch_agent.lead import RequiredField, Urgency
from dispatch_agent.updater import FALLBACK_QUESTIONS

CATEGORIES = [
    ("plumbing", "Pipes, drains, and plumbing leaks."),
    ("basement_waterproofing", "Foundation cracks, seepage, sump pumps."),
]

NEEDS_ZIP = {
    "problem_summary": "Kitchen sink drain completely clogged.",
    "category": "plumbing",
    "category_confidence": "high",
    "alternate_category": None,
    "urgency": None,
    "zip_code": None,
    "contact_name": None,
    "contact_phone": None,
    "safety_alert": False,
    "next_question": "Got it, a clogged sink. What's your ZIP code?",
    "question_field": "zip_code",
}

COMPLETE = {
    **NEEDS_ZIP,
    "urgency": "soon",
    "zip_code": "60601",
    "contact_name": "Sam",
    "contact_phone": "(312) 555-0100",
    "next_question": "Thanks!",
    "question_field": None,
}


def turn(conn, output, message="hello", conversation=None):
    client, _ = fake_client(output)
    conversation = conversation or Conversation()
    return handle_message(client, conn, CATEGORIES, conversation, message), conversation


def test_asks_the_drafted_question_for_the_top_missing_field(conn):
    reply, conversation = turn(conn, NEEDS_ZIP, "My kitchen sink is clogged")
    assert reply.message == NEEDS_ZIP["next_question"]
    assert reply.question_field == RequiredField.ZIP_CODE
    assert reply.lead is None
    assert conversation.state.category == "plumbing"


def test_off_target_draft_is_replaced_with_a_canned_question(conn):
    output = {**NEEDS_ZIP, "next_question": "How soon?", "question_field": "urgency"}
    reply, _ = turn(conn, output)
    assert reply.message == FALLBACK_QUESTIONS[RequiredField.ZIP_CODE]
    assert reply.question_field == RequiredField.ZIP_CODE


def test_canned_question_leads_with_safety_guidance(conn):
    output = {**NEEDS_ZIP, "safety_alert": True, "question_field": None}
    reply, _ = turn(conn, output)
    assert reply.message == f"{SAFETY_MESSAGE} {FALLBACK_QUESTIONS[RequiredField.ZIP_CODE]}"
    assert reply.safety_alert


def test_complete_state_returns_a_lead_with_providers(conn):
    reply, conversation = turn(conn, COMPLETE)
    lead = reply.lead
    assert reply.message == LEAD_MESSAGE and reply.question_field is None
    assert conversation.lead is lead
    assert lead.category == "plumbing" and lead.urgency == Urgency.SOON
    assert lead.zip_code == "60601"
    assert lead.contact_name == "Sam" and lead.contact_phone == "3125550100"
    assert len(lead.providers) == TOP_N


def test_no_providers_nearby_still_returns_the_lead(conn):
    reply, _ = turn(conn, {**COMPLETE, "zip_code": "90210"})
    assert reply.lead.providers == []
    assert reply.message == NO_PROVIDERS_MESSAGE


def test_unknown_zip_is_cleared_and_asked_again(conn):
    reply, conversation = turn(conn, {**COMPLETE, "zip_code": "00000"})
    assert reply.lead is None and conversation.lead is None
    assert reply.question_field == RequiredField.ZIP_CODE
    assert "00000" in reply.message
    assert conversation.state.zip_code is None


def test_closed_conversation_raises(conn):
    _, conversation = turn(conn, COMPLETE)
    with pytest.raises(ConversationClosedError):
        turn(conn, COMPLETE, conversation=conversation)


def test_history_keeps_raw_messages_and_replies(conn):
    client, messages = scripted_client([NEEDS_ZIP, COMPLETE])
    conversation = Conversation()
    first = handle_message(client, conn, CATEGORIES, conversation, "My sink is clogged")
    handle_message(client, conn, CATEGORIES, conversation, "60601")

    earlier_turns = [
        {"role": "user", "content": "My sink is clogged"},
        {"role": "assistant", "content": first.message},
    ]
    assert messages.calls[1]["messages"][:2] == earlier_turns
    assert len(conversation.history) == 4
