from datetime import datetime
from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from app.models import (
    ContextDocument,
    Conversation,
    ConversationKind,
    ConversationStatus,
    Document,
    DocumentFormat,
    DocumentRevision,
    Job,
    JobStatus,
    ProposalStatus,
    RevisionSource,
)
from app.schemas.base import Schema
from app.services.documents import DocumentError, normalise_document_path
from app.services.jobs import waiting_conversations


class ContextWrite(Schema):
    title: str = Field(min_length=1, max_length=200)
    format: DocumentFormat = DocumentFormat.MARKDOWN
    content: str = Field(min_length=1, max_length=500_000)


class ContextRead(ContextWrite):
    id: int


class RequestedOutput(Schema):
    path: str
    description: str = Field(default="", max_length=2000)

    @field_validator("path")
    @classmethod
    def check_path(cls, value: str) -> str:
        try:
            return normalise_document_path(value)
        except DocumentError as exc:
            raise ValueError(str(exc)) from None


class JobWrite(Schema):
    title: str = Field(min_length=1, max_length=200)
    instructions: str = Field(min_length=1, max_length=100_000)
    agent_id: int | None = None
    sample_ids: list[int] = Field(default_factory=list)
    contexts: list[ContextWrite] = Field(default_factory=list)
    requested_outputs: list[RequestedOutput] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_unique_outputs(self) -> Self:
        paths = [output.path for output in self.requested_outputs]
        if len(paths) != len(set(paths)):
            raise ValueError("Requested output file names must be unique.")
        return self


class AgentAssignment(Schema):
    agent_id: int | None


class DocumentSummary(Schema):
    id: int
    job_id: int
    path: str
    format: DocumentFormat
    word_count: int
    revision_count: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_document(cls, document: Document) -> "DocumentSummary":
        return cls(**_document_fields(document))


class DocumentRead(DocumentSummary):
    content: str

    @classmethod
    def from_document(cls, document: Document) -> "DocumentRead":
        return cls(**_document_fields(document), content=document.content)


class DocumentWrite(Schema):
    content: str = Field(max_length=1_000_000)


class RevisionSummary(Schema):
    id: int
    number: int
    source: RevisionSource
    summary: str | None
    conversation_id: int | None
    word_count: int
    created_at: datetime

    @classmethod
    def from_revision(cls, revision: DocumentRevision) -> "RevisionSummary":
        return cls(**_revision_fields(revision))


class RevisionRead(RevisionSummary):
    content: str

    @classmethod
    def from_revision(cls, revision: DocumentRevision) -> "RevisionRead":
        return cls(**_revision_fields(revision), content=revision.content)


class ConversationSummary(Schema):
    id: int
    job_id: int
    kind: ConversationKind
    status: ConversationStatus
    error: str | None
    document_id: int | None
    document_path: str | None
    quote: str | None
    prefix: str | None
    suffix: str | None
    resolved: bool
    message_count: int
    pending_proposals: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_conversation(cls, conversation: Conversation) -> "ConversationSummary":
        return cls(
            id=conversation.id,
            job_id=conversation.job_id,
            kind=conversation.kind,
            status=conversation.status,
            error=conversation.error,
            document_id=conversation.document_id,
            document_path=conversation.document.path if conversation.document else None,
            quote=conversation.quote,
            prefix=conversation.prefix,
            suffix=conversation.suffix,
            resolved=conversation.resolved,
            message_count=len(conversation.messages),
            pending_proposals=sum(
                proposal.status is ProposalStatus.PENDING for proposal in conversation.proposals
            ),
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
        )


class JobSummary(Schema):
    id: int
    title: str
    status: JobStatus
    agent_id: int | None
    agent_name: str | None
    busy: bool
    sample_count: int
    document_count: int
    started_at: datetime | None
    finished_at: datetime | None
    working_seconds: float
    llm_calls: int
    tool_calls: int
    prompt_tokens: int
    completion_tokens: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_job(cls, job: Job) -> "JobSummary":
        return cls(**_summary_fields(job))


class JobDetail(JobSummary):
    instructions: str
    requested_outputs: list[RequestedOutput]
    sample_ids: list[int]
    samples_read: list[int]
    contexts: list[ContextRead]
    documents: list[DocumentSummary]
    conversations: list[ConversationSummary]
    settings_snapshot: dict[str, Any] | None
    agent_summary: str | None

    @classmethod
    def from_job(cls, job: Job) -> "JobDetail":
        return cls(
            **_summary_fields(job),
            instructions=job.instructions,
            requested_outputs=[
                RequestedOutput.model_validate(item) for item in job.requested_outputs
            ],
            sample_ids=[sample.id for sample in job.samples],
            samples_read=job.samples_read,
            contexts=[_context_read(context) for context in job.contexts],
            documents=[DocumentSummary.from_document(document) for document in job.documents],
            conversations=[
                ConversationSummary.from_conversation(conversation)
                for conversation in job.conversations
            ],
            settings_snapshot=job.settings_snapshot,
            agent_summary=job.agent_summary,
        )


def _context_read(context: ContextDocument) -> ContextRead:
    return ContextRead(
        id=context.id, title=context.title, format=context.format, content=context.content
    )


def _summary_fields(job: Job) -> dict[str, Any]:
    return {
        "id": job.id,
        "title": job.title,
        "status": job.status,
        "agent_id": job.agent_id,
        "agent_name": job.agent.name if job.agent else None,
        "busy": bool(waiting_conversations(job)),
        "sample_count": len(job.samples),
        "document_count": len(job.documents),
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "working_seconds": job.working_seconds,
        "llm_calls": job.llm_calls,
        "tool_calls": job.tool_calls,
        "prompt_tokens": job.prompt_tokens,
        "completion_tokens": job.completion_tokens,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
    }


def _document_fields(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "job_id": document.job_id,
        "path": document.path,
        "format": document.format,
        "word_count": len(document.content.split()),
        "revision_count": len(document.revisions),
        "created_at": document.created_at,
        "updated_at": document.updated_at,
    }


def _revision_fields(revision: DocumentRevision) -> dict[str, Any]:
    return {
        "id": revision.id,
        "number": revision.number,
        "source": revision.source,
        "summary": revision.summary,
        "conversation_id": revision.conversation_id,
        "word_count": len(revision.content.split()),
        "created_at": revision.created_at,
    }
