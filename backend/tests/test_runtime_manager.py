import re
import sys
from pathlib import Path

import pytest

from app.context import AppContext
from app.database import utc_now
from app.models import (
    Deployment,
    DeploymentLog,
    DeploymentStatus,
    DownloadStatus,
    LanguageModel,
    Runtime,
    RuntimeKind,
)
from app.services.runtime_manager import RuntimeLaunchError, build_command, split_arguments


def test_placeholders_are_substituted_after_splitting():
    command = build_command(
        f'"{sys.executable}" -m http.server {{port}}',
        "--directory {model_dir}",
        {"port": "8080", "model_dir": "/models/with space"},
    )
    assert Path(command[0]) == Path(sys.executable)
    assert command[1:] == ["-m", "http.server", "8080", "--directory", "/models/with space"]


def test_quoted_arguments_are_kept_together():
    assert split_arguments('--chat-template "a b" -c 4096') == [
        "--chat-template",
        "a b",
        "-c",
        "4096",
    ]


def test_missing_executable_is_reported():
    with pytest.raises(RuntimeLaunchError, match="not found"):
        build_command("definitely-not-a-real-runtime --port {port}", "", {"port": "1"})


def test_managed_runtime_lifecycle(context: AppContext, tmp_path: Path):
    """Launch a real process that serves HTTP, wait for it to become healthy, then stop it."""
    model_dir = tmp_path / "model"
    model_dir.mkdir()
    with context.session_factory() as db:
        deployment = Deployment(
            name="HTTP server",
            model=LanguageModel(
                repo_id="example/http",
                local_path=str(model_dir),
                status=DownloadStatus.READY,
                completed_at=utc_now(),
            ),
            runtime=Runtime(
                name="Python HTTP server",
                kind=RuntimeKind.MANAGED,
                command_template=(
                    f'"{sys.executable}" -m http.server {{port}} --bind {{host}} '
                    "--directory {model_dir}"
                ),
                health_path="/",
                startup_timeout_seconds=30,
            ),
        )
        db.add(deployment)
        db.commit()
        deployment_id = deployment.id

    context.runtime_manager.start(deployment_id)
    try:
        with context.session_factory() as db:
            deployment = db.get_one(Deployment, deployment_id)
            assert deployment.status is DeploymentStatus.RUNNING, deployment.error
            assert deployment.pid is not None
            assert db.query(DeploymentLog).filter_by(deployment_id=deployment_id).count() >= 1
    finally:
        context.runtime_manager.stop(deployment_id)

    with context.session_factory() as db:
        deployment = db.get_one(Deployment, deployment_id)
        assert deployment.status is DeploymentStatus.STOPPED
        assert deployment.pid is None


def test_failed_launch_marks_deployment_failed(context: AppContext, tmp_path: Path):
    with context.session_factory() as db:
        deployment = Deployment(
            name="Broken",
            model=LanguageModel(
                repo_id="example/broken", local_path=str(tmp_path), status=DownloadStatus.READY
            ),
            runtime=Runtime(
                name="Exits immediately",
                kind=RuntimeKind.MANAGED,
                command_template=f'"{sys.executable}" -c "raise SystemExit(3)"',
                startup_timeout_seconds=30,
            ),
        )
        db.add(deployment)
        db.commit()
        deployment_id = deployment.id

    context.runtime_manager.start(deployment_id)

    with context.session_factory() as db:
        deployment = db.get_one(Deployment, deployment_id)
        assert deployment.status is DeploymentStatus.FAILED
        assert re.search(r"exited .*code 3", deployment.error or "")
