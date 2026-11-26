from fastapi import Depends, FastAPI

from app.config import Settings, get_settings
from app.deps import require_session
from app.routers import admin, auth, casting_calls, matches, media, profile
from app.services.auth import LoginRateLimiter


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="my-castings API")
    app.state.login_limiter = LoginRateLimiter(
        settings.login_max_attempts, settings.login_window_seconds
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth.router)
    # Everything else requires a valid session cookie.
    protected = [Depends(require_session)]
    for router in (
        casting_calls.router,
        matches.router,
        profile.router,
        media.router,
        admin.router,
    ):
        app.include_router(router, dependencies=protected)
    return app


app = create_app()
