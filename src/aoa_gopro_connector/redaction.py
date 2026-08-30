"""Fail-closed public-artifact safety checks."""

from __future__ import annotations

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
    ("GoPro-style stable hostname", re.compile(r"\bC\d{10,}\b")),
)


def public_safety_violations(value: Any, *, path: str = "$") -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key)
            if key_text.casefold() in SENSITIVE_KEYS:
                violations.append(f"{path}.{key_text}: forbidden identity/secret key")
            violations.extend(
                public_safety_violations(item, path=f"{path}.{key_text}")
            )
        return violations
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        for index, item in enumerate(value):
            violations.extend(public_safety_violations(item, path=f"{path}[{index}]"))
        return violations
    if isinstance(value, str):
        for label, pattern in VALUE_PATTERNS:
            if pattern.search(value):
                violations.append(f"{path}: contains {label}")
    return violations


def assert_public_safe(value: Any) -> None:
    violations = public_safety_violations(value)
    if violations:
        raise PublicSafetyError("; ".join(violations))
