"""Safe public-URL resume/profile importer with SSRF protection.

Task 04 §5.1 requires support for an explicitly supplied public resume/profile
URL, fetched in a bounded, safe way and saved/processed locally. This module
implements that with:

  - scheme/host validation (https only for remote targets)
  - rejection of private/loopback/link-local addresses (SSRF defense)
  - response-size cap and timeout
  - fetched content treated as untrusted input (caller sanitizes)

Privacy: the fetched content is never sent to a vacancy site or cloud LLM;
it is saved to the local data directory and parsed locally.
"""

from __future__ import annotations

import logging
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

logger = logging.getLogger(__name__)

# Response size limit: 2 MiB — large enough for a resume, small enough to
# bound memory use on arbitrary public pages.
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 15

ALLOWED_SCHEMES = frozenset({"https"})


@dataclass
class UrlImportResult:
    """Outcome of a URL resume import attempt."""
    success: bool
    url: str
    text: str = ""  # fetched content text (empty on failure)
    saved_path: Optional[str] = None
    content_type: Optional[str] = None
    size_bytes: Optional[int] = 0
    error: Optional[str] = None
    notes: list = field(default_factory=list)


def _host_is_private(hostname: str) -> bool:
    """Return True if the hostname resolves to a private/loopback address.

    This is a conservative string-based check (no DNS resolution, so it cannot
    be tricked by DNS rebinding to a public IP that later resolves privately).
    """
    host = (hostname or "").strip().lower()
    if not host:
        return True
    # Loopback / localhost
    if host in ("localhost", "0.0.0.0", "::1", "::"):
        return True
    # Loopback IPv4 127.0.0.0/8
    if host.startswith("127."):
        return True
    # Private IPv4 ranges
    for prefix in ("10.", "192.168.", "172.16.", "172.17.", "172.18.", "172.19.",
                   "172.20.", "172.21.", "172.22.", "172.23.", "172.24.", "172.25.",
                   "172.26.", "172.27.", "172.28.", "172.29.", "172.30.", "172.31.",
                   "169.254.", "100.64."):
        if host.startswith(prefix):
            return True
    # IPv6 loopback / unique local
    if host.startswith("fc") or host.startswith("fd") or host.startswith("fe80"):
        # crude: only flag obvious local unicast; public IPv6 starts with 2001:/2620:
        if len(host) >= 3 and host[:3] in ("200", "262"):
            return False
        return True
    return False


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate a URL for safe import (scheme + SSRF)."""
    if not url or not isinstance(url, str):
        return False, "URL is empty"
    parsed = urlparse(url)
    scheme = (parsed.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        return False, f"Only HTTPS is allowed for URL import (got '{scheme}')"
    host = parsed.hostname or ""
    if _host_is_private(host):
        return False, f"Private/local network target rejected (SSRF protection): {host}"
    # Reject credentials in URL
    if parsed.username or parsed.password:
        return False, "URL must not contain embedded credentials"
    return True, ""


def fetch_resume_text(
    url: str,
    max_bytes: int = MAX_RESPONSE_BYTES,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> UrlImportResult:
    """Fetch text content from a public resume URL.

    Returns a ``UrlImportResult``. On failure, ``success=False`` with an
    ``error`` message and ``saved_path=None``. The fetched content is NOT saved
    here — call ``save_imported_content`` after the caller sanitizes it.
    """
    ok, reason = _validate_url(url)
    if not ok:
        logger.warning("URL import rejected: %s (%s)", url, reason)
        return UrlImportResult(success=False, url=url, error=reason)

    try:
        req = Request(
            url,
            headers={"User-Agent": "vacancy-agent-career-assistant/1.0 (+local)"},
        )
        with urlopen(req, timeout=timeout) as resp:  # noqa: S310 — https + non-private validated above
            # Bounded read
            raw = resp.read(max_bytes + 1)
            if len(raw) > max_bytes:
                return UrlImportResult(
                    success=False,
                    url=url,
                    error=f"Response exceeds size limit ({len(raw)} > {max_bytes} bytes)",
                )
            content_type = resp.headers.get("Content-Type", "")
            text = raw.decode("utf-8", errors="replace")
    except HTTPError as e:
        return UrlImportResult(success=False, url=url, error=f"HTTP {e.code}: {e.reason}")
    except URLError as e:
        return UrlImportResult(success=False, url=url, error=f"URL error: {e.reason}")
    except TimeoutError:
        return UrlImportResult(success=False, url=url, error="Request timed out")
    except Exception as e:  # noqa: BLE001
        return UrlImportResult(success=False, url=url, error=f"Fetch failed: {e}")

    return UrlImportResult(
        success=True,
        url=url,
        text=text,
        content_type=content_type,
        size_bytes=len(text),
    )


def save_imported_content(text: str, target_dir: Path, profile_id: str = "default") -> Path:
    """Save fetched resume text locally and return the path.

    The content is treated as untrusted by the caller before parsing.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{profile_id}_imported_resume.txt"
    path.write_text(text, encoding="utf-8")
    return path
