from collections.abc import Iterator
from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.context import AppContext
from app.database import Base

ModelT = TypeVar("ModelT", bound=Base)


def get_context(request: Request) -> AppContext:
    context: AppContext = request.app.state.context
    return context


ContextDep = Annotated[AppContext, Depends(get_context)]


def get_db(context: ContextDep) -> Iterator[Session]:
    with context.session_factory() as db:
        yield db


DbDep = Annotated[Session, Depends(get_db)]


def get_or_404(db: Session, model: type[ModelT], identifier: int) -> ModelT:
    instance = db.get(model, identifier)
    if instance is None:
        label = model.__name__
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{label} {identifier} not found.")
    return instance


def conflict(detail: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, detail)
