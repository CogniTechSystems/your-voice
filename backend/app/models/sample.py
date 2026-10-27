from enum import StrEnum
from pathlib import PurePosixPath

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, TimestampMixin, enum_type


class DocumentFormat(StrEnum):
    MARKDOWN = "markdown"
    HTML = "html"
    TEXT = "text"


FORMAT_EXTENSIONS: dict[str, DocumentFormat] = {
    ".md": DocumentFormat.MARKDOWN,
    ".markdown": DocumentFormat.MARKDOWN,
    ".html": DocumentFormat.HTML,
    ".htm": DocumentFormat.HTML,
    ".txt": DocumentFormat.TEXT,
}


def format_for_path(path: str) -> DocumentFormat | None:
    """Return the format implied by a file name's extension, if it is a supported one."""
    return FORMAT_EXTENSIONS.get(PurePosixPath(path).suffix.lower())


class WritingSample(TimestampMixin, Base):
    """An article or document written by the user, read by agents to learn their voice."""

    __tablename__ = "writing_samples"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    format: Mapped[DocumentFormat] = mapped_column(enum_type(DocumentFormat))
    content: Mapped[str] = mapped_column(Text)
    notes: Mapped[str] = mapped_column(Text, default="")

    @property
    def word_count(self) -> int:
        return len(self.content.split())
