"""Sanitized capability probe shared by replay and live read adapters."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any

from .adapters.base import ReadAdapter
from .digest import attach_digest, verify_digest
from .errors import ContractError
from .redaction import assert_public_safe
from .schema import validate_document


OFFICIAL_EVIDENCE_REFS = [
    "https://gopro.github.io/OpenGoPro/",
    "https://gopro.github.io/OpenGoPro/http_2_0",
]


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
        if not self.observed_at or not self.protocol_version or not self.evidence_ref:
            raise ContractError("probe context is incomplete")


def _normalized_firmware(value: str) -> str:
    parts = value.split(".")
    if len(parts) >= 3 and all(part.isdigit() for part in parts[-3:]):
        major, minor, patch = parts[-3:]
        return f"{int(major)}.{minor.zfill(2)}.{patch.zfill(2)}"
    return value


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")


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
    current = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    return {
        "published_version": "0.22.0",
        "declared_python": ">=3.11,<3.14",
        "current_python": current,
        "current_python_compatible": (3, 11) <= sys.version_info[:2] < (3, 14),
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
    if not isinstance(model_name, str) or not model_name.strip():
        raise ContractError("camera info lacks safe model_name")
    if (
        isinstance(model_number, bool)
        or not isinstance(model_number, (str, int))
        or (isinstance(model_number, str) and not model_number.strip())
    ):
        raise ContractError("camera info lacks safe model_number")
    if not isinstance(firmware_version, str) or not firmware_version:
        raise ContractError("camera info lacks firmware_version")
    statuses = state.get("status")
    settings = state.get("settings")
    if not isinstance(statuses, dict) or not isinstance(settings, dict):
        raise ContractError("camera state lacks status/settings objects")
    media_group_count, media_item_count = _count_media(media)

    release_version = _normalized_firmware(firmware_version)
    profile_id = (
        f"gopro-{_slug(str(model_name))}-{context.firmware_posture}-"
        f"{release_version}-{context.topology.replace('_', '-')}"
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
            "model_number": str(model_number),
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
