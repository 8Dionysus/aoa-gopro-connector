"""Public-safe deterministic read replay."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..digest import canonical_digest
from ..errors import ContractError
from ..json_io import strict_json_dumps, strict_json_loads
from ..redaction import assert_public_safe
from .base import ALLOWED_READ_PATHS


FIXTURE_FIELDS = {"schema_version", "context", "responses"}
CONTEXT_FIELDS = {
    "observed_at",
    "topology",
    "discovery",
    "protocol_version",
    "firmware_posture",
}
CAMERA_INFO_FIELDS = {"model_name", "model_number", "firmware_version"}
CAMERA_STATE_FIELDS = {"status", "settings"}
MEDIA_LIST_FIELDS = {"id", "media"}
MEDIA_GROUP_FIELDS = {"d", "fs"}
MEDIA_FILE_FIELDS = {"n", "cre", "mod", "glrv", "ls", "s"}
SYNTHETIC_MEDIA_IDS = {"fixture", "fixture-empty-card"}
MEDIA_UNSIGNED_DECIMAL_FIELDS = {"cre", "glrv", "mod", "s"}


def _is_bounded_decimal_string(value: Any, *, allow_negative_one: bool = False) -> bool:
    if not isinstance(value, str):
        return False
    if allow_negative_one and value == "-1":
        return True
    return 1 <= len(value) <= 20 and value.isdecimal()


def _reject_unknown_fields(
    value: Any,
    allowed: set[str],
    *,
    label: str,
) -> None:
    if not isinstance(value, dict):
        return
    unknown = sorted(str(key) for key in value if key not in allowed)
    if unknown:
        raise ContractError(f"{label} contains unknown fields: {unknown}")


def _validate_response_shapes(responses: dict[str, Any]) -> None:
    info = responses["/gopro/camera/info"]
    _reject_unknown_fields(info, CAMERA_INFO_FIELDS, label="camera info response")

    state = responses["/gopro/camera/state"]
    _reject_unknown_fields(state, CAMERA_STATE_FIELDS, label="camera state response")
    if isinstance(state, dict):
        for section_name in ("status", "settings"):
            section = state.get(section_name)
            if not isinstance(section, dict):
                continue
            invalid_keys = sorted(
                str(key)
                for key in section
                if not isinstance(key, str)
                or not key.isdecimal()
                or not 1 <= len(key) <= 5
            )
            if invalid_keys:
                raise ContractError(
                    f"camera state {section_name} contains non-numeric keys: "
                    f"{invalid_keys}"
                )
            if any(type(item) not in (bool, int, float) for item in section.values()):
                raise ContractError(
                    f"camera state {section_name} contains non-scalar values"
                )

    media_list = responses["/gopro/media/list"]
    _reject_unknown_fields(media_list, MEDIA_LIST_FIELDS, label="media list response")
    if not isinstance(media_list, dict):
        return
    media_id = media_list.get("id")
    if media_id is not None and media_id not in SYNTHETIC_MEDIA_IDS:
        raise ContractError("replay media id is not a fixed synthetic value")
    groups = media_list.get("media")
    if not isinstance(groups, list):
        return
    for group in groups:
        _reject_unknown_fields(group, MEDIA_GROUP_FIELDS, label="media group")
        if not isinstance(group, dict):
            continue
        directory = group.get("d")
        if directory is not None and (
            not isinstance(directory, str)
            or len(directory) != 8
            or not directory[:3].isdecimal()
            or directory[3:] != "GOPRO"
        ):
            raise ContractError("replay media directory is not in NNNGOPRO form")
        items = group.get("fs")
        if not isinstance(items, list):
            continue
        for item in items:
            _reject_unknown_fields(item, MEDIA_FILE_FIELDS, label="media file entry")
            if not isinstance(item, dict):
                continue
            for field in MEDIA_UNSIGNED_DECIMAL_FIELDS:
                if field in item and item[field] is not None:
                    if not _is_bounded_decimal_string(item[field]):
                        raise ContractError(
                            f"media file entry {field} must be a bounded decimal string"
                        )
            if "ls" in item and item["ls"] is not None:
                if not _is_bounded_decimal_string(
                    item["ls"],
                    allow_negative_one=True,
                ):
                    raise ContractError(
                        "media file entry ls must be -1 or a bounded decimal string"
                    )


class ReplayReadAdapter:
    def __init__(self, fixture: dict[str, Any]) -> None:
        try:
            strict_json_dumps(fixture)
        except (TypeError, ValueError) as exc:
            raise ContractError("replay fixture contains non-JSON values") from exc
        snapshot = deepcopy(fixture)
        fixture_fields = set(snapshot)
        if fixture_fields != FIXTURE_FIELDS:
            unknown_fields = sorted(
                str(field) for field in fixture_fields if field not in FIXTURE_FIELDS
            )
            raise ContractError(
                "replay fixture fields differ: "
                f"missing={sorted(FIXTURE_FIELDS - fixture_fields)}, "
                f"unknown={unknown_fields}"
            )
        if snapshot.get("schema_version") != "aoa_gopro_read_replay_fixture_v1":
            raise ContractError("unsupported replay fixture schema")
        context = snapshot.get("context")
        if not isinstance(context, dict):
            raise ContractError("replay fixture has no context object")
        context_fields = set(context)
        if context_fields != CONTEXT_FIELDS:
            unknown_context_fields = sorted(
                str(field) for field in context_fields if field not in CONTEXT_FIELDS
            )
            raise ContractError(
                "replay context fields differ: "
                f"missing={sorted(CONTEXT_FIELDS - context_fields)}, "
                f"unknown={unknown_context_fields}"
            )
        responses = snapshot.get("responses")
        if not isinstance(responses, dict):
            raise ContractError("replay fixture has no responses object")
        unknown = sorted(
            str(route) for route in responses if route not in ALLOWED_READ_PATHS
        )
        missing = sorted(set(ALLOWED_READ_PATHS) - set(responses))
        if unknown or missing:
            raise ContractError(
                f"replay routes differ: missing={missing}, unknown={unknown}"
            )
        assert_public_safe(snapshot)
        _validate_response_shapes(responses)
        self._fixture = snapshot
        self.fixture_digest = canonical_digest(snapshot)
        self._responses = responses

    @property
    def fixture(self) -> dict[str, Any]:
        """Return an isolated copy of the content-addressed replay snapshot."""

        return deepcopy(self._fixture)

    @classmethod
    def from_path(cls, path: str | Path) -> "ReplayReadAdapter":
        fixture_path = Path(path)
        try:
            fixture = strict_json_loads(fixture_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ContractError(f"invalid replay fixture: {fixture_path}") from exc
        if not isinstance(fixture, dict):
            raise ContractError("replay fixture must be a JSON object")
        return cls(fixture)

    def get_json(self, path: str) -> dict[str, Any]:
        if path not in ALLOWED_READ_PATHS:
            raise ContractError(f"route is not read-allowlisted: {path}")
        value = self._responses[path]
        if not isinstance(value, dict):
            raise ContractError(f"replay response is not an object: {path}")
        return deepcopy(value)
