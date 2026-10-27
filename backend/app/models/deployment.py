from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, UtcDateTime, enum_type, utc_now
from app.models.language_model import LanguageModel
from app.models.runtime import Runtime


class DeploymentStatus(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    FAILED = "failed"


class Deployment(TimestampMixin, Base):
    """A downloaded model paired with a runtime and the settings used to serve it."""

    __tablename__ = "deployments"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    model_id: Mapped[int] = mapped_column(ForeignKey("language_models.id", ondelete="RESTRICT"))
    runtime_id: Mapped[int] = mapped_column(ForeignKey("runtimes.id", ondelete="RESTRICT"))

    model_file: Mapped[str | None] = mapped_column(String(500))
    served_model_name: Mapped[str | None] = mapped_column(String(200))
    launch_args: Mapped[str] = mapped_column(Text, default="")
    temperature: Mapped[float] = mapped_column(default=0.2)
    top_p: Mapped[float] = mapped_column(default=0.95)
    max_tokens: Mapped[int] = mapped_column(default=4096)
    request_timeout_seconds: Mapped[int] = mapped_column(default=600)

    status: Mapped[DeploymentStatus] = mapped_column(
        enum_type(DeploymentStatus), default=DeploymentStatus.STOPPED
    )
    port: Mapped[int | None]
    pid: Mapped[int | None]
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    model: Mapped[LanguageModel] = relationship(back_populates="deployments")
    runtime: Mapped[Runtime] = relationship(back_populates="deployments")
    logs: Mapped[list["DeploymentLog"]] = relationship(
        back_populates="deployment", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def effective_model_name(self) -> str:
        return self.served_model_name or self.model.repo_id

    def settings_snapshot(self) -> dict[str, object]:
        return {
            "deployment": self.name,
            "runtime": self.runtime.name,
            "model": self.model.repo_id,
            "revision": self.model.revision,
            "model_file": self.model_file,
            "served_model_name": self.effective_model_name,
            "launch_args": self.launch_args,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": self.max_tokens,
        }


class DeploymentLog(Base):
    """A line of output captured from a managed runtime process."""

    __tablename__ = "deployment_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"), index=True
    )
    line: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, default=utc_now)

    deployment: Mapped[Deployment] = relationship(back_populates="logs")
