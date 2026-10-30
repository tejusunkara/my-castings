"""Thin helpers over the stdlib email package."""

from datetime import datetime
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime


def load_message(raw_mime: bytes) -> EmailMessage:
    return message_from_bytes(raw_mime, policy=policy.default)  # type: ignore[return-value]


def html_body(msg: EmailMessage) -> str | None:
    part = msg.get_body(preferencelist=("html",))
    return part.get_content() if part is not None else None


def from_address(msg: EmailMessage) -> str:
    return parseaddr(str(msg.get("From", "")))[1].lower()


def address_domain(address: str) -> str:
    return address.rpartition("@")[2].lower().strip(">").strip()


def sent_at(msg: EmailMessage) -> datetime | None:
    """The original Date header (Gmail forwarding preserves it)."""
    value = msg.get("Date")
    if not value:
        return None
    try:
        return parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return None
