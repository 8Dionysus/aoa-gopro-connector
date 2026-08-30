from __future__ import annotations

import pytest

from aoa_gopro_connector.digest import ZERO_DIGEST, attach_digest
from aoa_gopro_connector.errors import ContractError
from aoa_gopro_connector.schema import validate_document


PROFILE_DIGEST = "sha256:" + "1" * 64


def _operation_plan(effect_kind: str = "record.start") -> dict[str, object]:
    payload = {
        "schema_version": "aoa_gopro_operation_plan_v1",
        "operation_id": "operation:fixture-record",
        "idempotency_key": "fixture-record-0001",
        "camera_ref": "device:fixture-camera",
        "capability_profile_digest": PROFILE_DIGEST,
        "effect": {"kind": effect_kind, "parameters": {}},
        "preconditions": [
            {
                "kind": "lease",
                "expected": "held",
                "observation_ref": "observation:fixture-lease",
            }
        ],
        "deadline": "2026-08-30T05:00:00Z",
        "retry_policy": {
            "max_attempts": 1,
            "backoff": "none",
            "reconcile_indeterminate": True,
        },
        "expected_postconditions": [
            {
                "kind": "recording",
                "expected": True,
                "observation_method": "camera_state",
            }
        ],
        "privacy_consequence": "synthetic fixture only",
        "retention_consequence": "inventory only",
        "approval": {
            "required": True,
            "approval_ref": "approval:fixture-operator",
        },
        "plan_digest": ZERO_DIGEST,
    }
    return attach_digest(payload, "plan_digest")


def _event() -> dict[str, object]:
    payload = {
        "schema_version": "aoa_gopro_event_v1",
        "event_id": "event:fixture-discovered",
        "event_type": "camera.discovered",
        "device_ref": "device:fixture-camera",
        "causal_operation_id": None,
        "wall_time": "2026-08-30T05:00:00Z",
        "monotonic_ns": 1,
        "observed_source": "fixture",
        "capability_profile_digest": PROFILE_DIGEST,
        "confidence": None,
        "freshness": {
            "observed_at": "2026-08-30T05:00:00Z",
            "expires_at": None,
            "posture": "current",
        },
        "payload": {},
        "evidence_refs": ["fixture:event"],
        "event_digest": ZERO_DIGEST,
    }
    return attach_digest(payload, "event_digest")


def _media_manifest() -> dict[str, object]:
    payload = {
        "schema_version": "aoa_gopro_media_manifest_v1",
        "manifest_id": "media-manifest:fixture-empty",
        "device_ref": "device:fixture-camera",
        "observed_at": "2026-08-30T05:00:00Z",
        "camera_media_ref": "camera-media:fixture",
        "media_kind": "video",
        "size_bytes": None,
        "source_checksum": None,
        "ingest_state": "inventory_only",
        "original_immutable": True,
        "retention_class": "inventory_only",
        "derivatives": [],
        "provenance_refs": ["fixture:inventory"],
        "manifest_digest": ZERO_DIGEST,
    }
    return attach_digest(payload, "manifest_digest")


def test_operation_plan_contract() -> None:
    validate_document("operation_plan", _operation_plan())


@pytest.mark.parametrize(
    "preconditions",
    [
        [
            {
                "kind": "battery",
                "expected": "sufficient",
                "observation_ref": "observation:fixture-battery",
            }
        ],
        [
            {
                "kind": "lease",
                "expected": "missing",
                "observation_ref": "observation:fixture-lease",
            }
        ],
        [
            {
                "kind": "lease",
                "expected": "held",
                "observation_ref": "observation:fixture-lease-one",
            },
            {
                "kind": "lease",
                "expected": "held",
                "observation_ref": "observation:fixture-lease-two",
            },
        ],
    ],
)
def test_operation_plan_requires_one_held_lease(
    preconditions: list[dict[str, object]],
) -> None:
    plan = _operation_plan()
    plan["preconditions"] = preconditions
    with pytest.raises(ContractError, match="preconditions"):
        validate_document("operation_plan", plan)


@pytest.mark.parametrize(
    "effect_kind",
    [
        "record.start",
        "firmware.install",
        "firmware.update",
        "factory.reset",
        "media.delete.irreversible",
    ],
)
def test_all_effects_require_exact_approval(effect_kind: str) -> None:
    plan = _operation_plan(effect_kind)
    plan["approval"] = {
        "required": False,
        "approval_ref": "approval:fixture-operator",
    }
    with pytest.raises(ContractError, match="approval.required"):
        validate_document("operation_plan", plan)

    plan["approval"] = {"required": True, "approval_ref": None}
    with pytest.raises(ContractError, match="approval.approval_ref"):
        validate_document("operation_plan", plan)

    plan["approval"] = {
        "required": True,
        "approval_ref": "approval:fixture-operator",
    }
    validate_document("operation_plan", plan)


@pytest.mark.parametrize("approval_ref", ["   ", "operator-approved"])
def test_operation_plan_requires_canonical_approval_ref(approval_ref: str) -> None:
    plan = _operation_plan()
    plan["approval"]["approval_ref"] = approval_ref
    plan = attach_digest(plan, "plan_digest")
    with pytest.raises(ContractError, match="approval.approval_ref"):
        validate_document("operation_plan", plan)


def test_date_time_formats_are_enforced() -> None:
    for schema_name, document, field in (
        ("operation_plan", _operation_plan(), "deadline"),
        ("event", _event(), "wall_time"),
    ):
        document[field] = "never"
        with pytest.raises(ContractError, match=field):
            validate_document(schema_name, document)


def test_event_and_media_contracts() -> None:
    validate_document("event", _event())
    validate_document("media_manifest", _media_manifest())


def test_event_rejects_expiration_before_observation() -> None:
    event = _event()
    event["freshness"]["expires_at"] = "2026-08-30T04:59:59Z"
    with pytest.raises(ContractError, match="freshness.expires_at"):
        validate_document("event", event)


def test_event_freshness_compares_instants_across_offsets() -> None:
    event = _event()
    event["freshness"]["observed_at"] = "2026-08-30T05:00:00+01:00"
    event["freshness"]["expires_at"] = "2026-08-30T04:00:00Z"
    event = attach_digest(event, "event_digest")
    validate_document("event", event)


def test_event_freshness_accepts_lowercase_rfc3339_utc_suffix() -> None:
    event = _event()
    event["wall_time"] = "2026-08-30T05:00:00z"
    event["freshness"]["observed_at"] = "2026-08-30T05:00:00z"
    event["freshness"]["expires_at"] = "2026-08-30T05:00:01z"
    event = attach_digest(event, "event_digest")
    validate_document("event", event)


def test_event_freshness_accepts_offset_equivalent_rfc3339_leap_second() -> None:
    event = _event()
    event["wall_time"] = "1990-12-31T23:59:60Z"
    event["freshness"]["observed_at"] = "1990-12-31T15:59:60-08:00"
    event["freshness"]["expires_at"] = "1990-12-31T23:59:60Z"
    event = attach_digest(event, "event_digest")
    validate_document("event", event)


def test_event_rejects_leap_second_away_from_month_boundary() -> None:
    event = _event()
    event["wall_time"] = "2026-08-30T05:00:60Z"
    event = attach_digest(event, "event_digest")
    with pytest.raises(ContractError, match="wall_time"):
        validate_document("event", event)


@pytest.mark.parametrize("causal_operation_id", ["", "not-an-operation"])
def test_event_rejects_invalid_causal_operation_id(
    causal_operation_id: str,
) -> None:
    event = _event()
    event["causal_operation_id"] = causal_operation_id
    with pytest.raises(ContractError, match="causal_operation_id"):
        validate_document("event", event)


def test_digest_bearing_packet_validation_rejects_stale_integrity_fields() -> None:
    plan = _operation_plan()
    plan["idempotency_key"] = "fixture-record-mutated"
    with pytest.raises(ContractError, match="plan_digest"):
        validate_document("operation_plan", plan)

    event = _event()
    event["monotonic_ns"] = 2
    with pytest.raises(ContractError, match="event_digest"):
        validate_document("event", event)

    manifest = _media_manifest()
    manifest["retention_class"] = "ephemeral"
    with pytest.raises(ContractError, match="manifest_digest"):
        validate_document("media_manifest", manifest)
