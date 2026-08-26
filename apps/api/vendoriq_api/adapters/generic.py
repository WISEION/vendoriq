"""The working connector: a configurable REST endpoint and its CSV twin (spec §6.3).

This is the adapter that actually talks to something. Everything the mocked ERP families do
they inherit from here; the only method they replace is :meth:`GenericRestAdapter._fetch`.
That is the whole point of the arrangement — the day a real 1C endpoint exists, the change
is deleting one ``_fetch`` override, not rewriting an integration.

Configuration is three things (contract ``AdapterConfig``): where to call (``base_url``),
how to authenticate (``auth_type`` + ``username``/``secret``) and what the answer means
(``field_map``). The endpoint is called with the vendor's remote key substituted into the
URL — ``{vendor}`` if the template names it, appended as ``?vendor=`` otherwise — and
``since`` is passed as an ISO-8601 query parameter for a source that can filter.
"""

from __future__ import annotations

import urllib.parse
from datetime import datetime
from typing import ClassVar, Literal

from vendoriq_excel_import import ImportWarning

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
from .mapping import observations_from, parse_csv, parse_json
from .transport import TransportError, auth_header, request

#: Placeholder a configured URL may use to say where the vendor key goes.
VENDOR_PLACEHOLDER = "{vendor}"


class GenericRestAdapter(SourceAdapter):
    """A JSON endpoint published by any ERP, mapped onto field codes by configuration."""

    key: ClassVar[AdapterKey] = AdapterKey.GENERIC_REST
    source: ClassVar[ObservationSource] = ObservationSource.API
    default_status: ClassVar[AdapterStatus] = "needs_configuration"
    name_az: ClassVar[str] = "Ümumi REST"
    name_en: ClassVar[str] = "Generic REST"
    description_az: ClassVar[str] = (
        "Sistemin dərc etdiyi REST müqaviləsi: hər təchizatçı üçün ünvan, "
        "avtorizasiya başlığı və sahə uyğunlaşdırması."
    )
    description_en: ClassVar[str] = (
        "The REST contract the system publishes: a per-vendor endpoint, an auth header "
        "and a field mapping."
    )
    #: ``json`` or ``csv`` — how the response body is read.
    payload_format: ClassVar[Literal["json", "csv"]] = "json"
    #: What an adapter family knows about its own remote shape before an admin types anything.
    default_field_map: ClassVar[dict[str, str]] = {}

    # ── configuration ───────────────────────────────────────────────────────
    @property
    def field_map(self) -> dict[str, str]:
        """The configured mapping, falling back to the family's own defaults."""
        return dict(self.config.field_map) or dict(self.default_field_map)

    def require_configuration(self) -> None:
        """Refuse to run half-configured. Contract: 409, not a silent empty result."""
        if not self.config.is_enabled:
            raise AdapterNotConfiguredError(
                "adapter_disabled",
                f"The {self.name_en} connector is not enabled for this vendor.",
                f"{self.name_az} konnektoru bu təchizatçı üçün aktiv deyil.",
            )
        if not self.config.base_url:
            raise AdapterNotConfiguredError(
                "adapter_not_configured",
                f"The {self.name_en} connector has no endpoint configured for this vendor.",
                f"{self.name_az} konnektoru üçün ünvan təyin edilməyib.",
            )
        if not self.field_map:
            raise AdapterNotConfiguredError(
                "adapter_no_field_map",
                f"The {self.name_en} connector has no field mapping, so nothing can be read.",
                f"{self.name_az} konnektoru üçün sahə uyğunlaşdırması yoxdur.",
            )

    # ── transport ───────────────────────────────────────────────────────────
    def endpoint_for(self, vendor: VendorRef, since: datetime | None) -> str:
        """The URL this pull calls. Public because the sync log records it as the source ref."""
        base = self.config.base_url or ""
        url = (
            base.replace(VENDOR_PLACEHOLDER, urllib.parse.quote(vendor.remote_key, safe=""))
            if VENDOR_PLACEHOLDER in base
            else _with_query(base, {"vendor": vendor.remote_key})
        )
        return _with_query(url, {"since": since.isoformat()}) if since else url

    def _fetch(self, vendor: VendorRef, since: datetime | None) -> tuple[bytes, str]:
        """Read the source. **The one method a mocked family replaces.**"""
        url = self.endpoint_for(vendor, since)
        headers = {
            "Accept": "text/csv" if self.payload_format == "csv" else "application/json",
            "User-Agent": "VendorIQ-Adapter/1.0",
            **auth_header(self.config.auth_type, self.config.username, self.config.secret),
        }
        try:
            response = request("GET", url, headers=headers)
        except TransportError as exc:
            raise AdapterUnreachableError(
                "source_unreachable",
                f"{self.name_en}: {exc.reason}.",
                f"{self.name_az}: mənbə ilə əlaqə qurulmadı ({exc.reason}).",
            ) from exc
        if response.status >= 400:
            # The status, never the body: a remote error page can echo the request headers.
            raise AdapterUnreachableError(
                "source_error_status",
                f"{self.name_en}: the source answered HTTP {response.status}.",
                f"{self.name_az}: mənbə HTTP {response.status} cavabı verdi.",
            )
        return response.body, url

    # ── the interface ───────────────────────────────────────────────────────
    def pull(self, vendor: VendorRef, since: datetime | None = None) -> PullResult:
        self.require_configuration()
        body, source_ref = self._fetch(vendor, since)
        payload = self._decode(body, source_ref)
        observations, warnings = observations_from(
            payload,
            self.field_map,
            source=self.source,
            source_ref=source_ref,
            observed_at=None,
        )
        return PullResult.of(observations, warnings + self._empty_warning(observations, vendor))

    def _decode(self, body: bytes, source_ref: str) -> object:
        try:
            return parse_csv(body) if self.payload_format == "csv" else parse_json(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise AdapterUnreachableError(
                "source_unparsable",
                f"{self.name_en}: the response from {source_ref} is not valid "
                f"{self.payload_format.upper()}.",
                f"{self.name_az}: {source_ref} ünvanından gələn cavab düzgün "
                f"{self.payload_format.upper()} deyil.",
            ) from exc

    def _empty_warning(
        self, observations: list[Observation], vendor: VendorRef
    ) -> list[ImportWarning]:
        """A reachable source that matched nothing is reported, not silently counted as zero."""
        if observations:
            return []
        return [
            ImportWarning(
                code="unknown_field_code",
                message_en=(
                    f"{self.name_en}: the source answered but none of the mapped paths were "
                    f"present for {vendor.legal_name}; nothing was written."
                ),
                message_az=(
                    f"{self.name_az}: mənbə cavab verdi, lakin {vendor.legal_name} üçün "
                    "uyğunlaşdırılmış sahələrdən heç biri tapılmadı; heç nə yazılmadı."
                ),
                severity="warning",
            )
        ]


class CsvAdapter(GenericRestAdapter):
    """The same connector reading ``text/csv`` — one header row, one row per vendor."""

    key: ClassVar[AdapterKey] = AdapterKey.CSV
    payload_format: ClassVar[Literal["json", "csv"]] = "csv"
    name_az: ClassVar[str] = "CSV ixracı"
    name_en: ClassVar[str] = "CSV export"
    description_az: ClassVar[str] = (
        "Bir başlıq sətri və təchizatçı başına bir sətir olan CSV ixracı; "
        "sütun adları sahə kodlarına uyğunlaşdırılır."
    )
    description_en: ClassVar[str] = (
        "A CSV export with one header row and one row per vendor; column names are mapped "
        "onto field codes."
    )


def _with_query(url: str, params: dict[str, str]) -> str:
    parsed = urllib.parse.urlparse(url)
    query = dict(urllib.parse.parse_qsl(parsed.query))
    query.update(params)
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))
