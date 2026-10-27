from fastapi import APIRouter, HTTPException, status

from app.api.deps import ContextDep, DbDep, conflict, get_or_404
from app.models import Document, DocumentRevision, RevisionSource
from app.schemas.jobs import DocumentRead, DocumentWrite, RevisionRead, RevisionSummary
from app.services.documents import DocumentError, restore_revision

router = APIRouter(prefix="/documents", tags=["documents"])


def _revision(db: DbDep, document: Document, revision_id: int) -> DocumentRevision:
    revision = get_or_404(db, DocumentRevision, revision_id)
    if revision.document_id != document.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The revision belongs to another document.")
    return revision


@router.get("/{document_id}", response_model=DocumentRead)
def get_document(document_id: int, db: DbDep) -> DocumentRead:
    return DocumentRead.from_document(get_or_404(db, Document, document_id))


@router.put("/{document_id}", response_model=DocumentRead)
def update_document(
    document_id: int, payload: DocumentWrite, context: ContextDep, db: DbDep
) -> DocumentRead:
    """Save the user's own edits as a new revision."""
    document = get_or_404(db, Document, document_id)
    if len(payload.content) > context.settings.document_character_limit:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Documents are limited to {context.settings.document_character_limit} characters.",
        )
    if payload.content != document.content:
        document.record(payload.content, RevisionSource.USER, "Edited by the user.")
        db.commit()
    return DocumentRead.from_document(document)


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(document_id: int, db: DbDep) -> None:
    document = get_or_404(db, Document, document_id)
    db.delete(document)
    db.commit()


@router.get("/{document_id}/revisions", response_model=list[RevisionSummary])
def list_revisions(document_id: int, db: DbDep) -> list[RevisionSummary]:
    document = get_or_404(db, Document, document_id)
    return [RevisionSummary.from_revision(revision) for revision in reversed(document.revisions)]


@router.get("/{document_id}/revisions/{revision_id}", response_model=RevisionRead)
def get_revision(document_id: int, revision_id: int, db: DbDep) -> RevisionRead:
    document = get_or_404(db, Document, document_id)
    return RevisionRead.from_revision(_revision(db, document, revision_id))


@router.post("/{document_id}/revisions/{revision_id}/restore", response_model=DocumentRead)
def restore(document_id: int, revision_id: int, db: DbDep) -> DocumentRead:
    document = get_or_404(db, Document, document_id)
    try:
        restore_revision(document, _revision(db, document, revision_id))
    except DocumentError as exc:
        raise conflict(str(exc)) from None
    db.commit()
    return DocumentRead.from_document(document)
