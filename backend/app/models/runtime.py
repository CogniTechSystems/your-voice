from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, enum_type

if TYPE_CHECKING:
    from app.models.deployment import Deployment


class RuntimeKind(StrEnum):
    MANAGED = "managed"
    EXTERNAL = "external"


class Runtime(TimestampMixin, Base):
    """An inference server that exposes an OpenAI-compatible chat completions API.

    Managed runtimes are launched by the application from ``command_template``.
    External runtimes are already running and are reached at ``base_url``.
    """

    __tablename__ = "runtimes"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[RuntimeKind] = mapped_column(enum_type(RuntimeKind))
    command_template: Mapped[str | None] = mapped_column(Text)
    base_url: Mapped[str | None] = mapped_column(String(500))
    health_path: Mapped[str] = mapped_column(String(200), default="/v1/models")
    startup_timeout_seconds: Mapped[int] = mapped_column(default=600)

    deployments: Mapped[list["Deployment"]] = relationship(back_populates="runtime")
