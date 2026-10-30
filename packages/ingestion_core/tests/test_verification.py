import pytest

from ingestion_core.parsing.mime import load_message
from ingestion_core.verification import aligned, verify_sender

SES_DKIM_PASS = (
    "amazonses.com; spf=pass (spf: domain of redacted+caf_=jobs@gmail.com designates "
    "1.2.3.4 as permitted sender) client-ip=1.2.3.4; "
    "envelope-from=redacted+caf_=jobs@gmail.com; helo=mail.gmail.com; "
    "dkim=pass header.i=@send.backstage.com; dmarc=pass header.from=backstage.com;"
)
# Phase 0's key finding: SPF passes after the Gmail hop, but for gmail.com.
SES_SPF_UNALIGNED_DKIM_FAIL = (
    "amazonses.com; spf=pass client-ip=1.2.3.4; "
    "envelope-from=redacted+caf_=jobs@gmail.com; "
    "dkim=fail header.i=@send.backstage.com; dmarc=fail header.from=backstage.com;"
)
SES_SPF_ALIGNED_NO_DKIM = (
    "amazonses.com; spf=pass client-ip=1.2.3.4; envelope-from=bounce@mail.backstage.com; "
    "dkim=none; dmarc=pass header.from=backstage.com;"
)
SES_DKIM_PASS_WRONG_DOMAIN = (
    "amazonses.com; spf=fail envelope-from=x@evil.example; "
    "dkim=pass header.i=@evil.example; dmarc=fail header.from=backstage.com;"
)
GOOGLE = "mx.google.com; dkim=pass header.i=@send.backstage.com; spf=pass"


@pytest.mark.parametrize(
    "name, domain",
    [
        ("backstage_sample.eml", "backstage.com"),
        ("backstage_badges.eml", "backstage.com"),
        ("casting_networks_sample.eml", "castingnetworks.com"),
        ("casting_networks_single_role.eml", "castingnetworks.com"),
    ],
)
def test_real_forwarded_fixtures_verify_via_dkim(fixture_bytes, name, domain):
    verdict = verify_sender(load_message(fixture_bytes(name)))
    assert verdict.verified
    assert verdict.details["verified_by"] == "dkim"
    assert verdict.details["from_domain"] == domain
    # Gmail's rewritten envelope sender must never count
    assert verdict.details["spf"]["aligned"] is False


def test_dkim_pass_aligned(make_email):
    verdict = verify_sender(make_email(auth_results=[SES_DKIM_PASS, GOOGLE]))
    assert verdict.verified and verdict.details["verified_by"] == "dkim"


def test_spf_pass_unaligned_and_dkim_fail_is_quarantined(make_email):
    verdict = verify_sender(make_email(auth_results=[SES_SPF_UNALIGNED_DKIM_FAIL]))
    assert not verdict.verified
    assert verdict.details["spf"] == {
        "result": "pass",
        "envelope_from_domain": "gmail.com",
        "aligned": False,
    }


def test_spf_pass_aligned_without_dkim(make_email):
    verdict = verify_sender(make_email(auth_results=[SES_SPF_ALIGNED_NO_DKIM]))
    assert verdict.verified and verdict.details["verified_by"] == "spf"


def test_spoofed_from_with_foreign_dkim_is_quarantined(make_email):
    verdict = verify_sender(make_email(auth_results=[SES_DKIM_PASS_WRONG_DOMAIN]))
    assert not verdict.verified


def test_only_topmost_header_is_trusted(make_email):
    # A forged lower SES header can't rescue a failing top one...
    msg = make_email(auth_results=[SES_SPF_UNALIGNED_DKIM_FAIL, SES_DKIM_PASS])
    assert not verify_sender(msg).verified
    # ...and a top header from anyone but SES is rejected outright.
    msg = make_email(auth_results=[GOOGLE, SES_DKIM_PASS])
    verdict = verify_sender(msg)
    assert not verdict.verified
    assert "mx.google.com" in verdict.details["reason"]


def test_missing_header(make_email):
    verdict = verify_sender(make_email())
    assert not verdict.verified
    assert verdict.details["reason"] == "no Authentication-Results header"


@pytest.mark.parametrize(
    "domain, from_domain, expected",
    [
        ("backstage.com", "backstage.com", True),
        ("send.backstage.com", "backstage.com", True),
        ("backstage.com", "send.backstage.com", True),
        ("BACKSTAGE.com", "backstage.com", True),
        ("notbackstage.com", "backstage.com", False),
        ("gmail.com", "backstage.com", False),
        (None, "backstage.com", False),
    ],
)
def test_aligned(domain, from_domain, expected):
    assert aligned(domain, from_domain) is expected
