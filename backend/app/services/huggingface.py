"""Searching and downloading models from the Hugging Face Hub."""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download
from huggingface_hub.utils import filter_repo_objects
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.database import utc_now
from app.models import DownloadStatus, LanguageModel

logger = logging.getLogger(__name__)

CACHE_DIRECTORY = ".cache"


class HubError(RuntimeError):
    """Raised when the Hugging Face Hub cannot be queried."""


@dataclass(frozen=True)
class HubModel:
    repo_id: str
    downloads: int
    likes: int
    pipeline_tag: str | None
    tags: list[str]


@dataclass(frozen=True)
class HubFile:
    path: str
    size_bytes: int | None


def local_directory_name(repo_id: str) -> str:
    return repo_id.replace("/", "__")


def directory_size(path: Path) -> int:
    """Size of downloaded files, including partial downloads but not Hub metadata."""
    if not path.is_dir():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if not entry.is_file():
            continue
        in_cache = CACHE_DIRECTORY in entry.relative_to(path).parts
        if not in_cache or entry.suffix == ".incomplete":
            total += entry.stat().st_size
    return total


class HubService:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        api: HfApi | None = None,
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._api = api or HfApi(token=settings.hf_token)

    def search(self, query: str, limit: int) -> list[HubModel]:
        try:
            results = list(
                self._api.list_models(search=query or None, sort="downloads", limit=limit)
            )
        except Exception as exc:
            raise HubError(f"Hub search failed: {exc}") from exc
        return [
            HubModel(
                repo_id=item.id,
                downloads=item.downloads or 0,
                likes=item.likes or 0,
                pipeline_tag=item.pipeline_tag,
                tags=list(item.tags or []),
            )
            for item in results
        ]

    def list_files(self, repo_id: str, revision: str) -> list[HubFile]:
        try:
            info = self._api.model_info(repo_id, revision=revision, files_metadata=True)
        except Exception as exc:
            raise HubError(f"Could not read {repo_id}@{revision}: {exc}") from exc
        return [
            HubFile(path=sibling.rfilename, size_bytes=sibling.size)
            for sibling in info.siblings or []
        ]

    def local_path_for(self, repo_id: str) -> Path:
        return self._settings.models_dir / local_directory_name(repo_id)

    def download(self, model_id: int) -> None:
        """Download a model snapshot. Run as a background task."""
        with self._session_factory() as db:
            model = db.get_one(LanguageModel, model_id)
            model.status = DownloadStatus.DOWNLOADING
            model.error = None
            db.commit()

            try:
                model.total_bytes = self._expected_size(model)
                db.commit()
                snapshot_download(
                    repo_id=model.repo_id,
                    revision=model.revision,
                    local_dir=model.local_path,
                    allow_patterns=model.allow_patterns or None,
                    token=self._settings.hf_token,
                )
            except Exception as exc:
                logger.exception("Download of %s failed", model.repo_id)
                db.rollback()
                model.status = DownloadStatus.FAILED
                model.error = str(exc)
                db.commit()
                return

            model.status = DownloadStatus.READY
            model.completed_at = utc_now()
            db.commit()

    def delete_files(self, model: LanguageModel) -> None:
        path = Path(model.local_path)
        if path.is_dir() and path.resolve().is_relative_to(self._settings.models_dir.resolve()):
            shutil.rmtree(path)

    def _expected_size(self, model: LanguageModel) -> int | None:
        files = self.list_files(model.repo_id, model.revision)
        selected = filter_repo_objects(
            files, allow_patterns=model.allow_patterns or None, key=lambda item: item.path
        )
        sizes = [item.size_bytes for item in selected]
        if any(size is None for size in sizes):
            return None
        return sum(size for size in sizes if size is not None)
