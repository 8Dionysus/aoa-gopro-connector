from __future__ import annotations

import json
from pathlib import Path

import pytest

from aoa_gopro_connector.adapters import ReplayReadAdapter
from aoa_gopro_connector.digest import verify_digest
from aoa_gopro_connector.errors import PublicSafetyError
from aoa_gopro_connector.probe import ProbeContext, build_capability_profile
from aoa_gopro_connector.redaction import assert_public_safe
from aoa_gopro_connector.schema import validate_document


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "connector/fixtures/hero13/stock-usb-ncm-read-only.json"


def _context(adapter: ReplayReadAdapter) -> ProbeContext:
    value = adapter.fixture["context"]
    return ProbeContext(
        observed_at=value["observed_at"],
        topology=value["topology"],
        discovery=tuple(value["discovery"]),
        protocol_version=value["protocol_version"],
        firmware_posture=value["firmware_posture"],
        evidence_ref=f"fixture:{adapter.fixture['fixture_id']}",
    )


def test_replay_builds_content_addressed_public_profile() -> None:
    adapter = ReplayReadAdapter.from_path(FIXTURE)
    profile = build_capability_profile(adapter, _context(adapter))
    validate_document("capability_profile", profile)
    verify_digest(profile, "profile_digest")
    assert_public_safe(profile)
    assert profile["camera"]["firmware_release_version"] == "2.10.00"
    assert profile["posture"] == "sanitized_replay"
    assert profile["privacy"] == {
        "raw_responses_retained": False,
        "device_identifiers_retained": False,
        "network_identity_retained": False,
        "media_names_retained": False,
    }


def test_replay_fixture_rejects_sensitive_keys() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    value["responses"]["/gopro/camera/info"]["serial_number"] = "redacted"
    with pytest.raises(PublicSafetyError):
        ReplayReadAdapter(value)


def test_named_live_profile_is_valid_and_redacted() -> None:
    path = REPO_ROOT / "connector/profiles/hero13-black-stock-2.10.00-usb-ncm.json"
    profile = json.loads(path.read_text(encoding="utf-8"))
    validate_document("capability_profile", profile)
    verify_digest(profile, "profile_digest")
    assert_public_safe(profile)
    assert profile["observations"]["status_key_count"] == 79
    assert profile["observations"]["setting_key_count"] == 120
