from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.deps import DB
from app.models import RawEmail
from app.schemas.admin import RawEmailOut, ReprocessOut
from app.services.ingestion import ingest
from app.services.raw_email_store import RawEmailNotFoundError, read_raw_email
from app.services.sweeps import run_match_sweep

router = APIRouter(prefix="/admin", tags=["admin"])

PARSE_STATUSES = ("pending", "success", "partial", "failed")


@router.get("/raw-emails", response_model=list[RawEmailOut])
def list_raw_emails(
    db: DB,
    parse_status: Annotated[list[str] | None, Query(alias="status")] = None,
    verified: bool | None = None,
    needs_attention: Annotated[
        bool, Query(description="failed or partial parses OR unverified senders")
    ] = False,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    query = select(RawEmail).options(selectinload(RawEmail.source))
    if parse_status:
        unknown = set(parse_status) - set(PARSE_STATUSES)
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT, f"unknown status: {sorted(unknown)}"
            )
        query = query.where(RawEmail.parse_status.in_(parse_status))
    if verified is not None:
        query = query.where(RawEmail.sender_verified.is_(verified))
    if needs_attention:
        # A spoofed sender can parse cleanly yet be untrusted, so both kinds show here.
        query = query.where(
            or_(RawEmail.parse_status.in_(("failed", "partial")), ~RawEmail.sender_verified)
        )
    query = query.order_by(RawEmail.received_at.desc(), RawEmail.id.desc())
    return db.scalars(query.limit(limit).offset(offset)).all()


@router.post("/raw-emails/{raw_email_id}/reprocess", response_model=ReprocessOut)
def reprocess_raw_email(raw_email_id: int, db: DB):
    raw_email = db.get(RawEmail, raw_email_id)
    if raw_email is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "raw email not found")
    try:
        raw_mime = read_raw_email(raw_email)
    except (RawEmailNotFoundError, NotImplementedError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, f"original email unavailable: {exc}") from exc

    raw_email.parse_status = "pending"
    result = ingest(db, raw_email, raw_mime)
    sweep = run_match_sweep(db)
    db.commit()
    return ReprocessOut(
        raw_email=RawEmailOut.model_validate(raw_email),
        created_roles=result.created_roles,
        updated_roles=result.updated_roles,
        deleted_roles=result.deleted_roles,
        kept_role_ids=result.kept_role_ids,
        new_matches=sweep.created,
    )
