"""Importing this package registers every model on Base.metadata (Alembic relies on it)."""

from app.models.casting import CastingCall, CastingSource, Role
from app.models.ingestion import RawEmail
from app.models.matches import SavedMatch
from app.models.profile import ArtistProfile, MediaAsset

__all__ = [
    "ArtistProfile",
    "CastingCall",
    "CastingSource",
    "MediaAsset",
    "RawEmail",
    "Role",
    "SavedMatch",
]
