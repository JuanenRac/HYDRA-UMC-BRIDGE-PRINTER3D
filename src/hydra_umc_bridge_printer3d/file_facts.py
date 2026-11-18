# =============================================================================
# HYDRA-UMC-BRIDGE-PRINTER3D - What the printer can say about a G-code file
# Copyright (C) 2026 JuanenRac (Electro Hobby 3D) <electrohobby3d@gmail.com>
# GPL-3.0-or-later - see LICENSE
# =============================================================================
"""The sha256 and the profile of a G-code file, for the command correlation.

Moonraker reports neither. The sha256 is therefore computed from the file itself,
downloaded from `/server/files/gcodes/<name>` with a ceiling on its size, and kept
by name and modification time so that a file is read once. The profile is the one
the slicer step wrote in the header of the file, as a comment line::

    ; hydra_profile: <id>

A file without that line has no profile (None), and a start that names a profile
is then refused by the correlation check.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request

from .moonraker import API_KEY_HEADER, _MAX_INFO_BYTES, _normalize_base_url, _open

PROFILE_COMMENT = re.compile(rb"^;\s*hydra_profile:[ \t]*([A-Za-z0-9._:-]{1,128})[ \t]*\r?$")
# the header of a G-code file is written before any move; only this many bytes of the start are searched
HEADER_BYTES = 8192
DEFAULT_MAX_BYTES = 256 * 1024 * 1024
_CHUNK = 64 * 1024


def profile_from_header(head: bytes) -> str | None:
    """The id of the first `; hydra_profile: <id>` comment line of the header, else None."""
    for line in head[:HEADER_BYTES].split(b"\n"):
        found = PROFILE_COMMENT.match(line)
        if found:
            return found.group(1).decode("ascii")
    return None


class MoonrakerFileFacts:
    """`FileFacts` callable: `facts(filename)` is `(sha256, profile_id)`, either None when it cannot be told."""

    def __init__(self, base_url: str, api_key: str | None = None, *, max_bytes: int = DEFAULT_MAX_BYTES, follow_redirects: bool = True, timeout_seconds: float = 10.0) -> None:
        self._base_url = base_url
        self._api_key = api_key
        self._max_bytes = max_bytes
        self._follow_redirects = follow_redirects
        self._timeout = timeout_seconds
        self._cache: dict[str, tuple[tuple[float, int], tuple[str | None, str | None]]] = {}
        self._lock = threading.Lock()

    def __call__(self, filename: str) -> tuple[str | None, str | None]:
        if self._max_bytes <= 0:
            return None, None
        base, _problem = _normalize_base_url(self._base_url)
        if base is None:
            return None, None
        stamp = self._stamp(base, filename)
        if stamp is None or stamp[1] > self._max_bytes:
            return None, None
        with self._lock:
            cached = self._cache.get(filename)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        facts = self._download(base, filename)
        if facts is not None:
            with self._lock:
                self._cache[filename] = (stamp, facts)
            return facts
        return None, None

    def _request(self, url: str) -> Request:
        return Request(url, headers={API_KEY_HEADER: self._api_key} if self._api_key else {})  # nosec B310: configured controller endpoint, restricted to HTTP(S)

    def _stamp(self, base: str, filename: str) -> tuple[float, int] | None:
        """(modification time, size) of the file as Moonraker reports them, or None."""
        try:
            with _open(self._request(f"{base}/server/files/metadata?{urlencode({'filename': filename})}"), self._timeout, self._follow_redirects) as response:
                body = response.read(_MAX_INFO_BYTES + 1)
            if len(body) > _MAX_INFO_BYTES:
                return None
            result = json.loads(body.decode("utf-8")).get("result")
            modified, size = result.get("modified"), result.get("size")
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, AttributeError, UnicodeDecodeError):
            return None
        if isinstance(modified, bool) or isinstance(size, bool) or not isinstance(modified, (int, float)) or not isinstance(size, int):
            return None
        return float(modified), size

    def _download(self, base: str, filename: str) -> tuple[str | None, str | None] | None:
        digest = hashlib.sha256()
        head = b""
        total = 0
        try:
            with _open(self._request(f"{base}/server/files/gcodes/{quote(filename, safe='/')}"), self._timeout, self._follow_redirects) as response:
                while True:
                    chunk = response.read(_CHUNK)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > self._max_bytes:
                        return None
                    if len(head) < HEADER_BYTES:
                        head += chunk[: HEADER_BYTES - len(head)]
                    digest.update(chunk)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError):
            return None
        return digest.hexdigest(), profile_from_header(head)
