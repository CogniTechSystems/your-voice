from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbDep, conflict, get_or_404
from app.models import Agent, Deployment
from app.schemas.agents import AgentRead, AgentWrite

router = APIRouter(prefix="/agents", tags=["agents"])


def _apply(db: DbDep, agent: Agent, payload: AgentWrite) -> None:
    agent.name = payload.name.strip()
    agent.deployment = get_or_404(db, Deployment, payload.deployment_id)
    agent.instructions = payload.instructions.strip()


def _commit(db: DbDep, name: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict(f"An agent named '{name}' already exists.") from None


@router.get("", response_model=list[AgentRead])
def list_agents(db: DbDep) -> list[AgentRead]:
    return [AgentRead.from_agent(agent) for agent in db.scalars(select(Agent).order_by(Agent.name))]


@router.post("", response_model=AgentRead, status_code=status.HTTP_201_CREATED)
def create_agent(payload: AgentWrite, db: DbDep) -> AgentRead:
    agent = Agent()
    _apply(db, agent, payload)
    db.add(agent)
    _commit(db, payload.name)
    return AgentRead.from_agent(agent)


@router.get("/{agent_id}", response_model=AgentRead)
def get_agent(agent_id: int, db: DbDep) -> AgentRead:
    return AgentRead.from_agent(get_or_404(db, Agent, agent_id))


@router.put("/{agent_id}", response_model=AgentRead)
def update_agent(agent_id: int, payload: AgentWrite, db: DbDep) -> AgentRead:
    agent = get_or_404(db, Agent, agent_id)
    _apply(db, agent, payload)
    _commit(db, payload.name)
    return AgentRead.from_agent(agent)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(agent_id: int, db: DbDep) -> None:
    db.delete(get_or_404(db, Agent, agent_id))
    try:
        db.commit()
    except IntegrityError:
        raise conflict("Assign other agents to this agent's jobs before deleting it.") from None
