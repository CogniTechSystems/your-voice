from datetime import datetime

from pydantic import Field

from app.models import DownloadStatus
from app.schemas.base import Schema

REPO_ID_PATTERN = r"^[A-Za-z0-9][\w.-]*/[\w.-]+$"


class HubModelRead(Schema):
    repo_id: str
    downloads: int
    likes: int
    pipeline_tag: str | None
    tags: list[str]


class FileRead(Schema):
    path: str
    size_bytes: int | None


class ModelDownloadRequest(Schema):
    repo_id: str = Field(pattern=REPO_ID_PATTERN, max_length=200)
    revision: str = Field(default="main", min_length=1, max_length=100)
    allow_patterns: list[str] | None = None
    register_only: bool = Field(
        default=False,
        description="Record the model without downloading files, for runtimes that manage "
        "their own model storage.",
    )


class LanguageModelRead(Schema):
    id: int
    repo_id: str
    revision: str
    allow_patterns: list[str] | None
    local_path: str
    status: DownloadStatus
    error: str | None
    total_bytes: int | None
    downloaded_bytes: int = 0
    completed_at: datetime | None
    created_at: datetime
