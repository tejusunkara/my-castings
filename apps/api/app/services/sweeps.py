"""Periodic match sweep: keeps saved_matches in step with roles and the profile.

Idempotent and safe to run any time (daily at 9am in production, after profile edits,
by the seed script):
- Roles with no saved_matches row are evaluated; matches get a 'new' row. Roles that
  don't match get no row, so they're re-evaluated on the next run (e.g. after the
  profile is edited).
- Existing 'new' rows are re-evaluated too: one that no longer matches (the profile
  changed) is removed, and a still-matching one gets fresh match_reasons. Rows the user
  has acted on (saved/applied/dismissed) are never touched.
"""

from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.models import Role, SavedMatch
from app.services.matching import evaluate_role
from app.services.profile import get_profile


@dataclass
class MatchSweepResult:
    evaluated: int = 0
    created: int = 0
    removed: int = 0  # stale 'new' matches that no longer fit the profile
    skipped_no_profile: bool = False


def run_match_sweep(db: Session) -> MatchSweepResult:
    result = MatchSweepResult()
    profile = get_profile(db)
    if profile is None:
        result.skipped_no_profile = True
        return result

    unmatched = db.scalars(
        select(Role)
        .where(~exists().where(SavedMatch.role_id == Role.id))
        .options(selectinload(Role.casting_call))
    ).all()
    for role in unmatched:
        result.evaluated += 1
        match = evaluate_role(role, profile)
        if match.is_match:
            # ON CONFLICT: a concurrent sweep may have inserted the row first.
            inserted_id = db.execute(
                insert(SavedMatch)
                .values(role_id=role.id, status="new", match_reasons=match.reasons)
                .on_conflict_do_nothing(index_elements=["role_id"])
                .returning(SavedMatch.id)
            ).scalar_one_or_none()
            result.created += inserted_id is not None

    untouched = db.scalars(
        select(SavedMatch)
        .where(SavedMatch.status == "new")
        .options(selectinload(SavedMatch.role).selectinload(Role.casting_call))
    ).all()
    for saved in untouched:
        result.evaluated += 1
        match = evaluate_role(saved.role, profile)
        if not match.is_match:
            db.delete(saved)
            result.removed += 1
        elif saved.match_reasons != match.reasons:
            saved.match_reasons = match.reasons

    db.flush()
    return result
