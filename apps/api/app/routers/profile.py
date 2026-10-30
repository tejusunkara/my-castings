from fastapi import APIRouter, HTTPException, status

from app.deps import DB
from app.schemas.profile import ProfileIn, ProfileOut
from app.services.profile import get_profile, upsert_profile
from app.services.sweeps import run_match_sweep

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileOut)
def read_profile(db: DB):
    profile = get_profile(db)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no profile yet")
    return profile


@router.put("", response_model=ProfileOut)
def replace_profile(body: ProfileIn, db: DB):
    profile = upsert_profile(db, body.model_dump())
    # Re-match now rather than at the next scheduled sweep, so edits show up immediately.
    run_match_sweep(db)
    db.commit()
    return profile
