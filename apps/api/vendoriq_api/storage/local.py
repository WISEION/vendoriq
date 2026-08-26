"""Filesystem backend with signed-URL emulation (ADR-002).

S3 signs a URL with the bucket's credentials and the object store verifies it. Here the API
signs a token with ``SESSION_SECRET`` and verifies it on its own storage routes, so the URL
has the same two properties that matter: it names one object and it stops working.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from ..security.tokens import TokenError, sign, unsign
from .base import ObjectNotFoundError, SignedUrl, Storage


class LocalStorage(Storage):
    """Objects are files under ``STORAGE_LOCAL_DIR``; keys are relative paths."""

    backend = "local"

    def __init__(self, root: Path, *, secret: str, url_prefix: str) -> None:
        self._root = Path(root)
        self._secret = secret
        #: e.g. ``/api/storage`` — the routes in ``routers/storage.py``.
        self._url_prefix = url_prefix.rstrip("/")

    # ── key handling ─────────────────────────────────────────────────────────
    def _path(self, key: str) -> Path:
        # ``resolve`` plus a containment check: a key is user-influenced input and
        # ``documents/../../etc/passwd`` must not escape the storage root.
        candidate = (self._root / key).resolve()
        root = self._root.resolve()
        if root != candidate and root not in candidate.parents:
            raise ObjectNotFoundError(f"key escapes the storage root: {key!r}")
        return candidate

    # ── signing ──────────────────────────────────────────────────────────────
    def _token(self, key: str, action: str, ttl_seconds: int) -> str:
        return sign({"key": key, "act": action}, self._secret, ttl_seconds=ttl_seconds)

    def verify_token(self, token: str, key: str, action: str) -> bool:
        """Used by the storage routes; the object store's signature check, in-process."""
        try:
            payload = unsign(token, self._secret)
        except TokenError:
            return False
        return payload.get("key") == key and payload.get("act") == action

    # ── interface ────────────────────────────────────────────────────────────
    def upload_url(self, key: str, *, content_type: str, ttl_seconds: int) -> SignedUrl:
        token = self._token(key, "put", ttl_seconds)
        return SignedUrl(
            url=f"{self._url_prefix}/upload?key={key}&token={token}",
            method="PUT",
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            headers={"Content-Type": content_type},
        )

    def download_url(self, key: str, *, filename: str | None, ttl_seconds: int) -> SignedUrl:
        token = self._token(key, "get", ttl_seconds)
        url = f"{self._url_prefix}/download?key={key}&token={token}"
        if filename:
            url = f"{url}&filename={filename}"
        return SignedUrl(
            url=url,
            method="GET",
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            headers={},
        )

    def put(self, key: str, data: bytes, *, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise ObjectNotFoundError(key)
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except ObjectNotFoundError:
            return False

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except ObjectNotFoundError:
            return
