"""Local development: `uv run python -m app.media_setup` (from apps/api).

Creates the media bucket in the local S3-compatible store and lets the dev frontend
upload to it. Safe to re-run. On AWS the bucket comes from CDK instead.
"""

from app.services.media_store import get_media_store


def main() -> None:
    store = get_media_store()
    store.ensure_bucket()
    print(f"media bucket {store.bucket!r} ready; uploads allowed from {store.cors_origins}")


if __name__ == "__main__":
    main()
