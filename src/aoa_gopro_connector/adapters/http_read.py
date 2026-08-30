"""Allowlisted local HTTP reader for the OpenGoPro USB/Wi-Fi API."""

from __future__ import annotations

import http.client
import ipaddress
import math
import re
import socket
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from ..errors import ContractError, TransportError
from ..json_io import strict_json_loads
from .base import ALLOWED_READ_PATHS


MAX_RESPONSE_BYTES = 2 * 1024 * 1024
ALLOWED_LOCAL_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in (
        "10.0.0.0/8",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
    )
)
LOCAL_MDNS_HOST_PATTERN = re.compile(
    r"(?i)^(?=.{1,253}\.?$)"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+local\.?$"
)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        raise TransportError("HTTP redirects are denied by the read contract")


def _is_allowed_local_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", maxsplit=1)[0])
    except ValueError:
        return False
    return any(address in network for network in ALLOWED_LOCAL_NETWORKS)


def _validate_mdns_resolution(hostname: str, port: int) -> None:
    try:
        results = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ContractError("camera mDNS hostname could not be resolved") from exc
    addresses = {result[4][0] for result in results if result[4]}
    if not addresses:
        raise ContractError("camera mDNS hostname resolved to no addresses")
    if any(not _is_allowed_local_address(address) for address in addresses):
        raise ContractError("camera mDNS hostname resolved outside local address space")


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
        port_number = parsed.port
    except ValueError as exc:
        raise ContractError("camera base URL has an invalid port") from exc
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if not LOCAL_MDNS_HOST_PATTERN.fullmatch(hostname):
            raise ContractError("camera hostname must be a valid local mDNS name")
        _validate_mdns_resolution(hostname, 80 if port_number is None else port_number)
    else:
        if not _is_allowed_local_address(str(address)):
            raise ContractError("camera address must be private, link-local, or loopback")
    port = f":{port_number}" if port_number is not None else ""
    normalized_hostname = f"[{hostname}]" if ":" in hostname else hostname
    return f"http://{normalized_hostname}{port}"


class HTTPReadAdapter:
    def __init__(self, base_url: str, *, timeout_seconds: float = 5.0) -> None:
        if (
            not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
            or timeout_seconds > 30
        ):
            raise ContractError("timeout must be finite and within (0, 30] seconds")
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
        except (
            urllib.error.URLError,
            http.client.InvalidURL,
            TimeoutError,
            OSError,
            TransportError,
        ) as exc:
            raise TransportError(f"read endpoint failed: {path}") from exc
        if len(payload) > MAX_RESPONSE_BYTES:
            raise TransportError(f"read endpoint exceeded size bound: {path}")
        try:
            value = strict_json_loads(payload)
        except (UnicodeDecodeError, ValueError) as exc:
            raise TransportError(f"read endpoint returned invalid JSON: {path}") from exc
        if not isinstance(value, dict):
            raise TransportError(f"read endpoint returned a non-object: {path}")
        return value
