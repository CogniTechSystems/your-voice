from datetime import datetime

from pydantic import Field

from app.models import Deployment, DeploymentStatus
from app.schemas.base import Schema


class DeploymentWrite(Schema):
    name: str = Field(min_length=1, max_length=100)
    model_id: int
    runtime_id: int
    model_file: str | None = Field(default=None, max_length=500)
    served_model_name: str | None = Field(default=None, max_length=200)
    launch_args: str = ""
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    top_p: float = Field(default=0.95, gt=0.0, le=1.0)
    max_tokens: int = Field(default=4096, ge=1, le=262_144)
    request_timeout_seconds: int = Field(default=600, ge=10, le=7200)


class DeploymentRead(DeploymentWrite):
    id: int
    model_repo_id: str
    runtime_name: str
    status: DeploymentStatus
    port: int | None
    pid: int | None
    error: str | None
    started_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_deployment(cls, deployment: Deployment) -> "DeploymentRead":
        return cls.model_validate(
            {
                **{field: getattr(deployment, field) for field in DeploymentWrite.model_fields},
                "id": deployment.id,
                "model_repo_id": deployment.model.repo_id,
                "runtime_name": deployment.runtime.name,
                "status": deployment.status,
                "port": deployment.port,
                "pid": deployment.pid,
                "error": deployment.error,
                "started_at": deployment.started_at,
                "created_at": deployment.created_at,
                "updated_at": deployment.updated_at,
            }
        )


class DeploymentLogRead(Schema):
    id: int
    line: str
    created_at: datetime
