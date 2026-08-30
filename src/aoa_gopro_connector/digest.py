"""Canonical content digests for public connector packets."""

from __future__ import annotations

import hashlib
from typing import Any, Mapping

from .errors import ContractError
from .json_io import strict_json_dumps


ZERO_DIGEST = "sha256:" + "0" * 64


def canonical_bytes(value: Any) -> bytes:
    try:
        return strict_json_dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ContractError("value cannot be canonically encoded as UTF-8 JSON") from exc


def canonical_digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_bytes(value)).hexdigest()


def attach_digest(payload: Mapping[str, Any], field: str) -> dict[str, Any]:
    result = dict(payload)
    result[field] = ZERO_DIGEST
    result[field] = canonical_digest(result)
    return result


def verify_digest(payload: Mapping[str, Any], field: str) -> None:
    actual = payload.get(field)
    if not isinstance(actual, str):
        raise ContractError(f"packet is missing string digest field {field!r}")
    expected = canonical_digest({**payload, field: ZERO_DIGEST})
    if actual != expected:
        raise ContractError(
            f"digest mismatch for {field}: expected {expected}, got {actual}"
        )
