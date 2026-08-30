from __future__ import annotations

from decimal import Decimal

import pytest

from aoa_gopro_connector.digest import attach_digest, canonical_digest, verify_digest
from aoa_gopro_connector.errors import ContractError
from aoa_gopro_connector.json_io import strict_json_loads


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


def test_digest_preserves_distinct_decimal_values_after_json_decode() -> None:
    approved = attach_digest({"value": Decimal("0.0")}, "digest")
    attacked = strict_json_loads('{"value": 1e-9999}')
    attacked["digest"] = approved["digest"]

    with pytest.raises(ContractError, match="digest mismatch"):
        verify_digest(attacked, "digest")


def test_programmatic_float_and_equivalent_decimal_share_canonical_digest() -> None:
    assert canonical_digest({"value": 0.1}) == canonical_digest(
        {"value": Decimal("0.1")}
    )
