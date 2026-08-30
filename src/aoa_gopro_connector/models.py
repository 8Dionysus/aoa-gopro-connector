"""Camera-domain models that do not depend on a transport SDK."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum

from .errors import ContractError


class Presence(StrEnum):
    ABSENT = "absent"
    DISCOVERED = "discovered"


class Power(StrEnum):
    UNKNOWN = "unknown"
    OFF = "off"
    WAKING = "waking"
    ON = "on"
    SLEEPING = "sleeping"


class Control(StrEnum):
    UNLEASED = "unleased"
    LEASED = "leased"
    READY = "ready"


class Network(StrEnum):
    OFFLINE = "offline"
    DISCOVERABLE = "discoverable"
    READY = "ready"


class MediaLifecycle(StrEnum):
    IDLE = "idle"
    FINALIZING = "finalizing"
    TRANSFERRING = "transferring"


class Health(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    RECOVERING = "recovering"
    NEEDS_OPERATOR = "needs_operator"


@dataclass(frozen=True, slots=True)
class CameraState:
    presence: Presence = Presence.ABSENT
    power: Power = Power.UNKNOWN
    control: Control = Control.UNLEASED
    network: Network = Network.OFFLINE
    previewing: bool = False
    recording: bool = False
    media: MediaLifecycle = MediaLifecycle.IDLE
    health: Health = Health.HEALTHY
    degraded_reasons: tuple[str, ...] = ()

    def validate(self) -> None:
        if self.presence is Presence.ABSENT:
            if self.control is not Control.UNLEASED:
                raise ContractError("an absent camera cannot hold a lease")
            if self.previewing or self.recording:
                raise ContractError("an absent camera cannot preview or record")
        if self.control is Control.READY and self.power is not Power.ON:
            raise ContractError("control-ready requires power=on")
        if self.previewing or self.recording:
            if self.control is not Control.READY:
                raise ContractError("camera activity requires control=ready")
            if self.network is not Network.READY:
                raise ContractError("camera activity requires network=ready")
        if self.health is Health.HEALTHY and self.degraded_reasons:
            raise ContractError("healthy state cannot carry degraded reasons")
        if self.health is not Health.HEALTHY and not self.degraded_reasons:
            raise ContractError("non-healthy state requires a reason")

    def as_dict(self) -> dict[str, object]:
        self.validate()
        result = asdict(self)
        result["schema_version"] = "aoa_gopro_camera_state_v1"
        result["degraded_reasons"] = list(self.degraded_reasons)
        return result
