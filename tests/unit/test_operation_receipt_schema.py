from __future__ import annotations

import pytest

from aoa_gopro_connector.digest import ZERO_DIGEST
from aoa_gopro_connector.errors import ContractError
from aoa_gopro_connector.schema import validate_document


PROFILE_DIGEST = "sha256:" + "1" * 64
STATE_DIGEST = "sha256:" + "2" * 64


def _receipt(outcome: str = "succeeded") -> dict[str, object]:
    return {
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
            "state_digest": STATE_DIGEST,
        },
        "after": {
            "observed_at": "2026-08-30T05:00:01Z",
            "state": {"recording": True},
            "state_digest": STATE_DIGEST,
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
        "error": None,
        "artifact_refs": [],
        "receipt_digest": ZERO_DIGEST,
    }


def test_successful_receipt_has_observed_satisfied_postcondition() -> None:
    validate_document("operation_receipt", _receipt())


@pytest.mark.parametrize(
    "verdicts",
    [
        [],
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
    validate_document("operation_receipt", receipt)
