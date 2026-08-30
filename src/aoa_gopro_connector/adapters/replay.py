"""Public-safe deterministic read replay."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from ..errors import ContractError
from ..json_io import strict_json_dumps, strict_json_loads
from ..redaction import assert_public_safe
from .base import ALLOWED_READ_PATHS


FIXTURE_FIELDS = {"schema_version", "fixture_id", "context", "responses"}
CONTEXT_FIELDS = {
    "observed_at",
    "topology",
    "discovery",
    "protocol_version",
    "firmware_posture",
}


class ReplayReadAdapter:
    def __init__(self, fixture: dict[str, Any]) -> None:
        try:
            strict_json_dumps(fixture)
        except (TypeError, ValueError) as exc:
            raise ContractError("replay fixture contains non-JSON values") from exc
        fixture_fields = set(fixture)
        if fixture_fields != FIXTURE_FIELDS:
            raise ContractError(
                "replay fixture fields differ: "
                f"missing={sorted(FIXTURE_FIELDS - fixture_fields)}, "
                f"unknown={sorted(fixture_fields - FIXTURE_FIELDS)}"
            )
        if fixture.get("schema_version") != "aoa_gopro_read_replay_fixture_v1":
            raise ContractError("unsupported replay fixture schema")
        context = fixture.get("context")
        if not isinstance(context, dict):
            raise ContractError("replay fixture has no context object")
        context_fields = set(context)
        if context_fields != CONTEXT_FIELDS:
            raise ContractError(
                "replay context fields differ: "
                f"missing={sorted(CONTEXT_FIELDS - context_fields)}, "
                f"unknown={sorted(context_fields - CONTEXT_FIELDS)}"
            )
        responses = fixture.get("responses")
        if not isinstance(responses, dict):
            raise ContractError("replay fixture has no responses object")
        unknown = sorted(set(responses) - set(ALLOWED_READ_PATHS))
        missing = sorted(set(ALLOWED_READ_PATHS) - set(responses))
        if unknown or missing:
            raise ContractError(
                f"replay routes differ: missing={missing}, unknown={unknown}"
            )
        assert_public_safe(fixture)
        self.fixture = fixture
        self._responses = responses

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
