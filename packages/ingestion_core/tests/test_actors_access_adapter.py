from datetime import UTC, datetime

import pytest

from ingestion_core.adapters.actors_access import ActorsAccessAdapter
from ingestion_core.adapters.registry import get_adapter_for
from ingestion_core.parsing.mime import load_message, sent_at

adapter = ActorsAccessAdapter()

# A manual Gmail forward (outer From is the Gmail account, not Actors Access), with the
# unsubscribe token and profile photo URL replaced. Swap in an auto-forwarded capture once
# one arrives; the parsing expectations below should hold for it unchanged.
FIXTURE = "actors_access_manual_forward.eml"
LINK = "https://actorsaccess.com/projects/?view=breakdowns&breakdown={id}&utm_content={kind}"


def parse_fixture(fixture_bytes):
    raw = fixture_bytes(FIXTURE)
    return adapter.parse(raw, sent_at(load_message(raw)))


def card(
    *,
    breakdown="1",
    title="Proj",
    tags=("Episodic", "NON-UNION", "New York, NY"),
    roles=(("Role", "Woman; 21 to 29 years old; all ethnicities. Lead"),),
):
    divider = '<span style="display:inline-block"> </span>'
    role_html = "".join(
        f'<div><div><a href="{LINK.format(id=breakdown, kind="html_role")}">{name}</a></div>'
        f"<div>{details}</div></div>"
        for name, details in roles
    )
    return (
        f'<div><a href="{LINK.format(id=breakdown, kind="html_title")}">{title}</a></div>'
        f"<div>{divider.join(tags)}</div>{role_html}"
    )


def parse_html(make_email, *cards):
    html = f"<html><body><div>{''.join(cards)}</div></body></html>"
    msg = make_email(html=html, from_addr="notifications@actorsaccess.com")
    return adapter.parse(msg.as_bytes(), datetime(2026, 11, 25, tzinfo=UTC))


# --- real fixture ----------------------------------------------------------------


def test_fixture_one_posting_per_breakdown(fixture_bytes):
    digest = parse_fixture(fixture_bytes)
    assert digest.status == "success"
    assert digest.field_errors == []
    assert [p.external_ref for p in digest.postings] == [
        "913212",
        "913207",
        "913193",
        "913192",
        "913144",
    ]
    assert all(len(p.roles) == 1 for p in digest.postings)
    # Same project, two breakdowns (lead and background): kept apart, as Actors Access lists them.
    lead, background = digest.postings[3], digest.postings[2]
    assert lead.title == "WHAT HAPPENED LAST NIGHT - SOCIAL MEDIA SKETCH COMEDY: BAR COMEDY SKETCH"
    assert background.title == lead.title + " (BACKGROUND)"


def test_fixture_posting_fields(fixture_bytes):
    posting = parse_fixture(fixture_bytes).postings[0]
    assert posting.title == "9/12 (FDNY VETERANS - NON-SAG-AFTRA COVERED BACKGROUND)"
    assert posting.category_tag == "Episodic | NON-UNION | Melville, NY"
    assert posting.project_type == "Episodic"
    assert posting.union_status == "nonunion"
    assert posting.seeking_locations == ["Melville, NY"]
    assert posting.description == (
        "Any gender; 30 to 85 years old; all ethnicities. "
        "Grant Wilfley Casting is seeking people for paid ba..."
    )
    assert posting.view_all_jobs_url == "https://actorsaccess.com/projects/"
    assert posting.posted_at is None and posting.submission_deadline is None


def test_fixture_union_tags(fixture_bytes):
    statuses = [p.union_status for p in parse_fixture(fixture_bytes).postings]
    # "Not Applicable" (a print job) carries no union information.
    assert statuses == ["nonunion", "union", "nonunion", "nonunion", None]


def test_fixture_role_fields(fixture_bytes):
    roles = {r.role_name: r for p in parse_fixture(fixture_bytes).postings for r in p.roles}
    vo = roles["EXPERIENCED VO ARTIST"]
    assert (vo.genders, vo.age_min, vo.age_max) == (["female"], 25, 40)
    fdny = roles["FDNY VETERANS (NON-SAG-AFTRA COVERED)"]
    assert (fdny.genders, fdny.age_min, fdny.age_max) == ([], 30, 85)
    assert vo.billing_type is None and not vo.is_featured


def test_fixture_apply_url_is_the_role_link_verbatim(fixture_bytes):
    role = parse_fixture(fixture_bytes).postings[1].roles[0]
    assert role.apply_url.startswith(
        "https://actorsaccess.com/projects/?view=breakdowns&breakdown=913207&utm_source="
    )
    assert "utm_content=html_role" in role.apply_url


def test_routed_by_registry():
    assert get_adapter_for("notifications@actorsaccess.com", {}).source_key == "actors_access"


def test_manual_forward_is_not_routed_to_actors_access():
    # A manual forward arrives from the Gmail account, so no adapter claims it.
    assert get_adapter_for("redacted@gmail.com", {}) is None


# --- synthetic cases -------------------------------------------------------------


def test_breakdown_with_several_roles(make_email):
    digest = parse_html(
        make_email,
        card(
            breakdown="7",
            roles=(
                ("Lead", "Man; 30 to 40 years old; all ethnicities. First"),
                ("Friend", "Man, Woman; 25 years old; all ethnicities. Second"),
            ),
        ),
        card(breakdown="8", title="Other"),
    )
    assert digest.status == "success"
    first, second = digest.postings
    assert [r.role_name for r in first.roles] == ["Lead", "Friend"]
    assert first.roles[1].genders == ["male", "female"]
    assert (first.roles[1].age_min, first.roles[1].age_max) == (25, 25)
    # The posting description comes from its first role.
    assert first.description == "Man; 30 to 40 years old; all ethnicities. First"
    assert [r.role_name for r in second.roles] == ["Role"]


@pytest.mark.parametrize(
    "tag, expected",
    [
        ("NON-UNION", "nonunion"),
        ("SAG-AFTRA", "union"),
        ("Not Applicable", None),
    ],
)
def test_union_tag_mapping(make_email, tag, expected):
    digest = parse_html(make_email, card(tags=("Feature Film", tag, "Remote")))
    assert digest.postings[0].union_status == expected
    assert digest.status == "success"


def test_unrecognized_union_tag_is_partial(make_email):
    digest = parse_html(make_email, card(tags=("Feature Film", "ACTRA", "Toronto")))
    assert digest.postings[0].union_status is None
    assert digest.status == "partial"
    assert "unrecognized tag 'ACTRA'" in digest.error_summary


def test_missing_tag_segment_is_partial(make_email):
    digest = parse_html(make_email, card(tags=("Feature Film", "SAG-AFTRA")))
    assert digest.status == "partial"
    assert digest.postings[0].category_tag == "Feature Film | SAG-AFTRA"
    assert digest.postings[0].union_status is None


def test_unparseable_age_is_partial(make_email):
    digest = parse_html(
        make_email, card(roles=(("Role", "Woman; 18 and over; all ethnicities. Text"),))
    )
    role = digest.postings[0].roles[0]
    assert digest.status == "partial"
    assert role.genders == ["female"] and role.age_min is None
    assert "age: unparseable '18 and over'" in digest.error_summary


def test_read_more_link_is_dropped_from_description(make_email):
    details = (
        "Any gender; 18 to 99 years old; all ethnicities. Long text...<a href='#'>Read more.</a>"
    )
    digest = parse_html(make_email, card(roles=(("Role", details),)))
    assert digest.postings[0].description.endswith("Long text...")


def test_no_cards_fails(make_email):
    digest = parse_html(make_email)
    assert digest.status == "failed"
    assert digest.error == "no breakdown cards found in Actors Access email"


def test_no_html_fails(make_email):
    msg = make_email(from_addr="notifications@actorsaccess.com")
    digest = adapter.parse(msg.as_bytes(), datetime(2026, 11, 25, tzinfo=UTC))
    assert digest.error == "email has no text/html part"
