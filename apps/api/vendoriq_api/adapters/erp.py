"""1C, SAP and Odoo — mocked against the real interface (brief §2, §8).

Real connectivity to these three is an explicit non-goal of this run. What is *not* a
non-goal is the interface: each family is a full :class:`~.generic.GenericRestAdapter` with
its own remote shape, its own identity field and its own default field map, and the only
thing it does differently from the working connector is where the bytes come from.

```python
def _fetch(self, vendor, since):          # GenericRestAdapter — an HTTP GET
def _fetch(self, vendor, since):          # here — the family's fixture file
```

Everything downstream — configuration checks, path resolution, value coercion, warnings,
the observations written and the sync-log row — is the same code. Replacing a fixture with
a live call is deleting one method.

The fixtures answer for **fictional vendors**. A mocked connector that returned turnover for
one of the thirteen real companies in the register would put an invented number behind a
real name, and the provenance layer would faithfully record it as coming from an ERP. A
vendor the fixture does not carry gets an honest "this mock has no record for you".
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import ClassVar

from ..models.enums import AdapterKey
from .base import AdapterUnreachableError, VendorRef
from .generic import GenericRestAdapter
from .mapping import resolve_path

FIXTURE_DIR = Path(__file__).parent / "fixtures"


class MockedErpAdapter(GenericRestAdapter):
    """Shared behaviour of the three ERP mocks: read the fixture, find *this* vendor."""

    #: File under ``fixtures/`` holding the family's canned response.
    fixture_name: ClassVar[str]
    #: Path to the list of records inside the family's envelope.
    records_path: ClassVar[str]
    #: Path, inside one record, to the tax id the record is matched on.
    identity_path: ClassVar[str]

    def _fetch(self, vendor: VendorRef, since: datetime | None) -> tuple[bytes, str]:
        """The single method that separates a mock from the live connector."""
        path = FIXTURE_DIR / self.fixture_name
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:  # pragma: no cover - a corrupt shipped fixture
            raise AdapterUnreachableError(
                "fixture_unreadable",
                f"{self.name_en}: the fixture response could not be read.",
                f"{self.name_az}: nümunə cavab oxunmadı.",
            ) from exc

        records = resolve_path(envelope, self.records_path)
        wanted = vendor.remote_key
        for record in records if isinstance(records, list) else []:
            if str(resolve_path(record, self.identity_path) or "") == wanted:
                # The source ref names the mock, so nobody mistakes this for a live pull.
                return json.dumps(record).encode("utf-8"), f"mock:{self.key.value}/{wanted}"
        raise AdapterUnreachableError(
            "mock_record_not_found",
            (
                f"{self.name_en} is a fixture-backed mock and holds no record for "
                f"{vendor.legal_name} ({wanted}). No value was written."
            ),
            (
                f"{self.name_az} nümunə əsaslı imitasiyadır və {vendor.legal_name} "
                f"({wanted}) üçün qeydi yoxdur. Heç bir dəyər yazılmadı."
            ),
        )


class Erp1CAdapter(MockedErpAdapter):
    """1C OData — ``Catalog_Kontragenty`` with the indicators under ``Pokazateli``."""

    key: ClassVar[AdapterKey] = AdapterKey.ERP_1C
    fixture_name: ClassVar[str] = "erp_1c.json"
    records_path: ClassVar[str] = "value"
    identity_path: ClassVar[str] = "INN"
    name_az: ClassVar[str] = "1C (imitasiya)"
    name_en: ClassVar[str] = "1C (mocked)"
    description_az: ClassVar[str] = (
        "1C OData konnektoru. Bu buraxılışda nümunə cavabla işləyir — interfeys realdır, "
        "mənbə deyil."
    )
    description_en: ClassVar[str] = (
        "1C OData connector. Fixture-backed in this release — the interface is real, the "
        "source is not."
    )
    default_field_map: ClassVar[dict[str, str]] = {
        "Pokazateli.VyruchkaSredniaya3Goda": "B.1",
        "Pokazateli.SobstvennyKapital": "B.2",
        "Pokazateli.ChislennostPersonala": "E.1",
        "Pokazateli.ChislennostITR": "E.2",
        "Proekty.Zavershennye": "C.1",
        "Proekty.MaksimalnayaStoimost": "C.2",
        "Proekty.Tekushchie": "C.3",
    }


class ErpSapAdapter(MockedErpAdapter):
    """SAP OData v2 — ``{"d": {"results": [...]}}``, matched on ``Stceg`` (VAT number)."""

    key: ClassVar[AdapterKey] = AdapterKey.ERP_SAP
    fixture_name: ClassVar[str] = "erp_sap.json"
    records_path: ClassVar[str] = "d.results"
    identity_path: ClassVar[str] = "Stceg"
    name_az: ClassVar[str] = "SAP (imitasiya)"
    name_en: ClassVar[str] = "SAP (mocked)"
    description_az: ClassVar[str] = (
        "SAP OData konnektoru. Bu buraxılışda nümunə cavabla işləyir — interfeys realdır, "
        "mənbə deyil."
    )
    description_en: ClassVar[str] = (
        "SAP OData connector. Fixture-backed in this release — the interface is real, the "
        "source is not."
    )
    default_field_map: ClassVar[dict[str, str]] = {
        "Financials.AnnualTurnoverAvg3Y": "B.1",
        "Financials.Equity": "B.2",
        "Headcount.Total": "E.1",
        "Headcount.Engineers": "E.2",
        "Projects.Completed": "C.1",
        "Projects.LargestValue": "C.2",
        "Projects.Ongoing": "C.3",
    }


class ErpOdooAdapter(MockedErpAdapter):
    """Odoo JSON-RPC — a flat ``res.partner`` record under ``result``, matched on ``vat``."""

    key: ClassVar[AdapterKey] = AdapterKey.ERP_ODOO
    fixture_name: ClassVar[str] = "erp_odoo.json"
    records_path: ClassVar[str] = "result"
    identity_path: ClassVar[str] = "vat"
    name_az: ClassVar[str] = "Odoo (imitasiya)"
    name_en: ClassVar[str] = "Odoo (mocked)"
    description_az: ClassVar[str] = (
        "Odoo JSON-RPC konnektoru. Bu buraxılışda nümunə cavabla işləyir — interfeys "
        "realdır, mənbə deyil."
    )
    description_en: ClassVar[str] = (
        "Odoo JSON-RPC connector. Fixture-backed in this release — the interface is real, "
        "the source is not."
    )
    default_field_map: ClassVar[dict[str, str]] = {
        "x_turnover_avg_3y": "B.1",
        "x_equity": "B.2",
        "x_employee_count": "E.1",
        "x_engineer_count": "E.2",
        "x_projects_completed": "C.1",
        "x_project_largest_value": "C.2",
        "x_projects_ongoing": "C.3",
    }
