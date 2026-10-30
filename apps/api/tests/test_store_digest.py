from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models import CastingCall, CastingSource, RawEmail, Role, SavedMatch
from app.services.ingestion import store_digest
from ingestion_core.adapters.backstage import BackstageAdapter
from ingestion_core.parsing.mime import load_message, sent_at
from ingestion_core.types import ParsedDigest, ParsedPosting, ParsedRole

FIXTURES = Path(__file__).resolve().parents[3] / "packages/ingestion_core/tests/fixtures"
RECEIVED = datetime(2026, 10, 29, 18, 13, 43, tzinfo=UTC)


@pytest.fixture
def source(db):
    return db.scalars(select(CastingSource).where(CastingSource.key == "backstage")).one()


@pytest.fixture
def raw_email(db):
    email = RawEmail(s3_bucket="raw", s3_key="abc", received_at=RECEIVED)
    db.add(email)
    db.flush()
    return email


def digest(*postings: ParsedPosting, field_errors=()) -> ParsedDigest:
    return ParsedDigest(postings=list(postings), field_errors=list(field_errors))


def posting(title="Film", *roles: ParsedRole, **kwargs) -> ParsedPosting:
    return ParsedPosting(title=title, roles=list(roles), **kwargs)


def role(name="Lead", **kwargs) -> ParsedRole:
    return ParsedRole(role_name=name, **kwargs)


def roles_by_name(db) -> dict[str, Role]:
    return {r.role_name: r for r in db.scalars(select(Role))}


def set_match(db, role_row: Role, status: str) -> None:
    db.add(SavedMatch(role_id=role_row.id, status=status, match_reasons={"age": True}))
    db.flush()
    db.expire_all()


def test_first_store_creates_rows(db, raw_email, source):
    result = store_digest(
        db, raw_email, source, digest(posting("Film", role("A", age_min=18), role("B")))
    )
    assert raw_email.parse_status == "success" and raw_email.parse_error is None
    assert raw_email.parsed_at is not None
    assert result.created_roles == 2
    call = db.scalars(select(CastingCall)).one()
    assert call.source_id == source.id and [r.role_name for r in call.roles] == ["A", "B"]


def test_partial_records_field_errors(db, raw_email, source):
    store_digest(db, raw_email, source, digest(posting(), field_errors=["age: bad"]))
    assert (raw_email.parse_status, raw_email.parse_error) == ("partial", "age: bad")


def test_reprocess_unchanged_keeps_ids_and_user_state(db, raw_email, source):
    parsed = digest(posting("Film", role("A"), role("B")))
    store_digest(db, raw_email, source, parsed)
    before = {name: r.id for name, r in roles_by_name(db).items()}
    set_match(db, roles_by_name(db)["A"], "applied")

    result = store_digest(db, raw_email, source, digest(posting("Film", role("A"), role("B"))))
    assert {name: r.id for name, r in roles_by_name(db).items()} == before
    assert (result.created_roles, result.updated_roles, result.deleted_roles) == (0, 0, 0)
    assert roles_by_name(db)["A"].saved_match.status == "applied"


def test_fixed_field_updates_in_place(db, raw_email, source):
    store_digest(db, raw_email, source, digest(posting("Film", role("A")), field_errors=["age"]))
    role_id = roles_by_name(db)["A"].id
    set_match(db, roles_by_name(db)["A"], "saved")

    result = store_digest(db, raw_email, source, digest(posting("Film", role("A", age_min=20))))
    a = roles_by_name(db)["A"]
    assert (a.id, a.age_min, a.saved_match.status) == (role_id, 20, "saved")
    assert raw_email.parse_status == "success" and raw_email.parse_error is None
    assert result.updated_roles == 1 and result.rematch_role_ids == []


@pytest.mark.parametrize(
    "new_posting",
    [
        posting("Film", role("A", age_min=30)),
        posting("Film", role("A", genders=["male"])),
        posting("Film", role("A"), seeking_locations=["Boston, MA"]),
    ],
)
def test_untouched_match_dropped_when_match_fields_change(db, raw_email, source, new_posting):
    store_digest(db, raw_email, source, digest(posting("Film", role("A"))))
    a = roles_by_name(db)["A"]
    set_match(db, a, "new")

    result = store_digest(db, raw_email, source, digest(new_posting))
    assert result.rematch_role_ids == [a.id]
    assert db.scalars(select(SavedMatch)).all() == []


def test_untouched_match_kept_when_only_other_fields_change(db, raw_email, source):
    store_digest(db, raw_email, source, digest(posting("Film", role("A"))))
    set_match(db, roles_by_name(db)["A"], "new")

    store_digest(db, raw_email, source, digest(posting("Film", role("A", billing_type="Lead"))))
    assert roles_by_name(db)["A"].saved_match.status == "new"


def test_new_role_inserted(db, raw_email, source):
    store_digest(db, raw_email, source, digest(posting("Film", role("A"))))
    result = store_digest(db, raw_email, source, digest(posting("Film", role("A"), role("B"))))
    assert result.created_roles == 1
    assert set(roles_by_name(db)) == {"A", "B"}


def test_vanished_role_deleted_unless_user_acted(db, raw_email, source):
    store_digest(db, raw_email, source, digest(posting("Film", role("A"), role("B"), role("C"))))
    rows = roles_by_name(db)
    set_match(db, rows["B"], "new")
    set_match(db, rows["C"], "dismissed")

    result = store_digest(db, raw_email, source, digest(posting("Film", role("A"))))
    assert result.deleted_roles == 1  # B; its untouched 'new' match cascades with it
    assert set(roles_by_name(db)) == {"A", "C"}
    assert result.kept_role_ids == [rows["C"].id]
    assert db.scalars(select(SavedMatch.status)).all() == ["dismissed"]


def test_vanished_posting_kept_only_while_it_holds_kept_roles(db, raw_email, source):
    store_digest(
        db,
        raw_email,
        source,
        digest(posting("Keep", role("X")), posting("Drop", role("Y")), posting("Stay")),
    )
    set_match(db, roles_by_name(db)["X"], "applied")

    store_digest(db, raw_email, source, digest(posting("Stay")))
    assert sorted(db.scalars(select(CastingCall.title))) == ["Keep", "Stay"]
    assert set(roles_by_name(db)) == {"X"}


def test_failed_reparse_leaves_stored_rows_untouched(db, raw_email, source):
    store_digest(db, raw_email, source, digest(posting("Film", role("A"))))
    result = store_digest(db, raw_email, source, ParsedDigest(error="no job cards found"))
    assert raw_email.parse_status == "failed"
    assert raw_email.parse_error == "no job cards found"
    assert result == type(result)()
    assert set(roles_by_name(db)) == {"A"}


def test_duplicate_names_pair_by_occurrence(db, raw_email, source):
    store_digest(
        db,
        raw_email,
        source,
        digest(posting("Film", role("Extra", age_min=18), role("Extra", age_min=40))),
    )
    ids = [r.id for r in db.scalars(select(Role).order_by(Role.id))]

    store_digest(
        db,
        raw_email,
        source,
        digest(posting("Film", role("Extra", age_min=21), role("Extra", age_min=41))),
    )
    rows = db.scalars(select(Role).order_by(Role.id)).all()
    assert [(r.id, r.age_min) for r in rows] == [(ids[0], 21), (ids[1], 41)]


def test_real_fixture_round_trip(db, raw_email, source):
    raw = (FIXTURES / "backstage_sample.eml").read_bytes()
    parsed = BackstageAdapter().parse(raw, sent_at(load_message(raw)))

    first = store_digest(db, raw_email, source, parsed)
    assert first.created_roles == 8
    ids = sorted(db.scalars(select(Role.id)))

    again = store_digest(db, raw_email, source, BackstageAdapter().parse(raw, RECEIVED))
    assert (again.created_roles, again.updated_roles, again.deleted_roles) == (0, 0, 0)
    assert sorted(db.scalars(select(Role.id))) == ids
    sparrow = db.scalars(select(Role).where(Role.role_name == "Sparrow Huang")).one()
    assert sparrow.genders == ["female", "trans female"]
