from __future__ import annotations

import pytest

from aoa_gopro_connector.errors import ContractError
from aoa_gopro_connector.models import (
    CameraState,
    Control,
    Health,
    Network,
    Power,
    Presence,
    canonical_profile_id,
)
from aoa_gopro_connector.schema import validate_document


def test_absent_default_state_is_valid() -> None:
    state = CameraState()
    document = state.as_dict()
    assert document["schema_version"] == "aoa_gopro_camera_state_v1"
    validate_document("camera_state", document)


def test_preview_and_recording_may_coexist_when_ready() -> None:
    state = CameraState(
        presence=Presence.DISCOVERED,
        power=Power.ON,
        control=Control.READY,
        network=Network.READY,
        previewing=True,
        recording=True,
    )
    validate_document("camera_state", state.as_dict())


def test_activity_requires_control_and_network() -> None:
    state = CameraState(
        presence=Presence.DISCOVERED,
        power=Power.ON,
        control=Control.LEASED,
        network=Network.DISCOVERABLE,
        previewing=True,
    )
    with pytest.raises(ContractError, match="control=ready"):
        state.validate()


def test_degraded_state_requires_reason() -> None:
    with pytest.raises(ContractError, match="requires a reason"):
        CameraState(health=Health.DEGRADED).validate()


def test_schema_rejects_control_ready_without_power_on() -> None:
    document = CameraState(
        presence=Presence.DISCOVERED,
        power=Power.ON,
        control=Control.READY,
    ).as_dict()
    document["power"] = "off"
    with pytest.raises(ContractError, match="power"):
        validate_document("camera_state", document)


def test_capability_profile_id_is_derived_from_sanitized_fields() -> None:
    assert (
        canonical_profile_id(
            model_name="HERO13 Black",
            firmware_posture="stock",
            firmware_release_version="2.10.00",
            topology="usb_ncm_http",
        )
        == "gopro-hero13-black-stock-2.10.00-usb-ncm-http"
    )
