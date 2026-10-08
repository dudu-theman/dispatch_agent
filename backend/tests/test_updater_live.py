"""Example conversations run against the real model.

Opt-in, since they cost money: `uv run pytest -m llm`. Assertions check fields, not wording.
"""

import anthropic
import pytest

from dispatch_agent.lead import Confidence, LeadState, RequiredField, Urgency
from dispatch_agent.updater import load_categories, update_lead

pytestmark = pytest.mark.llm


@pytest.fixture(scope="module")
def client():
    return anthropic.Anthropic()


@pytest.fixture(scope="module")
def categories(conn):
    return load_categories(conn)


def run(client, categories, messages):
    """Play user messages through the updater, returning the last update."""
    state, history = LeadState(), []
    for message in messages:
        update = update_lead(client, categories, state, history, message)
        history += [
            {"role": "user", "content": message},
            {"role": "assistant", "content": update.next_question},
        ]
        state = update.state
    return update


def test_basement_water_is_ambiguous(client, categories):
    update = run(client, categories, ["There's water in my basement after the storm"])
    state = update.state
    assert state.category_confidence != Confidence.HIGH
    pair = {state.category, state.alternate_category}
    assert pair & {"basement_waterproofing", "water_damage_restoration"}
    assert update.question_field == RequiredField.CATEGORY


def test_clarified_basement_water_becomes_confident(client, categories):
    update = run(
        client,
        categories,
        [
            "There's water in my basement after the storm",
            "It's seeping in through a crack in the foundation wall, no pipes nearby",
        ],
    )
    assert update.state.category == "basement_waterproofing"
    assert update.state.category_confidence == Confidence.HIGH
    assert update.question_field == RequiredField.ZIP_CODE


def test_dead_ac_in_a_heatwave(client, categories):
    update = run(
        client, categories, ["My AC died and it's 95 degrees, I need someone today. 60614"]
    )
    state = update.state
    assert state.category == "hvac" and state.category_confidence == Confidence.HIGH
    assert state.urgency == Urgency.EMERGENCY
    assert state.zip_code == "60614"
    assert update.question_field == RequiredField.CONTACT_NAME


def test_gas_smell_sets_safety_alert(client, categories):
    update = run(client, categories, ["I smell gas near my water heater"])
    assert update.state.safety_alert


def test_facts_carry_over_and_corrections_overwrite(client, categories):
    update = run(
        client,
        categories,
        [
            "My kitchen sink drain is completely clogged",
            "60614",
            "Within the next couple days is fine",
            "Sorry, the ZIP is actually 60657",
            "I'm Sam",
            "312-555-0100",
        ],
    )
    state = update.state
    assert state.category == "plumbing"
    assert state.zip_code == "60657"
    assert state.urgency == Urgency.SOON
    assert state.contact_name == "Sam"
    assert state.contact_phone is not None
    assert update.question_field is None
