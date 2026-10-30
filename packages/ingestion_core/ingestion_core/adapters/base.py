"""The adapter contract every casting source plugs into.

Adding a source = one new adapter class registered in adapters/registry.py plus a
casting_sources row. The Lambda handler, schema and frontend don't change.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from datetime import datetime

from ingestion_core.parsing.mime import address_domain
from ingestion_core.types import ParsedDigest


class CastingSourceAdapter(ABC):
    source_key: str  # "backstage", "casting_networks", later "actors_access"

    @abstractmethod
    def matches_sender(self, from_address: str, headers: Mapping[str, str]) -> bool: ...

    @abstractmethod
    def parse(self, raw_mime: bytes, received_at: datetime) -> ParsedDigest:
        """Must not raise on a malformed digest: return ParsedDigest(error=...) instead."""


def domain_matches(from_address: str, domain: str) -> bool:
    """True for the domain itself or any subdomain (noreply@send.backstage.com)."""
    sender = address_domain(from_address)
    return sender == domain or sender.endswith("." + domain)
