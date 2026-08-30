"""Sanitized capability probe shared by replay and live read adapters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .adapters.base import ReadAdapter
from .digest import attach_digest, verify_digest
from .errors import ContractError
from .models import canonical_profile_id, normalize_firmware_release
from .redaction import assert_public_safe
from .schema import validate_document


OFFICIAL_EVIDENCE_REFS = [
    "https://gopro.github.io/OpenGoPro/",
    "https://gopro.github.io/OpenGoPro/http_2_0",
]
OPEN_GOPRO_PUBLISHED_VERSION = "0.22.0"
OPEN_GOPRO_DECLARED_PYTHON = ">=3.11,<3.14"

DISCOVERY_MECHANISMS = (
    "ble",
    "cohn_registry",
    "manual",
    "mdns",
    "replay",
    "usb",
    "wifi_scan",
)
PROTOCOL_VERSION_PATTERN = re.compile(
    r"^(?:unknown|[0-9]{1,3}(?:\.[0-9]{1,3}){0,2})$"
)
MODEL_NAME_PATTERN = re.compile(
    r"^(?:HERO(?:[0-9]{1,2})?(?: Black(?: Mini)?)?|MAX(?: ?[0-9])?|LIT HERO)$"
)
MODEL_NUMBER_PATTERN = re.compile(r"^[0-9]{1,6}$")
FIRMWARE_VERSION_PATTERN = re.compile(
    r"^[A-Z][A-Z0-9]{1,7}(?:\.[0-9]{1,4}){3,6}$"
)


@dataclass(frozen=True, slots=True)
class ProbeContext:
    observed_at: str
    topology: str
    discovery: tuple[str, ...]
    protocol_version: str
    firmware_posture: str
    evidence_ref: str

    def validate(self) -> None:
        if self.topology not in {"usb_ncm_http", "wifi_ap_http", "cohn_http"}:
            raise ContractError(f"unsupported topology {self.topology!r}")
        if self.firmware_posture not in {"stock", "labs", "unknown"}:
            raise ContractError("firmware posture must be stock, labs, or unknown")
        if any(
            not isinstance(item, str) or item not in DISCOVERY_MECHANISMS
            for item in self.discovery
        ):
            raise ContractError("probe discovery contains an unknown mechanism")
        if not PROTOCOL_VERSION_PATTERN.fullmatch(self.protocol_version):
            raise ContractError(
                "probe protocol version must be unknown or one to three numeric components"
            )
        if not self.observed_at or not self.protocol_version or not self.evidence_ref:
            raise ContractError("probe context is incomplete")


def _count_media(payload: dict[str, Any]) -> tuple[int, int]:
    if "media" not in payload:
        raise ContractError("media response has no media field")
    groups = payload["media"]
    if not isinstance(groups, list):
        raise ContractError("media response has no list-valued media field")
    item_count = 0
    for group in groups:
        if not isinstance(group, dict):
            raise ContractError("media group is not an object")
        directory = group.get("d")
        if not isinstance(directory, str) or not directory.strip():
            raise ContractError("media group has no directory field")
        if "fs" not in group:
            raise ContractError("media group has no fs field")
        items = group["fs"]
        if not isinstance(items, list):
            raise ContractError("media group fs is not a list")
        for item in items:
            if not isinstance(item, dict):
                raise ContractError("media file entry is not an object")
            name = item.get("n")
            if not isinstance(name, str) or not name.strip():
                raise ContractError("media file entry has no name field")
        item_count += len(items)
    return len(groups), item_count


def _sdk_compatibility() -> dict[str, Any]:
    return {
        "published_version": OPEN_GOPRO_PUBLISHED_VERSION,
        "declared_python": OPEN_GOPRO_DECLARED_PYTHON,
        "posture": "optional_adapter",
    }


def build_capability_profile(
    adapter: ReadAdapter,
    context: ProbeContext,
) -> dict[str, Any]:
    context.validate()
    info = adapter.get_json("/gopro/camera/info")
    state = adapter.get_json("/gopro/camera/state")
    media = adapter.get_json("/gopro/media/list")

    model_name = info.get("model_name")
    model_number = info.get("model_number")
    firmware_version = info.get("firmware_version")
    if not isinstance(model_name, str) or not MODEL_NAME_PATTERN.fullmatch(model_name):
        raise ContractError("camera info lacks documented model_name")
    if isinstance(model_number, bool) or not isinstance(model_number, (str, int)):
        raise ContractError("camera info lacks safe model_number")
    model_number_text = str(model_number)
    if not MODEL_NUMBER_PATTERN.fullmatch(model_number_text):
        raise ContractError("camera info lacks safe model_number")
    if not isinstance(firmware_version, str) or not FIRMWARE_VERSION_PATTERN.fullmatch(
        firmware_version
    ):
        raise ContractError("camera info lacks documented firmware_version")
    statuses = state.get("status")
    settings = state.get("settings")
    if not isinstance(statuses, dict) or not isinstance(settings, dict):
        raise ContractError("camera state lacks status/settings objects")
    media_group_count, media_item_count = _count_media(media)

    release_version = normalize_firmware_release(firmware_version)
    profile_id = canonical_profile_id(
        model_name=str(model_name),
        firmware_posture=context.firmware_posture,
        firmware_release_version=release_version,
        topology=context.topology,
    )
    capabilities = {
        "read_camera_info": "observed",
        "read_camera_state": "observed",
        "list_media": "observed",
        "ble_discovery_and_wake": "not_observed",
        "wifi_ap_control": "not_observed",
        "cohn_control": "not_observed",
        "camera_effects": "not_observed",
        "preview": "not_observed",
        "recording": "not_observed",
        "hilight": "not_observed",
        "media_transfer": "not_observed",
        "gpmf": "not_observed",
        "disconnect_recovery": "not_observed",
    }
    payload: dict[str, Any] = {
        "schema_version": "aoa_gopro_capability_profile_v1",
        "profile_id": profile_id,
        "observed_at": context.observed_at,
        "posture": "live_read_only" if context.evidence_ref.startswith("local-live") else "sanitized_replay",
        "device_ref": "device:redacted",
        "camera": {
            "model_name": str(model_name),
            "model_number": model_number_text,
            "firmware_vendor_version": firmware_version,
            "firmware_release_version": release_version,
            "firmware_posture": context.firmware_posture,
        },
        "transport": {
            "topology": context.topology,
            "discovery": sorted(set(context.discovery)),
            "http_read": "observed",
        },
        "api": {
            "family": "OpenGoPro",
            "spec_version": "2.0",
            "protocol_version": context.protocol_version,
        },
        "observations": {
            "status_key_count": len(statuses),
            "setting_key_count": len(settings),
            "media_group_count": media_group_count,
            "media_item_count": media_item_count,
        },
        "capabilities": capabilities,
        "sdk": _sdk_compatibility(),
        "privacy": {
            "raw_responses_retained": False,
            "device_identifiers_retained": False,
            "network_identity_retained": False,
            "media_names_retained": False,
        },
        "limitations": [
            "Read-only observation does not establish control readiness.",
            "No preview, recording, transfer, recovery, or endurance operation was attempted.",
            "The profile applies only to the named model, firmware, and topology.",
        ],
        "evidence_refs": [*OFFICIAL_EVIDENCE_REFS, context.evidence_ref],
    }
    profile = attach_digest(payload, "profile_digest")
    assert_public_safe(profile)
    validate_document("capability_profile", profile)
    verify_digest(profile, "profile_digest")
    return profile
