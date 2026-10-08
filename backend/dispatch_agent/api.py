"""HTTP API: start a conversation, then send messages until it returns a lead.

Conversations live in memory for v1 and are lost on restart. The conversation id is a
random UUID, so it doubles as the only credential: whoever has it can continue the chat.
"""

import uuid
from contextlib import closing
from functools import cache
from typing import Annotated, Literal

import anthropic
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, StringConstraints

from dispatch_agent.config import MAX_MESSAGE_CHARS, UI_ORIGINS
from dispatch_agent.conversation import (
    GREETING,
    Conversation,
    ConversationClosedError,
    Lead,
    handle_message,
)
from dispatch_agent.db import connect
from dispatch_agent.lead import RequiredField
from dispatch_agent.updater import load_categories

app = FastAPI(title="Dispatch Agent")
app.add_middleware(
    CORSMiddleware, allow_origins=UI_ORIGINS, allow_methods=["POST"], allow_headers=["Content-Type"]
)
conversations: dict[str, Conversation] = {}


@cache
def get_client():
    return anthropic.Anthropic()


@cache
def get_categories():
    """Loaded once per process; restart to pick up category changes."""
    with closing(connect()) as conn:
        return load_categories(conn)


class Started(BaseModel):
    conversation_id: str
    message: str


class MessageIn(BaseModel):
    message: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_MESSAGE_CHARS)
    ]


class Turn(BaseModel):
    type: Literal["question", "lead"]
    message: str
    safety_alert: bool
    question_field: RequiredField | None = None  # set when type is "question"
    lead: Lead | None = None  # set when type is "lead"


@app.post("/conversations", status_code=status.HTTP_201_CREATED)
def start_conversation() -> Started:
    conversation_id = str(uuid.uuid4())
    conversations[conversation_id] = Conversation()
    return Started(conversation_id=conversation_id, message=GREETING)


@app.post("/conversations/{conversation_id}/messages")
def send_message(
    conversation_id: str,
    body: MessageIn,
    client: Annotated[anthropic.Anthropic, Depends(get_client)],
    categories: Annotated[list[tuple[str, str]], Depends(get_categories)],
) -> Turn:
    conversation = conversations.get(conversation_id)
    if conversation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "conversation not found")
    # Open the connection here: sqlite3 connections can't cross threads, and FastAPI may
    # run a dependency and the endpoint on different threadpool threads.
    with conversation.lock, closing(connect()) as conn:
        try:
            reply = handle_message(client, conn, categories, conversation, body.message)
        except ConversationClosedError:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "conversation already returned a lead"
            ) from None
    return Turn(
        type="lead" if reply.lead else "question",
        message=reply.message,
        safety_alert=reply.safety_alert,
        question_field=reply.question_field,
        lead=reply.lead,
    )
