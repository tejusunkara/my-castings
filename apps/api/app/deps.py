from collections.abc import Iterator
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.db.session import SessionLocal
from app.services.auth import SESSION_COOKIE, session_is_valid


def get_db() -> Iterator[Session]:
    """Handlers that write call db.commit() themselves, so a failed commit surfaces as an
    error response instead of happening after a success response was already sent."""
    with SessionLocal() as db:
        yield db


DB = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def require_session(
    settings: AppSettings,
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE)] = None,
) -> None:
    secret = settings.jwt_secret.get_secret_value()
    if not session or not secret or not session_is_valid(session, secret):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not logged in")
