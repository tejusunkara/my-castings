from collections.abc import Mapping
from datetime import datetime

import pytest

from ingestion_core.adapters.base import CastingSourceAdapter, domain_matches
from ingestion_core.adapters.registry import (
    AdapterRegistry,
    AmbiguousAdapterMatchError,
    get_adapter_for,
)
from ingestion_core.types import ParsedDigest


class DomainAdapter(CastingSourceAdapter):
    def __init__(self, source_key: str, domain: str):
        self.source_key = source_key
        self.domain = domain

    def matches_sender(self, from_address: str, headers: Mapping[str, str]) -> bool:
        return domain_matches(from_address, self.domain)

    def parse(self, raw_mime: bytes, received_at: datetime) -> ParsedDigest:
        return ParsedDigest()


registry = AdapterRegistry(
    [
        DomainAdapter("backstage", "backstage.com"),
        DomainAdapter("casting_networks", "castingnetworks.com"),
        DomainAdapter("greedy", "send.backstage.com"),
    ]
)


def test_exactly_one_match():
    adapter = registry.get_adapter_for("x@castingnetworks.com", {})
    assert adapter.source_key == "casting_networks"


def test_no_match_returns_none():
    assert registry.get_adapter_for("x@example.com", {}) is None


def test_multiple_matches_raise():
    with pytest.raises(AmbiguousAdapterMatchError) as exc:
        registry.get_adapter_for("x@send.backstage.com", {})
    assert exc.value.source_keys == ["backstage", "greedy"]
    assert "backstage, greedy" in str(exc.value)


def test_default_registry_routes_backstage():
    assert get_adapter_for("noreply@backstage.com", {}).source_key == "backstage"
