"""The adapter interface — the one abstraction the integration layer is built to outlive.

Brief §5 fixes the shape: ``pull(vendor, since) -> Observation[]``. Every source of vendor
data implements it — the working REST/CSV connector, the mocked ERP families, the registry
stub and the Excel importer alike — so the register does not know, and must not care, where
a number came from beyond the ``source`` recorded on the observation (ADR-004, spec §6.6).

Three rules hold for every implementation and are the reason this file is small:

1. **An adapter never invents a value.** If it cannot reach its source, cannot authenticate
   or was never configured, it raises :class:`AdapterError`. It does not return a plausible
   number, and it does not return an empty list pretending the source said nothing.
2. **An adapter never writes.** It returns observations; ``services.adapters`` decides what
   to persist and records the :class:`~vendoriq_api.models.SyncLog` row. That split is what
   lets the Excel importer show a preview without touching the database.
3. **An adapter never logs a credential.** Configuration carries a secret; the value is
   read once when the request is built and never reaches a log line, a warning or an error
   message.

``pull`` returns a :class:`PullResult` rather than a bare ``list``. It *is* the list — it
iterates as ``Observation[]`` and answers ``len()`` — and it additionally carries the
anomalies the source reported, which a bare list has no room for and which the officer has
to see (spec §6.1). That is the single deliberate widening of the brief's signature.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, ClassVar, Literal

from vendoriq_excel_import import ImportWarning

from ..models.enums import AdapterKey, ObservationSource

#: Contract ``Adapter.status``.
AdapterStatus = Literal["active", "planned", "needs_configuration"]

#: Contract ``AdapterConfig.auth_type``.
AuthType = Literal["none", "basic", "bearer", "api_key"]


@dataclass(frozen=True, slots=True)
class VendorRef:
    """What an adapter is allowed to know about the vendor it is pulling for.

    Deliberately not the ORM ``Vendor``: an adapter that could reach the session could
    write, and rule 2 above would be a convention rather than a fact. ``external_ref`` is
    the cross-system key of brief §2 — the id this vendor carries in the remote system.
    """

    id: uuid.UUID
    legal_name: str
    voen: str | None = None
    external_ref: str | None = None

    @property
    def remote_key(self) -> str:
        """What the remote system is asked about: its own id if we know it, else the VÖEN."""
        return self.external_ref or self.voen or str(self.id)


@dataclass(frozen=True, slots=True)
class Observation:
    """One value one source reported about one field, ready to be appended (ADR-004).

    ``source_ref`` is mandatory in spirit and in practice: an observation whose origin
    cannot be named is not evidence. It holds the request URL, the fixture name or the
    workbook file — whatever a human would need to go and look at the same thing again.
    """

    field_code: str
    value: Any
    source: ObservationSource
    source_ref: str
    unit: str | None = None
    observed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class PullResult:
    """``Observation[]`` plus the anomalies the source reported.

    Iterates and measures as the list the brief's signature names, so a caller that only
    wants the observations writes ``for observation in adapter.pull(vendor)``.
    """

    observations: tuple[Observation, ...] = ()
    warnings: tuple[ImportWarning, ...] = ()

    def __iter__(self) -> Iterator[Observation]:
        return iter(self.observations)

    def __len__(self) -> int:
        return len(self.observations)

    def __bool__(self) -> bool:
        return bool(self.observations)

    @classmethod
    def of(
        cls,
        observations: Sequence[Observation],
        warnings: Sequence[ImportWarning] = (),
    ) -> PullResult:
        return cls(tuple(observations), tuple(warnings))


class AdapterError(Exception):
    """The pull did not happen. Carries a bilingual reason for the sync log.

    Every failure mode is this one exception with a different ``code``, because the caller
    treats them identically: record what went wrong, write nothing, tell the officer.
    """

    #: HTTP status the router maps this to. 409 is "the adapter is not configured";
    #: a reachable-but-broken source is a completed run with ``result = failed``.
    http_status: ClassVar[int] = 502

    def __init__(self, code: str, message_en: str, message_az: str) -> None:
        super().__init__(message_en)
        self.code = code
        self.message_en = message_en
        self.message_az = message_az

    def as_warning(self, field_code: str | None = None) -> ImportWarning:
        return ImportWarning(
            code=self.code,
            message_en=self.message_en,
            message_az=self.message_az,
            severity="error",
            field_code=field_code,
        )


class AdapterNotConfiguredError(AdapterError):
    """No connection details for this adapter and vendor — contract 409.

    The registry adapter raises this unconditionally (brief §2, spec §6.4): until a real
    government API exists, "not configured" is the only true answer a registry check can
    give. A stub that returned a tax-clearance pass would be the most dangerous line of
    code in the system, because A.4 is a knock-out criterion.
    """

    http_status: ClassVar[int] = 409


class AdapterUnreachableError(AdapterError):
    """The source was configured but did not answer, or answered unusably."""


@dataclass(frozen=True, slots=True)
class AdapterConfig:
    """Per-vendor connection details (contract ``AdapterConfig``).

    ``secret`` is the live credential and is never serialised back to a client — the
    router sends :func:`mask_secret` instead. It is not in ``__repr__``-safe territory
    either, which is why the dataclass sets ``repr=False`` on it.
    """

    adapter: AdapterKey
    vendor_id: uuid.UUID | None = None
    is_enabled: bool = False
    base_url: str | None = None
    auth_type: AuthType = "none"
    username: str | None = None
    secret: str | None = field(default=None, repr=False)
    #: Remote path (``financials.turnover_avg``, or a CSV column) → VendorIQ field code.
    field_map: Mapping[str, str] = field(default_factory=dict)
    schedule_cron: str | None = None

    def with_secret(self, secret: str | None) -> AdapterConfig:
        return AdapterConfig(
            adapter=self.adapter,
            vendor_id=self.vendor_id,
            is_enabled=self.is_enabled,
            base_url=self.base_url,
            auth_type=self.auth_type,
            username=self.username,
            secret=secret,
            field_map=dict(self.field_map),
            schedule_cron=self.schedule_cron,
        )


class SourceAdapter(ABC):
    """One data source. Subclasses differ only in how they fetch (brief §2, spec §6).

    The four ERP families and the generic connector share every line of mapping and
    normalisation; ``_fetch`` is the only method a mocked adapter overrides. Swapping a
    fixture for a live call later is therefore a change inside one class, which is exactly
    what "mocked, same interface" has to mean to be worth anything.
    """

    #: Contract ``AdapterKey``.
    key: ClassVar[AdapterKey]
    #: Provenance stamped on every observation this adapter produces (spec §6.6).
    source: ClassVar[ObservationSource]
    #: What the data-sources screen shows when the adapter has no configuration yet.
    default_status: ClassVar[AdapterStatus] = "needs_configuration"
    name_az: ClassVar[str]
    name_en: ClassVar[str]
    description_az: ClassVar[str]
    description_en: ClassVar[str]

    def __init__(self, config: AdapterConfig) -> None:
        self.config = config

    @abstractmethod
    def pull(self, vendor: VendorRef, since: datetime | None = None) -> PullResult:
        """Read the source and return what it says about ``vendor``.

        ``since`` asks the source for changes after that instant; a source that cannot
        filter ignores it and returns its current state, which is still correct because
        observations are append-only.

        Raises :class:`AdapterError` when the source cannot be read. It never returns a
        value it did not receive.
        """


def mask_secret(secret: str | None) -> str | None:
    """What a configured credential looks like on the wire (contract ``secret_masked``).

    A fixed-length mask, never a prefix of the real value: showing "the first four
    characters, so you recognise it" is showing four characters of a credential.
    """
    return "••••••••" if secret else None


#: The exact string a client may send back in ``secret`` to mean "leave it alone".
MASKED_SENTINEL = "••••••••"
