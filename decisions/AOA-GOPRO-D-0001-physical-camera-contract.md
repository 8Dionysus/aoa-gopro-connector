# AOA-GOPRO-D-0001: physical camera contract

## Status

Accepted.

## Context

Sibling AoA connectors mostly turn external information sources into evidence,
indexes, graphs, and answers. A GoPro is instead a stateful physical sensor and
actuator with power, ownership, transport, recording, media finalization,
health, and recovery consequences.

## Decision

Reuse family repo hygiene, policy, schema, validation, evidence, storage, and
publication posture. Model the connector itself around composed camera state,
one leased actor, explicit operation plans, postcondition receipts, media
integrity, and replaceable transport/perception adapters.

## Consequence

Search, answer, crawl, and graph contracts are not required merely for family
symmetry. Runtime integration must preserve read, candidate, approval, effect,
and receipt as distinct layers.
