from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

from ingestion_core.adapters.casting_networks import (
    DEADLINE_TZ,
    CastingNetworksAdapter,
    parse_deadline,
    union_status,
)
from ingestion_core.adapters.registry import get_adapter_for
from ingestion_core.parsing.mime import load_message, sent_at

adapter = CastingNetworksAdapter()


def parse_fixture(fixture_bytes, name):
    raw = fixture_bytes(name)
    return adapter.parse(raw, sent_at(load_message(raw))), raw


def roles_by_name(digest):
    return {r.role_name: r for p in digest.postings for r in p.roles}


def card(
    *,
    title="Proj",
    tags="Commercial | Non Union",
    role="Role",
    due="October 30, 2026, 2:00pm",
    details="<b>Principal</b> / 18 - 30 / Woman",
    href="https://app.castingnetworks.com/talent/project/1/role/2?x=1",
):
    due_html = f"<div><b>Submissions Due</b> {due} </div>" if due is not None else ""
    link = f'<a class="btn" href="{href}">View Role</a>' if href else ""
    return (
        '<table><tr><td class="roleColumn">'
        f'<div><b style="font-size: 16px">{title}</b> <span>{tags}</span></div>'
        f"<div><div><b>{role}</b></div>{due_html}</div>"
        f"<div><div>{details}</div><div>$100</div>"
        '<div style="padding-top: 4px; font-style: italic;">About the role...</div></div>'
        f"{link}</td></tr></table>"
    )


def parse_html(make_email, html):
    msg = make_email(html=html, from_addr="notifications@castingnetworks.com")
    return adapter.parse(msg.as_bytes(), datetime(2026, 10, 30, tzinfo=UTC))


# --- real fixtures ---------------------------------------------------------------


def test_sample_groups_role_cards_into_projects(fixture_bytes):
    digest, _ = parse_fixture(fixture_bytes, "casting_networks_sample.eml")
    assert digest.status == "success"
    assert digest.field_errors == []
    assert len(digest.postings) == 22
    assert sum(len(p.roles) for p in digest.postings) == 48
    ctia = digest.postings[0]
    assert (ctia.title, ctia.external_ref, len(ctia.roles)) == (
        "CTIA 2026: 5G Home",
        "16060767",
        19,
    )
    # Cards for one project are not always adjacent in the email.
    bolitar = next(p for p in digest.postings if p.external_ref == "16049614")
    assert len(bolitar.roles) == 3


def test_single_role_fixture(fixture_bytes):
    digest, _ = parse_fixture(fixture_bytes, "casting_networks_single_role.eml")
    assert digest.status == "success"
    [posting] = digest.postings
    assert (posting.title, posting.external_ref) == ("King Street", "16054208")
    [role] = posting.roles
    assert role.billing_type == "Background"
    assert (role.age_min, role.age_max, role.genders) == (19, 99, [])


def test_posting_fields(fixture_bytes):
    digest, _ = parse_fixture(fixture_bytes, "casting_networks_sample.eml")
    ctia = digest.postings[0]
    assert ctia.category_tag == "Internet Commercial | Non Union"
    assert ctia.project_type == "Internet Commercial"
    assert ctia.union_status == "nonunion"
    assert ctia.description.startswith("*WE DON'T WANT ACTORS FOR THIS.")
    # Not present in Casting Networks emails.
    assert (ctia.posted_at, ctia.seeking_locations, ctia.is_featured) == (None, [], False)
    hot_smirk = next(p for p in digest.postings if p.external_ref == "16057575")
    assert hot_smirk.title == "Hot Smirk"  # trailing space in the source


def test_role_fields(fixture_bytes):
    digest, _ = parse_fixture(fixture_bytes, "casting_networks_sample.eml")
    roles = roles_by_name(digest)
    women = roles["WOMEN 20s"]
    assert (women.billing_type, women.age_min, women.age_max) == ("Principal", 23, 29)
    assert women.genders == ["female"]  # "Woman" uses the same key as Backstage's "Female"
    assert roles["REAL FRIENDS"].genders == []  # "Multiple Genders" is treated as open
    assert roles["Everyday New Yorkers"].billing_type == "Co-Star"
    assert roles["Silenced Younger Adults"].billing_type == "Featured Background"


def test_apply_url_is_stored_verbatim(fixture_bytes):
    digest, raw = parse_fixture(fixture_bytes, "casting_networks_sample.eml")
    url = digest.postings[0].roles[0].apply_url
    assert url == (
        "https://app.castingnetworks.com/talent/project/16060767/role/67475310"
        "?source=savedsearch_email&default_app_context="
        "REDACTED"
    )
    for role in (r for p in digest.postings for r in p.roles):
        assert role.apply_url.startswith("https://app.castingnetworks.com/talent/project/")


def test_submission_deadline_is_earliest_role_deadline(fixture_bytes):
    digest, _ = parse_fixture(fixture_bytes, "casting_networks_sample.eml")
    by_ref = {p.external_ref: p for p in digest.postings}
    # LINE OF FIRE roles close at 12:00pm and 3:30pm on Oct 29.
    line_of_fire = by_ref["16049034"].submission_deadline
    assert line_of_fire == datetime(2026, 10, 29, 12, 0, tzinfo=DEADLINE_TZ)
    # Myron Bolitar: Nov 2 4:00am, Nov 2 4:00am, Oct 29 7:30pm.
    bolitar = by_ref["16049614"].submission_deadline
    assert bolitar == datetime(2026, 10, 29, 19, 30, tzinfo=DEADLINE_TZ)


def test_union_status_from_tag_and_role_names(fixture_bytes):
    digest, _ = parse_fixture(fixture_bytes, "casting_networks_sample.eml")
    by_title = {p.title: p.union_status for p in digest.postings}
    assert by_title["Elsbeth"] == "union"  # SAG-AFTRA, "SAGAFTRA to portray", "Union avail"
    assert by_title["DOLCE"] == "union_and_nonunion"  # SAG-AFTRA project, "(NONSAG COVERED)" roles
    assert by_title["LINE OF FIRE"] == "union_and_nonunion"  # "NU to portray ..."
    assert by_title["AVAILABILITY"] == "union_and_nonunion"  # tag "Other", "UNION/NON"
    assert by_title["Amex"] == "nonunion"  # "No Union Affiliation"


def test_routed_by_registry():
    assert get_adapter_for("notifications@castingnetworks.com", {}).source_key == "casting_networks"


# --- synthetic edge cases --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("September 29, 2026, 8:00pm", datetime(2026, 9, 29, 20, 0, tzinfo=DEADLINE_TZ)),
        ("November 02, 2026, 4:00am", datetime(2026, 11, 2, 4, 0, tzinfo=DEADLINE_TZ)),
        ("  October 1, 2026,  12:00PM ", datetime(2026, 10, 1, 12, 0, tzinfo=DEADLINE_TZ)),
        ("Sept 29 2026", None),
        ("", None),
    ],
)
def test_parse_deadline(text, expected):
    assert parse_deadline(text) == expected


def test_deadline_matches_what_the_app_shows():
    # Role 67497529: the email says Nov 30 4:00am, the app shows 9:00am EST.
    eastern = ZoneInfo("America/New_York")
    deadline = parse_deadline("November 30, 2026, 4:00am")
    assert deadline.astimezone(eastern) == datetime(2026, 11, 30, 9, 0, tzinfo=eastern)
    # Midnight Eastern prints as 7:00pm the day before, in both DST periods.
    for day in ("October 20, 2026, 7:00pm", "November 20, 2026, 7:00pm"):
        assert parse_deadline(day).astimezone(eastern).strftime("%H:%M") == "00:00"


@pytest.mark.parametrize(
    ("tag", "roles", "expected"),
    [
        ("Non Union", ["Model"], "nonunion"),
        ("SAG-AFTRA", ["Lead"], "union"),
        ("SAG-AFTRA", ["Pedestrians (non-SAG-AFTRA COVERED)"], "union_and_nonunion"),
        ("Other", ["Soldiers"], None),
        ("Other", ["Union avail Monday"], "union"),
        ("Non Union", ["NU walkers"], "nonunion"),
    ],
)
def test_union_status_rules(tag, roles, expected):
    errors: list[str] = []
    assert union_status(tag, roles, "p", errors) == expected
    assert errors == []


def test_unrecognized_union_tag_is_reported():
    errors: list[str] = []
    assert union_status("Teamsters", ["Driver"], "posting 'X'", errors) is None
    assert errors == ["posting 'X': union_status: unrecognized tag 'Teamsters'"]


def test_unparseable_deadline_and_age_make_partial(make_email):
    digest = parse_html(
        make_email,
        card(due="sometime soon", details="<b>Principal</b> / 18 to 24 / Woman"),
    )
    assert digest.status == "partial"
    [posting] = digest.postings
    assert posting.submission_deadline is None
    [role] = posting.roles
    assert (role.age_min, role.age_max, role.genders) == (None, None, ["female"])
    errors = " | ".join(digest.field_errors)
    assert len(digest.field_errors) == 2
    assert "submission_deadline: unparseable 'sometime soon'" in errors
    assert "age: unparseable '18 to 24'" in errors


def test_role_line_without_age_or_gender(make_email):
    digest = parse_html(make_email, card(details="<b>Lead</b>"))
    [role] = digest.postings[0].roles
    assert (role.billing_type, role.age_min, role.genders) == ("Lead", None, [])
    assert digest.status == "success"


def test_missing_view_role_link_keeps_role_as_own_posting(make_email):
    html = card(title="A", href=None) + card(title="A", href=None)
    digest = parse_html(make_email, html)
    assert digest.status == "partial"
    assert [p.external_ref for p in digest.postings] == [None, None]
    assert all("apply_url: missing" in e for e in digest.field_errors)


def test_no_cards_is_failed(make_email):
    digest = parse_html(make_email, "<html><body><p>No new roles</p></body></html>")
    assert digest.status == "failed"
    assert digest.error == "no role cards found in Casting Networks digest"


def test_no_html_part_is_failed(make_email):
    msg = make_email(from_addr="notifications@castingnetworks.com")
    digest = adapter.parse(msg.as_bytes(), datetime(2026, 10, 30, tzinfo=UTC))
    assert digest.error == "email has no text/html part"
