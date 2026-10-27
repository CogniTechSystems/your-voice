from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin
from app.models.deployment import Deployment


class Agent(TimestampMixin, Base):
    """A named writer: a deployment and the role instructions it works under."""

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    deployment_id: Mapped[int] = mapped_column(ForeignKey("deployments.id", ondelete="RESTRICT"))
    instructions: Mapped[str] = mapped_column(Text, default="")

    deployment: Mapped[Deployment] = relationship()

    def settings_snapshot(self) -> dict[str, object]:
        return {"agent": self.name, **self.deployment.settings_snapshot()}
