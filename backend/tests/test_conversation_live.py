"""A full conversation against the real model, from first message to lead.

Opt-in, since it costs money: `uv run pytest -m llm`.
"""

import anthropic
import pytest

from dispatch_agent.conversation import Conversation, handle_message
from dispatch_agent.lead import Urgency
from dispatch_agent.updater import load_categories

pytestmark = pytest.mark.llm


def test_clogged_sink_becomes_a_lead(conn):
    client, categories = anthropic.Anthropic(), load_categories(conn)
    conversation = Conversation()
    # Answers in the order the agent asks: category is clear, then ZIP, urgency, contact.
    for message in [
        "My kitchen sink drain is completely clogged and won't drain at all",
        "60601",
        "Within the next couple of days is fine",
        "Sam",
        "312-555-0100",
    ]:
        reply = handle_message(client, conn, categories, conversation, message)

    lead = reply.lead
    assert lead is not None
    assert lead.category == "plumbing"
    assert lead.urgency == Urgency.SOON
    assert lead.zip_code == "60601" and lead.contact_phone == "3125550100"
    assert lead.providers
