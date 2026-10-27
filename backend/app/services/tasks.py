"""Background task execution."""

import logging
import threading
from collections.abc import Callable
from concurrent.futures import Future
from typing import Any

logger = logging.getLogger(__name__)


class TaskRunner:
    """Runs long operations such as downloads and agent turns off the request thread.

    Each task gets a daemon thread. A model call on local hardware can run for half an hour,
    and a thread pool's worker threads would hold up shutdown until it finished. Work cut off
    by shutdown is reconciled when the application next starts.
    """

    def __init__(self) -> None:
        self._counter = 0
        self._lock = threading.Lock()

    def submit(self, function: Callable[..., Any], *args: Any) -> Future[None]:
        future: Future[None] = Future()

        def run() -> None:
            _run_logged(function, *args)
            future.set_result(None)

        with self._lock:
            self._counter += 1
            name = f"yv-task-{self._counter}"
        threading.Thread(target=run, name=name, daemon=True).start()
        return future

    def shutdown(self) -> None:
        pass


class InlineTaskRunner(TaskRunner):
    """Executes tasks synchronously. Intended for tests and scripted use."""

    def submit(self, function: Callable[..., Any], *args: Any) -> Future[None]:
        future: Future[None] = Future()
        _run_logged(function, *args)
        future.set_result(None)
        return future


def _run_logged(function: Callable[..., Any], *args: Any) -> None:
    try:
        function(*args)
    except Exception:
        logger.exception("Background task %s failed", getattr(function, "__qualname__", function))
