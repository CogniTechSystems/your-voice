"""FastAPI application entry point."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from app.api import api_router
from app.config import get_settings
from app.context import AppContext, build_context


class SinglePageApplication(StaticFiles):
    """Serve the built frontend, falling back to ``index.html`` for client-side routes."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            return await super().get_response("index.html", scope)


def create_app(context: AppContext | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app_context = context or build_context(get_settings())
        app_context.initialise()
        app.state.context = app_context
        yield
        app_context.shutdown()

    app = FastAPI(title="Your Voice", version="0.1.0", lifespan=lifespan)
    app.include_router(api_router)

    frontend_dir = (context.settings if context else get_settings()).frontend_dist_dir
    if Path(frontend_dir, "index.html").is_file():
        app.mount("/", SinglePageApplication(directory=frontend_dir, html=True), name="frontend")
    return app


app = create_app()


def run() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    settings = get_settings()
    uvicorn.run(app, host=settings.host, port=settings.port)
