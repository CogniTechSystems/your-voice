"""Reconciliation of persisted state after the server restarts."""

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models import (
    Conversation,
    ConversationStatus,
    Deployment,
    DeploymentStatus,
    DownloadStatus,
    LanguageModel,
)

INTERRUPTED = "Interrupted by a server restart. Send another message to continue."


def recover_interrupted_work(db: Session) -> None:
    """Reset work that cannot survive a restart."""
    db.execute(
        update(Deployment)
        .where(Deployment.status.in_([DeploymentStatus.STARTING, DeploymentStatus.RUNNING]))
        .values(status=DeploymentStatus.STOPPED, pid=None)
    )
    db.execute(
        update(LanguageModel)
        .where(LanguageModel.status.in_([DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING]))
        .values(status=DownloadStatus.FAILED, error="Interrupted by a server restart.")
    )
    db.execute(
        update(Conversation)
        .where(Conversation.status.in_([ConversationStatus.QUEUED, ConversationStatus.RUNNING]))
        .values(status=ConversationStatus.ERROR, error=INTERRUPTED)
    )
    db.commit()
