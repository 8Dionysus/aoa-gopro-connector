"""Load and validate repository-owned JSON packet schemas."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .errors import ContractError
from .json_io import strict_json_loads


SCHEMA_NAMES = (
    "camera_state",
    "capability_profile",
    "operation_plan",
    "operation_receipt",
    "event",
    "media_manifest",
)


def schema_root() -> Path:
    configured = os.environ.get("AOA_GOPRO_SCHEMA_ROOT")
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend(
        [
            Path(__file__).resolve().parents[2] / "connector" / "schemas",
            Path(sys.prefix) / "share" / "aoa-gopro-connector" / "schemas",
        ]
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise ContractError("aoa-gopro schema root is unavailable")


def schema_path(name: str) -> Path:
    normalized = name.removesuffix(".schema.json")
    if normalized not in SCHEMA_NAMES:
        raise ContractError(f"unknown schema {name!r}")
    return schema_root() / f"{normalized}.schema.json"


def load_schema(name: str) -> dict[str, Any]:
    import json

    path = schema_path(name)
    try:
        value = strict_json_loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"invalid schema file {path.name}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"schema {path.name} is not an object")
    Draft202012Validator.check_schema(value)
    return value


def validate_document(name: str, document: Any) -> None:
    validator = Draft202012Validator(
        load_schema(name),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "$"
        raise ContractError(f"{name} validation failed at {location}: {first.message}")
