from datetime import datetime
from typing import Self

from pydantic import Field, model_validator

from app.models import RuntimeKind
from app.schemas.base import Schema


class RuntimeWrite(Schema):
    name: str = Field(min_length=1, max_length=100)
    description: str = ""
    kind: RuntimeKind
    command_template: str | None = None
    base_url: str | None = Field(default=None, max_length=500)
    health_path: str = Field(default="/v1/models", pattern=r"^/")
    startup_timeout_seconds: int = Field(default=600, ge=5, le=7200)

    @model_validator(mode="after")
    def check_kind_requirements(self) -> Self:
        if self.kind is RuntimeKind.MANAGED and not (self.command_template or "").strip():
            raise ValueError("Managed runtimes require a command template.")
        if self.kind is RuntimeKind.EXTERNAL:
            url = (self.base_url or "").strip()
            if not url.startswith(("http://", "https://")):
                raise ValueError("External runtimes require an http(s) base URL.")
        return self


class RuntimeRead(Schema):
    id: int
    name: str
    description: str
    kind: RuntimeKind
    command_template: str | None
    base_url: str | None
    health_path: str
    startup_timeout_seconds: int
    created_at: datetime
    updated_at: datetime
