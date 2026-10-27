"""Execution of agent turns: model calls interleaved with tool execution.

Each job has one agent, so its conversations take turns. Messages sent while the agent is busy
are queued, and the job's conversations are answered one after another in the order they were
queued. The user can keep editing documents meanwhile; the agent re-reads the job before every
model call and tool call, so it always works on the current text.
"""

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import asdict

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.models import (
    ChatMessage,
    Conversation,
    ConversationStatus,
    DeploymentStatus,
    MessageRole,
)
from app.services.agent.prompts import build_conversation, build_system_prompt
from app.services.agent.tools import ToolContext, execute_tool, tool_schemas
from app.services.llm_client import ChatClientFactory, GenerationParameters, Progress
from app.services.runtime_manager import RuntimeManager
from app.services.tasks import TaskRunner

logger = logging.getLogger(__name__)

PROGRESS_INTERVAL_SECONDS = 0.5


class AgentError(RuntimeError):
    """Raised when an agent turn cannot proceed."""


class TurnCancelledError(Exception):
    """Raised from the progress callback to abandon a model call the user stopped."""


class AgentRunner:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        runtime_manager: RuntimeManager,
        client_factory: ChatClientFactory,
        tasks: TaskRunner,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._runtime_manager = runtime_manager
        self._client_factory = client_factory
        self._tasks = tasks
        self._cancelled: set[int] = set()
        self._drafts: dict[int, Progress] = {}
        self._busy_jobs: set[int] = set()
        self._lock = threading.Lock()

    def draft(self, conversation_id: int) -> Progress | None:
        """Return the partial output of the model call currently running for a conversation."""
        with self._lock:
            return self._drafts.get(conversation_id)

    def schedule(self, job_id: int) -> None:
        """Answer the job's queued conversations, unless that is already under way.

        Call after committing a conversation with status ``queued``.
        """
        with self._lock:
            if job_id in self._busy_jobs:
                return
            self._busy_jobs.add(job_id)
        self._tasks.submit(self._drain, job_id)

    def request_cancel(self, conversation_id: int) -> None:
        """Stop the running turn of a conversation, or withdraw it from the queue."""
        with self._lock:
            self._cancelled.add(conversation_id)
        with self._session_factory() as db:
            conversation = db.get(Conversation, conversation_id)
            if conversation is not None and conversation.status is ConversationStatus.QUEUED:
                conversation.status = ConversationStatus.IDLE
                db.commit()

    def _drain(self, job_id: int) -> None:
        while True:
            # Checked under the lock so a conversation queued while the last turn was ending is
            # either seen here or schedules a new drain itself.
            with self._lock, self._session_factory() as db:
                conversation_id = db.scalar(
                    select(Conversation.id)
                    .where(
                        Conversation.job_id == job_id,
                        Conversation.status == ConversationStatus.QUEUED,
                    )
                    .order_by(Conversation.updated_at, Conversation.id)
                    .limit(1)
                )
                if conversation_id is None:
                    self._busy_jobs.discard(job_id)
                    return
                self._cancelled.discard(conversation_id)
                db.get_one(Conversation, conversation_id).status = ConversationStatus.RUNNING
                db.commit()
            self.run_turn(conversation_id)

    def run_turn(self, conversation_id: int) -> None:
        """Respond to the latest user message of a conversation marked as running."""
        with self._session_factory() as db:
            conversation = db.get_one(Conversation, conversation_id)
            try:
                self._run(db, conversation)
                conversation.status = ConversationStatus.IDLE
                conversation.error = None
            except TurnCancelledError:
                db.rollback()
                conversation.status = ConversationStatus.IDLE
                conversation.error = None
            except Exception as exc:
                logger.exception("Agent turn failed for conversation %s", conversation_id)
                db.rollback()
                conversation.status = ConversationStatus.ERROR
                conversation.error = str(exc)
            finally:
                self._clear_draft(conversation_id)
                with self._lock:
                    self._cancelled.discard(conversation_id)
            db.commit()

    def _run(self, db: Session, conversation: Conversation) -> None:
        job = conversation.job
        agent = job.agent
        if agent is None:
            raise AgentError("No agent is assigned to this job.")
        deployment = agent.deployment
        if deployment.status is not DeploymentStatus.RUNNING:
            raise AgentError(f"Deployment '{deployment.name}' is not running.")

        client = self._client_factory(self._runtime_manager.endpoint(deployment))
        parameters = GenerationParameters(
            temperature=deployment.temperature,
            top_p=deployment.top_p,
            max_tokens=deployment.max_tokens,
        )
        context = ToolContext(
            db=db,
            conversation=conversation,
            output_limit=self._settings.tool_output_limit,
            document_limit=self._settings.document_character_limit,
        )

        for _ in range(self._settings.agent_max_iterations):
            self._check_cancelled(conversation.id)

            # Reload everything so the prompt reflects the user's edits and applied proposals.
            db.expire_all()
            system_prompt = build_system_prompt(conversation, self._settings.tool_output_limit)
            started = time.perf_counter()
            completion = client.complete(
                build_conversation(system_prompt, conversation.messages),
                tool_schemas(conversation),
                parameters,
                on_progress=self._progress_recorder(conversation.id),
            )
            latency = time.perf_counter() - started
            self._clear_draft(conversation.id)

            db.expire_all()
            conversation.messages.append(
                ChatMessage(
                    role=MessageRole.ASSISTANT,
                    content=completion.content,
                    reasoning=completion.reasoning,
                    tool_calls=[asdict(call) for call in completion.tool_calls] or None,
                    agent_name=agent.name,
                    prompt_tokens=completion.prompt_tokens,
                    completion_tokens=completion.completion_tokens,
                    latency_ms=int(latency * 1000),
                )
            )
            job.llm_calls += 1
            job.prompt_tokens += completion.prompt_tokens or 0
            job.completion_tokens += completion.completion_tokens or 0
            job.working_seconds += latency
            db.commit()

            if not completion.tool_calls:
                return

            for call in completion.tool_calls:
                db.expire_all()
                tool_started = time.perf_counter()
                result = execute_tool(context, call.name, call.arguments)
                tool_latency = time.perf_counter() - tool_started
                job.tool_calls += 1
                job.working_seconds += tool_latency
                conversation.messages.append(
                    ChatMessage(
                        role=MessageRole.TOOL,
                        tool_call_id=call.id,
                        tool_name=call.name,
                        content=result,
                        latency_ms=int(tool_latency * 1000),
                    )
                )
                db.commit()

        raise AgentError(
            f"Stopped after {self._settings.agent_max_iterations} model calls without a final "
            "answer. Send another message to continue."
        )

    def _progress_recorder(self, conversation_id: int) -> Callable[[Progress], None]:
        last_update = 0.0

        def record(progress: Progress) -> None:
            nonlocal last_update
            self._check_cancelled(conversation_id)
            now = time.monotonic()
            if now - last_update < PROGRESS_INTERVAL_SECONDS:
                return
            last_update = now
            with self._lock:
                self._drafts[conversation_id] = progress

        return record

    def _clear_draft(self, conversation_id: int) -> None:
        with self._lock:
            self._drafts.pop(conversation_id, None)

    def _check_cancelled(self, conversation_id: int) -> None:
        with self._lock:
            if conversation_id in self._cancelled:
                raise TurnCancelledError
