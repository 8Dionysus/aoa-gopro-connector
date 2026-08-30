from __future__ import annotations

import pytest

from aoa_gopro_connector.digest import ZERO_DIGEST, attach_digest
from aoa_gopro_connector.errors import ContractError
from aoa_gopro_connector.schema import validate_document


SOURCE_DIGEST = "sha256:" + "3" * 64
DERIVATIVE_DIGEST_A = "sha256:" + "4" * 64
DERIVATIVE_DIGEST_B = "sha256:" + "5" * 64


def _manifest(ingest_state: str = "inventory_only") -> dict[str, object]:
    payload = {
        "schema_version": "aoa_gopro_media_manifest_v1",
        "manifest_id": "media-manifest:fixture-video",
        "device_ref": "device:fixture-camera",
        "observed_at": "2026-08-30T05:00:00Z",
        "camera_media_ref": "camera-media:fixture-video",
        "media_kind": "video",
        "size_bytes": None,
        "source_checksum": None,
        "ingest_state": ingest_state,
        "original_immutable": True,
        "retention_class": "inventory_only",
        "derivatives": [],
        "provenance_refs": ["fixture:inventory"],
        "manifest_digest": ZERO_DIGEST,
    }
    return attach_digest(payload, "manifest_digest")


def test_inventory_manifest_may_precede_transfer_integrity() -> None:
    validate_document("media_manifest", _manifest())


def test_completed_ingest_requires_concrete_size_and_checksum() -> None:
    manifest = _manifest("complete")
    manifest["retention_class"] = "ephemeral"
    with pytest.raises(ContractError, match="size_bytes"):
        validate_document("media_manifest", manifest)

    manifest["size_bytes"] = 1024
    with pytest.raises(ContractError, match="source_checksum"):
        validate_document("media_manifest", manifest)

    manifest["source_checksum"] = SOURCE_DIGEST
    manifest = attach_digest(manifest, "manifest_digest")
    validate_document("media_manifest", manifest)


def test_completed_ingest_rejects_inventory_only_retention() -> None:
    manifest = _manifest("complete")
    manifest["size_bytes"] = 1024
    manifest["source_checksum"] = SOURCE_DIGEST
    manifest = attach_digest(manifest, "manifest_digest")
    with pytest.raises(ContractError, match="retention_class"):
        validate_document("media_manifest", manifest)


def test_derivative_artifact_references_must_be_unique() -> None:
    manifest = _manifest()
    manifest["derivatives"] = [
        {
            "kind": "proxy",
            "artifact_ref": "artifact:shared-proxy",
            "checksum": DERIVATIVE_DIGEST_A,
            "provenance_ref": "receipt:first-derivative",
        },
        {
            "kind": "semantic",
            "artifact_ref": "artifact:shared-proxy",
            "checksum": DERIVATIVE_DIGEST_B,
            "provenance_ref": "receipt:second-derivative",
        },
    ]
    manifest = attach_digest(manifest, "manifest_digest")

    with pytest.raises(ContractError, match="duplicate artifact reference"):
        validate_document("media_manifest", manifest)


def test_distinct_derivative_artifact_references_are_valid() -> None:
    manifest = _manifest()
    manifest["derivatives"] = [
        {
            "kind": "proxy",
            "artifact_ref": "artifact:first-proxy",
            "checksum": DERIVATIVE_DIGEST_A,
            "provenance_ref": "receipt:first-derivative",
        },
        {
            "kind": "semantic",
            "artifact_ref": "artifact:second-observation",
            "checksum": DERIVATIVE_DIGEST_B,
            "provenance_ref": "receipt:second-derivative",
        },
    ]
    manifest = attach_digest(manifest, "manifest_digest")
    validate_document("media_manifest", manifest)
