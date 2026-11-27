"""The repository is public: real emails saved as fixtures must be scrubbed first.

Fails when a fixture still carries something tied to the real account: tracking or login
tokens in links, unsubscribe tokens, the Casting Networks account context, or a personal
address. Scrub by replacing the values with REDACTED (see git history for the script used
on the first fixtures), then run this test.
"""

import re
from email import message_from_bytes, policy
from pathlib import Path

import pytest

FIXTURES = sorted((Path(__file__).parent / "fixtures").glob("*.eml"))

# Value patterns that identify the recipient; each must be REDACTED in fixtures.
_VALUE = r"[^&\s\"'<>]"
_EQUALS = r"(?:=|%3D|&#x3D;)"
TOKEN_PATTERNS = {
    "SendGrid tracking id (upn=)": rf"upn=(?!REDACTED){_VALUE}+",
    "Casting Networks account context": rf"default_app_context{_EQUALS}(?!REDACTED){_VALUE}+",
    "Casting Networks saved search id": rf"savedSearchId{_EQUALS}(?!REDACTED){_VALUE}+",
    "Backstage tracked link": r"go\.backstage\.com/(?:uni/)?ls/click\?(?!upn=REDACTED)",
    "unsubscribe token": (
        rf"unsub(?:scribe)?/?\?{_VALUE}*(?:token|a)=(?!REDACTED|0000000){_VALUE}{{6,}}"
    ),
    "encoded artist id": r"eyJyb2xlQ29kZ",
}
# Addresses allowed to appear: placeholders, the app's own inbox, and sender addresses.
ALLOWED_ADDRESS = re.compile(
    r"(redacted(\+[^@]*)?@gmail\.com|@(mail\.)?allcastings\.fyi|@[\w.-]*(backstage\.com|"
    r"castingnetworks\.com|actorsaccess\.com|sendgrid\.(net|info)|google\.com|amazonses\.com|"
    r"amazon\.com|example\.com))$",
    re.IGNORECASE,
)


def all_text(raw: bytes) -> str:
    msg = message_from_bytes(raw, policy=policy.default)
    headers = " ".join(f"{k}: {v}" for part in msg.walk() for k, v in part.items())
    bodies = "".join(
        part.get_content()
        for part in msg.walk()
        if part.get_content_maintype() == "text" and not part.is_multipart()
    )
    # Decoded only: quoted-printable bytes split and escape values (upn=3D..., RED=\nACTED).
    return headers + "\n" + bodies


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_has_no_account_tokens(path):
    text = all_text(path.read_bytes())
    found = {
        name: re.search(pattern, text).group(0)[:60]
        for name, pattern in TOKEN_PATTERNS.items()
        if re.search(pattern, text)
    }
    assert not found, f"{path.name} still has account-linked values: {found}"


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_has_no_personal_gmail(path):
    text = all_text(path.read_bytes())
    gmail = {
        a
        for a in re.findall(r"[\w.+=-]+@gmail\.com", text, re.IGNORECASE)
        # "header.i=@gmail.com" in DKIM results names only the domain, not an address.
        if not a.split("@")[0].endswith("=") and not ALLOWED_ADDRESS.search(a)
    }
    assert not gmail, f"{path.name} has personal addresses: {sorted(gmail)}"


def test_the_guard_catches_a_real_token():
    leaked = (
        "https://app.castingnetworks.com/x?default_app_context&#x3D;eyJyb2xlQ29kZSI6IlRBTEVOVCJ9"
    )
    assert re.search(TOKEN_PATTERNS["Casting Networks account context"], leaked)
    assert not re.search(
        TOKEN_PATTERNS["Casting Networks account context"], "default_app_context=REDACTED"
    )
