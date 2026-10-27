"""Starting, completing and inspecting writing jobs."""

from app.database import utc_now
from app.models import (
    ChatMessage,
    Conversation,
    ConversationKind,
    ConversationStatus,
    DeploymentStatus,
    Job,
    JobStatus,
    MessageRole,
)


class JobStateError(ValueError):
    """Raised when a job cannot move to the requested state. The message is shown to the user."""


def main_conversation(job: Job) -> Conversation | None:
    return next((item for item in job.conversations if item.kind is ConversationKind.MAIN), None)


def running_conversation(job: Job) -> Conversation | None:
    return next(
        (item for item in job.conversations if item.status is ConversationStatus.RUNNING), None
    )


def waiting_conversations(job: Job) -> list[Conversation]:
    """Conversations the agent is answering now or has queued."""
    waiting = (ConversationStatus.QUEUED, ConversationStatus.RUNNING)
    return [item for item in job.conversations if item.status in waiting]


def check_agent_available(job: Job) -> None:
    """Raise unless the job has an agent whose deployment is running."""
    if job.agent is None:
        raise JobStateError("Assign an agent to the job first.")
    deployment = job.agent.deployment
    if deployment.status is not DeploymentStatus.RUNNING:
        raise JobStateError(
            f"Agent '{job.agent.name}' uses deployment '{deployment.name}', which is not running."
        )


def queue_message(conversation: Conversation, content: str) -> None:
    """Add a user message and queue the conversation for the agent's next free turn."""
    if conversation.status in (ConversationStatus.QUEUED, ConversationStatus.RUNNING):
        raise JobStateError("The agent has not answered your last message in this conversation.")
    conversation.messages.append(ChatMessage(role=MessageRole.USER, content=content))
    conversation.status = ConversationStatus.QUEUED
    conversation.error = None
    conversation.resolved = False


def kickoff_message(job: Job) -> str:
    return f'Please start the job "{job.title}".'


def start_job(job: Job) -> Conversation:
    """Activate a draft job and queue the agent's first turn in a new main conversation.

    Call ``AgentRunner.schedule`` after committing.
    """
    if job.status is not JobStatus.DRAFT:
        raise JobStateError("Only draft jobs can be started.")
    check_agent_available(job)
    assert job.agent is not None

    job.status = JobStatus.ACTIVE
    job.started_at = utc_now()
    job.finished_at = None
    job.samples_read = []
    job.settings_snapshot = job.agent.settings_snapshot()
    conversation = Conversation(kind=ConversationKind.MAIN)
    queue_message(conversation, kickoff_message(job))
    job.conversations.append(conversation)
    return conversation


def complete_job(job: Job, summary: str | None = None) -> None:
    if job.status is not JobStatus.ACTIVE:
        raise JobStateError("Only active jobs can be completed.")
    job.status = JobStatus.COMPLETED
    job.finished_at = utc_now()
    if summary:
        job.agent_summary = summary
