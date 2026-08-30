"""Load and validate repository-owned JSON packet schemas."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
import os
import re
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, validators
from jsonschema.exceptions import SchemaError

from .digest import canonical_digest, verify_digest
from .errors import ContractError
from .json_io import strict_json_loads
from .models import canonical_profile_id, normalize_firmware_release
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
RFC3339_PATTERN = re.compile(
    r"^(?P<year>[0-9]{4})-(?P<month>[0-9]{2})-(?P<day>[0-9]{2})"
    r"[Tt](?P<hour>[0-9]{2}):(?P<minute>[0-9]{2}):(?P<second>[0-9]{2})"
    r"(?:\.(?P<fraction>[0-9]+))?"
    r"(?P<offset>[Zz]|[+-][0-9]{2}:[0-9]{2})$"
)
Rfc3339Instant = tuple[int, int, Decimal]


def _is_json_schema_integer(_checker: object, instance: object) -> bool:
    if isinstance(instance, Decimal):
        return instance.is_finite() and instance == instance.to_integral_value()
    return Draft202012Validator.TYPE_CHECKER.is_type(instance, "integer")


CONNECTOR_TYPE_CHECKER = Draft202012Validator.TYPE_CHECKER.redefine(
    "integer",
    _is_json_schema_integer,
)
ConnectorValidator = validators.extend(
    Draft202012Validator,
    type_checker=CONNECTOR_TYPE_CHECKER,
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
    try:
        Draft202012Validator.check_schema(value)
    except SchemaError as exc:
        raise ContractError(f"invalid schema definition {path.name}") from exc
    return value


def _parse_rfc3339(value: str) -> Rfc3339Instant:
    match = RFC3339_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("value does not match the RFC 3339 grammar")
    components = {
        key: int(match[key])
        for key in ("year", "month", "day", "hour", "minute", "second")
    }
    calendar_date = date(
        components["year"],
        components["month"],
        components["day"],
    )
    if components["hour"] > 23:
        raise ValueError("RFC 3339 hour is outside 00-23")
    if components["minute"] > 59:
        raise ValueError("RFC 3339 minute is outside 00-59")
    if components["second"] > 60:
        raise ValueError("RFC 3339 second is outside 00-60")

    offset = match["offset"]
    offset_seconds = 0
    if offset.casefold() != "z":
        if offset == "-00:00":
            raise ValueError("RFC 3339 unknown local offset is not an instant")
        offset_hour = int(offset[1:3])
        offset_minute = int(offset[4:6])
        if offset_hour > 23 or offset_minute > 59:
            raise ValueError("RFC 3339 numeric offset is outside its grammar")
        direction = 1 if offset[0] == "+" else -1
        offset_seconds = direction * (offset_hour * 3600 + offset_minute * 60)

    local_second = (
        calendar_date.toordinal() * 86_400
        + components["hour"] * 3600
        + components["minute"] * 60
        + components["second"]
    )
    utc_second = local_second - offset_seconds
    leap_phase = 0
    if components["second"] == 60:
        utc_ordinal, utc_second_of_day = divmod(utc_second, 86_400)
        if utc_second_of_day != 0 or date.fromordinal(utc_ordinal).day != 1:
            raise ValueError("RFC 3339 leap second is not at a month boundary")
        leap_phase = -1
    fraction_text = match["fraction"]
    fraction = Decimal(f"0.{fraction_text}") if fraction_text else Decimal(0)
    return utc_second, leap_phase, fraction


RFC3339_FORMAT_CHECKER = FormatChecker()


@RFC3339_FORMAT_CHECKER.checks("date-time")
def _is_rfc3339_datetime(value: object) -> bool:
    if not isinstance(value, str):
        return True
    try:
        _parse_rfc3339(value)
    except ValueError:
        return False
    return True


def _rfc3339_datetime(
    value: str,
    *,
    schema_name: str,
    field: str,
) -> Rfc3339Instant:
    try:
        return _parse_rfc3339(value)
    except ValueError as exc:
        raise ContractError(
            f"{schema_name} validation failed at {field}: invalid date-time"
        ) from exc


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
    previous_step_at: Rfc3339Instant | None = None
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
        if previous_step_at is not None and observed_at < previous_step_at:
            raise ContractError(
                f"operation_receipt validation failed at steps.{index}.observed_at: "
                "must not precede the previous step"
            )
        previous_step_at = observed_at


def _validate_operation_receipt_snapshots(document: dict[str, Any]) -> None:
    observed: dict[str, Rfc3339Instant] = {}
    for field in ("before", "after"):
        snapshot = document[field]
        observed[field] = _rfc3339_datetime(
            snapshot["observed_at"],
            schema_name="operation_receipt",
            field=f"{field}.observed_at",
        )
        expected = canonical_digest(snapshot["state"])
        if snapshot["state_digest"] != expected:
            raise ContractError(
                f"operation_receipt validation failed at {field}.state_digest: "
                f"expected {expected}"
            )
        try:
            validate_document("camera_state", snapshot["state"])
        except ContractError as exc:
            raise ContractError(
                f"operation_receipt validation failed at {field}.state: {exc}"
            ) from exc
    if observed["before"] > observed["after"]:
        raise ContractError(
            "operation_receipt validation failed at after.observed_at: "
            "must not precede before.observed_at"
        )
    started_at = _rfc3339_datetime(
        document["started_at"],
        schema_name="operation_receipt",
        field="started_at",
    )
    if observed["before"] > started_at:
        raise ContractError(
            "operation_receipt validation failed at before.observed_at: "
            "must not postdate started_at"
        )
    if observed["after"] < started_at:
        raise ContractError(
            "operation_receipt validation failed at after.observed_at: "
            "must not predate started_at"
        )
    for index, step in enumerate(document["steps"]):
        step_observed_at = _rfc3339_datetime(
            step["observed_at"],
            schema_name="operation_receipt",
            field=f"steps.{index}.observed_at",
        )
        if observed["after"] < step_observed_at:
            raise ContractError(
                "operation_receipt validation failed at after.observed_at: "
                f"must not predate steps.{index}.observed_at"
            )
    finished_at = _rfc3339_datetime(
        document["finished_at"],
        schema_name="operation_receipt",
        field="finished_at",
    )
    if observed["after"] > finished_at:
        raise ContractError(
            "operation_receipt validation failed at after.observed_at: "
            "must not postdate finished_at"
        )


def _validate_event_freshness(document: dict[str, Any]) -> None:
    freshness = document["freshness"]
    wall_time = _rfc3339_datetime(
        document["wall_time"],
        schema_name="event",
        field="wall_time",
    )
    observed_at = _rfc3339_datetime(
        freshness["observed_at"],
        schema_name="event",
        field="freshness.observed_at",
    )
    if wall_time < observed_at:
        raise ContractError(
            "event validation failed at wall_time: "
            "must not precede freshness.observed_at"
        )
    expires_value = freshness["expires_at"]
    if expires_value is None:
        if freshness["posture"] == "stale":
            raise ContractError(
                "event validation failed at freshness.posture: "
                "stale requires expires_at"
            )
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
    if freshness["posture"] == "current" and expires_at < wall_time:
        raise ContractError(
            "event validation failed at freshness.posture: "
            "current event is expired at wall_time"
        )
    if freshness["posture"] == "stale" and expires_at >= wall_time:
        raise ContractError(
            "event validation failed at freshness.posture: "
            "stale event is not expired at wall_time"
        )


def _validate_capability_profile_identity(document: dict[str, Any]) -> None:
    camera = document["camera"]
    expected_release = normalize_firmware_release(camera["firmware_vendor_version"])
    if camera["firmware_release_version"] != expected_release:
        raise ContractError(
            "capability_profile validation failed at "
            "camera.firmware_release_version: "
            f"expected normalized value {expected_release!r}"
        )
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


def _validate_media_manifest_derivative_refs(document: dict[str, Any]) -> None:
    seen: set[str] = set()
    for index, derivative in enumerate(document["derivatives"]):
        artifact_ref = derivative["artifact_ref"]
        if artifact_ref in seen:
            raise ContractError(
                "media_manifest validation failed at "
                f"derivatives.{index}.artifact_ref: duplicate artifact reference"
            )
        seen.add(artifact_ref)


def validate_document(name: str, document: Any) -> None:
    normalized_name = name.removesuffix(".schema.json")
    validator = ConnectorValidator(
        load_schema(name),
        format_checker=RFC3339_FORMAT_CHECKER,
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
        _validate_operation_receipt_snapshots(document)
    elif normalized_name == "event":
        _validate_event_freshness(document)
    elif normalized_name == "media_manifest":
        _validate_media_manifest_derivative_refs(document)
    digest_field = PACKET_DIGEST_FIELDS.get(normalized_name)
    if digest_field is not None:
        verify_digest(document, digest_field)
