"""Writing output documents, applying proposals and restoring revisions."""

import re
from pathlib import PurePosixPath

from app.database import utc_now
from app.models import (
    Conversation,
    Document,
    DocumentRevision,
    Job,
    Proposal,
    ProposalStatus,
    RevisionSource,
    format_for_path,
)
from app.services.text_edits import PassageError, replace_passage

PATH_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._ -]*(/[A-Za-z0-9][A-Za-z0-9._ -]*)*$")
MAX_PATH_LENGTH = 200
SUPPORTED_EXTENSIONS = ".md, .html or .txt"


class DocumentError(ValueError):
    """Raised when a document operation is invalid. The message is shown to the caller."""


def normalise_document_path(path: str) -> str:
    """Validate an output file name such as ``blog/launch-post.md`` and return it normalised."""
    cleaned = path.strip().replace("\\", "/").removeprefix("./")
    if (
        not cleaned
        or len(cleaned) > MAX_PATH_LENGTH
        or ".." in PurePosixPath(cleaned).parts
        or not PATH_PATTERN.match(cleaned)
    ):
        raise DocumentError(
            f"'{path}' is not a valid file name. Use letters, digits, dashes, underscores and "
            "dots, optionally in folders, for example 'blog/launch-post.md'."
        )
    if format_for_path(cleaned) is None:
        raise DocumentError(f"'{path}' must end in {SUPPORTED_EXTENSIONS}.")
    return cleaned


def write_document(
    job: Job,
    path: str,
    content: str,
    source: RevisionSource,
    *,
    limit: int,
    summary: str | None = None,
    conversation_id: int | None = None,
) -> Document:
    """Create a document or replace its content, recording the change as a revision."""
    path = normalise_document_path(path)
    if len(content) > limit:
        raise DocumentError(f"Documents are limited to {limit} characters.")
    document = job.document(path)
    if document is None:
        file_format = format_for_path(path)
        assert file_format is not None
        document = Document(path=path, format=file_format, content="")
        job.documents.append(document)
    elif document.content == content:
        raise DocumentError(f"{path} already has exactly this content.")
    document.record(content, source, summary, conversation_id)
    return document


def edit_document(
    document: Document,
    original: str,
    replacement: str,
    source: RevisionSource,
    *,
    limit: int,
    summary: str | None = None,
    conversation_id: int | None = None,
) -> DocumentRevision:
    if original == replacement:
        raise DocumentError("The replacement is identical to the original passage.")
    try:
        content = replace_passage(document.content, original, replacement)
    except PassageError as exc:
        raise DocumentError(str(exc)) from None
    if len(content) > limit:
        raise DocumentError(f"Documents are limited to {limit} characters.")
    return document.record(content, source, summary, conversation_id)


def propose_revision(
    conversation: Conversation, original: str, replacement: str, explanation: str
) -> Proposal:
    """Record a proposed change to the conversation's document, superseding earlier ones."""
    document = conversation.document
    if document is None:
        raise DocumentError("This conversation is not about a document.")
    if original == replacement:
        raise DocumentError("The replacement is identical to the original passage.")
    try:
        replace_passage(document.content, original, replacement)
    except PassageError as exc:
        raise DocumentError(str(exc)) from None

    for earlier in conversation.proposals:
        if earlier.status is ProposalStatus.PENDING:
            earlier.status = ProposalStatus.SUPERSEDED
            earlier.resolved_at = utc_now()
    proposal = Proposal(
        document=document, original=original, replacement=replacement, explanation=explanation
    )
    conversation.proposals.append(proposal)
    return proposal


def apply_proposal(proposal: Proposal, *, limit: int) -> DocumentRevision:
    if proposal.status is not ProposalStatus.PENDING:
        raise DocumentError(f"Proposal {proposal.id} is {proposal.status.value}, not pending.")
    try:
        revision = edit_document(
            proposal.document,
            proposal.original,
            proposal.replacement,
            RevisionSource.PROPOSAL,
            limit=limit,
            summary=proposal.explanation[:500] or None,
            conversation_id=proposal.conversation_id,
        )
    except DocumentError as exc:
        raise DocumentError(
            f"Proposal {proposal.id} no longer applies, because the document has changed: {exc}"
        ) from None
    proposal.status = ProposalStatus.APPLIED
    proposal.resolved_at = utc_now()
    return revision


def reject_proposal(proposal: Proposal) -> None:
    if proposal.status is not ProposalStatus.PENDING:
        raise DocumentError(f"Proposal {proposal.id} is {proposal.status.value}, not pending.")
    proposal.status = ProposalStatus.REJECTED
    proposal.resolved_at = utc_now()


def restore_revision(document: Document, revision: DocumentRevision) -> DocumentRevision:
    if revision.document_id != document.id:
        raise DocumentError("The revision belongs to another document.")
    if document.content == revision.content:
        raise DocumentError(f"The document already matches revision {revision.number}.")
    return document.record(
        revision.content, RevisionSource.RESTORE, f"Restored revision {revision.number}."
    )
