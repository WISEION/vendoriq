"""The storage interface and its two backends (ADR-002)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from vendoriq_api.storage import ObjectNotFoundError, StorageNotConfiguredError, document_key
from vendoriq_api.storage.local import LocalStorage
from vendoriq_api.storage.s3 import BOTO3_AVAILABLE, S3Storage

SECRET = "storage-test-secret"


@pytest.fixture
def local(tmp_path: Path) -> LocalStorage:
    return LocalStorage(tmp_path, secret=SECRET, url_prefix="/api/storage")


def test_put_get_exists_delete(local: LocalStorage) -> None:
    local.put("documents/a/b.pdf", b"%PDF-1.4", content_type="application/pdf")
    assert local.exists("documents/a/b.pdf")
    assert local.get("documents/a/b.pdf") == b"%PDF-1.4"
    local.delete("documents/a/b.pdf")
    assert not local.exists("documents/a/b.pdf")


def test_reading_a_missing_object_raises(local: LocalStorage) -> None:
    with pytest.raises(ObjectNotFoundError):
        local.get("nothing/here.pdf")


def test_a_key_cannot_escape_the_storage_root(local: LocalStorage) -> None:
    """The key comes from user-influenced input; traversal must not reach the filesystem."""
    with pytest.raises(ObjectNotFoundError):
        local.get("../../etc/passwd")
    assert local.exists("../../etc/passwd") is False


def test_signed_urls_are_scoped_to_one_key_and_one_action(local: LocalStorage) -> None:
    """This is what makes the local backend equivalent to a pre-signed S3 URL."""
    upload = local.upload_url("documents/x.pdf", content_type="application/pdf", ttl_seconds=60)
    token = upload.url.split("token=")[1]
    assert local.verify_token(token, "documents/x.pdf", "put")
    # …not for another key,
    assert not local.verify_token(token, "documents/y.pdf", "put")
    # …and not for the other action.
    assert not local.verify_token(token, "documents/x.pdf", "get")


def test_a_signed_url_expires(local: LocalStorage) -> None:
    signed = local.download_url("documents/x.pdf", filename="x.pdf", ttl_seconds=1)
    token = signed.url.split("token=")[1].split("&")[0]
    assert local.verify_token(token, "documents/x.pdf", "get")
    time.sleep(1.1)
    assert not local.verify_token(token, "documents/x.pdf", "get")


def test_a_token_signed_with_another_secret_is_rejected(tmp_path: Path) -> None:
    mine = LocalStorage(tmp_path, secret="a", url_prefix="/api/storage")
    theirs = LocalStorage(tmp_path, secret="b", url_prefix="/api/storage")
    token = mine.upload_url("k.pdf", content_type="application/pdf", ttl_seconds=60).url.split(
        "token="
    )[1]
    assert not theirs.verify_token(token, "k.pdf", "put")


def test_the_upload_ticket_declares_the_method_and_content_type(local: LocalStorage) -> None:
    ticket = local.upload_url("k.pdf", content_type="application/pdf", ttl_seconds=60)
    assert ticket.method == "PUT"
    assert ticket.headers["Content-Type"] == "application/pdf"
    assert ticket.expires_at is not None


def test_document_keys_are_namespaced_and_sanitised() -> None:
    import uuid

    vendor = uuid.uuid4()
    key = document_key(vendor, "A-05", "vergi borcsuzluğu ../../hack.pdf")
    assert key.startswith(f"documents/{vendor}/A-05/")
    assert ".." not in key
    assert " " not in key


def test_two_uploads_of_one_filename_do_not_collide() -> None:
    import uuid

    vendor = uuid.uuid4()
    assert document_key(vendor, "A-01", "x.pdf") != document_key(vendor, "A-01", "x.pdf")


@pytest.mark.skipif(BOTO3_AVAILABLE, reason="boto3 is installed, so the stub path is unreachable")
def test_the_s3_backend_reports_that_it_is_not_configured() -> None:
    """ADR-005: boto3 is an optional extra. Without it, `s3` fails loudly, not obscurely."""
    with pytest.raises(StorageNotConfiguredError, match="boto3"):
        S3Storage(
            bucket="vendoriq",
            endpoint_url="http://localhost:9000",
            access_key="k",
            secret_key="s",
            region="us-east-1",
        )


def test_importing_the_s3_module_never_fails() -> None:
    """`STORAGE_BACKEND=local` must not pay for an S3 dependency it does not use."""
    from vendoriq_api.storage import s3

    assert s3.S3Storage is not None


@pytest.mark.skipif(not BOTO3_AVAILABLE, reason="boto3 not installed on this host")
def test_presigned_urls_are_minted_for_the_public_endpoint() -> None:
    """The URL a browser gets must carry a hostname the browser can resolve.

    Inside compose the API reaches MinIO as ``http://minio:9000``; a signature covers host
    and path, so a URL signed for that name and rewritten afterwards is just a well-formed
    403. Found live: the dev stack handed clients ``minio:9000`` and every upload died on
    the first PUT. The fix is a second signing client bound to ``S3_PUBLIC_ENDPOINT_URL``.
    """
    from vendoriq_api.storage.s3 import S3Storage

    storage = S3Storage(
        bucket="vendoriq",
        endpoint_url="http://minio:9000",
        public_endpoint_url="https://s3.vendoriq.example.az",
        access_key="k",
        secret_key="s",
        region="us-east-1",
    )
    up = storage.upload_url(
        "documents/x/A-01/f.pdf", content_type="application/pdf", ttl_seconds=60
    )
    down = storage.download_url("documents/x/A-01/f.pdf", filename="f.pdf", ttl_seconds=60)
    assert up.url.startswith("https://s3.vendoriq.example.az/")
    assert down.url.startswith("https://s3.vendoriq.example.az/")


@pytest.mark.skipif(not BOTO3_AVAILABLE, reason="boto3 not installed on this host")
def test_without_a_public_endpoint_the_internal_one_signs() -> None:
    """Native dev and a real AWS endpoint: one address serves both roles."""
    from vendoriq_api.storage.s3 import S3Storage

    storage = S3Storage(
        bucket="vendoriq",
        endpoint_url="http://localhost:9000",
        access_key="k",
        secret_key="s",
        region="us-east-1",
    )
    assert storage.upload_url("k", content_type="a/b", ttl_seconds=60).url.startswith(
        "http://localhost:9000/"
    )
