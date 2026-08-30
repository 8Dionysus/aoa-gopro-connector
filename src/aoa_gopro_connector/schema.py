"""Load and validate repository-owned JSON packet schemas."""

from __future__ import annotations

from datetime import datetime
import os
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from jsonschema.exceptions import SchemaError

from .digest import verify_digest
from .errors import ContractError
from .json_io import strict_json_loads
from .models import canonical_profile_id
from .redaction import assert_public_safe


SCHEMA_NAMES = (
    "camera_state",
    "capability_profile",
    "operation_plan",
    "operation_receipt",
    "event",
    "media_manifest",
)
PACKET_DIGEST_FIELDS = {
    "capability_profile": "profile_digest",
    "operation_plan": "plan_digest",
    "operation_receipt": "receipt_digest",
    "event": "event_digest",
    "media_manifest": "manifest_digest",
}


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
    try:
        Draft202012Validator.check_schema(value)
    except SchemaError as exc:
        raise ContractError(f"invalid schema definition {path.name}") from exc
    return value


def _rfc3339_datetime(value: str, *, schema_name: str, field: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ContractError(
            f"{schema_name} validation failed at {field}: invalid date-time"
        ) from exc
    if parsed.tzinfo is None:
        raise ContractError(
            f"{schema_name} validation failed at {field}: timezone is required"
        )
    return parsed


def _validate_operation_receipt_timeline(document: dict[str, Any]) -> None:
    started_at = _rfc3339_datetime(
        document["started_at"],
        schema_name="operation_receipt",
        field="started_at",
    )
    finished_at = _rfc3339_datetime(
        document["finished_at"],
        schema_name="operation_receipt",
        field="finished_at",
    )
    if finished_at < started_at:
        raise ContractError(
            "operation_receipt validation failed at finished_at: "
            "must not precede started_at"
        )
    for index, step in enumerate(document["steps"]):
        observed_at = _rfc3339_datetime(
            step["observed_at"],
            schema_name="operation_receipt",
            field=f"steps.{index}.observed_at",
        )
        if observed_at < started_at or observed_at > finished_at:
            raise ContractError(
                f"operation_receipt validation failed at steps.{index}.observed_at: "
                "must fall within started_at and finished_at"
            )


def _validate_event_freshness(document: dict[str, Any]) -> None:
    freshness = document["freshness"]
    observed_at = _rfc3339_datetime(
        freshness["observed_at"],
        schema_name="event",
        field="freshness.observed_at",
    )
    expires_value = freshness["expires_at"]
    if expires_value is None:
        return
    expires_at = _rfc3339_datetime(
        expires_value,
        schema_name="event",
        field="freshness.expires_at",
    )
    if expires_at < observed_at:
        raise ContractError(
            "event validation failed at freshness.expires_at: "
            "must not precede freshness.observed_at"
        )


def _validate_capability_profile_identity(document: dict[str, Any]) -> None:
    camera = document["camera"]
    expected = canonical_profile_id(
        model_name=camera["model_name"],
        firmware_posture=camera["firmware_posture"],
        firmware_release_version=camera["firmware_release_version"],
        topology=document["transport"]["topology"],
    )
    if document["profile_id"] != expected:
        raise ContractError(
            "capability_profile validation failed at profile_id: "
            f"expected canonical value {expected!r}"
        )


def validate_document(name: str, document: Any) -> None:
    normalized_name = name.removesuffix(".schema.json")
    validator = Draft202012Validator(
        load_schema(name),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(document), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "$"
        raise ContractError(f"{name} validation failed at {location}: {first.message}")
    if normalized_name == "capability_profile":
        _validate_capability_profile_identity(document)
        assert_public_safe(document)
    elif normalized_name == "operation_receipt":
        _validate_operation_receipt_timeline(document)
    elif normalized_name == "event":
        _validate_event_freshness(document)
    digest_field = PACKET_DIGEST_FIELDS.get(normalized_name)
    if digest_field is not None:
        verify_digest(document, digest_field)
