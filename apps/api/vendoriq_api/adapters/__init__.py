"""Data-source adapters — one interface, every source (brief §5, spec §6).

```python
adapter = build(AdapterKey.GENERIC_REST, config)
for observation in adapter.pull(vendor, since):   # Observation[]
    ...
```

The register is indifferent to where a number came from and always knows: every adapter
stamps its own ``ObservationSource`` on what it returns, and the trust order of spec §6.6
does the rest (ADR-004). What differs between the seven entries below is only how the bytes
are obtained.

| Key | What it is |
|---|---|
| ``generic_rest`` | Working. A configured endpoint, an auth header, a field map. |
| ``csv`` | Working. The same connector reading ``text/csv``. |
| ``erp_1c`` / ``erp_sap`` / ``erp_odoo`` | Mocked. Same class, fixture instead of a GET. |
| ``registry`` | Refuses. Highest trust rank, so it never guesses (spec §6.4). |
| ``excel`` | The eleven-sheet form; the importer is an adapter too. |
"""

from __future__ import annotations

from ..models.enums import CONTRACT_ADAPTER_KEYS, AdapterKey
from .base import (
    MASKED_SENTINEL,
    AdapterConfig,
    AdapterError,
    AdapterNotConfiguredError,
    AdapterStatus,
    AdapterUnreachableError,
    AuthType,
    Observation,
    PullResult,
    SourceAdapter,
    VendorRef,
    mask_secret,
)
from .erp import Erp1CAdapter, ErpOdooAdapter, ErpSapAdapter, MockedErpAdapter
from .excel import ExcelAdapter, observations_from_parsed
from .generic import CsvAdapter, GenericRestAdapter
from .registry import PLANNED_CHECKS, RegistryAdapter

#: Every adapter the contract's ``AdapterKey`` names, in the order the screen lists them.
ADAPTERS: dict[AdapterKey, type[SourceAdapter]] = {
    AdapterKey.GENERIC_REST: GenericRestAdapter,
    AdapterKey.CSV: CsvAdapter,
    AdapterKey.ERP_1C: Erp1CAdapter,
    AdapterKey.ERP_SAP: ErpSapAdapter,
    AdapterKey.ERP_ODOO: ErpOdooAdapter,
    AdapterKey.REGISTRY: RegistryAdapter,
    AdapterKey.EXCEL: ExcelAdapter,
}

#: Adapters an admin configures per vendor. ``excel`` is driven by an upload, ``registry``
#: by a government API that does not exist yet, so neither takes a per-vendor endpoint.
CONFIGURABLE: frozenset[AdapterKey] = frozenset(
    {
        AdapterKey.GENERIC_REST,
        AdapterKey.CSV,
        AdapterKey.ERP_1C,
        AdapterKey.ERP_SAP,
        AdapterKey.ERP_ODOO,
    }
)


def build(key: AdapterKey, config: AdapterConfig | None = None) -> SourceAdapter:
    """Instantiate one adapter. Unknown key is a programming error, not a 404."""
    try:
        adapter_class = ADAPTERS[key]
    except KeyError as exc:  # pragma: no cover - guarded by test_the_registry_covers_the_contract
        raise KeyError(f"no adapter registered for {key!r}") from exc
    return adapter_class(config or AdapterConfig(adapter=key))


__all__ = [
    "ADAPTERS",
    "CONFIGURABLE",
    "CONTRACT_ADAPTER_KEYS",
    "MASKED_SENTINEL",
    "PLANNED_CHECKS",
    "AdapterConfig",
    "AdapterError",
    "AdapterKey",
    "AdapterNotConfiguredError",
    "AdapterStatus",
    "AdapterUnreachableError",
    "AuthType",
    "CsvAdapter",
    "Erp1CAdapter",
    "ErpOdooAdapter",
    "ErpSapAdapter",
    "ExcelAdapter",
    "GenericRestAdapter",
    "MockedErpAdapter",
    "Observation",
    "PullResult",
    "RegistryAdapter",
    "SourceAdapter",
    "VendorRef",
    "build",
    "mask_secret",
    "observations_from_parsed",
]
