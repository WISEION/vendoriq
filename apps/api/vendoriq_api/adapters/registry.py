"""The government-registry check — a stub that refuses, deliberately (spec §6.4, brief §1.5).

Registry is trust rank 1: an observation carrying ``source = registry`` outranks the
vendor's own form, the officer's manual correction and every ERP. It is the source that
turns A.4 tax clearance and A.1 licence validity from "the vendor says" into "verified",
and A.4 is a **knock-out** criterion — a vendor that fails it is rejected regardless of its
score (brief §1.2).

Therefore this adapter has exactly one behaviour: it says it is not configured. There is no
sample response, no development shortcut and no "return the last known value" fallback,
because every one of those would put a fabricated verification at the top of the trust
order, where nothing else can correct it. When the State Tax Service e-services and the
construction licence register become reachable, ``pull`` is implemented here — as an HTTP
call like any other — and the refusal below goes away with it.
"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from ..models.enums import AdapterKey, ObservationSource
from .base import (
    AdapterConfig,
    AdapterNotConfiguredError,
    AdapterStatus,
    PullResult,
    SourceAdapter,
    VendorRef,
)

#: The two checks the umbrella key stands for (spec §6.4). Named so the screen can list what
#: is planned rather than a blank; neither is implemented, and neither pretends to be.
PLANNED_CHECKS: tuple[tuple[str, str, str], ...] = (
    ("registry_tax", "Vergi borcu arayışı (A.4)", "Tax clearance certificate (A.4)"),
    (
        "registry_licence",
        "Tikinti lisenziyası reyestri (A.1)",
        "Construction licence register (A.1)",
    ),
)


class RegistryAdapter(SourceAdapter):
    """Highest-trust source, lowest-risk implementation: it never returns a value."""

    key: ClassVar[AdapterKey] = AdapterKey.REGISTRY
    source: ClassVar[ObservationSource] = ObservationSource.REGISTRY
    default_status: ClassVar[AdapterStatus] = "planned"
    name_az: ClassVar[str] = "Dövlət reyestrləri"
    name_en: ClassVar[str] = "Government registries"
    description_az: ClassVar[str] = (
        "Vergi borcu (A.4) və lisenziya (A.1) yoxlamaları. Reyestr API-si hələ mövcud "
        "deyil: adapter «konfiqurasiya edilməyib» qaytarır və heç vaxt yoxlama uydurmur."
    )
    description_en: ClassVar[str] = (
        "Tax clearance (A.4) and licence (A.1) checks. No registry API exists yet: the "
        "adapter returns «not configured» and never fabricates a verification."
    )

    def __init__(self, config: AdapterConfig) -> None:
        super().__init__(config)

    def pull(self, vendor: VendorRef, since: datetime | None = None) -> PullResult:
        """Always refuses. The refusal *is* the implementation, not a missing one."""
        raise AdapterNotConfiguredError(
            "registry_not_configured",
            (
                "Registry checks are not configured: no government registry API is "
                "connected. Tax clearance and licence validity must be verified from the "
                "uploaded documents."
            ),
            (
                "Reyestr yoxlamaları konfiqurasiya edilməyib: dövlət reyestri API-si "
                "qoşulmayıb. Vergi borcu və lisenziya etibarlılığı yüklənmiş sənədlər "
                "əsasında yoxlanılmalıdır."
            ),
        )
