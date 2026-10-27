from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import JSON, BigInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base, TimestampMixin, UtcDateTime, enum_type

if TYPE_CHECKING:
    from app.models.deployment import Deployment


class DownloadStatus(StrEnum):
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    READY = "ready"
    FAILED = "failed"


class LanguageModel(TimestampMixin, Base):
    """A model repository downloaded from the Hugging Face Hub."""

    __tablename__ = "language_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    repo_id: Mapped[str] = mapped_column(String(200), unique=True)
    revision: Mapped[str] = mapped_column(String(100), default="main")
    allow_patterns: Mapped[list[str] | None] = mapped_column(JSON)
    local_path: Mapped[str] = mapped_column(String(1000))
    status: Mapped[DownloadStatus] = mapped_column(
        enum_type(DownloadStatus), default=DownloadStatus.QUEUED
    )
    error: Mapped[str | None] = mapped_column(Text)
    total_bytes: Mapped[int | None] = mapped_column(BigInteger)
    completed_at: Mapped[datetime | None] = mapped_column(UtcDateTime)

    deployments: Mapped[list["Deployment"]] = relationship(back_populates="model")
