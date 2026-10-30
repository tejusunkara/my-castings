"""Picks the adapter for an inbound email. Three explicit outcomes:

- exactly one adapter claims the sender -> that adapter
- none claims it                        -> None (email stays stored, source_id null)
- two or more claim it                  -> AmbiguousAdapterMatchError (never silently pick)
"""

from collections.abc import Mapping, Sequence

from ingestion_core.adapters.backstage import BackstageAdapter
from ingestion_core.adapters.base import CastingSourceAdapter


class AmbiguousAdapterMatchError(Exception):
    def __init__(self, from_address: str, source_keys: list[str]):
        self.source_keys = source_keys
        super().__init__(
            f"multiple adapters claim sender {from_address!r}: {', '.join(source_keys)}"
        )


class AdapterRegistry:
    def __init__(self, adapters: Sequence[CastingSourceAdapter]):
        self.adapters = list(adapters)

    def get_adapter_for(
        self, from_address: str, headers: Mapping[str, str]
    ) -> CastingSourceAdapter | None:
        claimed = [a for a in self.adapters if a.matches_sender(from_address, headers)]
        if len(claimed) > 1:
            raise AmbiguousAdapterMatchError(from_address, [a.source_key for a in claimed])
        return claimed[0] if claimed else None


default_registry = AdapterRegistry([BackstageAdapter()])


def get_adapter_for(from_address: str, headers: Mapping[str, str]) -> CastingSourceAdapter | None:
    return default_registry.get_adapter_for(from_address, headers)
