from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import ContextDep, DbDep, conflict, get_or_404
from app.database import utc_now
from app.models import DownloadStatus, LanguageModel
from app.schemas.models import FileRead, HubModelRead, LanguageModelRead, ModelDownloadRequest
from app.services.huggingface import CACHE_DIRECTORY, HubError, directory_size

router = APIRouter(tags=["models"])

IN_PROGRESS = (DownloadStatus.QUEUED, DownloadStatus.DOWNLOADING)


def _to_read(model: LanguageModel) -> LanguageModelRead:
    read = LanguageModelRead.model_validate(model)
    read.downloaded_bytes = directory_size(Path(model.local_path))
    return read


@router.get("/hub/search", response_model=list[HubModelRead])
def search_hub(
    context: ContextDep, query: str = "", limit: int = Query(default=25, ge=1, le=100)
) -> list[HubModelRead]:
    try:
        results = context.hub.search(query, limit)
    except HubError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return [HubModelRead.model_validate(result) for result in results]


@router.get("/hub/files", response_model=list[FileRead])
def list_hub_files(context: ContextDep, repo_id: str, revision: str = "main") -> list[FileRead]:
    try:
        files = context.hub.list_files(repo_id, revision)
    except HubError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return [FileRead.model_validate(file) for file in files]


@router.get("/models", response_model=list[LanguageModelRead])
def list_models(db: DbDep) -> list[LanguageModelRead]:
    models = db.scalars(select(LanguageModel).order_by(LanguageModel.repo_id))
    return [_to_read(model) for model in models]


@router.post("/models", response_model=LanguageModelRead, status_code=status.HTTP_202_ACCEPTED)
def download_model(
    request: ModelDownloadRequest, context: ContextDep, db: DbDep
) -> LanguageModelRead:
    model = db.scalars(
        select(LanguageModel).where(LanguageModel.repo_id == request.repo_id)
    ).one_or_none()
    if model is not None and model.status in IN_PROGRESS:
        raise conflict(f"{request.repo_id} is already downloading.")
    if model is None:
        model = LanguageModel(
            repo_id=request.repo_id,
            local_path=str(context.hub.local_path_for(request.repo_id)),
        )
        db.add(model)

    model.revision = request.revision
    model.allow_patterns = [pattern for pattern in request.allow_patterns or [] if pattern] or None
    model.error = None
    if request.register_only:
        model.status = DownloadStatus.READY
        model.completed_at = utc_now()
        db.commit()
        return _to_read(model)

    model.status = DownloadStatus.QUEUED
    model.completed_at = None
    db.commit()
    context.tasks.submit(context.hub.download, model.id)
    return _to_read(model)


@router.get("/models/{model_id}", response_model=LanguageModelRead)
def get_model(model_id: int, db: DbDep) -> LanguageModelRead:
    return _to_read(get_or_404(db, LanguageModel, model_id))


@router.get("/models/{model_id}/files", response_model=list[FileRead])
def list_model_files(model_id: int, db: DbDep) -> list[FileRead]:
    model = get_or_404(db, LanguageModel, model_id)
    root = Path(model.local_path)
    if not root.is_dir():
        return []
    return [
        FileRead(path=path.relative_to(root).as_posix(), size_bytes=path.stat().st_size)
        for path in sorted(root.rglob("*"))
        if path.is_file() and CACHE_DIRECTORY not in path.relative_to(root).parts
    ]


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(model_id: int, context: ContextDep, db: DbDep) -> None:
    model = get_or_404(db, LanguageModel, model_id)
    if model.status in IN_PROGRESS:
        raise conflict("Wait for the download to finish before deleting the model.")
    if model.deployments:
        raise conflict("Delete the deployments that use this model first.")
    context.hub.delete_files(model)
    db.delete(model)
    db.commit()
