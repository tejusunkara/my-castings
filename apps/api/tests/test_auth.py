from datetime import UTC, datetime, timedelta

import pytest

from app.services.auth import (
    SESSION_COOKIE,
    LoginRateLimiter,
    hash_password,
    issue_session,
    session_is_valid,
    verify_password,
)


def test_password_hash_round_trip():
    stored = hash_password("s3cret")
    assert stored.startswith("scrypt$")
    assert verify_password("s3cret", stored)
    assert not verify_password("S3cret", stored)
    assert hash_password("s3cret") != stored  # salted


@pytest.mark.parametrize("stored", ["", "plain-text-password", "bcrypt$a$b"])
def test_malformed_hash_never_verifies(stored):
    assert not verify_password("plain-text-password", stored)


KEY = "k" * 32


def test_session_tokens():
    token = issue_session(KEY, timedelta(hours=1))
    assert session_is_valid(token, KEY)
    assert not session_is_valid(token, "o" * 32)
    expired = issue_session(KEY, timedelta(hours=1), now=datetime.now(UTC) - timedelta(hours=2))
    assert not session_is_valid(expired, KEY)
    assert not session_is_valid("not-a-jwt", KEY)


def test_short_jwt_secret_rejected_at_startup():
    from pydantic import SecretStr, ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError):
        Settings(jwt_secret=SecretStr("short"))


def test_rate_limiter_fixed_window():
    now = [0.0]
    limiter = LoginRateLimiter(max_attempts=2, window_seconds=60, clock=lambda: now[0])
    limiter.record_failure("ip")
    limiter.record_failure("ip")
    assert limiter.is_blocked("ip") and not limiter.is_blocked("other-ip")
    now[0] = 61
    assert not limiter.is_blocked("ip")


# --- HTTP ---


def test_health_is_public(anon_client):
    assert anon_client.get("/health").json() == {"status": "ok"}


@pytest.mark.parametrize(
    "method, path",
    [
        ("get", "/auth/session"),
        ("get", "/casting-calls"),
        ("get", "/casting-calls/1"),
        ("get", "/matches"),
        ("patch", "/matches/1"),
        ("get", "/profile"),
        ("put", "/profile"),
        ("get", "/admin/raw-emails"),
        ("post", "/admin/raw-emails/1/reprocess"),
    ],
)
def test_everything_else_requires_login(anon_client, method, path):
    assert getattr(anon_client, method)(path).status_code == 401


def test_login_sets_httponly_session_cookie(anon_client, login_password):
    response = anon_client.post("/auth/login", json={"password": login_password})
    assert response.status_code == 204
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{SESSION_COOKIE}=")
    assert "HttpOnly" in cookie and "samesite=lax" in cookie.lower()
    assert anon_client.get("/auth/session").status_code == 204


def test_wrong_password(anon_client):
    response = anon_client.post("/auth/login", json={"password": "nope"})
    assert response.status_code == 401
    assert SESSION_COOKIE not in anon_client.cookies


def test_rate_limit_blocks_even_the_right_password(anon_client, settings, login_password):
    for _ in range(settings.login_max_attempts):
        assert anon_client.post("/auth/login", json={"password": "nope"}).status_code == 401
    response = anon_client.post("/auth/login", json={"password": login_password})
    assert response.status_code == 429


def test_forged_cookie_rejected(anon_client):
    anon_client.cookies.set(SESSION_COOKIE, issue_session("a" * 32, timedelta(hours=1)))
    assert anon_client.get("/auth/session").status_code == 401


def test_logout(client):
    assert client.post("/auth/logout").status_code == 204
    assert client.get("/auth/session").status_code == 401


def test_login_unconfigured_is_unavailable_not_open(app, anon_client, settings):
    from pydantic import SecretStr

    from app.config import get_settings

    unconfigured = settings.model_copy(update={"auth_password_hash": SecretStr("")})
    app.dependency_overrides[get_settings] = lambda: unconfigured
    assert anon_client.post("/auth/login", json={"password": ""}).status_code == 503


def test_database_url_built_from_rds_secret_parts():
    from app.config import Settings

    settings = Settings(
        db_host="db.example.internal",
        db_name="my_castings",
        db_user="admin",
        db_password="p@ss/w:rd",
        _env_file=None,
    )
    assert settings.database_url == (
        "postgresql+psycopg://admin:p%40ss%2Fw%3Ard@db.example.internal:5432/my_castings"
        "?sslmode=require"
    )


def test_partial_database_parts_are_rejected():
    import pytest
    from pydantic import ValidationError

    from app.config import Settings

    with pytest.raises(ValidationError, match="db_host needs"):
        Settings(db_host="db.example.internal", _env_file=None)


def test_client_address_from_cloudfront_header():
    from starlette.requests import Request

    from app.routers.auth import client_address

    def request(headers):
        scope = {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("10.20.1.5", 443),
        }
        return Request(scope)

    header = "cloudfront-viewer-address"
    assert client_address(request({header: "203.0.113.7:51544"}), header) == "203.0.113.7"
    assert client_address(request({header: "2001:db8::1:51544"}), header) == "2001:db8::1"
    # A forged X-Forwarded-For changes nothing.
    forged = request({header: "203.0.113.7:1", "x-forwarded-for": "1.2.3.4"})
    assert client_address(forged, header) == "203.0.113.7"
    # Not configured (local): the connection's address.
    assert client_address(request({header: "203.0.113.7:1"}), None) == "10.20.1.5"
