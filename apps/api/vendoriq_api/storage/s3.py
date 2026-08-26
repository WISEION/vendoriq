"""S3 / MinIO backend (ADR-002).

``boto3`` is an optional dependency (``vendoriq-api[s3]``) and is not installed on the build
host, so importing this module must not fail — only *using* it without boto3 does, with
:class:`StorageNotConfiguredError`. That way ``STORAGE_BACKEND=s3`` produces one clear error
at the first upload instead of an ``ImportError`` at process start.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from .base import ObjectNotFoundError, SignedUrl, Storage, StorageNotConfiguredError

try:  # pragma: no cover - boto3 is absent on the build host (ADR-005)
    import boto3
    from botocore.exceptions import ClientError

    BOTO3_AVAILABLE = True
except ImportError:  # pragma: no cover - the build host's path
    boto3 = None
    ClientError = Exception
    BOTO3_AVAILABLE = False


class S3Storage(Storage):
    """Pre-signed PUT and GET against any S3 API."""

    backend = "s3"

    def __init__(
        self,
        *,
        bucket: str,
        endpoint_url: str | None,
        access_key: str | None,
        secret_key: str | None,
        region: str,
        public_endpoint_url: str | None = None,
    ) -> None:
        if not BOTO3_AVAILABLE:
            raise StorageNotConfiguredError(
                "STORAGE_BACKEND=s3 needs boto3. Install vendoriq-api[s3], or use "
                "STORAGE_BACKEND=local."
            )
        if not access_key or not secret_key:
            raise StorageNotConfiguredError(
                "STORAGE_BACKEND=s3 needs S3_ACCESS_KEY and S3_SECRET_KEY."
            )
        self._bucket = bucket

        def _client_for(endpoint: str | None) -> Any:
            return boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=access_key,
                aws_secret_access_key=secret_key,
                region_name=region,
            )

        self._client: Any = _client_for(endpoint_url)
        # Pre-signed URLs are minted against the address the *browser* will use. A signature
        # covers host and path, so signing against the internal service name and rewriting
        # the host afterwards would just be a well-formed 403 (found live: the compose stack
        # handed clients `http://minio:9000/...`, unreachable from outside the network).
        self._signing_client: Any = (
            _client_for(public_endpoint_url) if public_endpoint_url else self._client
        )

    def upload_url(self, key: str, *, content_type: str, ttl_seconds: int) -> SignedUrl:
        url = self._signing_client.generate_presigned_url(
            "put_object",
            Params={"Bucket": self._bucket, "Key": key, "ContentType": content_type},
            ExpiresIn=ttl_seconds,
        )
        return SignedUrl(
            url=url,
            method="PUT",
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            headers={"Content-Type": content_type},
        )

    def download_url(self, key: str, *, filename: str | None, ttl_seconds: int) -> SignedUrl:
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": key}
        if filename:
            params["ResponseContentDisposition"] = f'attachment; filename="{filename}"'
        url = self._signing_client.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=ttl_seconds
        )
        return SignedUrl(
            url=url,
            method="GET",
            expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
            headers={},
        )

    def put(self, key: str, data: bytes, *, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def get(self, key: str) -> bytes:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            raise ObjectNotFoundError(key) from exc
        body: bytes = response["Body"].read()
        return body

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except ClientError:
            return False
        return True

    def delete(self, key: str) -> None:
        self._client.delete_object(Bucket=self._bucket, Key=key)
