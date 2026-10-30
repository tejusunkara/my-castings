from email.message import EmailMessage
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_bytes():
    def load(name: str) -> bytes:
        return (FIXTURES / name).read_bytes()

    return load


@pytest.fixture
def make_email():
    """Builds a minimal synthetic email for cases the real fixtures don't cover."""

    def build(
        *,
        html: str | None = None,
        text: str = "plain body",
        from_addr: str = "noreply@backstage.com",
        auth_results: list[str] | None = None,
    ) -> EmailMessage:
        msg = EmailMessage()
        # Real SES mail has the topmost (SES-written) header first.
        for value in auth_results or []:
            msg["Authentication-Results"] = value
        msg["From"] = from_addr
        msg["To"] = "jobs@mail.allcastings.fyi"
        msg["Subject"] = "test"
        msg["Date"] = "Thu, 29 Oct 2026 18:13:43 +0000"
        msg.set_content(text)
        if html is not None:
            msg.add_alternative(html, subtype="html")
        return msg

    return build
