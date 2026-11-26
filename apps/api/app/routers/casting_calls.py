from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.deps import DB
from app.models import CastingCall, Role
from app.schemas.casting import CastingCallOut

router = APIRouter(prefix="/casting-calls", tags=["casting calls"])


@router.get("", response_model=list[CastingCallOut])
def list_casting_calls(
    db: DB,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return db.scalars(
        select(CastingCall)
        .options(
            selectinload(CastingCall.roles).selectinload(Role.saved_match),
            selectinload(CastingCall.source),
        )
        .order_by(CastingCall.posted_at.desc().nulls_last(), CastingCall.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()


@router.get("/{casting_call_id}", response_model=CastingCallOut)
def get_casting_call(casting_call_id: int, db: DB):
    call = db.get(CastingCall, casting_call_id)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "casting call not found")
    return call
