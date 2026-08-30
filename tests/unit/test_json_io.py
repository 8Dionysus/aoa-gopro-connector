from __future__ import annotations

import json

import pytest

from aoa_gopro_connector.json_io import strict_json_dumps, strict_json_loads


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_strict_json_loads_rejects_nonstandard_numeric_constants(
    constant: str,
) -> None:
    with pytest.raises(json.JSONDecodeError, match="non-standard JSON"):
        strict_json_loads(f'{{"value": {constant}}}')


def test_strict_json_loads_rejects_float_overflow() -> None:
    with pytest.raises(json.JSONDecodeError, match="finite float range"):
        strict_json_loads('{"value": 1e999}')


def test_strict_json_loads_rejects_duplicate_object_keys() -> None:
    with pytest.raises(json.JSONDecodeError, match="duplicate JSON object key"):
        strict_json_loads('{"value": 1, "value": 2}')


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_strict_json_dumps_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="Out of range float"):
        strict_json_dumps({"value": value})
