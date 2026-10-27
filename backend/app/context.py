"""Construction and initialisation of the application's services."""

from dataclasses import dataclass

from huggingface_hub import HfApi
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.database import create_database_engine, create_session_factory, run_migrations
from app.services.agent.runner import AgentRunner
from app.services.huggingface import HubService
from app.services.llm_client import ChatClientFactory, OpenAICompatibleClient
from app.services.recovery import recover_interrupted_work
from app.services.runtime_manager import RuntimeManager
from app.services.tasks import TaskRunner


@dataclass
class AppContext:
    settings: Settings
    session_factory: sessionmaker[Session]
    tasks: TaskRunner
    runtime_manager: RuntimeManager
    hub: HubService
    agent: AgentRunner

    def initialise(self) -> None:
        """Apply migrations and reset work interrupted by the previous shutdown."""
        run_migrations(self.settings.resolved_database_url)
        with self.session_factory() as db:
            recover_interrupted_work(db)

    def shutdown(self) -> None:
        self.runtime_manager.shutdown()
        self.tasks.shutdown()


def build_context(
    settings: Settings,
    *,
    tasks: TaskRunner | None = None,
    client_factory: ChatClientFactory = OpenAICompatibleClient,
    hub_api: HfApi | None = None,
) -> AppContext:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.models_dir.mkdir(parents=True, exist_ok=True)

    session_factory = create_session_factory(create_database_engine(settings.resolved_database_url))
    runtime_manager = RuntimeManager(settings, session_factory)
    tasks = tasks or TaskRunner()
    return AppContext(
        settings=settings,
        session_factory=session_factory,
        tasks=tasks,
        runtime_manager=runtime_manager,
        hub=HubService(settings, session_factory, hub_api),
        agent=AgentRunner(settings, session_factory, runtime_manager, client_factory, tasks),
    )
