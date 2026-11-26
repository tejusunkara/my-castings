from datetime import UTC, datetime, timedelta

import pytest

from ingestion_core.adapters.backstage import BackstageAdapter
from ingestion_core.parsing.mime import html_body, load_message, sent_at

adapter = BackstageAdapter()


def parse_fixture(fixture_bytes, name):
    raw = fixture_bytes(name)
    received_at = sent_at(load_message(raw))
    return adapter.parse(raw, received_at), received_at, raw


def test_sample_counts(fixture_bytes):
    digest, _, _ = parse_fixture(fixture_bytes, "backstage_sample.eml")
    assert digest.status == "success"
    assert digest.field_errors == []
    assert [len(p.roles) for p in digest.postings] == [1, 1, 2, 1, 3]


def test_posted_at_is_received_minus_relative_age(fixture_bytes):
    digest, received_at, _ = parse_fixture(fixture_bytes, "backstage_sample.eml")
    # First card: "Posted 1 day, 20 hours ago"
    assert received_at == datetime(2026, 10, 29, 18, 13, 43, tzinfo=UTC)
    assert digest.postings[0].posted_at == received_at - timedelta(days=1, hours=20)


def test_posting_fields(fixture_bytes):
    digest, _, _ = parse_fixture(fixture_bytes, "backstage_sample.eml")
    first = digest.postings[0]
    assert first.title == "Bedding Brand E-Comm Photoshoot"
    assert first.project_type == "Photography / Stills"
    assert first.union_status == "nonunion"
    assert first.category_tag == "Photography / Stills · $ Paid · Nonunion"
    assert first.seeking_locations == ["New York, NY"]
    assert first.description.startswith("Seeking one model")
    assert digest.postings[1].union_status == "union"
    assert digest.postings[4].seeking_locations == [
        "Leola, PA",
        "Philadelphia, PA",
        "Baltimore, MD",
    ]


def test_variable_length_role_lines(fixture_bytes):
    digest, _, _ = parse_fixture(fixture_bytes, "backstage_sample.eml")
    roles = {r.role_name: r for p in digest.postings for r in p.roles}
    # "Day Player, Female, Trans Female, 25-35": two genders
    sparrow = roles["Sparrow Huang"]
    assert (sparrow.billing_type, sparrow.genders) == ("Day Player", ["female", "trans female"])
    assert (sparrow.age_min, sparrow.age_max) == (25, 35)
    # Billing + age only: open to any gender
    goers = roles["Mosque Goers"]
    assert (goers.billing_type, goers.genders) == ("Background / Extra", [])
    assert (goers.age_min, goers.age_max) == (18, 80)


def test_open_ended_age(fixture_bytes):
    digest, _, _ = parse_fixture(fixture_bytes, "backstage_badges.eml")
    painter = next(r for p in digest.postings for r in p.roles if r.role_name == "Bob Ross Painter")
    assert (painter.age_min, painter.age_max) == (18, None)


def test_posting_and_role_badges_are_independent(fixture_bytes):
    digest, _, _ = parse_fixture(fixture_bytes, "backstage_badges.eml")
    by_title = {p.title: p for p in digest.postings}

    hurt = by_title["'This is Going to Hurt'"]
    assert hurt.is_featured
    assert all(r.is_featured for r in hurt.roles)

    # Featured posting whose roles carry no badge of their own
    dance = by_title["'Dance For Your Life'"]
    assert dance.is_featured
    assert not any(r.is_featured for r in dance.roles)

    assert not by_title["Family Street Interview Project"].is_featured
    # The badge is not mistaken for the project type
    assert hurt.project_type == "Student Film"


def test_apply_urls_preserved_verbatim(fixture_bytes):
    digest, _, raw = parse_fixture(fixture_bytes, "backstage_sample.eml")
    html = html_body(load_message(raw))
    urls = [r.apply_url for p in digest.postings for r in p.roles]
    assert len(urls) == 8 and len(set(urls)) == 8
    for url in urls:
        assert f'href="{url}"' in html.replace("&amp;", "&")


def test_sample_without_badges(fixture_bytes):
    digest, _, _ = parse_fixture(fixture_bytes, "backstage_sample.eml")
    assert not any(p.is_featured for p in digest.postings)
    assert not any(r.is_featured for p in digest.postings for r in p.roles)


CARD = """
<div class="section_job-card">
  <span class="job-tag">Short Film</span><span class="job-tag union">Nonunion</span>
  <em>Posted 3 hours ago</em>
  <h2><a href="https://example.com/job">Title</a></h2>
  <p>Description</p>
  <table><tbody>
    <tr><td><h4>Good Role</h4><ul><li>Lead, Female, 20-30</li></ul>
      <a class="primary-cta" href="https://example.com/apply/1">Apply</a></td></tr>
  </tbody></table>
  <table><tbody>
    <tr><td><h4>Bad Role</h4><ul><li>Supporting, Male, 18 to 24</li></ul>
      <a class="primary-cta" href="https://example.com/apply/2">Apply</a></td></tr>
  </tbody></table>
</div>
"""


def test_unparseable_field_is_partial_not_dropped(make_email):
    raw = make_email(html=f"<html><body>{CARD}</body></html>").as_bytes()
    digest = adapter.parse(raw, datetime(2026, 10, 29, tzinfo=UTC))
    assert digest.status == "partial"
    roles = digest.postings[0].roles
    assert [r.role_name for r in roles] == ["Good Role", "Bad Role"]
    assert (roles[0].age_min, roles[0].age_max) == (20, 30)
    assert (roles[1].age_min, roles[1].age_max) == (None, None)
    assert roles[1].genders == ["male"]
    assert "'Bad Role': age: unparseable '18 to 24'" in digest.error_summary


@pytest.mark.parametrize(
    "build_kwargs, expected_error",
    [
        ({"html": "<html><body><p>No jobs today</p></body></html>"}, "no job cards"),
        ({}, "no text/html part"),
    ],
)
def test_whole_email_failures_do_not_raise(make_email, build_kwargs, expected_error):
    raw = make_email(**build_kwargs).as_bytes()
    digest = adapter.parse(raw, datetime(2026, 10, 29, tzinfo=UTC))
    assert digest.status == "failed"
    assert expected_error in digest.error_summary


def test_garbage_bytes_do_not_raise():
    digest = adapter.parse(b"\x00\xff not an email", datetime(2026, 10, 29, tzinfo=UTC))
    assert digest.status == "failed"


@pytest.mark.parametrize(
    "address, expected",
    [
        ("noreply@backstage.com", True),
        ("noreply@send.backstage.com", True),
        ("noreply@notbackstage.com", False),
        ("notifications@castingnetworks.com", False),
    ],
)
def test_matches_sender(address, expected):
    assert adapter.matches_sender(address, {}) is expected


# --- pay ---


def test_pay_from_estimated_pay_line(fixture_bytes):
    digest, _, _ = parse_fixture(fixture_bytes, "backstage_sample.eml")
    pays = [r.pay for p in digest.postings for r in p.roles]
    assert pays[:3] == [
        "$850 for 9 hours of work",
        "$400 for 1 days of work",
        "$100 for 3 hours of work",
    ]
    assert all(pays)


def test_role_without_pay_line(fixture_bytes):
    digest, _, _ = parse_fixture(fixture_bytes, "backstage_badges.eml")
    roles = {r.role_name: r for p in digest.postings for r in p.roles}
    assert roles["Eleanor"].pay is None


def pay_card(pay_line: str) -> str:
    return CARD.replace(
        "<li>Lead, Female, 20-30</li>", f"<li>Lead, Female, 20-30</li><li>{pay_line}</li>"
    )


@pytest.mark.parametrize(
    "pay_line, expected",
    [
        ("Estimated pay amount: $250 for None days of work", "$250"),
        ("Estimated pay amount:  $1500 for 8 hours of work ", "$1500 for 8 hours of work"),
        ("Estimated pay amount:", None),
    ],
)
def test_pay_text_cleanup(make_email, pay_line, expected):
    raw = make_email(html=f"<html><body>{pay_card(pay_line)}</body></html>").as_bytes()
    digest = adapter.parse(raw, datetime(2026, 10, 29, tzinfo=UTC))
    assert digest.postings[0].roles[0].pay == expected
