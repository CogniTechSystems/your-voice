from datetime import datetime

from pydantic import Field

from app.models import Agent, DeploymentStatus
from app.schemas.base import Schema


class AgentWrite(Schema):
    name: str = Field(min_length=1, max_length=100)
    deployment_id: int
    instructions: str = Field(default="", max_length=20_000)


class AgentRead(AgentWrite):
    id: int
    deployment_name: str
    deployment_status: DeploymentStatus
    model_repo_id: str
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_agent(cls, agent: Agent) -> "AgentRead":
        return cls(
            id=agent.id,
            name=agent.name,
            deployment_id=agent.deployment_id,
            instructions=agent.instructions,
            deployment_name=agent.deployment.name,
            deployment_status=agent.deployment.status,
            model_repo_id=agent.deployment.model.repo_id,
            created_at=agent.created_at,
            updated_at=agent.updated_at,
        )
