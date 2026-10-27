from fastapi import APIRouter, status

from app.api.deps import ContextDep, DbDep, conflict, get_or_404
from app.context import AppContext
from app.models import (
    ChatMessage,
    Conversation,
    ConversationKind,
    ConversationStatus,
    JobStatus,
    MessageRole,
    Proposal,
)
from app.schemas.base import Schema
from app.schemas.conversations import (
    ConversationDetail,
    DraftRead,
    LiveWriteRead,
    MessageCreate,
    ProposalRead,
)
from app.services.agent.live import live_write
from app.services.documents import DocumentError, apply_proposal, reject_proposal
from app.services.jobs import JobStateError, check_agent_available, queue_message

router = APIRouter(tags=["conversations"])


class ResolveRequest(Schema):
    resolved: bool = True


def _detail(context: AppContext, conversation: Conversation) -> ConversationDetail:
    progress = context.agent.draft(conversation.id)
    draft = None
    if progress is not None:
        writing = live_write(progress)
        draft = DraftRead(
            reasoning=progress.reasoning,
            content=progress.content,
            writing=LiveWriteRead(path=writing.path, content=writing.content) if writing else None,
        )
    return ConversationDetail.build(conversation, draft)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get_conversation(conversation_id: int, context: ContextDep, db: DbDep) -> ConversationDetail:
    return _detail(context, get_or_404(db, Conversation, conversation_id))


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=ConversationDetail,
    status_code=status.HTTP_202_ACCEPTED,
)
def send_message(
    conversation_id: int, payload: MessageCreate, context: ContextDep, db: DbDep
) -> ConversationDetail:
    conversation = get_or_404(db, Conversation, conversation_id)
    job = conversation.job
    if job.status is JobStatus.DRAFT:
        raise conflict("Start the job first.")
    if job.status is JobStatus.CANCELLED:
        raise conflict("The job was cancelled. Reopen it to continue.")
    if conversation.kind is ConversationKind.HIGHLIGHT and conversation.document is None:
        raise conflict("The highlighted document has been deleted.")
    try:
        check_agent_available(job)
        queue_message(conversation, payload.content.strip())
    except JobStateError as exc:
        raise conflict(str(exc)) from None
    db.commit()

    context.agent.schedule(job.id)
    return _detail(context, conversation)


@router.post("/conversations/{conversation_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_turn(conversation_id: int, context: ContextDep, db: DbDep) -> None:
    get_or_404(db, Conversation, conversation_id)
    context.agent.request_cancel(conversation_id)


@router.post("/conversations/{conversation_id}/resolve", response_model=ConversationDetail)
def resolve(
    conversation_id: int, payload: ResolveRequest, context: ContextDep, db: DbDep
) -> ConversationDetail:
    conversation = get_or_404(db, Conversation, conversation_id)
    if conversation.kind is not ConversationKind.HIGHLIGHT:
        raise conflict("Only highlight conversations can be resolved.")
    conversation.resolved = payload.resolved
    db.commit()
    return _detail(context, conversation)


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(conversation_id: int, db: DbDep) -> None:
    conversation = get_or_404(db, Conversation, conversation_id)
    if conversation.kind is not ConversationKind.HIGHLIGHT:
        raise conflict("The main conversation of a job cannot be deleted.")
    if conversation.status in (ConversationStatus.QUEUED, ConversationStatus.RUNNING):
        raise conflict("Stop the agent's reply in this discussion before deleting it.")
    db.delete(conversation)
    db.commit()


@router.post("/proposals/{proposal_id}/apply", response_model=ProposalRead)
def apply(proposal_id: int, context: ContextDep, db: DbDep) -> Proposal:
    proposal = get_or_404(db, Proposal, proposal_id)
    try:
        apply_proposal(proposal, limit=context.settings.document_character_limit)
    except DocumentError as exc:
        raise conflict(str(exc)) from None
    # Recorded so the agent knows the outcome when the conversation continues.
    proposal.conversation.messages.append(
        ChatMessage(role=MessageRole.USER, content=f"I applied proposal {proposal.id}.")
    )
    db.commit()
    return proposal


@router.post("/proposals/{proposal_id}/reject", response_model=ProposalRead)
def reject(proposal_id: int, db: DbDep) -> Proposal:
    proposal = get_or_404(db, Proposal, proposal_id)
    try:
        reject_proposal(proposal)
    except DocumentError as exc:
        raise conflict(str(exc)) from None
    proposal.conversation.messages.append(
        ChatMessage(role=MessageRole.USER, content=f"I rejected proposal {proposal.id}.")
    )
    db.commit()
    return proposal
