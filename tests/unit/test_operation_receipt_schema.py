from __future__ import annotations

import pytest

from aoa_gopro_connector.digest import ZERO_DIGEST, attach_digest, canonical_digest
from aoa_gopro_connector.errors import ContractError
from aoa_gopro_connector.schema import validate_document


PROFILE_DIGEST = "sha256:" + "1" * 64


def _receipt(outcome: str = "succeeded") -> dict[str, object]:
    payload = {
        "schema_version": "aoa_gopro_operation_receipt_v1",
        "receipt_id": "receipt:fixture-record",
        "operation_id": "operation:fixture-record",
        "plan_digest": ZERO_DIGEST,
        "outcome": outcome,
        "started_at": "2026-08-30T05:00:00Z",
        "finished_at": "2026-08-30T05:00:01Z",
        "actor_version": "fixture-actor-v1",
        "adapter": {
            "kind": "fixture",
            "version": "1",
            "topology": "replay",
            "capability_profile_digest": PROFILE_DIGEST,
        },
        "before": {
            "observed_at": "2026-08-30T05:00:00Z",
            "state": {"recording": False},
            "state_digest": canonical_digest({"recording": False}),
        },
        "after": {
            "observed_at": "2026-08-30T05:00:01Z",
            "state": {"recording": True},
            "state_digest": canonical_digest({"recording": True}),
        },
        "steps": [
            {
                "step_id": "effect",
                "status": "succeeded",
                "observed_at": "2026-08-30T05:00:00Z",
                "observation_ref": "observation:fixture-ack",
            }
        ],
        "postcondition_verdicts": [
            {
                "kind": "recording",
                "verdict": "satisfied",
                "observation_ref": "observation:fixture-state",
            }
        ],
        "recovery": {
            "attempted": False,
            "attempt_count": 0,
            "result": "not_needed",
        },
        "error": (
            None
            if outcome == "succeeded"
            else {
                "code": "fixture_failure",
                "message": "synthetic failure",
                "retryable": False,
            }
        ),
        "artifact_refs": [],
        "receipt_digest": ZERO_DIGEST,
    }
    return attach_digest(payload, "receipt_digest")


def test_successful_receipt_has_observed_satisfied_postcondition() -> None:
    validate_document("operation_receipt", _receipt())


@pytest.mark.parametrize(
    "verdicts",
    [
        [],
        [
            {
                "kind": "recording",
                "verdict": "satisfied",
                "observation_ref": None,
            }
        ],
        [
            {
                "kind": "recording",
                "verdict": "unknown",
                "observation_ref": None,
            }
        ],
        [
            {
                "kind": "recording",
                "verdict": "not_satisfied",
                "observation_ref": "observation:fixture-state",
            }
        ],
    ],
)
def test_successful_receipt_rejects_unproven_postconditions(
    verdicts: list[dict[str, object]],
) -> None:
    receipt = _receipt()
    receipt["postcondition_verdicts"] = verdicts
    with pytest.raises(ContractError, match="postcondition_verdicts"):
        validate_document("operation_receipt", receipt)


def test_failed_receipt_may_preserve_unknown_postcondition() -> None:
    receipt = _receipt("failed")
    receipt["postcondition_verdicts"] = []
    receipt = attach_digest(receipt, "receipt_digest")
    validate_document("operation_receipt", receipt)


def test_successful_receipt_rejects_error_or_failed_recovery() -> None:
    receipt = _receipt()
    receipt["error"] = {
        "code": "contradiction",
        "message": "success cannot carry an error",
        "retryable": False,
    }
    with pytest.raises(ContractError, match="error"):
        validate_document("operation_receipt", receipt)

    receipt = _receipt()
    receipt["recovery"] = {
        "attempted": True,
        "attempt_count": 1,
        "result": "failed",
    }
    with pytest.raises(ContractError, match="recovery.result"):
        validate_document("operation_receipt", receipt)


def test_non_success_receipt_requires_typed_error() -> None:
    receipt = _receipt("indeterminate")
    receipt["error"] = None
    with pytest.raises(ContractError, match="error"):
        validate_document("operation_receipt", receipt)


@pytest.mark.parametrize(
    "recovery",
    [
        {"attempted": False, "attempt_count": 5, "result": "recovered"},
        {"attempted": True, "attempt_count": 0, "result": "not_needed"},
    ],
)
def test_recovery_receipt_rejects_contradictory_fields(
    recovery: dict[str, object],
) -> None:
    receipt = _receipt()
    receipt["recovery"] = recovery
    with pytest.raises(ContractError, match="recovery.attempt_count"):
        validate_document("operation_receipt", receipt)


def test_recovery_receipt_accepts_attempted_recovery() -> None:
    receipt = _receipt()
    receipt["recovery"] = {
        "attempted": True,
        "attempt_count": 1,
        "result": "recovered",
    }
    receipt = attach_digest(receipt, "receipt_digest")
    validate_document("operation_receipt", receipt)


def test_receipt_rejects_finished_at_before_started_at() -> None:
    receipt = _receipt()
    receipt["finished_at"] = "2026-08-30T04:59:59Z"
    with pytest.raises(ContractError, match="finished_at"):
        validate_document("operation_receipt", receipt)


def test_receipt_timeline_compares_instants_across_offsets() -> None:
    receipt = _receipt()
    receipt["started_at"] = "2026-08-30T05:00:00+01:00"
    receipt["finished_at"] = "2026-08-30T04:00:00Z"
    receipt["steps"][0]["observed_at"] = "2026-08-30T04:00:00Z"
    receipt["before"]["observed_at"] = "2026-08-30T05:00:00+01:00"
    receipt["after"]["observed_at"] = "2026-08-30T04:00:00Z"
    receipt = attach_digest(receipt, "receipt_digest")
    validate_document("operation_receipt", receipt)


@pytest.mark.parametrize(
    "observed_at",
    ["2026-08-30T04:59:59Z", "2026-08-30T05:00:02Z"],
)
def test_receipt_rejects_step_outside_operation_interval(observed_at: str) -> None:
    receipt = _receipt()
    receipt["steps"][0]["observed_at"] = observed_at
    with pytest.raises(ContractError, match="steps.0.observed_at"):
        validate_document("operation_receipt", receipt)


def test_receipt_validation_rejects_stale_digest() -> None:
    receipt = _receipt()
    receipt["actor_version"] = "fixture-actor-v2"
    with pytest.raises(ContractError, match="receipt_digest"):
        validate_document("operation_receipt", receipt)


@pytest.mark.parametrize("snapshot_field", ["before", "after"])
def test_receipt_validation_rejects_stale_state_snapshot_digest(
    snapshot_field: str,
) -> None:
    receipt = _receipt()
    receipt[snapshot_field]["state"]["recording"] = "mutated"
    receipt = attach_digest(receipt, "receipt_digest")
    with pytest.raises(ContractError, match=f"{snapshot_field}.state_digest"):
        validate_document("operation_receipt", receipt)


def test_receipt_rejects_reversed_state_snapshot_chronology() -> None:
    receipt = _receipt()
    receipt["before"]["observed_at"] = "2026-08-30T05:00:01Z"
    receipt["after"]["observed_at"] = "2026-08-30T05:00:00Z"
    receipt = attach_digest(receipt, "receipt_digest")
    with pytest.raises(ContractError, match="after.observed_at"):
        validate_document("operation_receipt", receipt)


def test_receipt_rejects_after_snapshot_after_completion() -> None:
    receipt = _receipt()
    receipt["after"]["observed_at"] = "2026-08-30T05:00:02Z"
    receipt = attach_digest(receipt, "receipt_digest")
    with pytest.raises(ContractError, match="after.observed_at"):
        validate_document("operation_receipt", receipt)
