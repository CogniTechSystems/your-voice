from datetime import datetime
from typing import Any

from pydantic import Field

from app.models import Conversation, MessageRole, ProposalStatus
from app.schemas.base import Schema
from app.schemas.jobs import ConversationSummary


class MessageCreate(Schema):
    content: str = Field(min_length=1, max_length=50_000)


class HighlightCreate(MessageCreate):
    document_id: int
    quote: str = Field(min_length=1, max_length=10_000)
    prefix: str = Field(default="", max_length=2000)
    suffix: str = Field(default="", max_length=2000)


class MessageRead(Schema):
    id: int
    role: MessageRole
    content: str | None
    reasoning: str | None
    tool_calls: list[dict[str, Any]] | None
    tool_call_id: str | None
    tool_name: str | None
    agent_name: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    latency_ms: int | None
    created_at: datetime


class ProposalRead(Schema):
    id: int
    document_id: int
    original: str
    replacement: str
    explanation: str
    status: ProposalStatus
    created_at: datetime
    resolved_at: datetime | None


class LiveWriteRead(Schema):
    path: str
    content: str


class DraftRead(Schema):
    """Partial output of the model call in progress."""

    reasoning: str
    content: str
    writing: LiveWriteRead | None


class ConversationDetail(ConversationSummary):
    messages: list[MessageRead]
    proposals: list[ProposalRead]
    draft: DraftRead | None

    @classmethod
    def build(cls, conversation: Conversation, draft: DraftRead | None) -> "ConversationDetail":
        return cls(
            **ConversationSummary.from_conversation(conversation).model_dump(),
            messages=[MessageRead.model_validate(message) for message in conversation.messages],
            proposals=[ProposalRead.model_validate(item) for item in conversation.proposals],
            draft=draft,
        )
