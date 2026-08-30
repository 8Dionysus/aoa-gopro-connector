from __future__ import annotations

import pytest

from aoa_gopro_connector.digest import ZERO_DIGEST
from aoa_gopro_connector.errors import ContractError
from aoa_gopro_connector.schema import validate_document


SOURCE_DIGEST = "sha256:" + "3" * 64


def _manifest(ingest_state: str = "inventory_only") -> dict[str, object]:
    return {
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


def test_inventory_manifest_may_precede_transfer_integrity() -> None:
    validate_document("media_manifest", _manifest())


def test_completed_ingest_requires_concrete_size_and_checksum() -> None:
    manifest = _manifest("complete")
    with pytest.raises(ContractError, match="size_bytes"):
        validate_document("media_manifest", manifest)

    manifest["size_bytes"] = 1024
    with pytest.raises(ContractError, match="source_checksum"):
        validate_document("media_manifest", manifest)

    manifest["source_checksum"] = SOURCE_DIGEST
    manifest["retention_class"] = "ephemeral"
    validate_document("media_manifest", manifest)
