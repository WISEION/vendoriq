"""The local storage backend's object endpoints (ADR-002).

**These two routes are not in the contract**, and deliberately so. With
``STORAGE_BACKEND=s3`` the browser PUTs and GETs against MinIO and neither route is ever
called; with ``STORAGE_BACKEND=local`` there is no object store, so this process has to be
one. They are excluded from the schema because they are an implementation of the storage
backend, not part of the public API — the client only ever follows the URL that
``upload-init`` and the download ticket handed it.

Authorisation is the signed token, exactly as with a pre-signed S3 URL: the token names one
key and one action and stops working. No session is required, because the browser follows
these URLs the same way it would follow an S3 one.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from ..config import Settings, get_settings
from ..errors import ApiError
from ..storage import LocalStorage, ObjectNotFoundError, Storage, get_storage

router = APIRouter(include_in_schema=False)


def _local(storage: Storage) -> LocalStorage:
    if not isinstance(storage, LocalStorage):
        # With STORAGE_BACKEND=s3 the client never reaches here: the signed URL points at
        # the object store. Reaching it anyway means a stale URL from a previous config.
        raise ApiError(404, "not_found", "Local storage routes are inactive on this backend.")
    return storage


@router.put("/storage/upload")
async def upload_object(
    request: Request,
    key: str,
    token: str,
    settings: Settings = Depends(get_settings),
    storage: Storage = Depends(get_storage),
) -> Response:
    """Accept the bytes a signed upload ticket authorised."""
    backend = _local(storage)
    if not backend.verify_token(token, key, "put"):
        raise ApiError(403, "forbidden", "The upload token is invalid or has expired.")
    body = await request.body()
    if not body:
        raise ApiError(400, "bad_request", "Empty upload.")
    if len(body) > settings.upload_max_bytes:
        raise ApiError(
            413,
            "payload_too_large",
            f"The document exceeds the {settings.upload_max_bytes} byte limit.",
        )
    # Magic-number check: the content-type header is the client's claim, the first five
    # bytes are the file's. A vendor uploading a renamed .exe fails here, not at review.
    if not body.startswith(b"%PDF-"):
        raise ApiError(415, "unsupported_media_type", "Only PDF documents are accepted (spec §7).")
    backend.put(key, body, content_type="application/pdf")
    return Response(status_code=204)


@router.get("/storage/download")
def download_object(
    key: str,
    token: str,
    filename: str | None = None,
    storage: Storage = Depends(get_storage),
) -> Response:
    """Serve an object a signed download ticket authorised."""
    backend = _local(storage)
    if not backend.verify_token(token, key, "get"):
        raise ApiError(403, "forbidden", "The download link is invalid or has expired.")
    try:
        data = backend.get(key)
    except ObjectNotFoundError as exc:
        raise ApiError(404, "not_found", "No such object.") from exc
    disposition = f'attachment; filename="{filename}"' if filename else "attachment"
    return Response(
        content=data,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )
