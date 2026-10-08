import pytest
from fakes import scripted_client
from fastapi.testclient import TestClient
from test_conversation import CATEGORIES, COMPLETE, NEEDS_ZIP

from dispatch_agent.api import app, get_categories, get_client
from dispatch_agent.config import MAX_MESSAGE_CHARS, TOP_N
from dispatch_agent.conversation import GREETING


@pytest.fixture
def http():
    app.dependency_overrides[get_categories] = lambda: CATEGORIES
    yield TestClient(app)
    app.dependency_overrides.clear()


def use_llm(*outputs):
    llm, _ = scripted_client(outputs)
    app.dependency_overrides[get_client] = lambda: llm


def start(http):
    response = http.post("/conversations")
    assert response.status_code == 201
    return response.json()


def test_start_returns_an_id_and_a_greeting(http):
    body = start(http)
    assert body["conversation_id"] and body["message"] == GREETING


def test_conversation_runs_to_a_lead_then_closes(http):
    use_llm(NEEDS_ZIP, COMPLETE)
    url = f"/conversations/{start(http)['conversation_id']}/messages"

    question = http.post(url, json={"message": "My kitchen sink is clogged"}).json()
    assert question["type"] == "question"
    assert question["question_field"] == "zip_code"
    assert question["lead"] is None

    done = http.post(url, json={"message": "60601"}).json()
    assert done["type"] == "lead"
    assert done["lead"]["contact_phone"] == "3125550100"
    assert len(done["lead"]["providers"]) == TOP_N

    assert http.post(url, json={"message": "one more thing"}).status_code == 409


def test_unknown_conversation_is_404(http):
    use_llm(NEEDS_ZIP)
    response = http.post("/conversations/nope/messages", json={"message": "hi"})
    assert response.status_code == 404


@pytest.mark.parametrize("message", ["   ", "x" * (MAX_MESSAGE_CHARS + 1)], ids=["blank", "long"])
def test_invalid_messages_are_422(http, message):
    use_llm(NEEDS_ZIP)
    url = f"/conversations/{start(http)['conversation_id']}/messages"
    assert http.post(url, json={"message": message}).status_code == 422


def test_ui_origin_may_call_the_api(http):
    response = http.options(
        "/conversations",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
