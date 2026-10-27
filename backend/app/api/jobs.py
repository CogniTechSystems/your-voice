from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import ContextDep, DbDep, conflict, get_or_404
from app.models import (
    Agent,
    ContextDocument,
    Conversation,
    ConversationKind,
    Job,
    JobStatus,
    WritingSample,
)
from app.schemas.conversations import ConversationDetail, HighlightCreate
from app.schemas.jobs import AgentAssignment, DocumentRead, JobDetail, JobSummary, JobWrite
from app.services.jobs import (
    JobStateError,
    check_agent_available,
    complete_job,
    queue_message,
    start_job,
    waiting_conversations,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])

CONVERSABLE = (JobStatus.ACTIVE, JobStatus.COMPLETED)


def _apply(db: DbDep, job: Job, payload: JobWrite) -> None:
    job.title = payload.title.strip()
    job.instructions = payload.instructions.strip()
    job.agent = get_or_404(db, Agent, payload.agent_id) if payload.agent_id is not None else None

    sample_ids = set(payload.sample_ids)
    samples = list(db.scalars(select(WritingSample).where(WritingSample.id.in_(sample_ids))))
    missing = sample_ids - {sample.id for sample in samples}
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Writing samples not found: {', '.join(str(item) for item in sorted(missing))}.",
        )
    job.samples = samples
    job.contexts = [
        ContextDocument(
            position=position, title=item.title.strip(), format=item.format, content=item.content
        )
        for position, item in enumerate(payload.contexts)
    ]
    job.requested_outputs = [
        {"path": item.path, "description": item.description.strip()}
        for item in payload.requested_outputs
    ]


@router.get("", response_model=list[JobSummary])
def list_jobs(
    db: DbDep,
    job_status: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[JobSummary]:
    query = select(Job).order_by(Job.updated_at.desc()).limit(limit)
    if job_status is not None:
        query = query.where(Job.status == job_status)
    return [JobSummary.from_job(job) for job in db.scalars(query)]


@router.post("", response_model=JobDetail, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobWrite, db: DbDep) -> JobDetail:
    job = Job()
    _apply(db, job, payload)
    db.add(job)
    db.commit()
    return JobDetail.from_job(job)


@router.get("/{job_id}", response_model=JobDetail)
def get_job(job_id: int, db: DbDep) -> JobDetail:
    return JobDetail.from_job(get_or_404(db, Job, job_id))


@router.put("/{job_id}", response_model=JobDetail)
def update_job(job_id: int, payload: JobWrite, db: DbDep) -> JobDetail:
    job = get_or_404(db, Job, job_id)
    _apply(db, job, payload)
    db.commit()
    return JobDetail.from_job(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int, db: DbDep) -> None:
    job = get_or_404(db, Job, job_id)
    if waiting_conversations(job):
        raise conflict("Stop or cancel the agent's work before deleting the job.")
    db.delete(job)
    db.commit()


@router.put("/{job_id}/agent", response_model=JobDetail)
def assign_agent(job_id: int, payload: AgentAssignment, db: DbDep) -> JobDetail:
    job = get_or_404(db, Job, job_id)
    job.agent = get_or_404(db, Agent, payload.agent_id) if payload.agent_id is not None else None
    db.commit()
    return JobDetail.from_job(job)


@router.post("/{job_id}/start", response_model=JobDetail, status_code=status.HTTP_202_ACCEPTED)
def start(job_id: int, context: ContextDep, db: DbDep) -> JobDetail:
    job = get_or_404(db, Job, job_id)
    try:
        start_job(job)
    except JobStateError as exc:
        raise conflict(str(exc)) from None
    db.commit()
    context.agent.schedule(job.id)
    return JobDetail.from_job(job)


@router.post("/{job_id}/complete", response_model=JobDetail)
def complete(job_id: int, db: DbDep) -> JobDetail:
    job = get_or_404(db, Job, job_id)
    try:
        complete_job(job, "Marked complete by the user.")
    except JobStateError as exc:
        raise conflict(str(exc)) from None
    db.commit()
    return JobDetail.from_job(job)


@router.post("/{job_id}/reopen", response_model=JobDetail)
def reopen(job_id: int, db: DbDep) -> JobDetail:
    job = get_or_404(db, Job, job_id)
    if job.status not in (JobStatus.COMPLETED, JobStatus.CANCELLED):
        raise conflict("Only completed or cancelled jobs can be reopened.")
    job.status = JobStatus.ACTIVE
    job.finished_at = None
    db.commit()
    return JobDetail.from_job(job)


@router.post("/{job_id}/cancel", response_model=JobDetail)
def cancel(job_id: int, context: ContextDep, db: DbDep) -> JobDetail:
    job = get_or_404(db, Job, job_id)
    if job.status is not JobStatus.ACTIVE:
        raise conflict("Only active jobs can be cancelled.")
    job.status = JobStatus.CANCELLED
    db.commit()
    for conversation in waiting_conversations(job):
        context.agent.request_cancel(conversation.id)
    db.refresh(job)
    return JobDetail.from_job(job)


@router.get("/{job_id}/documents", response_model=list[DocumentRead])
def list_documents(job_id: int, db: DbDep) -> list[DocumentRead]:
    job = get_or_404(db, Job, job_id)
    return [DocumentRead.from_document(document) for document in job.documents]


@router.post(
    "/{job_id}/conversations",
    response_model=ConversationDetail,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_highlight_conversation(
    job_id: int, payload: HighlightCreate, context: ContextDep, db: DbDep
) -> ConversationDetail:
    """Open a conversation about a passage the user highlighted, and send the first message."""
    job = get_or_404(db, Job, job_id)
    if job.status not in CONVERSABLE:
        raise conflict("Start the job, or reopen it, before discussing its outputs.")
    document = next((item for item in job.documents if item.id == payload.document_id), None)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The document is not part of this job.")
    try:
        check_agent_available(job)
    except JobStateError as exc:
        raise conflict(str(exc)) from None

    conversation = Conversation(
        kind=ConversationKind.HIGHLIGHT,
        document=document,
        quote=payload.quote,
        prefix=payload.prefix,
        suffix=payload.suffix,
    )
    queue_message(conversation, payload.content.strip())
    job.conversations.append(conversation)
    db.commit()
    context.agent.schedule(job.id)
    return ConversationDetail.build(conversation, None)
