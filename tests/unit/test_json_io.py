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


def test_strict_json_loads_rejects_oversized_integer() -> None:
    encoded = '{"value": ' + "9" * 5000 + "}"
    with pytest.raises(json.JSONDecodeError, match="integer exceeds"):
        strict_json_loads(encoded)


def test_strict_json_loads_rejects_duplicate_object_keys() -> None:
    with pytest.raises(json.JSONDecodeError, match="duplicate JSON object key"):
        strict_json_loads('{"value": 1, "value": 2}')


@pytest.mark.parametrize(
    "encoded",
    [r'{"value": "\ud800"}', r'{"\udfff": "value"}'],
)
def test_strict_json_loads_rejects_lone_surrogate(encoded: str) -> None:
    with pytest.raises(json.JSONDecodeError, match="lone surrogate"):
        strict_json_loads(encoded)


def test_strict_json_loads_accepts_valid_surrogate_pair() -> None:
    assert strict_json_loads(r'{"value": "\ud83d\ude00"}') == {"value": "😀"}


def test_strict_json_loads_translates_decoder_recursion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_recursively(*args: object, **kwargs: object) -> object:
        raise RecursionError("synthetic decoder recursion")

    monkeypatch.setattr(json, "loads", fail_recursively)
    with pytest.raises(json.JSONDecodeError, match="nesting exceeds decoder limit"):
        strict_json_loads("{}")


@pytest.mark.parametrize(
    "value",
    [float("nan"), float("inf"), float("-inf")],
)
def test_strict_json_dumps_rejects_non_finite_numbers(value: float) -> None:
    with pytest.raises(ValueError, match="Out of range float"):
        strict_json_dumps({"value": value})


def test_strict_json_dumps_rejects_lone_surrogate() -> None:
    with pytest.raises(ValueError, match="lone surrogate"):
        strict_json_dumps({"value": "\ud800"})


def test_strict_json_dumps_still_rejects_circular_reference() -> None:
    value: list[object] = []
    value.append(value)
    with pytest.raises(ValueError, match="Circular reference"):
        strict_json_dumps(value)
