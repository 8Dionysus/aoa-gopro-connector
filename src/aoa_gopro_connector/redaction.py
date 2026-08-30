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
    "passphrase",
    "token",
    "device_id",
    "device_identifier",
    "camera_id",
    "camera_identifier",
    "hardware_id",
    "hardware_identifier",
    "unique_id",
    "uuid",
    "guid",
    "imei",
    "authorization",
    "authorization_header",
    "auth",
    "api_key",
    "access_key",
    "secret",
    "client_id",
    "client_secret",
    "access_token",
    "refresh_token",
}
SENSITIVE_KEY_FORMS = {key.replace("_", "") for key in SENSITIVE_KEYS}
SENSITIVE_KEY_COMPONENTS = {
    "auth",
    "authorization",
    "certificate",
    "credential",
    "credentials",
    "guid",
    "imei",
    "mac",
    "password",
    "secret",
    "serial",
    "ssid",
    "token",
    "uuid",
}
SENSITIVE_KEY_COMPONENT_PAIRS = {
    ("access", "key"),
    ("account", "id"),
    ("api", "key"),
    ("camera", "id"),
    ("client", "id"),
    ("device", "id"),
    ("hardware", "id"),
    ("ip", "address"),
    ("network", "address"),
    ("private", "key"),
    ("unique", "id"),
    ("user", "id"),
    ("wifi", "name"),
}

VALUE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "mac address",
        re.compile(
            r"(?i)\b(?:"
            r"(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}|"
            r"(?:[0-9a-f]{4}\.){2}[0-9a-f]{4}|"
            r"[0-9a-f]{12}"
            r")\b"
        ),
    ),
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
        "private hostname",
        re.compile(
            r"(?i)(?<![A-Za-z0-9_-])"
            r"(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+"
            r"(?:corp|home|home\.arpa|internal|intranet|lan|local|localdomain)"
            r"\.?(?![A-Za-z0-9_-])"
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
MAX_PUBLIC_ARTIFACT_DEPTH = 64
MAX_PUBLIC_ARTIFACT_NODES = 50_000


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


def _string_safety_violations(value: str, *, path: str) -> list[str]:
    violations: list[str] = []
    for label, pattern in VALUE_PATTERNS:
        if pattern.search(value):
            violations.append(f"{path}: contains {label}")
    if _contains_ipv6(value):
        violations.append(f"{path}: contains IPv6 address")
    return violations


def _is_sensitive_key(value: str) -> bool:
    snake_case = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", value)
    normalized = re.sub(r"[^A-Za-z0-9]+", "_", snake_case).strip("_").casefold()
    components = tuple(part for part in normalized.split("_") if part)
    component_pairs = set(zip(components, components[1:]))
    return (
        normalized in SENSITIVE_KEYS
        or normalized.replace("_", "") in SENSITIVE_KEY_FORMS
        or any(part in SENSITIVE_KEY_COMPONENTS for part in components)
        or bool(component_pairs & SENSITIVE_KEY_COMPONENT_PAIRS)
    )


def public_safety_violations(
    value: Any,
    *,
    path: str = "$",
    _segments: tuple[str | int, ...] = (),
) -> list[str]:
    violations: list[str] = []
    stack: list[tuple[Any, str, tuple[str | int, ...], int]] = [
        (value, path, _segments, 0)
    ]
    visited = 0
    while stack:
        item_value, item_path, segments, depth = stack.pop()
        visited += 1
        if visited > MAX_PUBLIC_ARTIFACT_NODES:
            violations.append(f"{path}: exceeds public artifact node limit")
            break
        if depth > MAX_PUBLIC_ARTIFACT_DEPTH:
            violations.append(f"{item_path}: exceeds public artifact nesting limit")
            continue
        if isinstance(item_value, Mapping):
            for key, item in reversed(tuple(item_value.items())):
                key_text = str(key)
                child_path = f"{item_path}.{key_text}"
                item_segments = (*segments, key_text)
                if _is_sensitive_key(key_text):
                    violations.append(f"{child_path}: forbidden identity/secret key")
                violations.extend(
                    _string_safety_violations(key_text, path=f"{child_path} key")
                )
                if _is_media_filename_path(item_segments):
                    violations.append(f"{child_path}: forbidden camera media filename")
                stack.append((item, child_path, item_segments, depth + 1))
            continue
        if isinstance(item_value, Sequence) and not isinstance(
            item_value, (str, bytes, bytearray)
        ):
            for index in range(len(item_value) - 1, -1, -1):
                stack.append(
                    (
                        item_value[index],
                        f"{item_path}[{index}]",
                        (*segments, index),
                        depth + 1,
                    )
                )
            continue
        if isinstance(item_value, str):
            violations.extend(_string_safety_violations(item_value, path=item_path))
    return violations


def assert_public_safe(value: Any) -> None:
    violations = public_safety_violations(value)
    if violations:
        raise PublicSafetyError("; ".join(violations))
