"""Turns one raw email into database rows: verify sender, pick adapter, parse, store.

ingest() is the single entry point for first-time ingestion (Lambda, seed script) and
admin reprocessing. An email whose sender fails verification is quarantined: recorded
as failed with the reason and never linked to a source, so a spoofed digest can't put
postings into the feed. It still shows in the admin view (sender_verified=false).

store_digest() writes the parse result. Reprocessing reconciles in place instead of
delete-and-replace, so role ids, and the saved/applied/dismissed state hanging off them,
survive a re-parse:

- A failed parse never touches previously stored rows; it only records the status.
  A parser regression must not wipe out jobs an earlier parse found.
- Postings are matched to existing casting_calls by (title, occurrence), and roles to
  existing roles within their posting by (role_name, occurrence). Occurrence is the
  1st/2nd/... time that name appears, so duplicate names pair up in digest order.
  Matched rows are updated in place; unmatched parsed items are inserted.
- If a role's match-relevant fields change (age, gender, locations) and its match is
  still 'new', the match is dropped so the next sweep re-evaluates it. Matches the user
  has acted on are kept as they are.
- Stored roles the new parse no longer contains are deleted, unless the user acted on
  their match: those are kept and reported, since user state is never silently lost.
"""

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CastingCall, CastingSource, RawEmail, Role
from ingestion_core.adapters.registry import (
    AdapterRegistry,
    AmbiguousAdapterMatchError,
    default_registry,
)
from ingestion_core.parsing.mime import from_address, load_message
from ingestion_core.types import ParsedDigest, ParsedPosting, ParsedRole
from ingestion_core.verification import verify_sender

POSTING_FIELDS = [f.name for f in fields(ParsedPosting) if f.name != "roles"]
ROLE_FIELDS = [f.name for f in fields(ParsedRole)]
MATCH_ROLE_FIELDS = ("genders", "age_min", "age_max")
MATCH_POSTING_FIELDS = ("seeking_locations",)


@dataclass
class StoreResult:
    created_roles: int = 0
    updated_roles: int = 0  # matched an existing role and at least one field changed
    deleted_roles: int = 0
    # Gone from the new parse but kept because the user saved/applied/dismissed them.
    kept_role_ids: list[int] = field(default_factory=list)
    rematch_role_ids: list[int] = field(default_factory=list)  # 'new' match dropped


def ingest(
    db: Session,
    raw_email: RawEmail,
    raw_mime: bytes,
    *,
    registry: AdapterRegistry = default_registry,
    now: datetime | None = None,
) -> StoreResult:
    """Parses raw_mime into raw_email's rows. Never raises for a bad email: every
    outcome is recorded on raw_email.parse_status / parse_error."""
    now = now or datetime.now(UTC)
    try:
        msg = load_message(raw_mime)
        sender = from_address(msg)
    except Exception as exc:
        return _fail(raw_email, f"could not decode email: {exc}", now)
    raw_email.from_address = sender
    raw_email.subject = str(msg.get("Subject", "")) or None

    verdict = verify_sender(msg)
    raw_email.sender_verified = verdict.verified
    raw_email.verdict_details = verdict.details
    if not verdict.verified:
        raw_email.source = None
        reason = verdict.details.get("reason", "no aligned DKIM or SPF pass")
        return _fail(raw_email, f"quarantined: sender not verified ({reason})", now)

    try:
        adapter = registry.get_adapter_for(sender, dict(msg.items()))
    except AmbiguousAdapterMatchError as exc:
        return _fail(raw_email, str(exc), now)
    if adapter is None:
        raw_email.source = None
        return _fail(raw_email, f"no adapter for sender {sender!r}", now)

    source = db.scalars(
        select(CastingSource).where(CastingSource.key == adapter.source_key)
    ).one_or_none()
    if source is None or not source.is_active:
        return _fail(raw_email, f"no active casting source {adapter.source_key!r}", now)
    raw_email.source = source

    digest = adapter.parse(raw_mime, raw_email.received_at)
    return store_digest(db, raw_email, source, digest, now=now)


def _fail(raw_email: RawEmail, error: str, now: datetime) -> StoreResult:
    raw_email.parse_status = "failed"
    raw_email.parse_error = error
    raw_email.parsed_at = now
    return StoreResult()


def store_digest(
    db: Session,
    raw_email: RawEmail,
    source: CastingSource,
    digest: ParsedDigest,
    *,
    now: datetime | None = None,
) -> StoreResult:
    raw_email.parse_status = digest.status
    raw_email.parse_error = digest.error_summary
    raw_email.parsed_at = now or datetime.now(UTC)
    result = StoreResult()
    if digest.status == "failed":
        return result

    existing = _keyed(raw_email.casting_calls, lambda c: c.title)
    for key, posting in _keyed(digest.postings, lambda p: p.title).items():
        call = existing.pop(key, None)
        if call is None:
            call = CastingCall(source=source)
            raw_email.casting_calls.append(call)
            locations_changed = False
        else:
            locations_changed = _changed(call, posting, MATCH_POSTING_FIELDS)
        call.source = source
        _assign(call, posting, POSTING_FIELDS)
        _reconcile_roles(call, posting.roles, locations_changed, result)

    for call in existing.values():
        _reconcile_roles(call, [], False, result)
        if not call.roles:
            raw_email.casting_calls.remove(call)

    db.flush()
    return result


def _reconcile_roles(
    call: CastingCall, parsed: list[ParsedRole], locations_changed: bool, result: StoreResult
) -> None:
    existing = _keyed(call.roles, lambda r: r.role_name)
    for key, parsed_role in _keyed(parsed, lambda r: r.role_name).items():
        role = existing.pop(key, None)
        if role is None:
            call.roles.append(_assign(Role(), parsed_role, ROLE_FIELDS))
            result.created_roles += 1
            continue
        match_changed = locations_changed or _changed(role, parsed_role, MATCH_ROLE_FIELDS)
        if _changed(role, parsed_role, ROLE_FIELDS):
            result.updated_roles += 1
        _assign(role, parsed_role, ROLE_FIELDS)
        if match_changed and role.saved_match is not None and role.saved_match.status == "new":
            role.saved_match = None
            result.rematch_role_ids.append(role.id)

    for role in existing.values():
        if role.saved_match is not None and role.saved_match.status != "new":
            result.kept_role_ids.append(role.id)
        else:
            call.roles.remove(role)
            result.deleted_roles += 1


def _keyed[T](items: Iterable[T], name: Callable[[T], str]) -> dict[tuple[str, int], T]:
    """{(name, occurrence): item}, so the 2nd "Extra" pairs with the 2nd "Extra"."""
    seen: Counter[str] = Counter()
    keyed = {}
    for item in items:
        key = name(item)
        keyed[(key, seen[key])] = item
        seen[key] += 1
    return keyed


def _changed(row: object, parsed: object, names: Iterable[str]) -> bool:
    return any(getattr(row, n) != getattr(parsed, n) for n in names)


def _assign[R](row: R, parsed: object, names: Iterable[str]) -> R:
    for n in names:
        setattr(row, n, getattr(parsed, n))
    return row
