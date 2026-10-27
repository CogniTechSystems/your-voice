"""Lifecycle management for runtime processes serving deployments."""

import contextlib
import logging
import os
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.database import utc_now
from app.models import Deployment, DeploymentLog, DeploymentStatus, RuntimeKind
from app.services.llm_client import Endpoint, normalise_base_url

logger = logging.getLogger(__name__)

PLACEHOLDERS = ("model_path", "model_dir", "port", "host", "served_model_name")
HEALTH_POLL_INTERVAL_SECONDS = 1.0
HEALTH_REQUEST_TIMEOUT_SECONDS = 3.0


class RuntimeLaunchError(RuntimeError):
    """Raised when a runtime cannot be started or never becomes healthy."""


def split_arguments(text: str) -> list[str]:
    """Split a command line using the quoting rules of the host platform.

    Windows paths keep their backslashes; surrounding quotes are removed from each token.
    """
    if sys.platform != "win32":
        return shlex.split(text)
    return [_strip_quotes(token) for token in shlex.split(text, posix=False)]


def format_command(command: list[str]) -> str:
    if sys.platform == "win32":
        return subprocess.list2cmdline(command)
    return shlex.join(command)


def build_command(template: str, launch_args: str, values: dict[str, str]) -> list[str]:
    """Split the template and extra arguments, then substitute ``{placeholder}`` tokens.

    Splitting happens before substitution so that paths containing spaces stay intact.
    """
    try:
        tokens = split_arguments(template) + split_arguments(launch_args or "")
    except ValueError as exc:
        raise RuntimeLaunchError(f"Invalid command: {exc}") from exc
    if not tokens:
        raise RuntimeLaunchError("The runtime command template is empty.")

    command = []
    for token in tokens:
        for name, value in values.items():
            token = token.replace(f"{{{name}}}", value)
        command.append(token)

    executable = shutil.which(command[0])
    if executable is None:
        raise RuntimeLaunchError(f"Executable not found on PATH: {command[0]}")
    command[0] = executable
    return command


def find_free_port(host: str) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind((host, 0))
        return int(probe.getsockname()[1])


def resolve_model_path(deployment: Deployment) -> Path:
    model_dir = Path(deployment.model.local_path)
    if not deployment.model_file:
        return model_dir
    model_path = (model_dir / deployment.model_file).resolve()
    if not model_path.is_relative_to(model_dir.resolve()) or not model_path.exists():
        raise RuntimeLaunchError(f"Model file not found: {deployment.model_file}")
    return model_path


class RuntimeManager:
    def __init__(self, settings: Settings, session_factory: sessionmaker[Session]) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._processes: dict[int, subprocess.Popen[str]] = {}
        self._stopping: set[int] = set()
        self._lock = threading.Lock()

    def endpoint(self, deployment: Deployment) -> Endpoint:
        return Endpoint(
            base_url=self.base_url(deployment),
            model=deployment.effective_model_name,
            timeout_seconds=deployment.request_timeout_seconds,
        )

    def base_url(self, deployment: Deployment) -> str:
        runtime = deployment.runtime
        if runtime.kind is RuntimeKind.EXTERNAL:
            return normalise_base_url(runtime.base_url or "")
        if deployment.port is None:
            raise RuntimeLaunchError("The deployment has not been started.")
        return f"http://{self._settings.runtime_host}:{deployment.port}"

    def start(self, deployment_id: int) -> None:
        """Launch the deployment and block until it is healthy. Run as a background task."""
        with self._lock:
            self._stopping.discard(deployment_id)
        with self._session_factory() as db:
            deployment = db.get_one(Deployment, deployment_id)
            db.execute(delete(DeploymentLog).where(DeploymentLog.deployment_id == deployment_id))
            deployment.status = DeploymentStatus.STARTING
            deployment.error = None
            deployment.started_at = utc_now()
            db.commit()

            try:
                process = None
                if deployment.runtime.kind is RuntimeKind.MANAGED:
                    process = self._launch(db, deployment)
                health_url = self.base_url(deployment) + deployment.runtime.health_path
                self._wait_until_healthy(
                    deployment_id, process, health_url, deployment.runtime.startup_timeout_seconds
                )
            except Exception as exc:
                logger.warning("Deployment %s failed to start: %s", deployment_id, exc)
                self._terminate(deployment_id)
                with self._lock:
                    if deployment_id in self._stopping:
                        return
                db.refresh(deployment)
                deployment.status = DeploymentStatus.FAILED
                deployment.error = str(exc)
                deployment.pid = None
                db.commit()
                return

            db.refresh(deployment)
            if deployment.status is DeploymentStatus.STARTING:
                deployment.status = DeploymentStatus.RUNNING
                db.commit()

    def stop(self, deployment_id: int) -> None:
        with self._lock:
            self._stopping.add(deployment_id)
        self._terminate(deployment_id)
        with self._session_factory() as db:
            deployment = db.get_one(Deployment, deployment_id)
            deployment.status = DeploymentStatus.STOPPED
            deployment.pid = None
            deployment.error = None
            db.commit()

    def shutdown(self) -> None:
        with self._lock:
            deployment_ids = list(self._processes)
        for deployment_id in deployment_ids:
            self.stop(deployment_id)

    def _launch(self, db: Session, deployment: Deployment) -> subprocess.Popen[str]:
        port = find_free_port(self._settings.runtime_host)
        model_path = resolve_model_path(deployment)
        values = {
            "model_path": str(model_path),
            "model_dir": deployment.model.local_path,
            "port": str(port),
            "host": self._settings.runtime_host,
            "served_model_name": deployment.effective_model_name,
        }
        command = build_command(
            deployment.runtime.command_template or "", deployment.launch_args, values
        )
        db.add(DeploymentLog(deployment_id=deployment.id, line=f"$ {format_command(command)}"))

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **_process_group_options(),
            )
        except OSError as exc:
            db.commit()
            raise RuntimeLaunchError(f"Failed to launch runtime: {exc}") from exc

        with self._lock:
            self._processes[deployment.id] = process
        deployment.port = port
        deployment.pid = process.pid
        db.commit()

        threading.Thread(
            target=self._capture_output,
            args=(deployment.id, process),
            name=f"runtime-output-{deployment.id}",
            daemon=True,
        ).start()
        return process

    def _wait_until_healthy(
        self,
        deployment_id: int,
        process: subprocess.Popen[str] | None,
        url: str,
        timeout_seconds: int,
    ) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            with self._lock:
                stopping = deployment_id in self._stopping
            if stopping:
                raise RuntimeLaunchError("Start cancelled.")
            if process is not None and process.poll() is not None:
                raise RuntimeLaunchError(f"Runtime exited with code {process.returncode}.")
            try:
                if httpx.get(url, timeout=HEALTH_REQUEST_TIMEOUT_SECONDS).status_code < 400:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(HEALTH_POLL_INTERVAL_SECONDS)
        raise RuntimeLaunchError(f"Runtime did not become healthy within {timeout_seconds}s.")

    def _capture_output(self, deployment_id: int, process: subprocess.Popen[str]) -> None:
        if process.stdout is not None:
            with self._session_factory() as db:
                for line in process.stdout:
                    db.add(DeploymentLog(deployment_id=deployment_id, line=line.rstrip()))
                    db.commit()
        return_code = process.wait()
        self._handle_exit(deployment_id, process, return_code)

    def _handle_exit(
        self, deployment_id: int, process: subprocess.Popen[str], return_code: int
    ) -> None:
        with self._lock:
            if self._processes.get(deployment_id) is process:
                del self._processes[deployment_id]
            stopped_deliberately = deployment_id in self._stopping
        if stopped_deliberately:
            return
        with self._session_factory() as db:
            deployment = db.get(Deployment, deployment_id)
            if deployment is None or deployment.pid != process.pid:
                return
            deployment.pid = None
            if deployment.status in (DeploymentStatus.STARTING, DeploymentStatus.RUNNING):
                deployment.status = DeploymentStatus.FAILED
                deployment.error = f"Runtime exited unexpectedly with code {return_code}."
            db.commit()

    def _terminate(self, deployment_id: int) -> None:
        with self._lock:
            process = self._processes.get(deployment_id)
        if process is not None:
            terminate_process_tree(process, self._settings.runtime_stop_timeout_seconds)


def terminate_process_tree(process: subprocess.Popen[Any], timeout_seconds: int) -> None:
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        _signal_group(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        if sys.platform != "win32":
            _signal_group(process.pid, signal.SIGKILL)
        process.kill()
        process.wait()


def _signal_group(pid: int, signal_number: int) -> None:
    if sys.platform == "win32":
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pid, signal_number)


def _strip_quotes(token: str) -> str:
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'":
        return token[1:-1]
    return token


def _process_group_options() -> dict[str, Any]:
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}
