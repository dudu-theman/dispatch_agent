from dataclasses import replace

import pytest

from dispatch_agent.lead import (
    Confidence,
    LeadState,
    RequiredField,
    Urgency,
    is_dispatchable,
    missing_fields,
    normalize_phone,
    normalize_zip,
)

COMPLETE = LeadState(
    problem_summary="Water heater leaking from the bottom in the basement since this morning.",
    category="plumbing",
    category_confidence=Confidence.HIGH,
    urgency=Urgency.SOON,
    zip_code="60614",
    contact_name="Sam",
    contact_phone="(312) 555-0100",
)

# The fields each RequiredField reads, cleared to show that field as missing.
CLEARED = {
    RequiredField.CATEGORY: {"category": None, "category_confidence": None},
    RequiredField.ZIP_CODE: {"zip_code": None},
    RequiredField.URGENCY: {"urgency": None},
    RequiredField.CONTACT_NAME: {"contact_name": None},
    RequiredField.CONTACT_PHONE: {"contact_phone": None},
}


def test_empty_state_is_missing_everything_in_order():
    assert missing_fields(LeadState()) == [
        RequiredField.CATEGORY,
        RequiredField.ZIP_CODE,
        RequiredField.URGENCY,
        RequiredField.CONTACT_NAME,
        RequiredField.CONTACT_PHONE,
    ]
    assert not is_dispatchable(LeadState())


def test_complete_state_is_dispatchable():
    assert missing_fields(COMPLETE) == []
    assert is_dispatchable(COMPLETE)


@pytest.mark.parametrize("field", list(RequiredField))
def test_clearing_one_field_reports_only_that_field(field):
    state = replace(COMPLETE, **CLEARED[field])
    assert missing_fields(state) == [field]
    assert not is_dispatchable(state)


def test_missing_fields_keep_ask_order():
    state = replace(COMPLETE, contact_phone=None, urgency=None, category=None)
    assert missing_fields(state) == [
        RequiredField.CATEGORY,
        RequiredField.URGENCY,
        RequiredField.CONTACT_PHONE,
    ]


@pytest.mark.parametrize("confidence", [None, Confidence.LOW, Confidence.MEDIUM])
def test_category_below_high_confidence_is_missing(confidence):
    state = replace(COMPLETE, category_confidence=confidence)
    assert missing_fields(state) == [RequiredField.CATEGORY]


def test_confidence_without_category_is_missing():
    state = replace(COMPLETE, category=None)
    assert missing_fields(state) == [RequiredField.CATEGORY]


def test_safety_alert_does_not_affect_completeness():
    assert is_dispatchable(replace(COMPLETE, safety_alert=True))
    assert missing_fields(replace(LeadState(), safety_alert=True)) == missing_fields(LeadState())


@pytest.mark.parametrize(
    "field, value",
    [
        (RequiredField.ZIP_CODE, "6061"),
        (RequiredField.ZIP_CODE, "Chicago"),
        (RequiredField.CONTACT_NAME, "   "),
        (RequiredField.CONTACT_PHONE, "555-0100"),
    ],
)
def test_invalid_values_count_as_missing(field, value):
    assert missing_fields(replace(COMPLETE, **{field.value: value})) == [field]


@pytest.mark.parametrize(
    "value, expected",
    [
        ("60614", "60614"),
        (" 60614 ", "60614"),
        ("60614-1234", "60614"),
        ("6061", None),
        ("606140", None),
        ("60614-12", None),
        ("abcde", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_zip(value, expected):
    assert normalize_zip(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("3125550100", "3125550100"),
        ("(312) 555-0100", "3125550100"),
        ("312.555.0100", "3125550100"),
        ("+1 312-555-0100", "3125550100"),
        ("1-312-555-0100", "3125550100"),
        ("312-555-010", None),  # 9 digits
        ("2-312-555-0100", None),  # 11 digits, not a +1 prefix
        ("012-555-0100", None),  # area code starts with 0
        ("312-155-0100", None),  # exchange starts with 1
        ("call me", None),
        ("", None),
        (None, None),
    ],
)
def test_normalize_phone(value, expected):
    assert normalize_phone(value) == expected
