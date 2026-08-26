"""The storage interface both backends implement (ADR-002).

The API never learns which backend is in use: it asks for an upload target and a download
link and gets back URLs. With ``s3`` those are pre-signed S3 URLs; with ``local`` they are
routes on this process carrying an HMAC token that the same process verifies. The frontend
code path is identical, which is the point — MinIO cannot run on the build host.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


class StorageError(Exception):
    """Base of the storage failures the API turns into an error envelope."""


class StorageNotConfiguredError(StorageError):
    """The selected backend cannot run — missing credentials, missing ``boto3``."""


class ObjectNotFoundError(StorageError):
    """The key is not in the bucket / not on disk."""


@dataclass(frozen=True, slots=True)
class SignedUrl:
    """A URL that stops working. ``headers`` are what the client must send with it."""

    url: str
    method: str
    expires_at: datetime
    headers: dict[str, str]


class Storage(ABC):
    """Put bytes somewhere, get a link back, read them again."""

    #: ``local`` or ``s3`` — mirrored into ``GET /health`` so the dev banner can show it.
    backend: str

    @abstractmethod
    def upload_url(self, key: str, *, content_type: str, ttl_seconds: int) -> SignedUrl:
        """Where the browser PUTs the file."""

    @abstractmethod
    def download_url(self, key: str, *, filename: str | None, ttl_seconds: int) -> SignedUrl:
        """A short-lived link to fetch the file (spec §13: signed, expiring)."""

    @abstractmethod
    def put(self, key: str, data: bytes, *, content_type: str) -> None:
        """Write bytes directly — used by the importer and by the local upload route."""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Read bytes back. Raises :class:`ObjectNotFoundError`."""

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...
