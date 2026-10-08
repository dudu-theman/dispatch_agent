"""Fake Anthropic client for tests that don't call the real model."""

import json
from types import SimpleNamespace


def _response(text, stop_reason="end_turn"):
    return SimpleNamespace(
        stop_reason=stop_reason, content=[SimpleNamespace(type="text", text=text)]
    )


class FakeMessages:
    def __init__(self, responses, error=None):
        self.responses, self.error, self.calls = responses, error, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        # The Nth call gets the Nth response; the last one repeats.
        return self.responses[min(len(self.calls), len(self.responses)) - 1]


def _client(messages):
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def fake_client(output=None, stop_reason="end_turn", text=None, error=None):
    """Client whose every call returns `output` as JSON (or raw `text`, or raises `error`)."""
    text = json.dumps(output) if text is None else text
    return _client(FakeMessages([_response(text, stop_reason)], error))


def scripted_client(outputs):
    """Client whose Nth call returns outputs[N] as JSON."""
    return _client(FakeMessages([_response(json.dumps(output)) for output in outputs]))
