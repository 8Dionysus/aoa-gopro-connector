from __future__ import annotations

import json
from pathlib import Path

import pytest

from aoa_gopro_connector.adapters import ReplayReadAdapter
from aoa_gopro_connector.digest import attach_digest, verify_digest
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


@pytest.mark.parametrize(
    "key",
    [
        "serial_number",
        "device_id",
        "device-id",
        "deviceId",
        "authorization",
        "wifiPassword",
        "wifiSsid",
        "authToken",
        "passphrase",
        "wifiName",
    ],
)
def test_replay_fixture_rejects_sensitive_keys(key: str) -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"]["/gopro/camera/info"][key] = "unit-kitchen-hero-13"
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


@pytest.mark.parametrize(
    ("route", "field"),
    [
        ("/gopro/camera/info", "unexpectedInfo"),
        ("/gopro/camera/state", "unexpectedState"),
        ("/gopro/media/list", "unexpectedMedia"),
    ],
)
def test_replay_fixture_rejects_unknown_response_fields(
    route: str,
    field: str,
) -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"][route][field] = "synthetic"
    with pytest.raises(ContractError, match="unknown fields"):
        ReplayReadAdapter(value)


def test_replay_fixture_rejects_non_numeric_state_keys() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"]["/gopro/camera/state"]["status"]["unitReference"] = 1
    with pytest.raises(ContractError, match="non-numeric keys"):
        ReplayReadAdapter(value)


def test_replay_fixture_rejects_non_gopro_media_directory() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"]["/gopro/media/list"]["media"] = [
        {"d": "owned-camera.example.com", "fs": []}
    ]
    with pytest.raises(ContractError, match="NNNGOPRO"):
        ReplayReadAdapter(value)


def test_replay_fixture_accepts_fixed_synthetic_media_filename() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"]["/gopro/media/list"]["media"] = [
        {
            "d": "100GOPRO",
            "fs": [
                {
                    "n": "synthetic-video.mp4",
                    "cre": "1788081600",
                    "mod": "1788081601",
                    "glrv": "1024",
                    "ls": "-1",
                }
            ],
        }
    ]
    adapter = ReplayReadAdapter(value)
    profile = build_capability_profile(adapter, _context(adapter))
    assert profile["observations"]["media_group_count"] == 1
    assert profile["observations"]["media_item_count"] == 1


@pytest.mark.parametrize("field", ["cre", "mod", "glrv", "ls", "s"])
def test_replay_fixture_rejects_identity_in_media_metadata(field: str) -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"]["/gopro/media/list"]["media"] = [
        {
            "d": "100GOPRO",
            "fs": [
                {
                    "n": "synthetic-video.mp4",
                    field: "owned-camera.example.com",
                }
            ],
        }
    ]
    with pytest.raises(ContractError, match=field):
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


@pytest.mark.parametrize("protocol_version", ["kitchen-hero13", "1.2.3.4"])
def test_probe_rejects_free_form_protocol_version(protocol_version: str) -> None:
    adapter = ReplayReadAdapter.from_path(FIXTURE)
    context = _context(adapter)
    invalid_context = ProbeContext(
        observed_at=context.observed_at,
        topology=context.topology,
        discovery=context.discovery,
        protocol_version=protocol_version,
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


@pytest.mark.parametrize(
    "capability",
    [
        "ble_discovery_and_wake",
        "wifi_ap_control",
        "cohn_control",
        "camera_effects",
        "preview",
        "recording",
        "hilight",
        "media_transfer",
        "gpmf",
        "disconnect_recovery",
    ],
)
def test_read_only_profile_rejects_observed_non_read_capability(
    capability: str,
) -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["capabilities"][capability] = "observed"
    with pytest.raises(ContractError, match=f"capabilities.{capability}"):
        validate_document("capability_profile", profile)


def test_capability_profile_rejects_mismatched_evidence_posture() -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["posture"] = "sanitized_replay"
    with pytest.raises(ContractError, match="evidence_refs.2"):
        validate_document("capability_profile", profile)


def test_capability_profile_rejects_ipv4_shaped_protocol_version() -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["api"]["protocol_version"] = "1.2.3.4"
    with pytest.raises(ContractError, match="api.protocol_version"):
        validate_document("capability_profile", profile)


def test_capability_profile_rejects_noncanonical_profile_id() -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["profile_id"] = "gopro-kitchen-hero13"
    profile = attach_digest(profile, "profile_digest")
    with pytest.raises(ContractError, match="profile_id"):
        validate_document("capability_profile", profile)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("published_version", "owned-camera.example.com"),
        ("declared_python", "owned-camera.example.com"),
    ],
)
def test_capability_profile_rejects_unpublished_sdk_metadata(
    field: str,
    value: str,
) -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["sdk"][field] = value
    profile = attach_digest(profile, "profile_digest")
    with pytest.raises(ContractError, match=field):
        validate_document("capability_profile", profile)


def test_capability_profile_rejects_mismatched_normalized_firmware() -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["camera"]["firmware_release_version"] = "9.99.99"
    profile["profile_id"] = (
        "gopro-hero13-black-stock-9.99.99-usb-ncm-http"
    )
    profile = attach_digest(profile, "profile_digest")
    with pytest.raises(ContractError, match="firmware_release_version"):
        validate_document("capability_profile", profile)


def test_capability_profile_validation_rejects_stale_digest() -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["limitations"].append("Synthetic mutation for digest validation.")
    with pytest.raises(ContractError, match="profile_digest"):
        validate_document("capability_profile", profile)


def test_capability_profile_rejects_public_hostname_in_limitation() -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    profile["limitations"].append("Observed at owned-camera.example.com.")
    profile = attach_digest(profile, "profile_digest")
    with pytest.raises(PublicSafetyError, match="public hostname"):
        validate_document("capability_profile", profile)
