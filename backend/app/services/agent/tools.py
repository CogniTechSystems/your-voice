"""Tools exposed to the model in a job's conversations."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    ContextDocument,
    Conversation,
    ConversationKind,
    Document,
    Job,
    JobStatus,
    MessageRole,
    Proposal,
    ProposalStatus,
    RevisionSource,
    WritingSample,
)
from app.services.documents import (
    DocumentError,
    apply_proposal,
    edit_document,
    normalise_document_path,
    propose_revision,
    write_document,
)
from app.services.jobs import JobStateError, complete_job


class ToolError(Exception):
    """An error reported back to the model as the tool result."""


@dataclass
class ToolContext:
    db: Session
    conversation: Conversation
    output_limit: int
    document_limit: int

    @property
    def job(self) -> Job:
        return self.conversation.job

    def require_samples_read(self) -> None:
        unread = self.job.unread_samples()
        if unread:
            listing = ", ".join(f"{sample.id} ({sample.title})" for sample in unread)
            raise ToolError(
                f"Read every writing sample before writing. Not read yet: {listing}. "
                "Use read_sample."
            )

    def document(self, path: str) -> Document:
        try:
            path = normalise_document_path(path)
        except DocumentError as exc:
            raise ToolError(str(exc)) from None
        document = self.job.document(path)
        if document is None:
            existing = ", ".join(item.path for item in self.job.documents) or "none yet"
            raise ToolError(f"No document named {path}. Existing documents: {existing}.")
        return document


ToolHandler = Callable[[ToolContext, dict[str, Any]], str]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


def _object_schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required}


def _string_argument(arguments: dict[str, Any], name: str, *, required: bool = True) -> str:
    value = arguments.get(name)
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ToolError(f"Argument '{name}' must be a string.")
    if required and not value.strip():
        raise ToolError(f"Missing required argument '{name}'.")
    return value


def _integer_argument(arguments: dict[str, Any], name: str, default: int | None = None) -> int:
    value = arguments.get(name, default)
    if value is None:
        raise ToolError(f"Missing required argument '{name}'.")
    try:
        return int(value)
    except (TypeError, ValueError):
        raise ToolError(f"Argument '{name}' must be an integer.") from None


def _line_range(title: str, content: str, arguments: dict[str, Any]) -> str:
    """Return the requested lines of a text, with a header saying which part is shown."""
    lines = content.splitlines()
    if not lines:
        return f"{title} is empty."
    start = max(1, _integer_argument(arguments, "start_line", 1))
    end = min(len(lines), _integer_argument(arguments, "end_line", len(lines)))
    if start > end:
        return f"{title} has {len(lines)} lines; the requested range is empty."
    header = f"{title} (lines {start}-{end} of {len(lines)})"
    return header + "\n\n" + "\n".join(lines[start - 1 : end])


LINE_RANGE_PROPERTIES = {
    "start_line": {"type": "integer", "description": "First line, default 1."},
    "end_line": {"type": "integer", "description": "Last line, default the end."},
}


def _list_samples(context: ToolContext, _arguments: dict[str, Any]) -> str:
    if not context.job.samples:
        return "This job has no writing samples."
    read = set(context.job.samples_read)
    return "\n".join(
        f"- {sample.id}: {sample.title} ({sample.format.value}, {sample.word_count} words)"
        + ("" if sample.id in read else ", not read yet")
        for sample in context.job.samples
    )


def _read_sample(context: ToolContext, arguments: dict[str, Any]) -> str:
    sample_id = _integer_argument(arguments, "sample_id")
    sample: WritingSample | None = next(
        (item for item in context.job.samples if item.id == sample_id), None
    )
    if sample is None:
        raise ToolError(f"Sample {sample_id} is not part of this job. Call list_samples.")
    context.job.mark_sample_read(sample.id)
    context.db.commit()
    notes = f"Notes from the author: {sample.notes.strip()}\n\n" if sample.notes.strip() else ""
    return notes + _line_range(f"Sample {sample.id}: {sample.title}", sample.content, arguments)


def _list_context(context: ToolContext, _arguments: dict[str, Any]) -> str:
    if not context.job.contexts:
        return "This job has no context documents."
    return "\n".join(
        f"- {item.id}: {item.title} ({len(item.content.split())} words)"
        for item in context.job.contexts
    )


def _read_context(context: ToolContext, arguments: dict[str, Any]) -> str:
    context_id = _integer_argument(arguments, "context_id")
    item: ContextDocument | None = next(
        (entry for entry in context.job.contexts if entry.id == context_id), None
    )
    if item is None:
        raise ToolError(f"Context document {context_id} does not exist. Call list_context.")
    return _line_range(f"Context {item.id}: {item.title}", item.content, arguments)


def _list_documents(context: ToolContext, _arguments: dict[str, Any]) -> str:
    if not context.job.documents:
        return "No documents have been written yet."
    return "\n".join(
        f"- {document.path} ({document.format.value}, {len(document.content.split())} words, "
        f"revision {len(document.revisions)})"
        for document in context.job.documents
    )


def _read_document(context: ToolContext, arguments: dict[str, Any]) -> str:
    document = context.document(_string_argument(arguments, "path"))
    return _line_range(document.path, document.content, arguments)


def _write_document(context: ToolContext, arguments: dict[str, Any]) -> str:
    context.require_samples_read()
    content = _string_argument(arguments, "content")
    summary = _string_argument(arguments, "summary", required=False).strip()
    try:
        path = normalise_document_path(_string_argument(arguments, "path"))
        existed = context.job.document(path) is not None
        document = write_document(
            context.job,
            path,
            content,
            RevisionSource.AGENT,
            limit=context.document_limit,
            summary=summary or ("Rewrote the document." if existed else "First draft."),
            conversation_id=context.conversation.id,
        )
    except DocumentError as exc:
        raise ToolError(str(exc)) from None
    context.db.commit()
    action = "Replaced" if existed else "Created"
    return (
        f"{action} {document.path} ({len(content.split())} words, "
        f"revision {len(document.revisions)})."
    )


def _edit_document(context: ToolContext, arguments: dict[str, Any]) -> str:
    context.require_samples_read()
    document = context.document(_string_argument(arguments, "path"))
    original = _string_argument(arguments, "original")
    replacement = _string_argument(arguments, "replacement", required=False)
    summary = _string_argument(arguments, "summary", required=False).strip()
    try:
        revision = edit_document(
            document,
            original,
            replacement,
            RevisionSource.AGENT,
            limit=context.document_limit,
            summary=summary or "Edited a passage.",
            conversation_id=context.conversation.id,
        )
    except DocumentError as exc:
        raise ToolError(f"{exc} Copy the passage exactly from read_document output.") from None
    context.db.commit()
    return f"Edited {document.path} (revision {revision.number})."


def _finish_job(context: ToolContext, arguments: dict[str, Any]) -> str:
    job = context.job
    if not job.documents:
        raise ToolError("Write at least one document before finishing the job.")
    written = {document.path for document in job.documents}
    missing = [item["path"] for item in job.requested_outputs if item["path"] not in written]
    if missing:
        raise ToolError(f"These requested outputs have not been written: {', '.join(missing)}.")
    summary = _string_argument(arguments, "summary", required=False).strip()
    try:
        complete_job(job, summary or None)
    except JobStateError as exc:
        raise ToolError(str(exc)) from None
    context.db.commit()
    return "The job is complete. Tell the user briefly what you wrote and invite their feedback."


def _propose_revision(context: ToolContext, arguments: dict[str, Any]) -> str:
    original = _string_argument(arguments, "original")
    replacement = _string_argument(arguments, "replacement", required=False)
    explanation = _string_argument(arguments, "explanation", required=False).strip()
    try:
        proposal = propose_revision(context.conversation, original, replacement, explanation)
    except DocumentError as exc:
        raise ToolError(
            f"{exc} Copy the passage exactly from the document source, including markup."
        ) from None
    context.db.commit()
    return (
        f"Proposal {proposal.id} is shown to the user with Apply and Reject buttons. Summarise "
        "it in a sentence and wait for their decision."
    )


def _apply_revision(context: ToolContext, arguments: dict[str, Any]) -> str:
    proposal_id = _integer_argument(arguments, "proposal_id")
    proposal: Proposal | None = next(
        (item for item in context.conversation.proposals if item.id == proposal_id), None
    )
    if proposal is None:
        raise ToolError(f"Proposal {proposal_id} does not belong to this conversation.")
    if proposal.status is not ProposalStatus.PENDING:
        raise ToolError(f"Proposal {proposal_id} is {proposal.status.value}, not pending.")
    replied = any(
        message.role is MessageRole.USER and message.created_at > proposal.created_at
        for message in context.conversation.messages
    )
    if not replied:
        raise ToolError("The user has not responded to this proposal yet. Wait for them to agree.")
    try:
        revision = apply_proposal(proposal, limit=context.document_limit)
    except DocumentError as exc:
        raise ToolError(f"{exc} Propose a new revision against the current text.") from None
    context.db.commit()
    return (
        f"Applied proposal {proposal.id} to {proposal.document.path} (revision {revision.number})."
    )


SAMPLE_TOOLS = (
    Tool(
        name="list_samples",
        description="List the author's writing samples for this job.",
        parameters=_object_schema({}, []),
        handler=_list_samples,
    ),
    Tool(
        name="read_sample",
        description="Read one of the author's writing samples.",
        parameters=_object_schema(
            {
                "sample_id": {"type": "integer", "description": "Sample ID from list_samples."},
                **LINE_RANGE_PROPERTIES,
            },
            ["sample_id"],
        ),
        handler=_read_sample,
    ),
    Tool(
        name="list_context",
        description="List the context documents provided for this job.",
        parameters=_object_schema({}, []),
        handler=_list_context,
    ),
    Tool(
        name="read_context",
        description="Read a context document, such as a project README or a brief.",
        parameters=_object_schema(
            {
                "context_id": {"type": "integer", "description": "ID from list_context."},
                **LINE_RANGE_PROPERTIES,
            },
            ["context_id"],
        ),
        handler=_read_context,
    ),
    Tool(
        name="list_documents",
        description="List the output documents written so far.",
        parameters=_object_schema({}, []),
        handler=_list_documents,
    ),
    Tool(
        name="read_document",
        description="Read the current source of an output document.",
        parameters=_object_schema(
            {
                "path": {"type": "string", "description": "Document file name."},
                **LINE_RANGE_PROPERTIES,
            },
            ["path"],
        ),
        handler=_read_document,
    ),
)

WRITING_TOOLS = (
    Tool(
        name="write_document",
        description=(
            "Create an output document, or replace its whole content. The extension sets the "
            "format: .md, .html or .txt."
        ),
        parameters=_object_schema(
            {
                "path": {"type": "string", "description": "File name, e.g. 'launch-post.md'."},
                "content": {"type": "string", "description": "The complete document."},
                "summary": {"type": "string", "description": "What this version changes."},
            },
            ["path", "content"],
        ),
        handler=_write_document,
    ),
    Tool(
        name="edit_document",
        description="Replace one passage of an output document. The passage must be unique.",
        parameters=_object_schema(
            {
                "path": {"type": "string", "description": "Document file name."},
                "original": {"type": "string", "description": "Exact passage to replace."},
                "replacement": {"type": "string", "description": "New text for the passage."},
                "summary": {"type": "string", "description": "What the edit changes."},
            },
            ["path", "original", "replacement"],
        ),
        handler=_edit_document,
    ),
)

FINISH_TOOL = Tool(
    name="finish_job",
    description="Mark the job complete once every requested output has been written.",
    parameters=_object_schema(
        {"summary": {"type": "string", "description": "Short summary for the user."}}, []
    ),
    handler=_finish_job,
)

PROPOSAL_TOOLS = (
    Tool(
        name="propose_revision",
        description=(
            "Propose replacing a passage of the highlighted document. The user reviews the "
            "proposal before it is applied."
        ),
        parameters=_object_schema(
            {
                "original": {
                    "type": "string",
                    "description": "Exact passage from the document source, including markup.",
                },
                "replacement": {"type": "string", "description": "Proposed new text."},
                "explanation": {"type": "string", "description": "Why this change helps."},
            },
            ["original", "replacement", "explanation"],
        ),
        handler=_propose_revision,
    ),
    Tool(
        name="apply_revision",
        description="Apply a pending proposal, only after the user has agreed to it.",
        parameters=_object_schema(
            {"proposal_id": {"type": "integer", "description": "ID of the proposal."}},
            ["proposal_id"],
        ),
        handler=_apply_revision,
    ),
)


def available_tools(conversation: Conversation) -> dict[str, Tool]:
    """The tools offered in a conversation, which depend on its kind and the job's state."""
    tools = list(SAMPLE_TOOLS)
    if conversation.kind is ConversationKind.HIGHLIGHT:
        tools += PROPOSAL_TOOLS
    else:
        tools += WRITING_TOOLS
        if conversation.job.status is JobStatus.ACTIVE:
            tools.append(FINISH_TOOL)
    return {tool.name: tool for tool in tools}


def tool_schemas(conversation: Conversation) -> list[dict[str, Any]]:
    return [tool.schema() for tool in available_tools(conversation).values()]


def execute_tool(context: ToolContext, name: str, raw_arguments: str) -> str:
    """Run a tool and return its textual result. Errors are returned, not raised."""
    tool = available_tools(context.conversation).get(name)
    if tool is None:
        return f"Error: the tool '{name}' is not available in this conversation."
    try:
        arguments = json.loads(raw_arguments or "{}")
    except json.JSONDecodeError as exc:
        return f"Error: arguments are not valid JSON ({exc.msg})."
    if not isinstance(arguments, dict):
        return "Error: arguments must be a JSON object."

    try:
        result = tool.handler(context, arguments)
    except ToolError as exc:
        context.db.rollback()
        return f"Error: {exc}"

    if len(result) > context.output_limit:
        omitted = len(result) - context.output_limit
        result = (
            f"{result[: context.output_limit]}\n... output truncated ({omitted} characters). "
            "Use start_line and end_line to read the rest."
        )
    return result
