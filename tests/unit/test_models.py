from __future__ import annotations

import pytest

from aoa_gopro_connector.errors import ContractError
from aoa_gopro_connector.models import (
    CameraState,
    Control,
    Health,
    MediaLifecycle,
    Network,
    Power,
    Presence,
    canonical_profile_id,
    normalize_firmware_release,
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


def test_absent_state_requires_offline_network_in_model_and_schema() -> None:
    state = CameraState(network=Network.READY)
    with pytest.raises(ContractError, match="network=offline"):
        state.validate()

    document = CameraState().as_dict()
    document["network"] = "ready"
    with pytest.raises(ContractError, match="network"):
        validate_document("camera_state", document)


@pytest.mark.parametrize(
    "media",
    [MediaLifecycle.FINALIZING, MediaLifecycle.TRANSFERRING],
)
def test_absent_state_requires_idle_media_in_model_and_schema(
    media: MediaLifecycle,
) -> None:
    state = CameraState(media=media)
    with pytest.raises(ContractError, match="media=idle"):
        state.validate()

    document = CameraState().as_dict()
    document["media"] = media.value
    with pytest.raises(ContractError, match="media"):
        validate_document("camera_state", document)


def test_schema_rejects_control_ready_without_power_on() -> None:
    document = CameraState(
        presence=Presence.DISCOVERED,
        power=Power.ON,
        control=Control.READY,
    ).as_dict()
    document["power"] = "off"
    with pytest.raises(ContractError, match="power"):
        validate_document("camera_state", document)


def test_powered_off_state_requires_offline_network_in_model_and_schema() -> None:
    state = CameraState(
        presence=Presence.DISCOVERED,
        power=Power.OFF,
        network=Network.READY,
    )
    with pytest.raises(ContractError, match="power=off"):
        state.validate()

    document = CameraState(
        presence=Presence.DISCOVERED,
        power=Power.OFF,
    ).as_dict()
    document["network"] = "ready"
    with pytest.raises(ContractError, match="network"):
        validate_document("camera_state", document)


@pytest.mark.parametrize(
    ("power", "network"),
    [
        (Power.OFF, Network.OFFLINE),
        (Power.ON, Network.DISCOVERABLE),
    ],
)
def test_media_transfer_requires_powered_ready_network_in_model_and_schema(
    power: Power,
    network: Network,
) -> None:
    state = CameraState(
        presence=Presence.DISCOVERED,
        power=power,
        network=network,
        media=MediaLifecycle.TRANSFERRING,
    )
    with pytest.raises(
        ContractError,
        match="media=transferring requires power=on and network=ready",
    ):
        state.validate()

    document = CameraState(
        presence=Presence.DISCOVERED,
        power=Power.ON,
        network=Network.READY,
        media=MediaLifecycle.TRANSFERRING,
    ).as_dict()
    document["power"] = power.value
    document["network"] = network.value
    with pytest.raises(ContractError):
        validate_document("camera_state", document)


def test_media_transfer_accepts_powered_ready_network() -> None:
    state = CameraState(
        presence=Presence.DISCOVERED,
        power=Power.ON,
        network=Network.READY,
        media=MediaLifecycle.TRANSFERRING,
    )
    state.validate()
    validate_document("camera_state", state.as_dict())


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


def test_firmware_release_normalization_is_shared_domain_logic() -> None:
    assert normalize_firmware_release("H24.01.02.10.00") == "2.10.00"
