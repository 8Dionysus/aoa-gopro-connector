"""Allowlisted local HTTP reader for the OpenGoPro USB/Wi-Fi API."""

from __future__ import annotations

import ipaddress
import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from ..errors import ContractError, TransportError
from .base import ALLOWED_READ_PATHS


MAX_RESPONSE_BYTES = 2 * 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise TransportError("HTTP redirects are denied by the read contract")


def _validate_base_url(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "http":
        raise ContractError("camera base URL must use http")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ContractError("camera base URL cannot contain auth, query, or fragment")
    if parsed.path not in ("", "/"):
        raise ContractError("camera base URL cannot contain a path")
    if not parsed.hostname:
        raise ContractError("camera base URL has no hostname")
    hostname = parsed.hostname
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if not hostname.casefold().endswith(".local"):
            raise ContractError("camera hostname must be a local mDNS name")
    else:
        if not (address.is_private or address.is_link_local or address.is_loopback):
            raise ContractError("camera address must be private, link-local, or loopback")
    try:
        port_number = parsed.port
    except ValueError as exc:
        raise ContractError("camera base URL has an invalid port") from exc
    port = f":{port_number}" if port_number is not None else ""
    normalized_hostname = f"[{hostname}]" if ":" in hostname else hostname
    return f"http://{normalized_hostname}{port}"


class HTTPReadAdapter:
    def __init__(self, base_url: str, *, timeout_seconds: float = 5.0) -> None:
        if timeout_seconds <= 0 or timeout_seconds > 30:
            raise ContractError("timeout must be within (0, 30] seconds")
        self._base_url = _validate_base_url(base_url)
        self._timeout_seconds = timeout_seconds
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            _NoRedirect(),
        )

    def get_json(self, path: str) -> dict[str, Any]:
        if path not in ALLOWED_READ_PATHS:
            raise ContractError(f"route is not read-allowlisted: {path}")
        request = urllib.request.Request(
            f"{self._base_url}{path}",
            method="GET",
            headers={"Accept": "application/json"},
        )
        try:
            with self._opener.open(request, timeout=self._timeout_seconds) as response:
                payload = response.read(MAX_RESPONSE_BYTES + 1)
        except (urllib.error.URLError, TimeoutError, OSError, TransportError) as exc:
            raise TransportError(f"read endpoint failed: {path}") from exc
        if len(payload) > MAX_RESPONSE_BYTES:
            raise TransportError(f"read endpoint exceeded size bound: {path}")
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TransportError(f"read endpoint returned invalid JSON: {path}") from exc
        if not isinstance(value, dict):
            raise TransportError(f"read endpoint returned a non-object: {path}")
        return value
