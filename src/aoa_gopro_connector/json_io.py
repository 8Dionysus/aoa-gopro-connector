"""Strict JSON helpers for connector-owned packets and wire payloads."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import math
from typing import Any, NoReturn


MAX_JSON_INTEGER_DIGITS = 256
MAX_JSON_DECIMAL_DIGITS = 256
MAX_JSON_ABS_EXPONENT = 10_000


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


def _parse_finite_decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise json.JSONDecodeError("invalid JSON decimal", value, 0) from exc
    if not parsed.is_finite():
        raise json.JSONDecodeError(
            f"JSON number is not finite: {value!r}",
            value,
            0,
        )
    decimal_tuple = parsed.as_tuple()
    exponent = int(decimal_tuple.exponent)
    adjusted = parsed.adjusted() if not parsed.is_zero() else 0
    if len(decimal_tuple.digits) > MAX_JSON_DECIMAL_DIGITS:
        raise json.JSONDecodeError(
            f"JSON decimal exceeds {MAX_JSON_DECIMAL_DIGITS}-digit limit",
            value,
            0,
        )
    if (
        abs(exponent) > MAX_JSON_ABS_EXPONENT
        or abs(adjusted) > MAX_JSON_ABS_EXPONENT
    ):
        raise json.JSONDecodeError(
            "JSON decimal exponent exceeds "
            f"+/-{MAX_JSON_ABS_EXPONENT} limit",
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


def _decimal_json_token(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("Out of range float values are not JSON compliant")
    decimal_tuple = value.as_tuple()
    digits = list(decimal_tuple.digits)
    exponent = int(decimal_tuple.exponent)
    adjusted = value.adjusted() if not value.is_zero() else 0
    if len(digits) > MAX_JSON_DECIMAL_DIGITS:
        raise ValueError(
            f"JSON decimal exceeds {MAX_JSON_DECIMAL_DIGITS}-digit limit"
        )
    if (
        abs(exponent) > MAX_JSON_ABS_EXPONENT
        or abs(adjusted) > MAX_JSON_ABS_EXPONENT
    ):
        raise ValueError(
            "JSON decimal exponent exceeds "
            f"+/-{MAX_JSON_ABS_EXPONENT} limit"
        )
    if value.is_zero():
        return "0"

    while len(digits) > 1 and digits[-1] == 0:
        digits.pop()
        exponent += 1
    digit_text = "".join(str(digit) for digit in digits)
    adjusted = len(digits) + exponent - 1
    if -6 <= adjusted < 21:
        if exponent >= 0:
            body = digit_text + "0" * exponent
        else:
            point = len(digits) + exponent
            if point > 0:
                body = f"{digit_text[:point]}.{digit_text[point:]}"
            else:
                body = "0." + "0" * (-point) + digit_text
    else:
        fraction = f".{digit_text[1:]}" if len(digit_text) > 1 else ""
        body = f"{digit_text[0]}{fraction}e{adjusted}"
    return ("-" if decimal_tuple.sign else "") + body


def _number_json_token(value: int | float | Decimal) -> str:
    if isinstance(value, int):
        text = str(value)
        digits = text[1:] if text.startswith("-") else text
        if len(digits) > MAX_JSON_INTEGER_DIGITS:
            raise ValueError(
                f"JSON integer exceeds {MAX_JSON_INTEGER_DIGITS}-digit limit"
            )
        return text
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Out of range float values are not JSON compliant")
        value = Decimal(str(value))
    return _decimal_json_token(value)


def _encode_json(
    value: Any,
    *,
    ensure_ascii: bool,
    sort_keys: bool,
    indent: str | None,
    item_separator: str,
    key_separator: str,
) -> str:
    active_containers: set[int] = set()

    def encode(item: Any, level: int) -> str:
        if item is None:
            return "null"
        if item is True:
            return "true"
        if item is False:
            return "false"
        if isinstance(item, str):
            return json.dumps(item, ensure_ascii=ensure_ascii)
        if isinstance(item, (int, float, Decimal)):
            return _number_json_token(item)
        if isinstance(item, (list, tuple)):
            identity = id(item)
            if identity in active_containers:
                raise ValueError("Circular reference detected")
            active_containers.add(identity)
            try:
                encoded = [encode(child, level + 1) for child in item]
            finally:
                active_containers.remove(identity)
            if not encoded:
                return "[]"
            if indent is None:
                return "[" + item_separator.join(encoded) + "]"
            child_prefix = indent * (level + 1)
            closing_prefix = indent * level
            return (
                "[\n"
                + child_prefix
                + (item_separator + "\n" + child_prefix).join(encoded)
                + "\n"
                + closing_prefix
                + "]"
            )
        if isinstance(item, dict):
            identity = id(item)
            if identity in active_containers:
                raise ValueError("Circular reference detected")
            active_containers.add(identity)
            try:
                pairs = list(item.items())
                if any(not isinstance(key, str) for key, _ in pairs):
                    raise TypeError("JSON object keys must be strings")
                if sort_keys:
                    pairs.sort(key=lambda pair: pair[0])
                encoded = [
                    json.dumps(key, ensure_ascii=ensure_ascii)
                    + key_separator
                    + encode(child, level + 1)
                    for key, child in pairs
                ]
            finally:
                active_containers.remove(identity)
            if not encoded:
                return "{}"
            if indent is None:
                return "{" + item_separator.join(encoded) + "}"
            child_prefix = indent * (level + 1)
            closing_prefix = indent * level
            return (
                "{\n"
                + child_prefix
                + (item_separator + "\n" + child_prefix).join(encoded)
                + "\n"
                + closing_prefix
                + "}"
            )
        raise TypeError(
            f"Object of type {type(item).__name__} is not JSON serializable"
        )

    return encode(value, 0)


def strict_json_loads(value: str | bytes | bytearray) -> Any:
    """Decode strict JSON while preserving decimal values losslessly."""

    try:
        decoded = json.loads(
            value,
            parse_constant=_reject_nonstandard_constant,
            parse_float=_parse_finite_decimal,
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
    """Encode strict JSON with one lossless canonical numeric representation."""

    if _has_surrogate_string(value):
        raise ValueError("JSON string contains a lone surrogate code point")
    ensure_ascii = bool(kwargs.pop("ensure_ascii", True))
    sort_keys = bool(kwargs.pop("sort_keys", False))
    indent_value = kwargs.pop("indent", None)
    separators = kwargs.pop("separators", None)
    if kwargs:
        names = ", ".join(sorted(kwargs))
        raise TypeError(f"unsupported strict JSON encoder options: {names}")
    if indent_value is None:
        indent = None
    elif isinstance(indent_value, int):
        indent = " " * max(indent_value, 0)
    elif isinstance(indent_value, str):
        indent = indent_value
    else:
        raise TypeError("indent must be None, an integer, or a string")
    if separators is None:
        item_separator = ", " if indent is None else ","
        key_separator = ": "
    else:
        if (
            not isinstance(separators, (list, tuple))
            or len(separators) != 2
            or any(not isinstance(item, str) for item in separators)
        ):
            raise TypeError("separators must contain two strings")
        item_separator, key_separator = separators
    try:
        return _encode_json(
            value,
            ensure_ascii=ensure_ascii,
            sort_keys=sort_keys,
            indent=indent,
            item_separator=item_separator,
            key_separator=key_separator,
        )
    except RecursionError as exc:
        raise ValueError("JSON nesting exceeds encoder limit") from exc
