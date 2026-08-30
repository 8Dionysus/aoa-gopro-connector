from __future__ import annotations

from aoa_gopro_connector.digest import ZERO_DIGEST
from aoa_gopro_connector.schema import validate_document


PROFILE_DIGEST = "sha256:" + "1" * 64


def test_operation_plan_contract() -> None:
    validate_document(
        "operation_plan",
        {
            "schema_version": "aoa_gopro_operation_plan_v1",
            "operation_id": "operation:fixture-record",
            "idempotency_key": "fixture-record-0001",
            "camera_ref": "device:fixture-camera",
            "capability_profile_digest": PROFILE_DIGEST,
            "effect": {"kind": "record.start", "parameters": {}},
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
            "approval": {"required": False, "approval_ref": None},
            "plan_digest": ZERO_DIGEST,
        },
    )


def test_event_and_media_contracts() -> None:
    validate_document(
        "event",
        {
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
        },
    )
    validate_document(
        "media_manifest",
        {
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
        },
    )
