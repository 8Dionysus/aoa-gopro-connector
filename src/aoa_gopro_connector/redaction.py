"""Fail-closed public-artifact safety checks."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Mapping, Sequence
from typing import Any

from .errors import PublicSafetyError


SENSITIVE_KEYS = {
    "serial",
    "serial_number",
    "hostname",
    "host_name",
    "ap_mac_addr",
    "mac",
    "mac_address",
    "ap_ssid",
    "ssid",
    "ip",
    "ip_address",
    "network_address",
    "credential",
    "credentials",
    "certificate",
    "private_key",
    "password",
    "token",
}

VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("mac address", re.compile(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b")),
    (
        "IPv4 address",
        re.compile(
            r"(?<![A-Za-z0-9.])"
            r"(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
            r"(?:25[0-5]|2[0-4]\d|1?\d?\d)"
            r"(?![A-Za-z0-9.])"
        ),
    ),
    (
        "mDNS hostname",
        re.compile(
            r"(?i)(?<![A-Za-z0-9_-])"
            r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
            r"local\.?(?![A-Za-z0-9_-])"
        ),
    ),
    ("GoPro-style stable hostname", re.compile(r"\bC\d{10,}\b")),
)

IPV6_CANDIDATE_PATTERN = re.compile(
    r"(?i)(?<![0-9a-f:])"
    r"\[?(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}"
    r"(?:%[0-9a-z_.~%-]+)?\]?"
    r"(?![0-9a-f:])"
)


def _contains_ipv6(value: str) -> bool:
    for match in IPV6_CANDIDATE_PATTERN.finditer(value):
        candidate = match.group(0).strip("[]").split("%", maxsplit=1)[0]
        try:
            ipaddress.IPv6Address(candidate)
        except ipaddress.AddressValueError:
            continue
        return True
    return False


def _is_media_filename_path(segments: tuple[str | int, ...]) -> bool:
    return (
        len(segments) >= 5
        and segments[-5] == "media"
        and isinstance(segments[-4], int)
        and segments[-3] == "fs"
        and isinstance(segments[-2], int)
        and segments[-1] == "n"
    )


def public_safety_violations(
    value: Any,
    *,
    path: str = "$",
    _segments: tuple[str | int, ...] = (),
) -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            item_segments = (*_segments, key_text)
            if key_text.casefold() in SENSITIVE_KEYS:
                violations.append(f"{path}.{key_text}: forbidden identity/secret key")
            if _is_media_filename_path(item_segments):
                violations.append(f"{path}.{key_text}: forbidden camera media filename")
            violations.extend(
                public_safety_violations(
                    item,
                    path=f"{path}.{key_text}",
                    _segments=item_segments,
                )
            )
        return violations
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, item in enumerate(value):
            violations.extend(
                public_safety_violations(
                    item,
                    path=f"{path}[{index}]",
                    _segments=(*_segments, index),
                )
            )
        return violations
    if isinstance(value, str):
        for label, pattern in VALUE_PATTERNS:
            if pattern.search(value):
                violations.append(f"{path}: contains {label}")
        if _contains_ipv6(value):
            violations.append(f"{path}: contains IPv6 address")
    return violations


def assert_public_safe(value: Any) -> None:
    violations = public_safety_violations(value)
    if violations:
        raise PublicSafetyError("; ".join(violations))
