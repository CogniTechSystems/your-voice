from fastapi import APIRouter, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import DbDep, conflict, get_or_404
from app.models import Runtime
from app.schemas.runtimes import RuntimeRead, RuntimeWrite

router = APIRouter(prefix="/runtimes", tags=["runtimes"])


def _apply(runtime: Runtime, payload: RuntimeWrite) -> None:
    runtime.name = payload.name.strip()
    runtime.description = payload.description.strip()
    runtime.kind = payload.kind
    runtime.command_template = (payload.command_template or "").strip() or None
    runtime.base_url = (payload.base_url or "").strip() or None
    runtime.health_path = payload.health_path
    runtime.startup_timeout_seconds = payload.startup_timeout_seconds


@router.get("", response_model=list[RuntimeRead])
def list_runtimes(db: DbDep) -> list[Runtime]:
    return list(db.scalars(select(Runtime).order_by(Runtime.name)))


@router.post("", response_model=RuntimeRead, status_code=status.HTTP_201_CREATED)
def create_runtime(payload: RuntimeWrite, db: DbDep) -> Runtime:
    runtime = Runtime()
    _apply(runtime, payload)
    db.add(runtime)
    try:
        db.commit()
    except IntegrityError:
        raise conflict(f"A runtime named '{payload.name}' already exists.") from None
    return runtime


@router.put("/{runtime_id}", response_model=RuntimeRead)
def update_runtime(runtime_id: int, payload: RuntimeWrite, db: DbDep) -> Runtime:
    runtime = get_or_404(db, Runtime, runtime_id)
    _apply(runtime, payload)
    try:
        db.commit()
    except IntegrityError:
        raise conflict(f"A runtime named '{payload.name}' already exists.") from None
    return runtime


@router.delete("/{runtime_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_runtime(runtime_id: int, db: DbDep) -> None:
    runtime = get_or_404(db, Runtime, runtime_id)
    if runtime.deployments:
        raise conflict("Delete the deployments that use this runtime first.")
    db.delete(runtime)
    db.commit()
