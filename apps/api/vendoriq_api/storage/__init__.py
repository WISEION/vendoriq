"""Document storage: one interface, a ``local`` and an ``s3`` backend (ADR-002)."""

from __future__ import annotations

import re
import uuid
from functools import lru_cache

from ..config import get_settings
from .base import ObjectNotFoundError, SignedUrl, Storage, StorageError, StorageNotConfiguredError
from .local import LocalStorage
from .s3 import S3Storage

__all__ = [
    "LocalStorage",
    "ObjectNotFoundError",
    "S3Storage",
    "SignedUrl",
    "Storage",
    "StorageError",
    "StorageNotConfiguredError",
    "document_key",
    "get_storage",
]

#: Anything outside this set is replaced in a stored filename — the key ends up in a URL.
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
#: Runs of dots are collapsed so no segment can read as a path traversal.
_DOTS = re.compile(r"\.{2,}")


def document_key(vendor_id: uuid.UUID, code: str, filename: str) -> str:
    """``documents/<vendor>/<code>/<uuid>-<safe name>`` — collision-free and greppable."""
    safe = _DOTS.sub(".", _UNSAFE.sub("_", filename)).strip("._") or "document.pdf"
    return f"documents/{vendor_id}/{code}/{uuid.uuid4().hex}-{safe[:120]}"


@lru_cache
def get_storage() -> Storage:
    """The configured backend. Cached: both backends are cheap but stateless clients."""
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3Storage(
            bucket=settings.s3_bucket,
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            region=settings.s3_region,
            public_endpoint_url=settings.s3_public_endpoint_url,
        )
    return LocalStorage(
        settings.storage_local_dir,
        secret=settings.session_secret,
        url_prefix=f"{settings.api_prefix}/storage",
    )
