"""The HTTP the integration layer is allowed to speak.

One module, two callers: the generic REST/CSV adapter (outbound GET) and webhook delivery
(outbound POST). It is built on ``urllib.request`` from the standard library rather than a
client package because ``apps/api`` has no HTTP client among its runtime dependencies, and
adding one is a contract change (``pyproject.toml`` is not this task's file). Nothing here
needs connection pooling: an adapter pull is one request on a schedule.

What this module exists to enforce, beyond "make a request":

* **Only http and https.** A configured ``file://`` or ``gopher://`` base URL would turn an
  admin-editable text field into a file read (spec §13).
* **A hard timeout and a hard read cap.** A source that never answers, or answers with a
  gigabyte, must not take the process with it.
* **No credential in an error.** Every failure is reported by status and reason; the
  ``Authorization`` header is built at the last moment and never formatted into a message.
"""

from __future__ import annotations

import base64
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

#: Largest response body read from a remote source. A vendor's ERP extract is kilobytes.
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
#: Connect + read timeout for one request, in seconds.
DEFAULT_TIMEOUT = 10.0

_ALLOWED_SCHEMES = frozenset({"http", "https"})


class TransportError(Exception):
    """The request did not produce a usable response. Never carries a credential."""

    def __init__(self, reason: str, status: int | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.status = status


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


def validate_url(url: str) -> str:
    """Refuse anything that is not an absolute http(s) URL, before a request is built."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise TransportError(f"unsupported URL scheme {parsed.scheme or '(none)'!r}")
    if not parsed.netloc:
        raise TransportError("URL has no host")
    return url


def auth_header(auth_type: str, username: str | None, secret: str | None) -> dict[str, str]:
    """The one place a stored credential becomes a header. Nothing here is ever logged."""
    if not secret or auth_type == "none":
        return {}
    if auth_type == "bearer":
        return {"Authorization": f"Bearer {secret}"}
    if auth_type == "api_key":
        return {"X-API-Key": secret}
    if auth_type == "basic":
        raw = f"{username or ''}:{secret}".encode()
        return {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}
    raise TransportError(f"unsupported auth type {auth_type!r}")


def request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Response:
    """One request, one response. A non-2xx status is returned, not raised.

    The caller decides what a 404 or a 500 means — an adapter treats it as "the source did
    not answer usably", a webhook delivery records it and retries — so this function only
    raises when there was no HTTP exchange at all.
    """
    validate_url(url)
    # The scheme is validated above, which is what makes this urlopen safe.
    prepared = urllib.request.Request(
        url,
        data=body,
        method=method.upper(),
        headers=headers or {},
    )
    try:
        with urllib.request.urlopen(prepared, timeout=timeout) as raw:
            payload = raw.read(MAX_RESPONSE_BYTES + 1)
            status = int(raw.status)
            received = {key.lower(): value for key, value in raw.headers.items()}
    except urllib.error.HTTPError as exc:
        # A 4xx/5xx is a real exchange: keep the status and whatever the body explained.
        payload = exc.read(MAX_RESPONSE_BYTES + 1) if exc.fp is not None else b""
        return Response(int(exc.code), payload[:MAX_RESPONSE_BYTES], {})
    except urllib.error.URLError as exc:
        raise TransportError(f"could not reach the host ({exc.reason})") from exc
    except TimeoutError as exc:
        raise TransportError("the source did not answer within the timeout") from exc
    except OSError as exc:  # connection reset, DNS failure surfacing as OSError
        raise TransportError("the connection failed") from exc

    if len(payload) > MAX_RESPONSE_BYTES:
        raise TransportError(f"response larger than {MAX_RESPONSE_BYTES} bytes")
    return Response(status, payload, received)
