from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.deps import AppSettings, require_session
from app.services.auth import SESSION_COOKIE, issue_session, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    password: str


@router.post("/login", status_code=status.HTTP_204_NO_CONTENT)
def login(body: LoginRequest, request: Request, response: Response, settings: AppSettings):
    password_hash = settings.auth_password_hash.get_secret_value()
    secret = settings.jwt_secret.get_secret_value()
    if not password_hash or not secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "login is not configured")

    limiter = request.app.state.login_limiter
    # Behind the ALB, uvicorn must run with --proxy-headers so this is the real client.
    client_ip = request.client.host if request.client else "unknown"
    if limiter.is_blocked(client_ip):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "too many attempts, try later")
    if not verify_password(body.password, password_hash):
        limiter.record_failure(client_ip)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "wrong password")

    limiter.reset(client_ip)
    ttl = timedelta(hours=settings.session_ttl_hours)
    response.set_cookie(
        SESSION_COOKIE,
        issue_session(secret, ttl),
        max_age=int(ttl.total_seconds()),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, settings: AppSettings):
    response.delete_cookie(
        SESSION_COOKIE, httponly=True, secure=settings.cookie_secure, samesite="lax"
    )


@router.get(
    "/session", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(require_session)]
)
def check_session():
    """204 when logged in, 401 otherwise; lets the SPA decide whether to show login."""
