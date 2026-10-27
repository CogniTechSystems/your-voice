from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, UtcDateTime, enum_type, utc_now
from app.models.job import Document, Job


class ConversationKind(StrEnum):
    MAIN = "main"
    HIGHLIGHT = "highlight"


class ConversationStatus(StrEnum):
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    ERROR = "error"


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class Conversation(TimestampMixin, Base):
    """A chat about a job.

    Each job has one main conversation, which carries the initial run and any discussion of the
    outputs as a whole. Highlight conversations are about a passage the user selected in one
    document; changes there are proposed first and applied once the user agrees.
    """

    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    kind: Mapped[ConversationKind] = mapped_column(enum_type(ConversationKind))
    status: Mapped[ConversationStatus] = mapped_column(
        enum_type(ConversationStatus), default=ConversationStatus.IDLE
    )
    error: Mapped[str | None] = mapped_column(Text)

    document_id: Mapped[int | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    quote: Mapped[str | None] = mapped_column(Text)
    prefix: Mapped[str | None] = mapped_column(Text)
    suffix: Mapped[str | None] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(default=False)

    job: Mapped[Job] = relationship(back_populates="conversations")
    document: Mapped[Document | None] = relationship()
    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="conversation",
        order_by="ChatMessage.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    proposals: Mapped[list["Proposal"]] = relationship(
        back_populates="conversation",
        order_by="Proposal.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class ChatMessage(Base):
    """A single message in a conversation, including tool calls and tool results."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MessageRole] = mapped_column(enum_type(MessageRole))
    content: Mapped[str | None] = mapped_column(Text)
    reasoning: Mapped[str | None] = mapped_column(Text)
    tool_calls: Mapped[list[dict[str, Any]] | None] = mapped_column(JSON)
    tool_call_id: Mapped[str | None] = mapped_column(String(200))
    tool_name: Mapped[str | None] = mapped_column(String(100))
    agent_name: Mapped[str | None] = mapped_column(String(100))
    prompt_tokens: Mapped[int | None]
    completion_tokens: Mapped[int | None]
    latency_ms: Mapped[int | None]
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Proposal(Base):
    """A change to a highlighted passage, suggested by the agent and awaiting the user."""

    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    original: Mapped[str] = mapped_column(Text)
    replacement: Mapped[str] = mapped_column(Text)
    explanation: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[ProposalStatus] = mapped_column(
        enum_type(ProposalStatus), default=ProposalStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    conversation: Mapped[Conversation] = relationship(back_populates="proposals")
    document: Mapped[Document] = relationship()
