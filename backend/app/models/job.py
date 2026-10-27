from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Column, ForeignKey, String, Table, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, UtcDateTime, enum_type, utc_now
from app.models.agent import Agent
from app.models.sample import DocumentFormat, WritingSample

if TYPE_CHECKING:
    from app.models.conversation import Conversation


class JobStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class RevisionSource(StrEnum):
    AGENT = "agent"
    PROPOSAL = "proposal"
    USER = "user"
    RESTORE = "restore"


job_samples = Table(
    "job_samples",
    Base.metadata,
    Column("job_id", ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
    Column("sample_id", ForeignKey("writing_samples.id", ondelete="CASCADE"), primary_key=True),
)


class Job(TimestampMixin, Base):
    """A writing task: context and instructions given to an agent, and the documents it produces."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    instructions: Mapped[str] = mapped_column(Text)
    requested_outputs: Mapped[list[dict[str, str]]] = mapped_column(JSON, default=list)
    agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("agents.id", ondelete="RESTRICT"), index=True
    )

    status: Mapped[JobStatus] = mapped_column(enum_type(JobStatus), default=JobStatus.DRAFT)
    samples_read: Mapped[list[int]] = mapped_column(JSON, default=list)
    settings_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    working_seconds: Mapped[float] = mapped_column(default=0.0)
    llm_calls: Mapped[int] = mapped_column(default=0)
    tool_calls: Mapped[int] = mapped_column(default=0)
    prompt_tokens: Mapped[int] = mapped_column(default=0)
    completion_tokens: Mapped[int] = mapped_column(default=0)
    agent_summary: Mapped[str | None] = mapped_column(Text)

    agent: Mapped[Agent | None] = relationship()
    samples: Mapped[list[WritingSample]] = relationship(
        secondary=job_samples, order_by=WritingSample.id
    )
    contexts: Mapped[list["ContextDocument"]] = relationship(
        back_populates="job",
        order_by="ContextDocument.position",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    documents: Mapped[list["Document"]] = relationship(
        back_populates="job",
        order_by="Document.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    conversations: Mapped[list["Conversation"]] = relationship(
        back_populates="job",
        order_by="Conversation.id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def unread_samples(self) -> list[WritingSample]:
        read = set(self.samples_read)
        return [sample for sample in self.samples if sample.id not in read]

    def mark_sample_read(self, sample_id: int) -> None:
        if sample_id not in self.samples_read:
            self.samples_read = [*self.samples_read, sample_id]

    def document(self, path: str) -> "Document | None":
        return next((document for document in self.documents if document.path == path), None)


class ContextDocument(Base):
    """Background material for a job, such as a project README, a goal or research notes."""

    __tablename__ = "context_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(default=0)
    title: Mapped[str] = mapped_column(String(200))
    format: Mapped[DocumentFormat] = mapped_column(enum_type(DocumentFormat))
    content: Mapped[str] = mapped_column(Text)

    job: Mapped[Job] = relationship(back_populates="contexts")


class Document(Base):
    """An output written by the agent. Every change is kept as a revision."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("job_id", "path"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    path: Mapped[str] = mapped_column(String(200))
    format: Mapped[DocumentFormat] = mapped_column(enum_type(DocumentFormat))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now, onupdate=utc_now)

    job: Mapped[Job] = relationship(back_populates="documents")
    revisions: Mapped[list["DocumentRevision"]] = relationship(
        back_populates="document",
        order_by="DocumentRevision.number",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def record(
        self,
        content: str,
        source: RevisionSource,
        summary: str | None = None,
        conversation_id: int | None = None,
    ) -> "DocumentRevision":
        """Replace the content and keep the new version as a revision."""
        self.content = content
        revision = DocumentRevision(
            number=len(self.revisions) + 1,
            content=content,
            source=source,
            summary=summary,
            conversation_id=conversation_id,
        )
        self.revisions.append(revision)
        return revision


class DocumentRevision(Base):
    __tablename__ = "document_revisions"
    __table_args__ = (UniqueConstraint("document_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    number: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    source: Mapped[RevisionSource] = mapped_column(enum_type(RevisionSource))
    summary: Mapped[str | None] = mapped_column(String(500))
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)

    document: Mapped[Document] = relationship(back_populates="revisions")
