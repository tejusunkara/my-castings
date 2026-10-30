"""Single-password login: scrypt-hashed password, JWT session cookie, login rate limit.

Generate a password hash for MY_CASTINGS_AUTH_PASSWORD_HASH with:
    uv run python -m app.services.auth
"""

import base64
import getpass
import hashlib
import hmac
import secrets
import threading
import time
from datetime import UTC, datetime, timedelta

import jwt

SESSION_COOKIE = "session"
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return "scrypt$" + "$".join(base64.b64encode(b).decode() for b in (salt, digest))


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored_hash.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt_b64), **_SCRYPT)
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def issue_session(secret: str, ttl: timedelta, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    return jwt.encode({"sub": "artist", "iat": now, "exp": now + ttl}, secret, algorithm="HS256")


def session_is_valid(token: str, secret: str) -> bool:
    try:
        jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.InvalidTokenError:
        return False
    return True


class LoginRateLimiter:
    """Fixed-window limit on failed logins per client IP.

    In-process: correct for the single API task v1 runs. Running several tasks would
    need a shared store (e.g. a Postgres table) to keep the limit global.
    """

    def __init__(self, max_attempts: int, window_seconds: int, clock=time.monotonic):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.clock = clock
        self._windows: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def _current(self, key: str) -> tuple[float, int]:
        start, count = self._windows.get(key, (self.clock(), 0))
        if self.clock() - start >= self.window_seconds:
            return self.clock(), 0
        return start, count

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            return self._current(key)[1] >= self.max_attempts

    def record_failure(self, key: str) -> None:
        with self._lock:
            start, count = self._current(key)
            self._windows[key] = (start, count + 1)

    def reset(self, key: str) -> None:
        with self._lock:
            self._windows.pop(key, None)


if __name__ == "__main__":
    first = getpass.getpass("Password: ")
    if first != getpass.getpass("Again: "):
        raise SystemExit("Passwords don't match")
    print(hash_password(first))
