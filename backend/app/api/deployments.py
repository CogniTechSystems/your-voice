from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import ContextDep, DbDep, conflict, get_or_404
from app.models import (
    Deployment,
    DeploymentLog,
    DeploymentStatus,
    DownloadStatus,
    LanguageModel,
    Runtime,
    RuntimeKind,
)
from app.schemas.deployments import DeploymentLogRead, DeploymentRead, DeploymentWrite
from app.services.runtime_manager import RuntimeLaunchError, resolve_model_path

router = APIRouter(prefix="/deployments", tags=["deployments"])

ACTIVE = (DeploymentStatus.STARTING, DeploymentStatus.RUNNING)


def _apply(db: DbDep, deployment: Deployment, payload: DeploymentWrite) -> None:
    model = get_or_404(db, LanguageModel, payload.model_id)
    runtime = get_or_404(db, Runtime, payload.runtime_id)
    deployment.name = payload.name.strip()
    deployment.model = model
    deployment.runtime = runtime
    deployment.model_file = (payload.model_file or "").strip() or None
    deployment.served_model_name = (payload.served_model_name or "").strip() or None
    deployment.launch_args = payload.launch_args.strip()
    deployment.temperature = payload.temperature
    deployment.top_p = payload.top_p
    deployment.max_tokens = payload.max_tokens
    deployment.request_timeout_seconds = payload.request_timeout_seconds

    if runtime.kind is RuntimeKind.MANAGED and model.status is DownloadStatus.READY:
        try:
            resolve_model_path(deployment)
        except RuntimeLaunchError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


def _commit(db: DbDep, name: str) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise conflict(f"A deployment named '{name}' already exists.") from None


@router.get("", response_model=list[DeploymentRead])
def list_deployments(db: DbDep) -> list[DeploymentRead]:
    deployments = db.scalars(select(Deployment).order_by(Deployment.name))
    return [DeploymentRead.from_deployment(deployment) for deployment in deployments]


@router.post("", response_model=DeploymentRead, status_code=status.HTTP_201_CREATED)
def create_deployment(payload: DeploymentWrite, db: DbDep) -> DeploymentRead:
    deployment = Deployment()
    _apply(db, deployment, payload)
    db.add(deployment)
    _commit(db, payload.name)
    return DeploymentRead.from_deployment(deployment)


@router.get("/{deployment_id}", response_model=DeploymentRead)
def get_deployment(deployment_id: int, db: DbDep) -> DeploymentRead:
    return DeploymentRead.from_deployment(get_or_404(db, Deployment, deployment_id))


@router.put("/{deployment_id}", response_model=DeploymentRead)
def update_deployment(deployment_id: int, payload: DeploymentWrite, db: DbDep) -> DeploymentRead:
    deployment = get_or_404(db, Deployment, deployment_id)
    if deployment.status in ACTIVE:
        raise conflict("Stop the deployment before changing its settings.")
    _apply(db, deployment, payload)
    _commit(db, payload.name)
    return DeploymentRead.from_deployment(deployment)


@router.delete("/{deployment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_deployment(deployment_id: int, db: DbDep) -> None:
    deployment = get_or_404(db, Deployment, deployment_id)
    if deployment.status in ACTIVE:
        raise conflict("Stop the deployment before deleting it.")
    db.delete(deployment)
    try:
        db.commit()
    except IntegrityError:
        raise conflict("The deployment is used by an agent and cannot be deleted.") from None


@router.post(
    "/{deployment_id}/start",
    response_model=DeploymentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_deployment(deployment_id: int, context: ContextDep, db: DbDep) -> DeploymentRead:
    deployment = get_or_404(db, Deployment, deployment_id)
    if deployment.status in ACTIVE:
        raise conflict("The deployment is already running.")
    if deployment.model.status is not DownloadStatus.READY:
        raise conflict("The model has not finished downloading.")
    deployment.status = DeploymentStatus.STARTING
    deployment.error = None
    db.commit()

    context.tasks.submit(context.runtime_manager.start, deployment.id)
    return DeploymentRead.from_deployment(deployment)


@router.post("/{deployment_id}/stop", response_model=DeploymentRead)
def stop_deployment(deployment_id: int, context: ContextDep, db: DbDep) -> DeploymentRead:
    deployment = get_or_404(db, Deployment, deployment_id)
    context.runtime_manager.stop(deployment.id)
    db.refresh(deployment)
    return DeploymentRead.from_deployment(deployment)


@router.get("/{deployment_id}/logs", response_model=list[DeploymentLogRead])
def get_deployment_logs(
    deployment_id: int,
    db: DbDep,
    after_id: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=5000),
) -> list[DeploymentLog]:
    get_or_404(db, Deployment, deployment_id)
    query = select(DeploymentLog).where(DeploymentLog.deployment_id == deployment_id)
    if after_id:
        query = query.where(DeploymentLog.id > after_id).order_by(DeploymentLog.id).limit(limit)
        return list(db.scalars(query))
    latest = db.scalars(query.order_by(DeploymentLog.id.desc()).limit(limit))
    return list(reversed(list(latest)))
