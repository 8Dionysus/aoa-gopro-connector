from __future__ import annotations

import pytest

from aoa_gopro_connector.digest import attach_digest, canonical_digest, verify_digest
from aoa_gopro_connector.errors import ContractError


def test_digest_is_stable_across_mapping_order() -> None:
    first = attach_digest({"b": 2, "a": 1}, "digest")
    second = attach_digest({"a": 1, "b": 2}, "digest")
    assert first["digest"] == second["digest"]
    verify_digest(first, "digest")


def test_digest_detects_mutation() -> None:
    packet = attach_digest({"value": 1}, "digest")
    packet["value"] = 2
    with pytest.raises(ContractError, match="digest mismatch"):
        verify_digest(packet, "digest")


def test_digest_translates_lone_surrogate_encoding_failure() -> None:
    with pytest.raises(ContractError, match="canonically encoded"):
        canonical_digest({"value": "\ud800"})
