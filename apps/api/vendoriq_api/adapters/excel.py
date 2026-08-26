"""The Excel importer, as an adapter (spec §6, brief §5).

The build brief lists the importer among the adapters on purpose: "every source is an
adapter, the Excel importer is one too". Treating it as a special case is how a system ends
up with two ways of writing a value — one that records provenance and one that does not.

The parsing is not repeated here. ``packages/excel_import`` already reads the eleven-sheet
form, addresses cells by their code, normalises the quirks of brief §1.11 and reports the
anomalies; this class is the thin piece that turns its output into
:class:`~.base.Observation` objects with ``source = excel`` and hands the warnings on
unchanged.

``pull`` reads the workbook named by ``base_url`` (a filesystem path for this adapter —
there is no other place in the contract's ``AdapterConfig`` for "where the file is"), which
is what makes a watched-mailbox drop folder possible later. The interactive two-step import
the officer uses does not go through ``pull``: it calls :func:`observations_from_parsed`
directly, because the preview must be able to parse without any configuration at all.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import ClassVar

from vendoriq_excel_import import ParsedApplication, parse_application_form

from ..models.enums import AdapterKey, ObservationSource
from .base import (
    AdapterNotConfiguredError,
    AdapterStatus,
    AdapterUnreachableError,
    Observation,
    PullResult,
    SourceAdapter,
    VendorRef,
)


def observations_from_parsed(parsed: ParsedApplication, source_ref: str) -> list[Observation]:
    """``ParsedApplication`` → observations, using the parser's own row shape (ADR-004).

    ``ParsedApplication.to_observations`` already produces the ``field_observation`` row
    dicts; this only lifts them into the adapter's value type so that an Excel import and
    an ERP pull are written by the same code path.
    """
    return [
        Observation(
            field_code=str(row["field_code"]),
            value=row["value"]["value"],
            source=ObservationSource.EXCEL,
            source_ref=source_ref,
            unit=row.get("unit"),
        )
        for row in parsed.to_observations(source="excel", source_ref=source_ref)
    ]


class ExcelAdapter(SourceAdapter):
    """The eleven-sheet application form as a data source."""

    key: ClassVar[AdapterKey] = AdapterKey.EXCEL
    source: ClassVar[ObservationSource] = ObservationSource.EXCEL
    default_status: ClassVar[AdapterStatus] = "active"
    name_az: ClassVar[str] = "Excel müraciət forması"
    name_en: ClassVar[str] = "Excel application form"
    description_az: ClassVar[str] = (
        "11 vərəqəli müraciət formasının oxunması: sahələr kod üzrə, sənəd siyahısı və "
        "məmur üçün anomaliya xəbərdarlıqları. Yazmadan öncə önizləmə təsdiqlənir."
    )
    description_en: ClassVar[str] = (
        "Reads the 11-sheet application form: fields by code, the document checklist and "
        "the anomaly warnings for the officer. The preview is confirmed before anything "
        "is written."
    )

    def pull(self, vendor: VendorRef, since: datetime | None = None) -> PullResult:
        """Parse the configured workbook. ``since`` is meaningless for a file and ignored."""
        if not self.config.base_url:
            raise AdapterNotConfiguredError(
                "adapter_not_configured",
                "No workbook path is configured for the Excel adapter.",
                "Excel adapteri üçün fayl yolu təyin edilməyib.",
            )
        path = Path(self.config.base_url)
        if not path.is_file():
            raise AdapterUnreachableError(
                "workbook_not_found",
                f"No workbook at {path.name}.",
                f"{path.name} adlı fayl tapılmadı.",
            )
        try:
            parsed = parse_application_form(path)
        except Exception as exc:  # openpyxl raises a family of unrelated errors
            raise AdapterUnreachableError(
                "workbook_unreadable",
                f"{path.name} could not be read as an .xlsx application form.",
                f"{path.name} .xlsx müraciət forması kimi oxunmadı.",
            ) from exc
        return PullResult.of(
            observations_from_parsed(parsed, path.name),
            tuple(parsed.warnings),
        )
