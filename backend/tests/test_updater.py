import anthropic
import httpx2
import pytest
from fakes import fake_client

from dispatch_agent.lead import Confidence, LeadState, RequiredField, Urgency
from dispatch_agent.updater import (
    DONE_MESSAGE,
    FALLBACK_QUESTIONS,
    load_categories,
    output_schema,
    parse_output,
    update_lead,
)

CATEGORIES = [
    ("plumbing", "Pipes, drains, and plumbing leaks."),
    ("basement_waterproofing", "Foundation cracks, seepage, sump pumps."),
]

OUTPUT = {
    "problem_summary": "Water seeping through a basement wall crack since last night's storm.",
    "category": "basement_waterproofing",
    "category_confidence": "high",
    "alternate_category": None,
    "urgency": None,
    "zip_code": "60657",
    "contact_name": None,
    "contact_phone": None,
    "safety_alert": False,
    "next_question": "How soon do you need someone out?",
    "question_field": "urgency",
}


def test_load_categories_reads_the_database(conn):
    names = [name for name, _ in load_categories(conn)]
    assert "plumbing" in names and "basement_waterproofing" in names


def test_schema_limits_categories_to_the_list():
    schema = output_schema(CATEGORIES)
    assert schema["properties"]["category"]["anyOf"] == [
        {"type": "string", "enum": ["plumbing", "basement_waterproofing"]},
        {"type": "null"},
    ]
    assert set(schema["required"]) == set(schema["properties"])


def test_update_lead_returns_the_parsed_state():
    client, _ = fake_client(OUTPUT)
    update = update_lead(client, CATEGORIES, LeadState(), [], "It's coming through a crack.")
    assert update.state.category == "basement_waterproofing"
    assert update.state.category_confidence == Confidence.HIGH
    assert update.state.zip_code == "60657"
    assert update.question_field == RequiredField.URGENCY
    assert update.next_question == "How soon do you need someone out?"


def test_request_includes_categories_history_state_and_message():
    client, messages = fake_client(OUTPUT)
    history = [
        {"role": "user", "content": "Water in my basement"},
        {"role": "assistant", "content": "What's your ZIP?"},
    ]
    state = LeadState(zip_code="60614")
    update_lead(client, CATEGORIES, state, history, "60657, sorry")

    request = messages.calls[0]
    assert "basement_waterproofing: Foundation cracks" in request["system"][0]["text"]
    assert request["messages"][:2] == history
    last = request["messages"][-1]
    assert last["role"] == "user"
    assert '"zip_code": "60614"' in last["content"] and "60657, sorry" in last["content"]


def test_unknown_categories_are_dropped():
    data = {**OUTPUT, "category": "roofing", "alternate_category": "plumbing"}
    state = parse_output(data, CATEGORIES).state
    assert state.category is None and state.category_confidence is None
    assert state.alternate_category == "plumbing"


def test_alternate_matching_category_is_dropped():
    data = {**OUTPUT, "alternate_category": "basement_waterproofing"}
    assert parse_output(data, CATEGORIES).state.alternate_category is None


def test_blank_strings_count_as_missing():
    data = {**OUTPUT, "contact_name": "  ", "zip_code": " 60657 "}
    state = parse_output(data, CATEGORIES).state
    assert state.contact_name is None and state.zip_code == "60657"


def test_nothing_missing_has_no_question_field():
    data = {**OUTPUT, "question_field": None, "next_question": "Thanks!"}
    assert parse_output(data, CATEGORIES).question_field is None


STATE = LeadState(category="plumbing", category_confidence=Confidence.HIGH)


@pytest.mark.parametrize(
    "client_args",
    [
        {"error": anthropic.APIConnectionError(request=httpx2.Request("POST", "https://x"))},
        {"output": OUTPUT, "stop_reason": "refusal"},
        {"output": OUTPUT, "stop_reason": "max_tokens"},
        {"text": "not json"},
        {"output": {**OUTPUT, "urgency": "whenever"}},
    ],
    ids=["api-error", "refusal", "max-tokens", "invalid-json", "invalid-enum"],
)
def test_failures_keep_the_state_and_ask_for_the_top_missing_field(client_args):
    client, _ = fake_client(**client_args)
    update = update_lead(client, CATEGORIES, STATE, [], "hello")
    assert update.state == STATE
    assert update.question_field == RequiredField.ZIP_CODE
    assert update.next_question == FALLBACK_QUESTIONS[RequiredField.ZIP_CODE]


def test_bad_requests_raise():
    request = httpx2.Request("POST", "https://x")
    error = anthropic.BadRequestError(
        "bad schema", response=httpx2.Response(400, request=request), body=None
    )
    client, _ = fake_client(error=error)
    with pytest.raises(anthropic.BadRequestError):
        update_lead(client, CATEGORIES, STATE, [], "hello")


def test_failure_on_a_complete_lead_says_thanks():
    state = LeadState(
        category="plumbing",
        category_confidence=Confidence.HIGH,
        urgency=Urgency.SOON,
        zip_code="60614",
        contact_name="Sam",
        contact_phone="312-555-0100",
    )
    client, _ = fake_client(text="not json")
    update = update_lead(client, CATEGORIES, state, [], "thanks")
    assert update.next_question == DONE_MESSAGE and update.question_field is None
