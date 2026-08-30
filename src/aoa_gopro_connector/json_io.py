"""Strict JSON helpers for connector-owned packets and wire payloads."""

from __future__ import annotations

import json
import math
from typing import Any, NoReturn


MAX_JSON_INTEGER_DIGITS = 256


def _contains_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


def _has_surrogate_string(value: Any) -> bool:
    stack = [value]
    visited_containers: set[int] = set()
    while stack:
        item = stack.pop()
        if isinstance(item, str):
            if _contains_surrogate(item):
                return True
        elif isinstance(item, dict):
            identity = id(item)
            if identity in visited_containers:
                continue
            visited_containers.add(identity)
            stack.extend(item.keys())
            stack.extend(item.values())
        elif isinstance(item, (list, tuple)):
            identity = id(item)
            if identity in visited_containers:
                continue
            visited_containers.add(identity)
            stack.extend(item)
    return False


def _reject_nonstandard_constant(value: str) -> NoReturn:
    raise json.JSONDecodeError(
        f"non-standard JSON numeric constant {value!r}",
        value,
        0,
    )


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise json.JSONDecodeError(
            f"JSON number is outside the finite float range: {value!r}",
            value,
            0,
        )
    return parsed


def _parse_bounded_int(value: str) -> int:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) > MAX_JSON_INTEGER_DIGITS:
        raise json.JSONDecodeError(
            f"JSON integer exceeds {MAX_JSON_INTEGER_DIGITS}-digit limit",
            value,
            0,
        )
    try:
        return int(value)
    except ValueError as exc:
        raise json.JSONDecodeError("invalid JSON integer", value, 0) from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise json.JSONDecodeError(f"duplicate JSON object key {key!r}", key, 0)
        result[key] = value
    return result


def strict_json_loads(value: str | bytes | bytearray) -> Any:
    """Decode RFC-compliant JSON without Python's NaN/Infinity extensions."""

    try:
        decoded = json.loads(
            value,
            parse_constant=_reject_nonstandard_constant,
            parse_float=_parse_finite_float,
            parse_int=_parse_bounded_int,
            object_pairs_hook=_unique_object,
        )
    except RecursionError as exc:
        raise json.JSONDecodeError("JSON nesting exceeds decoder limit", "", 0) from exc
    if _has_surrogate_string(decoded):
        raise json.JSONDecodeError(
            "JSON string contains a lone surrogate code point",
            "",
            0,
        )
    return decoded


def strict_json_dumps(value: Any, **kwargs: Any) -> str:
    """Encode JSON while refusing non-finite numeric values."""

    if _has_surrogate_string(value):
        raise ValueError("JSON string contains a lone surrogate code point")
    try:
        return json.dumps(value, allow_nan=False, **kwargs)
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds encoder limit") from exc
