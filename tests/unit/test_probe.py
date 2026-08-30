from __future__ import annotations

import json
from pathlib import Path

import pytest

from aoa_gopro_connector.adapters import ReplayReadAdapter
from aoa_gopro_connector.digest import verify_digest
from aoa_gopro_connector.errors import ContractError, PublicSafetyError
from aoa_gopro_connector.probe import ProbeContext, build_capability_profile
from aoa_gopro_connector.redaction import assert_public_safe
from aoa_gopro_connector.schema import validate_document


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "connector/fixtures/hero13/stock-usb-ncm-read-only.json"
REPLAY_PROFILE_DIGEST = (
    "sha256:936be8401ca039a5a600471e6d98b819113bd2607317ba733ba98bd17806eec1"
)
REPLAY_FIXTURE_DIGEST = (
    "sha256:8ab82b45ab6421e2b1c3cfe0e521ed3c29c43817281040b58364712dfdafab3e"
)


def _context(adapter: ReplayReadAdapter) -> ProbeContext:
    value = adapter.fixture["context"]
    return ProbeContext(
        observed_at=value["observed_at"],
        topology=value["topology"],
        discovery=tuple(value["discovery"]),
        protocol_version=value["protocol_version"],
        firmware_posture=value["firmware_posture"],
        evidence_ref=f"fixture:{adapter.fixture_digest}",
    )


def test_replay_builds_content_addressed_public_profile() -> None:
    adapter = ReplayReadAdapter.from_path(FIXTURE)
    profile = build_capability_profile(adapter, _context(adapter))
    validate_document("capability_profile", profile)
    verify_digest(profile, "profile_digest")
    assert profile["profile_digest"] == REPLAY_PROFILE_DIGEST
    assert profile["evidence_refs"][-1] == f"fixture:{REPLAY_FIXTURE_DIGEST}"
    assert_public_safe(profile)
    assert profile["camera"]["firmware_release_version"] == "2.10.00"
    assert profile["posture"] == "sanitized_replay"
    assert profile["privacy"] == {
        "raw_responses_retained": False,
        "device_identifiers_retained": False,
        "network_identity_retained": False,
        "media_names_retained": False,
    }
    assert profile["sdk"] == {
        "published_version": "0.22.0",
        "declared_python": ">=3.11,<3.14",
        "posture": "optional_adapter",
    }


def test_replay_fixture_rejects_sensitive_keys() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"]["/gopro/camera/info"]["serial_number"] = "redacted"
    with pytest.raises(PublicSafetyError):
        ReplayReadAdapter(value)


def test_replay_fixture_rejects_unknown_public_fields() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["context"]["note"] = "kitchen-camera.home.arpa"
    with pytest.raises(ContractError, match="replay context fields differ"):
        ReplayReadAdapter(value)

    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["fixture_id"] = "kitchen-hero13"
    with pytest.raises(ContractError, match="replay fixture fields differ"):
        ReplayReadAdapter(value)


def test_replay_fixture_rejects_non_finite_values() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"]["/gopro/camera/state"]["status"]["8"] = float("nan")
    with pytest.raises(ContractError, match="non-JSON values"):
        ReplayReadAdapter(value)


def test_replay_snapshot_is_immutable_from_public_aliases() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    adapter = ReplayReadAdapter(fixture)
    fixture["responses"]["/gopro/camera/info"]["model_name"] = "HERO12 Black"
    exposed = adapter.fixture
    exposed["responses"]["/gopro/camera/info"]["model_name"] = "HERO11 Black"

    response = adapter.get_json("/gopro/camera/info")
    assert response["model_name"] == "HERO13 Black"
    assert adapter.fixture_digest == REPLAY_FIXTURE_DIGEST


def test_probe_rejects_free_form_protocol_version() -> None:
    adapter = ReplayReadAdapter.from_path(FIXTURE)
    context = _context(adapter)
    invalid_context = ProbeContext(
        observed_at=context.observed_at,
        topology=context.topology,
        discovery=context.discovery,
        protocol_version="kitchen-hero13",
        firmware_posture=context.firmware_posture,
        evidence_ref=context.evidence_ref,
    )
    with pytest.raises(ContractError, match="protocol version"):
        build_capability_profile(adapter, invalid_context)


def test_probe_rejects_media_response_without_inventory() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"]["/gopro/media/list"] = {"id": "fixture"}
    adapter = ReplayReadAdapter(value)
    with pytest.raises(ContractError, match="no media field"):
        build_capability_profile(adapter, _context(adapter))


def test_probe_rejects_media_group_without_file_list() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"]["/gopro/media/list"] = {
        "id": "fixture",
        "media": [{"d": "100GOPRO"}],
    }
    adapter = ReplayReadAdapter(value)
    with pytest.raises(ContractError, match="no fs field"):
        build_capability_profile(adapter, _context(adapter))


def test_probe_rejects_media_group_without_directory() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"]["/gopro/media/list"] = {
        "id": "fixture",
        "media": [{"fs": []}],
    }
    adapter = ReplayReadAdapter(value)
    with pytest.raises(ContractError, match="no directory field"):
        build_capability_profile(adapter, _context(adapter))


@pytest.mark.parametrize(
    ("entry", "message"),
    [(None, "not an object"), ({}, "no name field")],
)
def test_probe_rejects_malformed_media_file_entry(
    entry: object,
    message: str,
) -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"]["/gopro/media/list"] = {
        "id": "fixture",
        "media": [{"d": "100GOPRO", "fs": [entry]}],
    }
    adapter = ReplayReadAdapter(value)
    with pytest.raises(ContractError, match=message):
        build_capability_profile(adapter, _context(adapter))


@pytest.mark.parametrize(
    ("field", "value"),
    [("model_name", True), ("model_number", False)],
)
def test_probe_rejects_boolean_model_fields(field: str, value: bool) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["responses"]["/gopro/camera/info"][field] = value
    adapter = ReplayReadAdapter(fixture)
    with pytest.raises(ContractError, match=field):
        build_capability_profile(adapter, _context(adapter))


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("model_name", "kitchen-hero13", "model_name"),
        ("model_number", "kitchen-65", "model_number"),
        ("model_number", -1, "model_number"),
        ("firmware_version", "kitchen-hero13", "firmware_version"),
    ],
)
def test_probe_rejects_identifier_shaped_camera_metadata(
    field: str,
    value: object,
    message: str,
) -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    fixture["responses"]["/gopro/camera/info"][field] = value
    adapter = ReplayReadAdapter(fixture)
    with pytest.raises(ContractError, match=message):
        build_capability_profile(adapter, _context(adapter))


def test_named_live_profile_is_valid_and_redacted() -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    validate_document("capability_profile", profile)
    verify_digest(profile, "profile_digest")
    assert_public_safe(profile)
    assert profile["observations"]["status_key_count"] == 79
    assert profile["observations"]["setting_key_count"] == 120


def test_capability_profile_requires_versioned_capability_vocabulary() -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    del profile["capabilities"]["disconnect_recovery"]
    with pytest.raises(ContractError, match="disconnect_recovery"):
        validate_document("capability_profile", profile)


def test_capability_profile_rejects_unknown_capability_name() -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["capabilities"]["firmware_update"] = "observed"
    with pytest.raises(ContractError, match="Additional properties"):
        validate_document("capability_profile", profile)


def test_capability_profile_rejects_mismatched_evidence_posture() -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["posture"] = "sanitized_replay"
    with pytest.raises(ContractError, match="evidence_refs.2"):
        validate_document("capability_profile", profile)
